# Upgrading Workflow Definitions While Executions Are Still Running

In serverless applications, a workflow can orchestrate a process lasting from seconds to hours or days. While executions are waiting for payment, approval, or an external event, engineering teams still need to update the workflow definition to add steps, adjust retries, update timeouts, or fix bugs.

The challenge is that a new deployment does not affect only executions started afterward. Already-started executions may hold state matching the old definition while task handlers, event schemas, or downstream services have been upgraded. Without version and compatibility management, running workflows can fail mid-flight or trigger duplicate side effects.

This lesson explains how to safely upgrade workflows while executions remain active: separating workflow definitions from execution state, managing versions, keeping data and task contracts compatible, choosing rollout strategies, and migrating running executions only when explicit mechanisms exist.

## Learning objectives

After this lesson, you will be able to:

- Explain why workflow definitions and running executions must be managed separately.
- Distinguish updating a definition, creating a new version, and migrating a running execution.
- Design workflow versioning and route new executions to the target version.
- Maintain compatibility across state data, event contracts, and task handlers over multiple versions.
- Choose between draining, backward-compatible rollouts, and explicit migration.
- Plan deployment, monitoring, rollback, and retirement of older workflow versions.

## 1. Workflow definitions and running executions are two distinct things

A **workflow definition** describes the process: states or steps, transition order, branching conditions, invoked tasks, timeouts, retries, catch blocks, parallel branches, and termination rules.

An **execution** is a specific run of a workflow. Each execution has its own input, current state, intermediate data, history of completed steps, and pending tasks. Many executions can run concurrently from the same definition.

For example, an order-processing workflow might include:

1. Validate order.
2. Reserve inventory in warehouse.
3. Charge payment.
4. Request shipment.
5. Mark order completed.

One execution might be waiting on payment in step 3 while the team deploys a new definition adding a risk-assessment step before inventory reservation. The older execution has already passed earlier steps; it cannot automatically rewind to the beginning to run the new step without an explicit business decision and migration.

| Component | Meaning | Upgrade question |
|---|---|---|
| Workflow definition | Graph of states, tasks, and transitions | Which definition will new executions use? |
| Workflow version | Immutable published definition revision | Can it be reproduced or rolled back to? |
| Execution state | Current state and data of a single run | Is the stored data still valid for the new version? |
| Task implementation | Java function, service, or API called by a task | Can older executions still call a compatible handler? |
| Event/data contract | Schemas for inputs, outputs, and inter-step messages | Can producer and consumer versions parse each other's data? |

**Updating a definition does not equal migrating running executions.** A platform may pin executions to the definition they started with, or apply different update semantics depending on the product. Always verify the exact behavior of your orchestrator before deploying. Never assume all executions automatically switch to the new definition.

## 2. Why upgrading while workflows are running easily causes failures

Long-running workflows frequently span multiple application releases. An execution can start under code version A, wait hours for a callback, and then resume after the system has deployed code version B.

The following changes can break in-flight executions:

- **Renaming or deleting states:** an execution holding an old state name may fail to resume if the platform does not retain a definition snapshot.
- **Changing data structures:** the next step expects new fields or different data types than what is persisted in state.
- **Changing task input/output:** a new Java handler cannot parse old payloads, or new outputs break old state transitions.
- **Changing retries and timeouts:** older executions may retry under different policies or expire earlier than expected.
- **Changing conditional branches:** a running execution may enter a new branch whose preconditions its current state does not satisfy.
- **Changing callback/task tokens:** a task waiting on a callback may fail to receive signals under the new format.
- **Changing function implementations:** an older definition might still point to a mutable alias or endpoint that was overwritten with new code.
- **Changing side effects:** a task re-run after an error may submit payment, email, or shipping requests a second time.

The risk is not confined to the definition alone. An old workflow version might invoke the same Lambda function name or HTTP endpoint that was updated in place. Consequently, versioning the workflow without versioning task implementations is insufficient to protect in-flight executions.

## 3. Choosing an upgrade strategy

Three common strategies exist. Choose based on execution lifespan, compatibility constraints, and platform migration support.

