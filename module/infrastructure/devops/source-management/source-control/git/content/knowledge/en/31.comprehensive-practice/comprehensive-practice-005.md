# Comparing Commit Graphs After Fast-Forward, Merge Commit, Squash, and Rebase

When integrating a feature branch into a main branch, Git offers several ways to shape history. Fast-forward simply moves a branch pointer when history is already linear; a merge commit creates a commit with multiple parents to record the integration point; squash combines changes into a single new commit; rebase replays commits onto a new base and produces new commit IDs. These approaches can yield identical file contents, yet the commit graph, traceability, and behavior of future merges will differ.

To choose the right strategy, look at both file content and ancestry relationships. `git log --graph`, `git show`, `git merge-base`, and `git rev-list` help you read the graph rather than only scanning a chronological commit list. This lab uses one shared scenario to compare all four outcomes and clarify when each approach fits.

## 1. Common Scenario and Graph Notation

Suppose a repository starts at commit `A`, followed by a shared commit `B`. From `B`, the team diverges onto two branches:

- `main` receives two new commits, `M1` and `M2`.
- `feature/payment` has two commits, `F1` and `F2`.

Pre-integration graph:

```text
             M1---M2  (main)
            /
A---B------+
     \
      F1---F2  (feature/payment)
```

In practice, branches may have more commits and touch many files. The key point is that `main` and `feature/payment` diverged after `B`: `M2` is not an ancestor of `F2`, and `F2` is not an ancestor of `M2`.

Key terms to keep in mind:

- **Parent:** the predecessor commit(s) recorded inside a commit object.
- **Ancestor:** any commit reachable by following parent links backward from another commit.
- **Merge base:** the best common ancestor Git uses as the baseline when merging two histories.
- **Ref:** a name such as `main` or `feature/payment` pointing to a commit.
- **Reachability:** the ability to reach a commit by traversing parents from a chosen ref or root commit.

The methods below may produce the exact same final file contents on `main`, while creating different parents and different histories.

## 2. Fast-Forward: Moving a Ref Without Creating a Merge Commit

A fast-forward is only possible when the tip of the current branch is an ancestor of the branch being integrated. In that case, Git simply advances the current branch ref to the newer commit; no new commit is created.

### When Fast-Forward Is Possible

Suppose `feature/payment` branched from `main` at `B`, and no new commits were added to `main` during development:

```text
A---B  (main)
     \
      F1---F2  (feature/payment)
```

Because `B` is an ancestor of `F2`, `main` can advance straight to `F2`:

```text
A---B---F1---F2  (main, feature/payment)
```

There is no new merge commit. Commits `F1` and `F2` retain their original OIDs, parents, and contents.

### Performing a Fast-Forward

Check out `main` and run:

```bash
git switch main
git merge --ff-only feature/payment
```

`--ff-only` instructs Git to integrate only if a fast-forward is possible. If history has diverged, the command aborts instead of creating a merge commit. This option is useful when a team wants a linear history and wants early notice that a branch is behind `main`.

### Verification

```bash
git log --oneline --graph --decorate --all
git show -s --format="%H%n%P%n%s" main
```

The tip commit after a fast-forward is still `F2`, and its parent list is unchanged. A fast-forward leaves no dedicated merge commit marking when the integration occurred.

### When Is It Appropriate?

- The target branch has no new commits since the feature branch was created.
- The team wants a linear history with minimal merge commits.
- Changes were reviewed elsewhere and no merge commit is needed to mark the integration point.

If `main` already has `M1` and `M2` as in our original graph, a direct fast-forward from `main` to `F2` is impossible because `M2` is not an ancestor of `F2`.

## 3. Merge Commit: Recording the Integration Point With Two Parents

When two branches have diverged, a standard merge creates a merge commit. This commit has two parents: the first parent is the tip of the current branch, and the second parent is the tip of the branch being merged in.

From the original graph:

```text
A---B---M1---M2---X  (main)
     \          /
      F1---F2---/    (feature/payment)
```

`X` is the new merge commit. It joins the two lines of history, preserves commits `M1`, `M2`, `F1`, and `F2`, and explicitly records that the two branches were merged.

### Creating a Merge Commit

```bash
git switch main
git merge --no-ff feature/payment
```

`--no-ff` forces Git to create a merge commit even when a fast-forward would be possible. When two branches have already diverged, a normal merge requires a merge commit anyway; `--no-ff` makes the intent to record an integration point explicit even in cases where fast-forward could apply.

