# Avoiding Duplicate Runs of the Same Check from Multiple Events

A single commit pushed to a repository can simultaneously generate multiple events: a branch push, a pull request update, a review status change, or entry into a merge queue. If multiple events trigger the same pipeline, the system can build and run tests repeatedly, consume runners, lengthen queues, and produce multiple check results that are hard to track.

The goal of trigger control is to ensure each change is verified in the right context, with a reasonable number of runs and traceable results. Two runs on the same commit are not automatically redundant: a check on the source branch, a check on the expected merge state, and a check in the merge queue may verify different conditions. Therefore, before eliminating a run, determine whether the two runs actually test the exact same content under the exact same conditions.

## 1. Distinguishing Events, Runs, and Check Results

The following concepts are often loosely referred to as triggers or pipelines, but they sit at different layers:

- **Event:** something that happened in the system, such as pushing commits, opening a pull request, updating a pull request, creating a tag, or requesting a deployment.
- **Event delivery:** a single attempt by the platform to deliver event information to a workflow or webhook receiver. Some platforms resend a delivery after transient errors.
- **Workflow run:** an execution instance created to process an event.
- **Job or stage:** a unit of work inside a workflow, such as build, unit test, scan, or deploy.
- **Check result:** a status reported back to a commit, pull request, or target object to be verified.

One event can spawn multiple workflow runs; one workflow run can contain multiple jobs; one job can report multiple checks. Conversely, different events can lead to the same type of check. To avoid duplication, identify which layer is repeating.

For example, a commit on a feature branch is pushed while a pull request is already open. The platform may emit both a push event and a pull_request synchronize event. If both triggers launch the same verification workflow, the same change can be built and tested twice. However, if one run tests the branch commit and the other tests the merge result against the latest target branch, they serve different purposes and should not be collapsed solely because they originated from the same commit.

## 2. Why Can Multiple Events Trigger the Same Check?

### Push and Pull Request Describe the Same Change

When a developer pushes commits to a branch that already has a pull request, the system typically emits a push event and a pull request update event. If a workflow listens to both event types without separation rules, the same test suite can run twice.

### One Pull Request Has Many Actions

A pull request can emit events when opened, synchronized with new commits, reopened, marked ready for review, edited in title, or labeled. Not every action requires re-running the entire test suite.

For example, adding a label to assign reviewers usually does not change source code. Conversely, a synchronize action indicates the source branch has new commits and normally requires re-running code-related checks.

### Multiple Workflows Listen to One Event

A repository may have a general CI workflow, a documentation check workflow, a security workflow, and an image build workflow. This can be a clean separation when each workflow owns a distinct scope. However, if multiple workflows all run the same unit test suite or build the same artifact without reason, resources are consumed redundantly.

### Manual Triggers and Automatic Triggers Overlap

A user may manually trigger a workflow re-run right after a push has already started a pipeline. Without checking current status and re-run reason, two instances can perform the same work. Re-running may be necessary when a runner or dependent service hits a transient failure, but reruns should not substitute for root-cause investigation.

### Retries and Duplicate Event Deliveries

Webhooks or integration systems may redeliver the same notification if they do not receive a timely acknowledgment. A webhook receiver must recognize an already-processed delivery to avoid spawning extra actions. A job retry can also repeat an operation that was partially executed.

### Multiple Sources Trigger the Same Release Flow

A tag can generate both a tag push event and a release event. If both run the same packaging and publishing workflow, the system may create duplicate artifacts or duplicate releases. Pick one event as the primary orchestrating source or design release steps to be idempotent.

## 3. Determining When Two Runs Are Truly Duplicate

Do not compare only branch names or commit SHAs. Two runs can only be considered duplicates when they share the same verification goal, the same input contents, and the same verification context.

Before merging or removing triggers, answer:

1. Do the two runs check the same commit or the same source code state?
2. Do both use the same target branch, configuration, environment variables, and dependencies?
3. Are results reported back to the same object and the same check context?
4. Does one run verify an expected merge state, merge queue, or a different environment?
5. Is one run a retry after a failure while the other is a new run from a different commit?

