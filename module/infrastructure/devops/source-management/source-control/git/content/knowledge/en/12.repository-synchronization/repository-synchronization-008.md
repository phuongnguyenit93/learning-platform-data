# Force Push, --force-with-lease, and Protection Limits with Background Fetch

When rewriting history on a branch that has already been pushed to a remote—such as after rebasing or squashing commits—Git normally rejects a push because the new update is no longer a fast-forward. `git push --force` can overwrite the remote branch tip with local history, but it can also drop commits that someone else just pushed.

`git push --force-with-lease` adds a condition: only allow the update if the remote ref still holds the value expected locally. This is a useful safeguard when collaborating, though the level of protection depends on how Git obtains that expected value. A background fetch process can update the remote-tracking branch and cause the default lease form to lose the ability to detect a commit you have not yet reviewed.

## 1. Why Force Push?

A normal push requires updating the remote in a fast-forward manner: the new history must contain the remote branch's current history. This prevents a push from accidentally making existing remote commits disappear.

For example, the local and remote branches initially both point to tip `C`, with history `A-B-C`:

```text
A---B---C  (origin/feature, feature)
```

You edit local history via rebase or squash, producing a new chain of commits:

```text
A---B---C       (origin/feature)
 \
  D'---E'       (feature)
```

In the diagram, `D'` and `E'` are new commits replacing history `B` and `C`. The local branch is no longer a descendant of the remote branch tip, so a normal push is rejected with a non-fast-forward error.

Force push tells the remote to move the ref to the new commit even though the old history is not an ancestor of the new history:

```bash
git push --force origin feature
```

This command can overwrite remote commits that local does not know about or has not included in the new history. If a teammate pushed commit `F` to the remote after your last fetch, force push can make `F` disappear from the shared branch tip.

Force push only changes the ref on the remote; it does not merge overwritten commits and does not guarantee others have updated their local copies. Therefore, verify the target branch and refspec scope before using it.

## 2. How Do `--force` and `--force-with-lease` Differ?

`--force` skips the fast-forward check for the pushed ref. It does not check whether the remote branch tip has changed since you last observed it.

`--force-with-lease` requires the current value of the remote ref to match an expected value. If the remote has changed, Git rejects the push so you have a chance to fetch, inspect new changes, and integrate them.

| Command | Condition Allowing Update | Protection Level |
|---|---|---|
| `git push --force` | Fast-forward not required | Can overwrite unreviewed remote changes |
| `git push --force-with-lease` | Remote ref must match expected value from remote-tracking ref | Detects remote changes if the expected value has not been updated |
| `git push --force-with-lease=<ref>:<expect>` | Remote ref must equal the specified OID exactly | Compares against a fixed expected value |
| `git push --force-with-lease --force-if-includes` | Default lease plus an additional check on integrating the remote-tracking tip | Useful when background fetch updates remote-tracking refs |

In a typical setup, when running:

```bash
git push --force-with-lease origin HEAD:refs/heads/feature
```

Git takes the expected value from the corresponding remote-tracking branch, typically `refs/remotes/origin/feature`. If the remote ref no longer equals that value, the push is rejected.

A lease is a check on the ref value at the time of update. It does not understand commit contents, does not merge changes, and is no substitute for reviewing history.

## 3. How Background Fetch Weakens the Default Lease

Suppose local and remote branches initially both point to tip `C`, with history `A-B-C`. You rewrite two commits `B` and `C` into `D'` and `E'` on top of `A`. While you work, an IDE or automated process runs `git fetch origin` in the background.

Before the background fetch:

```text
A---B---C  (origin/feature)
 \
  D'---E'  (feature)

```

A teammate pushes commit `F` to the remote. The background fetch downloads that commit and updates the remote-tracking ref:

```text
A---B---C---F  (origin/feature)
 \
  D'---E'  (feature)
```

Your local branch is still based on `A`; you have neither reviewed nor integrated `F`. However, the remote-tracking ref `origin/feature` has been updated to `F` by the background process.

If you use the default lease form, Git may take `F` as the expected value. The remote is also at `F`, so the lease comparison succeeds. Git does not know that your local history still omits commit `F`, and may allow the force push to replace the remote tip with `E'`.

That is the critical limitation: **the default lease relies on the current remote-tracking ref, not an immutable record of the remote commit you reviewed before rewriting history**. If a background fetch updates this ref, the expected value shifts along with it.

Background fetches often come from IDEs, GUI Git clients, extensions, sync scripts, or another terminal. You may not even notice one has run.

