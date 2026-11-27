# Identifying Handoffs and Error-Prone Manual Steps

A CI/CD workflow can automate many commands yet still produce faulty releases if information is lost or altered as it moves from one person, system, or stage to the next. For instance, a team builds the right commit, but an operator selects the wrong image during deployment; an approver reviews the report for one version while the pipeline releases another; or the on-call team receives a "deployment succeeded" alert without knowing which dashboard to check or how to roll back.

Such transfer boundaries are called **handoffs**. They are points where responsibility, decision authority, or data passes from one party to another. Properly identifying handoffs shows the team what information must be transferred, who confirms receipt, and what conditions permit work to proceed. The goal is to reduce errors caused by mis-selection, transcription mistakes, skipped steps, or acting on stale state.

## 1. What Is a Handoff?

A handoff occurs when a piece of work or output leaves the control boundary of its producer and is taken over by another party. The receiver can be:

- Another system, such as CI transferring an artifact to a registry.
- Another stage in the pipeline, such as the build stage passing outputs to the test stage.
- Another person or team, such as developers handing a release request to an approver.
- Another environment, such as staging promoting the same artifact to production.
- Operations teams assuming ownership of the service after deployment.

A handoff is more than sending a file or clicking a button. It also transfers context: which version is being handled, which checks were verified, what risks remain, which permissions are in use, and who owns the next step.

A reliable handoff must answer six questions:

1. **Who is the sender and who is the receiver?** Accountable parties on both sides must be identified.
2. **What is being handed off?** Explicitly specify the artifact, request, configuration, change, or decision being transferred.
3. **Which identifiers are used?** Examples include commit SHA, pipeline run ID, artifact digest, deployment revision, or change request ID.
4. **What evidence accompanies it?** Test reports, security scan results, logs, approvals, or verification outcomes.
5. **How does the receiver acknowledge receipt?** Ability to validate data, accept, reject, or request additional details.
6. **How are errors handled?** Define where to halt, how to retry, whom to notify, and how to recover.

If any of these answers live only in someone's memory or a scattered chat message, that handoff relies too heavily on human fallibility.

## 2. The Handoff Contract

Each handoff can be described by a concise contract. This contract clarifies responsibilities and defines what data the receiver is permitted to trust.

| Component | What to Define | Examples |
|---|---|---|
| Sender | System or role producing the output | Build job in the pipeline |
| Receiver | System or role accepting the output | Artifact registry |
| Handoff trigger | What initiates the transfer | Build finishes and gates pass |
| Identifier | Unique key identifying the exact object | Commit SHA and image digest |
| Payload | Data or product being transferred | Image, metadata, reports |
| Acceptance criteria | What the receiver validates | Matching digest, valid signature |
| Acknowledgment | How successful receipt is recorded | Registry returns stored digest |
| Failure handling | How to reject, retry, or escalate | Halt promotion, retain logs |

The example below is purely a conceptual model illustrating the contract, not mandatory syntax for any CI/CD platform:

```yaml
handoff:
  name: build-to-registry
  sender: build-job
  receiver: container-registry
  trigger: build-and-scan-passed
  identity:
    commit: "COMMIT_SHA"
    artifact_digest: "IMAGE_DIGEST"
  evidence:
    - build_metadata
    - vulnerability_scan_report
  acceptance:
    - artifact_upload_succeeded
    - stored_digest_matches
  on_reject: stop_release
```

Contracts should be enforced through automated checks wherever possible. For example, a registry can verify the digest after upload; a deploy step can reject manifests missing a digest; a production gate can require approval bound to that exact digest. For decisions requiring human judgment, the system must still capture identity, timestamp, approved target, and inspected evidence.

## 3. Common Handoffs in a CI/CD Flow

### 3.1. From Git to the Pipeline

The handoff begins when a Git event triggers a CI/CD run. Transferred details include repository, event type, branch or tag, commit SHA, pull request, and actor identity.

Common errors:

- Running the pipeline on the default branch when the release request targets a release branch.
- Using a branch name as an identifier and accidentally pulling a newer commit than the one that was tested.
- Manually typing a commit SHA or tag with missing characters.
- Re-running an old pipeline without checking whether the source has changed.
- Letting code from an untrusted pull request access secrets or publish permissions.

**Controls:** the pipeline must capture the commit SHA upon receiving the event and pass this identifier through every stage. When a user triggers a manual run, the UI should display the repository, ref, commit, and target environment for confirmation. Permissions for jobs running on untrusted code must be restricted; never grant production secrets or release registry write access solely because a pipeline was triggered.

### 3.2. Between Pipeline Stages

One stage often produces data consumed by the next stage. This is a handoff between jobs or runners, even when everything resides in the same pipeline file.

Common errors:

- A downstream job assumes files created by an upstream job still exist on a different runner.
- Passing data through undeclared or overwritten environment variables.
- Checking only the exit code while ignoring required test reports or metadata.
- Using leftover files in a workspace from an earlier run.
- A downstream stage independently pulling the latest source instead of using the verified snapshot.

**Controls:** declare outputs and dependencies explicitly; store intermediate artifacts keyed by run ID; verify file existence, format, and origin before use. Each job must receive the exact inputs declared for it. Never rely on leftover workspace or cache state. If a stage fails to produce a mandatory output, the pipeline must halt right there and report exactly which output is missing.

### 3.3. From Build to the Artifact Registry

After building, the product must be packaged and moved into storage accessible to downstream environments. Artifacts may be binaries, packages, container images, or deployment bundles.

Common errors:

- Manually copying image names or version tags between tools.
- Re-tagging a different image without updating reports.
- Pushing artifacts to the wrong repository or project.
- Storing only mutable tags like `latest` without recording the digest.
- Marking a build successful even though upload did not complete or the artifact cannot be pulled back.

**Controls:** let the pipeline publish artifacts using a least-privilege machine identity; capture the digest returned by the registry; pull back or verify the artifact by digest; store build metadata, commit SHA, and scan reports alongside the artifact identifier. Tags like `2.4.0` help humans look up releases, while digests identify the exact content. Never substitute eyeballing a tag name for content verification.

### 3.4. From Artifact to the Deployment Environment

This is a high-risk handoff because a single wrong selection can directly affect users. Receivers include deployment platforms, clusters, namespaces, cloud accounts, or target servers.

Common errors:

- Picking production instead of staging, or vice versa.
- Choosing the wrong cluster, namespace, region, or cloud account.
- Pasting the wrong image tag from a ticket or chat message.
- Deploying an artifact that has not passed staging.
- Using another environment's configuration or mis-scoped secrets.
- Manual changes on servers causing environment drift from managed configuration.

**Controls:** define environments via controlled configuration and protect production with dedicated permissions. Clearly display service, environment, artifact digest, and impact scope before allowing manual actions. Deploy jobs should accept an approved digest rather than a tag string typed by an operator. Use separate accounts and credentials per environment; never reuse production permissions in test jobs.

### 3.5. From Testing to Release Approval

Test results and security scans become evidence for an authorized approver to decide whether to release.

Common errors:

- Approvers only see a green status without knowing which commit it belongs to.
- Stale reports are reused to approve a newer version.
- Approvers select the wrong ticket or wrong pipeline run.
- Approvals happen in chat without being recorded in the release system.
- The author self-approves a high-risk change even when policy requires independent review.

**Controls:** approval screens must link to the commit SHA, pipeline run ID, artifact digest, test results, and target environment. Decisions must be recorded in the system with approver identity, timestamp, and approval scope. Approvals must expire or require re-evaluation if the artifact, critical configuration, or release scope changes. Enforce two-person review for high-impact actions when organizational policy requires it; avoid turning every trivial change into an unnecessary approval queue.

### 3.6. From Deployment to Operations

After rollout, responsibility gradually shifts from the release team to operations or the on-call service owner. A "deploy succeeded" message is not enough to complete this handoff.

Information that must transfer:

- Service, environment, artifact digest, and deployment revision.
- Deployment timestamp and initiating person or system.
- Configuration changes, feature flags, and migrations executed.
- Post-deployment checks and initial telemetry observations.
- Dashboards, logs, traces, runbooks, and accountable contacts.
- Previous stable version and how to roll back or roll forward.

A common mistake is that the deployment team knows what changed, yet the on-call engineer does not know which metrics to watch, which features are enabled, or which migrations could affect data. Produce a structured release record or operational notification linking to evidence and recovery instructions. Never force on-call engineers to hunt for critical information across multiple chat threads.

## 4. Common Error Patterns in Manual Steps

Manual steps are not inherently wrong. Humans are needed for decisions involving risk, blast radius, and release timing. Problems arise when repetitive tasks require memory, manual entry, or error-prone selection without verification.

| Error Pattern | Manifestation | Possible Consequences |
|---|---|---|
| Selection error | Choosing the wrong branch, artifact, cluster, or environment | Releasing the wrong version or to the wrong target |
| Transcription error | Mistyping characters in a digest, version, URL, or parameter | Artifact not found or referencing the wrong resource |
| Omission error | Forgetting to run migrations, smoke tests, or update release records | Service failure or missing audit trail |
| Sequencing error | Deploying before approval or running migrations out of order | Incompatible system state |
| Stale context | Relying on reports, tickets, or instructions from a prior release | Decisions based on outdated evidence |
| Authorization error | Using personal accounts or overly broad credentials | Hard to audit, wider blast radius |
| Duplicate action | Clicking deploy multiple times without knowing if the prior run finished | Duplicate resources or repeated state changes |
| Superficial verification | Looking only at a green job status without checking the live service | Incidents discovered late |

### 4.1. Selecting the Wrong Target

Humans frequently choose from long lists: repositories, branches, tags, artifacts, clusters, namespaces, and environments. Similar names such as `api-prod`, `api-preprod`, and `api-preview` raise the likelihood of picking the wrong item.

Reduce risk by:

- Using structured dropdown lists instead of free-text fields when valid values are known.
- Displaying full names alongside account, region, and environment.
- Automatically pulling the artifact from the selected pipeline run.
- Requiring explicit confirmation for high-impact operations.
- Validating the target server-side or inside the deploy job before execution.

A confirmation dialog is only useful if it displays details that expose mistakes. A generic "Are you sure?" prompt does not help an operator realize they are deploying to the wrong cluster.

### 4.2. Copying Data and Entering Parameters

Copying digests, versions, endpoints, or configuration variables across multiple windows invites truncation, pasting mistakes, or reusing stale values. The more manual handoffs involved, the higher the error probability.

Prefer passing data through structured outputs, APIs, or artifact metadata. If manual input is unavoidable, validate formats, echo back normalized values, and cross-check against the source. For long identifiers like SHA-256 digests, never ask operators to type them manually. Select artifacts from a list or pull them directly from an approved run.

### 4.3. Omissions and Wrong Ordering

A paper checklist can remind operators, yet steps can still be checked off without actually running. Critical actions such as migrations, toggling feature flags, smoke tests, and updating operational records should be tied to verifiable evidence.

For automatable steps, let the pipeline execute them and store results. For mandatory human steps, require verifiable records such as change ID, executor, and timestamp. Ordering dependencies should be encoded explicitly in pipelines or runbooks in unambiguous sequence.

### 4.4. Retrying Without Knowing Prior State

When a UI hangs or fails to respond, users may click deploy again or re-trigger a job. If the first request was already accepted by the backend, the second run can cause duplicate changes.

Before retrying, verify the state of the previous run using its run ID or deployment revision. Design jobs to be safely repeatable (idempotent) where appropriate; use environment/service locks or duplicate-request detection. For non-idempotent operations, inspect live state and require informed confirmation before proceeding.

### 4.5. Misusing Secrets and Accounts

A convenient yet dangerous habit is sending tokens over chat, saving passwords in temporary files, sharing admin accounts, or pasting secrets into command-line flags. These habits leak credentials and make it impossible for logs to identify who performed an action.

