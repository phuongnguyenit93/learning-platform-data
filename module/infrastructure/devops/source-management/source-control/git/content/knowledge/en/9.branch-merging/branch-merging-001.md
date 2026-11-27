# Common Ancestor and Three-Way Merge Principles

When two branches develop in parallel, Git needs to identify their shared history before combining their changes. That best common commit is called the **merge base** (common ancestor). In a three-way merge, Git examines three versions: the snapshot at the merge base, the snapshot of the current branch, and the snapshot of the branch being merged in. From the two sets of changes since the base, Git produces a combined result; if both sides modify the same region in ways that cannot be reconciled automatically, Git marks a conflict for the user to resolve.

Understanding the role of the merge base helps you predict merge outcomes, analyze why a conflict occurred, and correctly interpret the relationship between `ours`, `theirs`, and `base`. This is also the foundation for understanding why fast-forward does not need a three-way merge, why a merge commit has two parents, and why certain complex histories can have multiple merge bases.

## 1. Branches Developing in Parallel from a Common Commit

Suppose the `main` and `feature/payment` branches both start from commit `B`. Afterward, each branch creates its own commits:

```text
          C1---C2  feature/payment
         /
A---B---M1---M2  main
```

`B` is the nearest common commit in this simple graph. `main` has advanced with `M1` and `M2`; `feature/payment` has advanced with `C1` and `C2`.

When you want to merge the feature into main, Git needs to combine two lines of changes:

- What `main` has changed since `B`.
- What `feature/payment` has changed since `B`.

Git does not simply take the entire file from the newer branch and overwrite the other branch. That approach would lose changes from one side. Instead, Git uses the common snapshot as a starting point to compare both sides and produce a combined result.

## 2. What Is a Merge Base?

A **merge base** is a best common ancestor of two commits. A commit is a common ancestor if it can be reached from both commits by following parent links. Among all common ancestors, a merge base is a common ancestor that has no other common ancestor sitting between it and the two branch tips.

In a typical branching linear history, the merge base is simply the commit where the two branches diverged. However, in histories with multiple cross-merges, there can be multiple best merge bases; therefore, a merge base should not be defined simply as "the most recent common commit by date."

Find a merge base:

```bash
git merge-base main feature/payment
```

Git prints the OID of a suitable merge base. Use `--all` to view all best merge bases if more than one exists:

```bash
git merge-base --all main feature/payment
```

Check whether one commit is an ancestor of another commit:

```bash
git merge-base --is-ancestor <older-commit> <newer-commit>
```

Exit code `0` means the first commit is an ancestor of the second commit. A non-zero exit code means that ancestry relationship does not hold (or an error needs investigation).

### A Merge Base Is Not a Branch and Does Not Move HEAD

A merge base is simply a commit identified from the history graph. The `git merge-base` command does not create a commit, move any branch, or modify the working tree. It is a lookup operation for you or merge commands to use as a comparison baseline.

You can inspect the snapshot at the merge base:

```bash
git show --stat <BASE>
git show <BASE>:src/payment.js
```

The second command reads the file contents at the base snapshot. Replace `<BASE>` with the OID or revision returned by `git merge-base`.

## 3. The Three Versions in a Three-Way Merge

A three-way merge uses three logical inputs:

| Version | Meaning | In merging `main` with `feature/payment` |
|---|---|---|
| Base | Snapshot at the merge base | The shared content before the two branches diverged |
| Ours | Snapshot of the current branch | `main` if you are on `main` and run merge on feature |
| Theirs | Snapshot of the branch being merged in | `feature/payment` in this example |

Git computes the changes from base to ours and from base to theirs, then combines the compatible changes.

```text
                 Merge base (B)
                   /       \
                  /         \
       changes from ours    changes from theirs
                /             \
             main           feature/payment
                \             /
                 \           /
                  Merge result
```

The names `ours` and `theirs` depend on the direction of the operation. If you check out `feature/payment` and merge `main`, `ours` is feature and `theirs` is main. When resolving conflicts, rely on the current branch and the branch being merged—never hardcode `ours = main` or `theirs = feature` in your mind.

In a standard two-parent merge commit, the first parent is the commit you were on when starting the merge (ours); the second parent is the tip of the branch being merged in (theirs).

## 4. How Does Git Combine Two Sets of Changes?

Imagine the file `src/payment.js` at the merge base has the following content:

