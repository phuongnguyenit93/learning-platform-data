# Merge Strategies and Distinguishing ours from the -X ours Option

When merging two branches, Git must create a combined snapshot from the histories and contents of the branches. Sometimes Git combines all changes automatically; other times both branches edit the same region and conflict resolution rules are needed. Git provides multiple merge strategies and strategy options to control this process.

A crucial distinction is between the `-s ours` strategy and the `-X ours` option:

- `-s ours` selects a merge strategy whose resulting tree always comes from the current branch, ignoring the entire tree contents of the merged branch.
- `-X ours` is an option passed to a merge strategy such as `ort`; it favors the current side's version in conflicted sections, while still bringing non-conflicting changes from the other branch into the result.

Both flags contain the word `ours`, yet their purposes are completely different. Mistakenly using `-s ours` can prevent all changes from the other branch from appearing in the source tree even though that branch's history is marked as merged.

## 1. Merge Strategy Determines How Git Combines Trees

When merging a branch into the current branch, Git normally finds the merge base—the nearest common ancestor commit—and compares changes from the base to each side. The merge strategy defines how Git constructs the resulting tree from these inputs.

For example, two branches both develop from commit A:

~~~text
             B---C  feature
            /
A----------+
            \
             D---E  main (HEAD)
~~~

When on main and running:

~~~bash
git merge feature
~~~

Git needs to combine changes from B and C with changes from D and E. If there are no conflicts and main can fast-forward, Git may simply move the ref. If the two branches have diverged, Git typically creates a merge commit after combining the trees.

The merge strategy and how the merge commit is created are related but distinct concepts. The strategy handles tree contents; options such as `--ff-only`, `--no-ff`, or `--squash` control how the result is recorded in history.

## 2. The Default Strategy: ort

For two-head merges, modern Git uses the `ort` strategy by default. The name `ort` stands for "Ostensibly Recursive's Twin"; this strategy was designed to replace `recursive` in newer Git versions.

You can specify it explicitly:

~~~bash
git merge -s ort feature
~~~

In most standard workflows, you only need:

~~~bash
git merge feature
~~~

Git automatically selects the appropriate default strategy.

`ort` processes three-way changes based on the merge base, detects renames, combines non-conflicting changes, and reports regions requiring manual resolution. It cannot understand the business semantics of code. A merge result with no textual conflicts can still contain logic bugs or fail to compile, so post-merge testing and review remain necessary.

Other strategies serve specialized purposes:

| Strategy | Primary purpose | When to consider |
|---|---|---|
| ort | Modern three-way two-head merge | Default choice for normal merges |
| ours | Keep the current branch's tree intact, discard the merged branch's tree | Record that the other branch's history was integrated by ancestry while its content is superseded |
| octopus | Combine three or more heads in a single merge | Combine multiple small, independent branches without complex conflict resolution |
| subtree | Adjust tree structure to merge a subproject into a subdirectory of a parent project | Integrating sub-repositories under the subtree model |
| resolve | Older two-head merge strategy with more limited handling | Only encountered in legacy workflows or repositories |

When multiple branches are passed to a single merge command, Git normally selects `octopus`. This strategy is designed for branches that combine cleanly; if complex conflict resolution is needed, merge each branch individually with `ort` to control each step.

## 3. The -s ours Strategy: Keeping the Entire Current Tree

Syntax:

~~~bash
git merge --no-ff -s ours feature/legacy
~~~

You should use `--no-ff` when the goal is to record a merge commit using the `ours` strategy. If fast-forward is allowed, Git may simply advance the branch to the other commit without running the strategy's merge result creation; in that case the other branch's tree would appear.

When using the `ours` strategy:

- The resulting merge tree is identical to HEAD's tree before the merge.
- File changes from `feature/legacy` are not brought into the resulting tree.
- When the merge does not fast-forward (or with `--no-ff`), Git creates a merge commit whose parents are the current HEAD and the tip of `feature/legacy`.
- The history of `feature/legacy` is joined into the commit graph and is considered merged by ancestry.

Example:

~~~text
Before merge:

main:       A---B  (HEAD)
                 \
feature:          C---D

After git merge --no-ff -s ours feature:

main:       A---B---------M  (HEAD)
                 \       /
feature:          C---D

Tree of M matches tree of B.
~~~

Use this strategy when you intentionally want to keep an old branch's history without taking any of its content into the current tree. A typical scenario is when a legacy branch has been completely replaced by a new implementation, yet the team wants to record the historical relationship so Git knows the old branch was handled.

Example:

~~~bash
git switch main
git merge --no-ff -s ours legacy/old-implementation \
  -m "merge: mark old implementation as superseded"
~~~

After merging, verify:

~~~bash
git show --no-patch --pretty=raw HEAD
git diff HEAD^1 HEAD
git merge-base --is-ancestor legacy/old-implementation HEAD
~~~

If the merge succeeded, the new commit has two parents; the diff between the first parent and the merge commit shows no tree changes because the `ours` strategy preserves the current side's tree. The ancestry check returns exit code 0 if the legacy branch tip is an ancestor of the merge commit.

**Warning:** The `ours` strategy is not a shortcut for ignoring conflicts. It discards the entire tree contents from the merged branch. Because Git records that branch as an ancestor of the merge commit, subsequent merges from that same history may not bring back the discarded changes. Only use it when discarding the content is intentional and has been reviewed.

## 4. The -X ours Option: Favoring the Current Side Only in Conflicted Sections

Syntax:

~~~bash
git merge -X ours feature/search
~~~

Here Git still uses a merge strategy, normally `ort`. The `-X ours` option tells the strategy to favor the current side's content in sections where conflicts occur.

Key points:

- Non-conflicting changes from `feature/search` are still included in the result.
- For conflicting text hunks, Git selects the current side's content.
- For binary files, picking a side can apply to the entire file because Git cannot merge binary files line by line.
- Git still produces the merge result using the selected strategy; this is not a standalone strategy.

For example, two branches both edit `settings.conf`.

Common base version:

~~~ini
timeout=30
format=json
~~~

The `main` branch edits:

~~~ini
timeout=45
format=json
metrics=true
~~~

The `feature/retry` branch edits:

~~~ini
timeout=60
format=json
retries=3
~~~

The `timeout` line was modified differently on both sides, so it conflicts. The `metrics` and `retries` lines are non-conflicting changes, so Git can keep both.

When on `main`:

~~~bash
git merge -X ours feature/retry
~~~

Expected resulting tree:

~~~ini
timeout=45
format=json
metrics=true
retries=3
~~~

The `timeout` line comes from `main`; `retries` from `feature` is still kept. This is the core difference from `-s ours`, which would keep `main`'s entire tree unchanged and omit `retries`.

## 5. The -X theirs Option: Favoring the Branch Being Merged

Syntax:

~~~bash
git merge -X theirs feature/retry
~~~

In a normal merge command:

- Ours is the current branch, i.e., the branch HEAD is on.
- Theirs is the branch passed to the merge command.
- `-X theirs` selects the merged side in conflicted sections.
- Non-conflicting changes from both sides are still combined.

With the `settings.conf` example, if run from `main` using `-X theirs`, the expected result is:

~~~ini
timeout=60
format=json
metrics=true
retries=3
~~~

The `timeout` line is taken from `feature/retry`, while non-conflicting changes from both `main` and `feature` are preserved.

There is no standard built-in merge strategy named `theirs` corresponding to the `ours` strategy. The syntax `-s theirs` is not a valid substitute for `-X theirs` in standard Git. Always distinguish a strategy from a strategy option.

## 6. Direct Comparison of -s ours and -X ours

| Criterion | -s ours | -X ours |
|---|---|---|
| Option type | Selects merge strategy | Selects strategy option |
| Scope of favoring ours | Entire resulting tree | Conflicted sections only |
| Non-conflicting changes from other branch | Ignored | Preserved in result |
| Resulting tree | Identical to HEAD's tree before merge | Combined result after favoring ours in conflicts |
| Merge ancestry | Still creates parent relationship with other branch | Still creates parent relationship with other branch |
| Purpose | Mark the other branch's history as handled without taking its content | Automatically resolve conflicts by favoring current content |
| Main risk | Discards all content from the other branch while still recording ancestry | May choose wrong content in conflicted regions if unreviewed |

