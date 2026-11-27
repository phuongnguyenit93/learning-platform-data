# Choosing API Management, Logic Apps, and Functions by Scenario

An integration architecture on Microsoft Azure typically has to answer three distinct questions: **who is allowed to call the API**, **which steps the business process goes through**, and **what application code performs the specific processing**. Using the same service to answer all three questions can create a system that is hard to maintain, expensive, or insecure.

Three services are very easy to confuse:

- **Azure API Management (APIM):** creates an **API gateway and API governance** layer in front of backends, helping with routing, authentication/authorization at the gateway, policy enforcement, traffic limiting, observability, and publishing API products.
- **Azure Logic Apps:** builds **integration workflows and orchestration** based on triggers, actions, connectors, conditions, loops, and execution state; well suited for connecting SaaS systems, data, and multi-step processes.
- **Azure Functions:** runs **event-driven or HTTP processing code** under a serverless model; well suited for custom logic, computation, data transformation, webhook handlers, and triggered tasks.

This lesson belongs to the **API and Workflow Integration** chapter of the **CLOUD_PROVIDERS_AZURE** module, in the learning path exploring subscriptions, resource groups, Microsoft Entra ID, virtual networks, compute, storage, and data. The goal is to know how to **choose the right service or combine them**, and then design deployment, monitoring, security, and cost control for an application architecture on Azure.

> **Quick rule of thumb:** **APIM governs the front door**, **Logic Apps orchestrates the steps**, **Functions executes code**. This is a role-based comparison, not a rigid boundary: each service has additional capabilities, but you should not turn one service into an uncontrolled replacement for the other two.

## 1. Learning Objectives

Upon completing this lesson, you will be able to:

1. Explain the components of APIM: gateway, API, operation, backend, product, subscription, policy, and developer experience aspects.
2. Distinguish between Logic Apps **Consumption** and **Standard**, triggers, connectors, actions, stateful/stateless workflows, and retry options.
3. Understand Azure Functions triggers/bindings, hosting plans, timeouts, concurrency, cold start, and when **Durable Functions** is needed.
4. Evaluate scenarios by API traffic, latency, level of SaaS integration, logic complexity, long-lived state, security, operations, and cost.
5. Choose APIM, Logic Apps, Functions, a combination of two or three services, or alternative services such as App Service, Azure Container Apps, and Service Bus.
6. Design synchronous APIs versus asynchronous jobs returning HTTP **202 Accepted**, with tracking IDs and idempotency.
7. Build a sample Java HTTP Azure Function, an illustrative Logic Apps workflow, and an APIM policy for JWT validation/rate limiting.
8. Diagram user authentication, managed identity between services, private connectivity, and telemetry flows.
9. Handle retries, timeouts, duplicate delivery, partial failures, and compensation without falsely promising exactly-once delivery.
10. Design CI/CD, versioning, monitoring, runbooks, and end-to-end total cost analysis.

## 2. The Big Picture: Three Layers of Responsibility

~~~mermaid
flowchart LR
    CLIENT["Mobile, website, B2B partners"] --> APIM["Azure API Management<br/>gateway + policy"]
    APIM --> API["Azure Functions / App Service<br/>Business API"]
    API --> MSG["Service Bus / Event Grid"]
    MSG --> FLOW["Logic Apps<br/>workflow + connectors"]
    FLOW --> CRM["CRM / ERP / Microsoft 365"]
    FLOW --> FUNC["Azure Functions<br/>custom transformation"]
    API --> DB["Azure SQL / Cosmos DB"]
    FLOW --> DB
    ID["Microsoft Entra ID"] -. "Identities, tokens" .-> APIM
    ID -. "Managed identity" .-> API
    ID -. "Connections" .-> FLOW
    OBS["Azure Monitor / App Insights"] -. "Logs, traces, metrics" .-> APIM
    OBS -. "Telemetry" .-> API
    OBS -. "Run history" .-> FLOW
~~~

This architecture does not require using all three products. If an application only needs to process a Blob file when uploaded, a **Function with a Blob/Event Grid trigger** may be enough. If there are multiple SaaS systems and long-running approval processes, **Logic Apps** can proactively orchestrate without needing APIM. If a Java backend already exists and only needs partner API governance, **APIM can sit in front of the existing backend**; there is no need to rewrite the API into Functions.

### 2.1. Distinguishing Gateway, Orchestration, and Compute Layers

| Aspect | API Management | Logic Apps | Azure Functions |
|---|---|---|---|
| Primary responsibility | API gateway and governance | Workflow/integration orchestration | Running custom code |
| Common trigger points | HTTP requests passing through the gateway | HTTP, recurrence, connector event, message | HTTP, timer, queue, Blob, Event Hubs, and supported triggers |
| Processing | Policies, routing, limited request/response transformation | Actions, conditions, loops, connectors | Code in C#, Java, JavaScript/TypeScript, Python, PowerShell... per runtime |
| Long-lived business state | Not the place to hold workflows | Stateful workflows fit well | Functions should usually be stateless; Durable Functions for stateful orchestration |
| SaaS integration | API proxy; not a workflow connector library | Major strength with managed/built-in connectors | Uses SDK/HTTP clients or supported bindings |
| External API governance | Primary strength | Has HTTP trigger but does not replace a full gateway | Has HTTP trigger but does not replace a full gateway |
| Complex business logic | Should not put everything into policies | Suitable for orchestration; custom compute should call code | Suitable for code logic and algorithms |
| Scale/cost unit | Gateway/tier/requests per model | Workflow hosting, triggers/actions/connectors per plan | Executions, compute/memory, instances per hosting plan |
| Example | JWT validation, quota, versioning | When an order is approved, update ERP, send notification | Parse JSON, calculate tax, generate PDF file |

**Note:** features, limits, private networking, availability, deployment slots, and pricing vary by **tier/plan/region**. The table above compares the nature of the services and does not guarantee that a specific feature exists in every SKU.

## 3. Start with Requirements, Not Product Names

Before choosing a service, answer the following:

1. **Who is calling?** Browser, mobile app, B2B partner, internal system, scheduler, or event broker?
2. **What communication pattern?** Synchronous HTTP, webhook, queue, event stream, file, FTP/SFTP, or SaaS connector?
3. **Does the result need to be immediate?** Within a few hundred milliseconds, a few seconds, or several hours?
4. **Are humans involved in the process?** Approvals, waiting for responses, or scheduled timers?
5. **How long and customized is the logic?** Mapping a few fields, or complex Java algorithms with many libraries?
6. **Are there many services to coordinate?** Microsoft 365, Dynamics 365, Salesforce, SAP, SQL, Service Bus?
7. **What are the API governance requirements?** OAuth/JWT, subscriptions, productization, quotas, versioning, developer portal?
8. **What happens if a step fails?** Retry, compensation, manual intervention, dead-letter?
9. **What are the network and data boundaries?** Private endpoint, VNet, region, sensitive data, compliance?
10. **What are the load and cost profiles?** Number of API calls, workflow actions, execution duration, concurrency, peak traffic, and log retention?

This approach prevents using **Logic Apps like a web server**, using **APIM policies like a business application**, or using a **Function like a workflow engine without a state store**.

## 4. Service Selection Decision Tree

~~~mermaid
flowchart TD
    A["New integration problem"] --> B{"Need a shared gateway<br/>for HTTP APIs?"}
    B -->|Yes| C["Add API Management"]
    B -->|No| D["APIM not strictly needed"]
    C --> E{"What is the main processing?"}
    D --> E
    E -->|"Multiple SaaS, orchestrate steps, wait/approval"| L["Logic Apps"]
    E -->|"Computation/custom code transformation, event handler"| F["Azure Functions"]
    E -->|"Long-lived API with many connections, large app scale"| APP["Evaluate App Service / Container Apps / AKS"]
    L --> G{"Complex code algorithm segment?"}
    G -->|Yes| LF["Logic Apps calls Functions"]
    G -->|No| LONLY["Logic Apps may be sufficient"]
    F --> H{"Stateful, long-running, fan-out workflow?"}
    H -->|Yes| DF["Evaluate Durable Functions / Logic Apps"]
    H -->|No| FONLY["Function may be sufficient"]
~~~

The decision tree is a **heuristic**, not a feature rule. For example, a simple API may still need APIM if it must be published to multiple partners. A Function can run periodically in the background, but when a workflow includes hundreds of connector actions and human approvals, Logic Apps generally makes observing the process more convenient.

### 4.1. Five Quick Decision Questions

| If you are asking... | Prioritize considering |
|---|---|
| “How do I authenticate/rate-limit/version multiple backend APIs under a single gateway?” | **API Management** |
| “How do I run 8 steps and an approval when an email/file/CRM event arrives?” | **Logic Apps** |
| “How do I run Java code to transform JSON, sign a hash, or compute business rules?” | **Azure Functions** |
| “How do I run a multi-day orchestration with fan-out/fan-in and waiting for external signals?” | **Logic Apps stateful** or **Durable Functions** |
| “How do I manage a public API while also calling SaaS and running Java processing?” | **APIM + Logic Apps + Functions**, if each layer adds real value |

## 5. API Management: Governing APIs, Not Running Backends by Default

**Azure API Management** places a gateway layer between API callers and backend services. The gateway receives requests, evaluates policies, and forwards them; it can transform responses and emit telemetry.

### 5.1. Components to Distinguish

