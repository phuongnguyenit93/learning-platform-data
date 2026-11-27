# Changing Remote URLs When Migrating Repositories

When a repository moves to another server, is renamed on the hosting platform, or switches from HTTPS to SSH, the Git copy on your development machine still keeps the old remote address. If you continue using that address, fetch, pull, or push operations may fail, or accidentally connect to the old repository. You can update the remote address directly in the current repository while preserving your working tree, commits, branches, and local history.

This lesson belongs to the **Remote Connection** chapter of the **SOURCE_CONTROL_GIT** module. The module teaches Git from the working tree, staging area, commits, and history to branches, merging, rebasing, remotes, and tags; it also builds skills in collaborating through branches, resolving conflicts, tracing changes, and recovering from mistakes while preserving critical history. Managing remote URLs properly ensures collaboration operations continue pointing to the repository your team is actively using.

## 1. What Is a Remote and Where Is the Remote Address Stored?

A remote is a shorthand name Git uses to reference another repository. When cloning a repository, Git usually creates a remote named <code>origin</code> pointing to the cloned source address. The name <code>origin</code> is a common convention, not a mandatory name or special keyword. A project can have multiple remotes, such as <code>origin</code> pointing to the team's primary repository and <code>upstream</code> pointing to the original repository from which the project was forked.

Remote addresses can use multiple protocols:

~~~text
# HTTPS
https://github.com/acme/payment-service.git

# SCP-like SSH
git@github.com:acme/payment-service.git

# Full URI SSH
ssh://git@git.example.com:2222/platform/payment-service.git
~~~

Git stores remote configuration in the repository's local config file, usually <code>.git/config</code>. Therefore, changing a remote URL with a Git command only updates the configuration of the local copy you are working in. Each team member has their own clone and must update the URL in their clone when the official address changes.

A remote typically has two kinds of addresses to pay attention to:

- **Fetch URL:** the address Git uses to retrieve data from the remote during fetch or pull.
- **Push URL:** the address Git uses when pushing commits to the remote. If not configured separately, the push URL defaults to the same address as the fetch URL.

A single remote can display two different URLs. Thus, checking only one address line is insufficient if the team configures separate read and write locations.

## 2. When Do You Need to Change the URL?

Common situations:

| Situation | Example Change |
|---|---|
| Repository moved to a new organization or group | <code>acme/app.git</code> becomes <code>platform/app.git</code> |
| Repository renamed | <code>old-service.git</code> becomes <code>service-api.git</code> |
| Team switches Git providers | Moving from GitHub to GitLab or an internal Git server |
| Server changes domain name or SSH port | <code>git.old.example.com</code> becomes <code>git.example.com:2222</code> |
| Authentication method changes | Switching from HTTPS to SSH or vice versa |

Verify the exact target repository before editing configuration. A new address may look similar to the old one yet belong to a different repository, such as a personal repository instead of the organization's repository. If the repository was copied to a new server, confirm the target repository received all commits, branches, tags, and supplemental data used by the project.

**Changing the URL only changes where Git connects.** This command does not migrate data, copy commits to the new server, modify working tree contents, or delete the old repository.

## 3. Checking Current Configuration Before Modifying

Before updating, identify the remote name and both fetch/push URLs:

~~~bash
# List remotes along with fetch URL and push URL
git remote -v

# List remote names
git remote

# View the fetch URL of origin
git remote get-url origin

# View the push URL of origin
git remote get-url --push origin

# View all URLs if the remote has multiple URLs configured
git remote get-url --all origin
git remote get-url --push --all origin
~~~

Sample output:

~~~text
origin  https://github.com/acme/payment-service.git (fetch)
origin  https://github.com/acme/payment-service.git (push)
upstream https://github.com/example/payment-service.git (fetch)
upstream https://github.com/example/payment-service.git (push)
~~~

The output shows the repository currently has two remotes. If your team only migrated the organization's repository, you may only need to update <code>origin</code>; <code>upstream</code> might still point to the original repository. Do not blindly replace every URL.

You should also check the current branch and tracking links:

~~~bash
git status
git branch -vv
git branch --show-current
~~~

<code>git branch -vv</code> displays local branches and the remote-tracking branches they track, for example <code>main</code> tracking <code>origin/main</code>. This helps verify that upstream links remain valid after changing the URL.