A useful deduplication key can combine the following fields:

- Repository or project.
- Workflow name and check type.
- Pull request number or ref being verified.
- Input commit SHA.
- Target branch or merge context type.
- Significant test configuration, if configuration changes the outcome.

For example, a deduplication key for pull request unit tests could be repository + workflow + pull request + head SHA + check type. Merge queue checks must have a distinct merge group or merge result identifier. Omitting the target branch or merge context can cause two runs to be treated as identical even though they verify two different code combinations.

### Head SHA and Merge SHA Are Not Always Identical

On some platforms, a pull request is tested using a temporary merge commit between the source branch and the target branch. The head SHA represents the latest commit on the source branch; the merge SHA represents the expected merged state. When the target branch moves, the merge SHA can change even though the pull request's head SHA has not changed.

If the goal is checking the branch's code, the head SHA may be the right identifier. If the goal is ensuring changes merge cleanly with the current target branch, the merge result or merge group must be verified. Do not use a single key for both goals.

## 4. Designing an Event Matrix Before Configuring

An event matrix helps establish the authoritative trigger source for each verification type:

| Event | When It Should Run | Typically Suitable Checks |
|---|---|---|
| Pull request opened | When an integration request is created | Fast CI, lint, build, and required tests |
| Pull request synchronize | When the source branch receives new commits | Re-run code-dependent checks |
| Pull request reopened | When a closed PR is reopened | Re-verify if code state or policy changed |
| Pull request labeled/unlabeled | When labels change | Run only tasks that genuinely depend on labels |
| Push to main branch | When changes have been integrated | Main branch CI, artifact creation, or post-merge checks |
| Push to feature branch | When the team wants independent branch verification | Run when no PR exists or when that check has a distinct goal |
| Merge queue / merge group | When the platform prepares to integrate changes | Verify the code combination about to be merged |
| Tag or release | When creating a version | Packaging, signing, publishing, and artifact verification |
| Schedule | On a periodic schedule | Comprehensive checks, dependency updates, or maintenance checks |
| Manual dispatch | When intentionally requested by a person | Re-runs or operational tasks with explicit inputs |

This matrix is not a universal default for every repository. Adapt it to your branching strategy, test types, and CI platform. The key is giving each check type a clear trigger source instead of having every workflow listen to every event.

### A Common Division Strategy

For teams using pull requests, a common choice is:

- Pull requests are the CI trigger source for feature branches.
- Pushes to the main branch are the post-merge CI trigger source.
- Merge queues are the pre-merge combination check trigger source when the repository uses this feature.
- Tags or releases are the packaging and release trigger source.
- Schedules handle periodic checks that do not need to run per commit.

Once rules are chosen, inspect exception paths: pull requests from forks, release branches, hotfixes, merge queues, and workflows invoked by other workflows.

## 5. Filtering Events at the Workflow Level

Workflow-level filtering prevents the system from creating a workflow run when an event is out of scope. Restrict event types, actions, branches, and paths right in the trigger configuration if supported by the platform.

GitHub Actions example: running CI for pull requests targeting main, direct pushes to main, and the merge queue:

~~~yaml
name: CI

on:
  pull_request:
    branches:
      - main
  push:
    branches:
      - main
  merge_group:
    types:
      - checks_requested

jobs:
  validate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Run validation
        run: ./gradlew check
~~~

In this example, pushing to a feature branch does not launch this workflow. Pull requests handle pre-merge verification; pushes to main handle post-merge verification; merge_group handles verifying the expected state in the merge queue. Consequently, the same commit on a feature branch does not automatically spawn an extra push workflow duplicating the pull request workflow.

If a repository needs standalone CI for branches without an open pull request, you can add push triggers for those branches, provided you define how to avoid duplicate runs once a pull request exists. You can split workflows or use explicit conditions based on event and PR state.