| Component | Role |
|---|---|
| **API** | The managed API surface, with a base path and operations |
| **Operation** | A route + HTTP method and contract |
| **Backend** | The address/definition of the backend service called by the gateway |
| **Product** | A bundle grouping APIs for consumers via a subscription/publishing mechanism |
| **Subscription** | An access mechanism for an API product/API via keys when enabled |
| **Policy** | Inbound/backend/outbound/on-error rules |
| **Gateway** | Executes policies and forwards traffic |
| **Developer portal** | Discovery, documentation, and onboarding experience per tier/features |
| **Named value** | Shared configuration for policies, which can reference secrets where supported |
| **Version/revision** | Manages contract versions and API edits |

### 5.2. Policy Flow

~~~mermaid
flowchart LR
    R["HTTP request"] --> I["Inbound<br/>validate token / rate limit"]
    I --> B["Backend<br/>forward-request"]
    B --> A["Functions / App Service"]
    A --> O["Outbound<br/>header/response policy"]
    O --> C["Client response"]
    I -. "Policy error" .-> ERR["on-error"]
    B -. "Backend error" .-> ERR
~~~

An APIM policy is organized into **inbound**, **backend**, **outbound**, and **on-error** sections. Policies can be applied at different scopes such as global, product, API, or operation, following inheritance rules and processing order.

**Do not put entire business logic** such as complex tax calculation, multi-step data queries, or orchestration with human approval into expressions/policies. Policies work best as a communication governance layer and for clear, testable transformations.

### 5.3. Suitable Use Cases

- A company has 15 backend APIs and wants to publish them under **api.company.example**.
- A B2B partner needs **OAuth2/JWT, quotas, rate limits, IP restrictions**.
- You want unified **OpenAPI documentation**, onboarding, and versioning.
- You want to hide backend addresses, enforce headers, or route to different backends.
- You want to observe latency at the gateway and separate backend/gateway errors.
- You already have a Java backend on AKS/App Service but lack a standardized governance gateway.

### 5.4. Common Misconceptions

- **APIM does not replace backend computation.** The gateway forwards requests to a backend or uses policies to return responses in certain scenarios; it is not a general-purpose environment for running Java services.
- **A subscription key is not user authentication.** It is an API subscription access credential; OAuth/JWT/mTLS and business authorization must be designed separately.
- **Rate-limit does not guarantee an absolute global quota across all gateway topologies.** Some rate-limiting policies are approximate/distributed, so you need to understand scope and behavior when scaling.
- **Gateway caching is not a database.** You must evaluate invalidation, sensitive data, and consistency.
- **Enabling a public gateway does not automatically secure the backend.** If the backend remains directly accessible, callers can bypass APIM policies.

## 6. Illustrative APIM Policy: JWT Validation and Rate Limiting

Suppose a partner sends an OAuth 2.0 bearer access token issued by Microsoft Entra ID. An illustrative policy:

~~~xml
<policies>
  <inbound>
    <base />
    <validate-jwt
        header-name="Authorization"
        failed-validation-httpcode="401"
        failed-validation-error-message="Invalid access token"
        require-expiration-time="true"
        require-scheme="Bearer">
      <openid-config
          url="https://login.microsoftonline.com/TENANT_ID/v2.0/.well-known/openid-configuration" />
      <audiences>
        <audience>api://API_APP_ID</audience>
      </audiences>
    </validate-jwt>
    <rate-limit-by-key
        calls="60"
        renewal-period="60"
        counter-key="@(context.Request.IpAddress)" />
  </inbound>
  <backend>
    <base />
  </backend>
  <outbound>
    <base />
  </outbound>
  <on-error>
    <base />
  </on-error>
</policies>
~~~

This is a **sample for analysis**, not a policy to deploy as-is. You must replace **TENANT_ID**, **API_APP_ID**, select the right issuer/audience matching the application's access token, review required claims/scopes/roles, and verify what the APIM tier/policy version supports.

### 6.1. Why Does Policy Order Matter?

**validate-jwt** executes before **rate-limit-by-key** in this example. If the token is invalid, the request can be rejected before consuming quota as counted by the policy.

**rate-limit-by-key** uses IP in the demo. However, IP is not a user identity: many users may share a NAT IP, IPs can change, and proxies can affect the perceived value. In production, you should use a **trusted key from the client application, subscription, or verified claim**, depending on policy requirements and expression/APIM support.

### 6.2. JWT Validation Does Not Replace Business Authorization

The gateway can verify signature, expiry, issuer, and audience. However, the backend must still check:

- Is this user or client allowed to view **orderId=481**?
- Does the user have the required role/scope to update the order?
- Does the token's tenant ID match the data/tenant ownership?
- Is the resource currently in a state that allows modification?

**A valid JWT does not mean every operation is permitted**.

### 6.3. Protecting the Backend from Direct Access

If the Function backend has an independent public URL, an attacker can bypass APIM if they discover that URL. You need to design one or more protections based on hosting plan capabilities:

- Private Endpoint or network restrictions according to supported topology.
- Azure Functions authentication/authorization (Microsoft Entra) when appropriate.
- Function key managed by APIM as a secret/named value when appropriate; **a key does not replace OAuth**.
- mTLS or an appropriate service-to-service authentication mechanism.
- Azure Firewall, NSG/VNet, or other ingress policies per system design.

Do not rely on a backend URL being “hard to guess” as a security control.

## 7. Logic Apps: Workflow-First Integration

Azure Logic Apps lets you model flows consisting of **triggers**, **actions**, **conditions**, **loops**, **parallel branches**, **scopes**, and **connections**. Each run can be inspected via run history when supported by the environment/mode.

### 7.1. Workflow Example

~~~mermaid
flowchart TD
    E["Trigger: OrderApproved"] --> V["Validate payload"]
    V --> C["Create customer in CRM"]
    C --> F["Call Azure Function<br/>custom price mapping"]
    F --> ERP["Create sales order in ERP"]
    ERP --> N["Notify by email / Teams"]
    ERP -->|Failure| H["Compensation / alert / manual review"]
    N --> S["Record completion"]
~~~

Here, the strength of Logic Apps is **visualizing the sequence and state of steps**, using appropriate connectors, and handling integrations that already have built-in actions/triggers.

### 7.2. Key Components

| Component | Purpose | What to check |
|---|---|---|
| **Trigger** | Starts the workflow | Webhook, poll, recurrence, HTTP, Service Bus |
| **Action** | A processing/service call step | Output schema, timeout, retry |
| **Connector** | Integration mechanism with apps/services | Authentication, tier, throttling, region |
| **Condition/Switch** | Business branching | Handling unexpected values |
| **For each** | Processes a list | Concurrency/race conditions and ordering |
| **Scope** | Groups actions into a logical block | Succeeded/Failed/Skipped/TimedOut status |
| **runAfter** | Specifies under which status the next step runs | Error-handling and finally |
| **Stateful workflow** | Persists state/run history per supported model | Storage, privacy, retention, cost |
| **Stateless workflow** | Optimized for short processing with less persistence | Not suitable for long waits and detailed run history |
| **Managed identity** | Authenticates to Azure resources when supported by connector | Data-plane roles and connection config |

### 7.3. Logic Apps Consumption vs. Standard

| Criterion | Consumption | Standard |
|---|---|---|
| Resource model | Multitenant workflow model | Single-tenant hosting, workflow apps and corresponding hosting plan |
| Primary cost | Typically per trigger/action/connector executions | Hosting compute/storage plus applicable connector/operations charges |
| Workflows | Workflows managed under the Consumption model | Supports both stateful and stateless workflows in the appropriate environment |
| Connectors | Managed connectors per catalog | Built-in and managed connectors depending on type |
| Network/integration | Per Consumption/tier capabilities | Broader private hosting/network capabilities depending on plan |
| Local development | Per supported tools | Workflow project/VS Code per Standard experience |
| Best suited for | Event-driven/scheduled workflows not needing always-on custom hosting | Multiple workflows in one app, execution/latency/network requirements needing Standard |

**Do not assume Consumption is always cheaper or Standard is always faster.** Workloads with many actions, connectors, continuous execution, or private networking can reverse that conclusion; use the pricing calculator and benchmarks.

### 7.4. When Logic Apps Is a Strong Choice

- Integrating multiple **SaaS connectors** without wanting to build every API client yourself.
- Purchase/expense approval processes that involve **waiting for human approvers** and multiple branches.
- Moving data from FTP/SFTP/SharePoint/Office 365/Dynamics/SQL to other systems.
- Workflows requiring **run history**, tracing each action and failure condition.
- Orchestration combining synchronous and asynchronous steps, waiting for timers or webhook callbacks.
- Requirements where both business and operations teams need to read the flow structure.

### 7.5. Cases You Should Not Force into Logic Apps

- Long-running CPU-intensive calculations, or looping over millions of records in an unbounded For each.
- Complex Java business algorithms requiring extensive unit/integration tests and specialized libraries.
- High-throughput, low-latency APIs where each call only needs a short statement and workflow overhead is unwarranted.
- Storing long-lived business data in run history like a database.
- Unbounded loops, infinite retries, or relying on connectors without checking throttling.
- Expecting **exactly-once effects** when workflows have retries/resubmits; this must be solved with idempotency.

## 8. Logic Apps runAfter, Retry, and Compensation

### 8.1. Action-Level Retry

A connector action can automatically retry transient errors according to the connector/runtime retry policy. For example, if an HTTP call to an ERP returns HTTP 429, Logic Apps can retry according to configuration.

Risk: the ERP created the order, but the response timed out. If the workflow retries **POST /orders** without an idempotency key, it may create a duplicate order.

Solution:

- Pass a stable business key such as **externalOrderId**.
- Use idempotent/upsert APIs when supported by the partner.
- Check the outcome via GET/status before retrying when the outcome is uncertain.
- Set a retry cap, timeout, and alert after exhausting attempts.
- Do not store secrets/sensitive payloads in unprotected run history.