If the working tree has uncommitted changes, understand that state before continuing with other integration operations. Changing a remote URL does not require deleting or stashing local changes; however, it is always good practice to check status to avoid confusing connection errors with existing project edits.

## 4. Updating the Address with git remote set-url

Standard command to change a remote's fetch URL:

~~~bash
git remote set-url origin https://git.example.com/platform/payment-service.git
~~~

In this example:

- <code>origin</code> is the remote name to update.
- The address at the end of the command is the new target repository URL.

If the project switches from HTTPS to SSH:

~~~bash
git remote set-url origin git@git.example.com:platform/payment-service.git
~~~

If the SSH server uses a non-default port, you can use the full URI form:

~~~bash
git remote set-url origin ssh://git@git.example.com:2222/platform/payment-service.git
~~~

After running the command, verify again:

~~~bash
git remote -v
git remote get-url origin
~~~

<code>git remote set-url</code> updates the URL for the specified remote name. Because the remote name remains <code>origin</code>, upstream configurations referencing this remote name usually stay intact. You do not need to delete and recreate the remote simply because the repository address changed.

### Updating a Separate Push URL

In some teams, fetch and push use two different addresses. For instance, a team reads via HTTPS but pushes via SSH. In that case, update the push URL separately using the <code>--push</code> option:

~~~bash
# Update fetch URL
git remote set-url origin https://git.example.com/platform/payment-service.git

# Update separate push URL
git remote set-url --push origin git@git.example.com:platform/payment-service.git
~~~

Verify both directions:

~~~bash
git remote get-url origin
git remote get-url --push origin
git remote -v
~~~

If the remote already has a separate push URL, updating the fetch URL does not automatically change that separate push URL. Inspect both the <code>(fetch)</code> and <code>(push)</code> lines in <code>git remote -v</code> to ensure pushes no longer point to the old server.

### Replacing a Specific URL When a Remote Has Multiple URLs

Git allows a remote to have multiple URLs for specialized configurations. Before editing this kind of setup, view all URLs with <code>git remote get-url --all &lt;remote-name&gt;</code> and <code>git remote get-url --push --all &lt;remote-name&gt;</code>.

You can specify the old URL to replace the exact target:

~~~bash
git remote set-url origin https://git.example.com/platform/payment-service.git https://old.example.com/acme/payment-service.git
~~~

The <code>--add</code> and <code>--delete</code> options of <code>git remote set-url</code> are used to add or remove URLs in multi-address configurations. Use them only when you genuinely want to maintain multiple endpoints; for a standard repository migration, one clear fetch URL and one clear push URL are usually easier to manage.

## 5. Verifying Connectivity After Changing the Address

Having <code>set-url</code> succeed only means the local configuration was updated. It does not prove the new address exists, that you have access permissions, or that the target repository contains the right data. Verify step by step.

### Step 1: Check the Saved URLs

~~~bash
git remote -v
git remote get-url origin
git remote get-url --push origin
~~~

Compare the hostname, organization, repository name, protocol, and port (if any) against the migration details confirmed by your team.

### Step 2: Check Whether the Remote Responds

~~~bash
git ls-remote origin
~~~

<code>git ls-remote</code> queries the references advertised by the remote without modifying the working tree or creating local commits. If the command returns hash lines and reference names such as <code>refs/heads/main</code> or <code>refs/tags/v1.0.0</code>, Git has contacted the repository and read the ref list.

You can check the default branch advertised by the server:

~~~bash
git ls-remote --symref origin HEAD
~~~

If the command fails, classify the cause:

- **Repository not found or wrong URL:** double-check path, organization name, repository name, and port.
- **Permission denied or HTTP 403:** verify account, membership permissions, token, or SSH key.
- **Could not resolve host / timeout:** check DNS, internal network, VPN, proxy, or server status.
- **Host key verification failed:** verify the SSH host fingerprint using trusted guidance from the provider or administrator before accepting the host key.
- **Authentication failed:** check credential manager, expired token, or SSH agent and loaded keys.

Do not put passwords or access tokens directly into the URL and save them in repository configuration. URLs can appear in configuration files, command logs, backups, or screenshots. Use Git's credential manager or SSH keys according to your organization's policy.

### Step 3: Fetch and Check Remote Branches

After <code>ls-remote</code> works and you confirm this is the right repository:

~~~bash
git fetch origin
git branch -r
git branch -vv
~~~

