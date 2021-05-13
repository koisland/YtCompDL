import unittest
import main
from main import YTCompDL


class TestMain(unittest.TestCase):

    def setUp(self):
        pass

    def test_find_timestamps(self):
        self.assertEquals(YTCompDL.find_timestamps(), ["", "", "", ""])