### 8.2. Try / Catch / Finally with Scopes

A common pattern:

~~~text
Scope Try
  - Validate
  - Call CRM
  - Call ERP
  - Write final state

Scope Catch
  runAfter Try: Failed, TimedOut
  - Capture error
  - Mark NEEDS_REVIEW
  - Notify operator
  - Compensate per business rules

Scope Finally
  runAfter Try/Catch on appropriate statuses
  - Emit correlation/metrics
~~~

**Compensation is not automatic database rollback**. If step 1 already created a CRM customer and step 2 failed to create the ERP order, “deleting the CRM customer” might be wrong if that customer is already referenced by another system. Compensation must be defined according to business rules, typically changing a status or issuing an offsetting transaction.

### 8.3. Resubmit Can Create New Side Effects

Run history aids investigation, and some models allow resubmitting a run. Resubmit **is not a transaction rewind**: steps that already called external APIs may have already committed. You must verify workflow state, idempotency, deduplication, and compensation before re-running.

### 8.4. Concurrency and Ordering

If **For each** runs in parallel, iterations can complete out of input order. High trigger concurrency can also cause race conditions when multiple workflows update the same record.

To process in order, you need to:

- Design partitioning/business keys or concurrency limits.
- Use database locking/optimistic concurrency.
- Separate order-sensitive operations from independent processing.
- Do not disable all concurrency over a random bug without analyzing throughput.

## 9. Illustrative Logic Apps Workflow JSON

An example workflow with an hourly **Recurrence** trigger calling an HTTP endpoint to check status. This is a structural learning sample and **will not run as-is** because the URL is a placeholder, authentication is omitted, and resource/connection configurations are not included.

~~~json
{
  "$schema": "https://schema.management.azure.com/providers/Microsoft.Logic/schemas/2016-06-01/workflowdefinition.json#",
  "contentVersion": "1.0.0.0",
  "parameters": {},
  "triggers": {
    "Every_Hour": {
      "type": "Recurrence",
      "recurrence": {
        "frequency": "Hour",
        "interval": 1
      }
    }
  },
  "actions": {
    "Check_Service": {
      "type": "Http",
      "inputs": {
        "method": "GET",
        "uri": "https://api.example.invalid/health"
      },
      "runAfter": {}
    },
    "Evaluate_Result": {
      "type": "If",
      "expression": {
        "equals": [
          "@outputs('Check_Service')?['statusCode']",
          200
        ]
      },
      "actions": {},
      "else": {
        "actions": {}
      },
      "runAfter": {
        "Check_Service": [
          "Succeeded"
        ]
      }
    }
  },
  "outputs": {}
}
~~~

In practice:

- Workflow definitions are typically packaged inside a Logic App resource and include **connections/authentication** when using connectors.
- **Recurrence** is a start schedule; it does not mean every run finishes before the next one begins.
- HTTP actions should configure timeout/retry policies and managed identity or appropriate authentication.
- Use **runAfter** to distinguish Succeeded/Failed/TimedOut/Skipped.
- **Evaluate_Result** only runs if the HTTP action succeeded per runAfter. To handle an HTTP 500 that may mark the action as Failed, you need an appropriate Catch/runAfter branch rather than relying on a 200 condition.
- The URL **example.invalid** is an unreachable placeholder and must never be put into production.
- This example only illustrates choosing Logic Apps for a workflow and does not replace validated ARM/Bicep deployments.

## 10. Azure Functions: Triggered Custom Code

**Azure Functions** executes application code when a trigger fires. Instead of provisioning virtual machines and a scheduler/container host yourself, the platform provides hosting and trigger plumbing according to the plan.

### 10.1. Common Triggers

| Trigger | Scenario |
|---|---|
| **HTTP trigger** | Receive webhooks or API requests |
| **Timer trigger** | Run scheduled jobs |
| **Service Bus trigger** | Receive from queues/subscriptions |
| **Event Hubs trigger** | Process event streams by partition/batch |
| **Event Grid trigger** | React to resource events, e.g., BlobCreated |
| **Blob trigger** | Process Blob changes per extension and supported model |
| **Queue Storage trigger** | Run background processing from Azure Storage Queue |

Triggers determine **when the Function is invoked**, not the entire business logic. Bindings help read/write certain services via extensions, while direct SDK usage remains appropriate when you need full control over transactions, connections, retries, or specific domain logic.

### 10.2. When Functions Fits Well

- Running a few dozen or a few thousand lines of Java/C# to process data.
- Parsing/validating/transforming JSON/XML, calculating taxes, converting file formats.
- Handling webhooks/callbacks requiring custom verification.
- Processing an Azure Service Bus message, Blob, or Event Grid event.
- A small API where you do not want to operate a continuous web server.
- A custom compute step inside a Logic Apps workflow.

### 10.3. When You Should Not Default to Functions

- A large web application needing to host a web framework/server with specialized startup and connections: evaluate **App Service, Container Apps, or AKS**.
- Continuous jobs running longer than plan/trigger limits without checkpoints: evaluate **Durable Functions**, Container Apps Jobs, Batch, or splitting the work.
- Wanting to keep business state in Function memory across executions: unsuitable.
- APIs requiring consistently ultra-low latency where the plan has cold starts or SLA mismatches: choose an appropriate plan/always-ready instances or different hosting.
- Workflows with hundreds of connector actions and human approvals: consider Logic Apps instead of coding every step yourself.

## 11. How Functions Hosting Plans Affect Architecture

Azure Functions offers hosting models such as **Flex Consumption**, **Premium**, **Dedicated/App Service plan**, and supported options/variants by OS/runtime/region. Each plan has different characteristics for cost, startup, scaling, timeout, networking, and capacity.

| Requirement | What to evaluate |
|---|---|
| Uneven traffic with long idle periods | Consumption-based plans per execution/compute can be efficient |
| Latency sensitive to cold starts | Pre-warmed/always-ready instances or an appropriate provisioned plan |
| VNet integration and private networking | Feature support of the specific hosting plan/region |
| Long-running execution | Max timeout, trigger semantics, memory, shutdown behavior |
| High-throughput event streams | Scaling constraints, batch/concurrency, and downstream capacity |
| Java apps with heavy JVM startup | Cold start, heap, memory quota, prewarming |
| Predictable cost under steady load | Compare Premium/Dedicated or other app hosting options |
| Compliance and network isolation | Feature availability, identity, and network policies |

**Do not assume a single fixed timeout table applies to all Functions plans**: limits can vary by runtime, trigger, HTTP connection timeout, and plan. A backend running for several minutes can still hit a gateway/client HTTP timeout before the Function completes.

## 12. Java Azure Function Example: Receiving and Validating Requests

This example illustrates an HTTP Function using annotations from the Azure Functions Java library. The Function only validates the payload and returns a response; it **does not persist orders**, enqueue messages, and must not be mistaken for a complete production application.

~~~java
package com.example;

import com.microsoft.azure.functions.ExecutionContext;
import com.microsoft.azure.functions.HttpMethod;
import com.microsoft.azure.functions.HttpRequestMessage;
import com.microsoft.azure.functions.HttpResponseMessage;
import com.microsoft.azure.functions.HttpStatus;
import com.microsoft.azure.functions.annotation.AuthorizationLevel;
import com.microsoft.azure.functions.annotation.FunctionName;
import com.microsoft.azure.functions.annotation.HttpTrigger;

import java.util.Optional;

public class ValidateOrderFunction {
    @FunctionName("ValidateOrder")
    public HttpResponseMessage run(
            @HttpTrigger(
                name = "request",
                methods = { HttpMethod.POST },
                authLevel = AuthorizationLevel.FUNCTION,
                route = "orders/validate"
            )
            HttpRequestMessage<Optional<String>> request,
            ExecutionContext context) {

        String body = request.getBody().orElse("");

        if (body.isBlank()) {
            return request
                .createResponseBuilder(HttpStatus.BAD_REQUEST)
                .header("Content-Type", "application/json")
                .body("{\"error\":\"body_required\"}")
                .build();
        }

        context.getLogger().info("Received order validation request");

        return request
            .createResponseBuilder(HttpStatus.OK)
            .header("Content-Type", "application/json")
            .body("{\"valid\":true,\"note\":\"demo-only\"}")
            .build();
    }
}
~~~

### 12.1. Meaning of HTTP authLevel FUNCTION

**AuthorizationLevel.FUNCTION** requires a Function key or equivalent runtime mechanism; it **does not verify user identity or permission to view orders**. To protect a production public API:

1. Authenticate callers with Microsoft Entra ID/OAuth/JWT at APIM or an appropriate identity layer.
2. The backend must enforce **business authorization**.
3. Restrict direct access paths to the Function.
4. Protect Function keys as secrets and rotate them on schedule.
5. Use TLS and telemetry to detect 401/403 errors.

If APIM calls the backend using a Function key, store the key via **named value/Key Vault integration** or an approved secret mechanism. Never place literal function keys inside policy XML or a Git repository.

### 12.2. Why Does the Demo Return HTTP 200 Instead of 202?

The Function above **does not persist work to a durable queue yet**; returning 202 Accepted could mislead the caller into believing the backend has accepted asynchronous processing. In a real API implementation, only return 202 after the request has been **durably written** to a queue/outbox/workflow store and a tracking ID is available for lookup.

### 12.3. A Java Function App Is Not a Traditional JVM Web Server

Java Functions have their own runtime/annotations, `host.json`, dependencies, Java version, and packaging/deployment model. You cannot rename a Spring Boot executable JAR and expect it to become an HTTP Function automatically. You need a Function project with a compatible Java worker/runtime, or choose App Service/Container Apps if you want to keep your web framework application intact.

