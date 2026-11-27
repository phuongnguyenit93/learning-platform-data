# Connectors, Triggers, and Actions in Logic Apps

An enterprise receives orders through an API and must validate inputs, send processing commands to a queue, save receipts, and notify operations whenever a step fails. If all of this lives inside one monolithic integration app, every change to a target system may require modifying code and redeploying multiple components. **Azure Logic Apps** helps model integration flows as steps with a **trigger** to start, **actions** to execute, and **connectors** to integrate with external services.

Simple example:

```text
Partner sends HTTP POST
          |
          v
Trigger: When an HTTP request is received
          |
          v
Action: Parse JSON / validate
          |
          v
Action: Send message to Azure Service Bus
          |
          +-- Succeeded --> Action: Response 202 Accepted
          |
          +-- Failed ----> Action: log/alert + appropriate error Response
```

This lesson belongs to the **API and Workflow Integration** chapter of the `CLOUD_PROVIDERS_AZURE` module. The module explores Azure from subscriptions, resource groups, and Microsoft Entra ID to virtual networks, compute, storage, and data, while practicing how to deploy, monitor, secure, and control costs of an application architecture. The focus here is **how Logic Apps connects, gets triggered, processes data, and operates reliably**, not just dragging and dropping shapes in a UI.

> Examples use simulated data and resource names. Connector/action naming, authentication features, designer screens, SKUs, and technical limits may vary across **Consumption/Standard**, regions, and service versions. Only create workflows and connect to live systems when permitted by authorization and organizational policy.

## 1. Learning objectives

After this lesson, you will be able to:

1. Explain **Logic App**, **workflow**, **connector**, **connection**, **trigger**, **action**, and **run**.
2. Distinguish Logic Apps **Consumption** and **Standard**, and understand their impact on connectors and operations.
3. Choose between **built-in connectors**, **managed connectors**, HTTP actions, and other supported connectors.
4. Distinguish **polling triggers**, **webhook/event triggers**, **Request triggers**, and **Recurrence triggers**.
5. Build workflows with data-access actions, conditions, loops, variables, and error handling.
6. Use dynamic content and **Workflow Definition Language** expressions to map inputs/outputs.
7. Design **`runAfter`**, scopes, and retry policies to handle failures without duplicate sends.
8. Organize API connections, Microsoft Entra identity/managed identities, and secrets under least privilege.
9. Test and inspect trigger history, run history, and diagnostic logs.
10. Estimate costs from trigger frequency, action counts, connectors, hosting, and logging.
11. Build an HTTP → validate → Service Bus → response integration flow and handle common failure paths.
12. Recognize workflow limitations regarding transactions, idempotency, and sensitive data.

## 2. What problems does Logic Apps solve?

**Azure Logic Apps** is a platform for building and running integration workflows on Azure. Developers describe a sequence of steps via a visual designer or workflow definition; Azure handles execution, scheduling, service connectivity, and state tracking according to the selected hosting model.

A workflow can:

- Receive a webhook or HTTP request from a partner.
- Periodically read files from storage or SaaS systems.
- Transform JSON/XML and normalize payloads.
- Send messages to Azure Service Bus.
- Invoke an internal API or Azure Function.
- Write data to SQL, Blob Storage, or other services.
- Send notifications on errors or threshold breaches.
- Execute conditions, parallel branches, loops, waits, and exception handling.

Logic Apps excels when an integration flow **stitches multiple services together**, needs relatively rapid flow updates, benefits from prebuilt connectors, and requires run history visibility. It **does not automatically replace** database transaction managers, API gateways, message brokers, or compute-heavy applications. Workflows still require proper retries, schemas, permissions, limits, and error handling.

### Business example

A store has three requirements:

1. Whenever an order arrives from a partner, ingest and validate the input.
2. Push valid payloads into a queue for asynchronous backend processing.
3. If the queue is unavailable, record the incident and return a response that does not mislead the partner into believing the order was accepted.

This flow suits Logic Apps because it connects **multiple services with standard interfaces** and clear integration rules.

## 3. Core vocabulary

| Term | Meaning | Example |
|---|---|---|
| **Logic App resource** | Azure resource providing workflow execution capabilities per hosting type. | `la-orders-intake-prod` |
| **Workflow** | Definition of a process comprising a trigger and actions. | `ReceiveOrder` |
| **Connector** | Component exposing operations/triggers for a service or protocol. | Service Bus, SQL, HTTP, Blob, Office 365 |
| **Connection** | Connection/authentication config to a specific target system, usually carrying identity/credentials and scope. | Connection to Production Service Bus namespace |
| **Trigger** | Condition/event that initiates a workflow run. | HTTP request, 5-minute schedule, new message |
| **Action** | Step executed after the trigger or after another action. | Parse JSON, Condition, Send message |
| **Run** | Single workflow execution tied to a trigger and state history. | Run processing order `ORD-1042` |
| **Expression** | Runtime formula accessing/transforming data. | `triggerBody()?['orderId']` |
| **Dynamic content** | Output fields from prior triggers/actions insertable into later steps. | `orderId` from request |
| **runAfter** | Rule specifying which prior action statuses allow the next action to run. | Run alert when `Send message` is `Failed` |

**Connector is not synonymous with connection**: the Service Bus connector provides send/receive capabilities, while the connection specifies **the exact namespace and permissions** the workflow uses with that connector.

## 4. How does a workflow execute?

A workflow usually has **one trigger** as its entry point; the action graph then determines subsequent steps. Workflows can have conditional branches, parallel branches, scopes, and loops, though they are not unbounded infinite programs.

```text
                 Workflow definition
                         |
                         v
                    [TRIGGER]
                         |
                  Trigger fired?
                   /          \
                 No            Yes
                 |              |
             No run yet         v
                           Run started
                                |
                           [ACTION A]
                                |
                       +--------+---------+
                       |                  |
                    Success             Failure
                       |                  |
                   [ACTION B]         [HANDLE ERROR]
                       |                  |
                       +--------+---------+
                                |
                           Run outcome
```

A run ends in states such as **Succeeded, Failed, Cancelled, Running**, or other runtime-supported statuses. Action statuses such as **Succeeded, Failed, Skipped, TimedOut** are key signals driving branching via `runAfter`.

### Triggers that inspect or receive data are not actions

Examples:

- **Recurrence trigger** runs on a schedule.
- **Request trigger** listens for HTTP requests.
- **Service Bus trigger** receives events/messages per connector mechanics.
- **SQL action** runs a query after a trigger has already fired.
- **Response action** returns output to the caller in eligible workflows.

Confusing triggers with actions leads to flawed designs: placing a “read file” action after Recurrence is not equivalent to a “when a file is modified” trigger in frequency, state tracking, polling, permissions, or ingestion behavior.

## 5. Consumption vs. Standard: impact on connectors, triggers, and actions

Azure Logic Apps offers two primary hosting models:

| Aspect | Logic Apps Consumption | Logic Apps Standard |
|---|---|---|
| Hosting model | Multi-tenant under the Consumption model. | Single-tenant Logic Apps runtime on Standard hosting infrastructure. |
| Workflow organization | Typically one workflow per Logic App resource. | One Logic App resource can host **multiple workflows**. |
| Workflow runtime | Stateful workflows under the Consumption model. | Supports **stateful** and **stateless** workflows per Standard capabilities. |
| Connectors | Built-in/control actions and managed connectors per support. | In-app/built-in service-provider connectors alongside managed connectors depending on service. |
| Connections | Managed API connections play a central role for many connectors. | Uses built-in connection settings and managed API connections depending on connector type. |
| Scaling/billing | Typically billed per trigger/action execution, connector operations, and related items. | Hosting plan/runtime/capacity charges plus managed connector operations and related items. |
| Local development | Varies by tooling; Azure Portal designer is common. | Standard workflow projects fit VS Code and CI/CD pipelines per supported features. |
| Isolation/networking | Depends on SKU and supported config. | Offers richer networking and operational options per hosting plan; verify region/plan. |

**Standard does not mean all connectors are free**, and **Consumption does not mean zero charges when idle** if auxiliary resources or other billing meters remain active. Always review actual pricing meters.

### Stateful vs. stateless (Standard)

- **Stateful:** persists and tracks workflow state to manage steps, duration, and run history via the runtime; fits long-running integrations needing visibility and recovery.
- **Stateless:** optimizes short flows by skipping step-by-step state persistence; carries stricter duration/length and history constraints, suited to low-latency request flows when requirements fit.

