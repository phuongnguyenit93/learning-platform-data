# Listing Remote References with git ls-remote

When working with a repository hosted on a Git server, sometimes you only need to know which branches or tags exist on the remote, what the repository's default branch is, or whether a specific branch has been pushed yet. You may need that information before deciding to fetch, checkout, or integrate changes.

Git provides the `git ls-remote` command to query a remote repository for the references (*refs*) it is advertising. This command returns object IDs and reference names, allowing you to inspect branches, tags, and `HEAD` on the remote. It is a lookup operation: it does not download commit history, does not update remote-tracking branches on your machine, and does not modify the working tree.

## 1. What Are Remote References?

In Git, a reference (often abbreviated as *ref*) is a human-readable name pointing to a Git object, typically a commit. Some common refs:

| Ref Format | Example | Meaning |
|---|---|---|
| `refs/heads/` | `refs/heads/main` | A branch stored in that repository |
| `refs/tags/` | `refs/tags/v1.2.0` | A tag marking a milestone in history |
| `HEAD` | `HEAD` | The default location advertised by the repository; on a server it usually points symbolically to the default branch |

A branch on the remote and a remote-tracking branch on your machine are two different concepts. For example:

- `refs/heads/main` is the `main` branch in the remote repository.
- `refs/remotes/origin/main` is a locally stored remote-tracking branch reflecting the most recent sync from the `origin` remote.

The name `origin` is just the default remote name Git usually assigns when cloning. A repository can use another name or have multiple remotes at the same time.

## 2. Basic Syntax of git ls-remote

General syntax:

```bash
git ls-remote [<options>] <repository> [<patterns>...]
```

`<repository>` can be a configured remote name, such as `origin`, or a repository URL. If `<patterns>` is omitted, Git lists the refs advertised by the remote after applying any optional filters.

To view the basic list of refs:

```bash
git ls-remote origin
```

Sample output:

```text
7c9a1f2b3d4e5f60718293a4b5c6d7e8f9012345    HEAD
7c9a1f2b3d4e5f60718293a4b5c6d7e8f9012345    refs/heads/main
19ab2c3d4e5f60718293a4b5c6d7e8f901234567    refs/heads/feature/login
4d5e6f708192a3b4c5d6e7f8091a2b3c4d5e6f70    refs/tags/v1.0.0
8a9b0c1d2e3f405162738495a6b7c8d9e0f12345    refs/tags/v2.0.0
6b7c8d9e0f1234567890a1b2c3d4e5f60718293a    refs/tags/v2.0.0^{}
```

Each line typically has two columns separated by a tab:

1. **Object ID:** the identifier of the Git object that the ref points to. The ID length depends on the repository's hash format.
2. **Ref name:** the reference name, such as `HEAD`, `refs/heads/main`, or `refs/tags/v1.0.0`.

In the example, `HEAD` and `refs/heads/main` have the same object ID, indicating that the remote's `HEAD` points to the `main` branch. The `refs/tags/v2.0.0^{}` line is the peeled line of an annotated tag, showing the target object that the tag points to after dereferencing the tag object.

The hashes in the example are solely for illustrating the format; when run in practice, the object IDs are returned by the repository.

## 3. Listing Only Remote Branches or Tags

### Viewing Branches Only

Use `--heads` to filter refs under `refs/heads/`:

```bash
git ls-remote --heads origin
```

Example:

```text
7c9a1f2b3d4e5f60718293a4b5c6d7e8f9012345    refs/heads/main
19ab2c3d4e5f60718293a4b5c6d7e8f901234567    refs/heads/feature/login
2abc3d4e5f60718293a4b5c6d7e8f90123456789    refs/heads/release/1.x
```

This command is useful when you need to see which branches exist on the remote without mixing in tags or `HEAD`.

### Viewing Tags Only

Use `--tags` to filter refs under `refs/tags/`:

```bash
git ls-remote --tags origin
```

Example:

```text
4d5e6f708192a3b4c5d6e7f8091a2b3c4d5e6f70    refs/tags/v1.0.0
8a9b0c1d2e3f405162738495a6b7c8d9e0f12345    refs/tags/v2.0.0
6b7c8d9e0f1234567890a1b2c3d4e5f60718293a    refs/tags/v2.0.0^{}
```

Git has two common types of tags:

- **Lightweight tag:** a ref pointing directly to the tagged object, usually a commit. Output has one line for the tag.
- **Annotated tag:** a ref pointing to a tag object containing metadata such as creator, creation date, and message. Git may print an extra line with the `^{}` suffix representing the target object after dereferencing the tag object.

Therefore, for annotated tags, do not assume the hash on the `refs/tags/<tag>` line is the commit hash. If you want the output to exclude peeled lines and pseudorefs like `HEAD`, use `--refs`:

```bash
git ls-remote --tags --refs origin
```

### Combining Filters

You can combine `--heads` and `--tags` to view only branches and tags:

```bash
git ls-remote --heads --tags origin
```

`--refs` can be added when you only want real refs in those two groups without peeled lines or pseudorefs:

```bash
git ls-remote --heads --tags --refs origin
```

## 4. Finding a Branch or Group of Refs by Pattern

After the repository name, you can pass one or more patterns to filter ref names. Git interprets patterns as globs. For clarity and to avoid ambiguity, use full ref names starting with `refs/heads/` or `refs/tags/`.

Check a specific branch:

```bash
git ls-remote --heads origin "refs/heads/feature/login"
```

List branches in the `release` group:

```bash
git ls-remote --heads origin "refs/heads/release/*"
```

Find version tags starting with `v2.`:

```bash
git ls-remote --tags origin "refs/tags/v2.*"
```

