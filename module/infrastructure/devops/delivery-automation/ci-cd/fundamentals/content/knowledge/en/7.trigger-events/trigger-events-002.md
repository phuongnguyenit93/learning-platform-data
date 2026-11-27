# Manual Triggers with Validated Inputs

## Learning Objectives

After this lesson, learners will be able to:

- Distinguish between manually triggering a workflow and approving a step inside an already-running workflow.
- Choose appropriate use cases for manual triggers in CI/CD.
- Design input sets with explicit data types, allowed values, defaults, and constraints.
- Validate inputs on the execution side, scope permissions, and protect secrets.
- Design a preview, confirmation, execution, verification, and audit trail flow.
- Control duplicate runs, concurrency, and error handling so manual operations can be repeated safely.

## 1. What Is a Manual Trigger?

In CI/CD, many workflows start automatically on Git events such as push, pull request, tag creation, or merging into the main branch. However, some activities should only start when a person explicitly requests them. Examples include deploying a tested artifact to a specific environment, re-running a maintenance task, performing a controlled migration, or rolling back to a known version.

A **manual trigger** is a mechanism that allows an authorized user to start a workflow or job by providing a predefined set of inputs. The initiator chooses the action, target, and execution scope; the pipeline validates these values before making any impact.

A manual trigger does not mean humans must perform the technical steps by hand. Humans issue an intentional request; the pipeline still validates, executes, verifies, and records results automatically.

Two concepts should be distinguished:

- **Manual trigger:** a user proactively starts a workflow that is not yet running, such as requesting deployment of an artifact digest to staging.
- **Manual approval:** a running workflow pauses at a wait point and requires an authorized person to allow it to proceed, such as approving a production rollout after staging succeeds.

Both mechanisms can appear in the same flow. One person can trigger a release workflow, and another person can approve the production step. Clicking the button to run a workflow does not automatically mean all control gates have been passed.

## 2. When Should a Manual Trigger Be Used?

Manual triggers are useful when execution timing depends on an operational decision or when a specific target must be selected.

| Case | Typically Required Inputs | Reason for Intentional Initiation |
|---|---|---|
| Staging deployment | Artifact digest, environment | Select the version to verify |
| Production release | Tested artifact, release reason | Deliberately choose timing according to policy |
| Rollback | Target version, reason, incident ID | Select a known version to restore |
| Running migrations | Migration ID, environment, plan | Execute impactful data changes |
| Running maintenance tasks | Task type, scope, dry-run mode | Avoid running periodically outside actual need |
| Seeding test data | Dataset, tenant, or namespace | Prepare data for a specific activity |
| Re-running a step | Related pipeline run or artifact | Investigate and handle failures under control |

Do not use manual triggers for routine testing. Linting, unit tests, and checks that should run on every pull request should be automated on Git events. If developers must remember to click a button for basic quality checks, processes are easily missed and feedback slows down.

A useful rule of thumb is: **automatically trigger tasks that must happen consistently on events; use manual triggers for actions that require an intentional choice of timing, target, or scope.**

## 3. Inputs Are a Contract, Not an Arbitrary Command Line

When designing a manual trigger, do not start with a free-form text box like "enter command to run." Model inputs as a structured input contract.

An input field should define:

- **Name:** short, meaningful, and consistent.
- **Data type:** string, number, boolean, predefined choices, environment, or identifier.
- **Required or optional:** whether it may be left empty.
- **Default value:** if present, the default must be safe and clear.
- **Value domain:** allowlist, numeric range, format, or length.
- **Semantics:** what the field is used to decide.
- **Trust level:** whether the data is user-supplied and must be re-validated.

Example contract for a deployment operation:

| Field | Type | Rules |
|---|---|---|
| operation | Enum | Only deploy or rollback |
| target_environment | Enum / Environment | Only environments supported by the workflow |
| artifact_digest | String | Required, valid digest format, and must exist in a trusted registry |
| reason | String | Required, length-limited, not whitespace-only |
| change_reference | String | Ticket or change record ID matching the defined format |
| dry_run | Boolean | Defaults to true if the operation supports previewing |
| replica_count | Number | Used only when needed; bounded within an allowed range |

Not every workflow needs all of the fields above. Require only the information genuinely needed to identify the action and control risk. Too many fields confuse users and encourage arbitrary data entry.