<code>git fetch origin</code> downloads objects and updates remote-tracking refs according to the remote's fetch configuration. This command does not automatically merge changes into local branches and does not overwrite edits in the working tree.

If the new repository is missing branches or tags that the old repository had, stop and confirm whether the migration has finished. Do not rush to push local data to an unverified target repository.

## 6. What Is Preserved After Changing the URL?

If you only change the URL of the remote named <code>origin</code>, most of the local structure remains unchanged:

| Component | Effect of <code>git remote set-url origin ...</code> |
|---|---|
| Working tree | Unchanged |
| Index / staging area | Unchanged |
| Local commits and history | Unchanged |
| Local branch names | Unchanged |
| Remote name <code>origin</code> | Unchanged |
| Upstream links such as <code>origin/main</code> | Usually preserved because the remote name did not change |
| Fetch/push URL of <code>origin</code> | The specified URL is updated |
| Repository on the server | Not automatically changed or copied |

This is why changing the URL is usually the right approach when the same repository moves to a new address while keeping its branch structure and history.

### When the Default Branch or Branch Names Changed

Sometimes a migration is accompanied by a default branch rename, such as <code>master</code> becoming <code>main</code>. Changing the URL does not automatically rename local branches or upstreams. After fetching, inspect:

~~~bash
git branch -r
git branch -vv
git ls-remote --symref origin HEAD
~~~

If the local <code>main</code> branch needs to track <code>origin/main</code>, configure it explicitly:

~~~bash
git branch --set-upstream-to=origin/main main
~~~

Replace <code>main</code> with the actual local branch name. Only do this when the remote actually has the target branch and you want the local branch to track it. If the team still uses a different branch name, do not change the upstream by guessing.

## 7. Complete Example: Moving origin to a New Server

Suppose the old repository was:

~~~text
https://github.com/acme/inventory-api.git
~~~

The team moved the repository to:

~~~text
https://git.example.com/platform/inventory-api.git
~~~

Steps to perform in an existing clone:

~~~bash
# 1. Inspect current local and remote status
git status
git remote -v
git branch -vv

# 2. Update the origin address
git remote set-url origin https://git.example.com/platform/inventory-api.git

# 3. Confirm fetch and push configuration
git remote -v

# 4. Check server reachability and read access
git ls-remote origin

# 5. Fetch updated references locally
git fetch origin

# 6. Check branches and upstreams
git branch -r
git branch -vv

# 7. Check working tree status
git status
~~~

If the team uses SSH, step 2 can use:

~~~bash
git remote set-url origin git@git.example.com:platform/inventory-api.git
~~~

If you need to confirm a push can succeed without sending updates yet:

~~~bash
git push --dry-run origin HEAD
~~~

<code>--dry-run</code> tells Git to perform checks for the push operation without sending actual ref updates. It helps uncover some connectivity or write-permission issues, but does not replace verifying branch protection policies and team review workflows.

Once the target repository is fully verified and you genuinely need to push the current branch there, specify the remote and branch explicitly:

~~~bash
git push -u origin main
~~~

The command above pushes the local <code>main</code> branch to <code>origin</code> and sets the upstream for future pushes/pulls. Replace <code>main</code> with a branch your team permits updating. Do not run <code>git push --mirror</code> as a test step: the mirror option can update or delete refs on the target server to mirror local state, causing wide impact on a shared repository.

## 8. Changing URL, Renaming a Remote, and Adding a New Remote Are Three Different Tasks

Three operations are frequently confused:

| Goal | Command | Result |
|---|---|---|
| Same remote name, repository address changed | <code>git remote set-url origin &lt;new-url&gt;</code> | <code>origin</code> stays <code>origin</code>, URL is updated |
| Keep URL but rename the remote | <code>git remote rename origin upstream</code> | Remote is renamed; related ref configuration is updated by Git |
| Keep old remote and declare an additional repository | <code>git remote add new-origin &lt;new-url&gt;</code> | Creates a new remote named <code>new-origin</code> |

If you want to inspect the new repository alongside the old one during a transition period, adding a new remote can be useful:

~~~bash
git remote add new-origin https://git.example.com/platform/inventory-api.git
git remote -v
git ls-remote new-origin
git fetch new-origin
~~~