If a conflict occurs, Git pauses so you can resolve it. After fixing the files and staging the results:

```bash
git status
git add <resolved-paths>
git merge --continue
```

Or abort the in-progress merge if you do not want to continue:

```bash
git merge --abort
```

Only use `--abort` while the merge is still incomplete. Once the merge commit is created, `--abort` is no longer a way to undo it.

### Verifying Parents

```bash
git show -s --format="commit: %H%nparents: %P%nsubject: %s" HEAD
```

For a standard merge commit, the `parents` field contains two OIDs. Inspect the graph:

```bash
git log --oneline --graph --decorate --all
```

### When Is It Appropriate?

- You need to preserve branch history and original commits intact.
- You want to know the exact point when a branch was integrated.
- The team uses merge commits as checkpoints for review, auditing, or releases.
- Keeping branching structure helps visualize parallel development streams.

In exchange, history includes extra merge commits and a non-linear graph. Merging many short-lived branches frequently can make the graph dense.

## 4. Squash: Combining Changes Into One New Commit

A squash merge takes the net changes of the feature branch relative to the merge base, applies them to the target branch, and prepares a single new commit. The new commit normally has one parent: the current tip of the target branch. Individual commits from the feature branch do not become ancestors of the squash commit.

The post-squash graph looks like:

```text
             M1---M2---S  (main)
            /
A---B------+
     \
      F1---F2  (feature/payment)
```

`S` is the squash commit. The file contents of `S` may match combining `F1` and `F2`, yet `S` is a brand-new object with a new OID and only `M2` as its parent. The `feature/payment` branch still points to `F2` unless deleted or moved.

### Performing a Squash Merge

```bash
git switch main
git merge --squash feature/payment
git status
git diff --cached
git commit -m "feat: add payment workflow"
```

`git merge --squash` stages the merged changes in the index and working tree, but does not create a merge commit and does not move `HEAD`. You must run `git commit` separately.

If conflicts occur during squash, resolve the contents and stage the fixed files. Then review the staged diff and commit. Because no merge state is recorded for a merge commit, `git merge --continue` is not the finishing step as in a normal merge; run `git commit` once the result is ready.

### Verifying Parents and Contents

```bash
git show -s --format="commit: %H%nparents: %P%nsubject: %s" HEAD
git show --stat --oneline HEAD
```

Commit `S` normally has only one parent, `M2`. To inspect the changes the feature contributed relative to the base, compare the common base with the feature tip before integration:

```bash
git diff B feature/payment
```

In real usage, replace `B` with the OID or ref pointing to the recorded base commit. The content diff shows what the feature changed, while `S`'s parent shows how ancestry was recorded.

### Consequences for Future Merges

Because `F2` does not become an ancestor of `S`, Git does not record in ancestry that the feature branch was merged. If development continues on `feature/payment` and you merge it again later, Git still treats `F1` and `F2` as outside `main`'s history and computes changes against the old merge base. Previously squashed changes can reappear in diffs or trigger conflicts depending on subsequent edits.

With a squash workflow, teams normally delete the feature branch after integration or cut a fresh branch from `main` for follow-up work. Avoid reusing the old branch without understanding these ancestry implications.

### When Is It Appropriate?

- The feature branch has many experimental commits, minor fixes, or intermediate WIP commits.
- The team wants one purpose-focused commit on the main branch.
- The hosting platform's pull request / merge request already preserves review history and discussion.
- Project policy prioritizes a concise, readable `main` history.

Squash discards the ancestry of individual feature commits on the target branch. If per-commit auditing or preserving branch relationships is required, a merge commit is better suited.

## 5. Rebase: Replaying Commits Onto a New Base

Rebase takes the commits on the feature branch that are not yet in the new base and replays them on top of that base's tip. Each recreated commit gets a new OID because its parent changes; metadata such as committer and timestamps may also differ.

From the original graph, rebase `feature/payment` onto `main`:

```bash
git switch feature/payment
git rebase main
```

Post-rebase graph:

```text
A---B---M1---M2---F1'---F2'  (feature/payment)
            (main)
```

`F1'` and `F2'` are new commits recreated on top of `M2`. The original `F1` and `F2` commits are no longer on the feature branch after rebasing, though they may remain accessible via the reflog for a while. The diff contents may be equivalent, while the OIDs and parent links differ.

### Integrating After Rebase

After a successful rebase, `main` is an ancestor of `F2'`, so a fast-forward is possible:

```bash
git switch main
git merge --ff-only feature/payment
```

The result on `main` is a linear history:

```text
A---B---M1---M2---F1'---F2'  (main, feature/payment)
```

Rebase does not automatically integrate a branch into `main`; it moves the feature branch's history. The subsequent fast-forward merge is what advances `main` to the new tip.

### Handling Conflicts During Rebase

If a replayed commit hits a conflict, Git pauses:

```bash
git status
```

Fix the conflicted files, stage the results, and continue:

```bash
git add <resolved-paths>
git rebase --continue
```

To cancel the entire in-progress rebase and return to the pre-rebase state:

```bash
git rebase --abort
```

Do not use `--abort` after the rebase has already finished. If you need to return to a pre-rebase commit after completion, consult the reflog and create a rescue branch before moving refs.

### When Is It Appropriate?

- You want to bring a feature branch up to date with a new base before integrating.
- You want a linear, easy-to-read history.
- The feature branch has not been widely shared, or the team explicitly permits history rewriting.
- You prefer resolving conflicts commit by commit rather than in one large merge.

Never casually rebase a branch that others have already based work on. Because OIDs change, pushing again requires a controlled force update and can disrupt collaborators' clones.

## 6. Comparing the Four Graphs on the Same Scenario

For two branches that diverged at `B`, the outcomes can be summarized as follows:

| Method | Effect on target branch | Parents of new integration commit | Keeps feature commit OIDs? | Records feature ancestry? |
|---|---|---|---|---|
| Fast-forward | Moves ref to feature tip when current tip is an ancestor | No new commit created | Yes | Yes, feature commits sit directly in target history |
| Merge commit | Creates a merge commit joining both histories | Two parents | Yes | Yes, feature branch becomes an ancestor via the merge commit |
| Squash | Creates one new commit holding the combined changes | Usually one parent | Does not include feature commits in target history | No, does not record ancestry of feature commits |
| Rebase then fast-forward | Recreates feature commits on the new base, then moves target ref | Replayed commits normally have one parent; no merge commit needed | No, replayed commit OIDs change | Yes, new commits sit in target history after fast-forward |

Key distinction: **fast-forward is a way of updating a ref**, whereas **merge commit and squash are ways of creating an integration result**. Rebase is an operation that rewrites commits on the source branch, typically followed by a fast-forward to update the target branch.

## 7. Checking Ancestry With merge-base and rev-list

To determine whether two branches have diverged, check their merge base:

```bash
git merge-base main feature/payment
```

This returns the OID of the best common ancestor. If `main`'s tip itself is the merge base, `main` is an ancestor of the feature branch and can fast-forward to it (barring other blockers).

Check direct ancestry directly:

```bash
git merge-base --is-ancestor main feature/payment
```

Exit code `0` means `main` is an ancestor of `feature/payment`; a non-zero exit code means that ancestry relationship does not hold in that direction (or an error occurred). You can swap the arguments to test the reverse direction.

Count commits unique to each side:

```bash
git rev-list --left-right --count main...feature/payment
```

The output shows two numbers: commits reachable only from `main` and commits reachable only from `feature/payment` relative to their merge base. In our original graph, both sides have their own commits.

See which commits belong to which side:

```bash
git log --left-right --oneline main...feature/payment
```

Commits marked with `<` exist only on `main`; commits marked with `>` exist only on `feature/payment`. This is a helpful inventory before choosing merge, squash, or rebase.

## 8. Verifying Parent Counts and the Commit Graph

A normal commit has one parent; a root commit has zero parents; a standard merge commit has two or more parents. Use:

```bash
git show -s --format="%H%n%P%n%s" <commit>
```

Here `%H` is the commit's full OID, `%P` is the space-separated list of parent OIDs, and `%s` is the subject line.

To inspect the full branch/tag graph:

```bash
git log --oneline --graph --decorate --all
```

To compare two commit ranges before and after rebasing:

```bash
git range-diff <old-base>..<old-tip> <new-base>..feature/payment
```

`git range-diff` matches corresponding commits and highlights which commits stayed equivalent, changed, or were dropped after rebasing. Record the old OID/base before rebasing so the comparison is meaningful.

To compare final file contents between two branches:

```bash
git diff main feature/payment
```

A content diff does not reveal ancestry structure. Two branches can share an identical tree while having completely different commit graphs. Always pair `git diff` with `git log --graph`, `git show`, and `git merge-base`.

