# Updating the Pinned Commit and Push Order: Child Repository Before Parent Repository

Git submodules allow a parent repository to use another repository as a dependent component. The parent repository does not store the entire contents of the child repository inside its own commits; instead, it stores a reference to a specific commit of the child repository. This reference is called a **gitlink**. Therefore, when updating a submodule, you must keep track of which commit is currently pinned, which commit is checked out in the child repository's working tree, and whether that commit has already been pushed to the remote.

In the **Submodule** chapter of module **SOURCE_CONTROL_GIT**, this lesson focuses on two things that are frequently done in the wrong order: updating the pinned commit in the superproject and pushing changes in the correct sequence. The child repository must have its commit on the remote so others can fetch it; only then should the parent repository record and push the gitlink pointing to that commit. If you push the parent repository before the child commit is reachable, teammates can check out the superproject yet fail to download the right submodule version.

After this lesson, you will be able to:

- Explain gitlinks and how the superproject records a submodule's commit.
- Distinguish updating to the pinned commit from updating to a remote branch with --remote.
- Identify which branch or commit a submodule is currently using.
- Create, commit, and push changes inside the child repository.
- Stage the gitlink, commit, and push the superproject after the child repository is published.
- Check submodule status and confirm the remote contains the pinned commit.
- Use push.recurseSubmodules to check or automatically push submodules when appropriate.

## 1. The Superproject Pins a Commit Using a Gitlink

When a directory is added as a submodule, the superproject stores a special entry in its tree:

~~~text
100644 blob    .gitmodules
160000 commit  libs/common
100644 blob    README.md
~~~

The entry with mode **160000** is a gitlink. It holds the hash of a commit in the submodule repository. The superproject does not store the files of libs/common as its own regular blobs; file contents and history belong to the child repository.

You can visualize the relationship:

~~~text
Superproject commit P
        |
        +-- parent repository tree
               |
               +-- .gitmodules
               |
               +-- gitlink libs/common
                         |
                         v
                 Submodule commit C
                         |
                         +-- child repository tree
                                +-- source files
                                +-- tests
~~~

Commit P records that this version of the superproject uses exact commit C in libs/common. As the child repository's branch continues advancing to commit D, the superproject still pins C until you update the gitlink and commit that change in the parent repository.

This is a critical point: **updating a branch inside the submodule does not automatically update the pinned commit in the superproject**. The superproject only records the new commit when the gitlink is staged and included in a parent repository commit.

## 2. Checking Configuration and the Pinned Commit

The .gitmodules file in the superproject declares the path and URL of each submodule. For example:

~~~ini
[submodule "libs/common"]
    path = libs/common
    url = https://example.com/team/common.git
    branch = stable
~~~

Common fields:

- **path**: directory path of the submodule inside the superproject.
- **url**: address of the child repository.
- **branch**: branch used by remote update commands as the target when running git submodule update --remote. If omitted, Git uses the submodule's default remote HEAD.

Inspect the list and status:

~~~bash
git submodule status
git submodule status --recursive
git config --file .gitmodules --get-regexp '^submodule\..*\.(path|url|branch)$'
~~~

To view the commit currently pinned by the superproject for a submodule:

~~~bash
git ls-tree HEAD -- libs/common
~~~

Output looks like:

~~~text
160000 commit 1a2b3c4d...    libs/common
~~~

The hash after the word commit is the commit pinned in the superproject's HEAD. To inspect the commit currently checked out in the submodule's working tree:

~~~bash
git -C libs/common rev-parse HEAD
git -C libs/common status -sb
~~~

If the hash from git ls-tree differs from the hash of git -C libs/common rev-parse HEAD, the submodule working tree is at a different commit from the one recorded by the superproject. This could be a change awaiting a gitlink update, or merely a temporary checkout for review.

## 3. Understanding the Prefixes in git submodule status

The git submodule status command prepends a symbol before each hash:

| Symbol | Meaning |
| --- | --- |
| Space | Submodule has checked out the exact commit pinned by the superproject. |
| - | Submodule has not been initialized or checked out yet. |
| + | Currently checked-out commit in the submodule differs from the commit pinned by the superproject. |
| U | Submodule has a gitlink conflict that needs resolution. |

Example:

~~~text
 1a2b3c4d libs/common (heads/stable)
+5e6f7a8b libs/ui (heads/feature)
-9c0d1e2f libs/legacy
U3a4b5c6d libs/parser
~~~

