# Pre-Push Verification with --dry-run and Reference Comparison

Before sending commits to a remote repository, you should clearly verify **which remote will receive data, which branch will be updated, and which commits will be sent**. Git provides `git push --dry-run` to simulate a push: Git connects to the remote, computes the refs to update, and displays the expected outcome without actually updating refs on the server.

A dry run is useful when preparing to push to a shared branch, working with multiple remotes, or using explicit refspecs. However, dry-run output only reflects the remote's state at check time. Remote state can change before the real push, and the server can still reject the update due to permissions, branch policies, or server-side checks.

## 1. What Does `git push --dry-run` Do?

A normal push sends the necessary objects to the remote and requests the server to update one or more refs. With `--dry-run`, Git runs the preparation steps and reports the expected updates, without requesting those updates be applied on the remote.

Example:

```bash
# Simulate pushing branch main to origin's main branch
git push --dry-run origin main:refs/heads/main
```

This command shows that Git intends to push the local `main` branch to the `main` branch on remote `origin`. It does not update the `main` branch on the server.

You can add `--verbose` for more detail or `--porcelain` to receive machine-readable output:

```bash
git push --dry-run --verbose origin main:refs/heads/main
git push --dry-run --porcelain origin main:refs/heads/main
```

`--porcelain` is useful when output is parsed by scripts. When reading visually, pay attention to the destination remote, source ref, destination ref, and the status Git reports for each ref. Exact formatting may vary across Git versions and remote protocols.

### A dry run is not a completed push

A dry run does not update refs on the remote and does not make commits shared. The command still accesses the remote, so it may require network connectivity and authentication. A dry-run result also does not guarantee the actual push will succeed: someone else may push before you, permissions or server policies may change, and server-side checks may return a different outcome during the real update.

A dry run also does not upload uncommitted content to the remote. `git push` transfers commits reachable from the source ref; recent edits sitting only in the working tree or staging area not yet part of a commit will not be sent.

## 2. Understanding Refs Before Checking

To read push output, distinguish three reference types:

| Ref Type | Example | Meaning |
|---|---|---|
| Local branch | `main`, `feature/login` | Reference in the local repository pointing to the commit you are developing or preparing to send |
| Remote branch on server | `refs/heads/main` | Actual reference inside the remote repository |
| Remote-tracking branch | `origin/main` | Local record of the remote branch's state as of the most recent fetch |

`origin/main` does not automatically update the instant someone pushes to the server. It only reflects information local has received via `git fetch` or an appropriate ref-updating operation. Therefore, before comparing local with a remote-tracking branch, fetch the corresponding remote.

```bash
# Retrieve latest status and update remote-tracking refs
git fetch origin

# View local branches
git branch

# View remote-tracking branches
git branch -r

# View which remote branch each local branch tracks
git branch -vv
```

Fetch downloads data and updates references according to configured refspecs; it does not automatically merge changes into the current local branch and normally does not alter the working tree.

## 3. Checking Working State and Source Commits

Before pushing, check whether changes have been recorded in commits:

```bash
git status --short
git branch --show-current
git log -1 --oneline
```

If `git status --short` shows modified or staged files, those changes are not sent simply because you run `git push`. Review the diff, stage the intended changes, and commit according to your project's workflow:

```bash
git diff
git diff --cached
git add src/login
git diff --cached
git commit -m "Add login validation"
```

If you are in a detached HEAD state, explicitly identify the commit to send and consider creating a local branch to keep the reference easy to manage. Do not rely on default branch names without first verifying the current branch.

## 4. Comparing Local Against the Remote-Tracking Branch

After fetching, you can compare the two branch tips using `git rev-list`:

```bash
git rev-list --left-right --count origin/main...main
```

The output consists of two numbers:

- First number: commits reachable only from `origin/main`.
- Second number: commits reachable only from local `main`.

Example:

```text
2       3
```

This means the remote-tracking branch has two commits not yet in local `main`, while local `main` has three commits not yet in `origin/main`. The two branches have diverged; a normal push may be rejected as non-fast-forward.

To view the specific commits on each side:

```bash
# Commits in local main not yet in origin/main
git log --oneline origin/main..main

# Commits in origin/main not yet in local main
git log --oneline main..origin/main

# View two-sided graph
git log --oneline --left-right --graph origin/main...main
```

The range `A..B` lists commits reachable from `B` that are not reachable from `A`. The range `A...B` combines commits belonging solely to one side or the other; with `--left-right`, Git marks each commit according to its side.

If the remote branch does not exist yet, there will be no `origin/feature/login` to compare against. Check the destination ref directly on the remote before deciding:

```bash
git ls-remote --heads origin refs/heads/feature/login
```

If the command returns no lines for this exact ref, the remote is not currently advertising that branch (or the account lacks permission to see the ref). If results appear, the returned line contains the object ID and ref name, for example:

```text
8f2a1c...    refs/heads/feature/login
```

`git ls-remote` queries refs advertised by the remote without updating remote-tracking branches locally. If you need to analyze the full commit graph, fetch first.

## 5. Checking Fast-Forward Update Eligibility

For a branch already existing on the remote, a normal push can update the ref if the remote's current target commit is an ancestor of the local source commit. You can check that relationship with `git merge-base --is-ancestor` after fetching:

```bash
git merge-base --is-ancestor origin/main main
```

If the command exits with code `0`, `origin/main` is an ancestor of `main`: updating from `origin/main` to `main` can proceed as a fast-forward. If the exit code is `1`, that ancestor relationship does not hold; inspect the graph to distinguish whether local is missing remote commits or both branches have diverged. Other errors may return different exit codes and need separate handling.

