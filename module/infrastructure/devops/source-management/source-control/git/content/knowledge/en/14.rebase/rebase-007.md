# Resolving conflicts and using --continue, --skip, --abort

## Why can rebase pause due to conflicts?

Rebase takes a branch's commits and replays them one by one onto a new base commit. For example, main received additional changes while you were developing on feature/search. When you run:

~~~bash
git fetch origin
git switch feature/search
git rebase origin/main
~~~

Git identifies the unique commits on feature/search and applies each commit on top of origin/main. If a commit being replayed modifies the same region of content as changes on the base branch, Git may not be able to combine them automatically. Rebase pauses and asks you to resolve the conflict.

During this time, Git stores the state of the rebase process and the commit currently being processed. You need to identify the current commit, inspect the conflicted files, combine the contents properly, add the result to the staging area, and then decide whether to continue, skip the current commit, or abort the entire rebase.

The three main control commands have distinct meanings:

| Command | Effect |
|---|---|
| git rebase --continue | Continue replaying the current commit after resolving and staging conflicts |
| git rebase --skip | Skip the commit currently being replayed and move to the next commit |
| git rebase --abort | Cancel the rebase process and restore the branch to its original state before the rebase |

Choose the right command based on the intent of the change. --skip drops all changes from the current commit out of the rebase result. --abort cancels the entire rebase in progress.

## Recognizing that rebase is paused

When Git reports a conflict, start with:

~~~bash
git status
~~~

Git usually displays a message similar to:

~~~text
interactive rebase in progress; onto 9a8b7c6
Last command done (1 command done):
   pick 1a2b3c4 Add search filter
Next command to do (1 remaining command):
   pick 5d6e7f8 Add search tests
You are currently rebasing branch 'feature/search' on '9a8b7c6'.
  (fix conflicts and then run "git rebase --continue")
  (use "git rebase --skip" to skip this patch)
  (use "git rebase --abort" to check out the original branch)
~~~

Exact output varies by Git version and rebase type. Read the message to see:

- Which branch is being rebased.
- Which commit was just replayed.
- Which commits remain in the queue.
- Which paths are in an unmerged state.
- Which next command Git suggests.

List only the remaining conflicted paths:

~~~bash
git diff --name-only --diff-filter=U
git ls-files -u
~~~

If no paths are listed, the index currently has no unmerged entries. Check the rebase status information and staged/unstaged changes before continuing.

### Inspecting the commit being replayed

To view the patch of the current commit:

~~~bash
git rebase --show-current-patch
~~~

You can view the commit and summary information with:

~~~bash
git show --stat --oneline REBASE_HEAD
git show REBASE_HEAD
~~~

REBASE_HEAD is a reference to the commit Git is currently replaying. Reading this commit helps you understand what the author intended to change, why the file conflicted, and what parts must be preserved.

View the contents of each version in the index while a file is still unmerged:

~~~bash
git show :1:path/to/file
git show :2:path/to/file
git show :3:path/to/file
~~~

For standard content conflicts, stage 1 is the merge base, stage 2 is ours, and stage 3 is theirs. Some conflict types like add/add, modify/delete, or rename may not have all three stages.

## Understanding ours and theirs accurately during rebase

This is a common point of confusion when resolving conflicts during a rebase.

In a normal merge, ours is typically the branch you are on and theirs is the branch being merged in. During a rebase, Git replays the working branch's commits onto the base branch. In that context:

- **ours (stage 2):** the content of the base branch and any commits already successfully replayed earlier.
- **theirs (stage 3):** the content from the working branch's commit currently being replayed.

For example, suppose you are rebasing feature/search onto origin/main. If the current commit edits a method, Git places the content from origin/main on the ours side and the edits from the feature/search commit on the theirs side.

Therefore, do not choose ours simply because the name sounds like "my branch". In a rebase, doing so can cause you to keep the base branch's version and discard the change being replayed.

You can view each side separately while the file is still unmerged:

~~~bash
git show :2:src/SearchService.java
git show :3:src/SearchService.java
~~~

If you want to temporarily take one side intact to continue editing, you can use:

~~~bash
# Take stage 2 (ours) into the working tree
git restore --ours --worktree -- src/SearchService.java

# Or take stage 3 (theirs) into the working tree
git restore --theirs --worktree -- src/SearchService.java
~~~