In the example:

- libs/common is at the pinned commit.
- libs/ui has a different commit checked out from the superproject's gitlink.
- libs/legacy has not been initialized yet.
- libs/parser has a gitlink conflict.

To initialize submodules that do not yet have a working tree:

~~~bash
git submodule update --init
~~~

Including nested submodules:

~~~bash
git submodule update --init --recursive
~~~

If you only want to initialize one path:

~~~bash
git submodule update --init -- libs/common
~~~

## 4. Distinguishing Pinned-Commit Updates from Remote Updates

The two commands below serve different goals.

### Checking Out the Exact Commit Recorded by the Superproject

~~~bash
git submodule update --init -- libs/common
~~~

This command brings the submodule to the commit currently pinned in the superproject's index/checkout. This is the operation normally used after cloning, switching branches, or pulling the superproject to sync submodules to the declared versions.

Standard update does not mean fetching the latest commit on a remote branch. If the superproject pins C while the remote branch has moved to D, the command above still checks out C.

### Updating According to a Remote Branch

~~~bash
git submodule update --remote -- libs/common
~~~

The **--remote** option tells Git to fetch the submodule's remote and update the working tree according to the configured branch. The branch can be declared in .gitmodules via the branch field. If undeclared, Git uses the default remote HEAD.

By default, update --remote checks out the target commit in detached HEAD. It does not automatically create a new commit in the submodule, nor does it automatically commit the gitlink in the superproject. After updating, the superproject will normally show the submodule as modified; you must stage the submodule path to record the new gitlink.

If you want to integrate the remote branch into the currently checked-out branch inside the submodule, you can use --merge or --rebase:

~~~bash
git submodule update --remote --merge -- libs/common
~~~

Or:

~~~bash
git submodule update --remote --rebase -- libs/common
~~~

These options merge or rebase the remote branch into the current branch inside the submodule, respectively. Use them only when you are actively working on that branch and understand the history impact. If you only want the remote commit for testing or updating the gitlink, the default checkout mode is usually more predictable.

## 5. Selecting a Tracked Branch for a Submodule

If there is no branch in .gitmodules, --remote uses the submodule's default remote HEAD. To specify a stable branch, declare it in .gitmodules:

~~~ini
[submodule "libs/common"]
    path = libs/common
    url = https://example.com/team/common.git
    branch = stable
~~~

Or set it via command:

~~~bash
git submodule set-branch --branch stable -- libs/common
~~~

This command updates .gitmodules in the superproject. Inspect and commit the .gitmodules change along with the gitlink if it is part of the project change:

~~~bash
git diff -- .gitmodules
git status --short
~~~

The branch field is a convention for choosing the update source when using --remote; it does not make the submodule automatically check out that branch when opening the repository. Nor should you confuse branch in .gitmodules with the pinned commit. The pinned commit remains the hash in the gitlink.

To view the current branch and upstream of a submodule:

~~~bash
git -C libs/common branch --show-current
git -C libs/common branch -vv
git -C libs/common remote -v
~~~

If the branch has no upstream yet, determine the right remote and branch before pushing.

## 6. Workflow for Updating a Submodule to a New Commit

Suppose the superproject uses libs/common and wants to update from commit C to commit D on branch stable.

### Step 1: Check Superproject and Submodule Status

~~~bash
git status -sb
git submodule status
git -C libs/common status -sb
~~~

Ensure there are no unexpected uncommitted changes. If the submodule has local edits, commit, stash, or back them up as needed before checking out a different commit.

### Step 2: Fetch Updates from the Child Repository's Remote

~~~bash
git -C libs/common fetch origin
git -C libs/common log --oneline --decorate --graph -8 origin/stable
~~~

Inspect the commits on origin/stable. If the actual remote branch has a different name, replace stable with the correct branch name. Do not assume the branch is main or master.

### Step 3: Check Out or Integrate the Target Commit

If you only want to pin a commit already on the remote:

~~~bash
git -C libs/common switch --detach <target-commit>
~~~

If you want to continue working on branch stable and fast-forward it to remote:

~~~bash
git -C libs/common switch stable
git -C libs/common merge --ff-only origin/stable
~~~

Merge --ff-only only allows the local branch to advance straight to origin/stable. If the branches have diverged, the command stops for you to inspect; it does not automatically create a merge commit.

### Step 4: Verify the Child Repository Commit

