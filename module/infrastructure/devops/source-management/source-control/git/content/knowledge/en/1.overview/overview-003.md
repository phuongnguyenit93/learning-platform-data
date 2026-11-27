# Centralized and distributed version control

## Why is version control needed?

Version Control is the practice of recording and managing changes to source code, configuration files, and project files over time. A Version Control System (VCS) helps a development team know who changed what content, when the change was made, why it was made, and enables restoring or comparing previous states.

When multiple people work on a project together, a VCS also provides mechanisms to combine changes, develop features in parallel, and resolve conflicts. Two common architectural models are **Centralized Version Control Systems (CVCS)** and **Distributed Version Control Systems (DVCS)**. Git belongs to the distributed model.

## Centralized version control model

In the centralized model, the entire primary version history is stored on a single central server or repository. Team members check out a working copy from the server, edit files on their machines, and then send changes back to the server via a commit operation.

~~~mermaid
flowchart TB
    S[Central repository]:::central
    A[Developer A] -->|checkout / update| S
    B[Developer B] -->|checkout / update| S
    A -->|commit| S
    B -->|commit| S
    classDef central fill:#dbeafe,stroke:#2563eb,color:#1e3a8a
~~~

The server serves as the shared reference point for the project's history and state. Systems such as Subversion (SVN) and Perforce are commonly used under this model.

The basic workflow typically proceeds as follows:

1. A member checks out the project or a branch from the central repository.
2. The member edits files in their working copy and checks local changes.
3. The member updates with new changes from the server to detect content modified by others.
4. If there are conflicts, the member resolves them and then commits the changes to the server.
5. Other members run update to receive the new revision.

Example with SVN:

~~~bash
# Get a working copy from the central repository
svn checkout https://svn.example.com/repos/app/trunk app
cd app

# Check changes and differences
svn status
svn diff

# Add a new file to version control and commit to the server
svn add src/new-feature.java
svn commit -m "Add new feature"

# Retrieve new revisions from the server
svn update

# View revision history
svn log
~~~

The noticeable point is that the svn commit command sends changes to the central repository. The new revision is recorded on the server and becomes part of the shared history.

### Advantages and limitations

- **Centralized administration:** administrators have a single primary place to assign permissions, monitor activity, and enforce retention policies.
- **Intuitive collaboration model:** members work against the same primary repository; the shared state is updated through the server.
- **Suitable for strictly controlled workflows:** some organizations want to control read, write, and change-flow permissions at a single point.
- **Dependency on the server:** if the server is unreachable, members generally cannot commit new revisions to the shared history. They can still edit files locally, but recording changes must wait until the server is back online.
- **Frequent network operations:** checkout, update, and commit require connecting to the server; network latency can affect the experience.

CVCS can still support branching and merging. The difference lies in how history is stored and distributed: the central repository holds the primary history, while a member's working copy is typically not a complete, standalone copy of the entire repository.

## Distributed version control model

In the distributed model, every clone of the repository has the repository data and version history needed to work independently. Members can create commits on their own machines without needing to connect to a shared server first. When they need to exchange changes, they synchronize with one or more other repositories through operations such as fetch, pull, and push.