### Filtering Pull Request Actions

If only certain actions alter the content needing verification, limit the action list:

~~~yaml
on:
  pull_request:
    branches:
      - main
    types:
      - opened
      - synchronize
      - reopened
      - ready_for_review
~~~

Actions such as changing labels or titles can be handled by a separate workflow if needed. Do not add every action to the list just to receive all events.

### Filtering by Path

If a workflow only checks documentation, path filters can run it only when documentation changes. If a workflow builds the backend, it can be scoped to source directories and related configuration files. However, dependencies must be accounted for: changes to build scripts, lockfiles, shared libraries, or workflow YAML can affect multiple components even when outside the main source directory.

An overly narrow path filter can miss changes with indirect impact. List dependent paths and provide a way to run comprehensive checks when platform configurations change.

On GitHub Actions, a workflow skipped by branch or path filters may leave a required check in a pending state and block merging. When checks are required, consider always creating the workflow and using job-level conditions, or designing an aggregator check that always reports a clear status. Verify the platform's exact behavior before adding filters under branch protection.

## 6. Using Job-Level Conditions to Avoid Redundant Work

It is not always necessary to skip the entire workflow. A single workflow can accept multiple events while running only the jobs required for the specific event type or change scope.

GitHub Actions example: one job runs only when the workflow is triggered by a pull request:

~~~yaml
jobs:
  pr-tests:
    if: github.event_name == 'pull_request'
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: ./gradlew test

  main-validation:
    if: github.event_name == 'push' && github.ref == 'refs/heads/main'
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: ./gradlew check
~~~

Job-level conditions are helpful when multiple event types enter one workflow but require different steps. Ensure every conditional branch produces an understandable check outcome, especially when a check is required for merging.

### Do Not Confuse Conditions with Security

A condition only decides whether a job runs; it does not make pull request data or code trustworthy. For pull requests from forks, evaluate token permissions, secrets, and write access. Avoid running untrusted code in privileged contexts. In particular, workflows using events with access to the target repository must never arbitrarily check out and execute code controlled by the pull request submitter.

## 7. Using Concurrency to Supersede Stale Runs

When a pull request receives rapid consecutive commits, older runs may still be executing. Results from older commits generally no longer help decide whether to merge the newer commit. Concurrency controls can limit simultaneous runs in the same group and cancel older runs when a newer run arrives.

GitHub Actions example:

~~~yaml
concurrency:
  group: ci-${{ github.workflow }}-${{ github.event.pull_request.number || github.ref }}
  cancel-in-progress: true
~~~

The concurrency group is formed from the workflow and pull request number; for events without a pull request, the ref is used. When a new run in the same group starts, the currently running instance can be canceled. This suits checks that can safely restart from scratch on the latest commit.

Do not enable automatic cancellation for every workflow. A release, deployment, or migration task may have already caused external side effects; canceling mid-flight can leave an incomplete state. For such tasks, design safe shutdown steps, locking mechanisms, and resumption or recovery capabilities.

### Concurrency Is Not Absolute Deduplication

Concurrency limits or supersedes runs within the same group. It does not prove two events are identical, does not guarantee an operation executes only once, and does not replace idempotency. One workflow may finish before the next run arrives; a run in another group may execute in parallel; or the system may redeliver an event after a job has already performed an action.

Use concurrency to manage resources and eliminate stale results. Use event filters and identification keys to avoid creating unnecessary work. Use idempotency to protect operations with external side effects.

## 8. Protecting Operations with Idempotency

An **idempotent** operation can be executed multiple times with the same inputs without duplicating or corrupting the final state. This is especially important for deployments, release creation, artifact uploads, notifications, or external system updates.

For example, before creating a release for tag v2.4.0, the system checks whether a release with the same tag and the same artifact digest already exists. If it does, the workflow verifies and returns the existing result instead of creating a second release.

An idempotency key can be constructed from:

- Repository or project.
- Target environment.
- Version or tag.
- Artifact digest.
- Action type, such as deploy or publish.