```javascript
function calculateTotal(order) {
  const subtotal = order.subtotal;
  return subtotal;
}
```

On `main`, the team adds input validation:

```javascript
function calculateTotal(order) {
  if (!order) throw new Error("Order is required");
  const subtotal = order.subtotal;
  return subtotal;
}
```

On `feature/payment`, the team adds a transaction fee:

```javascript
function calculateTotal(order) {
  const subtotal = order.subtotal;
  const fee = order.fee ?? 0;
  return subtotal + fee;
}
```

The two sides modify different regions: main adds a check at the top of the function, while feature adds the fee calculation at the end. Git can usually combine them into:

```javascript
function calculateTotal(order) {
  if (!order) throw new Error("Order is required");
  const subtotal = order.subtotal;
  const fee = order.fee ?? 0;
  return subtotal + fee;
}
```

The user does not need to pick an entire file from one side because the changes do not conflict. Git uses context lines and its content-merging algorithm to produce the result.

## 5. Cases Where Merge Succeeds Automatically

When comparing both sides against the base, several situations are usually resolved automatically:

| Change from base to ours | Change from base to theirs | Typical result |
|---|---|---|
| Line unchanged | Line modified | Takes the change from theirs |
| Line modified | Line unchanged | Keeps the change from ours |
| Modified top region of file | Independently modified bottom region of file | Combines both changes |
| Both modified to produce identical content | Both modified identically | Keeps one shared result, no content conflict |
| Added two files at different paths | Added two files at different paths | Usually keeps both files |

"Succeeds automatically" only means Git can produce a result according to merge rules. It does not guarantee that the application logic is correct. Two changes in separate regions can still cause a logic bug when combined—for example, one branch changes the currency unit while the other adds a fee calculation without updating the conversion.

After a conflict-free merge, you still need to review the diff and run appropriate tests.

## 6. When Do Conflicts Occur?

A conflict occurs when Git cannot safely decide the merge result on its own. A common case is when both sides modify the same line region relative to the same base content but produce different results.

For example, the base has:

```javascript
return subtotal;
```

Ours changes it to:

```javascript
return subtotal - discount;
```

Theirs changes it to:

```javascript
return subtotal + fee;
```

Git cannot know whether the correct business rule is to subtract the discount, add the fee, or combine both in a specific order. It marks a conflict for the developer to decide.

Other cases that can cause conflicts:

- One side modifies a file while the other deletes it (modify/delete).
- Both sides rename the same file to two different paths (rename/rename).
- One side renames a file while the other modifies the old file's contents (rename/modify).
- Both sides add a file with the same path but different contents (add/add).
- Directory structure changes leading to file/directory conflicts.
- A binary file is modified on both sides; Git generally cannot reconcile binary content line by line.

A conflict does not necessarily mean one branch is wrong. It simply indicates that a decision is needed on how to combine two intended changes.

## 7. Understanding Ours, Theirs, and Base in the Index During a Conflict

When a conflict occurs at a path, the index can store multiple temporary versions (unmerged stages):

| Stage | Common name | Content |
|---:|---|---|
| 1 | Base | Version at the merge base |
| 2 | Ours | Version from the current branch |
| 3 | Theirs | Version from the branch being merged in |

Inspect unmerged entries:

```bash
git ls-files -u
```

Read each version of a conflicted file:

```bash
git show :1:src/payment.js
git show :2:src/payment.js
git show :3:src/payment.js
```

A stage may be absent in special add/delete scenarios. For instance, a file added on only one side will not have a base version. These stages are temporary data in the index; after resolving and running `git add <path>`, Git replaces them with a single stage 0 entry for the resolved result.

## 8. Performing a Merge to Observe Three-Way Behavior

Suppose `main` and `feature/payment` have diverged. Switch to the target branch and merge:

```bash
git switch main
git merge feature/payment
```

Git finds the merge base between `main` and `feature/payment`, compares both branch tips against the base, and produces the result. If a fast-forward is possible, Git may simply move the `main` ref; if the two branches have diverged, Git typically creates a merge commit after a successful combination.

To explicitly request a merge commit even when fast-forward is possible:

```bash
git merge --no-ff feature/payment
```

`--no-ff` controls how history is recorded (creating a merge commit instead of only fast-forwarding). It is not an option to toggle the three-way algorithm on or off. If the two branches have diverged, Git still needs to combine changes based on the merge base.

### Fast-Forward vs. Three-Way Merge