| Strategy | Approach | When suitable | Trade-offs |
|---|---|---|---|
| Drain old version | Stop starting new executions on the old definition and wait for old executions to finish | Workflows have bounded duration and running executions can wait | Requires keeping the old version longer; very long flows slow retirement |
| Backward-compatible rollout | New definition and tasks still understand state/input/output from old versions | Old executions must keep running after the new version is deployed | Requires maintaining multi-version compatibility and thorough testing |
| Explicit migration | Move running executions at defined checkpoints to a new workflow version | Clear business requirement exists and platform or application supports migration | Complex; must preserve state, side effects, callbacks, and history |

### Drain old version

This is usually the simplest and safest approach when workflows have a clear maximum duration:

1. Publish the new workflow version.
2. Switch the entry point for new executions to the new version.
3. Keep the old definition, task handlers, and schemas intact so running executions finish cleanly.
4. Monitor active execution counts on the old version.
5. Retire the old version only once zero executions require it, or overdue executions have been resolved per policy.

Never delete functions, secrets, queues, or endpoints still needed by older workflows. An old workflow can remain in a wait state for a long time, so “no recent invocations” does not prove a version is no longer in use.

### Backward-compatible rollout

When you cannot wait for all old executions to finish, new code must understand older data. For instance, if an older version lacks a `riskLevel` field, the new handler can apply a deliberate default value.

A useful rule is **expand first, contract later**:

1. Expand handlers to read both old and new schemas.
2. Deploy compatible consumers/tasks.
3. Publish the new workflow definition that writes or uses the new field.
4. Wait for older executions to finish and old data to pass its support window.
5. Only then remove legacy compatibility branches in a separate release.

Never alter the meaning of an existing field. If a field changes units or semantics, introduce a new field or increment the schema version. An `amount` field representing VND cannot silently switch to cents without breaking older executions.

### Explicit migration

Execution migration moves an in-flight run onto a new definition. Not every orchestrator supports modifying or moving running executions. If the platform lacks native support, the application may need its own checkpoints and resume mechanisms.

Migrate only at stable boundaries—for example, after saving inventory reservation results and before starting payment. A migration procedure must:

- Identify which executions qualify and which states are eligible for transition.
- Block or coordinate older executions from advancing while being migrated.
- Read saved state and transform it to the new schema with validation.
- Record source version, target version, and migration ID.
- Preserve correlation IDs, business IDs, deadlines, and idempotency keys.
- Guarantee already-completed tasks or side effects are not re-executed.
- Provide a way to resume from the new state or roll back to the old execution if migration fails.

Never mutate a running execution's state outside the orchestrator if the platform does not support it. Doing so can desynchronize application state from the history, task tokens, or checkpoints managed by the engine.

## 4. Versioning workflow definitions

A workflow version should represent a tested, released definition. Once published, never mutate that version in place; every change produces a new version.

A convention such as the following can be used:

| Version | Changes | Status |
|---|---|---|
| order-workflow v1 | Validate order, reserve stock, charge, ship | Serving older executions |
| order-workflow v2 | Added risk check and rejection branch | Used for new executions |
| order-workflow v3 | Added refund handling and updated timeouts | In testing |

Every execution should carry metadata identifying which version it runs. Depending on the platform, the version may be recorded in execution metadata, definition ARN, resolved alias, or workflow input. If auditing is required, also store `workflowVersion` in business records.

### Immutable versions and aliases

Immutable versions ensure new executions pick the exact intended definition. An alias or stage provides a stable name to route start-execution requests to a specific version.

For example:

- `order-workflow:prod` points to `v2`.
- `order-workflow:canary` routes a small portion of test traffic to `v3`.
- `order-workflow:v1` remains intact so older executions can complete.

Aliases are typically used for shifting traffic of **new executions**. Never assume updating an alias changes the version of already-started executions; verify platform semantics and how aliases resolve at start time.

### Example with AWS Step Functions

AWS Step Functions supports publishing state machine versions and creating aliases pointing to one or more versions. When starting an execution, you can pass a version ARN or alias ARN to specify which workflow revision to run.

