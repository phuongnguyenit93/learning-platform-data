# Mainline History with --first-parent and Reading Merge Commits

When inspecting the history of an integration branch such as main, including every commit from every feature branch can make the graph long and hard to follow. Git provides the **--first-parent** option to follow the mainline of history: starting from the inspected commit, it steps backward along the first parent of each commit without branching into the remaining parents of merge commits.

This view answers the question: which integrations did the main branch receive, and in what order? It is especially useful in team workflows that regularly merge pull requests into main or release branches. To fully understand the contents of an integration, however, you still need to know how to inspect a merge commit's parents and read the diff of a merge against each parent.

## 1. Git History Is a Commit Graph

Each commit stores information about a project snapshot and references its parent commits. A regular commit has one parent; the repository's initial commit has no parent. A merge commit typically has two or more parents.

For example, a feature branch is created from main, develops two commits, and is then merged into main:

~~~text
X (main) has parents: M1, F2
M1 -> A
F2 -> F1 -> A
~~~ 

In this parent-relationship description:

- A is the common baseline commit.
- M1 is a commit created on main after the feature branch diverged.
- F1 and F2 are commits unique to feature/search.
- X is the merge commit bringing feature/search into main.

Merge commit X has the following parent order:

1. The first parent is M1, the tip of the current branch prior to the merge.
2. The second parent is F2, the tip of the branch being merged in.

This order matters when inspecting history. The notation X^1 references the first parent; X^2 references the second parent.

## 2. How Does --first-parent Follow the Mainline?

When you run:

~~~bash
git log --first-parent
~~~

Git starts at HEAD and walks backward through history. For regular commits, it moves to the single parent. When it encounters a merge commit, Git follows only the first parent. Side branches joined via the second parent or subsequent parents are not traversed from that merge.

With the graph above, the mainline output consists of:

~~~text
X  Merge feature/search
|
M1 Main: update roadmap
|
A  Initial commit
~~~

Commits F1 and F2 do not appear in the first-parent line because they reside on the side branch brought in through X's second parent. Merge commit X still appears, so readers know an integration occurred.

**--first-parent only changes how history is traversed when viewing the log.** It does not modify commits, alter parents, create branches, or rewrite repository history.

## 3. Comparing Full History and Mainline History

In a repository with many merged branches, the two views answer different questions:

| View | Content | Best Used When |
|---|---|---|
| git log | Commits reachable across the parent graph from the selected ref | Investigating detailed changes and commit origins |
| git log --first-parent | Only commits along the first-parent chain, including merge commits | Tracking integration progress on main or release branches |
| git log --first-parent --merges | Only merge commits along the mainline | Viewing branch integrations |
| git log --first-parent --no-merges | Non-merge commits along the mainline | Viewing commits made directly on the mainline or brought in via fast-forward/rebase |

Do not replace full history with first-parent in every scenario. When you need to know which commits a feature branch contained, why a line of code appeared, or which commit introduced a bug, inspect the full graph and the side branch's history.

## 4. Creating a Practice Repository with a Merge Commit

Create a separate repository so these commands do not affect any active project:

~~~bash
mkdir first-parent-lab
cd first-parent-lab
git init --initial-branch=main

git config user.name "Git Learner"
git config user.email "learner@example.test"

printf '# Project\n' > README.md
git add README.md
git commit -m "Initial project"
~~~

Check the baseline commit:

~~~bash
git status --short
git log --oneline --decorate -1
~~~

The working tree should be clean before branching. This lab assumes Git supports `git switch`; on older versions, use the equivalent `git checkout` commands.

## 5. Creating a Feature Branch and Adding Two Commits

Create the feature branch:

~~~bash
git switch -c feature/search
~~~

Create the first commit:

~~~bash
printf 'Search API: v1\n' > search.md
git add search.md
git commit -m "Add search API notes"
~~~

Create the second commit:

~~~bash
printf 'Search API: v2\nPagination: enabled\n' > search.md
git add search.md
git commit -m "Document search pagination"
~~~

Inspect the branch:

~~~bash
git log --oneline --decorate -3
~~~

The feature/search branch now has two commits ahead of the baseline commit. These commits are not yet on the main mainline.

## 6. Creating a Separate Commit on main

Switch back to main:

~~~bash
git switch main
~~~

Add a separate change on main:

~~~bash
printf 'Next milestone: search integration\n' > ROADMAP.md
git add ROADMAP.md
git commit -m "Update project roadmap"
~~~

The two branches have diverged: main has the roadmap commit, while feature/search has two search documentation commits. View the full graph:

~~~bash
git log --graph --oneline --decorate --all
~~~

You will see both branches originating from the Initial project commit. At this point there is no merge commit yet.

## 7. Creating a Merge Commit to Preserve the Integration Milestone

While on main, merge feature/search with --no-ff:

~~~bash
git merge --no-ff feature/search -m "Merge feature/search"
~~~

Because the two branches diverged, Git needs to combine both histories. The --no-ff option forces a merge commit even when a fast-forward would be possible. In this lab, a merge commit is created naturally because main gained its own commit after the feature branch diverged.

Inspect the graph:

~~~bash
git log --graph --oneline --decorate --all
~~~

Conceptual parent relationships after the merge:

~~~text
X (HEAD -> main): parents M1, F2
M1 -> A
F2 -> F1 -> A
~~~

X is the merge commit. The first parent is M1 because main was checked out when running the merge. The second parent is F2 because feature/search was the branch merged in.

## 8. Reading the Mainline with --first-parent

Run:

~~~bash
git log --first-parent --oneline --decorate main
~~~

The output will look like:

~~~text
* X (HEAD -> main) Merge feature/search
* M1 Update project roadmap
* A Initial project
~~~

Because the command traverses only the first parent, the mainline commit list forms a linear sequence. Commits F1 and F2 are not printed in this output. To observe side branches and connecting edges as well, omit --first-parent:

~~~bash
git log --graph --oneline --decorate main
~~~

The first-parent list contains only X, M1, and A. F1 and F2 are not traversed through X's second parent.

Compare with the full log:

~~~bash
git log --oneline --decorate main
~~~

The full log includes X, F2, F1, M1, and A because all of them are reachable from main through the merge commit's parents.

## 9. Viewing Only Integrations on the Mainline

To view merge commits on main:

~~~bash
git log --first-parent --merges --oneline --decorate main
~~~

This command is useful when summarizing pull requests or features integrated via merge commits. In this lab, the output includes Merge feature/search.

To view non-merge commits on the mainline:

~~~bash
git log --first-parent --no-merges --oneline --decorate main
~~~

The output includes commits made directly on the main line such as Update project roadmap and Initial project. Commits F1 and F2 are not listed because they sit behind the merge commit's second parent.

You can also include author and date:

~~~bash
git log --first-parent --format="%h %ad %an %s" --date=short main
~~~

When preparing release notes, this compact format displays integration order along with commit creator and date.

## 10. Identifying the Parents of a Merge Commit

A merge commit is not merely a commit whose subject starts with the word Merge. Inspect metadata to verify its actual parents:

~~~bash
# Display metadata and parents of HEAD
git show --no-patch --pretty=raw HEAD

# Print OIDs of the first and second parents
git rev-parse HEAD^1
git rev-parse HEAD^2

# View the commit along with its parents on separate lines
git log -1 --format="%H%n%P%n%s" HEAD
~~~

In git show --pretty=raw output, parent lines appear in order. The first parent is the line onto which the merge was performed; subsequent parents are the tips merged in.

Useful revision expressions:

| Syntax | Meaning |
|---|---|
| HEAD^1 | First parent of HEAD |
| HEAD^2 | Second parent of HEAD |
| HEAD^ | Shorthand for HEAD^1 |
| HEAD~1 | Step up one first parent |
| HEAD~2 | Step up two generations along the first-parent chain |
| HEAD^2~1 | From the second parent, step up one first parent of that commit |

For a merge commit, HEAD~1 and HEAD^1 both point to the first parent. HEAD~2 continues along the first parent of the first parent, not to the second parent of the merge.

## 11. Seeing What a Merge Commit Changed Relative to Each Parent

A key question when reviewing a merge is: what did the merge commit add to the mainline relative to main's previous state?

Compare the merge result against the first parent:

~~~bash
git diff HEAD^1 HEAD
~~~

This diff shows the merge result compared to main immediately before the merge. It is usually the clearest way to see what changes were brought into main.

Compare the merge result against the second parent:

~~~bash
git diff HEAD^2 HEAD
~~~

This diff shows how the final result differs from the merged-in feature branch. It may include changes that were already on main as well as conflict-resolution decisions.

Restrict by path when needed:

~~~bash
git diff HEAD^1 HEAD -- src/
git diff HEAD^2 HEAD -- src/
~~~

If checking a specific merge OID rather than the current HEAD, replace HEAD with the merge commit's OID or ref name.

## 12. Three Ways to Read a Merge Commit Diff

Because a merge commit has multiple parents, its diff can be presented in several ways:

| View | Command | Purpose |
|---|---|---|
| Against first parent | git diff M^1 M | See content the merge brought into the current branch |
| Against each parent | git show -m M | Show separate diffs of the merge commit against each parent |
| Combined diff | git show --cc M | Show combined format highlighting where the result differs from all parents |
| Re-merge diff | git show --remerge-diff M | Compare the committed merge result against a recreated automatic merge, useful for inspecting manual conflict resolutions |

Replace M with the OID of the merge commit you want to inspect.

### Diff Against the First Parent

~~~bash
git diff M^1 M
~~~

This is usually the most direct perspective when reviewing what was integrated into main. If the merge simply brought in feature changes without conflicts, the diff closely matches the feature branch's contributions.

### Separate Diff Against Each Parent with -m

~~~bash
git show -m --format=fuller M
~~~

The -m option displays separate diffs of the merge commit against each parent. This generates multiple perspectives; do not sum line counts across those diffs as though they were independent changes.

### Combined Diff with --cc

~~~bash
git show --cc M
~~~

Combined diff uses a multi-column format, typically with hunk headers starting with @@@. It is designed to show the merge result against multiple parents simultaneously. Paths that differ from only one parent may not appear in a combined diff; when you need to verify all integrated contents, also check the diff against the first parent or use -m.

### Re-merge Diff

~~~bash
git show --remerge-diff M
~~~

On Git versions supporting this option, Git recreates the merge result from the parents and compares it against the committed merge result. Differences help you review manual conflict-resolution choices. Results depend on the merge strategy and Git's ability to reproduce the merge; if an automatic merge produces the exact final content, the re-merge diff will show no changes.

## 13. How --first-parent Differs from Other Traversal and Ordering Options

Several log options look similar but answer different questions:

| Option | Effect |
|---|---|
| --first-parent | At merges, traverse only the first parent |
| --all | Start traversal from all refs known to Git |
| --merges | Select only merge commits |
| --no-merges | Exclude merge commits from results |
| --ancestry-path | Restrict to commits on the ancestry path between two selected endpoints |
| --topo-order | Order so child commits never appear before parent commits in the graph |
| --date-order | Prioritize commit dates while still preserving parent/child constraints |
| --graph | Draw connecting lines between commits in the graph |

--topo-order and --date-order change presentation order; they do not replace --first-parent's parent-selection rule. --ancestry-path is also not synonymous with first-parent: it filters by ancestry paths between two points, whereas first-parent picks a single edge when passing through a merge.

Examples:

~~~bash
# View main's mainline with a graph
git log --first-parent --graph --oneline main

# View all refs and the full graph
git log --all --graph --oneline --decorate

# View merge commits in full history
git log --merges --oneline main
~~~

## 14. Impact of Branch Integration Strategies

First-parent history depends on how a team integrates branches. Not every workflow creates two-parent merge commits.

| Integration Method | History Shape | What first-parent Shows |
|---|---|---|
| Merge commit | A commit with multiple parents | Shows the merge commit and continues along its first parent; side-branch commits are not traversed via the second parent |
| Fast-forward | main ref advances straight to the feature commit | Feature commits become main's first-parent chain and appear in the first-parent log |
| Squash merge | One new commit on main, usually with one parent | Shows the squash commit; original feature commits are not parents of the squash commit |
| Rebase then fast-forward | Feature commits recreated on top of updated main | First-parent shows the rebased commit chain as linear history |
| Octopus merge | Merge commit with more than two parents | First-parent follows only the first parent and skips all remaining parents during traversal |

### Fast-forward

If main has no new commits after feature branched off, main is an ancestor of feature. When merging, Git simply advances the main ref to the feature tip:

~~~bash
git merge feature/search
~~~

No new merge commit is created. Feature commits now sit directly on main's first-parent chain, so the first-parent log will display them. To preserve an integration milestone even when a fast-forward is possible, use --no-ff.

### Squash Merge

A squash merge creates a single new commit containing the combined changes of the feature branch without linking the feature commits as parents:

~~~bash
git merge --squash feature/search
git commit -m "Add search feature"
~~~

The first-parent log displays Add search feature as a normal mainline commit. It does not show that the commit combined F1 and F2 unless commit messages, metadata, or pull request linking conventions provide that context.

### Rebase

Rebasing recreates feature commits on top of a new base. If main is then fast-forwarded to the feature tip, the rebased commits become part of the mainline sequence. Recreated commits have different OIDs from the originals because their parents changed.