~~~bash
git -C libs/common rev-parse HEAD
git -C libs/common show --no-patch --oneline HEAD
git -C libs/common status -sb
~~~

Confirm HEAD is at the intended commit and the working tree has no unexpected changes. If the commit was just created locally, note its hash.

### Step 5: Update the Gitlink in the Superproject

Return to the superproject root directory and stage the submodule path:

~~~bash
git add -- libs/common
git diff --cached --submodule=log
git status --short
~~~

Running git add on the submodule path records the commit currently checked out in the submodule working tree into the superproject's index. It does not stage individual files inside the child repository. The submodule log diff lets you see the old and new commits.

### Step 6: Commit the Change in the Parent Repository

~~~bash
git commit -m "chore: update common submodule"
~~~

The superproject commit stores the new gitlink and, if applicable, changes to .gitmodules. At this point the child commit is recorded in the parent repository's history, but you still need to ensure it is reachable from the child repository's remote.

You can create the superproject commit locally before or after pushing the submodule, but **never push the superproject commit to remote before the commit referenced by the gitlink is reachable from the submodule remote**. The workflow below pushes the child repository first so the order is easy to verify.

## 7. Why Must the Child Repository Be Pushed Before the Parent Repository?

A superproject commit containing a gitlink only stores the submodule's commit hash. When someone else clones the superproject, Git must contact the submodule's remote to fetch that exact commit.

Suppose:

~~~text
Submodule remote:
C---D  (origin/stable)
    ^
    new commit needed

Superproject local:
P---Q  (HEAD)
    |
    +-- gitlink libs/common -> D
~~~

If commit D exists only in your local repository, superproject commit Q already references D while the child remote does not yet serve D. When teammates clone or update, Git may report that the submodule commit cannot be found or fail to check out the right version.

Safe sequence:

1. Create and verify the commit inside the submodule.
2. Push the branch or tag containing that commit to the submodule remote.
3. Verify the submodule remote has the commit.
4. Stage the gitlink and commit the superproject.
5. Push the superproject branch to remote.

~~~text
Submodule local
   | commit D
   v
Push submodule
   |
   v
Submodule remote has D
   |
   v
Superproject stages gitlink -> D
   | commit Q
   v
Push superproject
   |
   v
Others clone/update and get Q and D
~~~

If the submodule commit is already on the remote and fetchable from the source teammates use, there is no need to push it again. What matters is guaranteeing that the commit referenced by the gitlink is reachable via the appropriate submodule remote.

## 8. Complete Push Workflow from Child Repository to Parent Repository

Suppose you edited code in libs/common and want to update both repositories.

### Step 1: Commit Inside the Submodule

~~~bash
git -C libs/common switch -c fix/empty-response
git -C libs/common status -sb
git -C libs/common diff
git -C libs/common add -- src/CommonClient.java
git -C libs/common diff --cached
git -C libs/common commit -m "fix: handle empty response"
~~~

This example assumes branch fix/empty-response does not exist yet. If the branch already exists, switch to it and confirm the proper base before editing. This commit belongs to the history of libs/common, not the superproject.

### Step 2: Push the Submodule Commit

~~~bash
git -C libs/common branch -vv
git -C libs/common push -u origin fix/empty-response
~~~

Replace fix/empty-response with the branch containing the commit to share. If the branch already exists on the remote, push according to the configured upstream or remote/branch.

After pushing, verify:

~~~bash
git -C libs/common ls-remote origin refs/heads/fix/empty-response
git -C libs/common fetch origin fix/empty-response
git -C libs/common merge-base --is-ancestor HEAD FETCH_HEAD
~~~

The ls-remote command confirms the branch exists on the remote. The fetch command retrieves the branch tip into FETCH_HEAD; merge-base --is-ancestor exits successfully if the current HEAD commit is an ancestor of the remote tip, meaning the remote branch already contains that commit. If these verification commands fail, do not push the superproject until the right commit is identified and published.

### Step 3: Stage the Gitlink in the Superproject

~~~bash
git add -- libs/common
git diff --cached --submodule=log
~~~

If .gitmodules also changed, inspect it separately:

~~~bash
git diff --cached -- .gitmodules
~~~

### Step 4: Commit and Push the Superproject

~~~bash
git commit -m "chore: update common submodule"
git push origin main
~~~

Replace main with the superproject branch your team uses. After pushing, others can fetch the superproject and submodule to obtain the exact commit.

## 9. Automatically Checking or Pushing Submodules with the Superproject