If the tip of the current branch is an ancestor of the branch being merged, Git can fast-forward:

```text
A---B---C  feature
     ^
    main
```

`main` only needs to move from B to C. Two branches did not independently make separate changes since the base, so there is no need to combine two sets of changes and no merge commit is created by default.

When the two branches have diverged:

```text
      C1---C2  feature
     /
A---B---M1---M2  main
```

Git must combine changes from both sides based on base B. If successful, a merge commit can be created with two parents.

## 9. How Does a Merge Commit Record the Result?

A two-parent merge commit stores the tree of the merged result and two parent commits. For example:

```text
      C1---C2------+
     /             \
A---B---M1---M2-----M  main
```

Merge commit `M` has:

- Tree: the post-merge snapshot.
- First parent: `M2`, the tip of the current branch before the merge.
- Second parent: `C2`, the tip of the branch being merged in.
- Author/committer and commit message.

Inspect parent information:

```bash
git show -s --format="%H%n%P%n%s" HEAD
```

If the current commit is a merge commit, the `%P` line contains two parent OIDs (or more in a multi-head merge). You can inspect the merge contents:

```bash
git show --cc HEAD
git log --graph --oneline --decorate -10
```

A merge commit preserves the record that two histories were combined. This differs from a squash merge, which may create a single commit containing the resulting changes without recording the feature commits as parents.

## 10. Viewing Each Side's Changes Separately Against the Merge Base

When you need to understand why a conflict happened, inspect each side against the base.

First, find the base:

```bash
BASE=$(git merge-base main feature/payment)
```

Then compare base with main:

```bash
git diff "$BASE" main -- src/payment.js
```

And compare base with feature:

```bash
git diff "$BASE" feature/payment -- src/payment.js
```

These two diffs show what each side did since the common point. In PowerShell, you can assign the variable with:

```powershell
$base = git merge-base main feature/payment
git diff $base main -- src/payment.js
git diff $base feature/payment -- src/payment.js
```

You can also read the snapshot of each side:

```bash
git show "$BASE:src/payment.js"
git show "main:src/payment.js"
git show "feature/payment:src/payment.js"
```

If branch names or paths contain special characters, quote the revisions appropriately for your shell. These commands only read data and do not modify branches or the index.

## 11. Resolving Conflicts Using the Three Versions

When a merge stops due to a conflict, inspect:

```bash
git status
git diff --cc
git ls-files -u
```

For text content conflicts, the working tree typically contains conflict markers:

```text
<<<<<<< HEAD
return subtotal - discount;
=======
return subtotal + fee;
>>>>>>> feature/payment
```

The section above `=======` is ours; the section below is theirs in the ongoing merge. Read both changes alongside the business requirements, then edit the file to produce the correct result. Do not simply delete the markers and arbitrarily keep one side.

When you need to inspect all three full versions, use stages 1/2/3 as shown earlier. During a merge conflict, you can also use:

```bash
git checkout --ours -- src/payment.js
git checkout --theirs -- src/payment.js
```

These two commands select one side's entire version for the file; they are generally unsuitable if logic from both sides needs to be combined. After editing:

```bash
git add src/payment.js
git status
```

Staging the resolved file marks that conflict as complete. Once all conflicts are resolved, check the diff and tests, then complete the merge with `git commit` if Git has not automatically created the commit.

If you decide to cancel the ongoing merge:

```bash
git merge --abort
```

This command attempts to restore the working tree and index to the state before the merge. For reliable recovery, always start a merge from a clean state; prior uncommitted changes can make it difficult for abort to restore cleanly.

## 12. Merge Base in Complex Histories

In a typical graph, two branches have only one merge base. However, with a **criss-cross merge** history, two branches may merge into each other in different directions without producing a single unique best merge base.

Illustrative example:

```text
       A1------M2  branch-A
      /  \    /
O----+    M1-+
      \  /    \
       B1------M3  branch-B
```

This diagram merely illustrates that both sides have cross-merged multiple times; real graphs can have multiple best merge bases. Check with:

```bash
git merge-base --all branch-A branch-B
```

When there are multiple merge bases, Git cannot always pick one simple commit as the base like in linear examples. Modern merge strategies can construct a **virtual merge base** by merging the best merge bases together, then using that result as the starting point for the main merge.

