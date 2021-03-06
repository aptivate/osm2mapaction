# -----------------------------------------------------------------------------
# Name:        configengine
# Purpose:
#
# Author:      asmith
#
# Created:     20/08/2014
# Copyright:   MapAction 2014
# Licence:     GPL v3
# -----------------------------------------------------------------------------

import sqlite3
import logging
import json
import re
logging.basicConfig(level=logging.INFO)


class RawConfigIterator:
    """
    Iterator for reading the raw config table into a SQL insert statement.
    """
    def __init__(self, area2d):
        (self.mysheet, self.rowxlo, self.rowxhi, self.colxlo,
         self.colxhi) = area2d
        self.row_current = self.rowxlo

    def __iter__(self):
        return self

    @staticmethod
    def _parse_cell_values(val):
        """
        Convert values to UTF8, handling any oddities
        """
        # replace '*' (utf-8 char 42) with None
        if (type(val) == int) and (val == 42):
            return None
        elif type(val) == unicode:
            return val.strip()
        else:
            return val

    def next(self):
        if self.row_current >= self.rowxhi:
            raise StopIteration
        else:
            self.row_current += 1
            u_rtn_list = self.mysheet.row_values(
                self.row_current - 1, self.colxlo, self.colxhi)
            utf8_rtn_list = map(RawConfigIterator._parse_cell_values, u_rtn_list)
            logging.debug(utf8_rtn_list)
            return utf8_rtn_list