Java AWS SDK v2 can start an execution via an alias or version ARN:

~~~java
import software.amazon.awssdk.services.sfn.SfnClient;
import software.amazon.awssdk.services.sfn.model.StartExecutionRequest;
import software.amazon.awssdk.services.sfn.model.StartExecutionResponse;

public final class WorkflowStarter {
    private final SfnClient stepFunctions;
    private final String workflowAliasArn;

    public WorkflowStarter(
            SfnClient stepFunctions,
            String workflowAliasArn) {
        this.stepFunctions = stepFunctions;
        this.workflowAliasArn = workflowAliasArn;
    }

    public String start(String inputJson) {
        StartExecutionResponse response = stepFunctions.startExecution(
                StartExecutionRequest.builder()
                        .stateMachineArn(workflowAliasArn)
                        .input(inputJson)
                        .build());

        return response.executionArn();
    }
}
~~~

`workflowAliasArn` is configured per environment—for example, the production alias ARN of the state machine. The deployment pipeline updates the alias after validating the new version. If an execution must stay pinned to one exact revision, pass the specific version ARN instead of an alias.

This example is specific to AWS Step Functions. On other orchestrators, look for equivalent mechanisms such as immutable workflow revisions, deployment versions, release channels, or definition snapshots. How an in-flight execution binds to a version varies by product.

## 5. Maintaining state and data contract compatibility

Running executions may hold state serialized hours earlier. When definitions or tasks are upgraded, ensure that stored data remains readable.

### Adding fields compatibly

Suppose old state stores:

~~~json
{
  "orderId": "ORD-1042",
  "amount": 1250000
}
~~~

The new version adds `riskLevel`. A default value can be applied when the field is absent:

~~~json
{
  "orderId": "ORD-1042",
  "amount": 1250000,
  "riskLevel": "STANDARD",
  "schemaVersion": 2
}
~~~

New handlers must accept both old inputs lacking `riskLevel` and new inputs containing it. If business rules have no safe default, route older executions through a compatibility branch or require a controlled migration instead of guessing.

### Compatibility rules

- Adding optional fields with explicit defaults is generally safer than removing or renaming fields.
- Never change the data type or unit of an existing field without incrementing the schema version.
- Keep the ability to read old outputs in any tasks that older executions may still invoke.
- Retain state names and transitions required by persisted executions if the engine uses the live definition to resume.
- Never assume every field in execution input passes untouched to every task; verify mappings and payload contracts at each step.
- When evolving event schemas, support producers and consumers running across staggered versions during rollout.
- Keep legacy enum values until no executions or messages still use them.

### Separating workflow version from schema version

Workflow version and schema version are two distinct concepts. A workflow `v3` may still read event schemas `v1` and `v2`; a workflow `v2` may handle multiple event types sharing a schema version if business contracts allow.

Record versions explicitly at key boundaries:

~~~json
{
  "workflowVersion": "order-workflow-v2",
  "schemaVersion": 2,
  "correlationId": "corr-71a9",
  "orderId": "ORD-1042"
}
~~~

There is no need to put version fields inside every internal object if it adds no value. At boundaries between producers, orchestrators, and task handlers, however, version metadata clarifies payload interpretation and aids incident investigation.

## 6. Task handlers must also stay compatible with old executions

A common mistake is keeping workflow definition `v1` while overwriting the Lambda function or HTTP service that `v1` calls. If an active task targets a mutable function name or endpoint, old executions will invoke new code even though the definition did not change.

This can be controlled in several ways:

- **Versioned function target:** workflow `v1` calls a dedicated function version or alias for `v1`; workflow `v2` calls the new target.
- **Stable handler contract:** keep input/output APIs compatible so new handlers understand legacy payloads.
- **Adapter by workflow version:** tasks read version metadata and map payloads into the appropriate internal model.
- **Drain old task implementations:** remove old code only after zero executions can still invoke it.

For example, a Java handler can inspect `schemaVersion` and map to an internal command:

~~~java
public record OrderTaskInput(
        String orderId,
        long amount,
        Integer schemaVersion,
        String riskLevel) {
}