Git supports the --recurse-submodules option for the push command. It helps reduce the risk of forgetting to push the child repository before the parent repository.

### Check Mode

~~~bash
git push --recurse-submodules=check origin main
~~~

Check mode requires any submodule commits referenced by the superproject push to be available on at least one remote of that submodule. If Git cannot verify that the required commit is reachable from a remote, the superproject push is rejected.

This mode suits teams that want to push submodules manually through their own workflow while adding a safeguard to prevent the superproject from referencing unpublished commits.

### On-Demand Mode

~~~bash
git push --recurse-submodules=on-demand origin main
~~~

On-demand mode tells Git to push the submodules required for the superproject push. If pushing a submodule fails, the superproject push will not proceed either.

To set as default:

~~~bash
git config --local push.recurseSubmodules on-demand
~~~

Or use check as default:

~~~bash
git config --local push.recurseSubmodules check
~~~

Choose a policy that matches your workflow. On-demand is convenient when submodule remotes and branches are clearly configured. Check is appropriate when the team wants explicit control over how child repositories are pushed while still blocking premature parent pushes.

These modes do not replace verifying branches, push permissions, and remote URLs of individual submodules. If a submodule lacks an appropriate remote/upstream or its commits cannot be pushed under current settings, on-demand may still fail. Read Git's output to see which child repository was not updated.

## 10. Verifying the Superproject Pins the Right Commit

After committing the parent repository, check the index, HEAD, and submodule working tree.

~~~bash
git ls-tree HEAD -- libs/common
git -C libs/common rev-parse HEAD
git submodule status
git diff HEAD --submodule=log
~~~

The hash in HEAD's gitlink must match the submodule's HEAD if the working tree has the recorded commit checked out. If git submodule status shows a + prefix, the submodule working tree is at a different commit than the current gitlink.

Inspect the staged gitlink commit before committing:

~~~bash
git ls-files --stage -- libs/common
git diff --cached --submodule=log
~~~

A staged submodule entry has mode 160000. After committing the superproject, use git ls-tree HEAD to confirm the gitlink was written into the commit.

Inspect the superproject remote:

~~~bash
git fetch origin
git log -1 --oneline --decorate origin/main
git ls-tree origin/main -- libs/common
~~~

The gitlink hash on origin/main must be the commit the team intends to publish. To verify the child remote can serve that commit, inspect the submodule's remote refs or try fetching the branch/tag containing the commit in a test clone.

## 11. When Updating a Submodule Causes a Conflict

If two superproject branches modify the gitlink of the same submodule, merging or rebasing the parent repository can report a conflict at the submodule path.

Inspect:

~~~bash
git status
git diff --submodule
git ls-files -u -- libs/common
~~~

The index may contain multiple stages for the gitlink corresponding to base, ours, and theirs versions. Determine which commit to use by inspecting the history inside the submodule repository:

~~~bash
git -C libs/common show --no-patch --oneline <ours-commit>
git -C libs/common show --no-patch --oneline <theirs-commit>
~~~

If both lines of development need to be combined, perform the merge or rebase inside the submodule repository according to its workflow, commit the result there, and push the new commit to the remote. Then check out the resulting commit in the submodule and re-stage the gitlink in the superproject:

~~~bash
git add -- libs/common
git diff --cached --submodule=log
~~~

Do not pick a gitlink hash merely because it appears at stage 2 or stage 3. Inspect the contents and history of the commits in the child repository before deciding.

## 12. Updating Submodules After Pulling the Superproject

When pulling the superproject, Git updates the gitlink in the parent branch. The submodule working tree may stay on the old commit until you run update.

~~~bash
git pull --ff-only
git submodule update --init --recursive
~~~

The update command checks out the exact commit pinned by the superproject. This behavior is essential so every team member uses the same dependency version.

If you want to update submodules to the latest remote branch instead of the pinned commit:

~~~bash
git submodule update --remote --recursive
~~~

After --remote, if the new commit differs from the superproject's gitlink, review and commit the gitlink change as an intentional dependency update. Do not run --remote just to "sync to latest" if the project requires reproducible builds tied to pinned commits.

To clone a superproject and initialize all submodules from the start:

~~~bash
git clone --recurse-submodules <superproject-url>
~~~

If already cloned without initializing submodules:

~~~bash
git submodule update --init --recursive
~~~

## 13. Updating a Submodule URL and Syncing Local Configuration

