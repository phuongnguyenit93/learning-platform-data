# Cloning a Repository with git clone: URL, Target Directory, and Initial Branch

When joining a project that already has a repository on GitHub, GitLab, an internal server, or another machine, the first step is usually obtaining a local copy to work on. The <code>git clone</code> command creates a local repository, downloads Git data from the source, configures a default remote, and checks out the initial branch so you can start reading the source code or developing.

To clone properly, you need to understand three choices: the URL identifies the repository source, the target directory determines where the copy is placed on your machine, and the initial branch determines which version is checked out. Git usually selects the default branch advertised by the remote automatically, but you can specify a particular branch or tag when needed.

This lesson belongs to the **Repository Initialization** chapter of the **SOURCE_CONTROL_GIT** module. The module teaches Git from the working tree, staging area, commits, and history through branches, merges, rebases, remotes, and tags; it also trains you in branch-based collaboration, conflict resolution, tracing changes, and recovering from mistakes while preserving important history. Mastering cloning helps you start working with existing repositories and understand the relationship between your local copy and the remote.

## 1. What does git clone do?

Basic command:

~~~bash
git clone <repository-url> [<directory>]
~~~

When you run the command, Git typically performs the following actions:

1. Creates the target directory and initializes the local repository structure.
2. Connects to the source repository via a URL or local path.
3. Downloads the required objects and refs from the source.
4. Creates a default remote named <code>origin</code> pointing to the clone source.
5. Creates remote-tracking refs, such as <code>origin/main</code>.
6. Creates a local branch for the default branch and sets up its upstream.
7. Checks out the snapshot of the initial branch into the working tree, unless you request not to check out.

After cloning succeeds, you have an independent repository on your machine. New commits you create locally do not automatically appear on the remote; you must push when you want to share them.

## 2. Finding the repository URL to clone

The URL is the address Git uses to retrieve data. Copy the URL from the repository page or obtain the path provided by the project maintainer. Common formats include:

| Connection type | Example | Characteristics |
|---|---|---|
| HTTPS | <code>https://github.com/acme/payment-service.git</code> | Easy to use over HTTPS networks; the server may require authentication via a token or credential manager |
| SSH (scp-like form) | <code>git@github.com:acme/payment-service.git</code> | Uses an authorized SSH key or agent |
| SSH (URL form) | <code>ssh://git@github.com/acme/payment-service.git</code> | Same SSH authentication mechanism, explicitly showing scheme and host |
| Local path | <code>../payment-service.git</code> or <code>/srv/git/payment-service.git</code> | Clones from an existing repository on the same machine or a mounted filesystem |

### HTTPS

Example:

~~~bash
git clone https://github.com/acme/payment-service.git
~~~

HTTPS is suitable when an organization uses browser-based login, personal access tokens, or Git Credential Manager. Many platforms no longer accept standard account passwords for Git over HTTPS; use an authentication method supported by your provider.

Do not embed tokens or passwords directly in the URL, such as <code>https://user:token@host/...</code>. URLs can appear in shell history, logs, remote configuration, or process listings. Let a credential manager or secure login mechanism handle credentials.

### SSH

Example:

~~~bash
git clone git@github.com:acme/payment-service.git
~~~

SSH requires your machine to have an appropriate key pair and for the public key to be registered on an account or server with read access to the repository. Test your SSH connection following your provider's documentation before cloning if this is your first time using it.

SSH is convenient when you fetch and push frequently because you can use an SSH agent or your OS key management mechanism. Private keys must be protected and never committed to a repository.

### Local path

If the source repository resides on the same machine or a mounted filesystem:

~~~bash
git clone ../payment-service
~~~

Relative paths are resolved from the terminal's current directory. Absolute paths can also be used. Git may optimize local clones using hardlinks when applicable; if you want to force copying objects instead of hardlinks, use the <code>--no-hardlinks</code> option.

Do not delete or move the source repository without understanding how the clone was created and where objects are stored. In a normal clone, the destination has its own object database; options such as <code>--shared</code> are a different case and can make the clone depend on the source's object database.