class ConfigXWalk:
    def _init_db_tables(self):
        """Create three tables in the DB - config, scratch and shpf_list.

        - "config": An exact copy of the relevant table in the config file
        - "scratch": A temporay working area.
        - "shpf_list": Details of the shapefiles to be created. One row per
            shapefile.

        :return: None

        """
        cur = self.cursor
        cur.executescript('''
            create table config (
                osm_key_name text,
                osm_key_value text,
                element_icon text,
                comment text,
                useful text,
                data_category text,
                cat_value text,
                data_theme text,
                theme_value text,
                conforms_to_hierarchy text,
                osm_element text,
                geom_str text,
                pt text,
                ln text,
                py text,
                rel text
            );

            create table scratch (
                osm_key_name text,
                osm_key_value text,
                cat_value text,
                theme_value text,
                osm_element,
                geom_type text
            );

            create table shpf_list (
                shpfile_name text,
                cat_value text,
                geom_type text,
                attrib_str text,
                condition_str text
            );

            ''')

    def _populate_config_table(self, area2d):
        """
        Copy the relevant table in the config file into the "config" table

        :param area2d: As from the xlrd module
        :return: None
        """
        cur = self.cursor

        cur.executemany('''
            INSERT INTO config
                (osm_key_name,
                osm_key_value,
                element_icon,
                comment,
                useful,
                data_category,
                cat_value,
                data_Theme,
                theme_value,
                conforms_to_hierarchy,
                osm_element,
                geom_str,
                pt,
                ln,
                py,
                rel)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''', RawConfigIterator(area2d))

    def _populate_scratch_table(self):
        """
        Duplicate config table which has been normalised wrt geometry type.

        :return: None

        """
        cur = self.cursor

        for geom in ("pt", "ln", "py", "rel"):
            u_sql = '''
                INSERT INTO scratch (
                    osm_key_name,
                    osm_key_value,
                    cat_value,
                    theme_value,
                    osm_element,
                    geom_type
                )
                select
                    osm_key_name,
                    osm_key_value,
                    cat_value,
                    theme_value,
                    osm_element,
                    '{geom}'
                from config where
                    config.geom_str like '%{geom}%'
                '''.format(geom=geom)
            cur.execute(u_sql)

    def _populate_shpfile_table(self, geo_extd, scale):
        """
        Fill list of shapefile, aggregating details of individual attributes.

        :param geo_extd:
        :param scale:
        :return: None

        """
        # TODO no longer using the cmdline_str column so remove it.
        cur = self.cursor

        u_sql = u'''
            INSERT INTO shpf_list (
                shpfile_name,
                cat_value,
                geom_type,
                attrib_str,
                condition_str
            )
            SELECT
                shpf_name(
                    '{geo_extd}', scratch.cat_value, scratch.theme_value,
                    scratch.geom_type, '{scale}'
                ),
                scratch.cat_value,
                scratch.geom_type,
                attriblist(scratch.osm_key_name),
                condition_clause(scratch.osm_key_name, scratch.osm_key_value)
            FROM scratch
            GROUP BY
                shpf_name(
                    '{geo_extd}', scratch.cat_value, scratch.theme_value,
                    scratch.geom_type, '{scale}'
                ),
                scratch.cat_value,
                scratch.geom_type
            '''.format(geo_extd=geo_extd, scale=scale)

        cur.execute(u_sql)

    @staticmethod
    def _create_shpf_name(geo_extd, data_cat, data_thm, geom_type, scale):
        # geoextent_datacategory_datatheme_datatype[_scale]_source[_permission][_FreeText]
        output_filename = "{geo_extd}_{cat}_{thm}_{geom_type}_{scale}_osm_pp.shp".format(
            geo_extd=geo_extd,
            cat=data_cat,
            thm=data_thm,
            geom_type=geom_type,
            scale=scale
        )
        return output_filename

    def _init_db_funcs(self):
        """
        Initialise in-memory DB with required custom & aggregation functions.

        The required functions:
        - Generate the DNC compliant shapefile name
        - Generate the SQL select clause to select the relevant features into
            each shapefile
        - Generate the SQL attribute list to include the relevant atributes
            into each shapefile

        :return: None
        """
        self.db.create_function("shpf_name", 5, ConfigXWalk._create_shpf_name)
        self.db.create_aggregate("attriblist", 1, _AttribList)
        self.db.create_aggregate("condition_clause", 2, _SelectClauseDict)

    def get_xwalk(self):
        """
        Return a table describing the XWalk between OSM tag and MapAction DNC.

        :return: A table containing one row per shapefile to be created. The
            tables colums are:
            - shpfile_name: The name of the shapefile
            - cat_value: The name of the data category (typicall used as the
                name of the output directory)
            - geom_type: The geometery type.....
            - attrib_str: The clause of a SQL statement specifying which
                attributes should be includes in the shapefile.
            - condition_str: The clause of a SQL statement specifying the
                relevant features into include in each shapefile.

        """
        # TODO update docstring. Does geom_type refer to OGR geomtype or SHP
        # geom_type?
        cur = self.cursor
        return cur.execute('''select
                    shpfile_name,
                    cat_value,
                    geom_type,
                    attrib_str,
                    condition_str
            from shpf_list''').fetchall()

    def __init__(self, area2d, geoextent_clause, scale_clause):
        """Constructor for ConfigXWalk.

        Create an in-memory database, copy the contents of the config file and
        manipulate it is to create a table containing one row per shapefile to
        be created.

        :param area2d: An excel Named Range as specificed here:
        https://secure.simplistix.co.uk/svn/xlrd/trunk/xlrd/doc/xlrd.html?p=4966#__init__.Name.area2d-method
        :param geoextent_clause: A string of the geoextent clause for the
            geographic area being converted.
        :param scale_clause: A string of the scale clause suitable for the
            features being converted.
        """
        self.db = sqlite3.connect(':memory:')
        self.cursor = self.db.cursor()
        self._init_db_funcs()
        self._init_db_tables()
        self.db.commit()
        self._populate_config_table(area2d)
        self._populate_scratch_table()
        self._populate_shpfile_table(geoextent_clause, scale_clause)
        self.db.commit()


class _AttribList:
    """
    Creates comma delimited list of attribute names for SELECT.

    Return object is a json-serialized version of the python list of attrib names.
    Decode with json.loads(obj).

    See:
    docs.python.org/2/library/sqlite3.html#sqlite3.Connection.create_aggregate
    """
    def __init__(self):
        self.set_attribs = set()

    def step(self, value):
        if len(value) > 0:
            self.set_attribs.add(value)

    def finalize(self):
        # returning (or rather, using) a single comma-joined string of attrib
        # names is a bit risky because if we are looking for an attribute like
        # "id" this will pull out attributes like "orchid". The client code
        # _should_ be more sensible, but if we return a set then we force it to be.
        # Actually we do a list as json can't serialize set
        return json.dumps(list(self.set_attribs))
        #return ", ".join(sorted(self.set_attribs))