The two commands above replace the file's working tree content with one side. Afterward, you still need to read through it, combine any necessary logic, and stage the result. Taking one entire side blindly can discard the other side's changes.

## Workflow for resolving conflicts during rebase

A conflict resolution round usually follows these steps:

1. Check the rebase status and the commit being replayed.
2. View the conflicting content along with both sides' versions.
3. Edit the file to produce the final content.
4. Check for markers, content accuracy, and whitespace.
5. Stage the resolved files.
6. Run appropriate checks and continue the rebase.
7. Repeat if the next commit also conflicts.

### Step 1: Identify conflicted files

~~~bash
git status
git diff --name-only --diff-filter=U
git ls-files -u
~~~

Also read the rebase message to see which operation is running. If there are multiple files, handle each file according to the current commit's change goal.

### Step 2: Read the differences

~~~bash
git diff
git diff --cc
git rebase --show-current-patch
~~~

git diff --cc displays a combined diff for conflicting files. Combine this information with the REBASE_HEAD patch and branch history to understand the context.

For each file, determine:

- What did the base branch change?
- What is the commit being replayed trying to change?
- Do the two changes depend on each other?
- Can both behaviors be combined?
- Are there any APIs, configs, schemas, or tests that need to be updated together?

### Step 3: Edit the final content

Suppose the base branch added a permission check for exporting reports, while the working branch's commit added a date filter. Both changes edit the same method:

~~~java
public Report exportReport(User user, ReportFilter filter) {
    // Git cannot automatically combine the two changes
}
~~~

The result needs to preserve both the permission check and the filter:

~~~java
public Report exportReport(User user, ReportFilter filter) {
    permissionService.requireCanExport(user);

    return reportService.createReport(filter);
}
~~~

This example only illustrates how to combine two requirements. In a real project, preserve the API contract, authorization rules, error handling, and existing edge cases.

If the conflict is in a configuration file, check keys, data types, profiles, and default values. If it is in a dependency manifest or lockfile, verify library version compatibility and ensure the lockfile is generated consistently. For rename or delete conflicts, clarify which path and content should exist after the rebase.

### Step 4: Check for markers and inspect the diff

Search for conflict markers in the edited files:

~~~bash
rg -n '^(<<<<<<<|=======|>>>>>>>|\|\|\|\|\|\|\|)' -- src/SearchService.java config/application.yml
~~~

If there are no matches and the command exits with code 1, no matching lines were found. If the tool reports an error reading a file or path, resolve that error before drawing conclusions. Marker strings can legitimately appear in documentation or test fixtures; evaluate in context.

Re-read unstaged changes and check whitespace:

~~~bash
git diff
git diff --check
~~~

Do not just delete markers and continue. Confirm that the final logic satisfies the intent of both the base branch and the commit being replayed.

### Step 5: Stage the result

Once the content is right, stage each file:

~~~bash
git add -- src/SearchService.java config/application.yml
~~~

If you decide to delete a file:

~~~bash
git rm -- path/to/obsolete-file
~~~

Verify the index and staged changes again:

~~~bash
git status
git diff --name-only --diff-filter=U
git ls-files -u
git diff --cached
git diff --cached --check
~~~

Having no remaining unmerged paths is a prerequisite to continue. Read the staged diff to be sure Git will record the exact resolved result.

### Step 6: Verify behavior and continue

Run checks appropriate to the modified area, such as unit tests, config syntax validation, or module builds. If the conflict involves authorization, APIs, queries, or data, test the corresponding business cases.

When everything is staged and ready to apply the current commit:

~~~bash
git rebase --continue
~~~

Git continues replaying the commit. If the next commit has no conflicts, the process proceeds automatically. If the next commit also conflicts, Git pauses again and you repeat the workflow above.

A single rebase can have multiple conflict rounds. After each --continue, check git status again to see whether Git finished or is processing another commit.

## When to use git rebase --continue?

Use --continue when you want to keep the current commit's changes after resolving conflicts.

Prerequisites before running:

- All conflicted files have been read and edited.
- Files to keep have been staged with git add or git rm.
- No unmerged paths remain.
- The staged diff accurately reflects what should be committed.
- Appropriate checks have been executed.

Example:

~~~bash
git status
git diff --name-only --diff-filter=U
git diff --cached
git rebase --continue
~~~