## 3. Authenticating before cloning

Cloning only succeeds if you have read permission for the repository and authentication is working.

For HTTPS, check:

- The URL is correct and the repository exists.
- Your account has read access.
- The credential manager or token has the appropriate permission scopes.
- The token has not expired or been revoked.

For SSH, check:

- An SSH client is available.
- The public key is registered on the correct account or server.
- The private key is loaded into the agent or discoverable by the SSH client.
- The server's host key is verified according to organizational policy.

If the repository is private and Git reports that the repository was not found, the cause may be an incorrect URL or lack of account permissions. Some providers intentionally return a generic message to avoid revealing whether a private repository exists.

## 4. Choosing the target directory

You can let Git name the directory automatically or specify a custom name.

### Letting Git create the directory automatically

~~~bash
git clone https://github.com/acme/payment-service.git
~~~

Git creates a directory based on the repository name at the end of the source path. In the example above, the directory is usually <code>payment-service</code>; the trailing <code>.git</code> suffix on the source name is typically stripped.

### Specifying a directory name

~~~bash
git clone https://github.com/acme/payment-service.git payment-local
~~~

Git creates the repository in the <code>payment-local</code> directory relative to the terminal's current directory. The local directory name does not need to match the repository name on the server.

Example in Windows PowerShell:

~~~powershell
Set-Location C:\Projects
git clone https://github.com/acme/payment-service.git payment-local
~~~

After the command, the repository is located at <code>C:\Projects\payment-local</code>.

### Cloning into the current directory

~~~bash
mkdir payment-local
cd payment-local
git clone https://github.com/acme/payment-service.git .
~~~

The dot refers to the current directory. The target directory must be empty so Git can place the cloned contents inside it. If the directory already contains files or subdirectories, Git normally refuses to clone to avoid overwriting existing data.

### Rules for choosing the target directory

| Target directory state | Typical outcome |
|---|---|
| No directory argument passed | Git automatically creates a directory based on the source name |
| Non-existent directory name passed | Git creates that directory |
| Existing empty directory passed | Git can clone into that directory |
| Existing non-empty directory passed | Git refuses to clone |
| Dot passed in an empty current directory | Git clones into the current directory |

Before cloning into an existing path, inspect its contents. Do not delete a directory just to make a clone succeed without confirming the data inside is no longer needed.

## 5. Which branch is checked out after cloning?

When you do not specify a branch, Git typically checks out the default branch advertised by the remote via its symbolic reference <code>HEAD</code>. The default branch is often named <code>main</code>, though the actual name could be <code>master</code>, <code>develop</code>, or another name configured by the project.

For example, if the remote advertises <code>refs/heads/main</code> as the default branch:

~~~bash
git clone https://github.com/acme/payment-service.git
cd payment-service
git branch --show-current
~~~

The final command typically displays <code>main</code>. If the remote sets its default branch to <code>develop</code>, Git checks out <code>develop</code> instead of assuming every repository uses <code>main</code>.

### What is Remote HEAD?

Remote HEAD is the symbolic HEAD information advertised by the remote, indicating the repository's default branch. In the clone, Git usually creates a symbolic ref:

~~~text
refs/remotes/origin/HEAD -> refs/remotes/origin/main
~~~

This reference helps Git and users identify the default branch on the remote. It is neither a local branch nor a separate commit.

You can inspect it:

~~~bash
git remote show origin
git symbolic-ref refs/remotes/origin/HEAD
~~~

If the server does not advertise a valid HEAD or HEAD points to a branch that no longer exists, the clone may download objects without automatically checking out a branch. In that case, ask the repository maintainer what the correct default branch is or explicitly specify the branch with the <code>--branch</code> option.

## 6. Selecting the initial branch with --branch

If you want to start from a specific branch, use <code>-b</code> or <code>--branch</code>:

~~~bash
git clone --branch develop https://github.com/acme/payment-service.git
~~~