### 3.1. Prefer Typed Inputs and Selection Lists

If there are only three environments—dev, staging, and production—use a predefined selection list instead of asking users to type them manually. Selection lists reduce typos and make the allowed scope explicit.

Similarly, if the only operations are deploy, rollback, and dry-run, define them as an enum or explicit choice. Never accept a free-form string and interpret it as a shell command name.

Booleans must be genuine booleans. Do not treat the string "false" as truthy simply because a scripting language treats non-empty strings as true. Numbers must be checked for bounds and units; for instance, replica_count must be a positive integer, not an arbitrary string.

### 3.2. Validate Cross-Field Constraints

An individual value may be valid on its own, yet a combination of multiple values may be invalid.

Examples:

- operation=rollback must specify a stored target version that is still deployable.
- target_environment=production requires the artifact to have passed mandatory production gates.
- dry_run=false on a destructive data migration may require a change record and additional approval.
- operation=deploy must not accept a digest that does not exist in the artifact registry.
- replica_count may only be provided for service types that support changing replica counts.

Therefore, a step to validate input combinations is needed before execution.

## 4. Validating Inputs on the Execution Side

Platform forms can help users enter the right data types, but they are not a security boundary. Inputs can arrive from an API, CLI, a re-invoked run, or another source. Users might also choose a branch containing a workflow definition different from the default branch.

Consequently, the pipeline must re-verify values on the execution side.

Validation can be divided into four layers:

### 4.1. Syntax Validation

Confirm values have valid formatting:

- Non-empty string after trimming.
- Digest matches the format used by the registry.
- Ticket ID matches conventions.
- Numbers fall within range and match the expected type.
- Enum values belong to the declared list.
- Strings do not exceed length limits.

### 4.2. Semantic Validation

Confirm values are meaningful within the system:

- The artifact actually exists in the registry.
- The artifact was built from an allowed repository and commit.
- The version has not been revoked or marked do-not-release.
- The target environment is configured.
- The migration ID exists in the managed migration catalog.
- The rollback version remains compatible with the current schema and configuration.

### 4.3. Policy Validation

Confirm the action is allowed under operational rules:

- The initiator has permission to request the operation.
- The branch or workflow source is authorized to perform the action.
- The environment permits deployments at this time.
- The artifact has passed mandatory gates.
- Whether the change requires approval or a change record.
- Whether the target resource is locked or has another active rollout.

### 4.4. Just-in-Time State Validation Before Impact

Some conditions can change after the workflow starts. For example, another pipeline just deployed to the environment, the digest was revoked, or the release window closed. Right before any impactful step, re-verify these conditions.

If a critical check cannot be performed, the pipeline should stop with a clear status. Never skip it silently just because a verification service is temporarily unreachable.

## 5. Trigger Permissions and Execution Permissions Are Two Separate Layers

A user who has permission to open or trigger a workflow does not necessarily have permission to deploy to every environment. Trigger permission defines who can submit a request; execution permission defines what the pipeline is allowed to do after the request is validated.

Examples:

| Role | Can Request | Corresponding Execution Permissions |
|---|---|---|
| Developer | Run tests, deploy preview or staging | No production credentials |
| Release manager | Request release of a gate-passed artifact | Can initiate workflow; production still follows policy |
| Production approver | Approve rollout within assigned scope | Can approve, not necessarily modify artifacts |
| Platform operator | Run selected operational tasks | Permissions scoped by system and time |

Important considerations:

- Do not trust a user-entered requested_by field to establish identity. Obtain identity from the platform.
- Do not treat an approved=true input as proof of approval.
- Do not allow someone with workflow trigger permissions to arbitrarily pick an environment and inherit administrative permissions over it.
- Use environment protection, role-based access, or equivalent controls to protect sensitive steps.
- When separation of duties is required, the initiator and approver must be verified against policy.
- Grant credentials only to the job that needs them, not to the entire workflow if other steps do not need them.

A manual trigger is the entry point to a controlled workflow. It does not replace the authorization system and does not grant permissions to the requester on its own.

## 6. Never Pass Secrets Through Inputs

Never ask users to enter passwords, access tokens, private keys, or connection strings into manual trigger forms. These values can appear in run history, logs, API requests, notifications, or administrative UIs.

Instead:

- Store secrets in a secret manager or the platform's secret vault.
- Scope secrets by environment and job.
- Use workload identities or short-lived tokens when supported by the platform.
- Limit credential permissions and lifetime.
- Never print secret values to logs, including in error messages.
- Revoke and rotate secrets if exposure is detected.

Inputs should contain **references** to managed resources, not the secrets of those resources. For example, a user selects production-eu as a configured environment ID; the workflow retrieves the credentials granted to that environment according to policy.

Log masking does not replace designing without secret inputs. Secret masking may fail to detect values that were transformed, encoded, or split before being logged.

## 7. Designing a Safe Manual Trigger Flow

A well-designed manual workflow can be divided into six steps:

1. **Receive request:** capture initiator identity, timestamp, workflow ref, and inputs.
2. **Validate inputs:** check types, value domains, formatting, and cross-field constraints.
3. **Check permissions and policy:** verify requester, artifact, environment, and release conditions.
4. **Preview:** display the intended action, target, blast radius, and upcoming changes.
5. **Execute:** proceed only when all mandatory gates pass and required approvals are granted.
6. **Verify and record:** inspect post-operation state, store results, and link to the run.

~~~mermaid
flowchart TD
    A["Authorized user submits request"] --> B["Capture input + actor + workflow ref"]
    B --> C["Validate schema and values"]
    C --> D{"Inputs valid?"}
    D -- "No" --> X["Reject, identify invalid fields"]
    D -- "Yes" --> E["Check permissions and policy"]
    E --> F{"Authorized?"}
    F -- "No" --> Y["Block and record audit"]
    F -- "Yes" --> G["Resolve artifact and target"]
    G --> H["Dry-run / preview"]
    H --> I{"Gates and approvals met?"}
    I -- "No" --> Z["Stop, preserve state"]
    I -- "Yes" --> J["Controlled execution"]
    J --> K["Post-action verification"]
    K --> L{"Verification passed?"}
    L -- "No" --> M["Halt rollout / recovery"]
    L -- "Yes" --> N["Record audit and results"]
~~~

Not every operation requires a separate dry-run step, but for production deployments, migrations, or potentially destructive operations, previewing often helps operators catch a wrong environment or wrong scope before acting.

## 8. Dry-Run, Confirmation, and High-Impact Actions

dry_run lets the pipeline compute or check what will happen without making changes. A useful dry-run should return concrete outputs:

- Target environment and resources.
- Selected artifact or version.
- Count of affected resources.
- Planned migrations or operations.
- Missing preconditions and unmet gates.
- Compatibility or recovery warnings.

Do not display "Dry run passed" if the pipeline actually just skipped the deploy step. A dry-run should execute every check possible without causing side effects and clearly state what could not be verified.

For destructive or hard-to-reverse operations, an additional confirmation step may be required. For example, a data deletion task requires selecting the exact environment, entering a run-generated confirmation code, or obtaining authorization from an approver. Do not rely solely on a checkbox or a requester-supplied string like confirm=yes.

Scope must also be bounded. If a task should only affect a single tenant or resource group, inputs should represent that exact scope and the workflow must verify the scope is on an allowlist.

## 9. Selecting Artifacts and Versions by Immutable Identifiers

A common mistake is letting users enter a branch name such as main, latest, or release and deploying it directly. These references can point to different contents at different points in time.

For release operations, select a built and tested artifact identified by an immutable digest or ID. The pipeline can accept an artifact_id, then query the registry for metadata and verify:

- The artifact belongs to the right product or repository.
- The artifact was built from an allowed commit.
- The digest matches registry records.
- Mandatory checks have passed.
- The artifact has not been revoked.
- The artifact is compatible with the environment and dependency versions.

If rollback support is needed, choose an existing release ID or digest from the release catalog. Never ask operators to paste an arbitrary URL and download packages from an untrusted source.

Likewise, the workflow ref or branch selected to run a manual trigger must be restricted. A workflow that holds production permissions but runs from a branch containing unreviewed configuration changes creates risk. Define allowed workflow sources, protect branches, and keep sensitive policies in governed locations.

## 10. Preventing Duplicate Runs and Conflicts

Manual triggers are easily clicked multiple times when the UI is slow or users are unsure whether the previous run started. If a deployment workflow is not designed for safe re-execution, two runs may modify the environment concurrently or execute a migration twice.

