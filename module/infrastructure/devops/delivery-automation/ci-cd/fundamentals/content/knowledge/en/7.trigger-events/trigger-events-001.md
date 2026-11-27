# Triggering by Push, Pull Request, Version Tag, and Schedule

A trigger is a rule that determines when a CI/CD pipeline starts running. Choosing the right trigger events helps a team verify changes at the right time, use resources efficiently, and control who or which changes can move the workflow toward release.

The four common event categories are push, pull request, version tag, and schedule. A push reflects new commits sent to a repository. A pull request opens a checkpoint before changes are merged. A version tag, typically a Git tag, marks a source code milestone with release significance. A schedule triggers tasks that do not directly depend on a new commit, such as security scanning, compatibility checks, or pipeline health aggregation.

These events can coexist in the same CI/CD system, but they should not automatically perform the exact same work. A pipeline needs to distinguish the goal, source code scope, access permissions, run conditions, and impact of each trigger. This lesson explains how to design these triggers, avoid duplicate runs or missed events, protect secrets, and preserve traceability from event to result.

## 1. Triggers in CI/CD Architecture

A trigger is the signal that initiates a workflow or pipeline. The CI/CD platform receives an event from Git, a schedule, or an authorized action, then evaluates filters and conditions to decide whether to create a run.

Three concepts should be distinguished:

- **Event:** what happened, for example a commit was pushed or a pull request was opened.
- **Filter:** restricts which events are of interest, for example only pushes to the main branch or only changes inside the API service directory.
- **Condition:** decides whether a job or step executes within that run, for example only publishing an artifact when the event is a push to a release branch.

Overview diagram:

~~~mermaid
flowchart TD
    A["Git / schedule / user action"] --> B["Event received by platform"]
    B --> C["Evaluate event filter"]
    C --> D{"Matches filter?"}
    D -- "No" --> E["Do not create pipeline run"]
    D -- "Yes" --> F["Create pipeline run"]
    F --> G["Evaluate job conditions"]
    G --> H["Run matching jobs"]
    H --> I["Store results, logs, and metadata"]
    I --> J["Update status / notifications"]
~~~

For example, a push to a feature branch might trigger linting and unit tests. That same commit, once merged into the main branch, might additionally trigger integration tests and artifact packaging. A version tag might trigger a release candidate verification and release preparation workflow. A nightly schedule might scan all dependencies or run regression tests.

Triggers determine when a run starts; stages inside the pipeline determine the work performed. Do not put all business decisions into trigger conditions so complex that they become hard to review. Keep event filters easy to understand and use job conditions for decisions that depend on data from the run.

## 2. Triggering by Push

A push event occurs when one or more commits are sent to a repository ref, typically a branch or tag. This is a common trigger for verifying source code after each update.

### 2.1. When to Use a Push Trigger?

A push can serve multiple goals:

- Fast checks on a feature branch to detect errors right after commits are pushed.
- Verification of a shared branch after a merge.
- Building and packaging artifacts from accepted commits.
- Updating documentation, preview websites, or integration environments.
- Triggering a release workflow when pushing a version tag, if the platform supports a dedicated tag event or push filter.

A repository can restrict push triggers to specific branches:

| Branch | Common Goal | Suitable Tasks |
|---|---|---|
| Feature branch | Early feedback for the author | Lint, unit tests, affected builds |
| Integration branch | Confirm combined state | Integration tests and selective regression |
| Main branch | Confirm release source | Build, deep tests, artifact creation |
| Maintenance branch | Verify patches for supported versions | Compatibility tests and maintenance version builds |

Not every push needs deployment permissions. A push from a feature branch may run tests in an ephemeral environment, whereas deploying to a shared environment is only permitted from protected branches and after required gates pass.

### 2.2. Branch and Path Filters

Branch filters restrict the pipeline to relevant branches. Path filters restrict runs to when files in a specific area change.

Conceptual policy example:

~~~yaml
push:
  branches:
    - main
    - release/*
  paths:
    - services/orders/**
    - shared/contracts/**
~~~

This example means listening for pushes on the main branch or release branches, while limiting the scope of changes to the specified paths. Syntax and how branch filters combine with path filters vary across CI/CD platforms; always confirm the exact AND/OR logic in the documentation of the platform in use.

Path filters are useful for monorepos, but they can miss indirect impacts. A change in a shared library can affect multiple services; a change to a build script, dependency lockfile, or pipeline configuration can affect the entire repository. Therefore, a fallback rule is needed to run broad checks when changes cannot be safely categorized.

### 2.3. Multi-Commit Pushes and Overlapping Runs

A single push can contain multiple commits. Pipelines typically check the final state of the ref at the time the event is processed, though details depend on the platform. If multiple consecutive pushes occur, multiple runs may compete for resources.

Control measures:

- Use concurrency groups per repository, branch, or pull request where appropriate.
- Cancel older runs when a new commit supersedes the input and old results are no longer valuable.
- Retain runs used for releases or investigations; do not cancel them merely because a new push arrived.
- Ensure deployment jobs cannot allow an older run to overwrite a newer version.
- Associate results with a specific commit SHA rather than recording only the branch name.

Canceling older jobs saves resources, but must be designed carefully. A run that is currently deploying or running a migration may not be safe to stop mid-flight. Distinguish cancelable verification jobs from operations that mutate environment state, which require locking and completion handling.

## 3. Triggering by Pull Request

A pull request (PR), or merge request on some platforms, is a proposal to merge changes from a source branch into a target branch. PR triggers automate checks before changes enter a shared branch.

### 3.1. Common Trigger Moments

A PR pipeline can run when:

- A PR is first opened.
- A PR receives new commits or is updated.
- A PR is reopened after being closed.
- PR labels or metadata change.
- There is a sync operation with the target branch.
- A PR is added to a merge queue or merge train.

Not every platform treats all metadata changes as the same PR event. Choose the exact event types needed to avoid re-running tests when only non-code changes occur.

### 3.2. Goals of a PR Pipeline

A PR pipeline typically performs:

- Formatting, linting, and static analysis.
- Unit tests and candidate builds.
- Targeted component or integration tests.
- API contract, schema, or configuration checks.
- Policy-based secret, license, and dependency checks.
- Creating a preview or ephemeral environment if the product needs visual review.

Results must be linked to the correct PR and commit. Reviewers need to know which checks are required, which are informational only, and why a job was skipped.

### 3.3. Checking the Commit or the Expected Merge Result?

There are two common input types:

- **Head commit:** the latest commit on the PR's source branch.
- **Merge candidate:** the simulated result of merging the source branch with the current target branch.

Checking the head commit validates the author's changes in the isolated state of the source branch. However, if the target branch has changed, the head commit may not reflect the upcoming merge outcome. A merge candidate helps catch integration errors caused by combining changes before merging.

For repositories with many concurrent PRs, a merge queue or merge train can test a combination of changes in the expected order. What matters is that the verified state matches the commit that actually gets merged. If the target branch or PR changes after verification, older results may no longer be valid.

### 3.4. PRs from Forks and Untrusted Code

PRs from forks may contain code or scripts controlled by someone outside the repository. A build or test step may execute that code. Therefore:

- Do not grant production secrets to jobs processing PRs from forks or untrusted sources.
- Restrict workflow token write permissions.
- Do not allow PR jobs to arbitrarily publish packages or deploy to shared environments.
- Isolate runners and test data from sensitive environments.
- Grant elevated permissions only after review or through an organization-approved trust mechanism.
- Do not assume masking secrets in logs protects them if malicious code can read environment variables.

PR pipelines should be designed according to the principle of least privilege. Needing to run tests does not imply access to every resource that a release pipeline has.

## 4. Triggering by Version Tag (Git Tag)

A Git tag marks a specific commit. Version tags such as v1.4.0 or v2.0.0 are commonly used to identify release milestones. When a tag is created and pushed to the remote, the CI/CD platform can trigger a release pipeline.

### 4.1. How Do Tags Differ from Branches?

A branch is a ref that can move as new commits arrive. A tag is typically used to mark a specific commit and is expected to remain fixed after release.

| Characteristic | Branch | Version Tag |
|---|---|---|
| Meaning | Ongoing line of development that continues changing | Source code milestone with a version identity |
| Pointer target | Moves when new commits are added | Usually fixed after creation |
| Common triggers | Push, pull request | Tag push or release event |
| Goal | Integration and development | Building, verifying, and releasing a version |
| Governance rules | Branch protection, review, merge | Restrict permissions to create, edit, or delete tags |

Tags can be lightweight tags or annotated tags. Annotated tags contain metadata such as author, timestamp, and message, making them better suited for marking intentional releases. Regardless of which type is used, tag creation must be protected to prevent release tags from being moved or replaced unintentionally.

### 4.2. Version Tags Triggering the Release Pipeline

A version tag can trigger the following steps:

1. Identify the commit that the tag points to.
2. Validate the tag name against the project's versioning rules.
3. Confirm the commit resides on an allowed branch or release point.
4. Run the build and required test suites.
5. Generate release artifacts and metadata.
6. Compute digests, sign artifacts, or generate provenance if required by the process.
7. Publish to a registry or release repository.
8. Wait for approval and deploy according to environment policies.
9. Record results, version, and links to the pipeline run.

For example, a Semantic Versioning tag rule might be vMAJOR.MINOR.PATCH, such as v2.3.1. The MAJOR number represents incompatible changes under the project's API policy; MINOR represents backward-compatible features; PATCH represents backward-compatible bug fixes. A project may follow its own conventions, but consistent format validation is required.

### 4.3. Do Not Let Tag Names Blindly Dictate Artifacts

A tag is a human-readable name, while the commit SHA and artifact digest identify the exact contents. A release pipeline should record all three:

- The tag name, for example v2.3.1.
- The commit SHA that the tag points to.
- The digest of the artifact produced from that commit.

If a tag is deleted and recreated pointing to a different commit, the same version name can represent different content. For registries that support immutable tags or release protection policies, enable mechanisms to prevent overwriting. If a moved tag is detected, treat it as a release governance issue.

### 4.4. Separating Release Tags and Pre-Release/Experimental Tags

A repository may use multiple conventions:

- Stable release tag: v2.3.1.
- Pre-release tag: v2.4.0-rc.1 or v2.4.0-beta.2.
- Experimental build tag: according to internal conventions.

The pipeline must distinguish these types. Pre-releases may be published to a separate registry or testing environment; they should not automatically be treated as stable production builds without passing a release gate.

## 5. Triggering by Schedule

Scheduled triggers run workflows on a schedule, typically using cron expressions or the platform's scheduling mechanism. They are suitable for tasks that do not need to wait for a new Git event.

Examples:

- Scanning dependencies and known vulnerabilities nightly.
- Running full regression tests on the main branch.
- Running compatibility tests across multiple runtime versions.
- Running weekly load tests or soak tests.
- Checking configuration or documentation drift.
- Aggregating build times, flaky tests, and pipeline health.
- Cleaning up artifacts or ephemeral environments according to policy.

### 5.1. Cron Schedules and Timezones

Cron typically describes minute, hour, day of month, month, and day of week. Example:

~~~cron
0 2 * * 1-5
~~~

This expression represents 02:00 Monday through Friday in the timezone used by the platform. Many CI/CD platforms interpret schedules in UTC, while some offer explicit timezone configuration. Check the platform documentation to avoid running at the wrong time, especially when teams operate across timezones or observe daylight saving time.

Do not assume cron schedules always run down to the exact second or never experience delays. Platforms may delay jobs under heavy load or apply rate limits to scheduled runs. If a task has strict deadlines, implement monitoring for the last run and alert when a schedule is missed.

### 5.2. Scheduled Workflows Must Specify the Ref

A scheduled workflow typically runs on a default branch or ref as configured by the platform. Clarify the following:

- Does it run on the main branch or a maintenance branch?
- Does it need to run on all supported branches?
- Are results tied to the commit SHA at the start of the run?
- If the branch changes while the job is running, do inputs remain consistent?
- Should the previous run be canceled if a new schedule arrives before the old one finishes?

Recording the commit SHA at startup keeps results traceable. If a schedule runs full tests across multiple branches, use a matrix and concurrency limits to avoid exhausting all runners.

### 5.3. Idempotency and Overlapping Schedules

Scheduled jobs may retry after failures or be triggered twice by manual execution. Jobs should be idempotent whenever possible: running multiple times with the same inputs should not create corrupted state or unintended side effects.

For example, a report aggregation job should record the reporting period and update the same record rather than creating unlimited duplicates. A cleanup job should only delete expired resources based on explicit labels or metadata. A load test job should be restricted to one run per environment to avoid skewing results.

## 6. Combining Multiple Triggers Without Duplicate Runs

A single workflow can listen to both push and pull request events. However, the same change can generate multiple runs: the PR is updated, commits are pushed to the source branch, and then the PR is merged into the target branch.

Duplicate execution is not always wrong. A PR check run and a main branch verification run serve different purposes. Problems arise when overlapping runs perform the same resource-intensive work or both deploy to the same environment.

Ways to organize triggers:

- Use separate workflows or jobs for PR validation, branch integration, and release.
- Use job conditions to run publish steps only when the event originates from an allowed branch or tag.
- Use concurrency groups per PR or ref to limit concurrent runs of the same scope.
- Cancel older verification runs when a new commit arrives, if old results are no longer valuable.
- Ensure deployment actions have environment locks or serialization mechanisms.
- Do not reuse check results if the commit, configuration, dependencies, or input environment have changed.

Guidance table:

| Trigger | Primary Tasks | Typical Required Permissions |
|---|---|---|
| Feature branch push | Fast checks, candidate build | Repository read, write check results if needed |
| Pull request | Review checks, test changes and merge candidate | Least privilege, no production secrets |
| Main branch push | Full validation, build and publish artifact per policy | Scoped registry write permissions |
| Version tag push | Verify and create release | Protected release/publish permissions |
| Scheduled | Scan, regression, performance, or reporting | Read permissions and job-specific environment permissions |

## 7. Designing Safe Filters and Conditions

A clear trigger definition should declare:

1. Which events are listened to?
2. Which refs or branches are accepted?
3. Are there path filters or tag patterns?
4. What conditions allow each job to run?
5. Which jobs are allowed to access secrets?
6. Which jobs are allowed to publish or deploy?
7. How are multiple concurrent runs handled?

Do not apply one shared condition to the entire workflow if individual jobs have different permissions and purposes. For example, a PR may run tests, but a package publishing job should only run on a push to the main branch or a protected tag.

Conceptual logic example:

~~~yaml
workflow:
  triggers:
    - pull_request
    - push_to_main
    - version_tag
    - scheduled_scan

  jobs:
    validate:
      runs_on:
        - pull_request
        - push_to_main
        - version_tag

    publish:
      condition:
        event_is: version_tag
        tag_matches: "v*"
        release_checks_pass: true

    scheduled_security_scan:
      condition:
        event_is: scheduled_scan
~~~

This is an illustrative model, not platform-specific syntax. When implementing in GitHub Actions, GitLab CI, Jenkins, or another system, use the exact event names, filters, and expressions of that platform.

### 7.1. Caution with Path Filters

Path filters can save resources, but they can also introduce verification gaps. Situations to watch for:

- Changes to shared files affecting multiple services.
- Changes to dependency lockfiles affecting the entire project build.
- Changes to pipeline definitions or build scripts altering how all jobs behave.
- Deleted or renamed files causing filters to inspect only the new paths.
- Pull requests containing multiple commits across multiple areas.
- Platform limits on the number of files or commits evaluated by filters.

When the exact scope cannot be determined, run the broad test suite according to policy. Skipped statuses must be explained and must never appear as though tests ran and passed.

### 7.2. Caution with Tag Filters

Tag patterns must be strict enough not to trigger release pipelines for experimental tags or invalid names. For example, the pattern v* can match both v-next and v2.0.0-rc.1. If only stable releases are desired, validate the version format and pre-release conditions inside the job.

Beyond the pattern, verify that the tag was created from a valid commit, the creator is authorized, and the tag was not moved under repository policies.

## 8. Protecting Permissions and Secrets by Event Type

Different triggers carry different trust levels. A PR from a fork, a push from a protected branch, and a release tag should not share the same permissions by default.

Principles to apply:

- **Least privilege:** grant only the read, write, publish, or deploy permissions a job genuinely needs.
- **Secret segregation:** tests do not need production secrets; release jobs receive secrets only after protection conditions are satisfied.
- **Appropriate runners:** untrusted code runs on isolated runners, never sharing environments with sensitive credentials.
- **Short-lived credentials:** prefer ephemeral tokens or temporary identities when the platform supports them.
- **Branch and tag protection:** restrict who can merge to the main branch, create release tags, or approve deployments.
- **Log controls:** avoid printing tokens, sensitive environment variables, or credentials to logs.
- **Environment approvals:** use approvals or protection rules for controlled environments.

A triggered workflow does not mean every job is authorized to perform every action. Permissions must be scoped at the specific job or step level. This is especially critical when a single workflow handles both untrusted PRs and official releases.

## 9. Ensuring Run Traceability

Each pipeline run should record metadata so operators can explain why it ran and what it verified.

Useful information includes:

| Metadata | Purpose |
|---|---|
| Event name | Know whether the trigger was push, PR, tag, or schedule |
| Event timestamp | Know when the platform received the event |
| Repository and ref | Identify the source of changes |
| Commit SHA | Identify the exact source code |
| PR number and base/head SHA | Trace changes and target branch |
| Tag name and target SHA | Identify the release milestone |
| Schedule identifier | Know which schedule a periodic run belongs to |
| Workflow version | Know which pipeline configuration executed |
| Actor or initiator | Trace the triggering actor in accordance with privacy policies |
| Job result and artifact digest | Link verification results to outputs |

For releases, the traceability chain should connect the tag, commit SHA, pipeline run, test report, artifact digest, approver or approval policy, and target environment. For scheduled scans, record the scanned commit or dependency version, timestamp, scope, and result.

If a run is skipped due to a filter, there should also be a way to explain the reason in system status or logs. This helps distinguish no matching changes from a trigger configuration error.

## 10. Example Scenario: From Pull Request to Release Tag

Suppose a team is developing an API service and wants to release version 2.3.1.

1. A developer pushes commits to a feature branch. The push trigger runs linting, unit tests, and a candidate build.
2. The developer opens a pull request. The PR trigger re-runs required checks on the commit or merge candidate and displays results to reviewers.
3. The PR is updated. The older run may be canceled if it only checked an outdated commit; the new run is tied to the current head SHA.
4. The PR meets all criteria and is merged into the main branch. The push trigger on the main branch runs integration tests, selective regression tests, and creates an artifact.
5. The artifact is stored with its commit SHA, pipeline run ID, and digest. It can be deployed to a test environment for verification.
6. When the team decides to release, an authorized user creates and pushes tag v2.3.1 on the verified commit.
7. The tag trigger runs the release pipeline: validates the tag format, confirms the target commit, verifies or builds the artifact per policy, checks provenance, and waits for approval if needed.
8. The artifact is published or promoted to the target environment. The pipeline confirms the running version and stores the results.
9. Scheduled workflows continue scanning dependencies, running regressions, and monitoring post-release system health.

This scenario illustrates that each trigger plays a distinct role. Push supports the development loop and shared branch validation; PR gates merging; tag marks intentional releases; schedule maintains ongoing checks after changes have been integrated or released.

## 11. Common Mistakes When Designing Triggers

| Symptom | Possible Cause | Resolution |
|---|---|---|
| Push does not trigger pipeline | Branch does not match filter, workflow not recognized, or incorrect webhook permissions | Check ref, workflow configuration, and event history |
| PR has no checks | Wrong PR event type, path filter excludes the run, or workflow lacks permission to update checks | Check event, filter, and permissions |
| No main branch pipeline after merge | Push filter does not match target branch or merge mechanism does not emit expected event | Check actual events and branch configuration |
| Release runs on wrong tag | Pattern too broad or missing version format validation | Validate tag and separate pre-releases |
| Same change runs multiple pipelines | Both push and PR trigger, or multiple equivalent events fire | Separate jobs, use concurrency and conditions |
| Schedule runs at wrong time | Wrong timezone or cron unsupported as expected by platform | Check timezone, syntax, and actual schedule |
| Overlapping scheduled runs | Job takes longer than interval or lacks concurrency limit | Set concurrency limits and handle idempotency |
| PR pipeline reads sensitive secrets | Overly broad workflow permissions or shared runners | Reduce permissions, isolate runners, and protect secrets |
| Tag altered after release | No tag protection or registry allows overwriting | Enable tag protection and immutable artifacts |
| Job skipped silently | Filter or condition lacks explanatory status | Log skip reason clearly and provide fallback |

When investigating, start from the actual event received by the platform, then inspect filters, job conditions, and access permissions. Do not look only at job logs, because the job may never have been created if the trigger or filter did not match.

## 12. Practice Roadmap

You can practice on a sample repository following these steps:

1. **Create a push workflow:** trigger on feature branches and the main branch, running lint, unit tests, and build.
2. **Create a PR workflow:** run required checks when a PR is opened or updated; attach status to both the commit and merge candidate if supported by the platform.
3. **Test path filters:** modify a module and confirm only relevant tests are selected; then modify a shared file to test the fallback.
4. **Create a test release tag:** create a tag following the version format and confirm the pipeline checks the target commit and metadata.
5. **Create a scheduled workflow:** run a scan or regression task on a cron schedule; verify timezone and input ref.
6. **Test overlapping runs:** push multiple consecutive commits and observe concurrency, cancellation, and deployment state.
7. **Test security:** use a PR from a fork or untrusted source in a safe environment to confirm there are no production secrets or unexpected write permissions.
8. **Verify traceability:** from a release, trace back to the event, tag, commit SHA, pipeline run, artifact digest, and verification results.

### Completion Criteria

Learners can consider the practice complete when they can demonstrate:

- Distinguishing between event, filter, and condition.
- Designing push triggers for appropriate branches.
- Designing PR triggers and explaining the difference between head commit and merge candidate.
- Triggering a release pipeline via version tag and verifying the target commit.
- Creating a scheduled workflow with clearly defined timezone and ref.
- Controlling path filters, tag filters, and fallbacks when scope is unclear.
- Preventing duplicate runs or concurrent deployments that overwrite newer versions.
- Scoping secrets and permissions by event trust level.
- Tracing every run back to its triggering event and input commit.

## Conclusion

Push, pull request, version tag, and schedule are four essential trigger categories in a CI/CD system. Push supports verification when code changes; pull request establishes a review gate before merging; tag marks an intentional release milestone; scheduled triggers maintain checks that do not depend on a new commit.

Reliable trigger design requires combining clear events, filters, and conditions, managing concurrency, specifying input refs, protecting permissions by event source, and storing sufficient metadata for traceability. When each trigger has an appropriate purpose and permission scope, the pipeline runs the right tasks at the right time and produces trustworthy evidence across the entire release flow.
