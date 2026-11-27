# Timing of pre-push, pre-receive, update, and post-receive

Git hooks are programs that Git invokes at specific moments during an operation. For the push workflow, four key hooks are **pre-push**, **pre-receive**, **update**, and **post-receive**. Their names look similar, yet they run in different places, receive different data, and hold different decision-making authority over a push.

In the **Hooks and Automation** chapter of the **SOURCE_CONTROL_GIT** module, this lesson focuses on the lifecycle of a push. You will distinguish client-side hooks on the pusher's machine from server-side hooks on the receiving repository, know which hook can reject an entire push, which can reject only a single ref, and which runs only after refs have been updated. This provides the foundation for placing quality checks, branch protection policies, event logging, and deployment triggers at the right point.

After this lesson, you will be able to:

- Describe the execution order of pre-push, pre-receive, update, and post-receive.
- Distinguish client-side hooks from server-side hooks.
- Read the arguments and stdin data received by each hook.
- Choose the right hook for pre-push testing, policy validation, per-ref protection, or post-push notifications.
- Explain the rejection scope of pre-receive and update.
- Understand why post-receive cannot cancel an accepted push.
- Configure hook locations, verify execute permissions, and troubleshoot hook errors.

## 1. What Is a Git Hook?

A hook is a program that Git locates and executes when a specific event occurs. Hooks are typically shell scripts, though they can be programs or scripts in any language as long as the runtime environment can execute them.

For example:

- pre-push runs in the client repository before Git sends updates to a remote.
- pre-receive runs in the server repository when receiving a push, before updating refs.
- update runs on the server individually for each ref being updated.
- post-receive runs on the server after refs are successfully updated.

A hook is neither a commit nor part of Git history. It is a program located in the repository's environment configuration or specified via a hooks path. A hook can inspect data, reject an operation, write logs, send notifications, or launch downstream jobs.

What matters is selecting a hook based on when intervention is required. A check meant to block an invalid push must run before refs are updated. A deployment task requiring the new commit to already exist on the server must run after the update succeeds.

## 2. Lifecycle of a Push

When a user runs git push, Git can go through the following main steps:

~~~text
Pusher's Machine (client)               Receiving Repository (server)

git push
   |
   v
pre-push
   |  non-zero -> abort push
   |
   v
Connect and send data ----------------> receive-pack accepts updates
                                           |
                                           v
                                      pre-receive
                                           | non-zero
                                           | -> reject all
                                           v
                                      update (per ref)
                                           | non-zero
                                           | -> reject that ref
                                           v
                                      Update accepted refs
                                           |
                                           v
                                      post-receive
                                           |
                                           v
                                      Notifications / deployment
~~~

The diagram illustrates the typical flow. If pre-push rejects, the client does not proceed with the push. If pre-receive rejects, the server accepts none of the refs in that push. If update rejects one ref, other refs can still be updated if valid. Post-receive processes only the refs that were successfully updated.

Not every push updates refs. For instance, a push with no changes or one rejected early may not reach later stages. Therefore, design hooks around the actual event at which they are invoked.

## 3. Comparison Table of the Four Hooks

| Hook | Where Does It Run? | Timing | Primary Data | Can It Reject? |
| --- | --- | --- | --- | --- |
| pre-push | Client | Before push updates remote | Remote name, URL, and list of refs to push | Yes, stops the push on the client |
| pre-receive | Server | When receiving push, before updating refs | List of old OID, new OID, ref name via stdin | Yes, rejects the entire push |
| update | Server | Individually per ref, before updating that ref | ref name, old OID, new OID via arguments | Yes, rejects that specific ref |
| post-receive | Server | After refs are successfully updated | List of updated refs via stdin | Cannot reject or roll back a successful push |

OID stands for object ID, commonly called a commit hash when a ref points to a commit. Git can also use the SHA-256 object format, so never assume every hash is always 40 characters long.

## 4. pre-push: Checking on the Pusher's Machine

pre-push is a client-side hook. Git invokes this hook in the repository executing the push command, before updates are sent to modify refs on the remote.

The hook receives two arguments:

1. The remote name, for example origin.
2. The remote address Git will push to.

In addition, Git sends the list of refs intended to be updated via stdin. Each line contains four fields:

~~~text
<local-ref> <local-oid> <remote-ref> <remote-oid>
~~~

Where:

- local-ref is the local ref used as the source.
- local-oid is the local object ID.
- remote-ref is the remote ref to be updated.
- remote-oid is the current object ID on the remote.

When creating a new ref on the remote, remote-oid is a string of zeros. When deleting a remote ref, local-ref may be (delete) and local-oid is a string of zeros. The length of the zero string depends on the repository's object format.

