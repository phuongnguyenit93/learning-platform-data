# Problems Git solves: change tracking, collaboration, and recovery

As a software project grows, its source code changes every day. One person may edit multiple files at once; multiple people may work on the same feature; a fix may accidentally break functionality that was working well. If you only save files on a computer or copy directories by version, the team quickly runs into hard-to-answer questions: what changes were made, why were they made, who is working on what, how to combine work, and can you return to a previous good state?

Git solves these problems by managing the project's change history. Git helps record confirmed states, organize independent work on branches, exchange history between copies of the repository, and recover unwanted changes. This is the foundation of the workflow in the `SOURCE_CONTROL_GIT` module, from the working tree, staging area, and commits to branches, merges, remotes, tags, and recovery operations.

## 1. Difficulties with manual source code management

Imagine a team of three people developing an application together. Without a version control system, the team often has to handle the following problems manually:

- **Not knowing exactly what changed:** a file is edited multiple times without a clear record of its before-and-after contents.
- **Difficulty finding the cause of a bug:** when a working feature suddenly breaks, the team has to manually compare copies or ask each person what they changed.
- **Easy to overwrite each other's work:** two people editing the same file and then sending back the entire file can cause the later person's edits to erase the earlier person's edits.
- **Difficulty experimenting with ideas:** developers want to try a new implementation approach but hesitate to affect the stable version.
- **Time-consuming recovery:** if an edit introduces a bug, the team has to search for an old copy or manually undo the changes.
- **Lack of context:** seeing a modified line of code without knowing which requirement that change was meant to address, or which bug or feature it relates to.

Naming directories like `project-final`, `project-final-new`, or `project-final-fixed` only creates disconnected copies. This approach does not provide a structured history, does not show relationships between changes, and lacks a reliable mechanism for merging work.

Git brings change history directly into the project's workflow.

## 2. Git solves the change tracking problem

### 2.1. A commit records a meaningful state

In Git, a **commit** is a history milestone that records the state of the project at a point in time. The commit author typically includes a message describing its purpose, such as:

- `Add password reset endpoint`
- `Fix rounding error in invoice total`
- `Update deployment instructions`

A commit helps answer three fundamental questions:

1. In what state was the project recorded?
2. In which commit was the change recorded, and where does it sit in history?
3. Why did the author make that change?

Conceptually, Git stores the state of files in a commit rather than just storing a list of edit operations. Objects inside Git are content-addressed. A commit links to a directory tree and parent commits, forming a history graph. Git may optimize internal storage space, but in day-to-day use, you should think of each commit as a snapshot of the project state at that moment.

A commit typically contains information about:

- The directory tree representing the project state.
- Parent commit(s), showing which history this commit continues from.
- Author and committer, along with their respective timestamps.
- A message describing the purpose of the change.

Therefore, Git history is not just an arbitrarily named list of versions. It is a chain or graph of interconnected milestones.

### 2.2. Working tree, staging area, and repository form the recording workflow

Git divides the process of preparing a commit into areas with distinct roles:

| Area | Role | Example |
| --- | --- | --- |
| Working tree | The files you are viewing and editing in the project directory | Editing `src/Invoice.java` |
| Staging area (index) | The set of selected content to be included in the next commit | Staging only the billing calculation fix |
| Local repository | Where commits and history are stored on the current machine | Created commits and local branches |

Basic workflow:

~~~bash
git status
git diff
git add src/Invoice.java
git diff --staged
git commit -m "Fix invoice total rounding"
~~~

The commands above represent each step:

- `git status` shows which files have been modified, which are staged, and which are untracked by Git.
- `git diff` shows changes in the working tree that have not been staged yet.
- `git add` puts the current contents of a file into the staging area.
- `git diff --staged` verifies the exact content selected to be committed.
- `git commit` creates a history milestone from the content in the staging area.