Mechanisms to consider:

**Idempotency key:** each request has a unique identifier. If the same request is resubmitted, the system recognizes it and returns the prior result or resumes safely rather than repeating everything.

**Concurrency control:** limit the number of workflows permitted to modify the same environment or resource at the same time.

**State check:** before executing, verify the current state. For example, if the artifact is already properly deployed to staging, the workflow can report completion instead of redeploying.

**Bounded retries:** retry only transient errors such as network timeouts or dependency service glitches. Never blindly retry non-idempotent operations.

**Timeout and cancellation:** define maximum duration, safe shutdown behavior, and handling if a job is canceled mid-flight.

Do not use a single global concurrency lock if unrelated environments or services do not conflict. Lock at the scope where actual contention occurs to preserve parallel execution capability.

## 11. Recording an Audit Trail for Every Run

A manually triggered operation must remain traceable: who requested it, what was requested, how the pipeline decided, and what final state the system reached.

An audit record should contain at a minimum:

| Field | Meaning |
|---|---|
| Run ID | Run identifier |
| Actor | True identity of the initiator from the platform |
| Workflow ref | Executed workflow configuration version |
| Requested action | The requested operation |
| Normalized inputs | Validated values after checks, with sensitive data stripped |
| Artifact identity | Commit, release ID, or digest |
| Target | Environment and resource scope |
| Policy result | Gates passed, failed, or waived |
| Approval | Approver, timestamp, and approval scope |
| Execution result | Executed steps and final status |
| Verification | Post-operation evidence |
| Correlation ID | Identifier linking logs, deployments, and incidents |

Do not write secrets or sensitive values into the audit trail. Sanitize inputs before storage, restrict read access, and retain records according to retention policies. Pipeline logs should link to the audit record so investigators can trace from request to outcome.

An audit trail is not only for post-incident investigation. It also helps teams identify which manual triggers are frequently mistyped, which actions fail often, and which steps should be automated on events instead of requiring human initiation.

## 12. Example Manual Trigger Workflow Model

The following YAML describes a general logical contract, not directly executable syntax for a specific CI/CD platform:

~~~yaml
workflow:
  name: controlled-deployment
  trigger:
    type: manual
    inputs:
      operation:
        type: enum
        required: true
        allowed:
          - deploy
          - rollback

      target_environment:
        type: enum
        required: true
        allowed:
          - staging
          - production

      artifact_digest:
        type: string
        required: true
        format: sha256
        max_length: 71

      change_reference:
        type: string
        required: true
        pattern: "CHANGE-[0-9]+"

      reason:
        type: string
        required: true
        min_length: 10
        max_length: 300

      dry_run:
        type: boolean
        required: false
        default: true

  validate:
    - validate_input_schema
    - verify_actor_permission
    - verify_artifact_exists_and_is_trusted
    - verify_artifact_policy
    - verify_target_environment
    - verify_operation_constraints

  preview:
    enabled: true
    show:
      - actor
      - operation
      - target_environment
      - artifact_digest
      - change_reference
      - expected_impact

  execute:
    requires:
      - validation_passed
      - approval_if_required
      - environment_available
    controls:
      - idempotency_key
      - concurrency_lock
      - timeout
    steps:
      - perform_requested_operation
      - verify_actual_state
      - record_audit_event
~~~

This example shows inputs declared upfront with explicit types and value domains. The pipeline must still verify the artifact, permissions, and environment state on the execution side. Never treat the form schema as the sole proof of validity.

Platforms like GitHub Actions, GitLab CI, and Jenkins have different syntax for declaring manual parameters. When implementing, map this logical contract to the input types, permissions, environment protections, and secret scopes of your chosen platform. Execution-side validation must still be preserved.

## 13. Statuses That Should Be Returned to the Initiator

A manual trigger workflow should distinguish outcomes so users know what to do next.

| Status | Meaning | Next Action |
|---|---|---|
| REJECTED | Invalid input or policy violation | Fix the indicated field or request appropriate permissions |
| BLOCKED | Missing precondition, environment, or approval | Satisfy precondition or wait for an authorized approver |
| PREVIEWED | Validated and planned, not yet executed | Review scope and confirm if permitted |
| RUNNING | Currently executing | Monitor run ID |
| SUCCEEDED | Action and verification both passed | Use release/deployment ID for lookup |
| FAILED | An execution step failed | Inspect logs and actual resource state |
| CANCELLED | Canceled through a supported method | Check whether partial side effects need cleanup |
| PARTIAL | Part of the operation occurred but did not complete | Run recovery procedure or continue under control |

