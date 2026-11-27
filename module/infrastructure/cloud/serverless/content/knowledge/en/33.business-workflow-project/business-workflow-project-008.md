# Releasing a New Workflow Version and Handling In-Flight Executions

## 1. Why Manage Workflow Versions?

A business workflow can run for seconds, hours, or days. For example, an order processing flow may validate a request, reserve inventory, wait for payment, wait for partner shipping confirmation, and then complete. While an execution is waiting, the development team may need to modify the definition, reorder tasks, add validation steps, adjust timeouts, or upgrade invoked Lambda functions.

Updating a workflow without a versioning strategy easily leads to issues such as:

- Older executions started under old logic continue calling modified dependencies.
- New executions use the new definition while old executions are still running.
- A production bug requires rollback, yet an alias only redirects new executions.
- Persisted input/state is incompatible with the new workflow definition.
- Redriving a failed execution runs old tasks or produces duplicate side effects.
- Inability to identify which version caused errors, latency spikes, or cost increases.

With AWS Step Functions, **state machine versions** and **aliases** enable controlled workflow releases. A version is an immutable snapshot of a state machine; an alias is a stable name that routes new executions to one or two versions. However, updating an alias does not move in-flight executions to the new version. Therefore, a workflow release must manage new executions, existing executions, state data, Lambda/task dependencies, and external side effects.

Within the CLOUD_SERVERLESS module, this applies to Java functions triggered by HTTP, messages, or events, especially when Step Functions orchestrates multiple steps with retries, timeouts, state, and long lifetimes.

## 2. Distinguishing Revision, Version, Alias, and Execution

These concepts are related but not interchangeable.

| Concept | Meaning | Can Start Executions Directly? |
|---|---|---|
| State machine revision | Read-only snapshot of definition/config after an update | No; a revision has no ARN for StartExecution |
| State machine version | Published snapshot with its own version number and ARN | Yes |
| State machine alias | Stable ARN pointing to one or up to two versions | Yes; Step Functions picks a version per routing config |
| Unqualified state machine ARN | State machine address without version/alias | Yes; uses the latest revision at start time |
| Execution | A specific run with its own input, history, and state | An instance of the workflow, not a version |

Example:

```text
State machine: OrderFulfillment

Revision: r-7d2...       # internal snapshot, not used for StartExecution
Version 12: ...:OrderFulfillment:12
Version 13: ...:OrderFulfillment:13
Alias PROD: ...:OrderFulfillment:PROD
  95% -> Version 12
   5% -> Version 13

Execution A -> Version 12 (already running)
Execution B -> Version 13 (selected by alias at start)
```

A version is an immutable snapshot of the state machine definition and configurations such as IAM role ARN, logging, and tracing configuration. An alias is an updatable pointer used to route traffic. An execution is a single run and retains its association with the version/alias used at start time when `StartExecution` uses a qualified ARN.