Never pick stateless for a multi-day approval flow that exceeds runtime/stateless limits. Conversely, do not assume every flow needs detailed step-by-step history persistence when high throughput and low latency matter.

## 6. What is a connector?

A **connector** wraps integration operations for a service or protocol, letting the designer surface triggers and actions without hand-crafting every raw HTTP request.

Examples:

| Connector / category | Typical trigger/action | Scenario |
|---|---|---|
| **HTTP** | Call a REST endpoint or receive requests via Request trigger. | Call internal/partner APIs. |
| **Azure Service Bus** | Send messages, receive messages per connector capabilities. | Queue orders for processing. |
| **Azure Blob Storage** | Read/write blobs, monitor blob/file changes where triggers exist. | Save receipts or ingest files. |
| **Azure SQL** | Query/insert/update records via supported actions. | Data reconciliation. |
| **Office 365 Outlook** | Trigger on new emails, send emails. | Notifications or mail intake. |
| **SharePoint** | Monitor or create/update items per connector. | Approvals and collaboration. |
| **Event Grid / Event Hubs** | Process streams or events when matching connectors apply. | Event-driven integration / stream ingestion. |
| **Azure Functions** | Invoke configured Function endpoints. | Specialized logic beyond data actions. |
| **Custom connector** | Expose a custom API interface per supported model. | Partner/internal systems lacking built-in connectors. |

Action names and capabilities vary by **connector, workflow type, SKU, and authentication mode**. Never infer “there is a connector” means every target-system operation is supported.

### What does a connector provide?

1. Input/output contracts inside the designer.
2. Service-aligned connectivity and authentication helpers.
3. Dynamic content bindings from action results.
4. Polling or webhook triggers on selected connectors.
5. Error/status signals for branching.
6. Maintained integration docs and mechanics instead of building REST plumbing from scratch.

### What does a connector NOT do?

- Does not guarantee business data committed cleanly in the backend.
- Does not solve duplicate requests or idempotency automatically.
- Does not replace authorization and network security.
- Does not guarantee every HTTP 5xx retries forever until success.
- Does not create distributed ACID transactions spanning SQL, Service Bus, and email.
- Does not waive API limits, rate limits, or SaaS target charges.

## 7. Built-in, managed, and service-provider connectors

This distinction is essential when choosing between Logic Apps Consumption and Standard.

### Built-in connectors / actions

Operations such as **Control, Data Operations, HTTP/Request, or workflow operations** run directly within the runtime as built-in capabilities. Standard also introduces **in-app service-provider connectors** for selected Azure services running inside the Standard runtime.

Typical characteristics:

- Execute inside the local runtime rather than routing through the managed connector gateway for supported operations.
- Different connection configuration compared to managed connectors.
- Better performance/latency in specific scenarios.
- Still subject to limits, RBAC, and target-service/infrastructure costs.

### Managed connectors

Managed connectors normally access services through the **Azure managed connector infrastructure** and rely on **API connection** configurations. Examples include SaaS connectors like Outlook/SharePoint as well as selected Azure connectors.

Characteristics:

- Often require creating an **API connection** resource/configuration and an authorization step.
- Subject to connector/API quotas, throttling, and connector operation billing.
- Credentials can expire or be revoked.
- Require managing connection ownership, consent, tenant, and secret rotation.
- In Standard, some Azure services offer both a built-in service-provider connector and a managed connector; **they are not identical** in connection settings or runtime behavior.

### Comparison table

| Criterion | Built-in / in-app | Managed |
|---|---|---|
| Where integration runs | Inside the workflow runtime/host per supported connector. | Managed connector / API connection infrastructure per service model. |
| Connection config | Often app settings or dedicated connection config. | Typically tied to a managed API connection resource. |
| Authentication | Varies by connector; may support managed identity. | Varies by connector/operation: OAuth, API key, or managed identity where supported. |
| Availability | Depends on Consumption/Standard and service provider. | Depends on managed connector catalog, region, and tier. |
| Limits | Runtime, connector, and target system limits. | Connector throttling, API limits, and target system limits. |
| Cost | Hosting/operations per SKU. | May incur additional managed connector operation fees. |

**Never choose a connector based solely on its designer icon.** Check connector type, authentication, runtime behavior, retries, networking, cost, and SKU support.

## 8. Connections and API connections: authenticating to the right target

A “Send message” action must know **which namespace to send to and with what permissions**. That comes from connection configuration, not the action's display name.

```text
Logic App: orders-intake
    |
    +-- Connector: Azure Service Bus
             |
             +-- Connection: sb-orders-prod
                     |
                     +-- Endpoint: target namespace
                     +-- Authentication: managed identity / supported credential
                     +-- Authorization: Send permission
```

Items to verify:

- **Target resource:** is it the exact Production namespace/storage account/database?
- **Principal:** managed identity, service principal, or user credential?
- **Role/scope:** only Send on the queue, or overly broad Manage on the namespace?
- **Network:** endpoint, private DNS, firewalls, VNet integration?
- **Lifecycle:** what happens when the connection creator leaves the company, OAuth consent expires, or a secret rotates?
- **Ownership:** are API connection resources provisioned/deployed alongside the workflow?
- **Secrets:** are connection strings/tokens leaking into JSON definitions, deployment logs, or parameters?

An API connection **succeeding at creation time** does not prove the live action will run reliably long term. Verify target-resource permissions, token refresh, and execute a safe test transaction.

## 9. Triggers: what starts a run

A **trigger** defines when a workflow begins. In Logic Apps, triggers either check on a schedule or fire on incoming requests/events depending on the connector.

Common categories:

| Trigger type | High-level behavior | Example |
|---|---|---|
| **Recurrence** | Runtime triggers on a configured schedule. | Aggregate reports every 15 minutes. |
| **Polling** | Periodically checks a source for new items/events. | Check for new files or database rows. |
| **Webhook / push** | Registers a callback; source pushes when events occur. | Change notifications where source supports it. |
| **Request** | Workflow exposes an HTTP trigger endpoint. | Partner POSTs an order. |
| **Event/message trigger** | Receives messages/events from a broker per connector capabilities. | New message in a Service Bus queue. |
| **Manual / external invocation** | Workflow invoked by another system/user/logic via supported mechanism. | Testing or workflow chaining. |

Never assume every action on a connector has a matching trigger. Available triggers depend on the connector, workflow type, and SKU.

### Can one connector have both triggers and actions?

Yes. For instance, the Service Bus connector provides triggers to receive messages and actions to send messages; the SQL connector can provide change-tracking triggers and query actions. However, connection requirements, permissions, and polling behavior can differ between triggers and actions.

## 10. Polling triggers: latency and check counts

A polling trigger runs on an interval—for example, checking every 5 minutes for new items.

```text
09:00  Poll → no data
09:05  Poll → found item A → workflow run
09:10  Poll → items B, C → workflow run(s) per trigger mechanics
09:15  Poll → no data
```

**Do not assume** one poll equals one workflow run or always fetches every item in one shot; triggers may use batching, split-on, watermarks, or pagination depending on the connector.

### What must be configured?

- Trigger **interval/frequency**.
- **Time zone** if tied to business schedules.
- **Start time** and data filters.
- **Concurrency** if multiple runs can overlap.
- **Polling window**, pagination, or connector checkpointing where supported.
- **Retry/backoff** when the source is temporarily unreachable.
- Target API **rate limits** or request quotas.

### Latency and cost

With a 5-minute interval, new items are not detected instantaneously. Latency also depends on connector backend, throttling, processing duration, and runtime scheduling. **Setting a 1-second poll does not guarantee near-real-time** if the connector enforces a minimum polling interval or the target service cannot keep up.

A polling trigger can consume operations/API quota even when returning zero items, depending on SKU and connector behavior. When reacting strictly to events, check if the source supports webhooks/push.

## 11. Webhook/push triggers: pushing events to workflows

A webhook trigger typically registers or uses a callback subscription with a source system; the source then **pushes notifications** to that endpoint to start runs.

```text
Logic App registers callback
         |
         v
Source emits event
         |
         +-- POST callback → Logic App trigger → run
         |
         +-- may retry callback per source rules
```

Pros:

- Eliminates continuous empty polling where supported.
- Reduces event-to-run latency.
- Suits sources with reliable notification subscriptions.

Watch out for:

- Callback registration/deregistration and subscription expiration.
- Webhook authentication/signatures if provided by the source.
- Retries/duplicate callbacks: **one event can trigger multiple runs** when sources redeliver.
- Public/private endpoint reachability and firewalls.
- When a workflow is disabled/deleted/moved, stale subscriptions might linger on the source depending on the connector.
- Never treat a webhook notification as complete committed proof without verifying; sometimes you must call the source API for authoritative state.

**Webhook triggers and Request triggers differ:** Request triggers expose an endpoint for callers to invoke directly; webhook connectors actively manage event-source subscriptions and specific handshakes.

## 12. Request triggers: creating an HTTP endpoint for a workflow

**When an HTTP request is received** is the standard trigger for self-managed webhooks or API intake.

Example caller payload:

```http
POST /orders HTTP/1.1
Content-Type: application/json

{
  "orderId": "ORD-1042",
  "customerRef": "C-81",
  "amount": 250000,
  "currency": "VND"
}
```

The snippet **simulates an HTTP request**; a real Logic App URL is not automatically `/orders`. The live URL is generated by the runtime and may include **signatures/credentials** and workflow-specific path segments.

### Design steps

1. Add a Request trigger.
2. Define a JSON schema for the input payload.
3. Restrict allowed HTTP methods/request styles per supported configuration.
4. Authenticate callers using an approved model.
5. Set payload limits, timeouts, concurrency, and error handling.
6. Parse and validate the payload.
7. Perform a durable action (such as sending to Service Bus) before returning `202 Accepted`.
8. Use a **Response** action to return explicit status codes and bodies.

### Protecting callback URLs

A Request trigger URL can embed an access signature (SAS or token) depending on configuration. **Anyone possessing that URL can invoke it** under that auth mode; never paste signed URLs into Git, logs, screenshots, or public tickets.

Protections to evaluate per SKU and requirements:

- Microsoft Entra authentication on workflow endpoints where supported.
- API Management in front of the endpoint enforcing OAuth/JWT, quotas, and rate limits.
- HTTPS/TLS and private networking/access restrictions.
- WAF/Front Door or gateways per topology if needed.
- Rotating/revoking callback signatures and restricting who can read URLs.
- Avoiding sensitive data in query strings or URLs wherever possible.

**Never equate schema validation with authorization.** Valid JSON can still be sent by an unauthorized caller.

## 13. Recurrence triggers: schedules and time zones

Recurrence fits periodic flows:

- Reading sales metrics every 15 minutes.
- Generating nightly reports.
- Running daily reconciliation checks.

Example:

```text
Trigger: Recurrence
Frequency: Day
Interval: 1
Time zone: Asia/Ho_Chi_Minh (if supported by designer/runtime)
At these hours: 07
At these minutes: 30
```

This is a **conceptual configuration**, not a literal JSON manifest. In practice, verify timezone and daylight-saving rules for the host region, start time, missed-schedule handling, and overlapping runs.

### Preventing overlapping workflow runs

If a run takes 20 minutes while Recurrence fires every 10 minutes, runs overlap, accessing the same files/records and creating duplicates. Mitigate by:

1. Capping trigger concurrency where supported.
2. Using business locks or idempotency mechanisms.
3. Assigning distinct batch/window IDs per period.
4. Scheduling intervals realistic for observed run durations.
5. Using queues/checkpoints/reconciliation when no period can be skipped.

Never insert arbitrary delays hoping “the previous run probably finished,” because execution times fluctuate.

## 14. Actions: individual steps in a processing flow

After the trigger, each action executes a specific operation such as:

- **Compose** values.
- **Parse JSON** against a schema.
- **Condition** branching.
- **For each** iterating over items.
- **HTTP** calling a service.
- **Send message** to Service Bus.
- **Create blob** storing documents.
- **Response** returning HTTP responses.
- **Scope** grouping actions.
- **Terminate** ending the workflow with an explicit status.

Every action has:

- **Inputs:** data, parameters, and connections.
- **Outputs:** results or error details.
- **Status:** `Succeeded`, `Failed`, `Skipped`, `TimedOut`, etc. per runtime.
- **`runAfter`:** conditions on prior action statuses.
- **Retry policy:** how transient errors retry where supported.
- **Timeout:** action duration limit per configuration and runtime.

**An action succeeding at the HTTP/connector level does not prove business completion.** For instance, a Service Bus Send action succeeding only proves the broker accepted the message—not that the consumer has paid or fulfilled the order.

## 15. Control actions: Condition, Switch, For each, Until, and Scope

| Action | Meaning | Common mistake |
|---|---|---|
| **Condition** | Binary branch based on an expression. | Comparing mismatched string vs. number types or nulls. |
| **Switch** | Multi-way branch on discrete values. | Missing a Default branch or failing on newly added enum values. |
| **For each** | Runs actions per array element. | Mutating shared variables in parallel or flooding target APIs. |
| **Until** | Loops until a condition holds or limits hit. | Missing safe iteration/time caps, polling endlessly. |
| **Scope** | Groups actions for collective status and error handling. | Misreading `Skipped` vs. `Failed` across scope and inner actions. |
| **Terminate** | Ends the workflow with an explicit status. | Marking `Succeeded` when the workflow actually failed. |
| **Delay / Delay until** | Pauses execution. | Using Delay in place of durable queues/long-term retries. |
| **Parallel branches** | Runs independent branches concurrently. | Two branches mutating the same resource without synchronization. |

### Condition example

An order is valid when `amount > 0` and `orderId` is non-empty:

```text
Condition:
  amount > 0 AND orderId is not empty
    |
    +-- True:
    |     Send message to queue
    |
    +-- False:
          Respond 400 Bad Request / audit invalid data
```

If `amount` arrives as a string like `"250000"`, cast types explicitly before numeric comparison. If a field is missing, expressions may return `null` or throw errors depending on property access syntax.

### Switch example

```text
Switch eventType
  OrderPlaced    → queue orders-created
  OrderCancelled → queue orders-cancelled
  Other/Default  → quarantine/validation error
```

Never route Default to “success” if event schemas may evolve later; silently dropping unknown events is notoriously hard to notice.

## 16. For each and parallelism: avoiding race conditions

Suppose a workflow receives 100 products and must call an inventory update API for each one:

```text
For each product in products:
    HTTP POST /inventory/update
```

Issues:

- `For each` may run iterations in parallel by default/configuration.
- Target APIs may cap concurrent requests and return HTTP 429.
- Iterations are not guaranteed to finish in input order.
- Updating a **shared variable** across parallel iterations causes race conditions.
- A single failing iteration affects overall loop status per runtime rules.

### Good design practices

1. Parallelize loops only when items are independent.
2. When ordering or shared state matters, lower concurrency—running sequentially when required.
3. Attach per-item idempotency keys.
4. Configure bounded retries/backoff for 429/503 responses.
5. Handle pagination so you never assume 100 items when the source holds 10,000.
6. For large volumes, enqueue individual tasks onto a queue so workers scale safely.

Never change workflow-wide concurrency settings just to fix one loop when separating tasks into safer parallel actions/workers works better.

## 17. Data Operations: Compose, Parse JSON, Select, Filter array

Data transformation actions normalize payloads without requiring a microservice for every mapping.

### Compose

Constructs a new value from inputs:

```text
Input:
  orderId = "ORD-1042"
  amount = 250000

Compose:
  {
    "orderId": "ORD-1042",
    "amount": 250000,
    "source": "partner-api"
  }
```

### Parse JSON

Declares a JSON schema so the designer surfaces strongly named dynamic content fields. Example schema:

```json
{
  "type": "object",
  "properties": {
    "orderId": { "type": "string", "minLength": 1 },
    "amount": { "type": "number", "exclusiveMinimum": 0 },
    "currency": { "type": "string" }
  },
  "required": ["orderId", "amount", "currency"],
  "additionalProperties": false
}
```

This is an illustrative strict schema. For evolving partner APIs, `additionalProperties: false` can reject newly added partner fields; align via API contracts rather than guessing.

### Select

Reshapes each array element into a new structure, e.g., mapping `[{sku, qty, price}]` to `[{productId, quantity}]`.

### Filter array

Retains elements matching a predicate, e.g., orders with `amount > 0`.

**Never confuse Filter array with authorization or input validation**: silently dropping invalid rows can make order totals wrong. For critical business payloads, reject invalid inputs or explicitly record filtered items.

## 18. Dynamic content and Workflow Definition Language expressions

