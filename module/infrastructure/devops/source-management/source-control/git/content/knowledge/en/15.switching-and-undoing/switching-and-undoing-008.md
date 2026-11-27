# Picking Commits onto Another Branch with `git cherry-pick`

During development, sometimes a commit completed on one branch needs to appear on another branch. For example, the team fixed a security bug on `main` and the maintenance branch `release/2.4` also needs that fix; or an independent commit from a feature branch needs to be brought to an experimental branch. You can use `git cherry-pick` to select a specific commit and apply its changes onto the current branch.

`git cherry-pick` creates a new commit on the target branch based on the changes introduced by the source commit. It lets you transfer a portion of work without merging the entire source branch. Because the new commit has a different parent and commit ID from the original commit, cherry-pick is an operation that selectively applies changes, rather than moving the same commit between two branches.

In the Git section of the source code management module, cherry-pick complements switching branches, merging, rebasing, and undoing. Using it at the right time delivers needed fixes to the right branch while keeping history understandable and avoiding bringing along unfinished changes.

## 1. How Does Cherry-Pick Work?

Suppose branch `feature/payment` has a commit fixing an amount validation bug, and branch `release/2.4` needs that exact fix. Initial history:

```text
                 F1 --- F2  feature/payment
                /
A --- B --- C --- D  release/2.4
```

You are on `release/2.4` and run:

```bash
git switch release/2.4
git cherry-pick F1
```

Git takes the changes introduced by `F1`, applies them onto the current content of `release/2.4`, and creates a new commit `C1`:

```text
                 F1 --- F2  feature/payment
                /
A --- B --- C --- D --- C1  release/2.4
```

`C1` may contain the same source code changes as `F1`, yet it is not the same commit: its parent is `D`, whereas `F1`'s parent is `B`. Because commit content and parent are part of the commit identifier, `C1`'s hash differs from `F1`.

Cherry-pick does not pull the entire history of branch `feature/payment` into `release/2.4`. It applies only the selected commit. If `F1` depends on an earlier commit not yet on the target branch, you may need to pick the prerequisite commit in order as well or adapt the fix to fit the target branch.

## 2. Preparing Before Cherry-Picking

Before picking a commit, clearly identify the target branch, source commit, and repository state.

```bash
git status -sb
git branch --show-current
git log --oneline --decorate --graph --all -15
```

Check that:

- The working tree and staging area contain no unexpected unfinished changes. Cherry-pick can be blocked or become hard to control if uncommitted changes exist.
- You are on the branch that will receive the change. Cherry-pick applies commits onto the current `HEAD`; it does not automatically switch branches.
- The source commit already exists in the local repository and is the right commit to pick.
- Any prerequisite commits for the source commit are already on the target branch or will be applied in the proper order.
- The target branch does not already have an equivalent change introduced another way, avoiding duplicate fixes.

If the source commit is on a remote and not yet local, fetch first:

```bash
git fetch origin
git log --oneline origin/feature/payment
```

After identifying the right commit, inspect its contents before applying:

```bash
git show --stat <commit-id>
git show <commit-id>
```

`git show` lets you check the commit message, modified files, and patch. Do not rely solely on the commit title, as the contents may be broader than the summary.

## 3. Cherry-Picking a Single Commit

The basic workflow consists of switching to the target branch, identifying the commit, and running cherry-pick:

```bash
git switch release/2.4
git cherry-pick 7a31b20
```

If it applies cleanly without conflicts, Git creates a new commit on `release/2.4`. The new commit message is copied from the source commit by default. You can inspect the result:

```bash
git status -sb
git log --oneline --decorate -5
git show --stat HEAD
```

If you want to edit the commit message during cherry-pick, use `-e` or `--edit`:

```bash
git cherry-pick --edit 7a31b20
```

Git opens the editor so you can adjust the message before creating the commit. This is useful when adding context about why the fix was brought to the maintenance branch.

### Recording commit origin with `-x`

When you need to preserve a reference to the source commit in the message, use:

```bash
git cherry-pick -x 7a31b20
```

Git appends a line of the form `cherry picked from commit ...` to the new commit message. This line helps readers trace back to the original commit, which is useful when the same fix is ported across multiple release branches. Git typically adds this line only for conflict-free cherry-picks; if you have to resolve conflicts manually, proactively record the source commit in the message if project conventions require it.