In particular, FAILED does not always mean the system remained unchanged. A deployment may update part of the resources and then fail during smoke testing. In that case, report the actual state clearly rather than merely showing a red X.

## 14. Anti-Patterns When Using Manual Triggers

| Anti-Pattern | Risk | Improvement |
|---|---|---|
| Free-form command input box | Input can become unintended executable code | Use an action enum and structured parameters |
| Arbitrary string for environment | Deploying to the wrong or unauthorized resource | Use an allowlist and configured environments |
| Using latest as release version | Contents can change between verification and deploy | Use an immutable digest or release ID |
| Validating only in the UI | Can be bypassed via API or other run paths | Re-validate inside the workflow and target service |
| Passing tokens via inputs | Exposed in logs, history, or metadata | Retrieve from secret manager or workload identity |
| Treating initiator as approver | Bypasses separation of duties | Use approval gates and separate actor verification |
| No dry-run for high-impact actions | Hard to spot wrong scope before acting | Display plan and require confirmation |
| Allowing unlimited concurrent runs | Overwrites or conflicting migrations | Per-environment concurrency control |
| Retrying entire workflow after failure | Repeats non-idempotent operations | Use idempotency keys and error-specific retries |
| No reason or audit logging | Cannot explain why an action occurred | Record actor, normalized inputs, policy, and outcome |

## 15. Manual Trigger Design Checklist

Before allowing a manual trigger to affect real resources, verify:

- [ ] The reason for a manual trigger is clear and it is not work that should run automatically on events.
- [ ] Inputs are defined by schema, data types, and value domains.
- [ ] Required fields, defaults, and length limits are declared.
- [ ] Cross-field constraints across inputs are validated.
- [ ] The workflow re-validates inputs on the execution side.
- [ ] Artifacts are selected by immutable digest or ID.
- [ ] Target environments and resources are on an allowlist.
- [ ] Trigger permissions and execution permissions are verified separately.
- [ ] Approvals are enforced when required by policy.
- [ ] No secrets are passed through inputs or written to logs.
- [ ] Dry-run/preview is provided commensurate with impact level.
- [ ] Concurrency control, timeouts, and duplicate-run handling are in place.
- [ ] Post-operation state verification is performed.
- [ ] An audit trail links actor, run ID, artifact, and target.
- [ ] Failure or partial execution states are explained clearly.

## 16. Self-Assessment Exercise

An operations team has a production deployment workflow. Currently, users just type a branch name, an environment name, and an arbitrary command string, then click run. The workflow shares a single administrative token, does not verify artifacts in the registry, and does not record a release reason. Once, an operator accidentally picked an experimental branch and deployed an untested build.

Redesign the workflow:

1. Which fields should be enums, booleans, numbers, or formatted strings?
2. Should free-form branch names be allowed to select production artifacts? Why or why not?
3. What should the workflow verify about the artifact before deploying?
4. How should trigger permissions be separated from production release permissions?
5. By what mechanism should secrets be provided to the job?
6. Are dry-run or separate approvals needed? Which conditions decide?
7. If a user clicks the button twice, how do you prevent duplicate deployments?
8. What information must be stored in the audit trail?
9. If deployment fails after partially updating resources, what status and recovery guidance should be shown?

A good design constrains choices, re-validates on the execution side, binds actions to immutable artifacts, enforces proper permissions, and records outcomes. Manual triggers should help humans make clear requests while the pipeline takes responsibility for executing them under control.

## Conclusion

Manual triggers let humans intentionally initiate CI/CD activities that require choices about timing, artifact, environment, or scope. To be safe and operable, inputs must be defined as a contract with clear data types and constraints; the pipeline must re-validate on the execution side, check permissions, use immutable artifacts, protect secrets, and control duplicate runs.

A well-built workflow lets the initiator see what they are requesting, what will be affected, and how results are verified. For high-risk actions, dry-runs, approvals, and audit trails preserve clear accountability. In this way, manual actions become a controlled checkpoint within an automated delivery process.