Once the team confirms the new repository is the primary target, you can update <code>origin</code> according to project conventions. Do not rename a remote just because the URL changed; renaming can break how commands and internal documentation refer to the remote.

## 9. Additional Cases to Check

### Repositories with Submodules

Submodules have their own URL configurations in the <code>.gitmodules</code> file. Changing the parent repository's remote URL does not automatically change child repository URLs. If submodule addresses also moved, update the corresponding URLs in <code>.gitmodules</code>, commit that change following project workflow, and synchronize local configuration:

~~~bash
git submodule sync --recursive
git submodule update --init --recursive
~~~

If only the parent repository address changed and submodule URLs remain valid, no submodule changes are needed.

### Repositories Using Git LFS

Git LFS stores large file contents in a separate LFS storage system alongside regular Git objects. When moving servers, confirm the provider migrated both LFS objects and endpoint configuration. A successful <code>git fetch</code> does not prove all LFS data is present on the new server.

For server migrations handled by an admin team, check the provider's migration documentation and confirm LFS files can be downloaded from the new remote before retiring the old server.

### URLs Rewritten by Git Configuration

Git supports <code>url.*.insteadOf</code> rules to automatically rewrite URLs. If <code>git remote get-url</code> displays an address different from the configured string, inspect rewrite rules in Git configuration:

~~~bash
git config --get-regexp '^url\..*\.insteadof$'
~~~

Rules may reside in local, global, or system configuration. Only modify a rule after determining its scope and impact on other repositories.

## 10. Common Errors and Troubleshooting

| Symptom | Possible Cause | How to Check |
|---|---|---|
| <code>git fetch</code> still accesses old server | Fetch URL not updated or URL rewrite rule active | <code>git remote -v</code>, <code>git remote get-url origin</code> |
| <code>git push</code> still goes to old server | Separate push URL still holds old address | <code>git remote get-url --push origin</code> |
| <code>Repository not found</code> | Wrong path or account lacks permission to view repository | Cross-check official URL and access permissions |
| <code>Permission denied (publickey)</code> | SSH key not loaded, not registered, or lacks permission | Check SSH agent, keys, and server permissions |
| Fetch succeeds but push is rejected | Read-only access, branch protection, or different push URL | Check push URL and repository policies |
| Local branch reports no upstream | New branch has no tracking set or upstream was renamed | <code>git branch -vv</code>, then configure the correct upstream |
| Old branches missing on new remote | Migration did not transfer all branches or branches were renamed | <code>git ls-remote --heads origin</code> and confirm with team |

Do not remove and re-add a remote just to try fixing authentication errors. First check fetch/push URLs, access permissions, and authentication configuration; removing a remote can lose custom fetch settings and related remote metadata in the local repository.

## 11. Pre-Completion Checklist for Migration

Before considering the remote address migration complete on your local machine, confirm:

- The new URL matches the official repository provided by your team.
- Both fetch URL and push URL point to the intended destination.
- <code>git ls-remote</code> can read refs from the new server.
- <code>git fetch</code> completes and expected remote-tracking branches appear.
- Local branches still track the right upstreams; if the default branch name changed, it has been verified and explicitly reconfigured.
- Push permissions, branch protection, submodules, and Git LFS have been verified as required by the project.
- Other team members know the canonical URL to update their clones.

Updating the URL is only part of a team-wide migration. The target repository needs the right data and access permissions; team members' local clones also need to point to the new address.

## 12. Self-Check Exercises

Practice in a test or personal repository:

1. Run <code>git remote -v</code>. How many remotes exist and what fetch/push URLs does each have?
2. Run <code>git branch -vv</code>. Which remote-tracking branch is the current branch tracking?
3. Replace <code>origin</code>'s URL with a valid test repository address. Run <code>git remote -v</code> again to confirm.
4. Run <code>git ls-remote origin</code>. Does this command alter the working tree or only query references from the remote?
5. Set a separate push URL, then explain why fetch and push can display two different addresses.
6. Explain why changing <code>origin</code>'s URL usually preserves the <code>origin/main</code> upstream.
7. If a repository has submodules, identify where submodule URLs are stored and why changing the parent remote URL alone is not enough.

You have mastered this operation when you can accurately identify the right remote, intentionally change fetch/push URLs, verify connectivity, and confirm local branches still track the intended repository. Making a habit of checking before and after changing addresses helps prevent pushing commits to the wrong server during a team repository migration.