## 13. Durable Functions: Stateful Code-First Workflows

**Durable Functions** adds a persistent orchestration model enabling fan-out/fan-in, timers, retries, and external events according to runtime-supported behavior.

~~~mermaid
flowchart TD
    T["HTTP start orchestration"] --> O["Durable orchestrator"]
    O --> A["Activity: validate order"]
    A --> B["Activity: reserve inventory"]
    B --> W["Wait for payment event or durable timer"]
    W --> C{"Paid?"}
    C -->|Yes| D["Activity: create shipment"]
    C -->|Timeout| E["Activity: compensate / release stock"]
    D --> F["Completed"]
    E --> F
~~~

### 13.1. How Does Durable Functions Differ from Logic Apps?

| Question | Durable Functions | Logic Apps |
|---|---|---|
| How flow is described | Code-first orchestrator and activities | Workflow definition/designer |
| Complex branching | Flexible in code, subject to framework constraints | Actions/conditions/scopes |
| Many SaaS connectors | Usually uses SDK/HTTP or bindings | Strong connector catalog |
| Human approval | Can wait for external events | Has built-in actions/connectors/workflow patterns |
| State/history | Durable orchestration state | Workflow run/state per plan |
| Code rules | Orchestrator must be deterministic per runtime model | Designer/workflow expression semantics |
| Observability | Orchestration status, function telemetry | Per-action run history |
| When suitable | Heavy code logic, fan-out/fan-in, backend workflows | SaaS integration and declarative orchestration |

### 13.2. Warning About Determinism

Orchestrator code in Durable Functions can be **replayed** to restore state; therefore, never make arbitrary I/O calls or read non-deterministic timestamps/random values directly inside the orchestrator. Place side effects inside **activity functions** and use durable timer/event APIs according to the runtime's guidelines.

Do not assume “Durable Functions guarantees exactly-once external API calls.” Activities can retry/re-run on system failures. Side effects such as transferring funds, creating invoices, or sending emails must be **idempotent**.

### 13.3. Choosing Logic Apps or Durable Functions for Long-Lived Workflows?

Choose **Logic Apps** when the biggest value lies in **connector integration, visual flow structure, and task coordination**.

Choose **Durable Functions** when the workflow requires **rich orchestration logic in code**, many compute activities, and the team wants standard code unit testing/versioning practices.

In some systems, Logic Apps calls Durable Functions or vice versa. However, combining them is only helpful when boundaries are clear, avoiding two orchestration engines managing the same business state.

## 14. Selection Matrix for Real-World Scenarios

| Scenario | Usually reasonable choice | Why | What to check |
|---|---|---|---|
| Publish 20 existing APIs to partners with JWT/rate limits | **APIM** in front of existing backend | Centralized governance | Backend does not bypass gateway |
| When an invoice is approved, write to Dynamics, SAP, send email, wait for approval | **Logic Apps** | Connectors and run history | Retry, human timeout, licensing |
| Convert newly uploaded Blob to PDF in Java | **Functions** or Container Apps Jobs if heavy | Event-driven custom compute | Timeout, memory, input size |
| API needing auth and Java pricing calculation | **APIM + Functions** | Gateway separated from business compute | Latency, direct backend exposure |
| Transform complex schema from Salesforce and write to ERP | **Logic Apps + Functions** | Connector orchestration + code transformation | Idempotency and correlation |
| Partner submits order, 5-minute processing, status lookup | **APIM + Function + Service Bus** | HTTP ingress + async handling | Durable enqueue, 202/status API |
| Wait for customer acceptance up to 3 days | **Logic Apps stateful** or **Durable Functions** | State and timers | Compensation, run retention |
| Java Spring Boot API already running on AKS | **APIM + AKS/App Service** | No need to rewrite backend | Ingress/network/observability |
| Nightly timer reading data and writing a simple report | **Function Timer** | Trigger + code | Idempotency, limits |
| Scheduler calling 10 SaaS APIs with existing connectors | **Logic Apps** | Low-code integration | Connector throttling and plan cost |
| High-volume telemetry stream of millions of events/hour | **Event Hubs + consumer/Stream Analytics** | Stream processing | APIM does not replace an event broker |
| Multi-hour GPU/CPU computation | **Container Apps Jobs/Batch/AKS** | More suitable compute model | Quota, scaling, orchestration |
| Very small internal API with no external consumers | Possibly **Functions directly** | No need for complex gateway | Evaluate actual policy needs |
| Enterprise needing API catalog, portal, versioning | **APIM** | API lifecycle management | Tier/support and operations |

This table is an **initial** decision guide. If there are unusual residency, private networking, compliance, or traffic requirements, the choice must be benchmarked and reviewed for the specific SKU.

## 15. Case Study A: B2B Orders API with Asynchronous Processing

A partner sends 300 requests/second at peak and needs fast HTTP responses. Checking inventory and creating a shipment can take up to 3 minutes.

### 15.1. Approach to Avoid

~~~text
Partner → APIM → Function HTTP → Call Inventory → Call ERP → Send email
                            └── Hold HTTP connection for 3 minutes
~~~

Problems:

- Timeouts at APIM/client/function hosting can occur before processing finishes.
- Retrying HTTP POST can create duplicate orders.
- Downstream errors exhaust connections and reduce availability.
- No reliable tracking status or business correlation.
- No durable store for accepted requests.

### 15.2. Queue-Based Approach

~~~mermaid
flowchart LR
    P["Partner B2B"] -->|"OAuth / HTTPS"| G["APIM"]
    G -->|"POST /orders"| F["HTTP Function<br/>validate + enqueue"]
    F --> Q["Service Bus orders-commands"]
    F -->|"202 + operationId"| G
    Q --> W["Worker Function / Logic Apps"]
    W --> DB["Orders DB"]
    W --> ERP["ERP / Inventory"]
    P -->|"GET /operations/{id}"| G
    G --> S["Status API"]
    S --> DB
~~~

Responsibility boundaries:

- **APIM:** token verification, quotas/rate limits, versioning, routing, tracing.
- **HTTP Function:** payload verification, issuing operationId/idempotency key, durably writing to queue/outbox.
- **Service Bus:** decouples HTTP traffic from long-running processing, supports retry/DLQ per configuration.
- **Worker Function or Logic Apps:** executes business steps.
- **Database:** stores PENDING/PROCESSING/SUCCEEDED/FAILED status and business outcome.

### 15.3. HTTP 202 Contract

Example response after a **successful durable enqueue**:

~~~http
HTTP/1.1 202 Accepted
Content-Type: application/json
Location: /operations/op-481

{
  "operationId": "op-481",
  "status": "PENDING",
  "statusUrl": "/operations/op-481"
}
~~~

This is an **example response**, not executed backend code. If enqueuing fails, do not return 202 and drop the request. Return an appropriate error or use the transactional outbox pattern if the API writes to a database at the same time.

### 15.4. Idempotency

Clients may retry due to a timeout immediately after enqueuing. If the second attempt generates a different operationId, two commands risk processing the same request.

Solution:

- Accept a client-provided **Idempotency-Key** or derive a stable business key.
- Enforce a unique constraint on **partnerId + idempotencyKey**.
- Return the same operationId when a duplicate request has identical content.
- Do not reuse one idempotency key for two different payloads; return a conflict/validation error.
- Make consumers idempotent using message/event IDs.
- If the broker send outcome is uncertain, use reconciliation/outbox instead of blind retries.

### 15.5. When Does Logic Apps Appear in This Case Study?

If after receiving the command you must:

1. Check ERP.
2. Send an approval request to a manager.
3. Wait up to 2 days.
4. Update Dynamics.
5. Send Teams/email notifications.
6. Compensate if any step fails.

That is a sign you need **workflow orchestration**, where stateful Logic Apps can be more advantageous than a long-running HTTP Function. If the computation logic is primarily Java, Logic Apps calls Functions for one or a few steps rather than rewriting code in expressions.

## 16. Case Study B: SaaS Integration and Approval Workflow

Scenario: invoice files arrive in SharePoint; they need to be verified, sent to ERP, routed for manager approval if the amount exceeds a threshold, and then trigger notifications.

### 16.1. Diagram

~~~mermaid
flowchart TD
    SP["SharePoint: New file"] --> LA["Logic Apps trigger"]
    LA --> META["Get metadata + file"]
    META --> FN["Function: verify invoice schema"]
    FN --> RULE{"Amount > threshold?"}
    RULE -->|Yes| APPROVAL["Approval / wait for decision"]
    RULE -->|No| ERP["Create invoice in ERP"]
    APPROVAL -->|Approved| ERP
    APPROVAL -->|Rejected/TimedOut| REVIEW["Mark rejected + notify"]
    ERP --> STATUS["Record external invoice id"]
    STATUS --> EMAIL["Notification"]
    ERP -->|Error| CATCH["Catch scope: retry/compensate/alert"]
~~~

### 16.2. Why Does Logic Apps Lead?

- SharePoint/ERP/Teams/email connectors are ready to use when catalog and permissions allow.
- The workflow has multiple branches, waits, and business approvals.
- Run history is useful when operators need to know **which step failed**.
- Functions handle only the code-heavy parts like XML/signature validation or logic difficult to express with workflow expressions.

### 16.3. Risks to Control

- Connectors signed in with a personal user account can lose permissions or expire. Prefer service connections/managed identity as supported by the connector.
- Files can be updated before the workflow reads them; use version/ETag checks.
- With For each, cap concurrency so two invoices are not created from the same file.
- ERP POST may succeed while the response times out; retries require idempotency.
- Run history can store invoice contents/PII; configure **secure inputs/outputs**, retention, and log access controls.
- Human approvals need deadlines, escalation, and fallback approvers.
- Business state must be persisted explicitly; relying solely on a sent email is not enough proof of approval.