## 9. Practicing in a Sandbox Repository

To observe all four outcomes without altering a real project repository, create an isolated practice repository. The example below uses Bash-style shell syntax:

```bash
mkdir git-merge-strategies
cd git-merge-strategies
git init -b main
git config user.name "Git Practice"
git config user.email "git-practice@example.com"

echo "base" > README.md
git add README.md
git commit -m "chore: create base"
```

To create a clean diverged graph, branch the feature right at the base commit before adding `main`-specific commits:

```bash
git switch -c feature/payment
echo "payment module" > payment.txt
git add payment.txt
git commit -m "feat: add payment module"

echo "retry handling" >> payment.txt
git add payment.txt
git commit -m "feat: add payment retry"

git switch main
echo "operations notes" > operations.txt
git add operations.txt
git commit -m "docs: add operations notes"

echo "deployment notes" >> operations.txt
git add operations.txt
git commit -m "docs: add deployment notes"
```

The graph now has two unique commits on each branch. Because the branches touch different files, you can focus on observing merge structures without intentionally triggering content conflicts. Starting from the same base, you can clone or copy separate lab directories for each strategy to compare results side-by-side without resetting history between runs.

In each lab, inspect:

```bash
git log --oneline --graph --decorate --all
git show -s --format="%H %P %s" HEAD
git rev-list --left-right --count main...feature/payment
```

Never use a real repository to test `reset --hard`, force-pushing, or history rewriting. A sandbox repository lets you inspect graphs and parents without risking active work.

## 10. Choosing a Strategy Based on Team Requirements

| Criterion | Fast-forward | Merge commit | Squash | Rebase then FF |
|---|---|---|---|---|
| Linear history | Yes | No | Yes on target branch | Yes |
| Preserves original feature commits | Yes | Yes | Not in target ancestry | No, creates new commits |
| Dedicated merge point | No | Yes | No | No |
| Shows diverged branches | No, only used when not diverged | Yes | No | Target graph is linearized |
| Safe for shared branches | Yes | Yes | Possible, though branch reuse needs care | Requires caution because commits are rewritten |
| Per-feature-commit traceability | Yes | Yes | Lower on target branch | Yes via new commits; needs range-diff against old history |

Selection guidelines:

- Choose **fast-forward** when the target branch has not advanced and the team prefers simply moving the ref.
- Choose **merge commit** when you want to record integration points and preserve both branch histories.
- Choose **squash** when you want one consolidated commit on the main branch and do not need individual feature-commit ancestry on the target branch.
- Choose **rebase** when you want to replay feature commits onto a fresh base, the branch is not widely shared, or the team has clear conventions around rewriting history.

No single strategy fits every project. Choose based on audit requirements, review style, integration frequency, team size, and branch policies.

## 11. Common Reasoning Errors

| Misconception | What to check |
|---|---|
| Fast-forward always creates a merge commit | Fast-forward only moves the ref; it creates no new commit |
| A merge commit changes branch commit OIDs | A merge commit keeps existing commits intact and adds a commit with multiple parents |
| Squash is equivalent to a merge commit because final file contents match | Squash creates a single-parent commit and does not record feature-commit ancestry |
| Rebase only moves a branch pointer | Rebase replays commits and generates new OIDs because parents and metadata change |
| Rebase automatically puts changes into `main` | Rebase updates the branch being rebased; a separate merge/fast-forward moves the target branch |
| Two branches with identical trees have identical history | Snapshot contents may match while parents and ancestry differ |
| `git log --oneline` alone distinguishes all strategies | Use `--graph`, `%P`, `merge-base`, or `rev-list` to inspect structure |
| It is always safe to rebase a branch others depend on | Rebase changes OIDs and can force collaborators to resync history |

## 12. Key Takeaways

Fast-forward only updates a ref when the current tip is an ancestor of the incoming tip. Merge commits preserve both histories and add a two-parent commit. Squash creates one new commit containing the net changes without recording feature-commit ancestry. Rebase replays commits onto a new base, generating new OIDs, usually followed by a fast-forward to update the target branch.

To verify outcomes, use `git log --graph --decorate --all`, `git show -s --format="%H %P %s"`, `git merge-base`, `git merge-base --is-ancestor`, `git rev-list --left-right --count`, and `git range-diff`. Always separate final file contents from historical structure: identical trees do not imply identical commit graphs. Pick an integration strategy aligned with your team's collaboration and traceability needs.
