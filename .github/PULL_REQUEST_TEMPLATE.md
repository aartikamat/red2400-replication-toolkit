<!--
  Thank you for opening a pull request. See CONTRIBUTING.md for the
  full development workflow. The sole author is the current
  maintainer; substantive changes are discussed on an issue before a
  PR is opened.
-->

## Summary

<!-- One-paragraph description of the change and why it is needed. -->

## Related issue

<!-- Closes #NNN or references #NNN. -->

## Test plan

- [ ] `pytest -v` passes locally on Python 3.10, 3.11, or 3.12.
- [ ] If the change touches classification, event identity, or the
      audit runner, an adversarial fixture with a hand-computed
      expected outcome was added to `tests/`.
- [ ] If the change is scientific-behaviour-affecting, `SEMVER_POLICY.md`
      is respected (major-version bump on any estimand change).

## Compatibility

- [ ] No change to the public API, OR the change is documented in
      `CHANGELOG.md` and reflected in `API_REFERENCE.md`.
- [ ] Legacy `MODE_LEGACY_MINT_POOLED` behaviour is unchanged (or
      the change is called out explicitly and covered by the legacy
      regression test).

## Checklist

- [ ] I have read `CONTRIBUTING.md` and `GOVERNANCE.md`.
- [ ] I did not rewrite `main` history or move existing tags.
- [ ] I did not silently substitute one estimand for another.
