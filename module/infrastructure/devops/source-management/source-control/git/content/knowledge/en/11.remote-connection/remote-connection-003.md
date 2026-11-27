# Distinguishing Fetch URLs from Push URLs

When working with a remote repository, Git needs to know where to pull data from and where to send data to. These two addresses are usually the same, but they do not have to be. A remote can use one address for fetching and a different address for pushing. Understanding this distinction helps you configure the right collaboration workflow, especially when a project uses separate read servers, write servers, or fork-based workflows.

In Git, names such as `origin` or `upstream` are the names of local remote configurations. Inside that configuration, `url` specifies the address for fetching data; `pushurl` can specify a separate address for sending data. If `pushurl` is not configured, Git uses `url` as the default push address.

## 1. Remote Is a Configuration Name, URL Is a Connection Address

When cloning a repository, Git usually creates a remote named `origin`. For example:

```bash
git clone https://git.example.com/team/app.git
cd app
git remote -v
```

`origin` is not the server address. It is a short name that Git uses to look up the connection settings saved in the local repository. You can choose another name when adding a remote:

```bash
git remote add upstream https://git.example.com/team/app.git
```

A remote can have the following key settings:

| Setting | Meaning |
|---|---|
| `remote.<name>.url` | The remote address used when fetching; also the default push address if `pushurl` is not set. |
| `remote.<name>.pushurl` | A separate address used when pushing. Multiple values can be configured; Git will push to all of those addresses. |
| `remote.<name>.fetch` | RefSpec defining which refs on the remote are fetched and which local refs they map to, usually remote-tracking branches. |

For example, for a remote named `origin`, the corresponding configuration keys are `remote.origin.url`, `remote.origin.pushurl`, and `remote.origin.fetch`.

## 2. Fetch and Push Perform Two Different Directions of Work

**Fetch** retrieves commits, trees, blobs, and ref information from the remote repository into the local repository. Git connects to the remote's `url`. After receiving the data, Git updates local refs according to the configured refspec, typically remote-tracking branches such as `origin/main`.

Fetch does not automatically merge changes into the current local branch and normally does not modify the working tree. For example:

```bash
# Retrieve new information and objects from remote origin
git fetch origin

# View remote-tracking branches after fetching
git branch -r

# Compare the local main branch with the fetched state of origin/main
git log --oneline main..origin/main
```

**Push** sends the required objects from the local repository to the remote repository and requests updating refs on the remote side. Git uses `pushurl` if the remote has this key configured; otherwise, Git uses `url`.

```bash
# Send the local main branch to the main branch on origin
git push origin main
```

In the example above, `origin` identifies the remote configuration, and `main` identifies the ref being pushed under this command syntax. The server may reject the update if the user lacks permissions, the branch is protected, or the update does not satisfy fast-forward rules.

`git pull` combines fetching with integrating changes into the current branch. The integration step may use merge or rebase depending on options and configuration. Therefore, when a remote has separate fetch and push addresses, `git pull` pulls data from the fetch address, whereas `git push` sends data to the push address.

## 3. When Are the Two Addresses the Same or Different?

In typical cases, the same server handles both read and write operations. In that case, only `url` needs to be configured:

```ini
[remote "origin"]
    url = https://git.example.com/team/app.git
    fetch = +refs/heads/*:refs/remotes/origin/*
```

Since there is no `pushurl`, Git uses `https://git.example.com/team/app.git` for both fetch and push.

Another system may provide separate read and write addresses. For example, a development team fetches from a read-only HTTPS server and pushes over SSH to a writable server:

```ini
[remote "origin"]
    url = https://read.git.example.com/team/app.git
    pushurl = git@write.git.example.com:team/app.git
    fetch = +refs/heads/*:refs/remotes/origin/*
```

In that case:

- `git fetch origin` connects to `https://read.git.example.com/team/app.git`.
- `git pull origin main` fetches from the read address before integrating changes.
- `git push origin main` connects to `git@write.git.example.com:team/app.git`.

Different addresses can serve multiple purposes: using HTTPS for reads but SSH for writes, fetching from a closer mirror server, or pushing changes to a fork repository while still pulling data from the original repository.

## 4. Checking the Effective Fetch and Push Addresses

The most useful command for quickly checking the configuration is:

```bash
git remote -v
```

Sample output when the two addresses differ:

```text
origin  https://read.git.example.com/team/app.git (fetch)
origin  git@write.git.example.com:team/app.git (push)
```

The `(fetch)` and `(push)` labels indicate which operation each address is used for. If the two addresses are the same, Git can still display two lines with the same URL.

You can also query each address individually:

```bash
# Fetch address
git remote get-url origin

# Effective push address
git remote get-url --push origin

# Display all URLs configured for the respective purpose
git remote get-url --all origin
git remote get-url --push --all origin
```

To inspect values stored in the configuration:

```bash
# View URL values used for fetch
git config --get-all remote.origin.url

# View pushurl values; may return nothing if not configured
git config --get-all remote.origin.pushurl
```

`git remote get-url` can expand URL shorthand rules such as `url.<base>.insteadOf`. Therefore, the output of this command is useful when you want to know the actual address Git uses after applying rewrite rules.

## 5. Configuring Separate Fetch and Push Addresses

### Changing the Fetch Address

Use `git remote set-url`:

```bash
git remote set-url origin https://read.git.example.com/team/app.git
```

This command updates `remote.origin.url`. If the remote does not have a `pushurl` yet, the new address also becomes the default push address. If `pushurl` was already configured separately, that separate push address remains unchanged.

### Setting or Changing the Push Address

Add the `--push` option to update the push address:

```bash
git remote set-url --push origin git@write.git.example.com:team/app.git
```

