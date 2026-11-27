# Squash Merge and Its Impact on History Relationships

Squash merge collapses the changes from a branch into a single commit on the target branch. This approach keeps the main branch history cleaner, but has an important consequence: the squash commit does not record the source branch commits as its ancestors. Git stores the content result in a new commit, while the ancestry relationship between the two branches remains separate.

Therefore, after squashing, Git may still treat the source branch as unmerged even though its content already appears in the target branch. This affects checking merged branches, deleting branches, continuing work on the old branch, and performing subsequent merges.

This lesson belongs to the **Branch Merging** chapter of the `SOURCE_CONTROL_GIT` module. The module covers working tree, staging area, commits, history, branches, merging, rebasing, remotes, and tags; understanding both content results and history relationships helps you choose the right integration approach for your collaboration workflow.

## 1. What Is a Squash Merge?

A squash merge takes the combined changes of the source branch relative to the common ancestor, applies them to the target branch, and prepares a snapshot for you to create a new commit. The individual commits on the source branch do not become parents of the new commit.

Suppose the initial history is:

~~~text
A---B---C  feature
 \
  (main)
~~~

Where:

- `A` is the initial common commit.
- `B` and `C` are two commits on the `feature` branch.
- The `main` branch is still at `A`.

After squashing the changes of `feature` into `main` and creating commit `S`, the history looks like:

~~~text
A---B---C  feature
 \
  S        main
~~~

Commit `S` has `A` as its parent. It contains the resulting snapshot after integrating the changes, but does not have `C` as a parent. Therefore, `B` and `C` are not on the ancestry path of `main`.

This is the key distinction between "having brought the content in" and "having recorded the source branch history as an ancestor."

## 2. Creating a Squash Merge with Git

Before integrating, switch to the target branch and check the working tree:

~~~bash
git status
git switch main
git fetch origin
~~~

If the target branch needs updates from the remote, integrate those changes per team policy before squashing. Next, inspect the history and change scope of the source branch:

~~~bash
git log --oneline --graph --decorate --all
git diff --stat main...feature
git diff main...feature
~~~

`git diff main...feature` compares the source branch against the common merge base, showing the changes that feature brings since the branch point.

Perform the squash:

~~~bash
git merge --squash feature
~~~

Git applies the merge result into the working tree and index. This command does not automatically create a commit, does not move `HEAD`, and does not write `MERGE_HEAD` like a regular merge.

Inspect the staged content:

~~~bash
git status
git diff --cached --stat
git diff --cached
~~~

If the result is correct, create the commit:

~~~bash
git commit -m "Add payment workflow"
~~~

The new commit is a regular commit on `main`, with a single parent being the previous commit on `main`. It stores the entire post-squash snapshot.

### Running git merge --squash Does Not Automatically Create a Commit

The `git merge --squash` command only prepares the index and working tree. You still need to inspect the content and then run `git commit`. If not yet committed, the changes remain local staged/working-tree changes with no new history milestone.

## 3. Comparing Squash Merge with Merge Commit and Rebase

All three approaches can bring changes to the same content result, but they produce different history relationships.

| Integration method | Result on target branch | Parents of new commit | Do source commits become ancestors? |
| --- | --- | --- | --- |
| Squash merge | One commit containing combined changes | One parent: previous commit of target branch | No |
| Merge commit | One merge commit recording the integration | Usually two parents: target and source | Yes |
| Rebase then fast-forward | Source commits replayed onto new base, then target advances to new tip | Each replayed commit has one parent | Yes, as rewritten commits residing on target branch |

Merge commit example:

~~~text
A---M  main
 \ /
  B---C  feature
~~~

`M` has two parents: the pre-merge commit on `main` and the `feature` tip. Git can walk ancestry backward from `M` to `C`, so it recognizes that the feature commits have been integrated by history relationship.

Squash example:

~~~text
A---B---C  feature
 \
  S        main
~~~

`S` only has parent `A`. Git cannot infer from ancestry alone that `B` and `C` were integrated.

Rebase then fast-forward example:

~~~text
A---B'---C'  main, feature (after rebase)
~~~

`B'` and `C'` are new commits recreated onto `A` or a newer base. The content can be equivalent to the old commits, but the hashes change because parents and commit metadata change.

### Squash Merge Differs from Interactive Rebase Squash

- `git merge --squash feature` applies changes from the source branch onto the target branch and creates a single new commit afterward.
- In interactive rebase, the `squash` or `fixup` commands combine commits within the sequence of commits being rewritten. Rebase recreates the commit history of that branch.

Both can reduce commit count, but their scope of operation and history relationships differ.

## 4. What Does a Squash Commit Record?

A squash commit is a normal commit. It has:

- Its own commit ID.
- Author and committer metadata.
- A commit message.
- One parent commit on the target branch.
- A tree snapshot containing the merged changes.

It does not automatically store the list of source commits as parents. Individual commit messages, authors, and commit boundaries on the source branch are also not automatically merged into the squash commit's metadata.

If you need to credit contributions or link reviews, you can include the pull request ID, issue number, feature name, or a trailer like `Co-authored-by` in the commit message according to project conventions.

Example:

~~~text
Add payment workflow

Combines validation, payment form and invoice updates.
Reviewed in PR #248.

Co-authored-by: Tran Binh <binh@example.com>
~~~

Trailers are merely text inside the commit message; they do not create ancestry relationships to the source commits.

## 5. Verifying the Squash Commit and Parents

After creating the commit, inspect the content:

~~~bash
git show --stat --oneline HEAD
git show --format=fuller HEAD
~~~

Inspect the commit object and parents:

~~~bash
git cat-file -p HEAD
~~~

Or view only parent hashes:

~~~bash
git rev-list --parents -n 1 HEAD
~~~

For a normal squash commit, the first line has the new commit ID and only one parent. A merge commit usually displays two or more parents.

View the graph of all refs:

~~~bash
git log --oneline --graph --decorate --all
~~~

Check whether the feature tip commit is an ancestor of main:

~~~bash
git merge-base --is-ancestor feature main
~~~

After a squash merge, this command typically returns a non-zero exit code because the `feature` tip is not an ancestor of `main`. That alone does not prove feature content was not brought into main; it only says the ancestry relationship was not recorded.

## 6. Why Is the Branch Still Considered Unmerged?

Git determines whether a branch is merged by commit ancestry, not simply by comparing file contents.

After squashing:

~~~bash
git branch --merged main
~~~

The `feature` branch typically does not appear in the list because its tip is not an ancestor of `main`.

The safe branch deletion command:

~~~bash
git branch -d feature
~~~

may refuse to delete with a message that the branch is not fully merged. This is intentional behavior: Git does not know that the source commits were combined into another commit via squash.

Do not immediately run `git branch -D feature` just to bypass the warning. First verify that the squash commit contains the intended content, check the pull request or review record, and confirm your source history retention policy.

Once confirmed that the local branch can be deleted:

~~~bash
git branch -D feature
~~~

This command deletes the local branch ref. It does not delete the squash commit on `main`. However, if no other ref holds the source commits, they can become unreachable and be reclaimed by Git during garbage collection cycles.

To delete the source branch on the remote after team confirmation:

~~~bash
git push origin --delete feature
~~~

Deleting remote branches must also follow the team's review and retention policies.

## 7. Same Content, Yet Different History

A common point of confusion: after a squash merge, the file trees of `main` and `feature` can be identical, yet Git still does not consider the feature tip an ancestor of main.

For example, if commit `S` on main contains the exact same snapshot as commit `C` on feature:

~~~bash
git diff main feature
~~~

may show no content differences. However:

~~~bash
git merge-base --is-ancestor feature main
~~~

will still return false.

The two commands answer two different questions:

- `git diff` compares tree contents.
- `git merge-base --is-ancestor` checks ancestry relationships between commits.

Similarly, view commits unique to each side:

~~~bash
git log --oneline --left-right main...feature
~~~

You will still see `S` on the main side and `B`, `C` on the feature side. These commits differ in ID and ancestry even though the final snapshots may match.