The receiving system should store the key and processing outcome in a consistent store. If two requests with the same key arrive simultaneously, only one is permitted to execute the side effect; the other receives the existing result or an in-progress status. Checking first and writing later without a uniqueness constraint still allows two concurrent requests to pass the check simultaneously.

For external APIs, prefer passing an idempotency key when supported by the API. When unsupported, implement state reconciliation after timeouts because the client may not know whether the previous request succeeded.

## 9. Handling Duplicate Webhook Deliveries and Retries

If building a custom webhook receiver to trigger pipelines, process deliveries following this flow:

1. Verify signature and sender source before trusting the payload.
2. Read the delivery ID or event ID supplied by the sender.
3. Record the ID in a store with a uniqueness constraint.
4. If the ID has already been processed, return an appropriate success response without triggering new actions.
5. If it is a new event, record receipt status and enqueue the work.
6. Workers process tasks using an idempotency key and update status to succeeded or failed.
7. Allow bounded retries for transient errors and keep traces for reconciliation.

Do not keep the webhook HTTP connection open during long-running builds or deployments. The receiver should acknowledge receipt promptly after durable persistence, then process asynchronously.

A delivery ID identifies a single notification delivery attempt; it does not necessarily identify a code change. Two different events can describe the same commit. Therefore, the system may need both an event ID to prevent reprocessing deliveries and a business key to coalesce requests sharing the same target.

## 10. Different CI Platforms Have Different Mechanisms

The general principle is selecting event sources, limiting actions, and protecting repeated operations. Syntax and semantics of each mechanism vary by platform.

### GitHub Actions

- Use the on section to select events, branches, paths, and actions.
- Use if conditions at the job or step level to restrict work based on event payloads.
- Use concurrency to limit runs in the same group and optionally cancel stale runs.
- When using a merge queue, configure the merge_group event and ensure required checks report on the merge group.

### GitLab CI

You can use workflow rules to select pipeline sources and prevent creating pipelines outside desired flows. The example below prioritizes merge request pipelines and push pipelines on the default branch:

~~~yaml
workflow:
  rules:
    - if: '$CI_PIPELINE_SOURCE == "merge_request_event"'
    - if: '$CI_COMMIT_BRANCH == $CI_DEFAULT_BRANCH'
    - when: never
~~~

This rule is a minimal example. Repositories may also need schedules, tags, triggers, or child pipelines. Inspect the pipeline types created when both a push and a merge request exist to avoid missing required checks.

GitLab resource_group can serialize jobs sharing a resource, such as deploying to the same environment. It resolves concurrency contention; on its own, it does not prove two pipelines are duplicates and does not eliminate an already-created pipeline.

### Jenkins and Other Systems

For Jenkins or self-managed CI systems, inspect webhook triggers, SCM polling, multibranch indexing, build causes, and resource-locking mechanisms. If both webhooks and polling detect a commit, two builds may appear. Pick one primary detection mechanism or apply build-recognition logic by repository, ref, and revision.

Option names vary across versions and plugins. Test the actual behavior of trigger plugins, especially with retries, multibranch pipelines, and builds triggered by upstream jobs.

## 11. Observing and Diagnosing Duplicate Runs

To verify whether trigger policies work effectively, every workflow run should record at a minimum:

- Event name and action.
- Repository, branch/ref, and pull request number if applicable.
- Head SHA, merge SHA, or merge group ID depending on context.
- Workflow name, job name, and run ID.
- Delivery ID if provided by the event source.
- Reason a job ran or was skipped.
- Relevant concurrency or idempotency key.
- Result, start time, and end time.

A dashboard can track:

| Metric | Meaning |
|---|---|
| Workflow runs per commit or PR | Detects the same change triggering too many times |
| Duplicate jobs by check type | Identifies which builds/tests run repeatedly |
| Runs canceled due to concurrency | Indicates many stale sessions are being created |
| Runner queue time and consumed runner minutes | Evaluates the cost of redundant triggers |
| Redelivered webhook rate | Detects webhook or receiver issues |
| Duplicate publish/deploy count | Identifies risk of external side effects |
| Pending required check rate | Detects filters dropping necessary results |