The staging area is especially useful when a work session involves multiple changes that do not all belong to the same purpose. For example, you fixed a billing calculation bug and also reformatted another file. You can select only the bug fix to commit separately, giving each commit a clear meaning and making it easy to review.

Note: `git add` captures the content at the time the command is run. If you continue editing the file afterward, the new edits stay in the working tree and are not automatically added to the staging area. Therefore, before committing, check again with `git diff` and `git diff --staged`.

### 2.3. History helps trace changes

Once commits exist, Git provides tools to inspect history and compare states:

~~~bash
git log --oneline
git log --oneline --graph --decorate --all
git show <commit>
git diff <old-commit> <new-commit>
~~~

- `git log` lists commits chronologically through history.
- `git log --graph --all` helps observe branches and relationships between lines of history.
- `git show` displays the metadata and changes recorded in a specific commit.
- `git diff` compares contents between two states.

For example, when a user reports that an invoice total is rounded incorrectly, the team can find commits near the time the bug appeared, inspect the relevant lines, and read commit messages to understand the intent of the edits. If commits are divided into reasonable units, tracing the root cause is much easier than comparing dozens of directory copies.

History is only valuable when commits are created intentionally. A commit containing too many unrelated changes, or having a generic message like `update`, reduces traceability.

## 3. Git solves the collaboration problem

### 3.1. Branches enable independent development of tasks

If everyone edits directly on a single line of history, unfinished changes can interfere with others' work. Git uses **branches** so each task can develop on its own line of history.

A Git branch is essentially a lightweight reference to a commit. Creating a branch does not mean copying the entire project into a separate repository. It creates a named reference to group the commits for that task together.

For example, a developer creates a branch to develop a password reset feature:

~~~bash
git switch -c feature/password-reset
~~~

After editing source code and creating commits, the developer can continue working on this branch without having to bring the changes into the main branch yet. Someone else can work on a payment bugfix branch. Both tasks are developed independently and can be reviewed before integration.

Branch names should reflect their purpose, such as `feature/password-reset`, `bugfix/invoice-rounding`, or `docs/setup-guide`. Specific naming conventions depend on the team.

### 3.2. Merge combines the history of branches

When a task is complete, the team can integrate that branch into the target branch using merge:

~~~bash
git switch main
git merge feature/password-reset
~~~

Git finds the common ancestor in history and combines the changes. If the branches modified non-conflicting sections, Git can usually complete the merge automatically. If the same region of content was modified in ways that cannot be resolved automatically, Git marks a conflict for the developer to review.

Merge preserves the relationship between lines of history. In some situations, Git can perform a fast-forward: the target branch simply moves its reference to the newer commit because there are no diverged commits to combine. In other situations, Git creates a merge commit to record the integration of two lines of history.

### 3.3. Conflicts are decision points for humans

A merge conflict does not necessarily mean the source code is wrong. It means Git cannot automatically determine what the final content should be.

For example, two people edit the same line:

- Person A changes the default fee rate from 5% to 6%.
- Person B changes the default fee rate from 5% to 7%.

Git does not know which business decision is right. The person resolving the conflict needs to consult the owners, check the requirements, and choose or combine the appropriate content.

The resolution workflow typically includes:

1. Run the merge or integration operation and list conflicted files using `git status`.
2. Open each file and inspect the conflict markers inserted by Git.
3. Edit the content to the correct version according to requirements.
4. Mark the file as resolved using `git add <file>`.
5. Complete the merge following the instructions Git displays, typically using `git commit` if Git asks to create a merge commit.

You should not simply delete the conflict markers just to make Git stop reporting errors. What matters is that the content after resolution is functionally and business-wise correct.

### 3.4. Remotes let copies exchange history

Git is a distributed version control system. Each normal clone has its own repository and contains most of the history needed to work independently. As a result, developers can view logs, create commits, and develop branches even while temporarily disconnected from the server. Shallow clones or partial clones may download only part of the history or objects depending on configuration.

A **remote** is a name used to refer to another repository, usually located on a server or source code hosting service. A remote is not a shared working folder; it is an endpoint for exchanging commits and references between repositories.

