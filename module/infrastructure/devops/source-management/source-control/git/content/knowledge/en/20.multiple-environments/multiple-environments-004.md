# Case sensitivity and handling case-only renames

Git stores path names with their exact uppercase and lowercase characters in commit trees and the index. However, whether the operating system can create or distinguish two files differing only by casing depends on the filesystem and environment configuration. Consequently, a rename such as `PaymentService.js` to `paymentService.js` may work normally on a case-sensitive filesystem, yet fail to be recognized as intended on Windows or macOS with default case-insensitive filesystem settings.

When a project is developed across multiple operating systems, this difference can cause checkout, merge, build, or import errors. This lesson explains how Git handles casing, the role of `core.ignorecase`, how to safely perform case-only renames, and how to resolve conflicts when branches use paths differing only by casing.

## 1. How does Git store path names?

### 1.1. Casing is part of the path name

In a commit, Git stores directory trees containing path names, modes, and content objects. Filenames are stored character-for-character, including uppercase and lowercase letters.

For example, Git can store two distinct paths:

- `src/PaymentService.js`
- `src/paymentService.js`

On a case-sensitive filesystem, these two paths can exist as two independent files. On a case-insensitive filesystem, they may be treated as the same name. This creates a limitation when checking out a repository that contains two paths differing only by casing.

You can inspect the exact path names stored in the current commit:

~~~bash
git ls-tree -r --name-only HEAD
~~~

Inspect the paths currently tracked by the index:

~~~bash
git ls-files
~~~

These commands help uncover the exact casing Git records, even when File Explorer or a file manager does not make the difference obvious.

### 1.2. Case-sensitive vs. case-insensitive

A **case-sensitive** filesystem distinguishes uppercase and lowercase letters. For example, `Config.yml` and `config.yml` are two different paths.

A **case-insensitive** filesystem does not distinguish casing when looking up paths. The two names above may be treated as the same file, even though the filesystem preserves the original capitalization for display. This is typically the default mode on many Windows and macOS machines, though specific configurations can vary.

| Environment | Typical behavior | Notes |
| --- | --- | --- |
| Linux with ext4 | Case-sensitive | Some other filesystems or storage layers have their own behavior |
| Windows with NTFS | Usually case-insensitive, case-preserving | Windows supports enabling per-directory case sensitivity in certain configurations |
| macOS with APFS | Usually case-insensitive, case-preserving | APFS can be formatted as either case-sensitive or case-insensitive |

Do not draw conclusions solely from the operating system name. A macOS machine can use a case-sensitive volume; a Windows folder can have case sensitivity enabled. Actual behavior depends on the filesystem and directory configuration containing the repository.

### 1.3. Problems when working across multiple environments

Suppose a developer on Linux renames:

~~~text
src/PaymentService.js
        ->
src/paymentService.js
~~~

On Linux, both Git and the filesystem recognize the two names as distinct. When committed, the Git tree accurately records the new name.

A teammate on Windows may encounter issues if the filesystem is case-insensitive:

- A checkout or merge command may fail to create the new path because the old path is treated as the same name.
- A casing change performed in File Explorer may not register as a change recognized by Git.
- Files or imports with inconsistent casing may still run on this machine yet fail in a Linux environment.
- Two branches that create two paths differing only by casing may not be able to be checked out simultaneously in the same working tree.

This is a coordination issue between path names in Git and what the filesystem can represent, not necessarily a bug in the file contents.

## 2. The role of core.ignorecase

### 2.1. What is core.ignorecase?

`core.ignorecase` is a setting that affects how Git handles uppercase/lowercase differences in working tree path names. Git typically probes the filesystem when creating or cloning a repository and sets the appropriate value for case-insensitive filesystems.

View the current setting:

~~~bash
git config --show-origin --get core.ignorecase
~~~

If the command prints no value, this key may not be explicitly set in the configuration files. You can view related configurations:

~~~bash
git config --show-origin --list
~~~

When `core.ignorecase=true`, Git applies behavior compatible with case-insensitive filesystems. That helps Git avoid certain misunderstandings when looking up paths in the working tree.

### 2.2. core.ignorecase does not change the filesystem

Distinguish between:

- The filesystem determines whether the operating system can create and distinguish paths with different casing.
- `core.ignorecase` adjusts how Git handles path names in that environment.

Setting `core.ignorecase=false` does not turn NTFS or case-insensitive APFS into a case-sensitive filesystem. If the filesystem still treats two names as one, Git can enter an awkward state where the index contains a path with different casing than the working tree.

Do not change this setting solely to force Git to detect a rename. Use a rename workflow suited to the filesystem, and only adjust the configuration when you thoroughly understand the environment's behavior, have a concrete reason, and have verified the impact.

### 2.3. Do not force identical configuration across every machine

In a multi-environment team, different machines may have different `core.ignorecase` values due to different filesystems. This is not necessarily a configuration error.

What the team needs to agree on is:

- Casing conventions for file, directory, package, and module names.
- Never creating two paths differing only by casing in the same directory if the project must support case-insensitive filesystems.
- Ensuring every casing change is explicitly recorded by Git.
- Having CI run in an appropriate environment to catch mis-cased paths or imports.

Do not commit a shared `core.ignorecase` value attempting to force all machines with different filesystems to behave identically.

## 3. Renaming a file differing only by casing

### 3.1. Why might a direct rename go unrecognized?

Suppose a tracked file is named:

`src/PaymentService.js`

You want to rename it to:

`src/paymentService.js`

On a case-insensitive filesystem, a direct rename command or UI action may be treated as renaming the file to itself. Git may show no changes, or the working tree may retain the old casing.

Check first:

~~~bash
git status --short
git ls-files -- src/PaymentService.js
~~~

If the casing change is not recognized by Git, use an intermediate name to create two unambiguous rename steps.

### 3.2. Safe approach: rename via a temporary name

Suppose you want to rename `PaymentService.js` to `paymentService.js`. Use a completely different temporary name:

~~~bash
git mv -- src/PaymentService.js src/PaymentService.__case_tmp__
git mv -- src/PaymentService.__case_tmp__ src/paymentService.js
~~~

The first step moves the file to an intermediate name. The second step moves it from the intermediate name to the target name with the desired casing. Because the intermediate name differs completely from the original name, a case-insensitive filesystem can execute it cleanly.

The temporary name is only an intermediate step in the working tree and index; you do not need to create a separate commit for it. After the two commands, verify:

~~~bash
git status --short
git diff --cached --summary
git ls-files -- src/paymentService.js
~~~

The expected result is that the index records the target path with the new casing and the old path is gone. If the temporary name already exists, pick another unused name.

### 3.3. Can you rename directly with git mv?

On some filesystems and Git versions, a direct rename command may work:

~~~bash
git mv -- src/PaymentService.js src/paymentService.js
~~~

However, in a case-insensitive environment, this operation may not behave as desired because the filesystem treats source and destination as the same path. The two-step temporary-name workflow is more predictable when you need to guarantee the casing is recorded in the index.

The `-f` option of `git mv` allows overwriting the destination in some situations, but it does not make the filesystem case-sensitive and should not be used to blindly resolve a casing collision. Inspect the destination path before using it.

### 3.4. If already renamed via File Explorer or a file manager

If a rename performed outside Git is not recognized:

1. Check the name Git is tracking using `git ls-files`.
2. Rename to an intermediate name that clearly differs beyond casing.
3. Rename from the intermediate name to the desired target name.
4. Re-check with `git status` and `git diff --cached --summary`.
5. If needed, stage the renamed paths with `git add -A -- src`.

Do not delete the index or directly edit metadata files in the Git directory to force a casing change.

## 4. Verifying the rename was recorded accurately

### 4.1. Check status before committing

After running `git mv`, Git usually stages the path change immediately. Verify:

~~~bash
git status
git diff --cached --summary
git diff --cached --name-status
~~~

Git may display output like:

~~~text
R100    src/PaymentService.js    src/paymentService.js
~~~

`R100` is how Git presents a change detected as a rename with 100% similarity. Git does not store a separate rename object type; when comparing two trees, Git infers renames from deleted and added paths based on content similarity.

Therefore, the similarity percentage and rename display may change if the file content is also substantially edited.

### 4.2. Check the exact path in the index