Mnemonic:

~~~text
-s ours
  = use the entire current side's tree for the merge result

-X ours
  = merge normally, but favor the current side in conflicted sections
~~~

If the goal is "keep non-conflicting changes from both branches, only pick my version on conflicting lines," consider `-X ours` or manual conflict resolution. Only consider `-s ours` if the goal is "mark the other branch as superseded and take none of its content."

## 7. Ours and Theirs Depend on Merge Direction

Suppose you are on `main` and run:

~~~bash
git merge feature/login
~~~

Then:

- Ours = `main`, the current branch.
- Theirs = `feature/login`, the branch being merged in.

If you reverse the operation direction, the meaning reverses as well. Standing on `feature/login` and merging `main` makes `feature/login` ours and `main` theirs.

Do not think of `ours` as "the main branch" or `theirs` as "the secondary branch." They are relative concepts based on the operation being executed.

Check the current branch before merging:

~~~bash
git branch --show-current
git status -sb
git log -1 --oneline --decorate
~~~

This is especially important when running automated merge scripts or when multiple branches have similar names.

## 8. Ours and Theirs in Rebase Can Feel Inverted

During a rebase, Git replays each commit of the working branch onto a new base. While resolving conflicts, Git's definition of `ours` and `theirs` differs from the intuition "the branch I am working on is ours."

Example:

~~~bash
git switch feature/login
git rebase main
~~~

When a commit from `feature/login` is being replayed onto `main`:

- Ours is typically the target branch onto which commits are being replayed—that is, `main` plus the commits already replayed successfully.
- Theirs is the commit from the working branch currently being replayed.
- Consequently, `--ours` in a rebase conflict can select the version from `main`, while `--theirs` selects the version from the feature commit being applied.

This rule is easy to mix up when switching from merge to rebase. Read rebase output, inspect stages in the index, and verify actual contents before choosing.

To inspect conflicted versions:

~~~bash
git status
git ls-files -u
~~~

For a specific file, you can view its stages if they exist:

~~~bash
git show :1:path/to/file
git show :2:path/to/file
git show :3:path/to/file
~~~

Stage 1 is normally the common base, stage 2 is ours in the current merge/rebase context, and stage 3 is theirs. Not every conflict type has all three stages; for example, add/add may have no stage 1.

## 9. Using -s and -X in the Right Places

General syntax:

~~~bash
git merge -s <strategy> -X <strategy-option> <branch>
~~~

Example using `ort` and favoring ours:

~~~bash
git merge -s ort -X ours feature/search
~~~

Because `ort` is the default for two-head merges, this can be shortened to:

~~~bash
git merge -X ours feature/search
~~~

Example using the `ours` strategy:

~~~bash
git merge --no-ff -s ours feature/obsolete
~~~

Do not confuse these options:

| Syntax | Role |
|---|---|
| -s ort | Selects the `ort` strategy |
| -s ours | Selects the strategy that preserves the entire current tree |
| -X ours | Option favoring the current side in conflicted regions |
| -X theirs | Option favoring the merged side in conflicted regions |
| --no-ff | Disallows fast-forward; forces a merge commit if merge succeeds |
| --ff-only | Accepts fast-forward only |
| --squash | Prepares tree/index result like a merge without creating a merge commit or recording merge ancestry |
| --no-commit | Pauses before creating the merge commit for review; combine with `--no-ff` to ensure no fast-forward |

`--no-ff`, `--ff-only`, `--squash`, and `--no-commit` are not merge strategies. They control how the merge process records history or pauses.

## 10. Useful Strategy Options for ort

The `-X` option is not limited to `ours` and `theirs`. Several other options help handle specific differences:

| Option | Effect |
|---|---|
| -X patience | Uses the patience diff algorithm to align changes |
| -X diff-algorithm=histogram | Selects the histogram diff algorithm |
| -X ignore-space-change | Ignores differences in whitespace amount when comparing |
| -X ignore-all-space | Ignores all whitespace differences during conflict detection |
| -X ignore-space-at-eol | Ignores trailing whitespace at end of line |
| -X renormalize | Runs virtual clean filters on all three file versions before merging, useful when normalization rules changed |
| -X find-renames | Enables rename detection |
| -X find-renames=80% | Sets similarity threshold for rename detection |
| -X no-renames | Disables rename detection |
| -X subtree or -X subtree=path | Adjusts tree level when integrating content using the subtree model |

