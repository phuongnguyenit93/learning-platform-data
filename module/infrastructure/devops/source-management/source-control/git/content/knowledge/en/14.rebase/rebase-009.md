# Comparing commit chains before and after with git range-diff

Rebase can change commit identifiers, commit order, or patch contents when you edit history. After rebasing, looking at the new commit list only shows the current history; it does not answer whether the original changes are still intact, which commits were modified, which were dropped, or whether any new changes were added.

Git provides **git range-diff** to compare two versions of a commit chain. This command pairs corresponding commits between two ranges based on patch content and displays what is identical, changed, removed, or added. It is a useful self-review tool after rebasing, especially when using interactive rebase, squashing, splitting commits, or moving a branch onto a new base.

## 1. Why compare commit chains after rebasing?

Rebase takes a branch's commits and replays them onto a different base commit. Because each new commit has a new parent commit, commit identifiers usually change even when the change content remains equivalent.

For example, before rebasing, the branch has the chain:

~~~text
A---B---C---D  main
         \
          E---F---G  feature/search
~~~

After main receives commit H and you rebase feature/search onto H:

~~~text
A---B---C---D---H  main
                 \
                  E'---F'---G'  feature/search
~~~

Commits E', F', and G' are newly created commits. They do not share the same identifiers as E, F, and G. If the rebase only changed parent commits without altering patches, the change content can remain equivalent. However, during interactive rebase, you might have:

- Edited a commit's contents with reword or edit.
- Combined multiple commits with squash or fixup.
- Split one large commit into several smaller commits.
- Reordered commits.
- Dropped a commit that is no longer needed.
- Resolved a conflict and accidentally altered logic.
- Added a new commit while making edits.

Therefore, after rebasing, you should review both history and content. **git range-diff** helps inspect the patch series before and after, catching differences that merely glancing at commit titles or running git log can miss.

## 2. What does git range-diff compare?

git range-diff takes two commit ranges and compares the commits within those two ranges. Typically, each range represents the working branch's commits since a base commit:

~~~text
base..tip
~~~

Where:

- **base** is the base commit of the change series.
- **tip** is the final commit of the branch at the point of comparison.
- Commits included in the range are those reachable from tip but not in the history of base.

If both chains share an unchanged base and you saved the old tip using a ref:

~~~
git range-diff origin/main..backup/search-before-rebase origin/main..feature/search
~~~

The command above compares the old commit chain and the new commit chain if both share the same base. When rebasing onto a new base, use the corresponding base for each version:

~~~
git range-diff old-base..old-tip new-base..new-tip
~~~

This is an important point: if the branch's base changed after rebasing, do not default to using a single base for both chains. Taking a range that is too wide can pull commits already belonging to the base branch into the comparison and make the output hard to read.

git range-diff focuses on a commit patch series. It is not a full comparison of two working trees, nor does it replace git diff when you need to know how final file states differ.

## 3. Preparing before rebasing

To compare accurately, save the branch's anchor points before rewriting history. A reliable approach is creating a backup branch pointing to the old tip and another backup branch pointing to the old base.

Suppose:

- The base branch is origin/main.
- The working branch is feature/search.
- You want to rebase feature/search onto the latest origin/main.

### 3.1. Check status and update remote information

~~~
git switch feature/search
git status -sb
git fetch origin
git log --oneline --graph --decorate --all
~~~

Before rebasing, the working tree should be clean. If uncommitted changes remain, finish committing them or stash them after inspecting their contents. Do not start a rebase without knowing clearly where local changes reside.

### 3.2. Save the old tip and old base

Create a backup branch for the current tip:

~~~
git branch backup/search-before-rebase feature/search
~~~

Create a backup branch for the common base commit between the working branch and the base branch:

~~~
git branch backup/search-base-before "$(git merge-base origin/main feature/search)"
~~~

These two backup branches preserve anchor points for post-rebase comparison. Backup names should be unique in the repository; if a name already exists, choose another name so you do not accidentally move an anchor you need to keep.

You can double-check them:

~~~
git show -s --oneline backup/search-before-rebase
git show -s --oneline backup/search-base-before
~~~

Keep these anchors until your review is complete. Do not rely solely on ORIG_HEAD or HEAD@{1} as your only record: reflog and ORIG_HEAD can change after subsequent Git operations, whereas backup branches have clear names and are easy to reference.

## 4. Performing the rebase

After saving the anchors:

~~~
git rebase origin/main
~~~

If you want to edit the commit chain, you can use interactive rebase:

~~~
git rebase -i origin/main
~~~

In the editor, you can choose actions such as:

| Action | Effect |
|---|---|
| pick | Keep commit |
| reword | Keep patch, edit commit message |
| edit | Pause at commit to modify |
| squash | Fold commit into previous commit and edit message |
| fixup | Fold commit into previous commit, discard folded commit's message |
| drop | Remove commit from chain |

Once the rebase completes, check the current branch and save the new base:

~~~
git status -sb
git log --oneline --graph --decorate -10
git branch backup/search-base-after "$(git merge-base origin/main feature/search)"
~~~

The backup/search-base-after branch points to the new base commit of the post-rebase chain. If the rebase pauses due to a conflict, resolve each file, stage the result, and run git rebase --continue. If you need to cancel the entire in-progress rebase, use git rebase --abort while the rebase session is still active.

Do not delete the old backup branches right after rebasing just because the new branch runs. Use them for comparison and keep them until you are certain you no longer need recovery or further inspection.

## 5. Running git range-diff after rebasing

Once all four anchors are in place, run:

~~~
git range-diff backup/search-base-before..backup/search-before-rebase backup/search-base-after..feature/search
~~~

This command compares:

- First range: commits on feature/search before rebasing, from old base to old tip.
- Second range: commits on feature/search after rebasing, from new base to new tip.

If the base did not change, you can use the same base for both ranges. However, keeping old base and new base separate makes the workflow clear when rebasing onto a base branch that has moved forward.

### Example output

Suppose before rebasing there were three commits:

~~~text
1:  a1b2c3d Add search endpoint
2:  b2c3d4e Handle empty query
3:  c3d4e5f Add search tests
~~~

After rebasing, the range-diff output might look like this:

~~~text
1:  a1b2c3d = 1:  d4e5f6a Add search endpoint
2:  b2c3d4e ! 2:  e5f6a7b Handle empty query
3:  c3d4e5f < -:  ------- Add search tests
-:  ------- > 3:  f6a7b8c Add search and pagination tests
~~~

Meaning:

- The first commit has equivalent patches before and after rebasing.
- The second commit still has a matching pair, but its patch changed.
- The third commit from the old chain no longer has a matching commit in the new chain.
- The new chain has an added commit not present in the old chain.

This output does not automatically conclude whether a change is right or wrong. It simply highlights items for you to inspect. For instance, a dropped old commit may have been squashed into a new commit; a new commit may be an intentional split. Cross-check against your original intent and patch contents.

## 6. Reading symbols in the output

git range-diff uses symbols to describe relationships between commits:

| Symbol | Meaning | What to do |
|---|---|---|
| = | Commits are paired and patches are equivalent | Quickly verify title and context |
| ! | Corresponding commit exists, but patch or commit content changed | Open the diff to understand the change |
| < | Commit appears only in the first range | Determine whether the commit was dropped or squashed/split |
| > | Commit appears only in the second range | Determine whether the new commit matches intent |

Each line typically shows the position and commit ID on both sides. For example:

~~~text
2: b2c3d4e ! 2: e5f6a7b Handle empty query
~~~

The first number is the commit's position in the old chain; the second is its position in the new chain. The two commit IDs can differ because rebase creates new commits. The ! symbol indicates you should inspect the detailed comparison displayed underneath that line.

### 6.1. An equals sign does not mean the entire branch is identical

The = symbol means paired commits have equivalent patches according to range-diff's comparison. The bases of the two branches may differ, and the overall history can certainly differ due to rebasing.

Therefore, = does not prove that:

- Both branches share the same commit IDs.
- Every file in the working tree is identical.
- Changes on the new base branch do not affect application behavior.
- Tests or business requirements are satisfied.

Even when range-diff shows the expected patch series, still run tests and review the final state.

### 6.2. Exclamation marks must be read carefully

The ! symbol is usually the most important part when auditing a rebase. It can appear when:

- You edited logic while resolving a conflict.
- You modified a commit with rebase -i.
- A change was rewritten to match a new API on the base branch.
- The commit message changed alongside the patch.
- Commits were split or squashed, altering how commits pair up.

Read the diff presented by range-diff, then inspect the new commit:

~~~
git show --stat e5f6a7b
git show e5f6a7b
~~~

If the change was intentional, note the reason or update the PR so reviewers understand. If the change was unintended, fix it on the new branch and run tests.

### 6.3. Commits present on only one side

< indicates a commit only in the old chain; > indicates a commit only in the new chain. When you squash two commits into one, range-diff may display an unpaired old commit and a new commit representing the combined changes.

Do not automatically assume every < is data loss or every > is an extraneous change. Verify whether the old commit's patch was folded into a new commit. Start by listing both commit chains:

~~~
git log --oneline --reverse backup/search-base-before..backup/search-before-rebase
git log --oneline --reverse backup/search-base-after..feature/search
~~~

Then use git show with specific commit IDs to read the old patch and the paired new patch. These commands help determine which commit absorbed the old change or whether it was genuinely omitted.

## 7. Inspecting detected changes in detail

### 7.1. Comparing a specific commit

When range-diff flags a commit with !, open the two corresponding commits using the SHA IDs shown on the result line:

~~~
git show <old-commit-sha>
git show <new-commit-sha>
~~~

Replace placeholders with actual commit IDs. Read additions, deletions, and surrounding context to verify the change does not deviate from requirements.

### 7.2. Comparing final file states

range-diff compares individual patches across two chains. To view the full change content of the branch before and after rebasing, diff against the respective bases:

~~~
git diff backup/search-base-before backup/search-before-rebase
git diff backup/search-base-after feature/search
~~~

These two commands help inspect the overall outcome of each chain. If you need to compare the two content trees at the tips directly:

~~~
git diff backup/search-before-rebase feature/search
~~~

Note that directly diffing the two tips also reflects changes from the new base branch. It may include many changes outside your patch series. Therefore, use range-diff to review the commit chain and diff against each respective base to inspect the scope of changes for each version.

### 7.3. Checking history order and structure

Read the commit list in order:

~~~
git log --oneline --reverse backup/search-base-before..backup/search-before-rebase
git log --oneline --reverse backup/search-base-after..feature/search
~~~

If you reordered commits via interactive rebase, confirm the new order accurately reflects dependencies between changes. For example, a commit adding a function must appear before a commit calling that function if the team expects every commit to be independently testable.

## 8. When range-diff reveals unexpected differences

Do not push immediately after seeing output with many !, <, or > markers. Categorize the causes and inspect systematically.

### 8.1. Missing commit

If an old commit only shows <:

1. View the old commit's contents with git show.
2. Check whether the change was folded into a new commit.
3. Inspect the overall diff of the new chain.
4. If the change was genuinely lost, restore the patch or create a new commit containing the missing part.

You can reapply an old commit with cherry-pick if appropriate, while checking dependencies and avoiding duplicating a patch that was already folded:

~~~
git cherry-pick <old-commit>
~~~

In this documentation example, <old-commit> is a placeholder; replace it with the actual commit ID from the backup branch. After cherry-picking, check for conflicts, inspect the diff, and run tests.

### 8.2. Unintended new commit

If a commit appears only in the new chain:

1. Identify which operation created it.
2. Check whether the patch belongs to the requirements or is an out-of-scope change.
3. If it is a necessary change for compatibility with the new base, document the reason.
4. If it is an accidental change, fix the branch with an intentional commit or perform an interactive rebase after saving anchors.

Do not delete a commit just because it lacks a counterpart. It may be a split commit or a necessary new fix.

### 8.3. Unintentionally altered patch

When ! appears, inspect the detailed diff and check:

- Were any lines of logic dropped?
- Did any conditions or error cases change?
- Were names or structures changed while preserving behavior?
- Did conflict resolution mistakenly pick the wrong side?
- Did the commit message change in a way that misleads reviewers about the goal?

If the difference is intentional, add context to the PR description. If the difference is unintended, fix it, run tests, and run range-diff again.

## 9. Useful options

### 9.1. Tuning the pairing threshold

git range-diff uses a pairing algorithm to match commits between two chains. When commits are split, squashed, or heavily modified, the algorithm may not pair them as expected. The --creation-factor option adjusts pairing flexibility:

~~~
git range-diff --creation-factor=80 old-base..old-tip new-base..new-tip
~~~

A higher value helps pair commits that changed more substantially, though it can also produce less intuitive pairings. Use it as an investigation aid, not to force outputs to look similar.

### 9.2. Viewing commits on one side only

When you want to focus on commits appearing only in the old or new range, you can use:

~~~
git range-diff --left-only old-base..old-tip new-base..new-tip
git range-diff --right-only old-base..old-tip new-base..new-tip
~~~

--left-only restricts output to the first range's side; --right-only restricts it to the second range's side. They are useful for finding vanished or added commits.

### 9.3. Viewing help and Git version

git range-diff has been available since Git 2.19. If the command does not exist on your machine, check the version:

~~~
git --version
git range-diff -h
~~~

Use a Git version recent enough to meet your project's tooling requirements. If your environment does not support it yet, you can compare manually using git log, git show, and git diff, though that approach lacks automatic patch pairing like range-diff.