From that point on, `git fetch origin` continues using the fetch URL, while `git push origin ...` uses the newly configured push URL.

### Creating a Remote and Configuring Both Addresses

You can do this step by step:

```bash
# Create the remote with the fetch address
git remote add origin https://read.git.example.com/team/app.git

# Configure a separate push address
git remote set-url --push origin git@write.git.example.com:team/app.git

# Verify both addresses again
git remote -v
```

If you want to remove the separate push address and return to sharing a single URL, unset the `pushurl` configuration:

```bash
git config --unset-all remote.origin.pushurl
```

After removal, pushes will use `remote.origin.url`. If there are multiple `pushurl` values, `--unset-all` removes all of them.

## 6. Practical Example: Fetch from the Original Repository, Push to a Fork

In a fork workflow, developers usually have write permissions on their own fork repository but read-only access to the project's original repository. Suppose the local repository does not yet have the two remotes `origin` and `upstream`; if `origin` already exists, update its URL with `git remote set-url` instead of adding it again. You can configure two separate remotes:

```bash
# origin is the fork where you have push permissions
git remote add origin git@github.com:my-account/project.git

# upstream is the original repository for receiving new changes
git remote add upstream https://github.com/original-owner/project.git

# Fetch new branches from the original repository
git fetch upstream

# Create a working branch from the updated main branch
git switch -c feature/search upstream/main

# After finishing and committing, push the branch to your fork
git push -u origin feature/search
```

In this setup, `origin` and `upstream` are two different remotes. `origin` points to the fork; `upstream` points to the original repository. You fetch from `upstream` and push your branch to `origin`.

An alternative configuration is to keep a single remote name while setting the fetch URL to the original repository and the push URL to the fork. This example uses a separate local repository; if `origin` already exists in the current repository, use `git remote set-url origin ...` to change the fetch URL instead of running `git remote add`:

```bash
# Create the remote with a read URL from the original repository
git remote add origin https://github.com/original-owner/project.git

# Specify the fork as the push address
git remote set-url --push origin git@github.com:my-account/project.git

# Verify connection directions
git remote -v
```

With the second configuration, `git fetch origin` pulls changes from the original repository, while `git push origin feature/search` pushes the branch to the fork. This approach is convenient when you want one remote name to represent both endpoints, but you need to inspect `git remote -v` carefully to avoid sending changes to the wrong place.

## 7. Distinguishing Remote Addresses from Target Branches

The fetch/push address only determines where Git connects. It does not automatically decide which branch is fetched or updated. Ref selection is governed by refspecs, upstream branches, and push options.

For example, the default fetch configuration typically looks like:

```ini
fetch = +refs/heads/*:refs/remotes/origin/*
```

This is a refspec: it takes branches on the remote and maps them into remote-tracking branches under `refs/remotes/origin/`. It is not a URL and does not change the server being connected to.

The following commands clearly illustrate the separation:

```bash
# Choose the remote to fetch from
git fetch origin

# Choose the remote and local/remote branch to push
git push origin feature/search:feature/search

# View the upstream branch of the current branch
git branch -vv
```

When calling `git push` without specifying a remote name, Git can infer the target remote from settings such as `branch.<name>.pushRemote`, `remote.pushDefault`, or the upstream branch. `push.default` affects how the ref to push is chosen. These settings determine the default remote or branch; once the remote is selected, `pushurl` still determines the connection address used for pushing.

## 8. Diagnosing When Fetch Succeeds but Push Fails

A successful fetch does not prove that a push will succeed. The two operations may use different URLs, protocols, credentials, or access permissions.

When encountering an error, check in this order:

1. **Confirm the selected remote:** check the remote name specified in the push command. If no remote name is given, check default settings with `git branch -vv` and the keys `branch.<name>.pushRemote`, `remote.pushDefault`; `git remote -v` helps cross-check each remote's URLs.
2. **Confirm the effective push address:** run `git remote get-url --push origin`, replacing `origin` with the actual remote.
3. **Check configuration:** use `git config --get-all remote.origin.url` and `git config --get-all remote.origin.pushurl` to spot stale URLs or multiple addresses.
4. **Check authentication:** for HTTPS, confirm valid credentials; for SSH, confirm the SSH key and account have repository access.
5. **Check permissions and branch rules:** the account may have read access without write permissions, or the target branch may be protected.
6. **Check history:** if the remote has new commits that local has not integrated, the server may reject a non-fast-forward push. Fetch and integrate changes according to your team's workflow before pushing again.

Do not assume you need to change the URL simply because a push is rejected. First determine whether the error comes from the address, authentication, write permissions, or the commit history relationship between the two branches.

## 9. Self-Check

1. **If a remote has `url` configured but no `pushurl`, which address does Git use when pushing?**
   - It uses `remote.<name>.url` as the default push address.
2. **When `pushurl` is configured, where does `git fetch origin` connect?**
   - It connects to `remote.origin.url`; `pushurl` is only for pushing.
3. **Which command displays only the effective push address?**
   - `git remote get-url --push origin`.
4. **Is `remote.origin.fetch` a server address?**
   - No. It is a refspec mapping refs from the remote into local.
5. **Why can fetch succeed while push still fails?**
   - Because push may use a different address or protocol, require different credentials, lack write permissions, or be rejected due to branch update rules.

## Conclusion

`remote.<name>.url` specifies the fetch address and also serves as the default push address. `remote.<name>.pushurl` allows specifying a separate push destination. Use `git remote -v` and `git remote get-url --push` to verify connection directions, `git remote set-url` to change the fetch URL, and `git remote set-url --push` to configure the push URL. When operating Git in a team, always distinguish where history is pulled from, where commits are sent, and which refs each command updates.