## 17. Case Study C: External Webhooks with API Governance

Partners send webhooks to the enterprise:

~~~text
External SaaS → Public HTTPS → APIM → Function handler
                                   |
                                   +→ durable message / DB
~~~

### 17.1. Is APIM Necessary?

If there is only one low-traffic internal webhook, an HTTP Function with appropriate authentication may suffice.

APIM becomes useful when:

- There are multiple webhook providers needing shared routing/policies.
- Per-partner versioning and quotas are required.
- You want centralized TLS/certificates, tracing, transformation, and IP filtering.
- You need an API catalog or different backend protection policies.

### 17.2. Webhook Signatures

Not every webhook uses Entra JWTs. Some providers send an **HMAC signature** over the body or a custom token.

Notes:

- Verify the signature over the **raw request body** as specified by the provider.
- Check timestamps/tolerance and prevent replay attacks.
- Do not log sensitive payloads/secrets.
- Prevent duplicate side effects on retries using eventId.
- If complex custom crypto logic is required, a **Function** is better suited than a long policy script in APIM.
- Return ACK only after the event has been durably enqueued/recorded per the provider contract.

## 18. Case Study D: Event-Driven Data Processing

Requirement: when a CSV file lands in Blob Storage, validate its schema, convert it to JSON, and update metadata.

### 18.1. Choosing Functions

~~~mermaid
flowchart LR
    B["Blob Storage: new CSV"] --> EG["Event Grid / Blob trigger"]
    EG --> F["Azure Function<br/>validate + transform"]
    F --> OUT["Blob Storage: JSON"]
    F --> DB["Metadata DB"]
    F -. "Errors/telemetry" .-> MON["Application Insights"]
~~~

Functions fits when:

- Transformation logic is testable code.
- No multi-SaaS orchestration is needed.
- Event triggers and load-based scaling meet the SLA.
- Data size and duration fit within the hosting plan.

### 18.2. When Should You Add Logic Apps?

When each file also needs to:

- Fetch metadata from SharePoint.
- Send an email to an approval department.
- Call CRM via a connector.
- Wait for a person in charge to confirm.
- Create a ticket on failure.

In that case, use Logic Apps for orchestration and keep the Function as the transformation step.

### 18.3. When Should You Use Container Apps Jobs/Batch Instead of Functions?

If each file is very large, takes hours to process, requires GPUs/specialized binaries, or demands resources beyond Function plan limits, evaluate **Azure Container Apps Jobs, Azure Batch, or AKS Jobs**; Logic Apps should never loop over millions of CSV rows in memory.

## 19. Case Study E: API with an Existing Java Backend

An enterprise has already deployed Spring Boot on App Service or AKS with:

- Business authentication/authorization.
- Database transactions.
- Connection pools.
- Multiple REST endpoints.
- A mature CI/CD pipeline.

If the new requirement is only to expose the API to partners, **there is no reason to migrate the entire Spring Boot application to Functions or Logic Apps**.

Architecture:

~~~mermaid
flowchart LR
    PARTNER["Partners"] --> APIM["APIM<br/>OAuth + quotas + versioning"]
    APIM --> JAVA["Spring Boot API<br/>App Service / AKS"]
    JAVA --> DB["Azure SQL"]
    JAVA --> SB["Azure Service Bus"]
    SB --> FLOW["Logic Apps<br/>downstream SaaS orchestration"]
~~~

Use the right service per boundary:

- **APIM** adds API lifecycle governance.
- **Spring Boot** retains long-lived business APIs and database transactions.
- **Logic Apps** is used only for connector workflows if any exist.
- **Functions** can be added for small event-driven tasks, but is optional.

## 20. Synchronous vs. Asynchronous HTTP Requests and Timeouts

### 20.1. Choosing by User Experience

| Requirement | Pattern | Usually suitable services |
|---|---|---|
| GET order status within 150 ms | Sync HTTP | APIM → backend API |
| POST create a record with short DB commit | Sync HTTP | APIM → Function/App Service |
| POST taking 3 minutes to process | Async 202 + status | APIM → Function enqueue → worker |
| Send 48-hour approval request | Stateful orchestration | Logic Apps/Durable Functions |
| Receive thousands of events/s | Broker-triggered processing | Event Hubs/Functions/ASA/consumer |
| Nightly import batch | Scheduled job | Functions Timer / Logic Apps / Container Apps Jobs depending on logic |

### 20.2. Multi-Layer Timeouts

A request going through APIM to Functions has multiple timeout points:

- Client/browser/proxy HTTP timeout.
- APIM gateway/backend forwarding timeout per policy/tier.
- Function hosting/HTTP trigger behavior.
- Downstream database/API timeout.
- Network/DNS/TLS timeouts.

**Do not raise every timeout to hours just to avoid an asynchronous architecture.** HTTP connections have practical limits; long-running tasks need durable queues/workflow state and a lookup endpoint.

### 20.3. Cancellation Does Not Mean Rollback

A client closing an HTTP connection does not guarantee that the backend Function or Logic Apps stopped side effects. If an order must be canceled, design a stateful **cancellation command** with compensation. You must also account for race conditions between cancellation and worker completion.

## 21. Reliability: Retry, Idempotency, Compensation

### 21.1. At-Least-Once Is the Safe Assumption

Event-driven Functions, Logic Apps connector triggers, and broker messages can retry/re-deliver depending on each trigger's mechanics. Design for the possibility that the same business event is processed multiple times.

~~~mermaid
flowchart TD
    IN["Incoming event / HTTP command"] --> ID["Read stable eventId/idempotencyKey"]
    ID --> CHECK{"Already processed?"}
    CHECK -->|Yes| ACK["Return previous outcome / acknowledge"]
    CHECK -->|No| WORK["Apply durable state transition"]
    WORK --> LOG["Record processed ID + outbox"]
    LOG --> ACK
~~~

Do not store idempotency keys solely in Function memory, as instances can recycle or scale out.

### 21.2. Transient vs. Permanent Retries

| Error | Response |
|---|---|
| HTTP 429 from SaaS | Backoff, honor Retry-After when present, limit concurrency |
| Network timeout | Reconcile outcome/idempotent retry |
| Invalid schema payload | Reject/quarantine; do not retry infinitely |
| 401/403 | Check token/role/secret; infinite retries will not fix authorization |
| Database deadlock | Bounded retry with proper transaction handling |
| API provider created record but response timed out | Query by external key or handle via idempotency |
| Logic Apps action failed after side effect | Compensate or manual review, do not resubmit blindly |
| Broker lock lost | Consumer may receive again; deduplicate business state |

### 21.3. Transactional Outbox

If a Function/API both writes to SQL and emits an event, there is no automatic transaction spanning SQL and Service Bus:

~~~mermaid
flowchart LR
    API["Function / backend API"] --> DBTX["Single database transaction"]
    DBTX --> ORDER["Orders table"]
    DBTX --> OUT["Outbox table"]
    OUT --> PUB["Outbox publisher"]
    PUB --> BUS["Service Bus / Event Hubs"]
    BUS --> CON["Consumer idempotent"]
~~~

The publisher can still send duplicates if it crashes between sending and marking as sent. Stable message/event IDs and consumer idempotency solve duplicate effects.

### 21.4. Compensation and Saga

If a workflow creates an invoice, deducts inventory, and books shipping, rolling everything back with an ACID transaction across SaaS systems is nearly impossible.

Model the states explicitly:

1. **Pending**.
2. **InventoryReserved**.
3. **InvoiceCreated**.
4. **ShipmentBooked**.
5. **Completed** or **Compensating/NeedsReview**.

Each step has an idempotency key, timeout, retry, and appropriate compensating action. Logic Apps/Durable Functions is useful for orchestration, while business data must reside in a reliable system of record.

## 22. Security Comparison Across the Three Services

| Layer | API Management | Logic Apps | Azure Functions |
|---|---|---|---|
| Caller authentication | JWT/OAuth validation, client certificates, subscription keys per config | HTTP trigger auth/connector connections | HTTP auth level, App Service auth/Entra per hosting |
| Backend identity | Managed identity to backend/Key Vault per feature | Managed identity/connection auth per connector | System/user-assigned managed identity |
| Business authorization | Can check claims/policies; does not replace all backend checks | Workflow conditions; must check business permissions | Code/API layer enforces resource permissions |
| Secrets | Named values/Key Vault integration | Secure connections/parameters/Key Vault | App settings/Key Vault references, managed identity |
| Network | Gateway endpoint, VNet/private networking per tier | Consumption/Standard networking differs | Hosting plan/private endpoint/VNet integration |
| Logging | API gateway requests/policies/diagnostics | Run history/action outputs | App Insights/application logs |
| Notable risks | Backend bypass, public gateway, misconfigured policy | Connector credentials/PII in history, unsafe resubmit | Leaked Function key, secrets in env/logs, code CVEs |

### 22.1. Zero Trust and Identity

A service-to-service call path should have independent security decisions:

1. **Client → APIM**: appropriate JWT/mTLS/subscription policy.
2. **APIM → Function/backend**: service-to-service authentication, private network, or backend restrictions.
3. **Function → Service Bus/Storage/SQL**: managed identity and least-privilege data-plane RBAC.
4. **Logic Apps → SaaS/ERP**: connection identity/service account with least privilege.
5. **Operator → Azure resources**: Azure RBAC separating management permissions from business data permissions.

**An enabled Managed Identity does not automatically have permission** to call Key Vault, Service Bus, or databases. You must assign roles and verify permission scopes.

