# What Is Serverless and What Is the Cloud Provider's Responsibility?

In the **Serverless Foundations** chapter, this lesson clarifies how serverless operates applications in the cloud and which responsibilities belong to the cloud provider versus the development team. This provides the foundation for deciding whether to use Function as a Service (FaaS) for a Java feature triggered by HTTP, messages, or events.

## Learning Objectives

After this lesson, you will be able to:

- Explain serverless and why the name does not mean applications run without servers.
- Distinguish FaaS from managed backend services (BaaS).
- Describe the flow of a request or event entering a function.
- Identify the responsibility boundary between the cloud provider and the development team.
- Recognize the application decisions you still must handle yourself: access permissions, state, retries, idempotency, scalability, cold starts, and cost.

## 1. What Is Serverless?

**Serverless** is a cloud service consumption model in which the provider is responsible for operating most of the underlying infrastructure and automatically allocating compute capacity on demand. The development team focuses on application code and service configuration instead of provisioning servers, installing operating systems, maintaining clusters, or scheduling scaling for individual machines.

The name is easy to misunderstand: **serverless still runs on servers**. Physical servers, operating systems, networking, and orchestrators still exist in the provider's data centers. They are abstracted away from the service consumer. Therefore, what changes is operational responsibility and the level of infrastructure control—not the disappearance of servers.

A serverless system typically combines two groups of services:

- **Function as a Service (FaaS):** deploys a small unit of code, usually a function, for the platform to invoke when an HTTP request, message, or event arrives. The platform manages the execution environment and adjusts the number of execution instances based on load within service limits.
- **Backend as a Service (BaaS) or managed backend services:** uses capabilities such as databases, object storage, authentication, queues, event buses, or API gateways operated by the provider. Applications call these services via APIs or SDKs.

FaaS and BaaS often go together. For example, a Java function that processes orders can be invoked when a queue receives a message, validate the data, and write the result to a managed database.

### How Does Serverless Differ from Running Traditional Servers?

| Model | Development team typically manages | Platform typically manages |
|---|---|---|
| Virtual machines (IaaS) | Guest OS, runtime, application, scaling configuration, and most machine operations | Hardware, networking, and virtualization layer |
| Self-managed containers | Images, application, container configuration, cluster, deployments, and scaling according to the chosen platform | Depends on the service: may be only machine infrastructure or also the control plane |
| FaaS | Function code, libraries, configuration, permissions, triggers, and error behavior | Execution infrastructure, invocation scheduling, and most capacity provisioning |
| BaaS / managed backend | How the application uses the service, data, permissions, and required configuration | Platform operations of the backend service within the product's scope |

The exact boundary depends on the service. A managed container service may offload more work than self-operated containers; a managed database may require customers to enable backups or configure networking themselves. Therefore, always check the responsibility documentation and configuration of the cloud product you are using.

## 2. How Is a Serverless Function Triggered?

A function typically does not run a loop waiting for requests like a traditional server application. Another service receives an event and then asks the platform to execute the corresponding function.

Common trigger types:

- **HTTP:** an API gateway or HTTP integration layer receives a request, validates it, and converts the request into an input event for the function. The function returns a result so the integration layer can build the HTTP response.
- **Message:** a queue or messaging service invokes the function when there is a message to process. This decouples the sender from the receiver and absorbs traffic spikes.
- **Event:** an event bus, schedule, storage service, or another cloud service emits an event when state changes. The function reacts to that event.

General flow:

~~~mermaid
flowchart LR
    A["Client or event-producing service"] --> B["HTTP Gateway / Queue / Event Bus"]
    B --> C["FaaS Platform"]
    C --> D["Java Function"]
    D --> E["Database / Object Storage / API"]
    C --> F["Logs and Metrics"]
~~~

The provider operates the gateway, queue, event bus, and FaaS environment according to the scope of each product. The development team still must decide which events trigger the function, what the function is allowed to do, whether input data is valid, and where results are stored.

### Simple Java Example

The following example illustrates a handler using the AWS Lambda API. The input event is simplified to a map; an actual event delivered by an HTTP gateway, queue, or event source may have a different structure.

~~~java
import com.amazonaws.services.lambda.runtime.Context;
import com.amazonaws.services.lambda.runtime.RequestHandler;
import java.util.Map;

public class GreetingHandler
        implements RequestHandler<Map<String, String>, Map<String, String>> {

    @Override
    public Map<String, String> handleRequest(
            Map<String, String> event, Context context) {
        String name = event.getOrDefault("name", "there");
        return Map.of("message", "Hello " + name);
    }
}
~~~

When an invocation occurs, the platform initializes or reuses an execution environment, passes the event and context to the handler, and receives the result. The development team still needs to package the code and libraries, choose a supported runtime, configure memory and timeout, attach triggers, grant appropriate permissions, and handle errors. The code snippet does not create an HTTP endpoint by itself; the endpoint must be configured in the integration layer.