~~~mermaid
flowchart TB
    A[A's local repository<br/>history and commits] <-->|fetch / push| R[Shared or team repository]
    B[B's local repository<br/>history and commits] <-->|fetch / push| R
    C[C's local repository<br/>history and commits] <-->|fetch / push| R
    A <-->|direct exchange when appropriate| B
~~~

Git and Mercurial are classic examples of DVCS. With Git, a normal git clone command creates a local repository containing the project's history, alongside a working tree for editing files. (Reduced clone modes such as shallow clones may retrieve only part of the history.)

Basic workflow with Git:

~~~bash
# Create a local repository from a remote repository
git clone https://example.com/team/app.git
cd app

# Create a branch and work independently
git switch -c feature/new-report

# Record changes into the local repository
git status
git add src/report.java
git commit -m "Add report generation"

# Fetch new information from the remote to inspect and integrate
git fetch origin
git rebase origin/main

# Share the branch to the remote
git push -u origin feature/new-report
~~~

The git commit command only records a snapshot in the local repository. git fetch downloads new information and commits from the remote without automatically integrating them into the current branch. git rebase in the example places the current branch's commits on top of origin/main; a team may also choose git merge depending on project conventions. git push sends local commits to the remote so others can retrieve them.

### Advantages and limitations

- **Working offline:** you can view history, create branches, compare changes, and commit locally without a network connection.
- **Multiple copies of history:** every full clone is an independent copy of the repository. If one machine fails, other clones still preserve the history and assist with recovery.
- **Flexible branching:** creating, switching, and merging local branches is fast, making parallel feature development convenient.
- **Multiple ways to collaborate:** members can exchange changes via a shared remote, a code review platform, or intermediate repositories.
- **Requires clear understanding of synchronization:** local commits do not automatically appear on the remote. Members must fetch/pull to receive changes and push to share commits.
- **Managing copies and access control:** history is replicated to many machines. Organizations need to manage access permissions, protect sensitive information, and establish appropriate policies for storing clones.

A DVCS does not strictly require a central server. However, many teams still choose one shared remote as the primary integration point to standardize release branches, code review, and deployment workflows.

## Comparing the two models

| Criterion | Centralized (CVCS) | Distributed (DVCS) |
|---|---|---|
| Primary history storage | Central repository | Present in each full clone repository |
| Typical commit | Sends a revision to the server | Records a commit in the local repository |
| Working offline | Can edit files; generally cannot commit to the shared repository | Can commit and operate on local history |
| Exchanging changes | Primarily through the central server | Through one or more remotes/other repositories |
| Branching | Can be supported; branches are managed in the central repository | Local branches are lightweight and flexible |
| Point of dependency | The central server is a critical point in the workflow | No server needed for local commits; a remote can still serve as the team's integration point |
| Examples | SVN, Perforce | Git, Mercurial |

One should not conclude that CVCS is always outdated or that DVCS is always a better fit. The choice depends on how the organization manages permissions, data types, team size, offline requirements, and release workflows. A centralized system can suit environments requiring tight governance; a distributed system is often advantageous for teams needing flexible branching and multi-site collaboration.

## Git is distributed yet can still follow a centralized workflow

This is an important point when learning Git: **Git's distributed architecture does not mean a team must work without a central repository**. Git gives each member a full repository, while the team still agrees on one remote—usually named origin—as the shared place for collaboration and integration.

A common team workflow is:

1. Members clone the shared remote to their machines.
2. Members create separate branches for each task and commit regularly on their local machines.
3. Before integrating, members fetch new changes from the remote and update their branch according to the team's merge or rebase convention.
4. Members push their branch to the remote, then open a review request (pull request or merge request) if the team's platform supports it.
5. Once approved, the changes are merged into an integration branch such as main.
6. Members fetch or pull to update their local repositories.

~~~mermaid
flowchart TD
    C[Clone remote] --> B[Create task branch]
    B --> L[Local commits]
    L --> F[Fetch new changes]
    F --> I[Merge or rebase]
    I --> P[Push branch to remote]
    P --> R[Review and integrate into main]
    R --> U[Members update local repositories]
    U --> B
~~~

In this workflow, the remote serves as the shared coordination point. Nevertheless, each member can still commit, view history, and create branches without needing the server. That is the benefit of a DVCS applied within a collaborative workflow that has a centralized integration point.

### Distinguishing common Git operations

| Command | Primary effect |
|---|---|
| git clone | Creates a local repository from another repository and configures the initial remote |
| git status | Shows the state of the working tree and staging area |
| git add | Places changed content into the staging area to prepare for a commit |
| git commit | Creates a commit in the local repository |
| git fetch | Retrieves new commits and references from the remote; does not automatically merge into the current branch |
| git pull | Fetches and then integrates changes into the current branch according to config or merge/rebase options |
| git push | Sends commits and updates references on the remote |
| git log | Views commit history |

Therefore, "committed" and "pushed" are two different states. A commit can exist safely in your local repository without having been shared with the team yet. Before concluding that changes are on the remote, check the sync status and target branch.

## Choosing a model and applying it in practice

When evaluating a version control model, a team should consider the following questions:

- **Does the team need to work offline?** If members frequently travel or work on unstable networks, a DVCS offers a clear advantage.
- **Who needs access to history?** CVCS centralizes control points. With DVCS, you must account for history being replicated to clones and establish data protection policies.
- **Does the team frequently develop in parallel?** A DVCS like Git supports local branching conveniently, though branch naming conventions, reviews, and integration rules are still needed.
- **What types of files does the project manage?** Text-based source code usually fits Git well. Projects with many large binary files or file-locking workflows may need to evaluate suitable tools and extensions.
- **What do the integration and release workflows look like?** Regardless of the model used, the team still needs to define where integration happens, how conflicts are resolved, how releases are created, and how backups are handled.

For projects using Git, agree on the primary remote, default branch, branch creation rules, how branches are updated, review practices, and push permissions on important branches. Create commits with a clear scope, write understandable messages, synchronize regularly, and resolve conflicts directly within the context of the change. Never put passwords, tokens, or secret keys into commit history; if a secret has been committed and pushed, handle it as an exposure incident, even if the file was deleted in a later commit.

## Common misconceptions

- **"GitHub or GitLab is Git."** Git is a distributed version control system. GitHub and GitLab are platforms providing repository hosting, code review, and collaboration services built on Git.
- **"Having a remote means it is a centralized system."** A remote is simply a repository with which Git can exchange data. A repository can have multiple remotes, and no remote is architecturally mandatory.
- **"Committing in Git shares it with the whole team."** Commits are created locally; you need to push to send commits to a remote.
- **"A DVCS has no central point."** A DVCS does not require a central point to store history, but a team can certainly choose one remote as its primary integration point.
- **"CVCS has no branches."** Many CVCSs support branches. How branches are created, stored, and shared is what differs between systems.

## Key takeaways

CVCS organizes history around a central repository and typically requires a server connection to record shared revisions. DVCS stores history in cloned repositories, enabling members to commit and develop independently and then synchronize changes when needed. Git is a DVCS; teams can leverage that flexibility within a workflow featuring a central remote, shared branches, and clear review steps. Understanding the exact roles of the working tree, local repository, commits, and remotes is the foundation for using Git safely and collaborating effectively.