~~~bash
git ls-files --stage
~~~

Or restrict to a directory:

~~~bash
git ls-files --stage -- src
~~~

Verify that only the path with the team's agreed-upon casing exists. On a case-insensitive filesystem, you cannot rely merely on opening the file using a differently cased name because the OS may still open the same file.

### 4.3. Commit and verify after committing

After confirming the diff:

~~~bash
git diff --cached
git commit -m "Rename PaymentService with canonical casing"
~~~

Check the commit tree:

~~~bash
git ls-tree -r --name-only HEAD
git show --summary --format=short HEAD
~~~

The commit tree must contain the exact path with the new casing. This is stronger proof than how File Explorer displays the filename.

## 5. Handling two branches renaming to different casings

### 5.1. Rename/rename scenario

Suppose two branches both start from `src/PaymentService.js`:

- Branch A renames it to `src/paymentService.js`.
- Branch B renames it to `src/PAYMENTSERVICE.js`.

Or two branches rename the same file to two names differing in capitalization. Git may detect a rename conflict or path collision depending on content, filesystem, and rename detection.

On a case-sensitive filesystem, two differently cased names can coexist. On a case-insensitive filesystem, they can collide because the OS treats them as the same path.

### 5.2. Inspect before resolving

Start with:

~~~bash
git status
git diff --name-only --diff-filter=U
git ls-files -u
git log --oneline --graph --decorate --all -10
~~~

If you need to view the versions at each stage of a conflicting path:

~~~bash
git show :1:src/PaymentService.js
git show :2:src/PaymentService.js
git show :3:src/PaymentService.js
~~~

Stage 1 is base, stage 2 is ours, and stage 3 is theirs in a normal merge. Some stages may not exist if one side renamed or deleted the path. In that case, check both the list from `git ls-files -u` and the new paths reported by Git.

During a rebase, the meaning of ours/theirs can be confusing; identify the current operation and inspect actual commit contents before choosing.

### 5.3. Agree on one canonical spelling

The team needs to decide on a single final path. For example, agree on:

`src/paymentService.js`

Then:

1. Compare contents from the branches and keep all necessary changes.
2. Establish the canonical path and remove old-cased paths if they are no longer used.
3. If the filesystem does not recognize a case change, move via a temporary name.
4. Stage all related additions, modifications, and deletions.
5. Inspect the index to ensure only the single canonical path remains.

For example, once the working tree is arranged according to the decision:

~~~bash
git add -A -- src
git status
git ls-files --stage -- src
git diff --cached --summary
~~~

Only stage a directory or path after inspecting other changes in that scope to avoid pulling unrelated content into the merge.

Once no unmerged entries remain and the content is verified, finish:

~~~bash
git merge --continue
~~~

If rebasing, use `git rebase --continue`. Do not manually delete conflict files or metadata to end the operation.

### 5.4. If checkout or merge cannot create two differently cased paths

If a repository simultaneously contains `Config.yml` and `config.yml`, a case-insensitive filesystem may be unable to check out both. Checkout or merge commands may report file creation, overwrite, or path collision errors.

The sustainable solution is to agree on renaming one or both paths so they differ beyond casing, then commit that standardization on a branch that can handle it. If you need to inspect or resolve existing contents that your filesystem cannot represent, use a clone or workspace on a case-sensitive filesystem.

Do not try to work around this merely by setting `core.ignorecase=false`: that configuration does not change the filesystem's ability to distinguish names.

## 6. Casing bugs in code and project configuration

### 6.1. Code runs on one machine but fails on another

An import path or reference may use casing that does not match the actual filename:

~~~text
Filename: src/paymentService.js
Import:   ./PaymentService.js
~~~

In a case-insensitive environment, the import may still resolve. In a case-sensitive environment, the path does not match and the build or tests fail.

Places to check:

- Imports in source code.
- Paths in build configuration.
- Package, module, and directory names.
- Deployment and test scripts.
- Asset paths in HTML, CSS, or configuration files.
- Documentation links and auto-generated paths.

Identifiers in programming languages can also be case-sensitive even when the filesystem is not. Do not assume the rules for variable, class, or package names match the filesystem's rules.

### 6.2. Testing on a case-sensitive environment