Supported options may depend on the strategy and Git version. If Git reports an invalid option, check the documentation for your Git version and chosen strategy.

Do not use ignore-space options to mask meaningful changes. For example, whitespace inside strings, YAML, Python, or Makefiles can alter behavior. Always inspect diffs and run tests after merging.

## 11. When Should You Automatically Favor ours/theirs?

Automatic favoring can be useful when the team has clear conventions for a specific content area and knows exactly what conflicts to expect. For example:

- An auto-generated file has a clear regeneration process and the team agrees which source is canonical.
- A configuration branch is intentionally maintained on one side, while non-conflicting changes still need integration.
- A merge has many repetitive conflicts and the team has determined a consistent selection rule.

Do not use `-X ours` just to make a merge "green" or to avoid reading conflicts. If both sides modified the same business logic, automatically picking one side can silently drop the other side's requirements.

For config files, inspect each key and its meaning. For code, check behavior, tests, and APIs. For binary files, keep in mind that Git usually cannot merge partial content like text files; favoring one side may replace the entire file.

## 12. Manual Conflict Resolution When Exact Control Is Needed

If you do not want an automatic policy, merge normally:

~~~bash
git merge feature/search
~~~

When conflicts occur, Git pauses the merge and marks unresolved files. Check:

~~~bash
git status
git diff --name-only --diff-filter=U
git ls-files -u
~~~

Open each file and read the markers:

~~~text
<<<<<<< HEAD
Content from current branch
=======
Content from branch being merged
>>>>>>> feature/search
~~~

Combine the right content, remove markers, and stage the file:

~~~bash
git add path/to/file
~~~

If you need to select the entire `ours` or `theirs` version for one file, you can use:

~~~bash
git restore --ours --worktree -- path/to/file
git add path/to/file
~~~

Or:

~~~bash
git restore --theirs --worktree -- path/to/file
git add path/to/file
~~~

This selects one side for a currently unmerged file; it is not the same as `-X ours` applied while the strategy automatically processes the merge. After staging, check:

~~~bash
git status
git diff --cached
~~~

Once all conflicts are resolved, conclude the merge:

~~~bash
git merge --continue
~~~

Or create the merge commit with `git commit` if your workflow requires it. To cancel a paused merge:

~~~bash
git merge --abort
~~~

Only abort after accounting for any pre-merge local changes; Git attempts to restore the state before the merge began.

## 13. Previewing the Merge Result Before Committing

If you want to inspect the resulting tree before creating a merge commit, use:

~~~bash
git merge --no-ff --no-commit feature/search
~~~

Git performs the merge and updates the index/working tree, pausing before creating the commit. Once ready to review:

~~~bash
git status
git diff
git diff --cached
~~~

Run appropriate tests. If the result is correct, continue:

~~~bash
git merge --continue
~~~

If you do not want that result, abort:

~~~bash
git merge --abort
~~~

With `-X ours`, this is useful for reviewing hunks that were automatically chosen. With `-s ours`, the resulting tree is kept identical to HEAD anyway; confirm that discarding all content from the other branch is genuinely the goal.

## 14. Practice A: Observing -X ours Preserve Non-Conflicting Changes

Perform this in a test repository, never on a shared release branch.

Create the repository and initial file:

~~~bash
mkdir merge-strategy-lab
cd merge-strategy-lab
git init -b main
git config user.name "Git Learner"
git config user.email "learner@example.test"
printf "timeout=30\nformat=json\n" > settings.conf
git add settings.conf
git commit -m "chore: add initial settings"
~~~

Create a feature branch, modify timeout, and also add retries:

~~~bash
git switch -c feature/retry
printf "timeout=60\nformat=json\nretries=3\n" > settings.conf
git add settings.conf
git commit -m "feat: add retry configuration"
~~~

Switch back to main, modify the same timeout line, and also add metrics:

~~~bash
git switch main
printf "timeout=45\nformat=json\nmetrics=true\n" > settings.conf
git add settings.conf
git commit -m "feat: add metrics configuration"
git branch manual-merge-base main
~~~

Inspect history:

~~~bash
git log --oneline --graph --all
~~~

Merge feature favoring ours while pausing before commit:

~~~bash
git merge --no-ff --no-commit -X ours feature/retry
~~~

Read the result:

~~~bash
git status
git diff --cached -- settings.conf
~~~

The expected content has `timeout=45`, `metrics=true`, and `retries=3`. If the result is right, finish:

~~~bash
git merge --continue
~~~

Verify the merge commit has two parents:

~~~bash
git show --no-patch --pretty=raw HEAD
~~~

Key observation: `-X ours` chose `main`'s `timeout` in the conflicted region, yet still brought `retries` from `feature` into the result.

## 15. Practice B: Demonstrating -s ours Discards the Entire Merged Branch Tree

Continue in the test repository. Create a branch with its own file:

~~~bash
git switch -c legacy/old-settings
printf "legacy=true\n" > legacy-only.conf
git add legacy-only.conf
git commit -m "feat: add legacy settings"
~~~

Switch back to main:

~~~bash
git switch main
~~~

Record the legacy branch's history while keeping main's tree intact:

~~~bash
git merge --no-ff -s ours legacy/old-settings \
  -m "merge: mark legacy settings as superseded"
~~~

Verify:

~~~bash
git show --no-patch --pretty=raw HEAD
git ls-tree HEAD -- legacy-only.conf
git merge-base --is-ancestor legacy/old-settings HEAD
~~~

Expected observations:

- The merge commit has the tip of `legacy/old-settings` as its second parent.
- `git ls-tree` does not list `legacy-only.conf` in main's tree after the merge.
- The ancestry check returns exit code 0.
- The legacy history is connected, yet the legacy file content was not brought into the resulting tree.

This is intentional behavior of the `ours` strategy. If you want to keep `legacy-only.conf` or other changes, do not use this approach.

## 16. Practice C: Comparing Results Against a Manual Merge

Create a branch from the point on `main` before Practice A's merge. The `manual-merge-base` branch was created in Practice A, so it can be reused to create an independent conflict scenario:

~~~bash
git switch -c manual-merge-lab manual-merge-base
git merge feature/retry
~~~

If there is a conflict, Git marks the file unmerged. Inspect the versions in the index:

~~~bash
git ls-files -u
git show :1:settings.conf
git show :2:settings.conf
git show :3:settings.conf
~~~

Resolve by writing the desired content, stage, and complete the merge. Compare the result with the `-X ours` merge to see that an automatic choice can match a specific manual decision, though it never replaces understanding what the changes mean.

## 17. Inspecting Merge Results via Graph and Tree

After merging, use these commands:

~~~bash
git log --oneline --graph --decorate --all
git show --no-patch --pretty=raw HEAD
git diff HEAD^1 HEAD
git diff HEAD^2 HEAD
git merge-base --is-ancestor feature/retry HEAD
~~~

Meaning:

- `git log` shows the graph shape and connection points.
- `git show --pretty=raw` shows the parents of the merge commit.
- `git diff HEAD^1 HEAD` shows how the merge tree differs from the first parent.
- `git diff HEAD^2 HEAD` shows how the merge tree differs from the second parent.
- `git merge-base --is-ancestor` checks whether the source branch has become an ancestor of the merge commit.

With the `-s ours` strategy, the diff from the first parent to the merge commit is normally empty because the resulting tree matches the current side. The diff against the second parent can be large because none of the other branch's content was kept.

With `-X ours`, diffs against both parents can show combined changes alongside conflicted regions where one side was favored. Do not judge correctness by diff line count alone; review content and run tests.

## 18. History Options That Are Not Merge Strategies

Several options are easily confused with strategies:

### Fast-forward

~~~bash
git merge --ff-only feature
~~~

Allows moving the current branch forward only if no merge commit is needed. If the two branches have diverged, the command refuses.

### Forcing a merge commit

~~~bash
git merge --no-ff feature
~~~

Creates a merge commit even when fast-forward is possible. This keeps an explicit integration point in history.

### Squash

~~~bash
git merge --squash feature
~~~

