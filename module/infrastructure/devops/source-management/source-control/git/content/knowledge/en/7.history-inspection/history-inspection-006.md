# Commit Ranges A..B and A...B in History Traversal Commands

When comparing two branches, common questions are: which commits exist on `feature` but not yet on `main`, and which commits exist only on one of the two branches? Git uses revision range syntax to select the commit set to traverse. In `git log`, `A..B` selects commits reachable from B but not reachable from A; `A...B` selects commits reachable from only one side, excluding the history shared by both.

The two syntaxes look nearly identical but answer different questions. Understanding the commit set selected by each range helps you review pull requests, check branch divergence, prepare for merges/rebases, and avoid confusing `git log` range syntax with `git diff`.

## 1. Git Traverses History by Reachability

Git does not store a branch as an independent list of commits. Each branch is a ref pointing to a commit; from that commit, Git follows parent links backward through history. A commit is considered **reachable** from a revision if you can walk from that revision via parent links to reach that commit.

Example of two branches sharing history and then diverging:

```text
             C1---C2  feature
            /
A---B---M1---M2      main
```

In this diagram:

- `A` and `B` are shared history.
- `M1` and `M2` are reachable only from `main` (assuming no other branch points to them).
- `C1` and `C2` are reachable only from `feature`.
- `B` is the merge base in this simple example.

Running `git log main` traverses commits reachable from `main`. Running `git log feature` traverses commits reachable from `feature`. Revision ranges construct sets from those two reachable regions by including or excluding one side.

## 2. Range A..B: Commits in B That A Does Not Have

Syntax:

```bash
git log A..B
```

In `git log`, `A..B` means:

> Include commits reachable from B, then exclude all commits reachable from A.

It can be written equivalently using exclusion syntax:

```bash
git log B ^A
```

Therefore, `A..B` is a directional range. Swapping A and B changes the result set.

Using the diagram above:

```bash
git log --oneline main..feature
```

The output contains `C1` and `C2`: commits present in `feature` that are not yet reachable from `main`. Commits `A` and `B` are excluded because they are also reachable from `main`.

Reversing the direction:

```bash
git log --oneline feature..main
```

The output contains `M1` and `M2`: commits present on `main` that `feature` does not have.

### When to Use A..B?

- Inspecting commits to bring from a feature branch into main.
- Checking which commits a local branch is missing compared to its upstream.
- Checking new commits on a remote-tracking branch not yet integrated locally.
- Reviewing the scope of changes before opening a pull request or merging.

Example checking unpushed local commits:

```bash
git log --oneline origin/main..main
```

This lists commits reachable from `main` that are not yet reachable from `origin/main`, based on the remote-tracking ref currently stored in the clone. To ensure results reflect the latest remote state, fetch first:

```bash
git fetch origin
git log --oneline origin/main..main
```

Remote-tracking refs are only updated on fetch; `git log` does not query the server on its own.

## 3. Range A...B: Divergent Commits on Both Sides

In `git log`, the three-dot syntax:

```bash
git log A...B
```

computes the **symmetric difference**: commits reachable from A or B, but not reachable from both. In other words, Git excludes shared history and keeps commits unique to each side.

Using the diverging diagram:

```text
             C1---C2  feature
            /
A---B---M1---M2      main
```

The command:

```bash
git log --oneline main...feature
```

displays `M1`, `M2`, `C1`, and `C2`. Commits `A` and `B` do not appear because they are reachable from both branches.

Unlike `A..B`, the three-dot range is symmetric with respect to the commit set:

```bash
git log A...B
git log B...A
```

Both commands select the same set of commits, though display order may vary. `A...B` is useful when you want to see everything both branches have developed independently since their shared history.

### Using --left-right to See Which Side Owns Each Commit

Symmetric difference output can interleave commits from both sides. Add `--left-right` to mark the origin:

```bash
git log --left-right --oneline main...feature
```

- `<` marks commits belonging only to the left side (`main`).
- `>` marks commits belonging only to the right side (`feature`).

Example:

```text
< 91ab230 Update deployment settings
< 3c4d510 Fix checkout timeout
> 7ef812a Add payment retry
> 5ab901c Add gateway metrics
```

The output shows that `main` has two unique commits and `feature` has two unique commits. If there are no `>` markers, `feature` has no unique commits relative to `main`; if there are no `<` markers, `main` has no unique commits relative to `feature`.

You can combine this with a graph:

```bash
git log --graph --left-right --oneline --decorate main...feature
```