Inspect visually:

```bash
git log --oneline --left-right --graph origin/main...main
```

Never use `--force` merely because the check shows branches have diverged. First understand which commits exist only on the remote and which exist only locally; integrate changes per team policy. If you must rewrite history on a branch you manage, consider `--force-with-lease` and coordinate with others using the branch.

## 6. Dry-Running with an Explicit Refspec

A push command may depend on default settings such as `push.default`, upstream branch, or default remote. When you want to check the exact destination, write out the refspec explicitly:

```bash
# Send local branch feature/login to the same branch name on origin
git push --dry-run origin feature/login:refs/heads/feature/login
```

In the refspec `source:destination`:

- `feature/login` is the local source ref used to determine which commits to send.
- `refs/heads/feature/login` is the destination ref on the remote to update.

If you want to send the commit at current `HEAD` to a specific remote branch:

```bash
git push --dry-run origin HEAD:refs/heads/review/login-check
```

The command above expects to update branch `review/login-check` on `origin` with the current commit of `HEAD`. This syntax is helpful when source and destination branches have different names or when you want to avoid relying on default push settings.

If you only run:

```bash
git push --dry-run origin
```

Git picks refs to push based on configured push refspecs and current default settings. This is convenient in a stably configured workflow, but when checking for the first time or working across multiple remotes, an explicit refspec makes the output easier to evaluate.

## 7. Reading Dry-Run Output

Output depends on local state, remote state, the refspec, and the Git version. Common messages have these meanings:

| Output Form | Interpretation |
|---|---|
| `Everything up-to-date` | No updates need to be sent for the selected refspec. |
| `[new branch]` | The command expects to create a new branch on the remote. |
| A branch listed as updating | Git expects to update the destination ref from the specified source ref. |
| `[rejected]` or non-fast-forward message | Update is not accepted under current push rules; inspect history and remote policies. |
| `error` during connection or authentication | Git could not complete the check with the remote; verify URL, network, and credentials. |

When using `--porcelain`, output is formatted so tools can parse per-ref status. Avoid writing scripts around free-form prose messages; when automating, rely on porcelain format and command exit codes.

A dry run only shows expected updates at the moment of inspection. For instance, if a teammate pushes a new commit after your dry run, the real push may be rejected even though the prior dry run reported no error. Fetch and re-check if significant time has passed or concurrent activity occurred on the branch.

## 8. A Complete Pre-Push Workflow

Suppose you finished branch `feature/login` and want to push it to `origin`. You can follow this sequence:

```bash
# 1. Verify working tree and current branch
git status --short
git branch --show-current

# 2. Verify remote and push URL
git remote -v
git remote get-url --push origin

# 3. Refresh remote information
git fetch origin

# 4. Review local commits to send and remote commits missing locally
git log --oneline origin/feature/login..feature/login
git log --oneline feature/login..origin/feature/login

# 5. Count unique commits on each side
git rev-list --left-right --count origin/feature/login...feature/login

# 6. Simulate the exact ref to be updated
git push --dry-run --verbose origin feature/login:refs/heads/feature/login
```

Review the output before pushing for real. Confirm the remote is the right fork or target repository, the destination branch is right, source commits have been reviewed, and no new remote changes need integration.

If the output looks right, perform the real push with the same refspec:

```bash
git push -u origin feature/login:refs/heads/feature/login
```

`-u` sets the upstream branch for the local branch once the push succeeds. If the branch already has the right upstream branch set, you may omit repeating this option.

## 9. Common Limitations and Misconceptions

| Misconception | Accurate Understanding |
|---|---|
| Dry-run proves the real push will definitely succeed | It only simulates updates under the state and conditions at check time; the server may change or reject the real push. |
| Dry-run updates local `origin/main` | No. To update remote-tracking refs, use `git fetch origin`. |
| Dry-run also sends staged content | No. Push sends commits referenced by the source ref; uncommitted changes are not part of that ref. |
| `origin/main` is always the latest state on the server | It is a local record from the most recent fetch; it may be stale. |
| No output from `git ls-remote` means the branch definitely does not exist | Usually the remote is not advertising a matching ref; visibility permissions or patterns can also affect results. |
| The two numbers from `rev-list --left-right --count` are counts of differing files | They are counts of commits unique to each side, not file counts or changed line counts. |
| Dry-run with the default remote always pushes the intended branch | Default push configuration may select another ref; use an explicit refspec when control is needed. |

## 10. Self-Check

1. **Does `git push --dry-run` update the branch on the server?**
   - No. It reports expected updates without applying ref updates on the remote.
2. **Why should you run `git fetch origin` before comparing `origin/main` with `main`?**
   - To update the local remote-tracking ref to the latest state advertised by the remote as of that fetch.
3. **In the output of `git rev-list --left-right --count origin/main...main`, what does the second number represent?**
   - The number of commits reachable only from local `main`, typically how far local is ahead of the remote.
4. **Which command checks whether the remote already has branch `feature/login` without updating remote-tracking refs?**
   - `git ls-remote --heads origin refs/heads/feature/login`.
5. **Why should you use an explicit refspec in a dry-run command?**
   - To clearly specify the source branch and destination ref, avoiding confusion from default push settings or upstream branch configuration.

## Conclusion

`git push --dry-run` helps preview which refs Git intends to update on the remote. To evaluate the output meaningfully, check the working tree, identify the remote and destination ref, fetch to update remote-tracking refs, compare commits on both sides, and then run a dry run with an explicit refspec. This output is a helpful pre-push check; the real push still needs to be evaluated against the remote's state and policies at execution time.