Documentation: [State machine versions](https://docs.aws.amazon.com/step-functions/latest/dg/concepts-state-machine-version.html), [State machine aliases](https://docs.aws.amazon.com/step-functions/latest/dg/concepts-state-machine-alias.html).

## 3. What Happens to In-Flight Executions When the Definition Updates?

When `UpdateStateMachine` is called to modify the definition or role ARN, in-flight executions continue using the old definition and role ARN. Updating does not alter the state machine definition mid-flight for executions that have already started.

This means:

- Executions in `Wait` continue under the old workflow once the wait ends.
- Executions running a `Task` continue under the old definition.
- Older executions may keep running for hours or days after a new version is published.
- New executions started with an unqualified state machine ARN use the latest revision once the update takes effect.
- New executions started with a version ARN or alias ARN bind to that version/alias.

You do not need to stop all old executions merely because a new workflow version was published. However, external dependencies invoked by the old workflow can change independently. This is a major risk: the state machine retains the old definition, yet if that definition calls Lambda via alias `orders-worker:PROD`, shifting the Lambda alias can cause old executions to invoke new code on their next step.

To preserve consistent behavior, version dependencies alongside workflow versions or maintain backward-compatible contracts while old executions remain alive.

API documentation: [UpdateStateMachine](https://docs.aws.amazon.com/step-functions/latest/apireference/API_UpdateStateMachine.html).

## 4. New Versions Apply Only to New Executions

State machine versions are not an in-place upgrade mechanism for running executions. Once an execution starts, Step Functions does not automatically move it to another version when an alias is updated.

Distinguish three groups of executions:

1. **In-flight executions from an old version/alias:** continue using the definition bound at start.
2. **New executions after release:** routed through the new alias/version according to the ARN used by the caller.
3. **Failed executions being redriven:** for Standard Workflows, redrive resumes the original execution using its original definition and version/alias, rather than fetching the alias's latest target.

Therefore, a release plan needs an explicit policy for in-flight executions: let them finish on the old version, drain before switching, stop and compensate, or start a new execution from a transformed business checkpoint. There is no safe "swap version in place" operation for an arbitrary running execution.

## 5. Creating State Machine Versions and Aliases

### Publish a Version

After updating the definition, publish a version from the current revision. AWS CLI example:

```bash
aws stepfunctions update-state-machine \
  --state-machine-arn "$STATE_MACHINE_ARN" \
  --definition file://order-workflow.asl.json \
  --role-arn "$STATE_MACHINE_ROLE_ARN" \
  --publish
```

The command returns `stateMachineVersionArn` on success. Alternatively, update the definition first and then call `publish-state-machine-version`. Version numbers increment sequentially and are never reused for the same state machine.

Record:

- Git commit SHA of the workflow definition.
- Hash of the deployed ASL/JSON/YAML.
- Published version ARN.
- IAM role ARN and logging/tracing configuration.
- Version ARNs of Lambda/task dependencies if pinned.
- Associated input schema version and event schema version.

### Create a Production Alias

Example `PROD` alias initially routing 100% to version 12:

```bash
aws stepfunctions create-state-machine-alias \
  --state-machine-arn "$STATE_MACHINE_ARN" \
  --name PROD \
  --routing-configuration '[
    {
      "stateMachineVersionArn": "arn:aws:states:ap-southeast-1:123456789012:stateMachine:OrderFulfillment:12",
      "weight": 100
    }
  ]'
```

Later, the alias can be updated to route between versions 12 and 13. An alias points only to versions, never to another alias; an alias can route across at most two versions, and weights must sum to 100.

### Start an Execution via Alias

```bash
aws stepfunctions start-execution \
  --state-machine-arn "$STATE_MACHINE_PROD_ALIAS_ARN" \
  --name "order-9381-fulfillment" \
  --input file://execution-input.json
```

Production callers should invoke the alias ARN rather than the unqualified state machine ARN when release control and per-version observability are needed. An unqualified ARN uses the latest revision, but the execution is not bound to a version or alias even if that revision matches a published version.

## 6. Alias Routing and Canary Deployments

Aliases allow splitting new executions across up to two versions. For example:

```text
PROD alias
  Version 12: 95%
  Version 13:  5%
```

When a caller invokes `StartExecution` using the alias ARN, Step Functions selects a version according to configured weights. This routing happens at **execution start**. It does not shift existing executions between versions when the alias changes.

Example alias update:

```bash
aws stepfunctions update-state-machine-alias \
  --state-machine-alias-arn "$STATE_MACHINE_PROD_ALIAS_ARN" \
  --routing-configuration '[
    {
      "stateMachineVersionArn": "arn:aws:states:ap-southeast-1:123456789012:stateMachine:OrderFulfillment:12",
      "weight": 95
    },
    {
      "stateMachineVersionArn": "arn:aws:states:ap-southeast-1:123456789012:stateMachine:OrderFulfillment:13",
      "weight": 5
    }
  ]'
```

A gradual ramp might proceed 1%, 5%, 10%, 25%, 50%, then 100%. Increase traffic only when new executions on version 13 meet thresholds for error rate, timeouts, latency, and business correctness.

Weighted routing distributes per execution start; it does not by default guarantee sticky routing per tenant or customer. If every execution for the same order/customer must use the same version, route via caller policy or persist the chosen version on the operation record and start executions using the specific version ARN.

Documentation: [State machine aliases and routing](https://docs.aws.amazon.com/step-functions/latest/dg/concepts-state-machine-alias.html).

## 7. Executions Started Before Versioning/Aliases Existed

A system may already have thousands of executions started via the unqualified state machine ARN before versioning was enabled. Step Functions does not retroactively attach those executions to a version merely because their definition matches a newly published version.

When taking inventory, categorize them into:

- Executions running from the unqualified ARN.
- Executions running from a version ARN.
- Executions running from an alias ARN.
- Completed or failed executions.
- Executions waiting in `Wait`, callback task tokens, or external integrations.

For unqualified executions, use execution ARN, start time, history, and available revision/definition metadata to identify the corresponding release if the system recorded it. If commit/version was not previously recorded in inputs or logs, it may not be possible to reconstruct the exact release from the state machine name alone.

Starting with the new release, include `workflowRelease`, `inputSchemaVersion`, `businessOperationId`, and correlation ID in execution input or metadata for easier lookup.

## 8. Choosing a Policy for In-Flight Executions

Not every old execution needs identical treatment. Choose a policy based on runtime duration, business state, and side-effect risk.

| Policy | When Appropriate | Actions Needed |
|---|---|---|
| Let old version finish | Executions can complete and old dependencies remain compatible | Keep old version/dependencies; monitor remaining execution count |
| Drain before switch | Short workflows where waiting for completion before switching alias is feasible | Pause new starts or queue them; wait until active count hits 0 |
| Stop and compensate | Workflow is broken or unsafe to continue | Stop execution, run idempotent compensation, and update operation state |
| Restart as new execution | New logic must apply to unfinished work | Create checkpoint, transform input/state, start new execution correlated to the old one |
| Keep old version for long tail | Workflows may wait for days or months | Retain required version and task dependencies until executions finish or redrive windows expire |

Never choose "restart all" as a default action. A workflow may have already captured payment or dispatched a shipment; restarting from scratch can repeat side effects. Restarting requires identifying a business checkpoint and knowing which steps already committed.

## 9. Draining Old Executions

Draining is the process of stopping new execution creation on an old version and waiting for already started executions to finish.

Process:

1. Switch the alias or callers to the new version for new executions.
2. Record the cutover timestamp and version ARNs.
3. List running executions per old version/alias.
4. Monitor executions in `RUNNING`, `WAITING`, or awaiting callbacks.
5. Set a drain deadline based on SLAs and maximum workflow duration.
6. Handle overdue executions: investigate, resume, stop/compensate, or perform a controlled migration.
7. Remove old dependencies only once no executions need them and redrive policies have been accounted for.

With Step Functions, use `ListExecutions` filtered by state machine/version/alias to take inventory. For executions started via an alias, the API can report the alias ARN and selected version. For earlier unqualified executions, rely on timestamps and stored metadata.

Do not look solely at `RUNNING` counts. An execution may sit in a callback wait or `Wait` state for a long time; it still needs a compatible definition/version and dependencies when it resumes.

## 10. Redriving Failed Executions After Releasing a New Version

Step Functions Standard Workflows support redriving eligible failed, aborted, or timed-out executions within the redrive window. Redrive resumes from the failed state, uses the same input, preserves results/history of succeeded states, and reuses the original execution's definition/ARN.

Key points:

- Redrive does not automatically use the latest version.
- If the original execution was bound to a version or alias, redrive remains bound to that execution's version/alias.
- Even after the alias points to a new version, redrive still uses the original version.
- To run with a new definition, create a new execution and intentionally migrate input/checkpoint.
- Re-executed tasks can repeat side effects if not idempotent.

Per current documentation, Standard Workflows have a 14-day redrive window for eligible executions; redrive does not apply directly to Express Workflows. Verify eligibility, execution history quotas, and specific rules before operating.

Example:

```text
Execution E-100 started by alias PROD -> Version 12
Version 13 is released
Alias PROD now points 100% -> Version 13
E-100 fails at CapturePayment

Redrive E-100:
  resumes failed state using Version 12
  does not switch to Version 13

Start a new execution with Version 13:
  requires a new execution ARN/name and migrated business input
```

Documentation: [Redrive executions](https://docs.aws.amazon.com/step-functions/latest/dg/redrive-executions.html).

## 11. Distinguishing Redrive vs. Migration to a New Execution

Redrive resumes an old execution under its old definition. Migration creates a new execution under a new definition, linked to the old operation/execution with a transformed checkpoint.

| Criterion | Redrive | New Execution Migration |
|---|---|---|
| Definition | Original execution's definition | New definition/version |
| Execution ARN | Keeps original execution ARN | New ARN |
| Successful states | Preserves results; skipped per redrive behavior | Must transfer checkpoint or recompute safely |
| Input | Original input | Transformed/versioned input |
| Side effects | Failed task re-runs; requires idempotency | Runs only remaining work per checkpoint |
| Use case | Transient error or recovered dependency | Need to apply new logic/schema/workflow |

Never edit execution history directly to pretend an execution traversed new states. Persist a migration record containing old execution ARN, new execution ARN, source version, target version, checkpoint, operator/reason, and timestamp.

## 12. Workflow Versions Do Not Pin Lambda and Service Dependencies Automatically

A state machine version snapshots the state machine's definition/config, but does not freeze all external resources referenced by that definition.

Example ASL invoking Lambda via an alias:

```json
{
  "Resource": "arn:aws:lambda:ap-southeast-1:123456789012:function:ReserveInventory:PROD"
}
```

If the Lambda `PROD` alias moves from function version 8 to 9, an execution running an older workflow version that has not yet reached `ReserveInventory` may invoke code version 9. The Step Functions definition did not change, yet the runtime dependency changed underneath.

To ensure reproducibility:

- Pin Lambda function version ARNs inside the workflow definition when immutable behavior is needed.
- Or keep dependency aliases backward-compatible until old executions finish draining.
- Record external API/service versions in the release manifest.
- Keep event schemas and database contracts compatible with both old and new workflows.
- Do not delete Lambda versions, layers, or container images still needed by old executions.

A state machine version also does not freeze the policy document attached to an IAM role ARN if that policy is modified externally. The version stores the role ARN, while effective permissions remain governed by current IAM policies/resource policies. For strict release safety, manage IAM policies as versioned artifacts and avoid permission edits that unexpectedly alter running executions.

## 13. Managing Input Schemas and Workflow State Across Versions

Execution input is persisted per execution. A new workflow version may expect new fields or different data types. If event/API producers already switched to a new schema while old executions are still running, old state may encounter incompatible data at a subsequent step.

Include `schemaVersion` in input:

```json
{
  "workflowRelease": "orders-2026.11.17.3",
  "inputSchemaVersion": 2,
  "operationId": "op-7f1a",
  "order": {
    "orderId": "order-9381",
    "customerId": "customer-42"
  }
}
```

Compatibility rules:

- Prefer additive changes: add optional fields before making them required.
- Old consumers ignore unknown fields if the contract permits.
- Never change the meaning of an existing field without incrementing schema version.
- Retain old fields while old executions remain in flight.
- Use an adapter/normalizer at workflow entry to convert inputs into a canonical model.
- Separate external event schemas from internal workflow state schemas.
- Document versions and migration paths clearly.

If a new workflow requires a field absent from old inputs, derive it from the database or an adapter. If it cannot be derived safely, keep the old workflow or use a human-supervised migration process.

## 14. Expand-Contract for Database Schemas

Old and new workflows may read and write the database concurrently for a long period. Do not deploy breaking schema changes at the same time as a workflow cutover if old executions are still active.

An expand-contract sequence:

1. **Expand:** add new columns/tables while keeping old fields.
2. Deploy services capable of reading both old and new schemas.
3. Deploy the new workflow version writing new data compatibly.
4. Backfill older data if needed.
5. Wait for old executions to drain and verify all consumers have upgraded.
6. **Contract:** stop reading/writing old fields, and only then drop old schema elements.

Never drop a column that an old execution might access on a future step. A workflow may wait days on a callback or timer; seeing zero queries for a few minutes does not prove a column is safe to drop.

## 15. Designing State Machines for Upgradability

Workflows should have stable state boundaries and sufficient data to resume after long waits.

Recommendations:

- Every operation carries a business ID and workflow execution ARN.
- Persist business checkpoints after critical side effects.
- State outputs carry only data needed for the next step; avoid large payloads or secrets.
- Use `Choice` to handle differing schema versions or business states.
- Use `Retry` for transient errors and `Catch` for errors requiring compensation.
- Task side effects must be idempotent per operation/step.
- Use `Wait`/callbacks for waiting periods instead of keeping Lambdas running.
- Enforce an overall timeout and business deadline.
- Explicitly document which states can be safely redriven or restarted.

Abbreviated ASL example:

```json
{
  "Comment": "Order workflow with versioned input contract",
  "StartAt": "NormalizeInput",
  "TimeoutSeconds": 86400,
  "States": {
    "NormalizeInput": {
      "Type": "Task",
      "Resource": "arn:aws:lambda:ap-southeast-1:123456789012:function:NormalizeOrder:7",
      "Next": "CheckSchemaVersion"
    },
    "CheckSchemaVersion": {
      "Type": "Choice",
      "Choices": [
        {
          "Variable": "$.inputSchemaVersion",
          "NumericEquals": 2,
          "Next": "ReserveInventory"
        }
      ],
      "Default": "UnsupportedInputVersion"
    },
    "ReserveInventory": {
      "Type": "Task",
      "Resource": "arn:aws:lambda:ap-southeast-1:123456789012:function:ReserveInventory:12",
      "Retry": [
        {
          "ErrorEquals": ["TransientDependencyError"],
          "IntervalSeconds": 2,
          "BackoffRate": 2,
          "MaxAttempts": 3
        }
      ],
      "Catch": [
        {
          "ErrorEquals": ["States.ALL"],
          "ResultPath": "$.failure",
          "Next": "Compensate"
        }
      ],
      "Next": "Complete"
    },
    "Compensate": {
      "Type": "Task",
      "Resource": "arn:aws:lambda:ap-southeast-1:123456789012:function:CompensateOrder:4",
      "End": true
    },
    "UnsupportedInputVersion": {
      "Type": "Fail",
      "Error": "UnsupportedInputVersion"
    },
    "Complete": {
      "Type": "Succeed"
    }
  }
}
```

This example uses specific Lambda version ARNs to illustrate dependency pinning. In production, substitute ARNs generated by the pipeline instead of hardcoding accounts/Regions across many files. `TimeoutSeconds`, retries, and state flow must match business requirements. `States.ALL` in `Catch` is a simplified example; in practice, classify errors so unnecessary compensation is not triggered.

## 16. Idempotency During Retries or Concurrent Two-Version Execution

Canary routing can run new executions of the same business operation type on either the old or new version. Retries within an execution can also invoke a task multiple times. Therefore, idempotency keys should be based on the business operation, not solely on the workflow version.

Example:

```text
operationId = order-9381
stepKey = order-9381:reserve-inventory
paymentKey = order-9381:capture-payment
notificationKey = order-9381:send-confirmation
```

Do not include workflow version in the idempotency key if the goal is preventing duplicate side effects across old and new versions. If versions 12 and 13 both touch the same order, they must recognize the same business effect. Only generate a new key for an intentionally new business action.

Side-effect steps need:

- Unique constraints/conditional writes in the database.
- Inbox/outbox when publishing events.
- Provider idempotency keys for payment/email APIs when supported.
- State transitions guarded by version/expected status.
- Reconciliation for unknown outcomes after timeouts.
- Audit trails showing which version executed the effect.

## 17. Workflow Releases Must Version Dependencies

A workflow release is more than an ASL file. It is the set of components that can affect an execution.

Example release manifest:

```yaml
release: orders-workflow-2026.11.17.3
stateMachine:
  versionArn: arn:aws:states:ap-southeast-1:123456789012:stateMachine:OrderFulfillment:13
  alias: PROD
inputSchemaVersion: 2
tasks:
  normalizeOrder: arn:aws:lambda:ap-southeast-1:123456789012:function:NormalizeOrder:7
  reserveInventory: arn:aws:lambda:ap-southeast-1:123456789012:function:ReserveInventory:12
  compensateOrder: arn:aws:lambda:ap-southeast-1:123456789012:function:CompensateOrder:4
events:
  orderAcceptedSchema: 3
database:
  schemaCompatibility: expand-contract-v5
```

This manifest is a conceptual example, not direct Step Functions configuration. Store it alongside artifacts/release metadata so you know which task versions and schemas execution version 13 invoked and required.

If the workflow calls a Lambda alias, mutable container tag, or an API endpoint without versioned contracts, the release manifest must explicitly note those mutable dependencies and how compatibility is maintained.

## 18. CI/CD Process for Releasing a New Workflow Version

A pipeline can be divided into steps:

1. Validate the ASL definition and input/output schemas.
2. Run unit tests for Java tasks and contract tests between steps.
3. Run integration tests in a sandbox with mock/sandbox dependencies.
4. Build, publish, and record immutable Lambda function versions.
5. Update the state machine definition/role/configuration.
6. Publish the state machine version and record the version ARN.
7. Verify definition, IAM role ARN, logging/tracing, and dependency references.
8. Update the test/staging alias to point 100% to the new version.
9. Run workflow smoke tests and failure tests.
10. Update the production alias according to canary weights.
11. Monitor metrics by version/alias and business outcomes.
12. Ramp traffic or roll back the alias.
13. Monitor/drain old executions and remove dependencies only when safe.

Do not deploy a task Lambda alias update before assessing its impact on in-flight workflow executions. A pipeline should publish immutable Lambda versions first, then create a state machine version referencing exact Lambda version ARNs.

## 19. Validating Definitions Before Publishing

Use Step Functions `ValidateStateMachineDefinition` or the corresponding AWS CLI command to catch syntax/validation errors before updating.

```bash
aws stepfunctions validate-state-machine-definition \
  --definition file://order-workflow.asl.json \
  --type STANDARD
```

Validation does not replace integration tests. A valid definition can still point to the wrong Lambda ARN, lack IAM permissions, pass mismatched payload schemas, or produce non-idempotent side effects.

Also verify:

- `StartAt` points to an existing state.
- Every `Next`/`Default` points to valid states.
- `Retry`/`Catch` classify errors properly.
- `TimeoutSeconds` and heartbeats are appropriate.
- Payloads stay within Step Functions size limits.
- Lambda/resource ARNs point to the intended versions.
- Role holds least privilege for the required tasks.
- Logging/tracing and encryption match the environment.
- New input schemas are compatible with running producers.

## 20. Alias Canaries and Traffic Ramp Criteria

Canaries need quantitative criteria before starting. Examples:

| Metric/Indicator | Promotion Criterion |
|---|---|
| `ExecutionsFailed` | No abnormal increase over old version baseline |
| `ExecutionsTimedOut` | No increase and within SLO threshold |
| `ExecutionTime` | p95/p99 within acceptable bounds |
| Business success rate | Business completion rate meets threshold |
| Compensation rate | No abnormal increase |
| Duplicate/idempotency conflicts | Zero duplicate side effects |
| Downstream throttling | Database/API providers remain within capacity |
| Cost per successful operation | Within projected budget |

Step Functions emits metrics per version/alias when executions start with a qualified ARN. Use version/alias dimensions to compare old and new versions. Never rely solely on aggregate state machine metrics where old and new traffic mix together.

A 5% canary may lack sufficient sample size for low-traffic workflows or rare failure modes. Extend observation windows or run controlled synthetic tests before increasing traffic weights.

## 21. Rolling Back an Alias Does Not Roll Back Started Executions

If version 13 causes errors, switch the `PROD` alias back to version 12:

```bash
aws stepfunctions update-state-machine-alias \
  --state-machine-alias-arn "$STATE_MACHINE_PROD_ALIAS_ARN" \
  --routing-configuration '[
    {
      "stateMachineVersionArn": "arn:aws:states:ap-southeast-1:123456789012:stateMachine:OrderFulfillment:12",
      "weight": 100
    }
  ]'
```

After rollback:

- New executions via the alias use version 12.
- Executions already started on version 13 continue running on version 13.
- Version 13 executions must be evaluated: let finish, stop/compensate, or migrate to new executions.
- Redriving version 13 executions still uses their original definition/version.
- Lambda/API/database dependencies must remain compatible with surviving version 13 executions.

Rolling back an alias only changes routing for new executions. It does not undo database writes, payments, emails, or emitted events. If executions must be stopped, `StopExecution` does not automatically undo prior side effects; compensation/reconciliation is still required.

## 22. Stopping Executions and Compensating

Only stop an execution once you understand its business state and the effects of completed tasks.

Before stopping:

1. Identify which state the execution is in and which side effects committed.
2. Check whether external tasks are currently running.
3. Inspect operation IDs/idempotency records and database state.
4. Determine required compensations (release inventory, void authorization, cancel shipment, etc.).
5. Stop the execution if no safe continuation path exists.
6. Run compensation via idempotent commands and record audit logs.
7. Update operation state to `CANCELLED`, `COMPENSATING`, or `MANUAL_REVIEW` as appropriate.

Stopping an execution does not guarantee an in-flight Lambda invocation or external API call is cancelled immediately. A task may have already sent a request that the provider continues processing. Always verify side-effect outcomes before compensating.

## 23. Migrating Executions to a New Version

Some long-running workflows require moving in-flight executions onto new logic. Since an execution's definition cannot be swapped in place, use a business migration process.

One approach:

1. Identify states/checkpoints that can be safely serialized.
2. Persist durable business state outside workflow history if long-term continuation is required.
3. Identify committed side effects and remaining steps.
4. Build the new input schema from the old checkpoint via a migration adapter.
5. Start a new execution using the target version ARN/alias.
6. Attach `supersedesExecutionArn`/correlation ID pointing to the old execution.
7. Use idempotency to avoid re-running already completed side effects.
8. Transfer the operation record to the new execution via a conditional update.
9. Stop the old execution once the new execution is confirmed to own the work.
10. Reconcile results and store a migration audit record.

Never run both the old and new executions concurrently against the same business operation without leasing/fencing or a single-owner rule. If a safe checkpoint cannot be proved, let the old execution finish or process manually with controls.

## 24. Managing Long-Lived Executions and Old Versions

Workflows with `Wait` states, callback tokens, or partner waits can outlive deployment cycles. Report on executions by:

- Version/alias used at start time.
- Current state and time spent in state.
- Estimated remaining duration.
- Dependency versions needed for upcoming steps.
- Input schema version.
- Business status and committed side effects.
- Redrive eligibility and redrive deadline.

Retain old versions and corresponding Lambda dependencies until:

- Zero executions are still running on that version.
- Zero redrive-eligible executions depend on that version, or the redrive window has expired.
- Zero legacy events/queue messages can still trigger the old workflow version.
- Zero callers start executions using the old version ARN.
- Audit/retention policies permit artifact deletion.

Never delete a version merely because the alias moved to a newer version. Running executions or redrives may still need the old version.

## 25. Java Example: StartExecution via Alias

Java producers should read the alias ARN from configuration rather than hardcoding an unqualified state machine ARN. AWS SDK for Java 2.x example:

```java
import software.amazon.awssdk.services.sfn.SfnClient;
import software.amazon.awssdk.services.sfn.model.StartExecutionRequest;
import software.amazon.awssdk.services.sfn.model.StartExecutionResponse;

public final class WorkflowStarter {
    private final SfnClient sfn;
    private final String productionAliasArn;

    public WorkflowStarter(SfnClient sfn, String productionAliasArn) {
        this.sfn = sfn;
        this.productionAliasArn = productionAliasArn;
    }

    public String start(String operationId, String workflowInputJson) {
        StartExecutionRequest request = StartExecutionRequest.builder()
                .stateMachineArn(productionAliasArn)
                .name(toExecutionName(operationId))
                .input(workflowInputJson)
                .build();

        StartExecutionResponse response = sfn.startExecution(request);
        return response.executionArn();
    }

    private String toExecutionName(String operationId) {
        // Normalize to satisfy Step Functions character/length limits.
        return "op-" + operationId.replaceAll("[^A-Za-z0-9_-]", "-");
    }
}
```

This is an abbreviated example; validate execution name length/uniqueness and serialize inputs using a JSON library. Store the execution ARN alongside the operation record for status queries. Configure the alias ARN per environment via parameter/config management.

`StartExecution` has different idempotency semantics by workflow type: for Standard, the same execution name and input while the execution is running returns the original start result; if the execution is closed or the input differs, the API returns `ExecutionAlreadyExists`. Execution names can be reused 90 days after an execution closes. Express has no `StartExecution` API idempotency. Even with Standard idempotency, never use execution names as a substitute for business idempotency. The same order might be resubmitted after execution closure, or a new request with a different name could still duplicate side effects.

## 26. Checking Which Version an Execution Ran On

When started with a version ARN or alias ARN, Step Functions associates the execution with that qualifier. `DescribeExecution`/`ListExecutions` can provide the corresponding alias/version details. Use this information in dashboards and incident triage.

Example inventory entry:

```text
operationId: order-9381
executionArn: arn:...:execution:OrderFulfillment:op-order-9381
stateMachineAliasArn: arn:...:stateMachine:OrderFulfillment:PROD
stateMachineVersionArn: arn:...:stateMachine:OrderFulfillment:13
workflowRelease: orders-2026.11.17.3
inputSchemaVersion: 2
```

Do not record only the `PROD` alias: aliases can be updated many times. Persist the exact selected version for each execution to investigate incidents accurately.

CloudWatch metrics by version/alias help compare `ExecutionsStarted`, `ExecutionsSucceeded`, `ExecutionsFailed`, `ExecutionsTimedOut`, and `ExecutionTime`. Avoid creating arbitrary metric dimensions from execution IDs due to high cardinality.

## 27. End-to-End Release Process

A release can follow this sequence:

1. **Source control:** review ASL, task code, schemas, and release manifest.
2. **Compatibility check:** verify the new workflow reads supported inputs/states and old dependencies still work.
3. **Build tasks:** build Java artifacts/containers, test, and publish immutable Lambda function versions.
4. **Validate definition:** run `ValidateStateMachineDefinition` and contract tests.
5. **Update state machine:** perform controlled updates to definition/role/configuration.
6. **Publish version:** create version ARN and persist artifact metadata.
7. **Smoke test:** start an execution by version ARN in staging.
8. **Alias canary:** route a small percentage of new executions to the new version.
9. **Observe:** compare per-version metrics, business success, and downstream impact.
10. **Promote:** ramp weight to 100% once criteria are met.
11. **Drain old:** monitor old executions and keep needed dependencies alive.
12. **Retire:** remove old code/schemas/resources once no executions require them.

In pipelines, never run `UpdateStateMachine` and immediately flip an alias without waiting to publish/verify the version ARN and state. AWS notes that `StartExecution` calls made within a few seconds after `UpdateStateMachine` may still use the old definition/role; qualified versions/aliases make releases clearer.

## 28. Failure Scenarios to Drill

| Scenario | How to Test | Expected Outcome |
|---|---|---|
| New version fails during canary | Inject controlled failure in test task | Alias rollback affects only new executions |
| Old execution is waiting | Hold in `Wait`/callback then publish new version | Old execution continues under old definition |
| Dependency alias changed | Shift Lambda alias before old workflow reaches task | Detect dependency drift; pin versions or maintain compatibility |
| Redrive after release | Fail an old execution then redrive it | Redrive uses original definition/version |
| Input schema changed | Start old execution then deploy new producer schema | Adapter/compatibility lets old execution continue |
| Rollback after side effect | Task reserved inventory then new version fails | Compensation/reconciliation avoids duplicate side effects |
| Canary alias error spike | Trigger error only in new version | Version-specific metrics detect and trigger rollback |
| New workflow lacks IAM | Remove permission on test role | Validation/integration tests block before production |
| Execution migration | Create checkpoint and start new version | Single-owner/idempotency stops two executions from acting together |
| Deleting old version too early | Attempt retirement while executions/redrives remain | Release gate blocks deleting still-needed dependencies |

## 29. Common Deployment Pitfalls

| Pitfall | Consequence | Fix |
|---|---|---|
| Assuming definition update moves old executions | Wrong assumptions about running logic | Old executions keep old definition/role; define drain/migration policies |
| Starting executions with unqualified ARN | Hard to trace version/alias and control releases | Use alias/version ARNs in production |
| Versioning only the state machine | Lambda aliases/dependencies still mutate underneath | Pin task versions or maintain compatibility |
| Shifting alias then deleting old version | Old executions/redrives lose dependencies | Drain and check redrive windows before retiring |
| Using redrive to apply new definitions | Redrive resumes old definition | Start a new execution with transformed input/checkpoint |
| Restarting entire workflow from scratch | Old side effects may repeat | Checkpoints, idempotency, and compensation |
| Not versioning input schemas | Old executions fail to parse new fields | Additive changes, adapters, and expand-contract |
| Viewing only aggregate metrics in canary | New version errors blend into baseline | Use version/alias metric dimensions |
| Assuming alias routing is tenant-sticky | Same tenant can hit multiple versions | Route/pin versions by business ID if needed |
| Editing IAM policy of an active role | Old executions may suffer unexpected permission changes | Manage policies as artifacts and review compatibility |
| Omitting workflow release metadata | Incidents cannot tell which release an execution used | Record version ARN, commit, schema, and dependency manifest |

## 30. Pre-Release Checklist

- [ ] Definition reviewed, validated, and stored in source control.
- [ ] New state machine version published with version ARN.
- [ ] Production alias points to tested version(s).
- [ ] Callers use alias/version ARNs instead of unqualified ARNs.
- [ ] Workflow/task dependencies are pinned or have a compatibility window.
- [ ] Input/event schemas have versions and migration paths.
- [ ] Database schemas use expand-contract while old executions remain active.
- [ ] Old executions are inventoried by version/alias and current state.
- [ ] Drain deadlines and policies exist for long-lived executions.
- [ ] Redrive policy accounts for redrive using the original definition.
- [ ] Idempotency keys do not depend solely on workflow version.
- [ ] Side effects have compensation/reconciliation where needed.
- [ ] Canary has weights, duration, and promote/rollback thresholds.
- [ ] Metrics/logs distinguish versions and aliases.
- [ ] Alias rollback is rehearsed; team understands faulty-version executions keep running.
- [ ] Old versions/dependencies are not deleted while executions or redrives still need them.
- [ ] Release manifest records commit, workflow version, task versions, and schema versions.
- [ ] IAM roles/policies, logging, tracing, and encryption are verified.
- [ ] Runbook exists for handling in-flight executions and migrating to new executions.

## References

- [Step Functions state machine versions](https://docs.aws.amazon.com/step-functions/latest/dg/concepts-state-machine-version.html)
- [Step Functions state machine aliases](https://docs.aws.amazon.com/step-functions/latest/dg/concepts-state-machine-alias.html)
- [Continuous deployments with versions and aliases](https://docs.aws.amazon.com/step-functions/latest/dg/concepts-cd-aliasing-versioning.html)
- [Associating executions with versions and aliases](https://docs.aws.amazon.com/step-functions/latest/dg/execution-alias-version-associate.html)
- [UpdateStateMachine API](https://docs.aws.amazon.com/step-functions/latest/apireference/API_UpdateStateMachine.html)
- [StartExecution API](https://docs.aws.amazon.com/step-functions/latest/apireference/API_StartExecution.html)
- [PublishStateMachineVersion API](https://docs.aws.amazon.com/step-functions/latest/apireference/API_PublishStateMachineVersion.html)
- [Redrive executions](https://docs.aws.amazon.com/step-functions/latest/dg/redrive-executions.html)
- [Step Functions error handling](https://docs.aws.amazon.com/step-functions/latest/dg/concepts-error-handling.html)
- [AWS Lambda function versions and aliases](https://docs.aws.amazon.com/lambda/latest/dg/configuration-versions.html)

## Conclusion

Releasing a new workflow version does not automatically migrate in-flight executions. Step Functions preserves the definition and role ARN of older executions; versions and aliases govern which version new executions start on. Publish immutable versions, use aliases for canary rollouts, pin Lambda/task dependencies when reproducibility is required, and maintain compatible input and database contracts during drain windows. On rollback, aliases only redirect new executions; executions already running on the faulty version must either finish, stop and compensate, or migrate to a new execution using a controlled checkpoint. Standard Workflow redrives resume the original definition, so combine idempotency, release manifests, version-specific observability, and clear dependency retirement policies.