## 3. What Is the Cloud Provider Responsible For?

In a managed FaaS model, the provider is typically responsible for the infrastructure layers that customers do not operate directly:

1. **Data centers and hardware:** physical facilities, power, cooling, network equipment, physical servers, and physical access controls.
2. **Platform layer:** virtualization or workload isolation, host operating system, control plane, scheduler, and execution environment provisioning mechanisms.
3. **FaaS service operations:** receiving invocation requests, initializing environments, passing events to handlers, reclaiming or reusing environments, and adjusting compute capacity according to the service's mechanisms.
4. **Maintenance of managed components:** patching and maintaining platform components that the product commits to managing, such as hosts and provider-supplied runtimes.
5. **Backend service operations:** maintaining the infrastructure of managed queues, object storage, API gateways, or databases according to each product's commitments and configuration.
6. **Providing metering and control mechanisms:** publishing quotas, limits, billing information, service status, and platform logs or metrics that customers can use.

This frees the development team from directly managing servers for each function. However, the provider's responsibility always has boundaries. For example, the provider may release patched runtimes, but the development team must still update the function to a supported runtime and update the application's third-party libraries.

## 4. What Is the Development Team Still Responsible For?

Serverless reduces infrastructure operations, but it does not transfer ownership of the application and data to the provider. The following decisions still belong to the development team or the organization using the cloud.

| Area | Cloud provider | Development team / customer |
|---|---|---|
| Physical infrastructure | Secures and operates data centers, servers, and underlying network | Chooses regions and services suited to requirements |
| FaaS environment | Operates control plane, hosts, and managed execution mechanisms | Writes functions, packages dependencies, tracks runtime lifecycles, and updates libraries |
| Application code and data | Provides storage or execution services | Owns code correctness, data classification, quality, and data usage permissions |
| Identity and permissions | Provides IAM, policy engine, and authentication mechanisms | Configures principals, roles, policies, and least-privilege permissions per function |
| Networking and data protection | Operates network infrastructure; provides encryption and control mechanisms | Configures network access, endpoints, firewalls, secrets, keys, and appropriate encryption requirements |
| Reliability | Operates services according to design and published SLAs | Designs retries, idempotency, timeouts, error handling, backups, and recovery as needed |
| Observability and cost | Provides telemetry, logs, metrics, and billing | Sets up alerts, monitors business behavior, and optimizes resources and budgets |

This is the **shared responsibility** model. A service being called "managed" does not mean all security, backup, recovery, or compliance settings are automatically configured correctly for your application. For example, a managed database may support encryption and backups, but the customer must verify whether the configuration, backup scope, retention period, and recovery capability meet requirements.

### Access Permissions Are a Critical Customer Responsibility

Each function should have its own execution identity and only be granted the permissions necessary for its task. An order-processing function may need to read from one queue and write to one specific table; it should not by default have administrative permissions across the entire cloud account.

Both directions must be checked:

- **Who can invoke the function?** For example: which API gateway, event source, or principal is allowed to trigger the function.
- **Which services can the function call?** For example: which queue the function may read from, which bucket it may write objects to, or which database it may access.

Credentials and secrets should not be hardcoded in source code or written to logs. Use platform-provided secret and identity management mechanisms, restrict secret read permissions, and rotate credentials according to organizational policy.

## 5. Operational Consequences to Understand When Using FaaS

Even though the provider manages the servers, the development team must still design functions to operate correctly in a distributed and constrained environment.

### State: Do Not Rely on Single-Run In-Memory State

An execution environment may be reused, but the platform can also create a new environment or reclaim an old one at any time. Global variables and temporary files can be useful for short-lived caching, but they are not the place to store durable business state.

If a function needs to remember state across invocations, store that state in a database, object storage, cache, or an appropriate service. Design functions to receive sufficient input data, perform a bounded processing step, and persist the required results.

### Retries and Idempotency: An Event May Be Processed Multiple Times

When a function fails or does not acknowledge processing in time, the source service may resend the event. Many message/event integrations use at-least-once delivery, so the same message can appear more than once. Exact behavior depends on the event source and configuration; read the trigger documentation carefully.

**Idempotency** is the ability to receive the same request multiple times while ensuring the final business outcome remains equivalent to processing it once. For example, when processing a payment, use a unique transaction ID and check whether the transaction has already been recorded before creating a new charge. Do not rely on the assumption that a function "usually runs only once."

You must clearly define:

- What conditions determine that a processing attempt succeeded.
- Which errors are retryable and which should be routed to a dead-letter queue (DLQ) or error-handling flow.
- Maximum retry counts, wait intervals, and maximum processing time.
- How results are recorded so redeliveries do not create duplicate side effects.