This is why you cannot look solely at file state to conclude Git considers the source branch merged.

## 8. What Happens If You Continue Using the Source Branch After Squashing?

Suppose you squash `feature` into `main` with commit `S` while keeping the `feature` branch at `C`.

Then you create an additional commit `D` on feature:

~~~text
A---B---C---D  feature
 \
  S            main
~~~

When merging feature into main again, Git still uses `A` as the merge base because `B` and `C` are not in `main`'s ancestry. Git will compare changes from A to D on the feature side against changes from A to S on the main side.

If snapshot S already contains the exact changes of B and C, the merge may recognize some content is already present, but there is no guarantee that subsequent integrations will be automatically clean. Different edits in the same regions, prior conflict resolutions, or new changes can cause conflicts or unexpected results.

Therefore, after squashing a pull request, the common workflow is:

1. Verify the squash commit has been landed on the target branch.
2. Close the pull request and delete the source branch per policy.
3. Create the next feature branch from the latest target branch.

Example:

~~~bash
git switch main
git pull --ff-only
git switch -c feature/payment-receipts
~~~

The new branch starts from history that already includes the squash commit, so subsequent development has an appropriate merge base with main.

If you must continue the old branch for work reasons, agree on how to re-sync with the target branch and carefully inspect patches/ancestry before the next integration. Do not assume squashing caused Git to mark every source commit as merged.

## 9. Preserving Source Branch History When Auditing Is Needed

Squashing keeps the target branch history cleaner, but can lose the direct path from the target branch to individual source commits. If the team needs detailed traceability, decide how to retain history before deleting the branch.

Some options:

- Keep the source branch on the remote for a defined retention period.
- Create an archive tag at the source tip per team naming conventions.
- Retain pull requests, review records, and commit links on the code hosting platform.
- Save a bundle or repository snapshot if long-term archival is required.

Example of creating a tag to preserve the branch milestone before deleting:

~~~bash
git tag archive/feature-payment feature
git push origin refs/tags/archive/feature-payment
~~~

This tag holds a ref to the feature tip. It does not make the source commits ancestors of main, but it keeps that commit chain reachable via the tag.

Tags are not technically immutable by themselves: authorized users can delete or move tags. If strict auditing is required, use tag protection policies and backups with appropriate retention.

## 10. Reverting a Squash Commit vs. Reverting a Merge Commit

Because a squash commit is a normal commit with one parent, it can be undone with:

~~~bash
git revert <squash-commit>
~~~

Git creates a new commit reversing the changes of the squash commit. No mainline parent needs to be specified.

For a merge commit with multiple parents, reverting requires picking the main parent, typically `-m 1` if you want to keep the target branch as the mainline:

~~~bash
git revert -m 1 <merge-commit>
~~~

Do not use the merge-commit revert syntax for a squash commit. Check the parent count first:

~~~bash
git rev-list --parents -n 1 <commit>
~~~

Reverting does not delete the old commit; it adds a new commit to invert the content. If the squash commit has already been shared, this is generally safer than rewriting shared branch history.

## 11. Handling Conflicts During a Squash

Squash merge uses a content-merging mechanism similar to regular merge. If the same region was edited on both sides, Git can stop with conflicts.

Execute:

~~~bash
git merge --squash feature
git status
~~~

List unmerged files:

~~~bash
git diff --name-only --diff-filter=U
~~~

Open each file, resolve conflict markers, then stage the result:

~~~bash
git add path/to/resolved-file
git diff --cached
~~~

Once all paths are resolved and the staged content is correct, create a normal commit:

~~~bash
git commit -m "Integrate feature with squash"
~~~

Because `git merge --squash` does not write `MERGE_HEAD`, it does not establish a normal merge state to continue with `git merge --continue`. Check the actual state and finish with commit after staging the resolved files.

If you want to discard an incomplete squash result, first preserve any local changes that existed prior to the merge. Squash does not store merge metadata like a standard merge, so do not assume `git merge --abort` can restore the exact initial state. Only use index/working tree restoration commands after checking and backing up content you need to keep.