This avoids arbitrarily picking one base and missing changes already combined in cross-merge history. However, it also makes reading conflicts more complex: the base version used by the algorithm may be a synthesized result that does not match any single commit you see in `git log`.

## 13. Merge Strategies and the Role of the Algorithm

Git supports multiple merge strategies. For standard two-branch merges, the modern default strategy is `ort` (used as the default since Git 2.34). Older versions commonly used the `recursive` strategy. The strategy is responsible for handling directory tree relationships, renames, and content merging based on appropriate bases.

You can view the help documentation:

```bash
git merge -h
git help merge
```

Other strategies serve specific purposes:

- `ort`: the default strategy for two-head merges in modern Git.
- `recursive`: the older two-head strategy, still specifiable on supported versions.
- `octopus`: used for multi-head merges; suitable when merging multiple branches without requiring complex conflict handling. If difficult conflicts arise, octopus typically refuses.
- `ours`: picks the current branch's tree as the result, ignoring the changed contents of the other heads; do not confuse with the `-X ours` option.

The strategy option `-X ours` means that when a content conflict occurs, favor the ours version for the conflicted hunks; non-conflicting changes from the other side are still combined. It is completely different from the `-s ours` strategy, which produces a tree identical to ours and ignores all content changes from the merged branches.

Do not pick a strategy or option that favors one side just to make the merge conflict-free. Understand the business changes and verify the post-merge result.

## 14. Key Points When Interpreting Merge Results

- **A clean merge does not mean correct logic.** Git only knows how to combine content, not business rules.
- **Ours/theirs flips with merge direction.** Always identify the current branch and the branch being merged.
- **Fast-forward does not create a merge commit by default.** Git only moves the ref when one branch tip is an ancestor of the other.
- **`--no-ff` controls history shape.** It does not replace the merge base or alter three-way merge rules.
- **Rename detection is heuristic.** Git uses content similarity to detect renames; results can vary depending on thresholds and situations.
- **Binary files usually require manual decisions.** Git cannot merge binary bytes according to application semantics.
- **Multiple merge bases make the base more complex.** Use `git merge-base --all` if the history contains cross-merges.
- **Merge conflicts store data in the index.** `git ls-files -u` shows unmerged stages; `git add` records the resolved result.
- **Verify before committing.** Use `git diff`, `git diff --check`, run tests, and review the merged files.

## 15. Practical Workflow for Analyzing Merge Base and Three-Way Merge

In a test repository, create `main` and `feature/payment` from a common commit and modify different regions in the same file.

**Step 1: Verify the two branches and history**

```bash
git branch -vv
git log --graph --oneline --decorate --all
```

**Step 2: Find the merge base**

```bash
git merge-base main feature/payment
git merge-base --all main feature/payment
```

**Step 3: Inspect what each side changed relative to the base**

```bash
git diff <BASE> main
git diff <BASE> feature/payment
```

**Step 4: Perform the merge**

```bash
git switch main
git merge --no-ff feature/payment
```

**Step 5: Inspect the result**

```bash
git status
git log --graph --oneline --decorate -10
git show -s --format="%H%n%P%n%s" HEAD
```

If there is a conflict, read all three versions, edit the result, stage the resolved files, and run tests before completing the merge.

## 16. Practice Exercise

Create a test repository with a base commit `B`, then create two branches `main` and `feature/demo`.

1. On `main`, modify the validation check at the top of a function in `src/order.js`; on `feature/demo`, add an independent calculation at the end of the function.
2. Run `git merge-base main feature/demo` and identify the base commit.
3. Use `git diff <BASE> main` and `git diff <BASE> feature/demo` to inspect each side's changes separately.
4. Merge `feature/demo` into `main`; verify that Git can automatically combine non-conflicting changes.
5. Recreate another test repository or branch where both sides modify the same line in two different ways and observe the conflict.
6. Use `git ls-files -u` and `git show :1:<path>`, `:2:<path>`, `:3:<path>` to read base, ours, and theirs.
7. Resolve the conflict by combining the logic from both sides, run tests, `git add` the file, and complete the merge.
8. Compare a regular merge with fast-forward; use `--no-ff` to observe a merge commit being created even when fast-forward is possible.
9. If possible, create a cross-merge history and run `git merge-base --all` to observe a case with multiple merge bases.

You have completed the exercise when you can explain what a merge base is, how Git uses the three snapshots, why independent changes can combine automatically, when conflicts occur, and how to correctly identify base/ours/theirs in the index.