Wrap the pattern in quotes so the shell does not expand the `*` character before passing the argument to Git. Patterns only filter the query output; they do not create branches, download refs, or change remote configuration.

If you need to check accurately whether a branch exists in a script, combine with `--exit-code`:

```bash
git ls-remote --exit-code --heads origin "refs/heads/feature/login"
```

When a matching ref exists, Git prints the corresponding line and returns exit code `0`. If the connection succeeds but no ref matches, Git returns exit code `2`. Authentication, DNS, or connection failures are distinct errors and must also be handled; do not treat every non-`0` exit code as meaning the branch does not exist.

Shell usage example:

```bash
if git ls-remote --exit-code --heads origin "refs/heads/feature/login"; then
    echo "Branch exists on remote"
else
    result=$?
    if [ "$result" -eq 2 ]; then
        echo "Branch does not exist on remote"
    else
        echo "Could not query remote (exit code: $result)"
        exit "$result"
    fi
fi
```

## 5. Identifying HEAD and the Remote's Default Branch

`HEAD` is a special reference indicating the default position advertised by the repository. When cloning, Git usually uses this information to choose the initial branch. You can inspect the object ID of `HEAD` with:

```bash
git ls-remote origin HEAD
```

To ask the server to provide symbolic ref details as well, use `--symref`:

```bash
git ls-remote --symref origin HEAD
```

Example:

```text
ref: refs/heads/main    HEAD
7c9a1f2b3d4e5f60718293a4b5c6d7e8f9012345    HEAD
```

The line starting with `ref:` shows that `HEAD` points symbolically to `refs/heads/main`; the next line is the object ID that `HEAD` resolves to. Symbolic ref details depend on whether the remote server advertises that information. If you only see the object ID line, you still know the target commit, though you may not be able to infer the default branch name from that output alone.

## 6. Checking Remotes Before Querying

To view the remotes configured in the current repository:

```bash
git remote -v
```

Example:

```text
origin  https://example.com/team/sample-project.git (fetch)
origin  https://example.com/team/sample-project.git (push)
upstream https://example.com/org/sample-project.git (fetch)
upstream https://example.com/org/sample-project.git (push)
```

You can query each remote by name:

```bash
git ls-remote origin
git ls-remote upstream
```

Or query a URL directly:

```bash
git ls-remote https://example.com/team/sample-project.git
```

If you want to view the URL after Git applies `url.*.insteadOf` settings, use `--get-url`:

```bash
git ls-remote --get-url origin
```

This option only prints the expanded URL without connecting to the server to list refs. For private repositories, Git requires valid authentication via SSH agent, a credential helper, or a configured login mechanism. Never embed access tokens or passwords directly in URLs or commands stored in terminal history.

## 7. Distinguishing git ls-remote from Other Ref-Viewing Commands

The following commands can all display branch or tag names, but they read data from different places and points in time:

| Command | Data Source | Updates Local Repository? |
|---|---|---|
| `git ls-remote origin` | Refs advertised by the remote at query time | No |
| `git branch -r` | Locally stored remote-tracking branches | No |
| `git show-ref` | Refs currently present in the local repository | No |
| `git fetch origin` | Data downloaded from the remote per refspec | Can update remote-tracking refs and download objects |

For example, `git branch -r` may still display `origin/feature/login` even after that branch was deleted on the server, if the latest fetch has not pruned local refs. In contrast, `git ls-remote --heads origin` reflects the branches the server is advertising at the moment the command is run.

If you only want to check which branches or tags exist on the remote, use `git ls-remote`. If you want to download commits and update local data for further work, use `git fetch`:

```bash
# Look up remote branches without updating local refs.
git ls-remote --heads origin

# Download data and update remote-tracking refs per fetch configuration.
git fetch origin

# View remote-tracking branches after fetching.
git branch -r
```

`git ls-remote` does not replace `git fetch`: it only provides the list of refs and object IDs advertised by the remote, without downloading commit contents or directory trees for you to checkout or inspect files.

## 8. Practical Notes for Daily Work

- **Check the right remote:** a project may have `origin` pointing to your personal fork and `upstream` pointing to the original repository. Run `git remote -v` before concluding whether a branch exists or not.
- **Distinguish remote refs from local refs:** `refs/heads/main` in the output is a branch on the server; `refs/remotes/origin/main` is the local tracking reference.
- **Use `--heads` or `--tags` when you need a clear list:** filtering reduces noise from other refs.
- **Use `--exit-code` when checking existence:** distinguish the case where a ref is not found (exit code `2`) from connection or authentication errors.
- **Watch out for annotated tags:** output may contain both the tag object and a peeled line ending in `^{}`.
- **Do not treat the output as static data:** the remote can change immediately after your query if someone else pushes or deletes branches/tags.
- **Do not put secrets into commands:** use a credential helper or SSH agent to authenticate safely.

## 9. Quick Lookup Workflow

When you need to check a remote's ref status in day-to-day work, you can follow this sequence:

1. Run `git remote -v` to confirm the remote name and URL.
2. Run `git ls-remote --heads origin` to see published branches.
3. Run `git ls-remote --tags origin` to see tags.
4. Run `git ls-remote --symref origin HEAD` to check default branch information provided by the server.
5. Use patterns and `--exit-code` if you need to verify a specific branch or tag.
6. Run `git fetch origin` only when you need to download data and update remote-tracking refs on your machine.

The key is to read the two columns of output accurately: the object ID tells you which object the ref points to, and the ref name tells you whether it is a branch, tag, or `HEAD`. Understanding this format lets you quickly inspect remote status, verify whether a branch has been pushed, and choose the right next synchronization step.