### When to Use pre-push?

- Running unit tests or formatting checks before sending code.
- Checking whether commits about to be pushed contain disallowed files.
- Reminding users to update documentation or verify migrations.
- Blocking pushes from a personal machine if a branch has not met an internal condition.

Example hook running tests before each push:

~~~sh
#!/bin/sh
set -eu

echo "Running checks before push to $1 ($2)" >&2
./scripts/test.sh
~~~

Save the file as pre-push in the active hooks directory and grant execute permission on Unix-like systems. If the script returns a non-zero exit code, Git aborts the push. The script above demonstrates running tests; a real-world hook can read stdin to inspect only the relevant refs or commits.

### pre-push Is Not a Server Security Policy

Because the hook resides on the user's machine, a user might not install it, might modify it, or might skip it. The git push --no-verify option bypasses pre-push. Thus, pre-push is well suited for fast feedback and developer-assistance checks. Mandatory organizational rules must be enforced on the server or repository management platform.

## 5. pre-receive: Checking the Entire Push on the Server

pre-receive is a server-side hook. Git invokes the hook once per received push, before updating any refs. The hook receives via stdin one line per proposed ref update:

~~~text
<old-oid> <new-oid> <ref-name>
~~~

Where:

- old-oid is the current object ID of the ref on the server.
- new-oid is the new object ID the client wants to update to.
- ref-name is the full name, such as refs/heads/main or refs/tags/v1.2.0.

When creating a new ref, old-oid is a string of zeros. When deleting a ref, new-oid is a string of zeros.

pre-receive fits policies that require examining the entire set of refs pushed together:

- Blocking updates to protected branches if conditions are not met.
- Checking commits or metadata across all refs before accepting.
- Preventing deletion of a critical branch.
- Ensuring a group of tags or branches is updated according to release rules.

If pre-receive returns a non-zero exit code, the server rejects the entire push. This is the right choice when refs in the same push must be accepted or rejected atomically as a group.

### Example: Preventing Deletion and History Rewriting of main

~~~sh
#!/bin/sh

while read old new ref
do
    case "$ref" in
        refs/heads/main)
            case "$new" in
                *[!0]*)
                    ;;
                *)
                    echo "Deletion of main is not allowed" >&2
                    exit 1
                    ;;
            esac

            case "$old" in
                *[!0]*)
                    if ! git merge-base --is-ancestor "$old" "$new"
                    then
                        echo "Non-fast-forward update of main is not allowed" >&2
                        exit 1
                    fi
                    ;;
                *)
                    ;;
            esac
            ;;
    esac
done

exit 0
~~~

This example uses shell pattern matching to detect an all-zero OID without hardcoding hash length. For an existing main branch, the hook requires the old commit to be an ancestor of the new commit; otherwise, the update is rejected. This rule is illustrative; teams still need to account for actual merge workflows and branch policies.

In server hooks, send rejection messages to stderr so the pusher can read the reason. Keep checks fast enough because the hook runs synchronously during the push.

## 6. update: Checking Each Ref Individually

update is also a server-side hook, differing from pre-receive in its invocation scope. Git invokes update once for each ref being updated.

The hook receives three arguments:

~~~text
<ref-name> <old-oid> <new-oid>
~~~

For example:

- refs/heads/main
- Old OID of main
- Proposed new OID

update is appropriate when policies can be decided independently per ref, such as:

- Allowing updates only within certain namespaces.
- Protecting release branches.
- Rejecting deletion of a specific ref.
- Applying different rules for branches and tags.

If update returns a non-zero exit code, that corresponding ref is rejected. Other refs in the same push can still be updated. This is a key difference from pre-receive, where a single rejection rejects the entire push.

### Example: Protecting Release Branches from Deletion

~~~sh
#!/bin/sh

ref_name=$1
old_oid=$2
new_oid=$3

