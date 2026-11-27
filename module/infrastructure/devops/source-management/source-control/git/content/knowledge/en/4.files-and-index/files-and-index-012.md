# Limitations of assume-unchanged and skip-worktree

Git has two flags in the index often mentioned when wanting to reduce file checking or keep certain files out of the working tree: `assume-unchanged` and `skip-worktree`. Both affect how Git handles a path in the local repository, yet they serve different purposes and both have clear limitations.

`assume-unchanged` is a promise from the user that a file in the working tree has not changed, allowing Git to skip some file status checks. `skip-worktree` instructs Git to avoid writing that file out to the working tree when possible and is used primarily to implement sparse checkout. Neither flag turns a tracked file into an ignored one, alters commit history, or establishes a shared policy for the whole team.

This lesson belongs to the **Files and Index** chapter of the `SOURCE_CONTROL_GIT` module. The module covers the working tree, staging area, commits, history, branches, merges, rebases, remotes, and tags; understanding the limits of these two index flags helps avoid missing changes or losing local data.

## 1. Where Do These Two Flags Live?

Git manages content and working state across several layers:

- **Working tree:** the files and directories you currently see and edit.
- **Index (staging area):** the snapshot of content and metadata that Git will use for the next commit.
- **Repository object database:** commits, trees, blobs, and history objects.
- **Index flags:** metadata bits attached to index entries that influence how Git checks or materializes paths.

`assume-unchanged` and `skip-worktree` are local metadata bits inside the index. They are not recorded in commit trees, are not pushed to remotes, and do not propagate to other people's clones.

| Characteristic | assume-unchanged | skip-worktree |
| --- | --- | --- |
| Primary purpose | Tell Git to assume the file is unchanged so it can reduce stat checks | Tell Git to avoid writing the file to the working tree when possible |
| Behavior when file is absent | Does not reliably mean ignore deletion | Absent file is treated as intentional in appropriate situations |
| Primary use case | Optimizing checks in local repositories in narrow scenarios | Sparse checkout and selective working trees |
| Replaces .gitignore? | No | No |
| Alters commits or remotes? | No | No |
| Mechanism to protect local changes? | No | No |

Both flags can cause confusion if you treat them as ways to “hide” an already-tracked file from Git.

## 2. assume-unchanged: A Promise About File State

Enable the flag for a path:

~~~bash
git update-index --assume-unchanged -- path/to/file
~~~

This command sets the assume-unchanged bit on the corresponding index entry. Git can skip some filesystem metadata checks (such as stat) for that file under the assumption that working tree content has not changed relative to the index.

This mechanism originated from optimization needs on filesystems or repositories with many files, where checking per-file metadata carries noticeable overhead. It is a promise from the user so Git can reduce inspection work.

Disable the flag:

~~~bash
git update-index --no-assume-unchanged -- path/to/file
~~~

After disabling, Git can re-check the file through its normal workflow. If the file has changed, a modified status may appear.

### What Happens If You Edit the File Anyway?

Suppose you enable the flag on `config/local-settings.json` and then edit that file. Because Git was told to assume the file is unchanged, `git status` or commands relying on working tree checks may fail to detect changes as you expect.

This is why you should not use this flag to maintain private local configuration while frequently editing the file. When you need to change the file, disable the flag first, then check:

~~~bash
git update-index --no-assume-unchanged -- config/local-settings.json
git status --short
git diff -- config/local-settings.json
~~~

If that change needs to be committed, stage it after reviewing the content. If you do not want to share local changes, choose a more suitable way to organize private configuration, such as separating local files from template files or placing untracked files in personal ignore rules.

### assume-unchanged Does Not Mean Ignore

A file already tracked by Git remains a tracked file. The assume-unchanged bit does not remove the file from the index, does not prevent committing if content is staged, and does not replace ignore rules.

If the goal is to stop tracking a file while keeping it on disk, operate on the index—such as `git rm --cached`—after considering the impact on the team. If the goal is ignoring new untracked files, use `.gitignore` or `.git/info/exclude`.

## 3. skip-worktree: Git Avoids Updating the Path in the Working Tree

Enable the flag for a path:

~~~bash
git update-index --skip-worktree -- path/to/file
~~~