## 4. Using a Fixed Expected OID

To prevent changes to the remote-tracking ref from drifting the expected value, you can explicitly specify the OID that the remote ref must have:

```bash
git push --force-with-lease=refs/heads/feature:EXPECTED_OID origin HEAD:refs/heads/feature
```

Replace `EXPECTED_OID` with the full commit ID recorded at the moment you identified the remote branch your work is based on.

Git allows the update only if `refs/heads/feature` on the remote still equals that exact OID. If a teammate pushed another commit after that point, the remote ref changes to a different OID and the push is rejected, even if a background fetch already updated `origin/feature` on your machine.

A workflow using a fixed expected OID:

1. Fetch the remote at a deliberate moment and inspect branch history.
2. Record the OID of the remote branch tip you reviewed before rewriting local history.
3. Create or rebase local commits based on the reviewed history.
4. Push with `--force-with-lease=refs/heads/<branch>:<expected-oid>`.
5. If rejected, fetch and inspect new commits; integrate changes that need to be kept, then determine the new expected OID before retrying.

You can retrieve the remote-tracking ref's OID with:

```bash
git rev-parse refs/remotes/origin/feature
```

Record the output at the appropriate moment and keep it unchanged while working. If you only run that command after a background fetch has already updated the ref, the new OID may represent a commit you have not reviewed; specifying the OID explicitly does not by itself make that value safe.

Instead of copying the OID into notes, you can pin it with a local tag before rewriting history:

```bash
git fetch origin
git log --oneline --decorate -10 refs/remotes/origin/feature
git tag feature-base refs/remotes/origin/feature

# After inspecting and rewriting local history
git push --force-with-lease=refs/heads/feature:feature-base origin HEAD:refs/heads/feature
```

The `feature-base` tag preserves the recorded OID even if a background fetch updates `origin/feature`. Pick an unused tag name and do not move that tag while working; after pushing, you can delete the local tag with `git tag -d feature-base` if no longer needed.

Another way to observe the OID directly on the remote is:

```bash
git ls-remote origin refs/heads/feature
```

This command displays the remote ref's current OID at query time. It is useful for checking remote status, though it does not replace reviewing commits. If you grab the OID after someone pushed a commit you have not integrated and immediately pass it as the expected value, the lease can still allow overwriting that commit. Cross-check history and only use an expected value tied to a state you have genuinely inspected.

## 5. Combining `--force-if-includes`

Git provides `--force-if-includes` as an additional check when used alongside `--force-with-lease` in the form without an explicit expected OID. This option checks whether the remote-tracking ref tip is reachable from one of the local branch's reflog entries created on top of that ref when rewriting history. Its goal is to help catch cases where the remote-tracking ref was updated by a background fetch while the local branch has not integrated those changes.

Example:

```bash
git push --force-with-lease --force-if-includes origin HEAD:refs/heads/feature
```

This is a helpful safeguard when another tool might run background fetches. `--force-if-includes` does not replace the lease and is not an automatic way to merge commits. If the check fails, the push is rejected so you can inspect history.

Remember:

- `--force-if-includes` is designed to supplement the remote-tracking-ref form of `--force-with-lease`, especially when background fetches occur.
- Using `--force-if-includes` alone without `--force-with-lease` does not provide equivalent force-push protection.
- When combined with `--force-with-lease=<ref>:<expect>` specifying an explicit expected OID, `--force-if-includes` is a no-op; the explicit lease already compares against a fixed value.
- It does not verify on your behalf that all changes are functionally or test-wise correct.
- When you need a fixed, unambiguous expected baseline, use `--force-with-lease=<ref>:<expect>` with the recorded OID.

## 6. Isolating the Remote-Tracking Ref Used for Pushing

Another strategy is creating a dedicated remote for pushing, so background fetches from the primary working remote do not update the ref used as the expected value.

For example, add a remote pointing to the same URL:

```bash
git remote add origin-push REMOTE_URL
git fetch origin-push
```

Replace `REMOTE_URL` with the URL of the remote repository you intend to push to; confirm it is the right repository before adding the remote.

Remote `origin-push` maintains its own set of remote-tracking refs, such as `refs/remotes/origin-push/feature`. If your IDE only auto-fetches `origin`, refs under `origin-push` are not updated by that fetch.

After inspecting and recording state from the push remote, you can run:

```bash
git push --force-with-lease origin-push HEAD:refs/heads/feature
```