When seeing two runs close together, compare event, SHA, PR number, merge context, workflow, and job. Never conclude duplication solely from start timestamps or branch names.

## 12. Testing Trigger Policies Before Rollout

Trigger changes can unintentionally drop a required check or skip a release branch. Before rolling out broadly, build a scenario matrix and verify expected outcomes:

| Scenario | Expected Outcome |
|---|---|
| Push commit to feature branch without PR | Run branch CI if the team requires standalone checks |
| Push commit to branch with open PR | Run the exact PR check suite; do not spawn an extra push suite duplicating the same goal |
| Open a new PR | Create required checks for the PR |
| Push new commit to PR | Re-verify the new SHA and invalidate old results as appropriate |
| Change PR labels or title | Do not re-run source code tests unless there is a dependency |
| Close and reopen PR | Apply re-verification policy based on state and changes since the last run |
| Merge into main branch | Run post-merge CI and required artifact creation steps |
| Merge queue creates merge group | Report all required checks on the merge group |
| Create tag or release | Create only one release for the same version and artifact |
| Webhook redelivered | Create no additional actions for the same delivery |
| User triggers manual rerun | Re-run intentionally and record the reason |

Beyond the scenario table, inspect logs from several real runs and confirm branch protection or merge rules still receive required checks. When changing configurations on critical repositories, roll out first on a test repository or a low-risk workflow.

## 13. Common Design Mistakes

### Using Concurrency as the Only Deduplication Mechanism

Concurrency can cancel or queue runs, but it does not guarantee external side effects happen only once. Add idempotency to publish, deploy, and webhook operations.

### Using Only Commit SHA as the Key

The same head SHA can be checked against different target branches or merge contexts. Keys must accurately reflect the verification goal.

### Overlooking the Merge Queue

If the main branch requires checks from the merge queue while the workflow listens only to pull_request and push, the merge group may never receive required checks. Add and verify a dedicated trigger for the merge queue flow.

### Filtering Paths Too Narrowly

Changes to build scripts, lockfiles, or shared configurations can affect many components. Path filters must account for indirect dependencies and provide a way to run broad checks when needed.

### Canceling Every Workflow on New Versions

A CI run may be safe to cancel; a deployment or migration run may not. Enable cancel-in-progress only for work that can stop and restart safely.

### Failing to Record Why a Job Was Skipped

A job not running could result from a valid condition, misconfiguration, or missing data. Logging conditions and events explicitly helps distinguish intended behavior from configuration errors.

### Assuming Retries Are Always Safe

A retry can repeat an operation that actually succeeded before the client received the response. Before retrying, check state or use an idempotency key to avoid duplicate releases, deployments, or notifications.

## 14. Practical Rules

- Identify the verification goal and input context before deciding whether two triggers are duplicates.
- Choose the authoritative event source for each check type: pull request, main branch push, merge queue, tag/release, or schedule.
- Filter events, actions, branches, and paths at the workflow level when appropriate; use job-level conditions for differences within a workflow.
- Use concurrency to curtail stale sessions, but cancel only work that can stop safely.
- Use idempotency keys and state checks before performing external side effects.
- For webhook receivers, authenticate the source, persist delivery IDs, and process asynchronously with retry support.
- Preserve all required checks for pull requests and merge queues; verify branch protection after changing triggers.
- Monitor runs by commit, PR, event, and check type to uncover real duplication.

Avoiding duplicate runs does more than save runner minutes. Clear trigger policies make CI results easier to understand, keep required checks reliable, and make release operations safe when retries or multiple simultaneous events occur. When a change must be verified in multiple contexts, keep the runs that serve distinct purposes; when they merely repeat the same check on the same input, consolidate trigger sources or apply appropriate controls.