This command is often most useful when checking branch divergence before deciding whether to merge or rebase.

## 4. Comparison Table of A..B and A...B

| Syntax in `git log` | Selected Commit Set | Question Answered |
|---|---|---|
| `A..B` | Reachable from B but not reachable from A | Which commits does B have that A lacks? |
| `B..A` | Reachable from A but not reachable from B | Which commits does A have that B lacks? |
| `A...B` | Reachable from A or B, excluding commits reachable from both | Which unique commits exist on each side? |

Set-theory illustration:

```text
Reachable(A) = {common, a1, a2}
Reachable(B) = {common, b1, b2}

A..B   = {b1, b2}
B..A   = {a1, a2}
A...B  = {a1, a2, b1, b2}
```

`A..B` is a directional difference. `A...B` is a symmetric difference, capturing unique commits from both sides. The intersection (`common`) is excluded in both ranges.

## 5. Exclusion Syntax with ^ and --not

The two-dot range is shorthand for combining positive revisions and excluded revisions.

Example:

```bash
git log B ^A
```

`B` is a positive revision: traverse commits reachable from B. `^A` is a negative revision: exclude commits reachable from A.

You can use `--not` to negate revisions based on their position in the argument list:

```bash
git log B --not A
```

With multiple revisions, explicit notation can be clearer:

```bash
git log main feature ^release/1.x
```

This selects commits reachable from `main` or `feature`, then excludes commits reachable from `release/1.x`. Multiple negative revisions can be combined:

```bash
git log main feature ^release/1.x ^archive/legacy
```

Remember that `^A` as a prefix before a revision is exclusion syntax in traversal; it differs from `A^` as a suffix after a revision, which refers to the first parent commit of A.

## 6. Distinguishing A^, A~, and ^A

These notations look similar but mean different things:

| Syntax | Meaning |
|---|---|
| `A^` | First parent of commit A |
| `A^2` | Second parent of A; commonly used with merge commits |
| `A~1` | First parent of A, equivalent to `A^` |
| `A~3` | Step backward three times along the first-parent chain |
| `^A` | Exclude all commits reachable from A from the traversal result |

Example with a merge commit M having two parents:

```text
      F1---F2---+
     /          \
A---B---M--------
        ^1       ^2
```

`M^1` is the first parent, usually the branch checked out when creating the merge; `M^2` is the second parent, usually the branch merged in. Parent order depends on how the merge was created and should not be guessed without checking.

Inspect the parents of a commit:

```bash
git show -s --format="%H%n%P" M
```

Or read the raw commit object:

```bash
git cat-file -p M
```

Do not confuse `git log A^..B` with `git log ^A B`. The first uses A's first parent as the exclusion baseline; the second excludes all history reachable from A.

## 7. Determining the Merge Base Before Comparing

The merge base is the best common ancestor of two commits, typically used as the baseline for a three-way merge. Find the merge base:

```bash
git merge-base main feature
```

In simple histories, the merge base is the last common commit before the two branches diverged. You can inspect shared and unique commits using:

```bash
git log --oneline main
git log --oneline feature
git log --oneline main..feature
git log --oneline feature..main
git log --oneline --left-right main...feature
```

Some complex graphs can have multiple best merge bases. To view all of them:

```bash
git merge-base --all main feature
```

When multiple merge bases exist, do not assume there is only a single common commit. Git may construct a virtual merge base during complex merges. Inspect the full graph and understand the merge history if ranges or integration results differ from linear examples.

Check direct ancestry directly:

```bash
git merge-base --is-ancestor main feature
```

Exit code `0` means `main` is an ancestor of `feature`; a non-zero exit code means that ancestry relationship does not hold. If A is an ancestor of B, `A..B` lists commits developed after A on B, while `B..A` is empty.

## 8. Ranges in Pull Request Review Workflows

Suppose you are reviewing branch `feature/search` before merging it into `main`.

**View commits only on feature:**

```bash
git log --oneline main..feature/search
```

This is normally the list of commits that feature introduces into main.

**View commits only on main:**

```bash
git log --oneline feature/search..main
```

If this returns output, main has advanced since feature branched off or since feature was last synchronized.

**View both sides together:**

```bash
git log --graph --left-right --oneline main...feature/search
```

This shows which branch has unique commits, helping determine how far they have diverged.

**View patches for feature commits not yet in main:**

```bash
git log -p main..feature/search
```

**Count unique commits:**