case "$ref_name" in
    refs/heads/release/*)
        case "$new_oid" in
            *[!0]*)
                ;;
            *)
                echo "Release branches cannot be deleted" >&2
                exit 1
                ;;
        esac
        ;;
esac

exit 0
~~~

This hook only rejects deletions of branches under refs/heads/release/. Other refs are unaffected by this rule. It can be extended to enforce fast-forward checks or other per-ref conditions.

### When to Choose update Instead of pre-receive?

Choose update when acceptance decisions can be made independently per ref. Choose pre-receive when you need to inspect all refs together and reject the entire push if any ref violates policy. If using update for a rule that must maintain consistency across multiple refs, be careful about the possibility of a partially successful push.

## 7. post-receive: Processing After Refs Are Updated

post-receive is a server-side hook that runs after accepted refs have been updated. Git invokes the hook once for the received push and passes the list of successfully updated refs via stdin, formatted as:

~~~text
<old-oid> <new-oid> <ref-name>
~~~

This hook suits tasks that require the new commits to already exist in the receiving repository:

- Sending notifications to chat, email, or tracking systems.
- Updating dashboards or audit logs.
- Triggering build and deployment pipelines.
- Synchronizing release metadata.
- Emitting events to integration systems.

### post-receive Cannot Reject a Completed Push

By the time post-receive runs, the refs have already been updated. A non-zero exit code from this hook does not cause Git to roll back the refs and does not turn an accepted push into a rejected one.

For example, if an application deployment hook fails:

- The commit has still been pushed to the branch.
- The ref on the server still points to the new commit.
- The deployment must be retried or handled through operations tooling.

Therefore, never place mandatory pre-acceptance checks in post-receive. Place rejecting checks in pre-receive or update; use post-receive to notify and trigger work after the data has been accepted.

### Example: Triggering a Deployment When main Is Updated

~~~sh
#!/bin/sh

while read old new ref
do
    case "$ref" in
        refs/heads/main)
            if ! ./scripts/enqueue-deploy.sh "$new"
            then
                echo "Could not enqueue deployment for $new" >&2
            fi
            ;;
    esac
done

exit 0
~~~

The example invokes a script that places a deployment request into a queue. In practice, design jobs to be idempotent/retryable, log properly, and avoid unintended duplicate deployments. For long-running tasks, enqueue the job and exit the hook quickly rather than holding the push connection open during a lengthy build or deployment.

## 8. Choosing a Hook by Goal

| Goal | Suitable Hook | Reason |
| --- | --- | --- |
| Run tests before sending code from a personal machine | pre-push | Runs before the client sends updates |
| Enforce policy across all refs in a single push | pre-receive | Receives the full ref list and can reject the entire push |
| Apply independent rules per branch or tag | update | Invoked separately for each ref |
| Send notifications after a branch is updated | post-receive | Runs only after refs are accepted |
| Trigger a deployment from a new commit on main | post-receive | The new commit is already in the receiving repository |
| Protect a branch from force updates | pre-receive or update | Can check the relationship between old and new OIDs before updating |

A workflow may use multiple hooks. For instance, pre-push runs fast tests on the developer's machine; pre-receive enforces mandatory policies on the server; post-receive sends events to CI. Each hook should have a clear responsibility and avoid repeating the same expensive check in multiple places.

## 9. Where Are Hooks Installed?

### Default Hooks Directory

In a repository, hooks reside by default in the hooks directory under the Git directory. In a regular repository, that directory is usually .git/hooks. In a bare repository, hooks reside in the bare repository's Git directory.

To query Git for the exact path:

~~~bash
git rev-parse --git-path hooks
~~~

Avoid always hardcoding .git/hooks because linked worktrees, submodules, or custom Git directory layouts may use a different path.

### core.hooksPath

Git allows specifying a different hooks directory:

~~~bash
git config --show-origin --get core.hooksPath
~~~

If this key is set, Git looks for hooks in the configured directory instead of the default hooks directory. It can be set per repository:

~~~bash
git config --local core.hooksPath .githooks
~~~

When using a relative path, it is resolved relative to Git's working directory at execution time. The team should standardize the layout and installation documentation so everyone uses the same hooks.

### Are Hooks Shared on Clone?

Hooks stored in the Git directory are not committed like normal source code and are not automatically transferred when someone clones the repository. Therefore, to share client-side hooks, teams typically store scripts in a version-controlled directory such as .githooks, then instruct members to point core.hooksPath to it or use an installer tool.

Server-side hooks must be installed on the receiving repository or managed by the platform. Committing a hook file in a client repository does not automatically install hooks on the server.

## 10. Execute Permissions and Rules for Writing Hooks

On Unix-like systems, hooks require execute permissions:

~~~bash
chmod +x .githooks/pre-push
chmod +x hooks/pre-receive
~~~

The actual path depends on hooksPath and the repository type. On Windows, Git for Windows typically runs shell hooks via its bundled environment; verify the interpreter, line endings, and access permissions in the deployment environment.

A good hook should:

- Exit with code 0 when allowing the operation; non-zero when rejecting in a hook permitted to reject.
- Print concise, actionable failure reasons to stderr.
- Read stdin in the hook's specified format without assuming only one ref.
- Handle newly created refs and deleted refs, where the OID is an all-zero string.
- Never assume hashes have a fixed length.
- Run quickly and avoid unnecessary interactive prompts.
- Log appropriately without exposing tokens, passwords, or sensitive data.
- Have tests and clear versioning if used as a shared policy.

If a hook must call an external API or system, handle timeouts, retries, and network errors. Especially in post-receive, record downstream work in a durable queue so it can be retried if external services are temporarily unavailable.

## 11. Inspecting Sample Hooks and Checking Active Hooks

Git normally creates sample files with a .sample suffix in the hooks directory. They do not run merely by existing; the suffix must be removed and valid content and execute permissions configured.

List the hooks directory:

~~~bash
git rev-parse --git-path hooks
~~~

Check hooksPath:

~~~bash
git config --show-origin --get core.hooksPath
~~~

Check repository state before testing a hook:

~~~bash
git status -sb
git remote -v
~~~

If a hook does not run as expected, verify:

1. Does the filename match the exact hook name without a .sample suffix?
2. Is Git using the default hooks directory or core.hooksPath?
3. Does the script have execute permission and a valid interpreter?
4. Does the script have syntax errors or depend on a program missing from PATH?
5. Is the hook being bypassed via --no-verify or the configuration of a tool invoking Git?
6. Is the hook on the client or server? Are you checking the right machine?

## 12. Testing Each Hook's Behavior

Do not test hooks directly on production branches or shared repositories the first time. Create a local test repository or a separate bare repository to observe behavior.

### Testing pre-push

Create a pre-push script returning a non-zero code:

~~~sh
#!/bin/sh
echo "Push blocked by local test hook" >&2
exit 1
~~~

Run git push and confirm the client stops before remote refs change. Then test with git push --no-verify to see how client hooks can be bypassed. Perform this only in a test repository.

### Testing pre-receive

In a receiving bare repository, install a pre-receive returning a non-zero code. Push a test branch and verify that all updates in the push are rejected. Do not use this reject-all example on a remote serving the team.

### Testing update with Multiple Refs

Create two test branches and configure update to reject one branch by name. Push both refs at once. Observe that the ref rejected by the hook is not updated, while the remaining ref can succeed if there are no other errors.

### Testing post-receive

Install a post-receive hook that logs the old OID, new OID, and ref name. Push a test branch and verify the log entry is written after the remote ref changes. You can also test having the hook return a non-zero exit code and confirm the ref still points to the received commit.

## 13. Common Misconceptions

### Are pre-push and pre-receive the same?

No. pre-push runs on the client before a push is sent. pre-receive runs on the server when receiving a push and can enforce centralized policy for the receiving repository.

### Does pre-receive run once per branch?

No. It runs once per push reception and receives the list of all refs via stdin. update is the hook invoked individually for each ref.

### Does update rejecting one ref cancel all other refs?

Not necessarily. update rejects the ref that particular invocation is checking. Other refs may still be updated. If atomicity across a group of refs is required, use pre-receive to validate upfront and reject the entire push.

### Can post-receive cancel a push if deployment fails?

No. The hook runs after refs have already been updated. If deployment fails, log and retry the operational task; the push has already been accepted.

### Are client-side hooks automatically shared on clone?

No. Hooks in the Git directory are not part of normal commit history. To share them, store scripts in the repository and provide an installation step; mandatory policies should be enforced on the server.

### Can --no-verify bypass every hook?

Do not assume that. --no-verify applies to certain client-side hooks, such as pre-push. It does not allow a client to bypass pre-receive, update, or post-receive enforced by the server.

## 14. Self-Check

A team wants to build a workflow:

- Developer machines run tests before pushing.
- The server rejects any push if one of the refs violates policy.
- The server prevents deleting release branches.
- When main is updated, the CI system receives an event to deploy.

Answer:

1. Which hook should run tests on the developer's machine?
2. Which hook checks all refs and rejects the entire push?
3. Which hook can individually reject a release branch?
4. Which hook runs after main has been updated?
5. What data does pre-push receive via arguments and stdin?
6. Why should mandatory checks not be placed in post-receive?
7. Why should server-side policies not rely solely on pre-push?

**Hint:** Use pre-push for client-side tests; pre-receive for policy applying to the entire push; update for per-ref rules; post-receive to send deployment events after updates. pre-push receives the remote name, URL, and lines of local-ref/local-OID/remote-ref/remote-OID. post-receive cannot roll back a successful push. Users might not install or might bypass client-side hooks, so mandatory rules must live on the server.

## Conclusion

pre-push runs on the client to check before sending; pre-receive runs once on the server to inspect all refs and can reject the entire push; update runs per ref and rejects only that corresponding ref; post-receive runs after refs are updated to notify or trigger downstream work. Choose hooks according to the exact timing and decision scope, parse input data properly, keep hooks short with clear messages. Above all, place mandatory policies on the server and treat post-receive as a post-push workflow trigger rather than a gatekeeper or rollback mechanism.