public record ProcessOrderCommand(
        String orderId,
        long amount,
        String riskLevel) {
}

public final class OrderTaskAdapter {
    public ProcessOrderCommand adapt(OrderTaskInput input) {
        int version = input.schemaVersion() == null
                ? 1
                : input.schemaVersion();

        if (version == 1) {
            return new ProcessOrderCommand(
                    input.orderId(),
                    input.amount(),
                    "STANDARD");
        }

        if (version == 2) {
            return new ProcessOrderCommand(
                    input.orderId(),
                    input.amount(),
                    input.riskLevel());
        }

        throw new IllegalArgumentException(
                "Unsupported schemaVersion: " + version);
    }
}
~~~

This is an illustrative adapter. In production, validate nulls, enum values, amount bounds, and default rules. If `schemaVersion` is omitted, default to `v1` only when legacy contracts explicitly specify that behavior.

## 7. Retries, timeouts, and side effects during upgrades

A workflow waiting on a retry may re-invoke a task after code has been updated. If the prior attempt committed a side effect before the engine recorded success, the task may be invoked again.

For example:

1. A task calls the payment gateway and the transaction succeeds.
2. The function times out before returning the result to the orchestrator.
3. The workflow retries the task.
4. The new handler calls payment a second time.

Versioning alone does not solve this scenario. You need an idempotency key that stays stable across retries and across workflow versions—for instance, deriving the key from `orderId` plus business operation type rather than generating a new UUID on every invocation.

When modifying retry policies, evaluate in-flight executions:

- Are previously recorded retry counts or intervals preserved?
- Do running tasks pick up the new timeout?
- Do Catch branches still match the exact error names and output formats?
- Are DLQs or compensation paths still compatible?
- Could shortening or altering a timeout cause side effects to re-execute?

Never confuse rolling back a workflow definition with rolling back side effects. If `v2` already dispatched a shipment or captured funds, reverting to `v1` does not undo those actions. Compensations or dedicated business recovery flows are required.

## 8. Process for deploying a new version while old executions are active

A controlled rollout can follow these steps:

1. **Inventory active executions:** count running executions by workflow version, current state, start time, and maximum runtime.
2. **Analyze impact:** identify affected states, fields, tasks, retries, timeouts, callbacks, and side effects.
3. **Prepare compatibility:** update task handlers to accept both old and new payloads; add schema versions or adapters if needed.
4. **Publish the new workflow version:** keep the old revision immutable and deploy the new definition under a new version.
5. **Pre-release testing:** validate the definition and test happy paths, errors, retries, timeouts, compensations, and executions with legacy inputs.
6. **Canary new executions:** route a small percentage of new executions to the new version or run in staging with representative data.
7. **Shift traffic:** update aliases or routing so new executions use the new version.
8. **Monitor side-by-side:** compare success rates, completion times, task errors, retries, timeouts, and side effects per version.
9. **Drain the old version:** retain task handlers, secrets, permissions, and endpoints required by older executions.
10. **Retire cleanly:** remove the old version only after no executions, callbacks, scheduled starts, or messages depend on it.

~~~mermaid
flowchart TD
    A["Running workflow v1"] --> B["Create and test v2"]
    B --> C["Task handlers support old and new schemas"]
    C --> D["Canary new executions on v2"]
    D --> E{"Results acceptable?"}
    E -->|No| F["Keep routing at v1 / fix v2"]
    E -->|Yes| G["Route new executions to v2"]
    G --> H["v1 continues finishing old executions"]
    H --> I["No v1 executions remaining"]
    I --> J["Retire v1 support"]
~~~

### Monitoring executions by version

Maintain dashboards or operational queries showing:

- `RUNNING` execution counts by workflow version.
- Execution counts per state and the age of those states.
- Executions waiting on callbacks, timers, or external messages.
- Success/failure rates and completion durations per version.
- Task retries, timeouts, throttling, and integration errors.
- Executions exceeding expected duration or stuck in a state.
- Committed side effects and their reconciliation statuses.

Do not count only actively executing tasks. An execution sitting in a long wait state may still depend on an older version's task handlers or secrets.