Or:

~~~bash
git clone -b develop https://github.com/acme/payment-service.git
~~~

Git fetches the <code>develop</code> branch from the remote and checks it out as a local branch. The local branch is typically configured to track the corresponding remote-tracking branch, such as <code>origin/develop</code>.

Verify:

~~~bash
git branch --show-current
git branch -vv
git status -sb
~~~

In <code>git branch -vv</code>, you can see the local branch's upstream. The upstream indicates which remote branch the local branch tracks to support status, pull, and push.

### --branch does not create a new branch on the remote

The <code>--branch develop</code> option only selects an existing branch or tag from the source to check out. It does not create a new branch on the server, nor does it push any changes automatically.

If you need to create a new working branch after cloning:

~~~bash
git switch -c feature/payment-retry
~~~

This command creates a new local branch from the current commit. When you want to share the branch, push with upstream tracking:

~~~bash
git push -u origin feature/payment-retry
~~~

## 7. Cloning a tag and detached HEAD state

The <code>--branch</code> option also accepts tag names. For example:

~~~bash
git clone --branch v2.4.0 https://github.com/acme/payment-service.git
~~~

If <code>v2.4.0</code> is a tag, Git checks out the commit the tag points to in a detached HEAD state. In this state, HEAD does not point to a local branch.

Verify:

~~~bash
git status -sb
git branch --show-current
git describe --tags --exact-match
~~~

<code>git branch --show-current</code> may print no branch name because HEAD is detached. This is appropriate when you only need to read source code, run tests, or inspect a specific release version.

If you want to develop from the tag, create a new branch:

~~~bash
git switch -c hotfix/v2.4.0
~~~

The new branch starts at the tag's commit. Subsequent commits will be recorded on that branch without modifying the released tag.

## 8. Downloading only one branch with --single-branch

A repository may have many remote branches. If you only need one branch, you can use:

~~~bash
git clone --single-branch --branch release/2.x https://github.com/acme/payment-service.git
~~~

Git fetches only the history associated with the selected branch rather than downloading history for all other branches as in a normal clone. This can reduce the amount of data downloaded in repositories with many long-lived branches or extensive history.

If you run:

~~~bash
git clone --single-branch https://github.com/acme/payment-service.git
~~~

Git only fetches the default branch advertised by the remote.

When cloning this way, remote-tracking refs for other branches may not be present. If you later need another branch, you can explicitly fetch that branch:

~~~bash
git fetch origin feature/payment
git switch -c feature/payment FETCH_HEAD
~~~

Fetching a single source branch by name typically writes the fetched commit to <code>FETCH_HEAD</code>; it does not necessarily create the <code>origin/feature/payment</code> remote-tracking ref. If you want to create a remote-tracking ref for ongoing tracking, use an explicit refspec:

~~~bash
git fetch origin refs/heads/feature/payment:refs/remotes/origin/feature/payment
git switch -c feature/payment --track origin/feature/payment
~~~

Do not confuse not seeing a branch in the local list with that branch not existing on the remote.

## 9. Shallow cloning with --depth

For repositories with very long histories, you can download only a limited number of commits near the tip of the branch:

~~~bash
git clone --depth 1 https://github.com/acme/payment-service.git
~~~

<code>--depth 1</code> creates a shallow clone with history truncated to one commit layer from the tip of the fetched branch. This is useful for CI jobs that only need the current source code or test environments that do not require deep history.

When using <code>--depth</code>, Git implies <code>--single-branch</code> by default unless you specify otherwise with <code>--no-single-branch</code>. Therefore, a shallow clone typically contains the history of only a single branch.

### Limitations of shallow clones

- Some parent commits are absent from the clone.
- Commands requiring deep history such as certain merge operations, bisect, or history analysis may be limited.
- You cannot inspect the entire older history that has not been downloaded.
- Some branch sharing or integration operations require fetching additional history beforehand.

When you need to deepen the history:

~~~bash
git fetch --deepen 50
~~~