When a URL in .gitmodules changes, the superproject may store the new URL while users' local configs still retain the old URL. Synchronize:

~~~bash
git submodule sync --recursive
git submodule update --init --recursive
~~~

sync updates URLs in the submodule's local configuration according to .gitmodules. It does not replace committing the .gitmodules change in the superproject.

Verify the URL:

~~~bash
git config --file .gitmodules --get submodule.libs/common.url
git -C libs/common remote -v
~~~

If a URL contains credentials, do not put sensitive output into shared logs. Use a credential manager or a separate authentication mechanism instead of embedding tokens in committed URLs.

## 14. Common Errors

### Superproject Pushed, but Others Cannot Fetch the Submodule Commit

The cause is usually a gitlink pointing to a commit that exists only locally or has not been pushed to a remote users have read access to. Check the gitlink hash, submodule remote, and the branch/tag containing the commit. Push the child repository first, then re-verify fetchability.

### git submodule update --remote Does Not Update the Gitlink in Parent Commits

This is normal behavior. The command updates the submodule working tree according to the remote branch. To record the new commit in the superproject, run git add -- <submodule-path>, inspect the diff, and commit the parent repository.

### Submodule Switches to Detached HEAD After Update

This is the usual default of git submodule update. Git checks out the pinned commit, not necessarily a branch. If you need to develop further, create or check out an appropriate branch inside the submodule repository.

### git push in Superproject Does Not Push Submodule Commits

A regular push only pushes superproject refs. Use --recurse-submodules=on-demand or push the submodule separately first. Do not assume pushing the parent repository automatically sends child repository objects.

### Cannot Create a Branch in a Submodule Because It Is Checked Out in Another Worktree

Submodules can also use linked worktrees or branches checked out elsewhere. Inspect branches and worktrees inside the submodule repository itself, then select a different branch or detached HEAD as appropriate.

### .gitmodules Lists Branch stable, Yet Submodule Remains on an Old Commit

The branch field specifies the source --remote uses to find commits. It does not automatically update the gitlink when you check out or pull the superproject. Run update --remote, review the new commit, and commit the gitlink in the parent repository.

## 15. Checklist Before Pushing the Superproject

Before pushing a superproject branch with submodule changes, verify:

- The submodule has the intended commit checked out.
- Changes inside the submodule have been committed.
- The submodule commit exists on a remote accessible to teammates/CI, or an on-demand recursive push succeeded.
- The branch/tag containing the submodule commit has been published and does not exist only in your local repository.
- The gitlink has been staged in the superproject.
- git diff --cached --submodule=log shows the right old and new commits.
- The superproject commit recorded the new gitlink.
- After pushing, the superproject remote points to the right gitlink hash.
- Others can run git submodule update --init --recursive to retrieve the exact version.

If any condition is unmet, stop the superproject push and fix the child repository first.

## 16. Self-Check

The superproject pins libs/common at commit C. You edit the child repository, create commit D on branch fix/api-response, then stage libs/common and create commit P in the superproject. Commit D currently exists only on your machine; branch fix/api-response has not been pushed yet.

Answer the following:

1. Does the gitlink in commit P store the file contents of libs/common or only the commit hash?
2. Why might teammates encounter an error when checking out P?
3. Which command pushes the branch containing D to the child repository's remote?
4. After pushing the child repository, what part of the superproject needs to be verified and pushed?
5. How do git submodule update --init and git submodule update --remote differ?
6. How do push.recurseSubmodules=check and on-demand differ?

**Hint:** A gitlink stores commit hash D, not the child repository's file contents. If D is not on the remote yet, others cannot download the commit that P requires. Push the submodule's fix/api-response branch first, verify the remote contains D, then stage/commit/push the superproject's gitlink. update --init brings the submodule to the commit pinned by the superproject; update --remote fetches and updates according to the configured remote branch. check blocks pushing if the submodule commit is not yet on a remote; on-demand tells Git to push required submodules before completing the parent repository push.

## Conclusion

The superproject records a submodule's version with a gitlink pointing to a specific commit. Standard update syncs the working tree to the pinned commit; update --remote fetches commits from a remote branch and only produces a gitlink change when you stage and commit in the parent repository. When a submodule has new commits, commit and push the child repository first, verify the remote can serve the commit, and only then commit and push the superproject. Use push.recurseSubmodules=check or on-demand to help enforce ordering, and verify gitlinks and submodule status before sharing changes.