## 4. Cherry-Picking Multiple Commits

You can pass multiple commit hashes in a single command:

```bash
git cherry-pick 7a31b20 91cd4e2 b8f02a1
```

Git applies the commits sequentially in the order passed. Order matters: a later commit may depend on changes from an earlier commit. Pass them in order from the older foundational commit to the newer commit.

For example, if `F1` creates a handler function and `F2` adds a call site for that function, apply `F1` before `F2`:

```bash
git cherry-pick F1 F2
```

If you want to pick a commit range, understand how revision ranges work. `A..B` selects commits reachable from `B` that are not in the ancestors of `A`; it excludes `A`. For a linear sequence, you can list them from oldest to newest and apply:

```bash
git rev-list --reverse A..B
```

Read the list first to verify the scope is right. Once confirmed, you can pass the commits in that order to `git cherry-pick` or pick individual commits explicitly. If you also need to include commit `A`, the usual range is `A^..B` when `A` has a parent.

Avoid cherry-picking a large range just because it is short to type. Inspect each commit to avoid bringing experimental changes, dependent commits, or out-of-scope changes onto the target branch.

## 5. Applying Changes Without Creating a Commit Using `-n`

The `-n` or `--no-commit` option applies changes from the source commit into the working tree and staging area without automatically creating a commit:

```bash
git cherry-pick --no-commit 7a31b20
```

You can inspect and adjust the result before creating the commit yourself:

```bash
git status
git diff
git diff --cached
```

After reviewing, you can create a new commit with an appropriate message:

```bash
git commit -m "Backport payment validation fix"
```

`--no-commit` is useful when you want to combine multiple picked changes into a single commit, or need to adapt a patch to fit an older version. When applying multiple commits with `-n`, changes accumulate in the index and working tree; check carefully so the final commit contains only intended content.

## 6. Cherry-Picking a Merge Commit with `-m`

A merge commit has multiple parents. Git needs to know which parent you want to take changes relative to, so cherry-picking a merge commit requires specifying the mainline parent with `-m`:

```bash
git cherry-pick -m 1 <merge-commit-id>
```

`-m 1` selects the first parent as the baseline. Git computes the difference of the merge commit relative to that parent and applies it onto the current branch. `-m 2` selects the second parent. Parent numbering starts at 1, not 0.

Before executing, inspect the parents:

```bash
git show --no-patch --pretty=raw <merge-commit-id>
git log --oneline --graph --decorate -10
```

For a merge commit, `git show` can display multiple parents. Understand which parent represents the base branch and which represents the merged branch. Choosing the wrong mainline can produce a patch opposite to your intent.

Cherry-picking a merge commit does not recreate the merge relationship between the two branches. It applies the diff relative to the selected parent and creates a new commit on the current branch. If the goal is to integrate a branch's full history, merge is usually more appropriate; cherry-picking a merge commit should only be used when you clearly understand the patch relative to the mainline.

## 7. Resolving Conflicts During Cherry-Pick

Conflicts occur when changes from the source commit cannot be applied automatically onto the target branch's current content. For example, the source commit modifies a line in `PaymentService.java`, while the target branch already modified that same line differently.

When cherry-pick stops, Git reports the conflicted files and leaves the operation in progress. Check:

```bash
git status
```

Open the conflicted file. Git may mark the unresolved region with conflict markers:

```text
<<<<<<< HEAD
Current content on the target branch
=======
Content from the commit being cherry-picked
>>>>>>> 7a31b20
```

This is an illustrative example; actual content depends on the file and merge strategy. Edit the file to the correct result, remove the markers, then stage the resolved file:

```bash
git add src/main/java/example/PaymentService.java
git status
```

Once all conflicts are resolved and staged, continue:

```bash
git cherry-pick --continue
```

If the list has multiple commits, Git proceeds to the next commit. You may need to resolve additional conflicts on subsequent commits.

### Canceling or skipping the commit being applied

If you want to cancel the entire in-progress cherry-pick sequence and return to the state before starting the operation:

```bash
git cherry-pick --abort
```

If you have confirmed the current commit does not need to be applied, you can skip that commit:

```bash
git cherry-pick --skip
```

`--skip` skips the commit causing the stop and continues with the rest of the sequence. Only use this when you understand the skipped change is unnecessary or handled elsewhere; if you skip a foundational commit, subsequent commits may fail to apply.

`git cherry-pick --quit` stops tracking the running operation while leaving the current index and working tree intact. This is not an undo command. If the goal is to return to the state before cherry-picking, use `--abort`.

## 8. When a Commit Is Already Applied or Becomes Empty

If the changes from the source commit already exist on the target branch, cherry-pick may report that there are no new changes to commit or stop because the commit became empty. This can happen when:

- The fix was already merged or cherry-picked previously.
- Another commit already produced the same content changes.
- While resolving conflicts, you chose content that leaves the current commit's patch with no remaining changes.

Before deciding, inspect history and content:

```bash
git log --oneline --all --decorate --grep="payment validation"
git show <commit-id>
git diff <target-branch>...<source-branch>
```

If the change is already present and no empty commit is needed as a marker, you can skip the commit following Git's instructions or use `git cherry-pick --skip` while in the sequencer state. If you intentionally need to keep an empty commit, Git provides `--allow-empty`; for commits that become empty because content is already applied, behavior can depend on Git version and the `--empty` option. Read Git's message and determine the reason before forcing an empty commit.

Do not repeatedly cherry-pick the same patch just because you do not see a commit with the same hash. A cherry-picked commit has a different hash from the source commit by design; compare content and history rather than hashes alone.

## 9. How Does Cherry-Pick Differ from Merge and Rebase?

The three operations serve different goals:

| Operation | Purpose | History impact |
| --- | --- | --- |
| `git merge` | Integrates a branch's history into the current branch | Keeps source commits and creates a merge commit if not fast-forward |
| `git rebase` | Replays a sequence of commits onto a different base | Creates new commits for the replayed sequence, changing commit hashes |
| `git cherry-pick` | Picks one or more specific commits to apply onto the current branch | Creates new commits with the selected changes without carrying over source branch ancestry |

Examples:

- Use **merge** when you want to integrate the entire `feature/payment` branch into `main` preserving branch history.
- Use **rebase** when you want to place `feature/payment`'s commit sequence onto the tip of a new base branch.
- Use **cherry-pick** when you only need a single isolated fix from `feature/payment` on `release/2.4`.

Cherry-pick can cause the same change to appear in multiple branches' histories under different commit hashes. If those branches are later merged, Git does not recognize two different-hash commits as the same commit merely because their patches are similar. Consider your branching strategy and record origins clearly to avoid difficulties during later integration.

## 10. Workflow for Backporting a Fix to a Release Branch

Backporting means bringing a change from a newer development branch back to an older version branch. Cherry-pick is commonly used for this task when only specific identified fixes are needed.

Suppose the team fixed a bug on `main` and wants to port that commit to `release/2.4`:

### Step 1: Update remote information

```bash
git fetch origin
git log --oneline origin/main -10
```

Find the reviewed commit confirmed as appropriate for the release branch. Inspect its patch and dependencies.

### Step 2: Switch to the release branch

```bash
git switch release/2.4
git status -sb
```

Ensure the working tree is clean and you are on the right target branch. If the local release branch needs updates from the remote, integrate the latest state per project workflow before cherry-picking.

### Step 3: Apply the commit and record its origin

```bash
git cherry-pick -x <fix-commit-id>
```

If conflicts occur, resolve them as shown earlier and run `git cherry-pick --continue`.

### Step 4: Verify the result

```bash
git show --stat HEAD
git show HEAD
git status -sb
```

Run tests appropriate for the release version. A fix that works on `main` is not guaranteed to be compatible with the APIs, libraries, or source structure of an older version.

### Step 5: Share via team workflow

After review and successful testing, push the release branch or open a pull request as required:

```bash
git push origin release/2.4
```

If the release branch is protected, submit a pull request instead of pushing directly. Cherry-pick only handles bringing the change onto the local branch; write permissions and release workflows are still governed by the server and team.

## 11. Common Options