## 12. When Should You Choose Squash Merge?

Squash is suitable when the team wants the main branch to have one commit representing one unit of change, such as a pull request or a small feature.

| Situation | Typically suitable option | Reason |
| --- | --- | --- |
| Feature branch has many experimental commits, typo fixes, and fixups | Squash merge | Collapses into one readable commit on main |
| Need to preserve every commit and branch merge relationship | Merge commit | Records parents of both branches |
| Want linear history while preserving individual commits | Rebase then fast-forward | Commits are replayed on new base and remain distinct |
| Branch has audit requirements for the integration process | Merge commit or retain extra refs/review records | Easy to trace back the source commit chain |
| Short branch, one independent unit of work | Squash merge may fit | One commit represents the change |

There is no single best strategy for every repository. Agree within your team on whether commits on main should reflect each development step or simply a complete snapshot per change.

## 13. Controlled Squash Merge Workflow

A practical sequence:

~~~bash
# 1. Check local status
git status

# 2. Switch to target branch and update
git switch main
git fetch origin
git pull --ff-only

# 3. Review source branch history and changes
git log --oneline --graph --decorate main...feature
git diff --stat main...feature
git diff main...feature

# 4. Squash changes into index and working tree
git merge --squash feature

# 5. Review content to be committed
git status
git diff
git diff --cached --stat
git diff --cached

# 6. Create one new commit on target branch
git commit -m "Add payment workflow"

# 7. Verify commit and ancestry
git show --stat --oneline HEAD
git rev-list --parents -n 1 HEAD
git merge-base --is-ancestor feature main

# 8. Push target branch
git push origin main
~~~

The `git merge-base --is-ancestor feature main` command in step 7 normally returns false after squashing; this is expected. Evaluate integrated content via commit diff, review records, and tree checks rather than relying solely on ancestry.

Delete the source branch only after verifying the target commit, deciding retention, and confirming the team no longer needs to continue development on that branch.

## 14. History Relationship Diagram

~~~mermaid
flowchart TD
    A[Common commit A] --> B[Feature commit B]
    B --> C[Feature commit C]
    A --> S[Squash commit S on main]
    C -. Not a parent of S .-> S
    S --> T[Next commit on main]
    C --> D[Next commit if feature is still used]
~~~

Solid lines represent parent-child relationships. The dashed line only indicates that the two branches are related by work content, not an ancestry relationship recorded by Git in the commit.

Before finishing, confirm for yourself:

1. Can I distinguish squash merge from a merge commit and interactive rebase squash?
2. Do I understand that a squash commit only has a parent belonging to the target branch?
3. Did I review the staged diff before creating the commit?
4. Do I understand why `git branch --merged` may not list a squashed branch?
5. Did I decide whether to keep or delete the source branch based on retention and audit needs?
6. If continuing development, am I creating a new branch from the updated target branch?
7. Do I know that reverting a squash commit is a regular commit revert, without needing mainline `-m`?

Squash merge keeps the target branch history concise by saving a single commit containing the combined result. In exchange, source commits do not become ancestors of the squash commit. Manage the source branch, subsequent merges, and audit requirements in line with this consequence; do not equate content existing in the tree with history being connected by ancestry.

## References

- [Git documentation: git-merge](https://git-scm.com/docs/git-merge) — `--squash` option, merge strategies, and handling merge results.
- [Git documentation: git-commit](https://git-scm.com/docs/git-commit) — creating a commit from the index.
- [Git documentation: git-merge-base](https://git-scm.com/docs/git-merge-base) — finding common ancestors and checking ancestry relationships.
- [Git documentation: git-branch](https://git-scm.com/docs/git-branch) — checking merged branches and deleting branches.
- [Git documentation: git-revert](https://git-scm.com/docs/git-revert) — undoing regular commits and merge commits.
- [Pro Git: Basic Branching and Merging](https://git-scm.com/book/en/v2/Git-Branching-Basic-Branching-and-Merging) — branch model and merging methods.