Prepares combined changes in the index and working tree without creating a merge commit and without recording ancestry via a merge commit. Afterward you create a regular commit.

### Pausing before commit

~~~bash
git merge --no-commit --no-ff feature
~~~

Allows reviewing the tree/index before creating the merge commit. `--no-ff` prevents Git from completing via fast-forward before having a chance to pause.

These options can be combined with appropriate strategies or strategy options, but you must understand each individual effect. For instance, `-X ours` determines content in conflicted regions; `--no-ff` determines history shape.

## 19. Common Mistakes

- **Using `-s ours` to keep most of your own changes:** this command discards the merged branch's entire tree, including non-conflicting changes.
- **Thinking `-X ours` discards the other branch completely:** this option only favors the current side in conflicted sections; non-conflicting changes are still combined.
- **Using `-s theirs`:** standard Git does not provide a built-in `theirs` strategy; use `-X theirs` if you want to favor the merged side in conflicted regions.
- **Assuming `ours` is always `main`:** `ours` is the current branch of the merge operation; reversing the merge direction reverses the roles.
- **Applying merge intuition to rebase:** `ours`/`theirs` labels in rebase conflicts can feel inverted compared to thinking about feature branches.
- **Using `-X ours` to skip review:** automatically selected content can still violate logic or break compatibility.
- **Confusing `--no-ff` with a strategy:** it is an option controlling fast-forward and merge commits.
- **Not checking the tree after the `ours` strategy:** a merge commit may exist while files from the source branch are completely absent from the snapshot.
- **Not running tests after merging:** Git only combines content; it does not prove the program works correctly.

## 20. Workflow for Choosing a Strategy

Before merging, answer in sequence:

1. Which branch are you on, and which branch are you merging in?
2. Do you need to keep all non-conflicting changes from both sides?
3. When conflicts occur, does the team have a clear rule for favoring one side?
4. Do you intentionally want to discard the entire tree contents from the merged branch?
5. Do you need a merge commit marking the integration point, or do you want a squash?
6. Should the result be inspected before committing?

Choose the right approach:

| Intent | Suitable command |
|---|---|
| Normal merge and manual conflict resolution | git merge feature |
| Normal merge, favor ours in conflicts | git merge -X ours feature |
| Normal merge, favor theirs in conflicts | git merge -X theirs feature |
| Keep current tree intact while recording other branch's ancestry | git merge --no-ff -s ours feature |
| Allow fast-forward only | git merge --ff-only feature |
| Always create a merge commit | git merge --no-ff feature |
| Get combined result without creating a merge commit | git merge --squash feature |
| Combine multiple independent branches at once | git merge branch-a branch-b branch-c, typically using octopus if no complex conflict resolution is needed |

When unsure, use the default `ort`, resolve conflicts manually, and verify the result. Only pick `-X ours/theirs` or `-s ours` when the goal is explicit.

## 21. Pre- and Post-Merge Checklist

Before merging:

- [ ] Working tree and index have been checked.
- [ ] Current branch and source branch are confirmed.
- [ ] Fetched remote if the source branch comes from a remote.
- [ ] Inspected merge base and commits on both sides.
- [ ] Selected the right strategy or strategy option for the goal.
- [ ] Have a backup or suitable recovery plan if the operation has a large scope.

After merging:

- [ ] No unmerged files remain.
- [ ] Resulting tree retains the required changes from both sides.
- [ ] If `-s ours` was used, discarding the entire source branch tree was intentional.
- [ ] Merge commit parents are as expected.
- [ ] Reviewed diffs against both parents when needed.
- [ ] Tests, build, and integration checks passed.
- [ ] Branch and history were shared per team workflow.

## 22. Takeaways

`-s ours` and `-X ours` differ in scope of impact. The `-s ours` strategy keeps the current branch's entire tree intact while still connecting the merged branch's history via a merge commit. The `-X ours` strategy option is used within a strategy like `ort` to favor the current side's content in conflicted regions while still keeping non-conflicting changes from the other branch. `ours` and `theirs` are determined by merge direction; in rebase, the naming can feel counterintuitive. Choose the strategy according to your history and content goals, review the tree after merging, and run tests before sharing the result.