| Option | Effect |
| --- | --- |
| `-x` | Records the source commit hash in the new commit message |
| `-e`, `--edit` | Opens editor to edit the commit message |
| `-n`, `--no-commit` | Applies changes to index/working tree without automatically creating a commit |
| `-m <parent-number>` | Selects the mainline parent when cherry-picking a merge commit |
| `--continue` | Continues the sequence after resolving conflicts |
| `--abort` | Cancels the in-progress cherry-pick sequence and restores pre-operation state |
| `--skip` | Skips the current commit and continues the sequence |
| `--quit` | Stops the sequencer while keeping the current index and working tree state |
| `--ff` | Fast-forwards if current `HEAD` is the parent of the selected commit |
| `--allow-empty` | Allows creating an empty commit where appropriate |

Read `git help cherry-pick` to see the full set of options and differences for your installed Git version.

## 12. Common Errors and How to Handle Them

| Situation | Possible cause | How to handle |
| --- | --- | --- |
| `bad object` or commit not found | Commit is not yet local or commit hash is wrong | Fetch from the right remote, verify ref and commit hash |
| Cherry-pick reports conflict | Patch does not apply automatically to target branch | Resolve files, stage, run `--continue` |
| Cherry-pick reports empty | Change already exists or was neutralized during resolution | Inspect content, then skip or keep empty commit if intentional |
| Cherry-pick merge commit requires `-m` | Source commit has multiple parents | Inspect parent order and choose the appropriate mainline |
| Result fails on release | Commit depends on APIs or other commits not yet ported | Inspect patch, find dependencies, pick prerequisite commits in order, or adapt the backport |
| Cherry-picked the wrong commit | Wrong commit or wrong target branch chosen | If in progress, `--abort`; if commit already created, assess impact and consider `git revert` |
| Fix appears twice | Same patch was introduced by another commit | Compare diffs and history before proceeding |

If a cherry-pick already completed and created an unwanted commit, do not casually reset a shared branch. For shared commits, `git revert <new-commit-id>` is usually the way to create a new reversing commit while keeping published history. On an unshared personal branch, you can choose an appropriate history-editing approach, but check the working tree and subsequent commits before acting.

## 13. Practice

Perform this in a test repository so shared branches are unaffected:

1. Create a branch `feature/report` and create a commit adding a reporting feature.
2. Create a branch `release/test` from an earlier commit so it does not yet contain the reporting commit.
3. Switch to `release/test` and run `git cherry-pick <commit-id>` to pick the reporting commit.
4. Use `git log --oneline --graph --decorate --all` to observe the two branches having commits with similar content but different commit hashes.
5. Try `git cherry-pick -x <commit-id>` with another bugfix commit and inspect the new message.
6. Try `git cherry-pick -n <commit-id>`, inspect the index/working tree, then create the commit manually.
7. On another test branch, create a scenario where two branches edit the same line to observe a conflict; resolve it with `--continue`, then try again and cancel with `--abort`.
8. Create a merge commit in the test repository and inspect its parents with `git show --pretty=raw`; try cherry-picking the merge commit with the appropriate mainline.

After practicing, explain why cherry-pick creates a new commit, when multiple commits must be picked in order, and why a backport must be tested on the older version branch itself.

## 14. Knowledge Self-Check

1. Where does `git cherry-pick <commit>` apply the source commit's changes?
2. Why does a commit created by cherry-pick have a different hash from the source commit?
3. What should you check before cherry-picking a commit from a remote branch?
4. What information does `git cherry-pick -x` add to the new commit?
5. In which scenarios is `--no-commit` appropriate?
6. Why does cherry-picking a merge commit require specifying `-m` and a mainline parent?
7. When a conflict occurs, what is the sequence of steps to continue cherry-pick?
8. How do `--abort`, `--skip`, and `--quit` differ?
9. When should you use merge or rebase instead of cherry-pick?
10. Why should you check for potential duplicate patches before backporting?

## Conclusion

`git cherry-pick` lets you select specific commits and apply their changes onto the current branch. It is a useful tool for backporting, porting urgent fixes, and reusing a subset of work across branches. Identify the right target branch and source commit, check dependencies, resolve conflicts intentionally, and verify content after applying. Because cherry-pick creates new commits without carrying over the source branch's history relationships, record origins clearly and coordinate with your team when the same fix is delivered to multiple branches.