The first-parent log reflects the post-rebase topology rather than restoring the original branch structure. If you need to investigate pre-rebase history, you may need to inspect remaining refs, the reflog, or another repository clone.

## 15. When Should You Use First-Parent History?

First-parent is useful when:

- Tracking integration milestones into main or release branches.
- Writing release notes based on merge commits.
- Viewing mainline history without drowning output in granular feature-branch commits.
- Determining the sequence of integrations and commits made directly on the mainline.
- Quickly identifying which merge commits warrant deeper review.

Do not rely solely on first-parent when:

- Tracing the line of code or commit that introduced a bug.
- Reviewing every individual contribution within a feature branch.
- Investigating conflicts or code-fix decisions made inside a merge.
- Analyzing rebased or squashed history.
- Inspecting commits on branches not yet integrated into the mainline.

A solid workflow is to start with first-parent to understand integration milestones, then expand to full history and merge commit diffs when investigating specific questions.

## 16. Workflow for Reviewing a Merge Commit

When inspecting an integration into main, follow this sequence:

1. View merge commits along the mainline:

   ~~~bash
   git log --first-parent --merges --oneline --decorate main
   ~~~

2. Select merge commit M and read its metadata, especially parent order:

   ~~~bash
   git show --no-patch --pretty=raw M
   ~~~

3. Identify the mainline state before the merge and the tip of the merged branch:

   ~~~bash
   git rev-parse M^1
   git rev-parse M^2
   ~~~

4. Inspect the content introduced onto the mainline:

   ~~~bash
   git diff M^1 M
   ~~~

5. If the merge resolved conflicts, inspect each parent separately or run re-merge diff:

   ~~~bash
   git show -m M
   git show --remerge-diff M
   ~~~

6. To understand feature history, view commits reachable from the second parent:

   ~~~bash
   git log --oneline M^1..M^2
   ~~~

7. Run tests or checks relevant to the integrated changes.

Re-merge diff requires a Git version that supports it. If unavailable, compare diffs against each parent and inspect feature history to understand the result.

## 17. Common Misconceptions

| Misconception | Accurate Understanding |
|---|---|
| --first-parent only shows non-merge commits | No. It shows merge commits on the mainline, then continues along their first parent. |
| --first-parent deletes side-branch commits | No. It simply skips secondary parents in that log traversal; commits still exist in the graph if retained by refs or objects. |
| The first parent is always the chronologically newest commit | No. The first parent is determined by parent order recorded in the merge commit, usually the tip of the branch merged into. |
| The second parent is always a feature branch | In a normal two-branch merge, the second parent is the tip merged in; multi-branch merges can have additional parents. |
| HEAD~2 is the second parent of a merge | No. The ~ operator always follows the first-parent chain; use ^2 to select the second parent. |
| Every merge creates a merge commit | No. Fast-forward only moves a ref; squash creates a regular single-parent commit; rebase changes topology prior to integration. |
| Combined diff always shows every change from every parent | No. Combined diff follows its own display rules; inspect the diff against the first parent or use -m for fuller coverage. |
| First-parent shows the complete feature development history | No. It focuses on the integration line; use full history to inspect commits inside side branches. |

## 18. Self-Check

1. **What does --first-parent do when it encounters a merge commit?**
   - Follows only the first parent and does not traverse secondary parents from that merge.
2. **Which commit is typically the first parent of a merge commit on main?**
   - The tip of main immediately before the merge.
3. **Which command views only merge commits along the mainline?**
   - git log --first-parent --merges.
4. **How do you view the merge result's content compared to main before the merge?**
   - git diff M^1 M.
5. **How does HEAD~2 differ from HEAD^2?**
   - HEAD~2 steps back twice along the first parent; HEAD^2 directly selects the second parent.
6. **How does a squash merge appear in the first-parent log?**
   - As a normal mainline commit; the original feature commits are not parents of the squash commit.
7. **Why inspect full history after first-parent identifies a merge commit?**
   - To see granular commits on the side branch, change origins, and how the feature evolved.
8. **Which command helps inspect conflict resolutions that differ from an automatic merge result?**
   - git show --remerge-diff M on supported Git versions.

## Conclusion

--first-parent provides a focused view along a branch's integration mainline. It preserves merge commits as milestones while following only first parents to keep main or release branch history readable. To understand a merge commit, check parent order with git show --pretty=raw, distinguish the two sides using M^1 and M^2, and inspect diffs against the first parent, individual parents, or combined/re-merge diffs. Always pair first-parent with full history when tracing details, since fast-forward, squash, and rebase produce different topologies.