## 9. Rollback and recovery

Rollback usually means routing **new executions** back to the previous version. It does not necessarily alter in-flight `v2` executions and never automatically reverses data or side effects that already occurred.

A rollback plan should specify:

- Criteria for halting new executions on the new version.
- Which version aliases or routing rules revert to.
- Whether running `v2` executions continue, drain, or migrate.
- Which task handlers and schemas must remain deployed so `v2` executions can finish.
- How to handle data written by `v2` that is incompatible with `v1`.
- How to reconcile or compensate payments, shipments, and notifications already executed.
- Conditions required before re-releasing the fixed new version.

If `v2` has already persisted records under a new schema, do not automatically strip fields or force records back into the old schema. Use audited data migrations and preserve backward-compatible reads during rollback windows.

## 10. Scenario example: adding an order risk check step

Workflow v1:

~~~mermaid
flowchart LR
    A["OrderCreated"] --> B["Reserve inventory"]
    B --> C["Charge payment"]
    C --> D["Create shipment"]
    D --> E["Complete"]
~~~

Workflow v2 adds a risk assessment step:

~~~mermaid
flowchart LR
    A["OrderCreated"] --> B["Risk assessment"]
    B --> C{"Risk acceptable?"}
    C -->|Yes| D["Reserve inventory"]
    D --> E["Charge payment"]
    E --> F["Create shipment"]
    F --> G["Complete"]
    C -->|No| H["Reject / release order"]
~~~

During the rollout of `v2`, all of the following can coexist:

- `v1` executions that already reserved stock and await payment.
- `v1` executions that already captured payment and await shipment creation.
- New `v2` executions starting at the risk assessment step.
- `v2` executions rejected by risk assessment and executing the rejection branch.

Do not automatically push a `v1` execution waiting for payment backward to the risk assessment step. That could alter business decisions after stock was reserved or trigger duplicate side effects. If the new rule must apply retroactively to older orders, run a dedicated business procedure specifying which states require re-evaluation, whether stock must be released or payments refunded, and how decisions are audited.

In this situation, the easiest strategy to control is keeping `v1` for in-flight executions, routing new executions to `v2`, and migrating only a selected subset of executions when explicit business rules and checkpoints exist.

## 11. Safe workflow upgrade checklist

- [ ] Definition/version used by every active execution has been identified.
- [ ] Definition update semantics of the specific orchestrator have been verified.
- [ ] Published versions remain immutable and referenceable.
- [ ] New executions route explicitly to the intended version.
- [ ] Task handlers remain compatible with payloads from older executions.
- [ ] Schema versions, defaults, and data transformation rules are defined.
- [ ] State, task tokens, callbacks, and checkpoints are preserved during rollout.
- [ ] Retries, timeouts, catch blocks, and compensations are tested for both versions.
- [ ] Side effects use idempotency keys stable across retries and versions.
- [ ] Active execution inventory and drain criteria for old versions exist.
- [ ] Canaries and dashboards differentiate errors by workflow version.
- [ ] Rollback plans account for new executions, in-flight executions, and persisted data.
- [ ] Functions, secrets, policies, or endpoints still used by older versions are not deleted.
- [ ] Old versions are retired only after verifying zero dependent executions or triggers remain.

## Self-check

1. Why does updating a workflow definition not mean running executions automatically switch to the new definition?
2. How can a `v1` execution be impacted if the Lambda function it calls is overwritten with `v2` code?
3. When should you drain an old version rather than migrate running executions?
4. Why is adding optional fields usually easier to keep compatible than changing types or meanings of existing fields?
5. How do workflow aliases help route new executions, and what must be checked regarding already-started executions?
6. Why does rolling back a workflow definition not automatically undo payments or shipping orders?
7. What conditions must be met before retiring support for an old workflow version?

When workflows can outlive individual application releases, versioning must cover definitions, state schemas, task handlers, and side effects alike. Keeping old versions intact long enough for running executions to finish, routing new executions deliberately, and migrating only at controlled checkpoints allow teams to upgrade processes without disrupting in-flight runs.