This lets the default lease reference a remote-tracking ref less exposed to background processes. You must still proactively fetch `origin-push` and review changes before rewriting history or pushing. If you fetch the separate remote after a new commit appears without integrating it, the lease could once again accept that new value.

Inspect remote settings:

```bash
git remote -v
git config --get-all remote.origin.push
git config --get-all remote.origin-push.fetch
```

Only add a separate remote when you understand the URL and refspecs in use. Avoid accidentally pointing a push remote to another repository or an unintended fork.

## 7. Controlled Force Push Workflow

A practical workflow when needing to push rebased history to a shared branch:

```bash
# 1. Verify branch and local status
git status
git branch --show-current

# 2. Fetch and inspect remote status at a deliberate point in time
git fetch origin
git log --oneline --graph --decorate --all -20

# 3. Check the remote branch tip OID and record the reviewed value
git rev-parse refs/remotes/origin/feature

# 4. Inspect local commits differing from the remote
git log --oneline origin/feature..HEAD
git log --oneline HEAD..origin/feature

# 5. After rebasing/squashing and verifying results,
#    push with the expected OID recorded in step 3
git push --force-with-lease=refs/heads/feature:EXPECTED_OID origin HEAD:refs/heads/feature
```

In this workflow, `git log origin/feature..HEAD` shows commits present locally that are not in the remote-tracking ref; the reverse direction shows remote-tracking commits not present locally. Check both sides before deciding to rewrite history.

If the push is rejected:

1. Do not switch to `--force` just to get past the error.
2. Run `git fetch origin` and inspect new commits on the remote.
3. Determine which changes need to be kept; re-rebase, cherry-pick, or coordinate with teammates.
4. Run appropriate tests.
5. Record the new expected OID after inspecting and push again with a lease.

If multiple people are working on the same branch, communicate before rewriting history. Force push can cause teammates' local copies to diverge; they need to know the branch was rewritten and how to update safely.

## 8. Lease Limitations and Server-Side Protection

`--force-with-lease` is a client-side check on the remote ref value. It is not a branch-locking mechanism and cannot replace server-side protection rules.

Several limitations to understand clearly:

- **Does not verify contents were reviewed:** if you specify the wrong expected OID or pick one you never inspected, the lease can still pass if the remote ref matches that OID.
- **Does not stop you from overwriting known history:** if the remote is still at the expected OID, Git permits the update even when the new result drops the commit at that OID. That is the purpose of force push; responsibility for choosing the right history rests with the operator.
- **Does not prevent every refspec mistake:** if you push to the wrong remote name or destination branch, a valid lease for that ref can still update the wrong target. `--force` also applies to every ref being pushed; use an explicit refspec like `HEAD:refs/heads/feature` to restrict updates strictly to the intended branch.
- **Does not bypass server policies:** branch protection, user permissions, receive hooks, or settings prohibiting non-fast-forward updates can still reject a push. Clients cannot use `--force` to override these policies.
- **Does not replace team coordination:** collaborators may still be building on the old history; notify them and guide them on how to sync after the branch is rewritten.

Forms of `--force-with-lease` that do not specify an explicit expected OID are noted in Git documentation as experimental; when fixed comparison behavior is required, use the `<ref>:<expect>` form. To check whether a branch has protection policies, review your code hosting platform settings or ask the repository administrator. If the server forbids force pushing, use a pull request workflow or an organization-approved alternative branch.

## 9. Common Misconceptions

| Misconception | Reality |
|---|---|
| `--force-with-lease` is always completely safe | The default lease can be affected when background fetch updates the remote-tracking ref |
| Background fetch only updates data and does not affect push | It can change the expected value used by the default lease |
| Simply fetching right before pushing is enough | Fetching shows the latest remote state, yet if you have not reviewed new commits, the lease can still allow overwriting them |
| `--force-if-includes` replaces the lease | It is a supplemental check used alongside the lease, not a replacement option |
| The lease will automatically merge new commits | The lease only permits or rejects updating a ref; it does not integrate commits |
| The server allows force push if the client uses `--force` | Server-side branch protection rules, hooks, and permissions still remain in force |

## Conclusion

Using `--force` can overwrite a remote branch tip without checking for new changes. `--force-with-lease` adds a ref-value comparison condition, but its default form relying on the remote-tracking ref can lose protection when a background fetch updates that ref. For important history, record a verified expected OID before rewriting history and use the OID-specified lease form; you can also combine `--force-if-includes` or use a dedicated push remote to reduce risk from background fetches. Always check the refspec, inspect history on both sides, and respect server branch protection policies.