Provision credentials via a secret manager or workload identity mechanism; prefer short-lived credentials; scope permissions by job and environment. Never ask operators to paste secrets into pipeline forms when the platform offers secure provisioning. Logs must record identity and action without recording secret values.

## 5. Separating Human Decisions from Automatable Actions

Do not eliminate every human-in-the-loop step. Some decisions require weighing business impact or accepting risk—such as release timing, policy exceptions, or traffic shifting during an incident. Conversely, copying digests, updating tags, fetching files, and checking rule-based conditions should usually be automated.

| Work Type | Appropriate Handling | Examples |
|---|---|---|
| Risk and priority decisions | Human decides, system records evidence | Approving release during maintenance window |
| Deterministic rule checks | Automated as a gate | Tests pass, digest matches, scan meets threshold |
| Moving data between systems | Automated transfer via structured interfaces | Promoting artifact by digest |
| Emergency exceptions | Human executes under controlled break-glass procedure | Restoring service when pipeline is unavailable |
| Repetitive rule-bound work | Automated with logging | Staging deploy, smoke test, creating release record |

An approval step only has value when the approver holds enough context and authority to decide. If approvers merely click a button to unblock the pipeline without inspecting evidence, the step becomes pure theater. Design approval screens around the change, artifact, environment, passed checks, remaining risks, and recovery plan.

## 6. Measures to Reduce Handoff Errors

### 6.1. Use Immutable Identifiers

Pass commit SHA, artifact digest, and deployment revision through all steps. Avoid relying on branch names, mutable tags, or generic filenames like `build.zip`. Whenever an identifier changes, the system must create a new record and clarify which evidence remains valid.

### 6.2. Validate on Both Sender and Receiver Sides

The sender must prove what source produced the output. The receiver must verify the output satisfies the contract before consuming it. For example, the build job records commit metadata; the registry returns the stored digest; the deploy job verifies the digest belongs to the list of artifacts approved for release.

### 6.3. Encode Policies as Code

Rules defining which branches may release, which vulnerability severities block releases, which environments require approval, and who may deploy should live in versioned configuration or policy code. That allows policy changes to be reviewed and audited just like source code changes.

### 6.4. Restrict Permissions and Separate Duties

Separate build, publish, and deploy permissions when risk warrants it. Test jobs do not need production write access; approvers do not necessarily need permission to modify artifacts; deployment accounts should only affect assigned services and environments. For emergencies, use time-bound break-glass access with logged justification and post-incident review.

### 6.5. Record Acknowledgments and Evidence

Every handoff needs an explicit status: pending, accepted, or rejected. Record sender, receiver, timestamp, object identifier, check outcomes, and rejection reasons. Logs should let you trace backward from a production deployment to the pipeline run, artifact, reports, and commit.

### 6.6. Make Operations Safely Repeatable

Design APIs and jobs so resending the same request does not cause duplicate side effects. Use idempotency keys, environment/service locks, pre-change state checks, or concurrency limits. Where idempotency cannot be guaranteed, surface the status of the previous run so operators can decide accurately.

### 6.7. Provide an Exception Handling Path

The pipeline will not always be available. Runbooks must document how to inspect current state, who has authority to intervene, which commands or actions are permitted, what evidence must be logged, and how to return the system to normal workflow. After using an emergency path, reconcile live state with managed configuration and update the release record.

## 7. Example: Releasing the Wrong Artifact Due to a Manual Handoff

Suppose API version `2.8.1` passed testing in staging. An operator opens the production UI, searches for the image by tag, and accidentally picks `api:2.8.0` because the two entries sit next to each other. The deploy job succeeds because that image exists and is validly formatted, yet users receive the older version.

This failure happened at the handoff from release decision to deployment action. The pipeline only checked whether the image could be pulled; it never verified whether the image matched the approved artifact.

A better-controlled flow works as follows:

1. The pipeline builds the image from an identified commit and records the pipeline run ID.
2. The artifact is published; the registry returns the digest, and metadata is stored alongside test reports.
3. Staging deploys using the digest. Test outcomes are bound to that deployment revision and digest.
4. The approver inspects that exact release record, including commit, digest, reports, and intended production environment.
5. Upon approval, the system records the decision tied to that specific digest.
6. The production job pulls the approved digest from the release record. The operator merely selects the release request rather than retyping a tag.
7. After deployment, the system verifies the running deployment revision uses the approved digest and runs smoke tests.

If the digest in a deploy request mismatches the approved digest, the gate must reject it. This prevents a mis-selection from silently turning into a valid release.

## 8. When to Stop and Require Confirmation

Not every discrepancy requires human approval. However, the pipeline should stop whenever it cannot prove the integrity of a critical handoff. Typical situations include:

- Commit SHA or artifact digest mismatches prior evidence.
- Target environment or deployment identity cannot be determined.
- Mandatory test or scan reports are missing, expired, or belong to a different run.
- Approval decision is not bound to the current artifact and release scope.
- A prior deploy has an unknown status while a re-run is requested.
- Drift or out-of-band changes are detected in the production environment.
- Emergency privileges are needed or a protected gate must be bypassed.

When stopping, the message must specify which condition failed, which identifiers were compared, what evidence is missing, and who can resolve it. Avoid vague alerts like "Deployment failed" that force operators to dig through the entire pipeline manually.

## 9. Handoff Review Checklist

Use this checklist when designing a new pipeline or reviewing an operating release workflow:

- [ ] Boundaries between systems, stages, teams, and environments are mapped out.
- [ ] Every handoff has an explicit sender, receiver, and accountable owner.
- [ ] Transferred data has a defined schema or format.
- [ ] Commit SHA, artifact digest, and deployment revision are linked end-to-end.
- [ ] Receivers verify origin and acceptance criteria before consuming inputs.
- [ ] Critical artifact identifiers do not require manual retyping or copying.
- [ ] Approvals are bound to the exact artifact, environment, and change scope.
- [ ] Permissions are scoped per job, user, and environment.
- [ ] Retry actions inspect prior state and avoid duplicate side effects.
- [ ] Manual steps record evidence, actor, and timestamp.
- [ ] Operations receives the release record, dashboards, runbooks, and recovery steps.
- [ ] Exception paths and break-glass access are controlled and audited afterward.

During reviews, prioritize handoffs that combine high impact with manual interaction: selecting production artifacts, changing configuration, provisioning secrets, running migrations, approving releases, and executing rollbacks. A mistake at these points typically causes far wider damage than a failure inside an isolated check.

## 10. Scenario Exercise

A team releases a service via this workflow: a developer creates a tag, CI builds the image, a tester verifies it on staging, a release manager approves, an operator deploys to production, and operations monitors it.

During one release, the tester confirms staging passed. Later, the developer updates the tag to fix a small bug without regenerating the test report. The release manager still approves based on the earlier message. The operator deploys the current tag to production. The service fails because the new image was never tested.

Identify:

1. Which handoffs exist in this scenario?
2. Which identifier or piece of evidence lost its link?
3. Why does a mutable tag make the prior approval unreliable?
4. What should the system check before allowing production deployment?
5. If defects are discovered post-deployment, what records does the team need to roll back or roll forward?

A strong solution binds test reports and approvals to an immutable artifact digest. When the tag is updated and produces a new digest, old test results and approvals do not automatically carry over to the new digest. The pipeline requires re-running mandatory checks and re-approving according to policy. The release record captures the new digest, source commit, run ID, and deployment revision so operations can act quickly if an incident occurs.

## 11. Conclusion

A handoff is where a change, artifact, or decision moves from its creator to its consumer. Risk escalates whenever humans must remember context, pick from look-alike values, copy identifiers, enter secrets, or repeat actions without knowing prior state.

A resilient CI/CD workflow formalizes handoff contracts, passes immutable identifiers, verifies on both sides, and retains evidence. Humans focus on decisions requiring judgment; data transfer, condition checks, and repetitive actions are automated. When exceptions occur, the team can stop at the right boundary, know who is accountable, and recover using recorded facts.
