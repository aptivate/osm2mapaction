# This file was originally generated by PyScripter's unitest wizard

import unittest
import xlrd
from configengine import _AttribList, _SelectClause
from configengine import xwalk_from_raw_config
from configengine import ConfigXWalk
from configengine import RawConfigIterator
import fixtures


class TestRawConfigIterator(unittest.TestCase):

    def setUp(self):
        self.rci = RawConfigIterator(fixtures.rawconf_good)

    def tearDown(self):
        pass

    def test__iter__(self):
        self.assertEquals(self.rci, self.rci.__iter__())

    def test_next(self):
        # There are 18 rows in fixtures.rawconf_good
        # Each row contains 16 cells
        for x in range(0, 18):
            nextrow = self.rci.next()
            # print len(nextrow)
            self.assertIsInstance(nextrow, list, "Expected another row to be returned as a list object.")
            self.assertEqual(len(nextrow), 16, "Expected row (list obj) to contain 16 cells.")

        self.assertRaises(StopIteration, self.rci.next)

    def test_parse_cell_values(self):
        # special handling of '*' with None
        self.assertEqual(RawConfigIterator._parse_cell_values(42), None)
        # other ints should be returned
        self.assertEqual(RawConfigIterator._parse_cell_values(41), 41)
        self.assertEqual(RawConfigIterator._parse_cell_values(u' a'), u'a')
        self.assertEqual(RawConfigIterator._parse_cell_values(u'a '), u'a')
        self.assertEqual(RawConfigIterator._parse_cell_values(u''), u'')


class TestConfigXWalk(unittest.TestCase):

    def setUp(self):
        self.configxwalk = ConfigXWalk(fixtures.rawconf_good, "wrl", "su")

    def tearDown(self):
        pass

    def test_populate_scratch_table(self):
        scratch = self.configxwalk.cursor.execute('''select * from scratch''').fetchall()
        self.assertEquals(scratch, fixtures.scratch_table_good, "Scratch table incorrect")

    def test_populate_shpfile_table(self):
        shpf_list = self.configxwalk.cursor.execute('''select * from shpf_list''').fetchall()
        for x in range(0, len(shpf_list)):
            self.assertEquals(shpf_list[x], fixtures.shpf_list_table_good[x],
                              "Shapefile name table incorrect, row {}".format(x))

    def test_get_xwalk(self):
        shpf_list = self.configxwalk.get_xwalk()
        self.assertEquals(shpf_list, fixtures.shpf_list_table_good)

    def test_create_shpf_name(self):
        testname = "abc_defg_hij_py_s1_osm_pp.shp"
        # u'{geo_extd}_{cat}_{thm}_{geom_type}_{scale}_osm_pp.shp'
        extd = "abc"
        cat = "defg"
        thm = "hij"
        goem = "py"
        sca = "s1"
        newname = ConfigXWalk._create_shpf_name(extd, cat, thm, goem, sca)
        self.assertEqual(newname, testname, "Shapefile name incorrectly formed")


class TestAttribList(unittest.TestCase):

    def setUp(self):
        self.al = _AttribList()

    def tearDown(self):
        pass

    def test_class_function(self):
        """
        This test is a functional test of the whole class not of individual methods. The main purpose of the case is to
        maintian state during the aggreegation process. Therefore it is difficult to meaningfully subdivide tests.
        :return:
        """
        for arg in fixtures.attrib_list_args:
            self.al.step(arg)

        self.assertEqual(self.al.finalize(), fixtures.attrib_list_result)


class TestSelectClause(unittest.TestCase):

    def setUp(self):
        pass

    def tearDown(self):
        pass

    def test_class_function(self):
        """
        This test is a functional test of the whole class not of individual methods. The main purpose of the case is to
        maintian state during the aggreegation process. Therefore it is difficult to meaningfully subdivide tests.
        :return:
        """
        for args, result in fixtures.select_clause_args_and_result_pairs:
            sc = _SelectClause()
            for key, val in args:
                sc.step(key, val)

            self.assertEqual(sc.finalize(), result)


class TestGlobalFunctions(unittest.TestCase):

    def setUp(self):
        pass

    def test_xwalk_from_raw_config(self):
        """
        This is just an intergration test for the whole of the configengine module
        :return:
        """
        result = xwalk_from_raw_config(fixtures.rawconf_good, "wrl", "su")
        # print type(result)
        self.assertIsInstance(result, list)