### 22.2. Sensitive Data in Workflows

Logic Apps can store trigger/action inputs and outputs in run history depending on configuration. Do not log passwords, tokens, payment card numbers, or unnecessary PII in:

- Plaintext workflow parameters.
- Publicly logged connector outputs.
- APIM trace/diagnostics.
- Function stdout.
- Application Insights custom events.
- Git, IaC templates, or deployment logs.

Use **secure inputs/outputs** when needed, set appropriate retention, and restrict who can view run history. Do not leave verbose payload tracing enabled in production just for long-term debugging.

## 23. Network Topology and Private Connectivity

A properly authenticated API can still run into issues if private network paths are not clearly designed.

### 23.1. Inbound and Outbound Are Two Different Directions

- **APIM inbound:** callers reach the gateway via public or private ingress per tier/topology.
- **APIM outbound:** the gateway calls the backend, requiring DNS/routing/auth to Function/App Service/AKS.
- **Functions VNet Integration:** typically serves **outbound traffic from the Function app** into a VNet/private services per hosting plan.
- **Function Private Endpoint:** serves **private inbound** traffic per features and configuration.
- **Logic Apps Standard networking:** offers hosting/network options different from Consumption.
- **Logic Apps connectors:** managed connector traffic has its own network model; do not assume all connectors automatically run inside the workflow's VNet.

### 23.2. Private Integration Pattern

~~~mermaid
flowchart LR
    C["B2B client"] --> G["APIM gateway"]
    G -->|"Private backend route"| PE["Function private endpoint"]
    PE --> F["Azure Function API"]
    F -->|"VNet outbound / private DNS"| SQL["Azure SQL Private Endpoint"]
    F -->|"Managed identity"| KV["Key Vault"]
    F --> SB["Service Bus Private Endpoint"]
    SB --> LA["Logic Apps Standard<br/>workflow per network design"]
    LA --> ERP["Internal ERP / SaaS"]
~~~

This is a **target** diagram; actual feasibility depends on tier, SKU, region, subnets, Private DNS, gateway deployment, built-in/managed connectors, and routing/NAT requirements.

### 23.3. Common Mistakes

- Enabling VNet Integration and assuming the Function no longer has public inbound access.
- Enabling a Private Endpoint while forgetting the Private DNS zone/link.
- Choosing an APIM tier that does not support the required internal/external gateway type.
- Assuming Consumption Logic Apps has the same VNet capabilities as Standard.
- Using a managed connector to an internal system without configuring an on-premises data gateway/hybrid connectivity when required.
- Opening a `0.0.0.0/0` public firewall rule temporarily to bypass DNS issues.
- Omitting network egress/NAT/Firewall costs from cost calculations.

## 24. Monitoring, Tracing, and Correlation

### 24.1. Why Is Correlation Needed?

An order travels through:

~~~text
Partner POST
  → APIM request
  → HTTP Function
  → Service Bus command
  → Logic Apps workflow
  → Function transform
  → ERP
~~~

Without an end-to-end **operationId/traceId**, operators have to guess whether scattered logs belong together.

### 24.2. Recommended Identifiers

- **traceparent** or W3C trace context for request tracing as supported by SDK/transport.
- Stable **operationId** for asynchronous operations.
- Stable **eventId/messageId** for idempotency.
- **workflowRunId** to link Logic Apps run history.
- **externalOrderId** for ERP/business reconciliation.

Do not use the same ID for every purpose without understanding semantics; one request can spawn multiple messages and workflow runs.

### 24.3. Three Telemetry Layers

| Layer | Signals |
|---|---|
| APIM | Total requests, p50/p95/p99 latency, 4xx/5xx, gateway/backend errors, throttling/quota |
| Logic Apps | Trigger runs, action success/failure/timeout, run duration, retries, connector throttling |
| Functions | Invocation count/duration, errors, dependencies, cold start indicators, memory/concurrency |
| Architecture-wide | End-to-end completion SLO, backlog age, failed operations, DLQ, replay count, cost per completed workflow |

Azure Monitor, Application Insights, and Log Analytics must be configured according to requirements/plans; do not assume every metric, trace, or payload is captured by default.

### 24.4. Business-Outcome SLOs

An API with **99.9% HTTP 202** is not necessarily healthy if 10% of operations get stuck in ERP. Example SLOs:

- 99% of authenticated partner requests receive an ACK within 2 seconds.
- 99% of accepted orders complete within 5 minutes.
- Zero orders remain PENDING beyond 15 minutes without an alert.
- 100% of failed workflows have an error reason and correlation sufficient for triage.
- Discrepancy between processed orders and source records stays within controlled bounds.

These numbers are **illustrative targets**, not Azure service SLAs.

## 25. Structured Cost Comparison

### 25.1. Cost Model

| Component | Cost units typically evaluated | Hidden costs to account for |
|---|---|---|
| **APIM** | Gateway tier/units/requests per plan and config | Gateway capacity, diagnostics, private networking |
| **Logic Apps Consumption** | Triggers/actions/connector executions per model | Polling, retries, loops, managed connector calls |
| **Logic Apps Standard** | Hosting plan compute/storage, applicable connectors/operations | Always-on capacity, state storage, diagnostics |
| **Azure Functions** | Executions, duration/compute/memory, provisioned instances per plan | Cold start mitigation, storage, logs, VNet/NAT |
| **Durable Functions** | Function executions, state/storage operations, and hosting | History growth, retries, timers, telemetry |
| **Service Bus/Event Grid** | Messaging operations/events and tier | DLQ, retention, processing retries |
| **Azure Monitor** | Ingestion, retention, alerts | Verbose action logs, PII masking |
| **Network** | Private Endpoints, NAT, bandwidth/egress per service | Cross-region transfers, firewall |

**Do not assume APIM is free just because the API has zero requests.** Some gateway tiers carry fixed provisioning/capacity charges. Likewise, do not assume Consumption Logic Apps costs almost nothing per execution when flows involve many actions and retries.

### 25.2. Example Action Count Calculation

A Logic Apps workflow runs **100,000 times/month**, and each successful run executes:

- 1 trigger.
- 2 connector actions.
- 1 HTTP action.
- 1 condition.
- 1 notification action.

The ideal number of action executions is:

~~~text
100,000 workflow runs × 5 actions/run
= 500,000 action executions
~~~

This is only a **hypothetical action count**, excluding trigger pricing, connector categories, retries, polling, skipped actions, concurrency, Standard hosting, and individual action pricing meters. Conditions/triggers may also be metered differently depending on runtime/plan.

If 20% of ERP calls retry twice, total actual invocations will significantly exceed the simple estimate.

### 25.3. Comparing Cost per Completed Operation

A better model than “cost per request”:

~~~text
TCO / completed order
 = (APIM + Function + Logic Apps + messaging
    + database + storage + networking
    + logging + operations)
   / number of orders actually completed
~~~

A system with heavy retries, manual recovery, and dead-lettering increases costs even if incoming traffic stays flat. Track **cost per successful business transaction** and SLOs rather than optimizing each service in isolation.

### 25.4. When Not to Use All Three

If you only need a nightly Timer Function, adding APIM and Logic Apps increases operational overhead, latency, and cost without delivering value.

If you only use APIM to forward to an existing Spring Boot backend, do not insert a pointless Function in the middle just to look “serverless.”

If Logic Apps already has sufficient connectors/actions and there is no specialized algorithm, do not wrap every step in a Function.

## 26. Reliability and Limits of Each Service

### 26.1. APIM

- Gateway capacity/throughput per tier; policy latency increases with configuration complexity.
- Backend timeouts and connection failures.
- Retry policies for POST require idempotency.
- Caching requires invalidation and isolation of sensitive data.
- Rate-limit/quota behavior must be verified against the actual gateway topology.
- Gateway HA/availability depends on tier and deployment mode.

### 26.2. Logic Apps

- Workflow state, action count, run duration, and trigger frequency limits per plan.
- Connector-specific throttling/limits and authentication refresh.
- Polling triggers carry distinct latency and cost implications.
- For each/concurrency can overload downstream ERP systems.
- Retries/resubmits create duplicate effects if business logic is not idempotent.
- Run history retention and sensitive data exposure.
- Connection reference and built-in connector differences when moving between Consumption ↔ Standard.

### 26.3. Functions

- Hosting plan scaling/cold start and request timeouts.
- Trigger/binding version compatibility.
- Queue lock/visibility timeout, poison queue/DLQ behavior per broker.
- Application startup, JVM heap/thread pools.
- Stateless execution: instances can recycle.
- Durable Functions requires deterministic orchestrators, durable state, and safe activity retries.
- Optimal concurrency should follow downstream quotas rather than raw core count.

### 26.4. Cross-Region Outages

If an entire region experiences an outage, no single product guarantees multi-region resilience automatically just because it is PaaS. You must design:

- Appropriate APIM gateway instance/region routing.
- Redundantly deployed Function apps or backends.
- Logic Apps workflow deployment and state recovery strategy.
- Replication/restore for databases, messaging, and storage.
- DNS/Front Door/Traffic Manager according to supported architecture.
- Secrets/identities and private networking in the secondary region.
- Failover runbooks, RPO/RTO targets, and real disaster recovery drills.

## 27. Anti-Patterns to Avoid