`skip-worktree` instructs Git to avoid writing that path's content out to the working tree when possible. When a path with this flag is not present in the working tree, Git can treat its absence as intentional instead of reporting it as a normal deleted file.

Disable the flag:

~~~bash
git update-index --no-skip-worktree -- path/to/file
~~~

Git uses this flag as the foundation for sparse checkout: files outside the selected path set can be marked skip-worktree so Git does not materialize them in the working tree.

### skip-worktree Is Not a Way to Hide Local Edits

Some people set this flag on a tracked configuration file to edit private values without having Git show changes. This usage easily leads to surprises:

- Git may skip updating the file in the working tree when the branch or index content changes.
- When the file does not exist, Git may treat it as intentionally omitted from the working tree.
- If upstream changes the same path, merge, checkout, or update operations may alter the flag or force Git to reprocess the path.
- If you forget the flag is enabled, you may not realize your local file is outdated compared to committed content.

Do not rely on skip-worktree to protect local data or conceal a change that needs to be managed. Before updating branches, merging, or pulling, check which paths currently have flags set and preserve any local changes you need to keep.

## 4. Checking Enabled Flags

Git provides `git ls-files` to inspect entries in the index.

### Checking assume-unchanged

Use:

~~~bash
git ls-files -v -- path/to/file
~~~

With `-v`, Git displays a status tag before the path; a lowercase tag letter indicates the entry is marked assume-unchanged. For example, a path may appear as:

~~~text
h config/local-settings.json
~~~

A lowercase letter is the sign to check. To list all entries with lowercase tags in a POSIX shell:

~~~bash
git ls-files -v | grep '^[a-z]'
~~~

On PowerShell:

~~~powershell
git ls-files -v | Select-String '^[a-z]'
~~~

### Checking skip-worktree

Use:

~~~bash
git ls-files -t -- path/to/file
~~~

The `-t` option displays status tags. The `S` tag indicates an entry with skip-worktree. To filter the list in a POSIX shell:

~~~bash
git ls-files -t | grep '^S '
~~~

On PowerShell:

~~~powershell
git ls-files -t | Select-String '^S '
~~~

If there is no output for a path, either the corresponding flag is not set or the path is not in the index. Verify the exact path and tracked state before drawing conclusions.

## 5. Safely Enabling and Disabling Flags

update-index commands affect the local index. Before making changes, note the current state and inspect file contents.

Example checking a file:

~~~bash
git status --short
git ls-files -v -- config/local-settings.json
git ls-files -t -- config/local-settings.json
~~~

Enable assume-unchanged only when you truly understand Git will skip certain checks:

~~~bash
git update-index --assume-unchanged -- config/local-settings.json
~~~

Enable skip-worktree when necessary:

~~~bash
git update-index --skip-worktree -- config/large-local-fixture.json
~~~

Clear flags before working with the files:

~~~bash
git update-index --no-assume-unchanged -- config/local-settings.json
git update-index --no-skip-worktree -- config/large-local-fixture.json
~~~

After clearing flags, inspect status and diffs:

~~~bash
git status --short
git diff -- config/local-settings.json
git diff --cached -- config/local-settings.json
~~~

If a file is missing or has local changes, do not rush to run restore/checkout commands that could overwrite data. Back up local copies you need to keep, then decide which content belongs in the working tree, index, or commit.

## 6. Flags Are Not Shared via Commit or Push

Suppose you enable assume-unchanged on `config/app.yml` and commit other changes. Anyone else cloning the repository will not receive that bit automatically. They have their own index, and Git checks files according to their local state.

Similarly, skip-worktree is stored in the index of the current working copy. It is not an attribute in commit trees like an executable bit or symlink mode. Pushing commits does not carry this flag to the remote.

This leads to three consequences:

1. Two team members can have different flag states for the same path.
2. Re-cloning or creating a new working tree will not preserve manually set flags.
3. Flags cannot serve as a team policy to ignore a file or synchronize local configuration.

If the entire team needs to ignore an untracked file type, commit `.gitignore`. If only one person wants to ignore a local file, consider `.git/info/exclude` or `core.excludesFile`. If the team needs to check out part of a repository, use sparse checkout through its supported workflow.