Git may open your editor to confirm the commit message. Afterward, Git replays the next commit if any remain.

If the rebase pauses at another conflict, resolve and continue again. Do not assume one run of --continue suffices for the entire rebase.

### When the current commit becomes empty

Sometimes the changes in the commit being replayed already exist on the base branch or were integrated by another commit. After resolution, Git may report that the current commit has no remaining changes to apply.

Inspect the patch and current contents before deciding. If the commit no longer produces any needed change, you can use:

~~~bash
git rebase --skip
~~~

If an empty commit holds special meaning in your team's workflow, such as marking a milestone or driving automation, review your policy on keeping empty commits and the appropriate rebase option. Do not skip a commit just to make the process move forward.

## When to use git rebase --skip?

--skip tells Git to omit the commit currently being replayed and proceed to the next commit in the rebase queue.

This command is appropriate when you have confirmed the current commit's changes do not need to appear in the final result. Common cases:

- The commit's changes were already brought into the base branch by another commit.
- The commit becomes empty because the desired result already exists.
- The commit's changes are obsolete and the team decided not to keep them.
- Upon review, the current commit no longer belongs to the branch's goal.

Example:

~~~bash
git status
git rebase --show-current-patch
git show REBASE_HEAD
~~~

After confirming there is no need to keep the current commit's changes:

~~~bash
git rebase --skip
~~~

Git skips that commit's patch and continues the rebase. If the next commit conflicts, Git pauses for you to resolve it.

### Consequences of skipping

Suppose the feature branch has three commits:

~~~text
A -- B -- C
     ^
     commit B causing conflict
~~~

If you use --skip at B, Git omits B's changes from the rebase result. Commit C may still be replayed, but if C depends on B's changes, it may continue conflicting or stop working properly.

Therefore, before skipping, ask yourself:

- Is the commit's content already in the base branch?
- Do any subsequent commits depend on this change?
- Does dropping the commit lose necessary tests, documentation, or bug fixes?
- Does the branch still meet its original goal after dropping the commit?

If you need to keep part of the change, resolve the conflict and use --continue. If you want to discard all rebase work and return to the previous state, use --abort.

## When to use git rebase --abort?

--abort cancels the entire current rebase process and returns HEAD to the branch or initial state when the rebase began.

Use this command when:

- You chose the wrong base or target branch.
- The rebase is generating too many conflicts and you need to re-evaluate the integration strategy.
- You discover commits that are unsuitable for replaying.
- You want to stop to discuss with the team or prepare the branch again.
- You cannot determine a safe resolution at the moment.

Example:

~~~bash
git status
git rebase --abort
git status
git branch --show-current
~~~

After aborting, verify the branch, history, and working tree. Changes that existed before starting the rebase are handled according to the state Git restores; if --autostash was used, Git reapplies the automatically created stash and conflicts may occur when applying the stash.

--abort does not delete commits that existed before the rebase. It cancels the in-progress replay and restores the branch to its state at the start of the operation.

### Distinguishing --abort and --quit

Git also has the command:

~~~bash
git rebase --quit
~~~

--quit stops tracking the rebase process while leaving HEAD, the index, and the working tree in their current state. It does not restore the branch back to its starting position like --abort. If autostash was used, the automatic stash remains in the stash list.

Only use --quit when you intentionally want to keep the current state and handle the rest manually. When the goal is to cancel the rebase and return to the pre-rebase state, use --abort.

## Comparing the three rebase control options

| Criterion | --continue | --skip | --abort |
|---|---|---|---|
| Purpose | Keep and apply the current commit | Drop the current commit | Cancel the entire rebase |
| Requires conflict resolution | Yes, then stage the result | No need to keep current patch; must confirm it can be dropped | No resolution needed to proceed |
| Current commit | Replayed as a new commit | Skipped | Branch is restored to pre-rebase history, where original commit remains |
| Next commits | Continues processing | Continues processing | Not replayed |
| Final state | Rebase continues or completes | Rebase continues or completes | Returns to pre-rebase state |

One way to remember:

- Want to keep the commit after fixing conflicts: --continue.
- Want to drop the commit currently being replayed: --skip.
- Want to stop everything and return to the start: --abort.

## Complete workflow example

Suppose you are updating feature/search onto origin/main and the first commit hits a conflict:

~~~bash
# Update remote information
git fetch origin

# Start rebase
git switch feature/search
git rebase origin/main

# Git pauses due to conflict: check status and current commit
git status
git rebase --show-current-patch
git diff --name-only --diff-filter=U

# Edit the conflicted files in your editor
# Then re-read content and check for markers
rg -n '^(<<<<<<<|=======|>>>>>>>|\|\|\|\|\|\|\|)' -- src/SearchService.java

# Inspect diff and stage the result
git diff
git diff --check
git add -- src/SearchService.java
git status
git diff --cached

# Keep commit after resolving
git rebase --continue

# If the next commit also conflicts, repeat the resolution steps
git status

# After rebase completes, verify the result
git status
git log --oneline --graph --decorate -n 12
git diff --stat origin/main...HEAD
~~~

In this example, if after reading the patch you realize the commit being processed has already been applied on origin/main and has nothing left to keep, you can choose --skip instead of --continue. If you realize you started the rebase in the wrong direction or need to stop altogether, use --abort.

Do not run all three commands in sequence. They are three mutually exclusive choices based on your state and goal.

## Verifying after rebase completes

When Git reports the rebase succeeded, check the status:

~~~bash
git status
git branch --show-current
git log --oneline --graph --decorate -n 15
~~~

Confirm:

- There is no longer an in-progress rebase message.
- The current branch is the intended working branch.
- Commits to keep are present in history.
- Skipped commits did not lose needed changes.
- Diff relative to the base branch contains only intended changes.
- Relevant tests and builds pass.

View the branch's changes relative to the base branch:

~~~bash
git diff --stat origin/main...HEAD
git diff origin/main...HEAD
~~~

Re-run necessary tests. Rebase changes commit IDs, so pre-rebase test results are not enough to verify the post-rebase result.

### If the branch was pushed before rebasing

Rebase creates new commits with different identifiers. If the branch was already pushed and others rely on the old history, discuss with the team before updating the remote.

When the team agrees to update rewritten history, typically use:

~~~bash
git fetch origin
git push --force-with-lease origin feature/search
~~~

--force-with-lease checks that the remote ref is still in the state local expects before force-updating. This helps avoid overwriting new changes you have not fetched, though it still replaces remote history. Only use it when authorized and coordinated with collaborators on the branch.

If the branch only exists locally, no force push is needed.

## Common errors

| Situation | Possible cause | How to resolve |
|---|---|---|
| Ran --continue but Git still stops | Unmerged or unstaged files remain | Check git status, git ls-files -u, and stage resolved files |
| Conflicts repeat across multiple commits | Each replayed commit may touch the same code area | Handle each round and read the REBASE_HEAD patch |
| Using --skip drops a feature | Skipped a commit containing needed changes | Review the commit, consider aborting and re-running rebase with proper resolution |
| Using --abort when intending to drop one commit | Confused abort and skip | Confirm your goal before choosing a command |
| Chose wrong ours or theirs | Applied merge intuition to rebase | Remember stage 2 is base and stage 3 is the commit being replayed during rebase |
| Rebase finishes but tests fail | Combined result has broken logic or missing dependent changes | Read diff, history, and re-run tests for affected behavior |
| Push rejected after rebase | Commit hashes changed | Sync and coordinate; only use force-with-lease when permitted |

## Safe habits when handling rebase conflicts

- Fetch the base branch and confirm the right branch before starting.
- Ensure a clean working tree or clearly isolate work in progress.
- Read the current commit with git rebase --show-current-patch before editing.
- Understand ours/theirs properly in the context of rebase.
- Stage each resolved file and inspect the staged diff before continuing.
- Only skip when you have confirmed the entire commit patch does not need to be kept.
- Use abort when you want to cancel the entire process and return to the initial state.
- Re-run tests after the rebase completes.
- Coordinate with the team before pushing rewritten history.

## Summary

Rebase can pause at any commit when Git cannot combine changes automatically. Check git status and the REBASE_HEAD patch to understand the commit being replayed, resolve each file, stage the result, and verify behavior. Use git rebase --continue to keep the fixed commit, --skip to drop the current commit once confirmed unnecessary, or --abort to cancel the entire rebase and return to the initial state. Once finished, review history, diffs, and run tests before sharing the branch.