The designer exposes **Dynamic content** from triggers and prior actions. Under the hood, workflows evaluate expressions to read runtime data.

Examples:

| Purpose | Illustrative expression | Meaning |
|---|---|---|
| Read trigger body | `triggerBody()` | Trigger payload. |
| Null-safe property read | `triggerBody()?['orderId']` | `orderId` field if present. |
| Read action output | `outputs('Compose_Order')` | Output value of the named action. |
| Read action body | `body('Parse_JSON')` | Body returned by the named action. |
| Read nested output field | `body('Parse_JSON')?['amount']` | Parsed `amount` value. |
| Format JSON | `string(...)`, `json(...)` | Convert types as needed. |
| Current timestamp | `utcNow()` | Runtime UTC timestamp; does not replace original event timestamp. |
| Generate ID | `guid()` | New UUID, useful for correlation when needed. |
| Concatenate strings | `concat('order-', triggerBody()?['orderId'])` | Build a prefixed key. |

**Action names in expressions must match internal workflow action names**, which do not always match display labels after renames. After renaming an action, verify all referencing expressions.

### Expression syntax in JSON

Full expressions in workflow JSON normally start with `@`:

```json
{
  "orderId": "@triggerBody()?['orderId']",
  "correlationId": "@coalesce(triggerBody()?['correlationId'], guid())",
  "receivedAtUtc": "@utcNow()"
}
```

When embedding expressions inside literal text strings, use **interpolation** syntax `@{...}`. Never place quotes or braces carelessly where the runtime treats the expression as a plain literal string.

### Nulls and parsing errors

Missing fields evaluate to `null`; calling `int(null)` or chaining unguarded nested property accesses can fail the action. Therefore:

1. Validate against accurate schemas.
2. Use the null-safe `?` operator where appropriate.
3. Use `coalesce` for meaningful defaults.
4. Check real source types (string vs. number vs. array).
5. Never default missing totals to `0` if doing so masks malformed payloads.

## 19. Workflow JSON: minimal structure

Logic Apps workflow definitions center around `triggers` and `actions`. The minimal example below **illustrates structure and expressions only**—it does not enqueue anything yet:

```json
{
  "$schema": "https://schema.management.azure.com/providers/Microsoft.Logic/schemas/2016-06-01/workflowdefinition.json#",
  "contentVersion": "1.0.0.0",
  "parameters": {},
  "triggers": {
    "When_HTTP_request_received": {
      "type": "Request",
      "kind": "Http",
      "inputs": {
        "schema": {
          "type": "object",
          "properties": {
            "orderId": { "type": "string" }
          },
          "required": ["orderId"]
        }
      }
    }
  },
  "actions": {
    "Compose_Order": {
      "type": "Compose",
      "inputs": {
        "orderId": "@triggerBody()?['orderId']",
        "receivedAtUtc": "@utcNow()"
      },
      "runAfter": {}
    },
    "Response_200": {
      "type": "Response",
      "inputs": {
        "statusCode": 200,
        "body": "@outputs('Compose_Order')"
      },
      "runAfter": {
        "Compose_Order": ["Succeeded"]
      }
    }
  },
  "outputs": {}
}
```

**Note:** Response 200 above only confirms the workflow parsed/composed the payload; **never interpret it as saving an order or durably enqueuing work**. In real scenarios, return 202 Accepted only after the durable acceptance step succeeds, matching what the API contract promises callers.

In Standard, project layouts and definition files (such as `workflow.json`, `connections.json`, and app settings) differ from Consumption deployment templates, though **trigger/actions/runAfter** concepts carry over. Never paste a Consumption ARM resource verbatim into a Standard project expecting connection references to resolve automatically.

## 20. `runAfter`: controlling behavior after success or failure

By default, subsequent actions run only after the preceding action has **`Succeeded`**. On failure, downstream actions become **`Skipped`**. Use `runAfter` to specify which prior statuses should trigger an action.

JSON fragment example:

```json
{
  "Log_failed_send": {
    "type": "Compose",
    "inputs": "Send failed or timed out; investigate",
    "runAfter": {
      "Send_message": ["Failed", "TimedOut"]
    }
  }
}
```

This is an **action-set fragment** assuming an internal action named `Send_message` exists at the matching scope/level. Action names and statuses must conform to the runtime schema.

### Key statuses

- **Succeeded:** action succeeded per its own contract.
- **Failed:** action did not complete successfully.
- **TimedOut:** action exceeded its configured timeout.
- **Skipped:** action did not run because of prior branch/status conditions.
- Some scenarios emit additional runtime states; inspect real run history before building dependent logic.

### Risks of misconfiguring `runAfter`

Suppose a workflow logs errors whenever any step fails, yet `Log_failed_send` runs only on `Send_message=Failed`. When `Send_message` hits **`TimedOut`**, logging is `Skipped` and the incident goes unrecorded. Conversely, attaching alerts to `Succeeded` creates false alarms.

Never treat an alert action showing **`Succeeded`** as proof the workflow recovered. Explicitly govern the **final run status** and whether business work completed.

## 21. Scopes and the Try–Catch–Finally pattern

In complex workflows, grouping steps into **Scopes** organizes error handling cleanly.

```text
Trigger
   |
   v
Scope: TRY
   |
   +-- Validate
   +-- Send message
   +-- Record acceptance
   |
   +---- Succeeded --------> Scope: FINALLY
   |
   +---- Failed/TimedOut --> Scope: CATCH
                                  |
                                  +-- Log sanitized error
                                  +-- Alert / compensate
                                  +-- Report failure
                                  |
                                  v
                             Scope: FINALLY
                                  |
                             Cleanup/metrics
```

This is a **design pattern**, not an automatic language construct like Java `try/catch`. In Logic Apps, scopes wire together via **Configure run after** and runtime status rules.

### Inspect nested action statuses

A Scope's overall status summarizes its inner actions and how they failed or were skipped. Inspecting only the step after a Scope can hide the true failing inner action.

To extract inner errors where supported, Logic Apps provides functions like `result('Scope_Try')`; sanitize outputs carefully and **never dump secrets/sensitive payloads** into logs.

### Finally is not guaranteed unconditionally

If a workflow stops before starting a run, gets terminated/cancelled, or runtime limits fail, a Finally scope is not guaranteed to run under every possible condition. Configure Finally via `runAfter` over **supported terminal states**, paired with external monitoring for un-triggered or cancelled runs.

## 22. Retry policies and timeouts: transient vs. permanent failures

Many HTTP/connector actions support **retry policies**, though no single rule fits every connector, status code, or error.

| Error type | Is retry usually helpful? | Notes |
|---|---|---|
| HTTP 429 rate limit | Yes, with backoff and bounds. | Honor `Retry-After` if supported by connector/runtime. |
| Transient HTTP 500/502/503/504 | Possibly. | Evaluate side effects, timeouts, and idempotency. |
| Network timeout | Possibly. | The prior request **may already have been processed by the target**. |
| HTTP 400 invalid schema | Usually no. | Fix payload or contract; blind retries fail identically. |
| HTTP 401 expired token | Fix auth/refresh. | Blind retries will not repair invalid credentials. |
| HTTP 403 missing permissions | Usually no. | Fix RBAC/authorization rather than raising retry counts. |
| Duplicate business operation | Never fixed by retrying. | Use idempotency, deduplication, and reconciliation. |

### Controlled retry pattern

- **Finite** retry count.
- **Exponential backoff** or connector-supported retry policy.
- Delay/jitter so concurrent workflows do not retry in lockstep.
- Realistic action and workflow timeouts.
- Idempotency keys for side-effecting targets.
- Alerts when retries exceed thresholds.

**Especially dangerous failure:** a POST action creating an order times out after the server already wrote to the DB, so the workflow retries and creates a duplicate order. Automatic retries cannot distinguish “server never received it” from “server committed but response got lost” unless the API supports idempotency or status queries.

## 23. Idempotency and preventing duplicate sends

In order integrations, a Request trigger may receive the **same payload multiple times** due to partner retries. Polling or webhook triggers can also re-deliver the same event per connector semantics.

Safe design:

1. Producer sends a stable `eventId` or `requestId`.
2. Logic App validates the schema and extracts the idempotency key.
3. Write a marker into a store with a **unique constraint / atomic conditional write**, or call an idempotent API.
4. Execute the side effect once per agreed key.
5. For valid duplicates, return the already-accepted/processed status rather than creating a second record.
6. Log correlation IDs for reconciliation and safe replay control.

