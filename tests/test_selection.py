import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))

import random
import unittest
from datetime import date, timedelta

from selection import canonical_names, day_number, select, selection_index


class SelectionTests(unittest.TestCase):
    def test_cycles_are_permutations_and_boundaries_do_not_repeat(self):
        for count in list(range(1, 65)) + [100, 250, 1000]:
            for cycle in [0, 1, 2, 10, 100, 1000]:
                values = [selection_index(count, day)
                          for day in range(cycle * count, (cycle + 1) * count)]
                self.assertEqual(set(values), set(range(count)), (count, cycle))
                if count > 1:
                    self.assertTrue(all(a != b for a, b in zip(values, values[1:])))
                    if cycle:
                        self.assertNotEqual(values[0], selection_index(count, cycle * count - 1))

    def test_enumeration_order_does_not_affect_selection(self):
        names = ['wallpaper-%06d.png' % i for i in range(1, 18)] + [
            'A summer day.JPG', 'café 🍁.png', 'quote " photo.png', 'same base.jpg',
            'same base.png', 'Photo 2.PNG', 'Photo 02.png', '日本語.HEIC', 'line\nbreak.png']
        shuffled = names[:]
        random.Random(42).shuffle(shuffled)
        for offset in range(40):
            day = date(2026, 10, 31) + timedelta(days=offset)
            self.assertEqual(select(names, day), select(shuffled, day))

    def test_resize_and_filename_validation(self):
        self.assertEqual(select([], '2026-10-31'), {'status': 'empty', 'count': 0})
        for count in range(1, 35):
            names = ['wallpaper-%06d.jpg' % (i * 7 + 1) for i in range(count)]
            self.assertIn(select(names, '2026-10-31')['filename'], names)
        with self.assertRaisesRegex(ValueError, 'unique'):
            canonical_names(['photo.png', 'photo.png'])
        self.assertEqual(len(canonical_names(['wallpaper-000001.jpg', 'wallpaper-000001.png'])), 2)
        self.assertEqual(canonical_names(['a.png', 'z.png', 'same.jpg', 'same.png']),
                         ['same.jpg', 'z.png', 'a.png', 'same.png'])

    def test_pacific_boundaries_dst_and_travel(self):
        cases = {
            '2026-11-01T06:59:59Z': '2026-10-31',
            '2026-11-01T07:00:00Z': '2026-11-01',
            '2026-11-01T08:59:59Z': '2026-11-01',
            '2026-11-01T09:00:00Z': '2026-11-01',
            '2026-03-08T09:59:59Z': '2026-03-08',
            '2026-03-08T10:00:00Z': '2026-03-08',
            '2028-02-29T08:00:00Z': '2028-02-29',
            '2026-11-01T16:00:00+09:00': '2026-11-01',
        }
        for timestamp, expected in cases.items():
            self.assertEqual(day_number(timestamp), day_number(expected), timestamp)
        self.assertEqual(day_number('2028-03-01') - day_number('2028-02-28'), 2)

    def test_known_cross_language_vectors(self):
        for count, expected in [(1, 0), (2, 1), (3, 0), (10, 9)]:
            self.assertEqual(selection_index(count, day_number('2026-10-31')), expected)


if __name__ == '__main__':
    unittest.main()