class _SelectClauseDict:
    """
    Generates dictionary of components of a where clause to select contents of a shapefile.

    Dictionary is keyed by the column name and values are the where clause
    components in which that column name is mentioned. Dictionary is returned
    as a json-encoded string for compatibility with the sqlite create_aggregate
    usage. Decode with json.loads(obj)

    Certain values (eg '*' and 'user defined') are filtered out.

    See:
    https://docs.python.org/2/library/sqlite3.html#sqlite3.Connection.create_aggregate
    """

    def __init__(self):
        self.query_args = dict()
        self.exclude_keys = set()

    def step(self, osm_key, osm_value):
        # need to quote any fieldnames starting with digit, including a space, or
        # possibly some other characters too
        # e.g. 'public transport', '4wd_only'
        # can't make this check work as a separate function for some reason
        dodgyRE = '(^\d)|_|\s|:'
        keyNeedsQualifying = False
        if re.search(dodgyRE, osm_key):
            keyNeedsQualifying = True

        if (type(osm_value) == unicode) and (
                osm_value.lower() in {u'*', u'user defined', u'number', u'url or article title'}):
            self.exclude_keys.add(osm_key)
        else:
            if "/" in osm_value:
                trySplitChar = u'/'
            else:
                # some things in the sheet are comma delimited instead, e.g. voltage
                trySplitChar = u','
            for val in osm_value.split(trySplitChar):
                # TODO: This might be dangerous, because you can't be
                # sure that the val or key won't contain a quote, for
                # example.
                # FIXME: Use params to execute?
				# must be single quotes outside double quotes
                if keyNeedsQualifying:
                    qualKey = '"{key}"'.format(key=osm_key)
                else:
                    qualKey = osm_key

                unique_clause = u"{key}='{val}'".format(
                    key=qualKey, val=val.strip()
                )
                # we build query_args the opposite way round i.e. keys are the
                # col name not the clause: don't know why it was the other way
                # round anyway
                if osm_key not in self.query_args:
                    self.query_args[osm_key] = [unique_clause]
                else:
                    self.query_args[osm_key].append(unique_clause)

    def finalize(self):
        dodgyRE = '(^\d)|_|\s|:'
        for osm_key in self.exclude_keys:
            keyNeedsQualifying = False
            if re.search(dodgyRE, osm_key):
                keyNeedsQualifying = True

            if keyNeedsQualifying:
                # must be single quotes outside double quotes
                qualKey = '"{key}"'.format(key=osm_key)
            else:
                qualKey = osm_key

            self.query_args[osm_key] =(
                [u"({key} IS NOT null AND {key} NOT IN ('', 'None'))"
                    .format(key=qualKey)
                    ]
                )
        # return (to the column in the DB!) a string representation of the dict
        # which the ogrwrapper code will be able to reconstruct once it knows
        # what's actually in the data so it can use only the relevant clauses
        return json.dumps(self.query_args)

class _SelectClause:
    """
    Generates WHERE clause, to select the contents of a shapefile.

    Certain values (eg '*' and 'user defined') are filtered out.
    Class will be redundant if _SelectClauseDict is ok

    See:
    https://docs.python.org/2/library/sqlite3.html#sqlite3.Connection.create_aggregate
    """
    def __init__(self):
        self.query_args = dict()
        self.exclude_keys = set()
        # probably a better way of getting this to the constructor but i'm unsure how
        self.tblName = 'scratch'

    def step(self, osm_key, osm_value):
        if (type(osm_value) == unicode) and (
                osm_value.lower() in {u'*', u'user defined', u'number', u'url or article title'}):
            self.exclude_keys.add(osm_key)
        else:
            for val in osm_value.split(u'/'):
                # TODO: This might be dangerous, because you can't be
                # sure that the val or key won't contain a quote, for
                # example.
                # FIXME: Use params to execute?
                unique_clause = u"{key}='{val}'".format(
                    key=osm_key, val=val.strip()
                )
                self.query_args[unique_clause] = osm_key

    def finalize(self):
        cleaned_pairs = set()
        for osm_key in self.exclude_keys:
            cleaned_pairs.add(
                # investigation of why sometimes all features go through: looking at
                # whether it was a wrong "null" being exposed.
                # This doesn't seem to be the issue so could go back to is not null
                # alone
                u"({key} IS NOT null AND {key} NOT IN ('', 'None'))"
                .format(key=osm_key)
            )
        for unique_clause, osm_key in self.query_args.iteritems():
            if osm_key not in self.exclude_keys:
                cleaned_pairs.add(unique_clause)
        if len(cleaned_pairs) > 0:
            return u" OR ".join(sorted(cleaned_pairs))
        else:
            return u''


def xwalk_from_raw_config(raw_config, geoextent_clause, scale_clause):
    """Wrap an ConfigXWalk instance and return the XWalk table

    :param raw_config:
    :param geoextent_clause:
    :param scale_clause:
    :return: A XWalk table, with a row for each attribute for each shapefile to
        be generated.

    """
    return ConfigXWalk(raw_config, geoextent_clause, scale_clause).get_xwalk()
