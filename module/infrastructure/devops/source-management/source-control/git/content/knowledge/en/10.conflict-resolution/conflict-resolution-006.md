# Handling Rename, File-Mode/Type, and Binary Conflicts

When two branches modify the same file, Git can often combine the content automatically. However, not every change is just editing a few lines of text. One branch may rename a file while the other continues editing the old path; two branches may change a file from a regular file to a symbolic link or alter its executable permission; or both may update an image, design document, or binary archive. These situations require developers to understand which versions Git is holding and decide the final state of the file.

This lesson focuses on three conflict categories: renames, file type or attribute changes tracked by Git, and binary files. The goal is to know how to identify the conflict, inspect data from each side, select or combine the right version, and finish the merge or rebase while preserving a meaningful history.

## 1. Understanding Conflict State Before Editing

### 1.1. Conflicts Do Not Always Have Markers Inside the File

For text files, Git usually inserts delimiter markers such as `<<<<<<<`, `=======`, and `>>>>>>>` into regions it cannot combine automatically. The developer can open the file, edit the content, and remove these markers.

However, with renames, file-type changes, or binary data, the conflict may lie in the path name, object type, or data version. In those cases, Git may not insert delimiter markers into the file. A binary file also cannot be merged line-by-line like source code.

Therefore, start with the repository status instead of only searching for `<<<<<<<`.

~~~bash
git status
git status --short
git diff --name-only --diff-filter=U
git ls-files -u
~~~

These commands serve different purposes:

- `git status` describes the paused operation and the paths still in conflict.
- `git status --short` gives a compact status, convenient when many files are involved.
- `git diff --name-only --diff-filter=U` lists the paths currently in an unmerged state.
- `git ls-files -u` shows the unmerged entries in the index, including mode, object hash, stage number, and path.

Do not start fixing by deleting files or immediately running `git add .`. First, determine which files are in conflict, which versions Git sees, and what requirements the final change must meet.

### 1.2. The Three Stages in the Index

During a three-way merge operation, Git can keep up to three versions for a conflicted path:

| Stage | Meaning | Interpretation |
| --- | --- | --- |
| 1 | Base | Common version at the point where the two branches diverged |
| 2 | Ours | Version on the current branch receiving the changes |
| 3 | Theirs | Version from the branch being integrated |

You can inspect these entries with:

~~~bash
git ls-files -u -- path/to/file
~~~

The output typically contains mode, object hash, stage, and path. Stage 1 is the baseline for comparison; stage 2 and stage 3 are the two sides being reconciled. A path may lack a stage, such as when one side deleted the file.

In a standard merge operation, "ours" is the branch you are on and "theirs" is the branch being merged in. During a rebase, this naming can be misleading: "ours" is typically the target branch onto which commits are being replayed, while "theirs" is the commit from the branch being rebased. Therefore, before selecting one side by command, check whether you are performing a merge or a rebase and verify the actual content of each version.

## 2. Handling File Rename Conflicts

### 2.1. Why Can Renaming Cause Conflicts?

Git stores directory trees and file contents in commits. Git does not store a separate "rename" operation as a historical object. When comparing two states, Git infers that a file was renamed based on the similarity between old and new contents.

Rename detection helps Git recognize many file moves, but the result depends on the content and similarity threshold. If two branches rename the same file in two different directions, or one branch renames while the other modifies or deletes the old file, Git may be unable to determine the final path automatically.

Common cases:

- **Rename/rename:** both branches rename the same file to two different names.
- **Rename/delete:** one branch renames the file while the other deletes it.
- **Rename/modify:** one branch renames the file while the other edits content at the old path.
- **Rename/add or path collision:** the new name is used for a different file on the other branch.
- **File/directory:** one branch uses a path as a file while the other uses the same path as a directory containing child files.

Not every case is displayed the same way. Use `git status` to see the specific message and paths.

### 2.2. Example: Two Branches Rename the Same Document

Suppose the `feature/setup-guide` branch renames:

- `docs/guide.md` to `docs/setup.md`.

Meanwhile, the `main` branch renames the same file:

- `docs/guide.md` to `docs/installation.md`, and also updates the guide content.

When merging, Git may report a rename/rename conflict. Git cannot automatically know which name is the standard name the project wants to use.

First, inspect the status:

~~~bash
git status
git ls-files -u
~~~

Then decide the final path based on the project's documentation structure and naming conventions. For instance, the team agrees to use `docs/setup.md`, while still needing to keep the useful updates from the `docs/installation.md` version.

Resolution workflow:

1. Open the available versions and compare their contents. You can use `git show` with a specific stage to inspect each side's content when the corresponding path is still in the index.
2. Choose the final name. If needed, combine content from both versions into the file at that path.
3. Remove or move unused paths in the working tree.
4. Verify that only the final file remains in the right location with complete content.
5. Stage the affected paths, including both deleted paths and the new path.

Example after arranging the working tree according to the team's decision:

~~~bash
git add -A -- docs/guide.md docs/setup.md docs/installation.md
git status
~~~

Depending on the specific conflict state, the list of paths to stage may vary. Use the exact paths shown by Git in `git status`. The `-A` option updates additions, modifications, and deletions within the specified paths.

### 2.3. One Branch Renames, the Other Modifies Content

Suppose branch A renames `src/PaymentService.java` to `src/payment/PaymentService.java`. Branch B continues editing `src/PaymentService.java` to add input validation.

If Git detects the rename relationship, it may automatically apply the edit to the new path. If it cannot combine them, inspect both paths and the change history. The sensible target is usually to keep the new name and incorporate the valid edits into the file at the new location.

Do not delete the file at the old path before confirming that the other branch's edits have been preserved. After merging the content and arranging the paths, stage the addition, modification, and deletion:

~~~bash
git add -A -- src/PaymentService.java src/payment/PaymentService.java
git status
~~~

If the other branch deleted the file while the current branch renamed it, the team must decide whether the deletion still matches current requirements. If the feature has been removed, you can accept the deletion. If the file is still needed, keep the renamed version and explain the decision during code review.

### 2.4. Inspecting Rename History

Because Git infers renames during comparison, history does not contain a standalone rename record. Some useful commands:

~~~bash
git log --follow -- path/to/current-file
git diff -M <old-commit> <new-commit>
git diff --summary <old-commit> <new-commit>
~~~

- `git log --follow` attempts to continue following a file's history across renames; this option is mainly useful when viewing the history of a single file.
- `git diff -M` enables rename detection when comparing two states.
- `git diff --summary` summarizes changes such as creations, deletions, renames, or mode changes when detectable.

These commands help trace a file's path over time, though the final name and content decision must still be based on project requirements.

## 3. Handling File-Type or Attribute Conflicts

### 3.1. Which Attributes Does Git Track?

Git does not store full operating system permissions for every file. For an entry in a Git tree, common modes include:

| Mode | Meaning |
| --- | --- |
| `100644` | Regular file, non-executable |
| `100755` | Regular file with executable permission |
| `120000` | Symbolic link |
| `160000` | Gitlink, referencing a submodule commit |

Git also stores file contents, paths, and related objects. Git does not track empty directories as standalone objects.

You can check the mode recorded in the index with:

~~~bash
git ls-files --stage -- path/to/file
~~~

During a conflict, use `git ls-files -u` to compare the mode and stage of each side. Different modes can indicate that the two branches not only edited content, but also changed how Git interprets the object at that path.

### 3.2. Executable Permission Changes

A script file might be marked executable on one branch, while another branch removes that permission. Git mainly cares about the executable bit it supports; it does not store full Unix permissions or Windows ACLs.

For example, a deployment script needs to run directly:

~~~bash
./scripts/deploy.sh
~~~

If the file must be executable in the repository, the mode needs to be `100755`. If it is just a regular text file, the mode is usually `100644`.