```bash
git rev-list --count main..feature/search
git rev-list --count feature/search..main
```

These two numbers indicate how many uniquely reachable commits exist on each side. This is a commit count, not a file count or line change count.

Before drawing conclusions, fetch from the remote to ensure `main` and `feature/search` are the refs you intend to compare. If a branch exists only on the remote, use its remote-tracking ref such as `origin/main` or `origin/feature/search`.

## 9. Ranges When Checking Local Branches vs. Upstream

Git typically configures an upstream for local branches. For example, local branch `feature/search` tracks `origin/feature/search`.

Inspect upstream configuration:

```bash
git branch -vv
```

Local commits not yet on upstream:

```bash
git log --oneline "@{upstream}"..HEAD
```

Upstream commits not yet in the local branch:

```bash
git log --oneline HEAD.."@{upstream}"
```

The `@{upstream}` and `@{u}` expressions resolve to the current branch's upstream if configured. Quoting them prevents the shell from interpreting special characters, which is especially helpful in PowerShell. If the branch has no upstream set, Git reports that it cannot resolve the revision. You can substitute explicit refs:

```bash
git log --oneline origin/feature/search..feature/search
```

Before comparing, update remote-tracking refs:

```bash
git fetch origin
```

Ranges only compare objects and refs present in the local clone. They do not automatically inspect branches on the server unless you fetch or retrieve those refs first.

## 10. Combining Ranges with git log Filters

Revision ranges select the commit set first; other options further filter or format that set.

View only merge commits on feature not yet in main:

```bash
git log --merges --oneline main..feature
```

View only commits by a specific author:

```bash
git log --author="An Nguyen" --oneline main..feature
```

Search commits whose message mentions cache:

```bash
git log --grep="cache" --oneline main..feature
```

View file change statistics:

```bash
git log --stat --oneline main..feature
```

View graph with both sides marked:

```bash
git log --graph --left-right --decorate --oneline main...feature
```

Path filters can also be used after `--`:

```bash
git log --oneline main..feature -- src/search/
```

This displays only commits within the range affecting path `src/search/`. When using path limitations, Git may simplify history differently from the full graph; if analyzing branch relationships, also run the command without path restrictions.

## 11. --cherry-pick and Patch-Equivalent Commits

Two branches can contain commits with different OIDs that carry equivalent changes, for example when a commit is cherry-picked to another branch or recreated after a rebase.

When using:

```bash
git log --left-right --cherry-pick --oneline A...B
```

Git omits commits that have a patch-equivalent commit on the opposite side, helping focus on changes without an equivalent on the other branch. This is patch comparison, not OID comparison or ancestry checking.

To mark patch-equivalent commits instead of omitting them:

```bash
git log --left-right --cherry-mark --oneline A...B
```

Patch-equivalent commits are marked with `=`; commits unique to one side are marked `<` or `>`. This option is useful when verifying whether a branch already received a change via cherry-pick despite differing commit hashes.

Patch equivalence has limits: a change that was further edited, split across multiple commits, or squashed from multiple commits may not be recognized as equivalent. Inspect actual patches before concluding a change has been integrated.

## 12. --boundary and Range Boundary Commits

By default, `git log A..B` does not display commits reachable from A because they were excluded from the result set. If you want to see the boundary commits connecting to the excluded history, use `--boundary`:

```bash
git log --boundary --oneline A..B
```

Boundary commits are usually marked with `-` at the start of the line. They help show the history immediately preceding the range, though they do not belong to the positive commit set requested by the range.

Combine with a graph:

```bash
git log --graph --boundary --oneline A..B
```

This is a helpful way to see feature commits alongside the baseline commit they branched from.

## 13. Crucial Distinction: git diff A..B vs. git diff A...B

Do not mechanically apply `git log` revision range semantics to `git diff`. `git diff` compares **tree snapshots**, rather than listing commit sets.

### Two Dots in git diff

```bash
git diff A..B
```

In `git diff`, this syntax is equivalent to:

```bash
git diff A B
```

It directly compares the tree of A with the tree of B. It does not mean "commits on B that A lacks" as in `git log A..B`.

### Three Dots in git diff

```bash
git diff A...B
```

In `git diff`, three dots compare the tree of the merge base between A and B against the tree of B. It typically answers: "What has B changed since its common point with A?"

To view changes on side A since the merge base, swap the order:

```bash
git diff B...A
```

### Comparison Table