### Example

Two HTTP requests both contain:

```json
{
  "requestId": "partner-x-2026-1042",
  "orderId": "ORD-1042",
  "amount": 250000
}
```

You cannot rely on an in-run variable `alreadyProcessed` because **two independent runs can start simultaneously**. You need shared persistent state with atomic check-and-write semantics—such as a SQL unique key, API idempotency layer, or inbox/outbox pattern.

### Logic Apps is not a distributed transaction coordinator

If a workflow runs three steps SQL → Service Bus → Email, step 3 failing does not roll back steps 1 and 2. Strong consistency requirements call for **transactional outbox, sagas/compensation, and domain-specific reconciliation** rather than trying to “undo” via `runAfter` alone.

## 24. Handling large datasets, pagination, and connector throttling

A “List rows” connector action may return only a single page of results, not the entire database. **Pagination, thresholds, and batching** capabilities vary by connector.

### Common symptoms

- The source holds 50,000 records, yet the workflow sees only a subset.
- `For each` over thousands of items stretches run duration.
- Connectors return HTTP 429 or action timeouts.
- Excessive run history drives high logging/storage costs.
- Target SaaS caps API calls per minute.
- Payloads exceed trigger/action or connector size limits.

### Design guidance

1. Verify whether pagination is supported and properly configured.
2. Pick sensible batch sizes rather than reading full history on every poll.
3. Use source watermarks or change tracking where supported.
4. Cap loop concurrency and retries.
5. For very high volumes, split into ingestion → queue/broker → workers.
6. Store large payloads in Blob Storage and pass safe references instead of embedding huge bodies.
7. Trim schemas to only required fields.
8. Monitor throttling at both **the connector** and **the target API**.

Never crank timeouts and retries up indefinitely to force a workflow into heavy ETL work; Azure Data Factory, Functions, Batch, or dedicated data pipelines may fit much better.

## 25. Security: identity, permissions, and secrets

A Logic App can be a sensitive component because it reads and writes across multiple systems.

### Principle of least privilege per connection

- Read-only workflow: grant only required **Read** permissions.
- Service Bus sender workflow: **`Azure Service Bus Data Sender`**, not `Data Owner` by default.
- Blob-writing workflow: data-plane roles scoped to the specific account/container.
- Internal API calls: tokens/audiences/scopes tailored to that API.
- Workflow editors: minimal Azure RBAC plus change approval.
- Run history viewers: restricted based on data visibility.

### Managed identity

Where connectors/actions support it, using a **system-assigned or user-assigned managed identity** reduces static client secrets. Ensure you:

1. Enable the identity on the Logic App/host resource.
2. Assign data-plane roles on the exact target resource.
3. Select managed identity authentication inside the connector if supported.
4. Verify token audience/resource and networking.
5. Test the **live** connection—never equate “identity enabled” with access to every Azure service.

**Not every managed connector/action supports managed identity identically.** When a connector supports only OAuth user consent or API keys, enforce proper credential management and rotation.

### API connections and OAuth consent

A connection authorized with an employee's account depends on that user's permissions/consent; when the employee leaves or tokens revoke, workflows break. For Production, prefer **service-owned identities/connections** with clear owners and credential/authorization review schedules.

### Secrets

- Avoid hardcoding connection strings, SAS tokens, or API keys in workflow definitions or deployment parameters.
- Use Azure Key Vault or supported secret management platforms.
- Never log secrets into `Compose` for debugging.
- Restrict who can view trigger/action inputs and outputs.
- Rotate callback signatures and OAuth credentials per runbook.
- Protect source repos, CI/CD variables, IaC state, and ARM deployment history.
- Review run history data residency and retention when handling sensitive data.

## 26. Secure Inputs, Secure Outputs, and run history exposure

Logic Apps lets you mark **Secure Inputs** and **Secure Outputs** on supported actions/triggers to mask sensitive payloads in run history.

Understand the boundaries:

- Enabling it on one action does not automatically protect **all downstream actions**.
- If a later `Compose` prints a token, it reappears elsewhere.
- Target connectors/APIs may keep their own logs.
- Developers with edit rights could add a step exposing secrets without change control.
- Check tracing/diagnostic properties or tracked properties so PII/secrets never enter telemetry.
- Masking run history **does not replace** encryption, RBAC, network security, or data minimization.

### Verification steps

1. Inventory sensitive fields: passwords, tokens, customer details.
2. Enable Secure Inputs/Outputs at all relevant steps.
3. Test run history with synthetic data.
4. Verify diagnostics / Application Insights / Log Analytics exclude forbidden values.
5. Audit who can read run history or resubmit runs.
6. Never use real secrets in screenshots or training materials.

**Rule:** if a value is not required for incident investigation, never emit it to logs just for “convenient debugging.”

## 27. API Management and Logic Apps: separation of duties

A Logic Apps Request trigger can accept HTTP requests directly, but for public APIs serving multiple partners, evaluate placing **Azure API Management (APIM)** in front.

```text
External partner
       |
       v
API Management
  - OAuth/JWT validation
  - client quota / rate limit
  - API versioning / transformation
  - request/response policies
       |
       v
Logic Apps Request trigger
  - validate business payload
  - orchestrate connectors/actions
       |
       v
Azure Service Bus / SQL / Blob
```

APIM handles request governance and security policies; Logic Apps focuses on **workflow orchestration/integration**.

Do not assume APIM automatically authenticates to a Logic App callback URL simply by knowing the endpoint. Configure **backend authentication**, secrets/managed identity, and access policies per supported product/runtime features.

### When to write an Azure Function instead of complex workflow actions?

When logic requires heavy algorithms, complex payload parsing, specialized libraries, predictable performance, or deep unit tests, offload it to **Azure Functions** or an API worker. Logic Apps calls the Function as an action with a clean contract—never cram thousands of expressions into the designer just to avoid writing code.

## 28. Real-world example: HTTP → Parse JSON → Service Bus → Response

**Business requirements:**

- Partner POSTs an order request.
- Workflow verifies `requestId`, `orderId`, and `amount > 0`.
- Workflow sends a command to Service Bus queue `order-intake`.
- Only after the broker **accepts the send**, return HTTP 202 with a correlation ID.
- On invalid schema, return 400; on enqueue failure, return an appropriate error and emit telemetry/alerts.
- Never leak tokens/sensitive PII into run history.

### Test payload

```json
{
  "requestId": "partner-x-2026-1042",
  "orderId": "ORD-1042",
  "amount": 250000,
  "currency": "VND"
}
```

### Flow design

```text
HTTP Request Trigger
         |
         v
Parse JSON / Validate payload
         |
         +---- Invalid --------> Response 400
         |
         v
Condition: amount > 0
         |
         +---- False ----------> Response 400
         |
         v
Compose normalized command
         |
         v
Send message: Service Bus queue order-intake
         |
         +---- Succeeded -----> Response 202
         |                         body: requestId, status=accepted
         |
         +---- Failed/Timeout -> Scope Error
                                   +-- sanitized diagnostics
                                   +-- alert (best effort)
                                   +-- Response 503/500 per contract
```

### Why 202?

HTTP 202 **Accepted** signals the request was accepted for asynchronous processing, not completed in business terms. Therefore:

- Never return `paid=true` or `orderCompleted=true` right after Service Bus send.
- Provide a status endpoint/store or correlation ID for partners to track outcomes.
- Persist idempotency keys so caller retries never generate duplicate work.
- If the Send message action times out, the broker **may still have received the message**; never return an error assuming with certainty it was not enqueued.

### What if Response never runs?

Request/Response actions in Logic Apps have response timeout and runtime limits. If a workflow runs a long task or Response is skipped, callers time out or receive unexpected errors. Always **respond immediately after fast, durable intake**, pushing long work onto queues/backends.

## 29. Portal walkthrough: creating a Consumption workflow

High-level steps for a Consumption workflow in an approved lab subscription:

1. Open the [Azure Portal](https://portal.azure.com/) and verify tenant/subscription.
2. Create a **Logic App (Consumption)** in your lab resource group and region.
3. Open **Logic App Designer** and select **When an HTTP request is received**.
4. Provide a sample JSON payload or enter the request JSON schema manually.
5. Add **Parse JSON** if explicit dynamic content and validation are needed.
6. Add a **Condition** checking `amount > 0`; on False, return HTTP 400.
7. On True, use **Compose** to build the command payload with `correlationId`/`requestId`.
8. Add a **Service Bus Send message** action. Pick the queue and create/select an API connection with minimal Sender permissions.
9. After Send Succeeded, add a **Response** returning HTTP 202 and a non-sensitive body.
10. Add an error branch after Send using **Configure run after** for `Failed`/`TimedOut`.
11. Save the workflow and retrieve the callback URL securely; never commit signed URLs to repos.
12. Send a simulated request using an authorized test client.
13. Inspect **Runs history**, verifying trigger/action statuses and sanitized outputs.
14. Cross-check Service Bus queue/broker metrics or a test receiver to confirm message arrival.
15. Enable monitoring/alerts; disable/clean up lab resources when finished.

**Note:** action names in Designer and managed identity support for Service Bus vary by connector, region, and SKU. If your desired auth mode is unavailable, check the exact connector's documentation rather than pasting connection strings into workflow code.

### Testing schema validation failure

Send:

```json
{
  "requestId": "partner-x-2026-1043",
  "orderId": "",
  "amount": -1,
  "currency": "VND"
}
```

Expect the workflow **not to enqueue** this payload and to return a client error response instead of silently passing bad messages to workers.

### Testing enqueue failure

Using a **lab queue** and an approved controlled change, simulate Service Bus unavailability or missing permissions. Verify the error branch executes and never returns `202` without confirmed send success.

## 30. Standard workflows: organizing multiple workflows in one app

One Logic App Standard resource can host multiple workflows, for example:

```text
Logic App Standard: la-integration-platform
  |
  +-- Workflow: ReceiveOrder     (stateful)
  |     Request → Validate → Service Bus
  |
  +-- Workflow: DailyReconcile   (stateful)
  |     Recurrence → SQL → Blob
  |
  +-- Workflow: QuickLookup      (stateless, where appropriate)
        Request → HTTP → Response
```

In Standard, project configuration typically includes:

- `workflow.json` defining each workflow.
- `connections.json` holding connection references/configs per connector type.
- App settings and supported runtime config files.
- Deployment pipelines/IaC for Logic App Standard hosting and connected resources.

### Choosing stateful vs. stateless

| Criterion | Stateful | Stateless |
|---|---|---|
| Long-term step tracking needed | Usually better suited. | Different limits; inspect observability. |
| Fast workflows with minimal waits | Usable, with state-persistence overhead. | Good fit if runtime limits match. |
| Long-running orchestration | Supported and appropriate. | Generally unsuitable for long runs. |
| Replay and debugging | Richer built-in history/diagnostics. | Requires different logging/monitoring design. |
| Cost/performance | Driven by hosting/operations. | Driven by hosting/operations; not automatically free. |

In Standard, **managed connectors and built-in service-provider connectors reference connections differently**. Never hand-edit `connections.json` in Production without knowing the exact schema and secret handling; prefer Designer or tested CI pipelines.

## 31. Azure CLI: inspecting Logic App resources (read-only)

For Logic Apps Consumption, Azure CLI supports managing workflow resources. The commands below are primarily **read-only**:

```bash
az account show \
  --query "{Name:name,Subscription:id,Tenant:tenantId}" \
  --output table

az logic workflow list \
  --resource-group "<RESOURCE_GROUP>" \
  --output table

az logic workflow show \
  --resource-group "<RESOURCE_GROUP>" \
  --name "<CONSUMPTION_LOGIC_APP_NAME>" \
  --query "{Name:name,State:state,Location:location}" \
  --output json
```

Verify your Azure CLI/extension version and ARM permissions. Output fields vary by API version. **Never print full workflow definitions/parameters to logged terminals** if they contain credentials or signed URLs.

### Logic Apps Standard

Standard Logic Apps are hosted on an App Service/Functions-style workflow app resource. Do not expect Consumption's `az logic workflow show` command to list individual Standard workflows.

Query the ARM resource at the hosting app level:

```bash
az resource show \
  --resource-group "<RESOURCE_GROUP>" \
  --resource-type "Microsoft.Web/sites" \
  --name "<STANDARD_LOGIC_APP_NAME>" \
  --query "{Name:name,Kind:kind,Location:location}" \
  --output json
```

This checks the **host resource**; it does not prove individual Standard workflows are running cleanly or API connections are healthy. To inspect workflow runtime health, use the Portal, Standard tooling, and diagnostic logs.

## 32. Run history, trigger history, and action details

When a workflow misbehaves, look deeper than the final status badge.

### Trigger history

- Did the trigger run/poll?
- Did it detect an event/request?
- Did trigger conditions or filters drop the payload?
- Did polling return 0 items or an auth error?
- Was there concurrency capping, rate limiting, or connector throttling?
- Was the callback endpoint blocked by networking, or did the caller never send?

### Run history

- When did the run start, and with which correlation ID?
- Which action Failed/TimedOut first?
- Which actions were Skipped due to `runAfter`?
- Are inputs/outputs masked with Secure Inputs/Outputs?
- Did retries or earlier actions already cause side effects before failing?
- Did parallel branches complete?
- Did one step take abnormally long (e.g. a slow API connector)?

### Limits to know

- When a workflow is disabled or a trigger never received requests, there may be **zero runs** to inspect.
- Stateful and stateless workflows store and surface history differently.
- Run history/diagnostic retention is bounded by SKU and configuration.
- Run details can expose sensitive payloads if unprotected.
- Resubmitting a run can **re-execute previously succeeded actions**, causing duplicate business side effects without idempotency.

**Resubmit is a risky operational action**, not a harmless “retry fix” button for any failed run.

## 33. Azure Monitor, Log Analytics, and Application Insights

Logic Apps integrates with Azure Monitor metrics, diagnostic settings, Log Analytics, and Application Insights depending on hosting model and configuration.

| Source | Used for |
|---|---|
| Portal trigger/run history | Investigating a single trigger evaluation or run. |
| Azure Monitor metrics | Run counts, trigger successes/failures, durations, or similar SKU-dependent signals. |
| Diagnostic settings → Log Analytics | Storing and querying workflow runtime/resource logs within retention. |
| Application Insights | Traces, exceptions, dependencies, and correlation where Standard/integration supports it. |
| Azure Activity Log | Tracking control-plane resource changes (editing workflows, policies, role assignments). |
| Connector/target API logs | Confirming target APIs received requests/messages for reconciliation. |

**Do not assume Azure Activity Log contains full payloads or per-action executions.** Configure runtime diagnostics and logging sources explicitly.

### Starter KQL

In a workspace receiving Logic Apps diagnostic logs, a reference query:

```kusto
AzureDiagnostics
| where TimeGenerated > ago(2h)
| where ResourceProvider =~ "MICROSOFT.LOGIC"
| project TimeGenerated, Resource, Category, OperationName
| order by TimeGenerated desc
```

Table and column names vary with **resource-specific tables**, Logic Apps Standard hosting, and diagnostic versions. If a query returns empty results, check **destination, table schema, ingestion latency, and retention** before concluding no runs occurred.

### Designing correlation

Attach `requestId`/`correlationId` to clean payloads:

```text
Partner requestId = partner-x-2026-1042
        |
Logic App run ID + correlationId
        |
Service Bus message ID = partner-x-2026-1042
        |
Worker log + DB orderId = ORD-1042
```

Never generate a fresh `guid()` at every action, which breaks tracking across steps of the **same** request. Assign a correlation ID early and propagate it consistently per contract.

## 34. Alerts and SLOs for integration workflows

A workflow can report **`Succeeded`** even while business outcomes fail—such as dropping a mapped field or sending to the wrong queue. Alerts must cover both technical and business signals.

| Signal | Goal | Action |
|---|---|---|
| Trigger did not fire in expected window | Detect broken webhooks, polling, or connections. | Inspect trigger history, upstream source, and auth. |
| Rising run failure rate | Detect workflow/connector errors. | Inspect the first Failed/TimedOut action. |
| Run duration exceeds threshold | Detect latency or dependency bottlenecks. | Profile HTTP/DB/queue actions and retries. |
| HTTP 429 from connector/API | Spot throttling early. | Lower concurrency, back off, adjust capacity. |
| Response timeout | Caller did not receive timely reply. | Offload long work onto queues. |
| Service Bus enqueue succeeds, consumer backlog grows | Downstream falling behind. | Inspect queue metrics/workers rather than blaming Logic Apps. |
| Rising payload validation errors | Partner changed schema or sent bad data. | Run contract tests; alert per client. |
| Managed connection unauthenticated | OAuth/managed identity/secret failure. | Check connection health, roles, and consent. |
| Unusual action cost surge | Polling/loops/retries or traffic spike. | Audit execution counts, trigger frequency, diagnostics. |

### Example SLOs

- 99.9% of valid requests are **durably accepted** within the agreed latency window.
- 99.9% of commands are processed by workers before their async deadline.
- Invalid payloads receive clear 4xx responses with trace records intact.
- When Service Bus is unavailable, the workflow never falsely reports `accepted`.
- All critical incidents carry correlation IDs for reconciliation.

The first two SLOs are **distinct**: one governs Logic App intake, and the other governs asynchronous backend processing.

## 35. Costs: action executions, connectors, and hosting

Total Logic Apps cost can include:

- Logic App hosting/execution model.
- Trigger/action executions, including polling, loop iterations, and retries per applicable billing policy.
- Managed connector calls, if used.
- Standard hosting plan/capacity/runtime.
- Azure Service Bus, SQL, Storage, Functions, and target systems.
- API Management, VNet/private endpoints, NAT/firewalls.
- Azure Monitor Log Analytics / Application Insights ingestion and retention.
- Test/staging resources and operational overhead.

### Activity estimation example

Suppose 10,000 valid requests arrive daily:

- Each run uses 1 Request trigger.
- 1 Parse JSON action.
- 1 Condition.
- 1 Compose.
- 1 Service Bus Send action.
- 1 Response.
- 5% of requests retry one action once.

Total billed executions **for capacity/cost modeling** will differ from `10,000 × 5` due to conditional branches, loops, retries, and billing meter classifications. Never convert theoretical execution counts into dollar estimates without checking the exact **pricing meters for your SKU and connectors**.

### Evidence-based optimization

1. Filter events at the source before triggering workflow runs.
2. Batch large datasets where connectors support it.
3. Avoid per-item `For each` HTTP calls when a bulk API exists.
4. Bound retries, timeouts, and concurrency.
5. Remove verbose debug logging of huge payloads.
6. Compare built-in vs. managed connectors on performance, security, and actual fees.
7. Pick Consumption vs. Standard based on frequency, runtime duration, networking, isolation, and host utilization.
8. Monitor costs with tags, budgets, and cost attribution.
9. Load-test realistically before scaling up.
10. Never sacrifice business correctness merely to shave action counts.

## 36. Troubleshooting: triggers, actions, and connectors not running

| Symptom | Possible cause | First check |
|---|---|---|
| Zero runs | Trigger never fired, workflow disabled, trigger conditions unmatched. | Workflow state, trigger history, callback/polling config. |
| Polling trigger finds no records | Interval, watermark, filter, pagination, or source API returned nothing. | Trigger configuration and source data. |
| Webhook never arrives | Expired subscription/callback, signature/auth, networking. | Source event logs, registration, endpoint reachability. |
| Request returns 401/403 | Unauthorized caller or invalid callback URL/signature. | Auth policy, APIM/Entra/SAS, permissions. |
| Parse JSON Failed | Schema mismatch, missing fields, type mismatch, malformed payload. | Sanitized input and JSON schema. |
| Action Skipped | `runAfter` mismatch or other Condition branch taken. | Prior action status and `runAfter`. |
| Service Bus Send 403 | Connection principal lacks Data Sender or wrong scope. | Identity, role, namespace/queue. |
| Service Bus Send timeout | Network, broker, connector throttling, or outage. | DNS/routes, Azure Monitor, SDK/connector errors. |
| Invalid OAuth connection | Expired/revoked token, missing consent, tenant mismatch. | API connection health, owner, and consent. |
| Loop processes only some items | Pagination, filters, branches, timeouts, iteration caps. | Input counts, connector paging, loop status. |
| Run Succeeded yet data missing downstream | Wrong target environment, async queue pending, bad mapping. | Target IDs, correlation, backend logs. |
| Returns HTTP 202 even when Send fails | Response wired to wrong `runAfter`/error branch. | Run graph, action statuses, response path. |
| Duplicate orders after resubmit | Retries/non-idempotent API, multiple replays. | `RequestId`, outbox/inbox, DB constraints. |
| Standard workflow lacks expected history | Stateless vs. stateful differences or diagnostics disabled. | Workflow type and monitoring settings. |
| Slow execution or high cost | Excess retries, polling, loops, or high concurrency. | Billing, metrics, run durations, logs. |

### Decision tree

```text
Missing downstream data?
        |
        +-- Trigger history present?
        |      |
        |      +-- No → check trigger config / source events / polling
        |      |
        |      +-- Yes
        |          |
        |          +-- Workflow run created?
        |          |      |
        |          |      +-- No → trigger conditions, schedule, throttling
        |          |      |
        |          |      +-- Yes
        |          |          |
        |          |          +-- Validate/Parse failed → schema/contract
        |          |          |
        |          |          +-- Connector failed → auth/network/quota
        |          |          |
        |          |          +-- Send succeeded → inspect queue/worker
        |          |
        |          +-- Source callback never arrived?
        |
        +-- Duplicate data?
               |
               +-- Retries/resubmits/parallel runs
               +-- Missing idempotency/deduplication
```

Never change three things at once (schema, connection, retries) before isolating the fault; making one targeted change guided by run history isolates root causes cleanly.

## 37. Scenario A: HTTP trigger runs, but queue has no message

**Symptom:** partner POSTs an order, Logic App records a run, HTTP returns 202, yet workers see no message.

**Investigation:**

1. Capture `requestId` and timestamp from the client.
2. Open run history and locate the Service Bus Send action.
3. Check whether it `Succeeded`, `Failed`, or was `Skipped`.
4. If `Succeeded`, verify the **exact namespace/queue** and Service Bus metrics; a worker may already have received and completed it quickly.
5. If `Failed` with 403, check Data Sender role and connection identity.
6. If `TimedOut`, recognize the broker might still have accepted it, and reconcile by `requestId` before retrying.
7. If `Skipped`, inspect Condition/`runAfter`.
8. If the queue holds messages that workers aren't processing, shift investigation downstream.

**Common root cause:** Response was wired after Validate instead of **after Send Succeeded**, causing the Logic App to report `accepted` prematurely.

**Fix:** move Response onto the exact `Send Succeeded` branch, add failure responses/alerts, and enforce idempotency. Test both successful sends and simulated failures.

## 38. Scenario B: Polling duplicates or misses records

**Symptom:** a Recurrence workflow every 10 minutes reads an `Orders` table and sends emails. After a timeout, one order triggers two emails, while several other orders never appear in output.

**Investigation:**

1. Check whether workflow runs overlapped.
2. Inspect time filters and time zones; did it use `updatedAt > lastRunTime` without a durable watermark?
3. Check connector pagination / Top counts.
4. Did the email action succeed before the workflow retried or was resubmitted?
5. Is there an idempotency key combining `orderId` + notification type?
6. Compare source records against outputs to identify exactly which rows were missed.

**Fix:** use durable watermarks, ordered queries with safe overlap windows, proper pagination, deduplication keys, and safe concurrency policies. Never drive email notifications off an in-memory `lastRunTime` variable alone.

## 39. Scenario C: Expired OAuth connection

**Symptom:** after staff turnover, a workflow sending emails via a managed connector starts failing continuously with unauthorized errors.

**Investigation:**

1. Inspect the API connection reference and authentication type.
2. Determine whether the connection depended on OAuth consent/tokens from a former employee's account.
3. Check tenant, policies, licensing, and service mailbox permissions.
4. Correlate the error start time with user/credential/policy changes.
5. Never paste access tokens or refresh tokens into support tickets.

**Fix:** re-create/re-authorize the connection under organizationally governed ownership; use managed identity/service-owned integrations where supported; monitor credential expiry/revocation and re-test the workflow.

**Lesson:** “creating the connection” is not the end of the job. Connections have lifecycles, owners, and human-dependency risks.

## 40. Hands-on lab: deploying an order-intake Logic App

**Lab context:** a simulated partner submits order requests; the Logic App must validate and forward them to a Service Bus queue. Never connect to Production systems or send real emails.

| Component | Illustrative value |
|---|---|
| Resource group | `rg-integration-lab` |
| Logic App | `la-orders-intake-lab` |
| Workflow | `ReceiveOrder` |
| Trigger | `When an HTTP request is received` |
| Queue | `order-intake` |
| Namespace | `sb-orders-lab-unique` |
| Connection | Service Bus connection with minimal Sender role |
| Payload | `requestId`, `orderId`, `amount`, `currency` |
| Success response | HTTP 202 with correlation ID |
| Invalid response | HTTP 400 |
| Enqueue failure | Error HTTP status per API contract + alert |
| Observability | Runs history, sanitized logs, queue metrics |

### Tasks

1. Diagram trigger → Parse JSON → Condition → Compose → Send message → Response.
2. Explain the difference between a connector and a connection.
3. Choose Consumption or Standard for the lab and justify your choice.
4. Provision resources in an approved lab environment.
5. Declare a Request JSON schema with required fields.
6. Use expressions to extract `orderId`/`requestId`.
7. Use a Condition to reject `amount <= 0`.
8. Create the Service Bus connection with managed identity if supported by connector/hosting; otherwise document an approved secure auth alternative.
9. Wire Response 202 **only after Send Succeeded**.
10. Add an error branch with Configure run after `Failed`/`TimedOut`.
11. Enable Secure Inputs/Outputs if sensitive fields exist.
12. Send a valid lab request and verify the queued message.
13. Send a schema-invalid request and prove **nothing is enqueued**.
14. Simulate Service Bus unavailability and verify error response/alerts.
15. Replay the same `requestId` and explain how duplicate side effects are prevented.
16. Inspect run history/diagnostic logs and viewer permissions.
17. Estimate impact if volume grows from 100 to 10,000 requests/day.
18. Clean up the lab per procedure without deleting shared queues/connections.

### Test payloads

**Valid request:**

```json
{
  "requestId": "partner-x-lab-1042",
  "orderId": "ORD-LAB-1042",
  "amount": 250000,
  "currency": "VND"
}
```

**Invalid request:**

```json
{
  "requestId": "partner-x-lab-1043",
  "orderId": "",
  "amount": -100,
  "currency": "VND"
}
```

### Guided solution

- **Trigger:** HTTP Request.
- **Connector:** Service Bus to dispatch commands; authentication connection separated.
- **Action mapping:** Parse JSON + Condition enforce schema/amount; Compose normalizes event ID.
- **Success path:** Send Succeeded → Response 202. HTTP response never claims “paid.”
- **Failure path:** Invalid → 400; Send Failed/TimedOut → error response per API contract, sanitized alert, and reconciliation.
- **Idempotency:** persist `requestId`/business operation keys durably—never rely solely on an in-run variable.
- **Monitoring:** trace `requestId` across Logic App → Service Bus → worker.
- **Security:** never store callback URL signatures or connection strings in Git/logs.
- **Validation:** every test documents expected outcome, run history, and queue evidence.

**Acceptance criteria:** the workflow rejects invalid payloads, never reports accepted prior to confirmed enqueue, prevents log viewers from extracting secrets, handles retry/resubmit deduplication safely, and correlates across both systems.

## 41. Self-check questions

**Question 1.** How does a Logic Apps connector differ from a connection?

**Answer:** A connector provides trigger/action capabilities for a service; a connection specifies how to connect and authenticate to a specific target resource.

**Question 2.** How does a trigger differ from an action?

**Answer:** A trigger initiates a workflow run when matching conditions/events occur; an action is a step executed after the trigger or preceding steps.

**Question 3.** Do polling triggers and webhook triggers receive events the same way?

**Answer:** No. Polling checks the source periodically; webhook/push triggers receive callbacks from the source when events occur per connector mechanics.

**Question 4.** If an HTTP Request trigger has a valid JSON schema, does that authorize callers?

**Answer:** No. Schema validates payload structure, whereas authorization requires dedicated controls such as Entra/APIM/callback signatures where supported.

**Question 5.** Can Logic Apps Standard host multiple workflows inside one resource?

**Answer:** Yes. Standard supports multiple workflows and stateful/stateless modes per runtime capabilities; Consumption typically pairs one workflow per Logic App resource.

**Question 6.** Do managed connectors and built-in service-provider connectors always share the same connection format?

**Answer:** No. Their runtime, connection config, limits, and pricing can differ, especially in Standard.

**Question 7.** What is `Compose` typically used for?

**Answer:** Constructing or transforming a value or payload from trigger/action outputs for downstream steps.

**Question 8.** Why can Parse JSON fail even when the HTTP body is valid JSON?

**Answer:** The payload may violate the JSON schema, omit required fields, have wrong data types, or violate contract constraints.

**Question 9.** How does `triggerBody()?['orderId']` differ from `triggerBody()['orderId']`?

**Answer:** The null-safe `?` operator handles missing/null properties gracefully per runtime rules; strict validation is still needed for required fields.

**Question 10.** Why might the next action become Skipped after the previous action Failed?

**Answer:** Default `runAfter` runs only after `Succeeded`; actions handling failures must configure `runAfter` for those failure statuses explicitly.

**Question 11.** If you need to alert when an action **Fails or TimesOut**, should you select only `Failed` in Configure run after?

**Answer:** No. Select both `Failed` and `TimedOut` whenever logic must cover both failure outcomes.

**Question 12.** How should HTTP 429 be handled?

**Answer:** Bounded retry/backoff honoring rate limits/`Retry-After` if supported, reducing concurrency, or adjusting capacity—never spamming infinite retries.

**Question 13.** Why does retrying a timed-out HTTP POST risk creating duplicate orders?

**Answer:** The server may have committed before the client timed out; retrying repeats the side effect unless the API is idempotent.

**Question 14.** Can an in-run Logic App variable stop two identical concurrent requests from running together?

**Answer:** No. Separate runs have isolated state; you need idempotency keys and durable/atomic shared state.

**Question 15.** Does a Service Bus Send message `Succeeded` status prove the worker processed the order?

**Answer:** No. It proves only that the broker accepted the send per connector semantics; downstream processing must be tracked separately.

**Question 16.** Where should Response 202 sit in an order-intake flow?

**Answer:** Immediately after the durable intake step (e.g. Service Bus Send) succeeds, returning a correlation ID and a clear accepted status contract.

**Question 17.** Does enabling managed identity on a Logic App automatically let it read SQL/Service Bus/Blob?

**Answer:** No. The identity must receive data-plane roles, the connector must support that auth mode, and networking must allow access.

**Question 18.** Does enabling Secure Inputs/Outputs on one action guarantee downstream actions won't leak secrets?

**Answer:** No. Subsequent actions, diagnostics, tracked properties, and run history permissions must all be protected.

**Question 19.** Why shouldn't `For each` concurrency be raised without limits?

**Answer:** It invites race conditions, API throttling, retry storms, out-of-order effects, and higher costs.

**Question 20.** If a Logic App run Failed, is clicking Resubmit safe for every workflow?

**Answer:** No. Earlier actions may already have produced side effects before the failure; resubmitting risks duplicate writes/sends without idempotency.

**Question 21.** Does Azure Activity Log replace workflow run history?

**Answer:** No. Activity Log captures control-plane resource changes; run history and runtime diagnostics are needed for triggers/actions.

**Question 22.** Why might a workflow show `Succeeded` in run history while business results are still wrong?

**Answer:** Actions may succeed technically while mapping wrong fields, targeting the wrong queue, only enqueuing without tracking outcomes, or misfiltering payloads.

**Question 23.** Is a Stateless Standard workflow suitable for multi-week approval processes?

**Answer:** Usually not; evaluate duration limits, state persistence needs, and choose stateful instead.

**Question 24.** Why must a “no runs” issue check trigger history and the source before inspecting run details?

**Answer:** When a trigger never fires or creates a run, no action history exists to inspect; the fault lies at the trigger layer.

**Question 25.** When should you use an Azure Function instead of stuffing dozens of expressions into a workflow?

**Answer:** When logic requires complex algorithms/libraries, predictable performance, and thorough unit tests; Logic Apps can orchestrate the Function via a clean contract.

**Summary:** In Azure Logic Apps, **triggers** decide *when a workflow starts*, **connectors** determine *which services it talks to and how*, and **actions** define *what each step does and how outcomes are handled*. A reliable Production workflow needs **least-privilege connections/identities, validation, `runAfter`, bounded retries, idempotency, end-to-end observability, sensitive-data protection, and cost control**. Never stop at asking “did the workflow run succeed?”; ask **“did the data reach the right system, did the business outcome complete, and can we recover safely when something fails?”**.