This command downloads 50 additional commit layers beyond the current shallow boundary. If you want to convert it into a full-history clone:

~~~bash
git fetch --unshallow
~~~

Only use shallow clones when you understand your work does not depend on full history. For long-term development environments, a standard clone is usually simpler.

## 10. Cloning without checking out the working tree

The <code>--no-checkout</code> (or <code>-n</code>) option instructs Git to download the repository without immediately checking out files into the working tree:

~~~bash
git clone --no-checkout https://github.com/acme/payment-service.git payment-inspect
~~~

This mode can be useful when you want to inspect refs, configuration, or prepare the index before choosing what content to check out. Afterward, you can check out the desired branch:

~~~bash
cd payment-inspect
git reset --hard HEAD
~~~

In a clone created with <code>--no-checkout</code>, HEAD is normally set to the initial branch, while the working tree and index have not yet been populated. The reset command above updates the index and working tree to match the snapshot HEAD points to. Only run this in a fresh clone without local changes you need to keep, as <code>--hard</code> overwrites the state of the index and working tree.

## 11. Bare and mirror clones: cases without a working tree

A normal clone creates a working tree for editing files. In certain administrative scenarios, you only want a Git repository without checked-out files:

~~~bash
git clone --bare https://github.com/acme/payment-service.git payment-service.git
~~~

A bare repository has no normal working tree. It is commonly used as a central repository on a server or as Git data storage.

Mirror clone:

~~~bash
git clone --mirror https://github.com/acme/payment-service.git payment-mirror.git
~~~

A mirror clone is a form of bare clone configured to mirror refs from the source more broadly than a normal clone. It is suited for mirroring or ref backup purposes, not as a daily development directory.

Be cautious when using mirror push: a mirror operation can update or delete destination refs to match the source. Do not use a mirror clone as a regular working copy.

## 12. Inspecting the repository after cloning

After cloning, enter the directory:

~~~bash
cd payment-service
~~~

Run these commands:

~~~bash
# Check remotes
git remote -v

# Check local branches and upstreams
git branch -vv

# Check both local and remote-tracking branches
git branch -a

# Check working tree status
git status

# View current commit
git log -1 --oneline --decorate
~~~

Typically you will see:

- A remote named <code>origin</code> with fetch and push URLs.
- The currently checked-out local branch, such as <code>main</code>.
- The corresponding upstream, such as <code>origin/main</code>.
- A clean working tree if no changes were made after cloning.

To view detailed information about the remote:

~~~bash
git remote show origin
~~~

This command can display URLs, the HEAD branch, tracked remote branches, and local status relative to the remote.

## 13. Renaming the default remote or choosing another name during clone

By default, Git names the remote <code>origin</code>. If you want a different name from the start, use:

~~~bash
git clone --origin upstream https://github.com/acme/payment-service.git
~~~

Or the short form:

~~~bash
git clone -o upstream https://github.com/acme/payment-service.git
~~~

This is useful when cloning a fork while wanting the original remote named <code>upstream</code>, or when a team has its own remote naming convention.

If you have already cloned and want to rename it:

~~~bash
git remote rename origin upstream
~~~

A remote name is a local alias. Renaming it does not change the repository URL on the server.

## 14. When the remote's default branch changes

Suppose a repository previously used <code>master</code> and later switched to <code>main</code>. The remote may have updated its symbolic HEAD, while older clones still retain the old remote HEAD information until refreshed.

Check:

~~~bash
git remote show origin
git symbolic-ref refs/remotes/origin/HEAD
~~~

To ask Git to re-detect the HEAD branch on the remote:

~~~bash
git remote set-head origin --auto
~~~

This command updates the symbolic ref <code>refs/remotes/origin/HEAD</code> based on remote information. It does not automatically change your current local branch. If you want to switch to the new default branch, check your working tree status and switch explicitly:

~~~bash
git fetch origin
git switch main
~~~

If the local <code>main</code> branch does not exist yet, create a tracking branch:

~~~bash
git switch --track origin/main
~~~