CI running on Linux commonly helps catch mis-cased import paths that case-insensitive Windows or macOS machines might overlook.

A suitable workflow:

1. Check exact filenames in Git using `git ls-files`.
2. Cross-check imports or references against path casing.
3. Run builds and tests on a case-sensitive environment.
4. Also check scripts and assets loaded by path.
5. Fix references and rename files using the team's agreed Git workflow.

CI does not automatically fix path names. It helps catch errors early before changes are integrated or released.

## 7. Team conventions to avoid casing conflicts

A team working across multiple operating systems should have clear conventions:

- Choose a consistent naming style for directories and files, such as PascalCase for Java class names or kebab-case for documentation.
- Never create two files in the same directory differing only by uppercase/lowercase.
- When changing casing, use `git mv` and an intermediate name if the filesystem does not recognize direct changes.
- Check paths in imports, configuration, scripts, and documentation after renaming.
- Review rename diffs before committing; do not rely solely on file manager feedback.
- Run CI on a case-sensitive filesystem if the project needs to support Linux.
- When a collision occurs between branches, agree on one canonical path and integrate contents before completing the merge.

If a project already has many paths differing only by casing, plan standardization separately. Mass renames can affect imports, builds, scripts, and links; break them down by functional group and test after each group.

## 8. Comprehensive example: case-only file rename on Windows

Suppose the repository currently tracks:

`src/PaymentService.js`

The team decides to standardize it to:

`src/paymentService.js`

On a Windows machine with the default case-insensitive filesystem, a direct rename may not be recorded by Git. Perform:

**Step 1 — Check status**

~~~bash
git status --short
git ls-files -- src/PaymentService.js
~~~

**Step 2 — Rename via temporary name**

~~~bash
git mv -- src/PaymentService.js src/PaymentService.__case_tmp__
git mv -- src/PaymentService.__case_tmp__ src/paymentService.js
~~~

**Step 3 — Check staged changes**

~~~bash
git status
git diff --cached --summary
git ls-files --stage -- src
~~~

Confirm the index contains `src/paymentService.js` and no longer contains the old path.

**Step 4 — Update references**

Find and fix imports, build configurations, scripts, or docs using the old name. Casing in references must match the new name exactly.

**Step 5 — Verify and commit**

~~~bash
git diff --cached
git diff
~~~

Run the project's build/tests, then:

~~~bash
git add -- path/to/changed-importer
git diff --cached --check
git commit -m "Normalize PaymentService filename casing"
~~~

**Step 6 — Verify the commit tree**

~~~bash
git ls-tree -r --name-only HEAD
git show --summary --format=short HEAD
~~~

If the commit has been pushed, team members need to fetch and update their branches per the team workflow. Case-insensitive machines may need a fresh checkout or a temporary-name rename if they still hold the old path.

## 9. Quick reference table

| Need | Command |
| --- | --- |
| View casing in current commit | `git ls-tree -r --name-only HEAD` |
| View paths in index | `git ls-files` |
| View ignorecase setting | `git config --show-origin --get core.ignorecase` |
| Rename via temporary name | `git mv -- old-name temp-name` then `git mv -- temp-name new-name` |
| Check staged rename | `git diff --cached --summary` |
| View changed names and status | `git status --short` |
| View conflicting paths | `git diff --name-only --diff-filter=U` |
| View index stages during conflict | `git ls-files -u` |
| Re-stage changes by path | `git add -A -- path` |
| View filenames in latest commit | `git ls-tree -r --name-only HEAD` |

## 10. Summary

Git stores path names with exact casing, while a developer machine's filesystem may be case-sensitive or case-insensitive. `core.ignorecase` helps Git adapt to the filesystem, but it does not change the operating system's rules.

When performing a case-only rename on a case-insensitive filesystem, going through a temporary name with two `git mv` commands generally ensures Git records the change accurately. Afterward, inspect the index, diff, and commit tree to confirm the new name was stored properly.

In a multi-environment team, agree on casing conventions, avoid two paths differing only by case, and run CI on a case-sensitive environment when appropriate. This practice helps minimize checkout, merge, import, and build errors when the same repository is used across Windows, macOS, and Linux.