| Anti-pattern | Problem | Fix |
|---|---|---|
| Putting tax calculation and multi-step database queries inside APIM | Policies hard to test/maintain, gateway becomes a bottleneck | Move domain logic to Function/backend |
| Logic Apps For each over millions of records | Bloated runs, throttling/memory/cost spikes | Batch/stream engine or Functions/Batch |
| An HTTP Function holding a connection for 30 minutes | Timeouts, resource pressure | 202 + durable queue + status |
| Using Function global static state as workflow state | Scale/restarts wipe state | Durable Functions/Logic Apps/DB |
| Logic Apps using personal user OAuth connections in production | User leaving company/token expiry breaks flow | Managed/service identity per connector |
| APIM key as the sole security layer | Keys can be shared/leaked, lacks user permissions | OAuth/JWT/business authorization |
| Public Function backend without blocking direct access | APIM policies get bypassed | Private/restricted backend + service auth |
| Retrying ERP POST without idempotency | Duplicate transactions | External business key, reconciliation |
| Resubmitting workflow when outcome is uncertain | Re-executes side effects | Check state first, compensation |
| Monitoring only HTTP 200/202 | No visibility into whether operations actually finish | End-to-end status, correlation, and alerts |
| Using all three services for a single-step flow | Unnecessary overhead/cost | Pick the simplest service meeting requirements |
| Hard-coding API keys/connection strings in IaC | Credential leakage | Key Vault, managed identity, secret references |
| Not versioning APIs/workflow contracts | Clients and backends break on changes | OpenAPI, schema versioning, backward compatibility |
| Undefined data ownership | Workflows cross-call and overwrite databases | Clear ownership, event-driven integration |

## 28. Architecture Selection and Review Process

### 28.1. Step 1: Describe the Business Event/Command

Example:

~~~text
Trigger: Partner sends new order HTTP POST
Identity: Partner application with Entra token
Response SLO: 2 seconds
Business completion SLO: 5 minutes
Downstream: ERP, payment provider, email
Approval: Sometimes, for high value orders
Peak: 300 requests/s
Data classification: Confidential
Network: Prefer private backend and managed identities
Failure handling: Idempotent retry, compensation, manual review
~~~

### 28.2. Step 2: Separate Responsibilities

- API ingress/gateway governance → **APIM**.
- Short-lived validation/enqueuing → **Function** or existing backend.
- Async commands/events → **Service Bus/Event Grid** when needed.
- SaaS connectors and approvals → **Logic Apps**.
- Complex computation → **Function/Durable Functions or app backend**.
- Durable business state → **database/workflow state**, not telemetry logs alone.

### 28.3. Step 3: Check Non-Functional Requirements

- Availability/SLA, p95/p99 latency.
- RTO/RPO, region/data residency.
- OAuth/mTLS/managed identity, private networking.
- Peak throughput, scale limits, runtime and connectors.
- Run history/log retention, data privacy.
- CI/CD, staging, rollback, DR.
- Monthly budget and cost per completed operation.

### 28.4. Step 4: Test Failure Modes

At a minimum:

1. APIM gateway receives an invalid token.
2. Backend Function times out after enqueuing.
3. Service Bus redelivers the same message.
4. ERP returns 429 for 10 minutes.
5. Logic Apps action succeeds, but the response is lost.
6. Approver does not respond before the deadline.
7. Function/Logic Apps scale-out processes the same business key concurrently.
8. Private DNS failure prevents backend from reaching SQL.
9. Workflow is resubmitted after data has already committed.
10. A region or connector becomes unavailable.
11. Secrets expire or role assignments are revoked.
12. Excessive telemetry inflates cost and risks data exposure.

### 28.5. Step 5: Make a Conditional Decision

Example conclusion:

> “Use APIM Premium or a tier supporting private networking for the B2B gateway; the existing Orders API on App Service handles validation and queueing; Service Bus decouples long-running processing; Logic Apps Standard if the workflow requires private connectors and approvals; a Java Azure Function performs the specialized algorithm. Benchmark per SKU, verify connector/region compatibility, enforce OAuth/managed identity, test idempotency, and build a cost estimate before production.”

This is a **reasoning template**, not a mandatory tier recommendation. During implementation, select the specific SKU based on supported features and current pricing.

## 29. Controlled Azure Portal Hands-On Guide

The following steps are for an approved lab environment, not actions performed within this lesson.

### 29.1. Preparation

- Dedicated subscription and resource group for the lab.
- Azure permissions to manage/create each service.
- An identity with deployment rights, without necessarily being subscription Owner.
- Budgets/alerts; note that certain APIM tiers incur gateway charges even with zero requests.
- A demo Function App or backend endpoint containing no sensitive data.
- A test Logic App workflow calling an approved endpoint/connector.
- Application Insights/Azure Monitor per policy.
- A plan to properly delete lab resources afterward.

### 29.2. Create the Function First

In the Portal:

1. **Create → Function App**; select a Java-supported runtime along with hosting plan and region.
2. Review cost/network/instance limits.
3. Deploy the Function project via CI/CD/IDE or built artifact.
4. Configure App settings via secret references or managed identity.
5. Test the HTTP Function in the lab environment with valid/invalid bodies.
6. Record the base URL, route, auth mechanism, and deployment version.
7. Never send production credentials in test payloads.

### 29.3. Create the API in APIM

1. Create an APIM instance/tier suitable for lab needs, reading pricing carefully.
2. Create an **API** via OpenAPI/HTTP or add operations manually.
3. Configure the backend Function URL.
4. Add test validation/rate-limiting policies.
5. Verify auth, routing, status codes, and backend errors.
6. Protect the direct Function endpoint using a supported approach.
7. Test the API from both unauthorized and authorized callers.
8. Inspect request logs along with the correlation ID.

### 29.4. Create the Logic App Workflow

1. Create a Consumption or Standard Logic App per the lab architecture.
2. Choose a **Recurrence** or HTTP/request trigger as appropriate.
3. Add an HTTP action calling the Function/APIM endpoint.
4. Add a condition and a Catch branch using Scope/runAfter.
5. Configure identity/connections/secrets.
6. Enable secure inputs/outputs for sensitive content.
7. Run with sample data and inspect run history and errors.
8. Simulate an action failure to verify retry/alert handling.
9. Confirm no duplicate side effects occur on resubmit.

### 29.5. Clean Up the Lab

- Check whether the APIM instance serves other APIs.
- Check whether the Function App contains code/config that must be kept.
- Check whether the Logic Apps workflow still runs on recurrence and incurs ongoing costs.
- Check for supporting Service Bus/Storage/App Insights/Key Vault resources.
- Check for shared private endpoints, NAT Gateways, custom DNS, Log Analytics, or connections.
- Delete only lab-dedicated resources with owner approval.

Do not delete an entire resource group without checking for shared resources inside it.

## 30. Symptom-Based Troubleshooting

| Symptom | Possible cause | How to check |
|---|---|---|
| APIM returns 401 even though Function works directly | Wrong JWT issuer/audience/expiry | APIM validate-jwt policy, Entra app registration |
| APIM 403 | Policy/backend authorization, IP restriction, product subscription | APIM diagnostics, claims, backend access |
| APIM 429 | Rate-limit/quota exceeded | Counter key, limits, and partner traffic |
| APIM 502/504 | Backend timeout/network/DNS/TLS | Gateway/backend logs and routing |
| Function accessible directly, fails through APIM | Backend network/auth or policy issue | APIM trace, Function access restrictions |
| Function 401 due to key | Wrong Function auth level/key | Key rotation, APIM named value |
| Slow Function cold start | Plan/instance startup/JVM initialization | Invocation latency, hosting plan, prewarming |
| Logic Apps trigger does not fire | Trigger config/poll interval/connection | Trigger history, connector auth |
| Logic Apps action 429 | SaaS throttling | Retry policy, concurrency, provider limits |
| Logic Apps Failed, but ERP created data | Lost response/partial failure | Query external business key, idempotency |
| Function Service Bus trigger runs repeatedly | Lock expired, redelivery/retry | Queue DLQ/delivery count, consumer idempotency |
| Logic Apps run history exposes payloads | Secure outputs disabled, overly broad permissions | Access control, retention, secure IO |
| Azure Function cannot call private SQL | VNet Integration/DNS/firewall | Effective routes, private endpoint, identity |
| APIM private gateway unreachable from client | Routing/DNS/tier/topology | Gateway network config and DNS |
| Logic Apps Standard networking differs from Consumption | Incompatible connector/hosting model | Check plan and connection model |
| Sudden cost spike | APIM tier, workflow retries, Functions scaling, logs | Cost Management by resource/meter |

### 30.1. Debug APIM First

1. Verify hostname, API path, and HTTP method.
2. Determine whether 401/403/429/5xx comes from gateway policy or backend.
3. Check token issuer/audience/scope/role or subscription config.
4. Verify named values and key references.
5. Verify backend URL, DNS, private route, and TLS.
6. Compare a direct backend call (from an allowed network path) with a request via APIM.
7. Inspect diagnostics/tracing safely without logging secret payloads.
8. Monitor gateway vs. backend latency.
9. If the backend committed while the gateway timed out, use idempotency/reconciliation.
10. Never disable JWT validation entirely as an unapproved temporary workaround.

### 30.2. Debug Logic Apps

1. Did the trigger actually fire?
2. Are connections/authentication valid?
3. At which action did run history stop?
4. Was the action Failed/TimedOut/Skipped, and is `runAfter` configured properly?
5. What were the retry count and retry timing?
6. Did the external API already create a side effect?
7. Is there a concurrency race or connector throttling?
8. Did payload schema/size/encoding change?
9. Are secure inputs/outputs hiding data as expected for security?
10. Do you need to repair/compensate or perform an idempotent resubmit?

### 30.3. Debug Functions