## 7. Relationship Between skip-worktree and Sparse Checkout

Sparse checkout lets you choose which paths are materialized in the working tree. Git uses skip-worktree to mark entries outside the selected path set.

Example checking out only two directories in a monorepo:

~~~bash
git sparse-checkout init --cone
git sparse-checkout set services/billing libraries/common
git sparse-checkout list
~~~

Git manages skip-worktree bits according to the sparse checkout pattern set. When changing scope:

~~~bash
git sparse-checkout add docs/api
~~~

Git can materialize additional files belonging to the new directory. When disabling sparse checkout:

~~~bash
git sparse-checkout disable
~~~

Git attempts to bring tracked files back into the working tree; if the repository is a partial clone, this process may need to fetch additional blobs.

### Do Not Manually Edit Bits Inside a Sparse Region

If sparse checkout is enabled, avoid manually setting or clearing skip-worktree for paths managed by sparse rules. Manual edits can cause index state to drift out of sync with the sparse checkout configuration. The `git sparse-checkout reapply` command can reapply patterns and align the working tree/index with the configuration.

Inspect sparse checkout status:

~~~bash
git sparse-checkout list
git status --short
git ls-files -t
~~~

Use `git sparse-checkout set`, `add`, `reapply`, and `disable` to manage checkout scope instead of treating skip-worktree as a standalone tool to hide files.

## 8. Limitations When Branches or Upstream Content Change

Neither flag is a contract that Git will always ignore the path across every operation. Git commands may re-check, update, or alter the bit when needed to keep the index and working tree consistent.

For example, you mark a config file with skip-worktree and then fetch a new branch containing changes to that exact file. During checkout, merge, or rebase, Git may need to handle it differently from initial expectations; conflicts can arise or the flag may be cleared so Git can update the file.

With assume-unchanged, if the file actually changes while Git relies on the unchanged promise, status may miss it until you clear the flag and Git re-checks.

Before major operations like merge, rebase, branch switching, or pull, check and remove flags that are no longer needed. Do not use them to conceal local state over long periods.

## 9. Choosing the Right Alternative for the Goal

Pick the tool according to the problem you need to solve:

| Need | Appropriate Approach | Why |
| --- | --- | --- |
| Skip untracked build outputs or caches | `.gitignore` | Rules shared with the repository |
| Ignore untracked local files only on your machine | `.git/info/exclude` or `core.excludesFile` | Does not alter team rules |
| Separate private environment config from shared files | Template file + ignored local file, environment variables, or external config | Avoids editing a tracked file and trying to hide changes |
| Check out only a few directories in a monorepo | `git sparse-checkout` | Git manages selective working tree and skip-worktree |
| Optimize stat checks in special cases | `assume-unchanged` | Use only when accepting the promise not to edit the file |
| Keep tracked files out of working tree per sparse rules | `skip-worktree` via sparse checkout | Matches the mechanism Git uses for sparse working trees |

### Example: Private Local Configuration

Instead of editing a tracked `config/app.yml` and turning on assume-unchanged, design it as:

~~~text
config/
  app.example.yml
  app.local.yml
~~~

Commit `app.example.yml`, ignore `app.local.yml`, and have the application load the local file if present. Or keep a shared config file while reading private values from environment variables.

This makes clear which configuration is team-managed and which is personal; Git does not have to guess whether a tracked file should be checked.

## 10. Diagnostic Workflow When Git Does Not See Changes

If you edit a tracked file yet `git status` does not report it as modified, do not immediately assume Git has a bug. Check the flags:

~~~bash
git ls-files -v -- path/to/file
git ls-files -t -- path/to/file
~~~

If assume-unchanged is found, clear the flag:

~~~bash
git update-index --no-assume-unchanged -- path/to/file
~~~

If skip-worktree is found, clear the flag when you intentionally want the file back within inspection/checkout scope:

~~~bash
git update-index --no-skip-worktree -- path/to/file
~~~

Then inspect:

~~~bash
git status --short
git diff -- path/to/file
git diff --cached -- path/to/file
~~~

If the file does not appear in the index, double-check the name and path with:

~~~bash
git ls-files -- path/to/file
~~~

If the file is untracked, check ignore rules:

~~~bash
git check-ignore -v -- path/to/file
~~~

If the file is ignored yet needs to be added to Git, consider why it was ignored first; only when certain you want to track it, use:

~~~bash
git add -f -- path/to/file
~~~

`git add -f` force-adds an ignored path into the index. It is not the fix for assume-unchanged or skip-worktree.

## 11. Behavior and Risk Comparison Table

| Scenario | assume-unchanged | skip-worktree |
| --- | --- | --- |
| Tracked file edited locally | Git may not detect it because it skips some checks | Git may treat it specially; no guarantee local changes stay hidden |
| File absent from working tree | Not its primary purpose; may be seen as deletion on re-check | Absence is usually treated as intentional |
| Checking out a new branch | Flag does not guarantee keeping the file or avoiding conflicts | Git tries to avoid writing the file when possible; upstream changes may force Git to reprocess |
| Commit | Flag does not prevent content from being staged and committed | Flag does not prevent content from being staged and committed |
| Another clone | Not propagated | Not propagated |
| Used for sparse checkout | No | Yes, this is a primary use |
| Used to ignore new files | No | No |

Remember: an index flag affects Git behavior only in a specific working tree. It does not replace version control, ignore rules, or configuration management.

## 12. Common Mistakes

- **Using assume-unchanged to hide a local config file:** Git may fail to detect when the file changes and you may forget to clear the flag before committing.
- **Using skip-worktree like .gitignore:** the file stays tracked and the flag creates no ignore rule.
- **Assuming flags are shared with teammates:** flags live in the local index, not in commits.
- **Assuming flags persist forever across every operation:** Git can re-check or adjust flags when checkout/merge requires it.
- **Manually editing skip-worktree during sparse checkout:** can cause index state to diverge from sparse patterns.
- **Not checking flags when status shows no changes:** can waste time chasing the wrong cause.
- **Running restore or checkout immediately upon clearing a flag:** risks overwriting local copies you need to keep; back up and review first.
- **Confusing index flags with file mode:** executable bit, symlink mode, and skip-worktree/assume-unchanged have distinct meanings.

## 13. Decision Flowchart

~~~mermaid
flowchart TD
    A[Want to change how Git handles a tracked file] --> B{What is the goal?}
    B -- Skip untracked files --> C[.gitignore or info/exclude]
    B -- Check out only part of the repository --> D[git sparse-checkout]
    B -- Separate local configuration --> E[Template file, local config, or environment]
    B -- Reduce stat checks in narrow cases --> F[assume-unchanged]
    D --> G[Git manages skip-worktree]
    F --> H[Track the flag and clear it before editing]
    C --> I[Check status and ignore rules]
    E --> I
    G --> I
    H --> I
~~~

Before enabling or disabling a flag, verify for yourself:

1. Is the file currently tracked and present in the index?
2. Do I need to optimize stat checks or restrict the working tree?
3. Is sparse checkout currently managing skip-worktree?
4. Have I backed up local changes before clearing flags or checking out?
5. Do I understand flags are not committed/pushed and do not apply to teammates?
6. After changing a flag, have I re-checked status, working tree, and staged diff?

`assume-unchanged` and `skip-worktree` are two index-level directives with distinct purposes. Use assume-unchanged only when you genuinely want Git to reduce checks on a file you commit not to edit; use skip-worktree in the context of a selective working tree, ideally through sparse checkout. When the goal is ignoring files, separating local configuration, or managing generated files, use the mechanism dedicated to that goal.

## References

- [Git documentation: git-update-index](https://git-scm.com/docs/git-update-index) — describes assume-unchanged, skip-worktree, and index-updating options.
- [Git documentation: git-ls-files](https://git-scm.com/docs/git-ls-files) — displays index status tags with `-t` and `-v`.
- [Git documentation: git-sparse-checkout](https://git-scm.com/docs/git-sparse-checkout) — manages sparse working trees and skip-worktree.
- [Git documentation: gitignore](https://git-scm.com/docs/gitignore) — distinguishes ignore rules from tracked/index state.
- [Git FAQ: assume-unchanged and skip-worktree](https://git-scm.com/docs/git-update-index#_using_assume_unchanged_bit) — semantics and limitations of index bits.
