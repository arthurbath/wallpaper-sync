"""Check the daily guard's boundaries in both generated production workflows."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from native_builder import build_sync, SUCCESS_DATE_KEY


BINDING = {'displayName': 'Example Project', 'filename': 'Example Project',
           'fileLocation': {'WFFileLocationType': 'iCloud', 'relativeSubpath': 'Example Project'}}


class DailySuccessTests(unittest.TestCase):
    def test_repeat_run_stops_before_any_file_access(self):
        for platform in ('mac', 'iphone'):
            with self.subTest(platform=platform):
                actions = build_sync(BINDING, platform).actions
                ids = [a['WFWorkflowActionIdentifier'].split('.')[-1] for a in actions]
                read = ids.index('getstoredcontent')
                first_file = next(
                    i for i, a in enumerate(actions) if a['WFWorkflowActionIdentifier'].endswith('.documentpicker.open'))
                guard = actions[read + 2]['WFWorkflowActionParameters']
                self.assertEqual(guard['WFCondition'], 4)
                self.assertEqual(guard['WFControlFlowMode'], 0)
                self.assertIn('pacific-date', str(guard['WFConditionalActionString']))
                self.assertIn('already_completed', str(actions[read + 3]))
                self.assertEqual(ids[read + 4], 'output')
                self.assertLess(read + 4, first_file)
                self.assertTrue(any('America/Los_Angeles' in str(a) for a in actions[:read]))

    def test_only_success_records_the_date_and_storage_is_shortcut_scoped(self):
        for platform, final in (('mac', 'runshellscript'), ('iphone', 'wallpaper.set')):
            with self.subTest(platform=platform):
                actions = build_sync(BINDING, platform).actions
                reads = [a for a in actions if a['WFWorkflowActionIdentifier'].endswith('.getstoredcontent')]
                writes = [i for i, a in enumerate(actions)
                          if a['WFWorkflowActionIdentifier'].endswith('.setstoredcontent')]
                self.assertEqual(len(reads), 1)
                self.assertEqual(len(writes), 1)
                write = writes[0]
                self.assertTrue(actions[write - 1]['WFWorkflowActionIdentifier'].endswith('.' + final))
                self.assertIn('pacific-date', str(actions[write]['WFWorkflowActionParameters']['WFInput']))
                for action in (reads[0], actions[write]):
                    p = action['WFWorkflowActionParameters']
                    self.assertEqual(p['WFStoredContentKey'], SUCCESS_DATE_KEY)
                    self.assertIs(p['WFStoredContentGlobalValue'], False)
                # All unavailable, invalid, setup, and unsupported exits precede the write.
                for i, action in enumerate(actions):
                    if any(status in str(action) for status in (
                            'unavailable', 'empty', 'invalid_image', 'setup_required', 'unsupported_device')):
                        self.assertLess(i, write)

    def test_diagnostics_neither_skip_nor_modify_production_success(self):
        for platform in ('mac', 'iphone'):
            actions = build_sync(BINDING, platform, diagnostics=True).actions
            self.assertFalse(any('storedcontent' in a['WFWorkflowActionIdentifier'] for a in actions))
            self.assertNotIn('already_completed', str(actions))


if __name__ == '__main__':
    unittest.main()