### Cold Starts: The First Invocation May Take Extra Time

If no execution environment is ready yet, the platform must initialize an environment before running the handler. This additional initialization time is commonly called a **cold start**. Duration depends on the runtime, package size, libraries to load, configuration, and platform.

You can reduce the impact by keeping packages lean, avoiding unnecessary initialization, and measuring actual timings. Some platforms provide pre-warmed environments or provisioned concurrency; those mechanisms can reduce startup latency but usually incur additional cost. Choose based on latency requirements and measured data rather than assuming every invocation experiences a cold start.

### Automatic Scaling Still Has Limits

FaaS can scale up concurrent invocations as load rises and scale down when load drops. That does not mean capacity is infinite. Accounts and services have quotas on concurrency, invocation rate, execution duration, payload size, or connection counts.

A traffic surge can cause a function to generate many concurrent requests to a downstream database or API. If the target system cannot handle that load, scaling the function can make matters worse. The development team needs to set appropriate concurrency limits, use queues to absorb load, manage backpressure, and monitor throttling as well as errors from dependent services.

### Cost: Pay-Per-Use, but Account for the Whole System

FaaS typically bills based on invocation count and compute resources or execution duration; measurement and unit pricing vary by provider. The total cost of a serverless flow can also include API gateways, queues/events, databases, storage, data transfer, logs, metrics, and provisioned capacity.

Therefore, a function with a low unit price can still generate a large bill if invoked too frequently, running too long, logging excessively, or calling expensive supporting services. Track costs by function, environment, and business flow; set budgets and alerts; and check for abnormal retries, event loops, and invalid requests.

## 6. When Should You Consider FaaS?

FaaS is often a good fit when:

- Work is triggered by clear HTTP requests, messages, schedules, or events.
- Traffic fluctuates heavily or has periods of low activity.
- Work can be broken into relatively independent processing steps whose execution time fits within service limits.
- The development team wants to reduce server operations and accepts the provider's runtime model, quotas, and integrations.

Consider carefully when:

- A process must run continuously or longer than the function's duration limit.
- The application depends heavily on in-memory state or long-lived connections.
- Traffic is steadily high and cost needs to be compared against continuously running containers or servers.
- Latency requirements are very strict and startup time cannot be tolerated.
- The application requires deep control over the operating system, runtime, or network environment.

No model is always cheaper or better. Compare total cost, latency, reliability, operational effort, and required level of control for a specific workload.

## 7. Integrated Example: Processing Orders from Messages

Suppose an e-commerce application sends an **OrderCreated** message to a queue. A Java function is triggered to validate the order and write its status to a database.

- The provider operates the queue, FaaS infrastructure, and managed database according to each service's commitments.
- The development team configures the event source, permissions for the function to read the queue and write to the specific table, timeout, concurrency, and retry policy.
- The function validates the schema and order ID; if the same message is redelivered, an idempotency key or unique constraint prevents creating duplicate records or side effects.
- For recoverable errors, the retry policy allows reattempts. If the message still fails after the limit, the system can move the message to a DLQ for investigation.
- Logs and metrics record the correlation ID, processing time, retry count, and errors. Do not log sensitive data or secrets.
- The development team monitors backlog count, oldest message age, error rate, concurrency, throttling, and the cost of the entire flow.

This example shows that the provider reduces the burden of server operations, but business correctness, access permissions, and resilience still must be designed in the application.

## 8. Pre-Production Checklist for a Function

- [ ] Trigger, event structure, and who is allowed to invoke the function are defined.
- [ ] Function has least-privilege permissions to access required services.
- [ ] Data and state needing long-term retention are stored in an appropriate service.
- [ ] Timeouts, retries, DLQ, and error event handling are defined.
- [ ] Operations that may be repeated have idempotency mechanisms.
- [ ] Cold starts, concurrency, quotas, and downstream service limits have been checked.
- [ ] Logs, metrics, alerts, and error investigation procedures are ready.
- [ ] Backups, recovery, data protection, and network configuration have been reviewed.
- [ ] Costs have been estimated for the function as well as gateway, queue, storage, database, and logs.

## Self-Check

1. Why does "serverless" not mean "no servers"?
2. For a Java function invoked from a queue, which layers does the cloud provider manage and what must the development team configure?
3. Why should exclusive business state not be stored in a function's global variables?
4. If a message can be redelivered, how should idempotency be designed to avoid creating an order twice?
5. Which components beyond function execution time can increase the cost of a serverless system?

If you can answer these questions, you have grasped the fundamental responsibility boundaries of serverless. Topics such as triggers, permissions, state, retries, idempotency, cold starts, scaling, and cost will be applied more deeply when designing and implementing real Java functions.
