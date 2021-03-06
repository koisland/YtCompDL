import subprocess
import unittest
from ytcompdl.yt_comp_dl import YTCompDL


class TestMain(unittest.TestCase):

    def setUp(self):
        self.start_ts = """
            20:45 Absurd (理不尽)
            23:20 Abnormal Situation (異常事態)
            25:33 Own Words (自分の言葉)
        """
        self.dur_ts = """
            4:35 - 7:10 "Concerning Hobbits"
            7:11 - 7:44	"The Seduction of the Ring"
            7:45  - 10:25 "A Shortcut To Mushrooms"
        """

    def test_find_timestamps(self):
        self.assertEqual(list(YTCompDL.find_timestamps(self.start_ts)),
                         [[('', '20:45', 'Absurd (理不尽)')],
                          [('', '23:20', 'Abnormal Situation (異常事態)')],
                          [('', '25:33', 'Own Words (自分の言葉)')]])

        self.assertEqual(list(YTCompDL.find_timestamps(self.dur_ts)),
                         [[('', '4:35', '7:10', 'Concerning Hobbits')],
                          [('', '7:11', '7:44', 'The Seduction of the Ring')],
                          [('', '7:45', '10:25', 'A Shortcut To Mushrooms')]])

    def test_format_timestamps(self):
        pass

    def test_validate_timestamps(self):
        pass

    def test_download(self):
        pass

    def test_format_opt_metadata(self):
        apply_metadata_cmd = []
        show_metadata_cmd = ['ffmpeg', '-i', '', '-f', 'ffmetadata', 'test_metadata.txt']
        subprocess.call(show_metadata_cmd, shell=False)