1. Did the trigger receive the request/event?
2. Do the app/runtime/JDK version/dependencies match?
3. What do invocation logs/exceptions/correlation IDs show?
4. Are there memory/CPU/cold start/concurrency bottlenecks?
5. Are auth level/App Service auth/managed identity configured properly?
6. Are App settings and Key Vault references resolving?
7. Is it an HTTP request timeout or queue lock expiry?
8. Are Service Bus/Event Hubs/Storage roles and networking valid?
9. Was the business result durably committed?
10. Are there retries/duplicate effects or poison messages to handle?

## 31. Production Checklist

- [ ] API gateway, workflow orchestration, and custom compute are clearly separated as three distinct responsibilities.
- [ ] APIM/Logic Apps/Functions are not deployed merely to overcomplicate the architecture.
- [ ] Hosting plans/SKUs match region, network, latency, and real workload requirements.
- [ ] APIs have OpenAPI/versioning contracts and owners.
- [ ] APIM authenticates via JWT/OAuth or appropriate mechanisms; subscription keys do not replace authorization.
- [ ] Backends cannot be bypassed via uncontrolled public endpoints.
- [ ] Function/Logic Apps connections use proper identity/secret management.
- [ ] Inbound/outbound VNet, private DNS, and connector networking are clearly designed.
- [ ] Stateful/stateless Logic Apps choice aligns with workflow duration and history needs.
- [ ] Retry caps, dead-letter/manual review, compensation, and explicit business states are implemented.
- [ ] Long-running HTTP calls use 202 + durable enqueue + status API where appropriate.
- [ ] Idempotency keys are designed across HTTP POST, queue messages, and workflow actions.
- [ ] Resubmit/retry is never treated as guaranteeing an exactly-once business effect.
- [ ] Durable Functions orchestrators follow deterministic/replay rules.
- [ ] Correlation IDs flow across APIM, Functions, Service Bus, and Logic Apps.
- [ ] Monitoring measures business completion, not only HTTP 200/202.
- [ ] Logs/run history do not leak secrets or sensitive data; retention is configured.
- [ ] CI/CD and IaC manage runtimes, policies, workflow definitions, and connections.
- [ ] Staging and tests cover network errors, timeouts, 429s, and rollbacks.
- [ ] RTO/RPO and DR plans exist for the entire end-to-end process.
- [ ] Cost estimates cover APIM tier, Logic Apps actions/hosting, Functions compute, messaging, logs, and networking.
- [ ] Incident runbooks and permission/key revocation procedures have been tested.

## 32. Practice Exercises

### Exercise 1: Task Classification

Choose APIM, Logic Apps, Functions, or a combination for six requirements:

1. Public API for 25 partners requiring JWT, quotas, and a developer portal.
2. When an email with an attachment arrives, extract metadata, update CRM, and notify Teams.
3. API calculating shipping rates using a 500-line Java algorithm.
4. Wait up to 72 hours for executive approval on a purchase request.
5. A Java REST API already running reliably on AKS that only needs a public versioned endpoint.
6. On BlobCreated, validate schema and convert the file to JSON.

Explain why the remaining services were excluded when unnecessary.

### Exercise 2: APIM and Backend Function

1. Create a lab HTTP Function returning a JSON validation response.
2. Add an API/operation in APIM.
3. Design JWT validation and rate limiting.
4. Test 401, 429, and successful requests.
5. Describe how to block direct calls to the backend.
6. Explain how to manage the function key if used.
7. Propagate a correlation ID across APIM/Function.

### Exercise 3: Logic Apps Workflow

Design a workflow triggered when an invoice is uploaded:

- SharePoint/Blob trigger.
- Validate schema.
- Call Function to process JSON/XML.
- Create invoice in ERP.
- If the invoice exceeds a threshold, wait for approval.
- Send email/Teams notification.
- When ERP returns 429, retry with backoff and idempotency.
- On failure, run Catch/alert/compensation.

Diagram the flow, specify action concurrency, and identify where business state is stored.

### Exercise 4: Async Orders API

For **POST /orders** taking 3 minutes to process:

1. Design APIM + HTTP Function + Service Bus + worker.
2. Define HTTP 202, Location, and operationId.
3. Ensure durable enqueue happens before ACK.
4. Use Idempotency-Key to prevent duplicate creation.
5. Write the PENDING/PROCESSING/SUCCEEDED/FAILED state machine.
6. Design recovery/retry when a worker crashes after DB commit.
7. Explain how to monitor end-to-end SLOs.

### Exercise 5: Logic Apps or Durable Functions?

A process has 30 computational steps, fans out to 500 parallel tasks, waits for an external event up to 2 days, and uses 2 SaaS connectors.

Propose:

- A code-first Durable Functions design.
- A Logic Apps + Functions design.
- Selection criteria based on team skills, state, observability, connectors, limits, testability, and cost.
- Why activity side effects still require idempotency.

### Exercise 6: Network and Identity

A company wants public APIM, private Function/SQL/Service Bus backends, and Logic Apps calling ERP over a private path.

Describe:

- Gateway inbound and backend outbound paths.
- Function private endpoint and VNet integration.
- Private DNS / NSG / firewall.
- Managed identity & RBAC for each service.
- Networking differences between Logic Apps Standard and Consumption.
- How to test without opening unrestricted public access.

### Exercise 7: FinOps

A system has 200,000 API calls/month, 30,000 workflows averaging 8 actions/run with 10% of ERP call actions retrying once, and Functions handling 100,000 executions.

Build a breakdown covering:

1. APIM plan and request workload.
2. Logic Apps actions/connector executions, plus retries.
3. Functions executions/compute per plan.
4. Service Bus, database, logs, and networking.
5. Total cost per **completed business operation**.
6. When to drop APIM or avoid Logic Apps to reduce complexity.

### Exercise 8: Incident Response

An API returns HTTP 504, yet the ERP created the order. The client retries the POST, and Logic Apps also resubmits a run.

Identify:

- Points where duplicate side effects can occur.
- Roles of APIM, Function, Logic Apps, and ERP in the investigation.
- Where idempotency/unique keys belong.
- Whether automatic resubmit is safe.
- How to check state before running compensation.
- Minimum traces and logs required.

### Self-Check Questions

1. Is APIM a general-purpose environment for running Java business code?
2. Does an APIM subscription key replace user OAuth/authorization?
3. Why must the gateway protect the backend from direct access?
4. When are API versioning and a developer portal needed?
5. In what types of processes is Logic Apps strongest?
6. How does a trigger differ from an action?
7. What is the fundamental difference between Logic Apps Consumption and Standard?
8. How does a stateful workflow differ from a stateless one?
9. What error can retrying an HTTP POST that creates an invoice cause?
10. What is Logic Apps `runAfter` used for?
11. Does resubmitting a workflow roll back external systems?
12. When is an HTTP Function sufficient without APIM?
13. Does a Function key determine permission to view a specific `orderId`?
14. What factors influence Azure Functions cold start?
15. When should you use Durable Functions instead of a single HTTP Function?
16. Why does a Durable Functions orchestrator require deterministic code?
17. What HTTP contract should an API taking more than 3 minutes use?
18. What is the risk of returning 202 before the message is durably stored?
19. Why do callbacks or event-driven triggers need idempotency?
20. Does a managed identity automatically grant permission to Service Bus or Key Vault?
21. Does VNet Integration automatically block public inbound access to a Function?
22. Why do managed SaaS connectors not always share the same network path as the Logic Apps runtime?
23. Which SLOs measure workflow outcomes better than HTTP 200/202?
24. Can APIM incur costs even when an API receives no traffic?
25. Why should you calculate cost per completed operation rather than only cost per request?

## 33. References

- [Azure API Management overview — Microsoft Learn](https://learn.microsoft.com/azure/api-management/api-management-key-concepts)
- [Azure API Management policies](https://learn.microsoft.com/azure/api-management/api-management-howto-policies)
- [APIM validate-jwt policy](https://learn.microsoft.com/azure/api-management/validate-jwt-policy)
- [APIM rate-limit-by-key policy](https://learn.microsoft.com/azure/api-management/rate-limit-by-key-policy)
- [APIM authentication and authorization](https://learn.microsoft.com/azure/api-management/authentication-authorization-overview)
- [Azure Logic Apps overview](https://learn.microsoft.com/azure/logic-apps/logic-apps-overview)
- [Single-tenant versus multitenant Logic Apps](https://learn.microsoft.com/azure/logic-apps/single-tenant-overview-compare)
- [Managed and built-in connectors for Logic Apps](https://learn.microsoft.com/azure/connectors/apis-list)
- [Logic Apps run history and troubleshooting](https://learn.microsoft.com/azure/logic-apps/monitor-logic-apps)
- [Azure Functions overview](https://learn.microsoft.com/azure/azure-functions/functions-overview)
- [Azure Functions hosting options](https://learn.microsoft.com/azure/azure-functions/functions-scale)
- [Java developer guide for Azure Functions](https://learn.microsoft.com/azure/azure-functions/functions-reference-java)
- [Azure Functions triggers and bindings](https://learn.microsoft.com/azure/azure-functions/functions-triggers-bindings)
- [Durable Functions overview](https://learn.microsoft.com/azure/azure-functions/durable/durable-functions-overview)
- [Durable Functions code constraints](https://learn.microsoft.com/azure/azure-functions/durable/durable-functions-code-constraints)
- [Azure Service Bus overview](https://learn.microsoft.com/azure/service-bus-messaging/service-bus-messaging-overview)
- [Microsoft Entra managed identities for Azure resources](https://learn.microsoft.com/entra/identity/managed-identities-azure-resources/overview)
- [Azure API Management pricing](https://azure.microsoft.com/pricing/details/api-management/)
- [Azure Logic Apps pricing](https://azure.microsoft.com/pricing/details/logic-apps/)
- [Azure Functions pricing](https://azure.microsoft.com/pricing/details/functions/)