After agreeing on the final content and file type, stage the file to replace the conflict entries with one chosen entry in the index. Then explicitly set the mode to record:

~~~bash
git add -- scripts/deploy.sh
git update-index --chmod=+x -- scripts/deploy.sh
~~~

Or remove executable permission:

~~~bash
git add -- scripts/deploy.sh
git update-index --chmod=-x -- scripts/deploy.sh
~~~

Verify again:

~~~bash
git ls-files --stage -- scripts/deploy.sh
git diff --cached --summary
~~~

The `git update-index --chmod` command updates the mode in the index. If the file content also changed, ensure the right content has been staged before setting the mode, then check the final result.

On some filesystems or Windows environments, executable permissions may not be represented by the filesystem the same way as on Unix. The `core.filemode` setting affects whether Git detects executable-bit changes from the working tree. You can check the current setting with:

~~~bash
git config --get core.filemode
~~~

Do not change this configuration merely to silence warnings. Determine the mode the project expects and verify the mode actually stored in the index.

### 3.3. Regular Files vs. Symbolic Links

A symbolic link is a different object type from a regular file. Git records a symbolic link with mode `120000`; its blob content is the target path of the link. A corresponding regular file has mode `100644` or `100755`.

For example, one branch replaces `config/current` with a symbolic link pointing to `config/prod.yml`, while the other continues updating `config/current` as a regular configuration file. This is an object-type conflict and can affect how the application reads configuration.

Determine the project's intent:

- If the path must be a symbolic link, create the link with the correct target using a method supported on the team's operating systems and development environments.
- If the path must be a regular file, create the file with the right configuration content.
- If it should move to a new path, update all references in related source code or configuration as well.

Once the working tree has the correct object type and content, stage the path:

~~~bash
git add -- config/current
git ls-files --stage -- config/current
~~~

The output should reflect the desired mode. If the current environment does not support creating symbolic links, coordinate using a supported environment to verify the result before finishing. Do not replace a symbolic link with a plain text file containing the target path without confirming the project intentionally uses that approach.

### 3.4. Conflicts Involving Submodules

Submodules are recorded by Git with mode `160000`, which is a reference to a commit in a child repository. When two branches update a submodule to different commits, Git in the parent repository does not automatically merge the contents of the child repository like a regular source directory.

How to handle it:

1. Check the submodule path and status with `git status`.
2. Enter the child repository, inspect the log, and determine which commit should be used.
3. If the two lines of history can be combined, perform a merge or rebase inside the child repository according to the project's workflow.
4. If a specific commit must be chosen, check out that commit inside the submodule.
5. Return to the parent repository and stage the submodule path.

~~~bash
git -C libs/shared status
git -C libs/shared log --oneline --graph --all
git add -- libs/shared
git ls-files --stage -- libs/shared
~~~

Running `git add` in the parent repository records the current commit the submodule points to. It does not replace resolving content conflicts inside the child repository itself.

## 4. Handling Binary File Conflicts

### 4.1. Why Doesn't Git Automatically Merge Binary Files?

Text files can be compared line-by-line and independent changed regions can often be combined. Binary files such as PNG images, design assets, audio files, videos, PDFs, or archives typically lack a line-based text structure for Git to apply standard three-way merging.

If two branches modify the same binary file, Git usually requires choosing one version or using a specialized tool. You may see a message like:

~~~text
warning: Cannot merge binary files: assets/banner.png
CONFLICT (content): Merge conflict in assets/banner.png
~~~

There are no `<<<<<<<` markers inside the image file to edit. Opening the file in a text editor will not resolve the conflict and can corrupt the data.

### 4.2. Choosing One Side's Version

If the team decides to use the exact version from the current branch during a merge operation:

~~~bash
git restore --ours --worktree -- assets/banner.png
git add -- assets/banner.png
~~~

If deciding to use the version from the branch being merged in:

~~~bash
git restore --theirs --worktree -- assets/banner.png
git add -- assets/banner.png
~~~