Commonly used commands:

~~~bash
git clone <url>
git remote -v
git fetch origin
git pull
git push origin feature/password-reset
~~~

- `git clone` creates a copy of a repository to begin working.
- `git remote -v` lists the configured remote URLs.
- `git fetch` downloads new information and history from the remote into the local repository without automatically integrating them into the working branch.
- `git pull` performs a fetch and then integrates changes into the current branch, usually via merge or rebase depending on configuration and flags.
- `git push` sends local commits to the remote so others can retrieve them.

A common collaboration workflow is for each person to develop on their own branch, push the branch to the remote, and open a Pull Request or Merge Request for the team to review. Pull Requests and Merge Requests are features of source code hosting platforms; they use Git to exchange history, though they are not core Git commands themselves.

Through this mechanism, teams can work in parallel, review changes before integration, and maintain a traceable shared history.

## 4. Git solves the change recovery problem

Not every change is right on the first try. A mistyped command, a rushed edit, or a bad commit can leave the project in an unwanted state. Git provides several recovery methods depending on where the change lives and whether it has been shared.

### 4.1. Restoring unstaged changes

If a file has changes in the working tree and you want to discard those changes to return to the content in the current commit, you can use:

~~~bash
git restore src/Invoice.java
~~~

By default, this command restores the file in the working tree from the staging area (index). If the file has no staged changes, the content in the index usually matches `HEAD`. Changes not saved elsewhere can be lost, so check `git diff` before running it.

### 4.2. Unstaging while keeping modified content

If you already ran `git add` but decide not to include the file in the next commit yet, you can unstage it:

~~~bash
git restore --staged src/Invoice.java
~~~

This command removes the file from the staging area while keeping the edits in the working tree intact. You can continue editing or re-select what to commit.

### 4.3. Reversing a shared commit with revert

If a commit has already been pushed and others may have built on top of it, the safe approach is usually to create a new commit that reverses the change:

~~~bash
git revert <commit>
~~~

Revert does not delete the old commit from history. It creates a new commit with the inverse effect of the specified commit. Thus, the history still shows that the original change occurred and was later reversed.

This is usually the right choice when fixing shared history on a branch used by multiple people.

### 4.4. Moving a branch with reset

`git reset` moves the current branch reference to another commit and, depending on options, updates the staging area or working tree:

~~~bash
git reset --soft <commit>
git reset --mixed <commit>
git reset --hard <commit>
~~~

- `--soft`: moves the branch while keeping the staging area and working tree unchanged.
- `--mixed`: moves the branch and updates the staging area; keeps the working tree contents. This is the default mode if no option is specified.
- `--hard`: moves the branch and updates both the staging area and working tree to match the target commit. Uncommitted changes to tracked files can be overwritten and lost; untracked files usually remain.

Reset is useful when cleaning up local history, such as squashing or dropping unpushed commits. However, rewriting shared history can cause others' branches to diverge from the remote and create synchronization difficulties. Therefore, consider the scope of impact before resetting a pushed commit; for shared changes, `git revert` is usually easier to coordinate.

### 4.5. Recovering commits with reflog

Sometimes a commit no longer appears in the log of the current branch because the branch was reset or moved. If that commit is still in local data and has not been garbage-collected by Git, reflog can help trace the movement of references:

~~~bash
git reflog
~~~

After identifying the commit hash to recover, you can create a new branch pointing to that commit:

~~~bash
git branch rescue-work <commit>
~~~

Reflog is a local log of when references were updated. It is very useful for rescuing commits that were recently detached from a branch, but it is not a permanent backup: reflog entries can expire and unreferenced objects can be cleaned up. Therefore, when you notice a missing commit, check reflog early.

### 4.6. Temporarily shelving work with stash

Sometimes you are editing a feature and need to switch to another branch to handle an urgent bug. If you do not want to create a commit yet, you can temporarily stash the changes:

~~~bash
git stash push -m "WIP password reset"
git stash list
git stash pop
~~~

Stash temporarily saves changes so the working tree can return to a cleaner state. Afterward, you can reapply them using `git stash pop` or `git stash apply`. Untracked files are not included in a stash by default; if you need to save those too, look into the `-u` option.

Stash is suitable for short-term context switching. For longer-running work or work that needs to be shared, creating commits on a separate branch usually keeps history clearer.

## 5. A combined scenario

Suppose the team is developing a payment application. One developer is assigned to fix an invoice total rounding bug. Git can be applied in the following sequence:

**Step 1 — Sync and create a working branch**

~~~bash
git switch main
git pull
git switch -c bugfix/invoice-rounding
~~~

The developer starts from the latest state of the main branch and works on an isolated branch.

**Step 2 — Inspect and select changes**

After editing the source code:

~~~bash
git status
git diff
git add src/Invoice.java
git diff --staged
~~~

The developer reviews the changes and stages only the content related to the rounding bug.

**Step 3 — Record the change milestone**

~~~bash
git commit -m "Fix invoice total rounding"
~~~

The commit creates a milestone that can be reviewed and compared later.

**Step 4 — Share for team review**

~~~bash
git push -u origin bugfix/invoice-rounding
~~~

The branch is pushed to the remote. The team can open a Pull Request, discuss, request edits, and review before integrating.

**Step 5 — Integrate and resolve conflicts if any**

Once the change is approved, the working branch is merged into the target branch according to the team's workflow. If Git reports conflicts, the developer resolves the content, re-verifies, and completes the integration operation.

**Step 6 — Recover if a bug is found after integration**

If a shared change causes a bug, the team can create a reverse commit with `git revert`, then continue investigating and fixing the root cause properly. History retains both the original commit and the revert commit, helping everyone understand what happened.

This scenario shows three interconnected benefits: commits create an audit trail, branches and remotes support collaboration, and recovery commands help handle mistakes in a controlled manner.

## 6. Git does not automatically determine change quality

Git manages history and supports coordination, but it does not know on its own whether a change meets business requirements. Nor does Git replace testing, code review, release processes, or operational data backups.

Some limitations to understand clearly:

- **Good commits do not equal good code:** clear messages and clean history do not guarantee bug-free functionality.
- **A successful merge does not equal correct logic:** Git can combine text without detecting two changes that conflict in business logic.
- **A remote is not the sole backup:** permission errors, repository deletion, or server outages can still happen. Critical projects need an appropriate backup policy.
- **Git primarily manages file contents:** large data files, frequently changing binaries, or specialized assets may require additional solutions like Git LFS.
- **Git does not protect secrets automatically:** never commit passwords, tokens, private keys, or sensitive data. If a secret has been committed and shared, you must also revoke or rotate the secret; deleting the file in a new commit does not remove the secret from old history.
- **Git does not automatically exclude already-tracked files:** adding a filename to `.gitignore` mainly affects untracked files. Files already tracked by Git still need to be handled separately if you want to stop tracking them.

Therefore, Git works best when combined with commit conventions, a branching strategy, code review, testing, and a clear release process.

## 7. Summary

Git solves three major groups of problems in the software development process:

| Problem | Supporting Git mechanisms | Outcome |
| --- | --- | --- |
| Not knowing what changes happened and why | Staging area, commit, log, diff, show | History available to inspect, compare, and trace root causes |
| Multiple people working simultaneously | Branch, merge, remote, fetch, pull, push | Independent development, sharing, and integration of work |
| Fixing mistakes or needing to return to a prior state | Restore, revert, reset, reflog, stash | Ways to handle changes across different stages |

When you understand Git through these three goals, commands are no longer disconnected statements to memorize. Every operation serves a specific purpose: controlling changes in progress, recording a reliable state, sharing history with others, or recovering when needed. That is the foundation for using Git safely and effectively in both personal projects and development teams.