## 10. Limitations to understand

git range-diff is a review aid, not a verifier of program correctness.

**It compares patches, not business semantics.** Two seemingly similar patches can behave differently when combined with a new base branch. Conversely, a heavily altered patch may still be right because an API or design changed.

**Pairing results rely on heuristics.** When commits are split, squashed, or heavily rewritten, the algorithm may pair them differently than a human expects. Read both ranges and tune the creation factor when needed.

**It does not replace tests.** = does not prove the application runs correctly; ! does not automatically mean a bug. Run unit tests, integration tests, static analysis, and checks appropriate to the changes.

**It does not replace a full-tree diff.** If you need to know how the final state of all files differs, use git diff with the appropriate anchors.

**It works best on linear commit chains.** When history contains many merge commits or complex topology, range-diff may not fully capture the merge structure. Combine git log --graph and git diff to inspect history and contents.

**It requires two reachable commit chains.** If the old tip was not saved and old objects have been pruned from the repository, comparison may be difficult or impossible. Create backup branches before rebasing.

## 11. Recommended post-rebase verification workflow

A concise workflow you can apply for every important rebase:

1. Fetch latest updates from remote and confirm a clean working tree.
2. Create backup branches for the old tip and old base.
3. Rebase the branch onto the new base or perform interactive rebase.
4. Create an anchor for the new base once rebase finishes.
5. Run git range-diff with the two corresponding base-tip pairs.
6. Investigate every !, <, and >; confirm squashed, split, added, or dropped changes are intentional.
7. Use git log to verify commit order and git diff to inspect file states.
8. Run tests and necessary quality checks.
9. Update the PR/MR description so reviewers know history was rewritten and understand notable differences.
10. Only push once you understand the impact. If the branch is shared and rebasing changed commits, coordinate with collaborators; use --force-with-lease when policy permits and make sure you understand how the remote will be updated.

If you need to update a remote branch after rebasing, a force push may be required because commit SHAs changed. Prefer --force-with-lease over --force so Git verifies the remote is still at the point local expects. This is still a history-rewriting operation and requires coordination if others use the branch.

## 12. Complete example

Suppose you have a feature/search branch with three commits already pushed to the remote. The team asks you to rebase onto the latest origin/main and review again to ensure no changes were lost.

**Before rebase:**

~~~
git switch feature/search
git fetch origin
git status -sb
git branch backup/search-before-rebase feature/search
git branch backup/search-base-before "$(git merge-base origin/main feature/search)"
~~~

**Rebase:**

~~~
git rebase origin/main
~~~

If conflicts occur, resolve each file, stage the result, and continue:

~~~
git add src/search/search-service.ts
git rebase --continue
~~~

**After rebase:**

~~~
git status -sb
git branch backup/search-base-after "$(git merge-base origin/main feature/search)"
git range-diff backup/search-base-before..backup/search-before-rebase backup/search-base-after..feature/search
~~~

Suppose the output shows two commits with =, one commit with !, and one old commit with <. Read the patch of the commit marked !, then check which new commit absorbed the old commit marked < or whether it was genuinely lost. Once verified, inspect:

~~~
git log --oneline --reverse origin/main..feature/search
git diff origin/main..feature/search
~~~

Run search-related tests, check the PR, and update reviewers on changes made during the rebase. If the branch was pushed earlier, only update the remote after agreeing on safe force-push procedures with the team.

## 13. Commit chain comparison checklist

**Before rebase**

- [ ] Working tree is clean and current branch is right.
- [ ] Latest base branch has been fetched.
- [ ] Old tip saved with a backup branch.
- [ ] Old base saved to bound the patch series accurately.

**After rebase**

- [ ] Rebase is complete and working tree is in the expected state.
- [ ] New base corresponding to the post-rebase chain has been saved.
- [ ] range-diff run between the two base-tip pairs.
- [ ] Every commit marked !, <, and > inspected.
- [ ] Confirmed that squashed, split, added, or dropped commits are intentional.
- [ ] Commit order and final-state diff verified.
- [ ] Required tests and checks executed.
- [ ] Reviewers and collaborators notified if branch history changed.

## 14. Conclusion

git range-diff helps verify how a commit chain changed after rebasing by pairing old and new patches. = indicates equivalent patches, ! flags modified patches, and < and > help locate commits present on only one side. For meaningful results, save the tip and base before rebasing, then compare the two corresponding range pairs.

Use range-diff alongside git log, git diff, and tests. The tool helps you spot differences in history; confirming that changes meet requirements still requires content review and verifying program behavior.