| Command | Meaning |
|---|---|
| `git log A..B` | Commits reachable from B but not reachable from A |
| `git log A...B` | Unique commits on both A and B, excluding shared history |
| `git diff A..B` | Compare tree A with tree B |
| `git diff A...B` | Compare merge base(A, B) with tree B |

Example when reviewing a feature:

```bash
# List of feature commits not yet on main
git log --oneline main..feature

# Content differences between main and feature snapshots
git diff main..feature

# Changes introduced by feature since its common point with main
git diff main...feature
```

These three commands answer different questions. If `main` received new commits after `feature` branched off, `git diff main...feature` isolates what `feature` changed since the merge base, whereas `git diff main..feature` compares the two current tip snapshots.

## 14. Edge Cases and Limitations

### A Is an Ancestor of B

If A is an ancestor of B, `A..B` contains commits following A on B. `B..A` is empty. `A...B` also contains only the unique commits on B, since A has no unique commits.

### Both Branches Point to the Same Commit

If A and B point to the same commit, `A..B`, `B..A`, and `A...B` are all empty.

### Two Branches Have No Common Ancestor

If two histories share no merge base, `A...B` can still select all commits uniquely reachable from both sides. However, `git diff A...B` cannot use a standard merge base if none exists; Git reports an error or cannot perform that comparison form.

### Multiple Merge Bases

In criss-cross merge histories, multiple best merge bases can exist. The three-dot revision range in `git log` excludes shared history according to the applicable merge bases; results may not match a simple diagram with a single branch point. Use `git merge-base --all A B` and the full graph to inspect.

### Shallow Clones or Unfetched Refs

If a clone has truncated history, Git may lack enough parents to determine ancestry accurately. Similarly, if a remote branch has not been fetched, your range may compare against a stale ref or fail to find the ref. Check:

```bash
git rev-parse --is-shallow-repository
git branch -a
git fetch --all --prune
```

### Patch-Equivalent Commits with Different OIDs

Cherry-picking and rebasing create new commits with different parents or metadata. `A..B` and `A...B` are based on reachability, so they may still show both commits even when patches are equivalent. Use `--cherry-pick` or `--cherry-mark` to help detect this case.

## 15. Range Selection Workflow When Investigating a Branch

When assigned to review `feature/reporting` before integrating into `main`, follow these steps:

**Step 1: Update refs and confirm branches**

```bash
git fetch --all --prune
git branch -vv
```

**Step 2: View commits only on feature**

```bash
git log --oneline main..feature/reporting
```

**Step 3: Check whether main has moved ahead**

```bash
git log --oneline feature/reporting..main
```

**Step 4: View both sides on the same graph**

```bash
git log --graph --left-right --decorate --oneline main...feature/reporting
```

**Step 5: Find the merge base and inspect the patch**

```bash
git merge-base main feature/reporting
git diff main...feature/reporting
```

The last command compares feature's changes since the merge base against feature's current snapshot. If you want the direct difference between the two tip snapshots, use `git diff main..feature/reporting`.

**Step 6: Check for cherry-pick equivalents if the branch was synced manually**

```bash
git log --left-right --cherry-mark --oneline main...feature/reporting
```

Note each side's unique commits, the merge base, patch changes, and equivalent commits. From there, decide whether feature needs to be updated via merge/rebase or is ready to integrate.

## 16. Hands-On Exercise

In a test repository, create branch `main` and `feature/demo` from the same baseline commit. Create two unique commits on `main` and three unique commits on `feature/demo`, leaving the two branches unmerged.

1. Run `git log --oneline main..feature/demo` and record the commits present only on feature.
2. Run `git log --oneline feature/demo..main` and record the commits present only on main.
3. Run `git log --left-right --graph --oneline main...feature/demo` to identify which side each commit belongs to.
4. Use `git rev-list --count` in both directions to count unique commits.
5. Use `git merge-base main feature/demo` to find the common ancestor.
6. Create a commit on feature and cherry-pick an equivalent change onto main; run `--cherry-mark` and `--cherry-pick` to observe how patch equivalence is detected.
7. Compare `git diff main..feature/demo` with `git diff main...feature/demo`; explain why the two commands produce different output.
8. Try `git log --boundary --oneline main..feature/demo` to observe boundary commits.
9. After merging feature into main, re-run the ranges and explain why the unique commit sets changed.

You have completed the exercise when you can accurately explain which commits are selected by `A..B` and `A...B` in `git log`, identify commit ownership with `--left-right`, and avoid confusing three-dot syntax between `git log` and `git diff`.