The `--ours` and `--theirs` options pull content from stage 2 or stage 3 to update the working tree. Afterward, `git add` is needed to mark the path as resolved in the index.

Before choosing, confirm the meaning of each side. With rebase, the ours/theirs interpretation is reversed compared to what newcomers often expect: check the target branch and the commit being replayed, rather than choosing mechanically by name.

### 4.3. Manually Combining with a Specialized Application

One version does not always contain all the changes that need to be kept. For example:

- Branch A adjusts the layout and colors of a banner image.
- Branch B updates the logo and copy on the same image.
- The desired result is A's layout combined with B's new logo and copy.

In this case, the asset owner can open each version in an appropriate application, combine them into one final file, and save it to the exact path in the working tree. For documents or formats with specialized comparison tools, use those tools to inspect the relevant content, layers, pages, or components.

After saving the combined version:

~~~bash
git add -- assets/banner.png
git status
~~~

If the project configures a specialized merge tool or merge driver for the file format, you can use that tool. The configuration must fit the format and be agreed upon by the team; Git cannot inherently understand the structure of arbitrary binary formats.

### 4.4. Declaring Binary Files in .gitattributes

Git usually detects many binary formats automatically, but the team should explicitly declare file types that must not be processed as text. For example, in `.gitattributes`:

~~~gitattributes
*.png binary
*.jpg binary
*.psd binary
*.pdf binary
*.zip binary
~~~

The `binary` attribute tells Git not to process the content using standard text mechanisms. This avoids meaningless text diffs and prevents line-based merging from being attempted on binary formats.

If the project uses Git LFS, follow the repository's LFS workflow to ensure the corresponding binary object is uploaded and retrievable. A Git LFS pointer file in Git does not mean the actual binary payload is stored locally in every clone.

### 4.5. Rules for Selecting a Binary Version

Before accepting a version, confirm:

- Which version satisfies the latest business or design requirements?
- Does any part of the content from the other version need to be preserved?
- Does the final file have the right format, dimensions, resolution, or structure required by the application?
- Do other files reference this asset's name or version?
- If the file is tracked in Git LFS, has the LFS object been stored and can it be downloaded?

Do not pick a version solely because it belongs to the main branch or the checked-out branch. The decision must be grounded in actual content and the requirements of the change.

## 5. Completion Workflow After Resolution

Whether it is a rename, mode/type, or binary conflict, the final step requires inspecting both the index and the working tree. A file looking right when opened in an editor is not enough to prove Git has recorded that decision.

### 5.1. Stage the Exact Resolved Paths

For a file that was edited or had one side chosen:

~~~bash
git add -- path/to/file
~~~

For a file to be removed from the repository:

~~~bash
git rm -- path/to/obsolete-file
~~~

For renames or multiple related paths, stage both old and new paths within the verified scope:

~~~bash
git add -A -- old/path new/path
~~~

Only stage verified paths. Avoid mechanically running `git add .` because the working tree may hold unrelated changes that do not belong in this integration.

### 5.2. Confirm No Unmerged Entries Remain

Run:

~~~bash
git status
git diff --name-only --diff-filter=U
git ls-files -u
git diff --cached --check
git diff --cached --summary
~~~

What to confirm:

- `git status` no longer reports unmerged paths.
- `git diff --name-only --diff-filter=U` lists no unresolved files.
- `git ls-files -u` has no stage 1, 2, or 3 entries left.
- `git diff --cached --check` finds no common whitespace errors in staged changes.
- `git diff --cached --summary` helps verify the summary of renames, file creations/deletions, or mode changes.

Then inspect the final content and structure. For binary files, open them with an appropriate application. For symbolic links, verify the link target. For submodules, confirm the commit recorded by the parent repository is the desired commit.

### 5.3. Continue or Abort the Integration Operation

If merging and all conflicts are resolved:

~~~bash
git merge --continue
~~~

If rebasing:

~~~bash
git rebase --continue
~~~

If you need to stop the operation and return to the state before it started:

~~~bash
git merge --abort
~~~

Or:

~~~bash
git rebase --abort
~~~

Aborting is appropriate when the integration decision cannot proceed yet or needs further team discussion. Save any edits made during resolution separately if you want to keep them, because aborting returns the repository to the state before the merge or rebase and may discard work in progress.

After completing, inspect the history and status again:

~~~bash
git status
git log --oneline --graph --decorate -8
~~~

If merging, history may include a merge commit depending on the integration style. If rebasing, commits are replayed onto the new history base. In either case, ensure the working tree is in the expected state and changes are recorded.

## 6. Combined Example

A team is developing an e-commerce application. At the same time:

- Branch `feature/new-branding` renames `assets/logo-old.png` to `assets/logo.png` and updates the design.
- Branch `main` replaces the logo image at the old path with a new version provided by the branding team.
- Branch `feature/deploy` modifies `scripts/deploy.sh` and marks the file as executable.

During integration, the developer checks:

~~~bash
git status
git diff --name-only --diff-filter=U
git ls-files -u
~~~

For the logo, the team opens both versions in an image viewer, identifies the official version, and saves it at `assets/logo.png`. Then they remove the old path if it is no longer used and stage the related paths:

~~~bash
git add -A -- assets/logo-old.png assets/logo.png
~~~

For the deployment script, the team checks the current mode in the index and confirms the file must run directly. To set executable permission if needed:

~~~bash
git add -- scripts/deploy.sh
git update-index --chmod=+x -- scripts/deploy.sh
~~~

Next, the team verifies:

~~~bash
git ls-files --stage -- assets/logo.png scripts/deploy.sh
git diff --cached --summary
git status
git ls-files -u
~~~

Once no unmerged entries remain and the final versions are verified, the developer runs `git merge --continue` or `git rebase --continue` depending on the original operation. The Pull Request is then reviewed to confirm the logo matches the design and the deployment script still works in the target environment.

This scenario shows that a single integration can involve multiple types of decisions. Renames require aligning paths and preserving content; binary files require picking or producing a complete version; mode changes require verifying the attributes Git will record in the index.

## 7. Common Mistakes

- **Searching only for `<<<<<<<`:** rename, mode, or binary conflicts may not create delimiter markers inside file content. Check `git status` and `git ls-files -u`.
- **Deleting a path before inspecting its content:** this can lose edits from the other branch. Compare all versions before deciding.
- **Confusing ours and theirs during a rebase:** the meaning of the two sides differs from a standard merge. Check the active operation and inspect each side's content.
- **Using a text editor on binary files:** this can corrupt data. Use a format-aware application or choose a verified version.
- **Staging the entire repository without reviewing:** this can pull unrelated changes into the merge commit. Stage only the resolved paths.
- **Assuming Git stores full OS permissions:** Git only stores a specific set of modes. Verify the mode with `git ls-files --stage`.
- **Treating the remote as a place that resolves conflicts automatically:** a remote only exchanges commits and refs. Developers or appropriate merge tools must still decide the final content.

## 8. Summary

The three conflict groups have different characteristics and handling methods:

| Conflict group | What must be decided | Inspection or handling tools |
| --- | --- | --- |
| Rename | Final path and content to keep | `git status`, `git ls-files -u`, `git add -A`, `git log --follow` |
| File type or attribute change | Regular file, executable permission, symbolic link, or submodule commit | `git ls-files --stage`, `git update-index --chmod`, `git add` |
| Binary file | Choose one side or create a combined version with a specialized tool | `git restore --ours/--theirs`, appropriate application, `git add` |

The key principle is to inspect status and data before deciding. After selecting the final path, file type, and content, stage the exact scope, confirm the index has no unmerged entries remaining, and only then continue the merge or rebase. Following this sequence handles even conflicts that cannot be solved by editing text delimiter markers, while keeping Git history clear for the team to review later.