## 15. How does clone differ from git init and git remote add?

These two approaches serve different purposes:

| Approach | Result |
|---|---|
| <code>git clone &lt;url&gt;</code> | Retrieves an existing repository, downloads objects and refs, configures the remote, creates the initial branch, and checks out |
| <code>git init</code> | Initializes a new local repository, initially with no remote history |
| <code>git init</code> + <code>git remote add</code> + <code>git fetch</code> | Manually creates a local repository, then connects and fetches data from a remote in separate steps |

If your goal is to join an existing repository, <code>git clone</code> is usually the right choice. If you are starting a new project on your machine and plan to publish it to a server later, you typically start with <code>git init</code> and configure the remote when needed.

## 16. Common cloning errors

| Message or symptom | Possible cause | Resolution |
|---|---|---|
| Repository not found | Incorrect URL or account lacks read permission | Verify the URL and access permissions with the maintainer |
| Authentication failed | Expired token, wrong credentials, or unsupported authentication method | Refresh credentials via credential manager or use a platform-supported method |
| Permission denied (publickey) | SSH key not registered, not loaded, or wrong account | Check SSH agent, public key, and repository permissions |
| Host key verification failed | Host key mismatch or not yet verified | Verify the server fingerprint via a trusted channel and update known_hosts according to instructions |
| Destination path already exists and is not an empty directory | Target directory already contains data | Choose another path or inspect and move existing data first |
| Remote HEAD refers to nonexistent ref | Remote default branch is invalid or unconfigured | Ask the maintainer for the default branch or clone with an explicit <code>--branch</code> |
| Clone is very slow | Large repository or history, slow network, server throttling | Check network; consider shallow/single-branch if your workflow allows |
| Clone succeeds but expected branch is missing | Used <code>--single-branch</code> or a restricted refspec | Fetch the specific branch or adjust the refspec |
| Working tree has no files after clone | Possibly used <code>--no-checkout</code> or bare clone | Check clone options and check out a branch if it is a standard repository |

When reporting an error to an administrator, include the error message, the URL with sensitive information redacted, the connection method, and the timestamp. Never send tokens, passwords, or private keys.

## 17. Recommended cloning workflow for beginners

A simple workflow you can follow:

1. Open the repository page and copy the HTTPS or SSH URL recommended by your team.
2. Confirm your account or SSH key has read permission.
3. Choose the parent directory where you want to store the project.
4. Run <code>git clone</code>, specifying a target directory if you want a different name.
5. If the project requires a specific branch, use <code>--branch</code>; only use <code>--single-branch</code> or <code>--depth</code> when you understand their limitations.
6. Navigate into the new directory.
7. Verify the remote, branch, upstream, and working tree.
8. Create a separate working branch before developing features.

Example:

~~~bash
git clone --branch main https://github.com/acme/payment-service.git payment-service
cd payment-service
git remote -v
git branch -vv
git status
git switch -c feature/payment-retry
~~~

## 18. Self-check exercises

Practice with a public repository or a test repository you manage:

1. Clone via HTTPS and let Git name the directory automatically.
2. Clone the same repository into a directory with a different name.
3. Try cloning into a directory that already has files and observe why Git refuses.
4. Use <code>git branch --show-current</code> to identify the checked-out default branch.
5. Re-clone using <code>--branch</code> to select a specific branch.
6. Clone a tag and confirm the detached HEAD state; then create a new branch from the tag.
7. Use <code>--single-branch</code> and compare the list of remote-tracking refs with a normal clone.
8. Use <code>--depth 1</code>, observe the history limitation, then try <code>git fetch --unshallow</code>.
9. Use <code>--origin upstream</code> and verify the remote name with <code>git remote -v</code>.
10. Explain the roles of remote HEAD, local branch, and remote-tracking branch.

When cloning, carefully check the URL, where the copy is saved, and which branch is checked out. After a successful clone, verify the remote and upstream so you know where your local copy pulls data from and which branch it will synchronize with.
