# Comparing Serverless with Virtual Machines, Containers, and Kubernetes

When deploying a Java application, a development team can run the application on a virtual machine (VM), package it into a container, orchestrate containers with Kubernetes, or deploy serverless functions. All of these options bring source code into a real runtime environment, but they place operational responsibilities in different places.

In the **CLOUD_SERVERLESS** module, the focus is the serverless model, especially Function as a Service (FaaS): a Java function invoked by an HTTP request, message, or event. To decide when FaaS is appropriate, you need to understand how it differs from VMs, containers, and Kubernetes in terms of deployment unit, control, scalability, state, latency, and cost.

## 1. Four Concepts Solving Different Layers of Problems

### Virtual Machine (VM)

A virtual machine emulates a complete computer on physical hardware or a virtualization platform. Each VM typically has a guest operating system, allocated CPU and memory, storage disks, and dedicated networking. The operations team has extensive control over the OS, processes, system libraries, network ports, and how the application runs.

In return, the team must manage a lot: provisioning and configuring VMs, updating the OS, patching vulnerabilities, installing the JDK, monitoring resources, configuring load balancing, scaling machine counts, and handling failed machines. A Spring Boot application can run as a long-lived process on a VM and continue serving requests even when traffic is absent.

### Container

A container packages an application together with its required libraries and configuration into an image that can be deployed consistently across environments. Containers typically share the host OS kernel, making them lighter than VMs and faster to start in many scenarios. For Java, an image can contain the JAR, an appropriate JRE, and the command to launch the application.

Containers solve packaging and consistency well, but by themselves they do not solve all operations. You still need an environment to run containers, allocate CPU and memory, manage networking, replace failed instances, scale replica counts, store logs, and roll out new versions. That environment could be a single server, a managed container service, or Kubernetes.

### Kubernetes

Kubernetes is a container orchestration platform. Operators declare a desired state—for example, that an application needs three replicas, each with specific resource limits, exposed via a Service. Kubernetes continuously reconciles actual state with desired state: scheduling Pods onto nodes, restarting failed containers, replacing Pods, supporting rolling updates, and scaling based on configuration.

Kubernetes is not a packaging format that replaces containers. In common deployments, containers are the execution unit while Kubernetes manages the lifecycle and connectivity of those units. Even when using a managed Kubernetes service, the team still needs to understand and operate workloads, resource configurations, access permissions, networking, storage, autoscaling, observability, and cluster costs.

### Serverless and Function as a Service (FaaS)

Serverless is a service delivery model in which the cloud provider takes on most of the provisioning and operations of the underlying infrastructure. "Serverless" does not mean applications do not run on servers; it means developers do not directly manage servers for individual workloads.

With FaaS, the deployment unit is typically a function or a package of functions. A function is activated by a trigger such as an HTTP request, a message in a queue, a data change, or a scheduled event. The platform creates or reuses an execution environment, invokes the function, manages the number of concurrent execution instances, and can scale down to zero when there is no work. Cost is typically tied to invocation count, execution duration, and allocated resources, depending on the provider's pricing model.

FaaS significantly reduces server management work, but the application must adapt to the function execution lifecycle. An invocation may run in a new environment or a reused one; memory and local disk should not be treated as places for long-term state. Execution time, memory, concurrency, deployment package size, and execution duration are also subject to per-platform limits.

## 2. Quick Comparison

| Criterion | Virtual Machine (VM) | Container | Kubernetes | Serverless FaaS |
|---|---|---|---|---|
| Deployment unit | Machine and guest OS, then the application | Image containing the application and dependencies | Container workloads, typically declared via Deployment/Job | Function or function package with trigger configuration |
| Who manages the servers? | Operations team or VM provider at the infrastructure layer | Operations team or container service managing host machines | Operations team or provider managing control plane/nodes | Cloud provider manages execution infrastructure |
| Environment control | Very high | High at the image level; depends on runtime environment | High for workloads and cluster configuration | More limited; runs within platform runtime and limits |
| Application lifecycle | Usually a continuously running process | Containers typically run continuously or per task | Pods maintained according to declared state | Function runs on trigger; environment may be reused |
| Scaling | Typically configures VMs, autoscaling groups, and load balancers | Increases container counts via tooling or container runtime services | Built-in orchestration and autoscaling mechanisms | Platform automatically adjusts execution instances to load within quota limits |
| When idle | VMs typically remain provisioned | Containers or host machines may remain running | Nodes and workloads typically still consume resources | Can scale to zero if configuration and service type support it |
| State | Can use local disk and long-lived processes, but requires HA/backup design | State should generally be kept outside containers | Can use volumes, databases, or external services | State should be stored in external databases, object storage, or durable services |
| Operational work | OS, patching, networking, deployment, scaling, monitoring | Image, runtime, host, networking, deployment, and scaling | Cluster, nodes, workloads, policies, networking, storage, and observability | Triggers, permissions, function config, limits, retries, logs, and supporting services |
| Typical billing model | VM resources over provisioned time, plus storage and networking | Host machines or container resources over time, plus storage and networking | Nodes/cluster and companion services over time, plus workload resources | Invocation count, duration, resources, and related services |

The table above describes general tendencies. Managed services can shift operational responsibilities and billing models; for example, a container service can scale to zero automatically, while a FaaS service can allow configuring minimum instances to reduce latency.

## 3. Key Architectural and Operational Differences

### Deployment Unit and Control

With VMs, teams typically deploy an application or multiple processes onto a machine with an installed OS and runtime. Teams can make deep system configuration changes, but they bear responsibility for more layers.

With containers, teams shift focus to the image: the image must contain the right JRE, application, and dependencies. The same image can run on a laptop, a server, a container service, or Kubernetes if environments are compatible. Still, who provides the runtime host and handles failed containers remains a separate question.

With Kubernetes, teams describe how workloads should behave: replica counts, resources, health checks, deployment configurations, Services, and scaling policies. The platform orchestrates fulfilling those declarations. High control comes with a larger set of concepts and components to understand.

With FaaS, teams focus on function code, runtime configuration, triggers, access permissions, and the services the function calls. The provider decides how execution environments are placed. This reduces infrastructure work but also limits customization of the OS, background processes, and execution lifetime.

### Scaling and Handling Traffic Spikes

An application running on VMs typically scales by increasing machine size or adding VMs, then distributing requests via a load balancer. Provisioning new machines and starting the application can take time; therefore, capacity planning or maintaining spare headroom is needed.

Containers allow scaling application replicas independently of the image. With Kubernetes, Deployments and Horizontal Pod Autoscalers can adjust replicas based on CPU, memory, or custom metrics. However, new Pods still require nodes with sufficient resources; if the cluster runs out of capacity, node scaling or pre-provisioned capacity is required.

FaaS can increase execution instances to handle many concurrent triggers without developers provisioning individual machines. This mechanism is convenient for uneven traffic and independent tasks. Scalability is not infinite: concurrency quotas, message ingestion rates, downstream limits, and target service limits can all become bottlenecks. If thousands of concurrent invocations simultaneously hit a database with a small connection limit, rapid FaaS scaling can overwhelm the database.

Therefore, autoscaling must be paired with load control. For message processing, you can cap concurrency, tune batch sizes, and control queue consumption rates. For HTTP, set timeouts, rate limits, and protect supporting services. Never equate "auto-scaling" with "no need to design system capacity."

### Lifecycle, State, and Data Durability

VMs and containers can run processes for long periods. Applications can keep caches or connection pools in process memory, though critical data still needs durable storage and recovery mechanisms when a machine or container is replaced.

Kubernetes Pods can also be recreated or moved across nodes. In-container memory is not a durable data store. If files must be stored, teams must choose appropriate volumes or off-cluster storage services and clearly understand backup, recovery, and availability policies.

FaaS functions typically have short lifecycles, and an execution environment can be shut down at any time after processing completes. An environment may be reused across invocations, so global variables can help reuse objects or connection pools in some cases. However, you must not rely on the environment remaining alive, nor use global memory or temporary files as an authoritative data source. Store business state in an appropriate database, object storage, cache, or durable service.

### Retries, Duplicate Errors, and Idempotency

In continuously running systems, teams typically decide retry behavior at the application, queue, or client layer. With FaaS, the platform may automatically retry certain asynchronous event types according to service policy. Behavior differs across triggers and providers: synchronous HTTP, queues, and event buses may have different rules for timeouts, retries, visibility timeouts, and dead-letter queues.

A message can be redelivered when a function times out, an environment fails, or processing acknowledgment does not complete. Therefore, event-handling functions should be idempotent: processing the same event multiple times still produces the exact business effect once. You can use an event ID as a deduplication key, unique constraints, a processed-events table, or conditional updates. For message batches, understand partial-batch failure reporting mechanisms to avoid reprocessing an entire batch when only one item fails.

Retries need bounds and appropriate backoff. Invalid data errors usually do not resolve on retry; route those messages to a dead-letter queue or error-handling flow for investigation. If retries happen too fast or too many times, a failure in a supporting service can amplify into an even larger load spike.

### Cold Starts and Latency

Long-running VMs and containers can respond to requests once the process has started. New VMs or new containers still have startup time, but teams usually control when startup occurs and can maintain minimum replica counts.

With FaaS, when the platform needs to create a new execution environment, a request may have to wait for runtime loading, Java class loading, library initialization, and startup code execution. This extra delay is commonly called a cold start. Java can be affected by deployment package size, number of dependencies, work inside static initializers, and the framework being loaded.

Not every invocation experiences a cold start; the platform can reuse already initialized environments. Even so, do not assume environments are always warm. You can reduce impact by keeping deployment packages lean, avoiding unnecessary heavy initialization, measuring actual timings, and using features like provisioned concurrency or runtime snapshots if supported by the provider and permitted by budget. Weigh cold starts against user latency requirements rather than optimizing before measuring.

## 4. Example: Same Java Business Logic Across Four Models

Suppose a system needs to receive an `OrderPaid` event and update an order's status.

| Model | Possible deployment approach |
|---|---|
| VM | Run a long-lived Java application on a VM. The application receives HTTP requests or consumes the queue itself, keeps shared components in-process, and is updated and monitored by the operations team. |
| Container | Package the Java application into an image. Run one or more containers on a host or container service; configure restarts, health checks, and replica counts on the runtime platform. |
| Kubernetes | Put the image into a Deployment or an appropriate workload. Declare replicas, resources, probes, Service, and autoscaling; run a queue consumer in a Pod or an API receiving events. |
| Serverless FaaS | Deploy a Java function triggered when the queue receives `OrderPaid`. The platform invokes the function per message, adjusts concurrency, and applies configured retry policies. |

Business logic should be kept in a Java class that can be tested independently. Each model's adapter is responsible for translating HTTP requests or messages into business calls. Example illustrating the core:

```java
public final class OrderService {
    private final OrderRepository orders;

    public OrderService(OrderRepository orders) {
        this.orders = orders;
    }

    public void markPaid(String orderId, String eventId) {
        // The repository performs a conditional update or records the eventId
        // so that redelivery of the same event does not produce duplicate side effects.
        orders.markPaidIfNotProcessed(orderId, eventId);
    }
}
```

On a VM or container, an HTTP controller or queue consumer typically calls `OrderService` inside a long-lived process. On Kubernetes, the same application can run inside Pods and be orchestrated via workload configuration. On FaaS, a handler receives the payload passed by the platform, validates the data, calls `OrderService`, and returns a result or throws an error so the trigger applies its corresponding policy.

The handler skeleton below only illustrates the boundary between adapter and business logic; exact event types, handler signatures, and context APIs depend on the FaaS provider:

```java
public final class OrderPaidFunction {
    private final OrderService orderService;

    public OrderPaidFunction(OrderService orderService) {
        this.orderService = orderService;
    }

    public void handle(OrderPaid event, FunctionContext context) {
        validate(event);
        orderService.markPaid(event.orderId(), event.eventId());
    }

    private void validate(OrderPaid event) {
        if (event == null || event.orderId() == null || event.eventId() == null) {
            throw new IllegalArgumentException("Invalid OrderPaid event");
        }
    }
}
```

This snippet is not a handler that compiles directly for every cloud provider. In real deployments, you must use the platform's proper interfaces and adapter libraries, configure triggers, timeouts, memory/CPU, permissions to call databases and queues, error responses, and appropriate idempotency mechanisms.

The example also highlights an important point: moving from containers to FaaS does not automatically change the business logic. The major changes lie in how the application is triggered, process lifecycle, configuration and connection management, error handling, resource limits, and operational observability.

## 5. Comparing Costs Properly

You cannot conclude that FaaS is always cheaper than VMs or Kubernetes just because it only charges when the function runs. You must calculate the total cost of the workload and how the workload is used.

- **VM:** typically pays for CPU, RAM, and machine capacity for the duration the VM is provisioned, even at low load. Cost can be predictable under steady load; the team must also factor in storage, backups, data transfer, load balancers, and operational effort.
- **Container:** cost depends on where it runs. If self-managing servers, cost is close to VMs; if using a container service billed by task or resources, the bill is based on configuration and runtime. Image registries, logging, networking, and supporting services also contribute to total cost.
- **Kubernetes:** beyond workload CPU/RAM resources, you must account for nodes, control plane if billed, storage, load balancers, logs/metrics, add-ons, and operations team time. A cluster can be shared across workloads, yet management overhead and spare capacity still exist.
- **FaaS:** typically bills by invocation count, duration, and configured memory or CPU; there may be charges for provisioned concurrency, logs, data transfer, API gateways, queues, databases, and integrated services. Scale-to-zero reduces cost when idle, but high, continuous load can make cost per unit of work higher than a steadily running service.

When estimating, use real measurements or traffic scenarios: monthly requests/events, average and high-percentile processing duration, memory/CPU, error and retry rates, idle time, network traffic, storage capacity, and required redundancy. Compare at the same availability level and performance requirements. Also include development, on-call operations, upgrade, and incident-response costs.

## 6. When Should You Choose Each Model?

| Scenario | Typically suitable choice | Rationale and considerations |
|---|---|---|
| Legacy application needing a custom OS, dedicated agents, or long-lived processes | VM | High environment control; in return, the team owns patching and machine operations. |
| Wanting consistent application packaging across dev, test, and production | Container | Images make runtime and dependencies explicit; you still need to choose the runtime host and orchestration. |
| Having multiple container services needing coordinated deployment, service discovery, policies, and custom autoscaling | Kubernetes | Strong orchestration ecosystem; requires cluster operations capability and complexity management. |
| Short, independent tasks triggered by HTTP, queues, or events with fluctuating traffic | Serverless FaaS | Reduces server management and can scale to zero; must design for runtime limits, retries, idempotency, and cold starts. |
| Continuously running background work, needing long-lived connections or long-running stream processing | Container, Kubernetes, or VM | A long-lived process model may fit better; some serverless platforms support longer tasks, though specific limits must be checked. |
| Steady, high load most of the time needing predictable performance | VM, container, or Kubernetes | Always-on capacity can be more economical and easier to control; compare via benchmarks and actual bills. |

These options are not mutually exclusive. A system can run its main API on Kubernetes, use FaaS for image processing after upload, store data in a managed database, and pass messages via queues. It can also use VMs for components requiring OS control and FaaS for event-driven tasks. Boundaries should be drawn based on the characteristics of each workload.

## 7. Misconceptions to Avoid

1. **"Serverless has no servers."** Code still runs on server infrastructure; the provider is responsible for managing most of that infrastructure.
2. **"Container means Kubernetes."** A container is a way to package and isolate processes; Kubernetes is a container orchestration platform. You can run containers without Kubernetes.
3. **"Kubernetes and serverless are technologies at the same layer."** Kubernetes primarily solves workload orchestration; FaaS provides an invocation- or event-based execution model. Some serverless platforms are built on top of containers or Kubernetes underneath.
4. **"FaaS automatically handles all failures."** The platform may retry according to policy, but the application still needs idempotency, timeouts, dead-letter queues, observability, and handling for malformed data.
5. **"Scale-to-zero is always optimal."** It saves idle resources but can introduce cold starts. With continuous traffic or strict latency requirements, keeping instances ready or using an always-on model may make more sense.
6. **"A re-run function will always receive exactly one message."** Many event mechanisms provide at-least-once delivery semantics or possible redelivery. Design for safe duplicate handling and check the semantics of the specific trigger.
7. **"Not managing servers means no operations needed."** You still must manage IAM permissions, secrets, configuration, quotas, concurrency, logs, metrics, alerts, retries, and costs.

## 8. Decision Workflow

When choosing a deployment model for a Java service, you can walk through these questions:

1. **How is the workload triggered?** If primarily by HTTP requests or discrete events from queues/event buses, FaaS is a strong candidate. If it requires an always-on process, long-lived connections, or long-running tasks, look at containers, Kubernetes, or VMs.
2. **Do execution time and resources fit within platform limits?** Compare timeouts, memory, CPU, artifact size, concurrency, and quotas against provider limits.
3. **Can state be decoupled from the process?** If sessions or durable data must live in local memory/disk, redesign with external stores or consider a long-lived workload.
4. **Can the system tolerate retries and duplicate delivery?** Clarify delivery semantics, timeouts, and dead-letter handling; add idempotency before increasing concurrency.
5. **Is startup latency acceptable?** Measure cold starts and high-percentile latency, especially with Java and frameworks that have significant initialization time.
6. **Can supporting services handle concurrent load?** Check connection limits, throughput, and quotas of databases, external APIs, and queues; set concurrency limits or backpressure where needed.
7. **Do total cost and team capabilities align?** Compare both infrastructure and operational costs at the same load, availability, and security requirements.

If the answers show the workload is short, independent, event-triggered, minimally reliant on in-process state, and able to handle retries safely, FaaS is often a good choice. If the workload needs OS control, long-lived processes, dedicated resources, or predictable performance at high load, VMs or containers may be a better fit. Kubernetes is worth considering when an organization needs to orchestrate many container workloads and has the capability to operate that platform.

## 9. Conclusion

VMs grant control over virtualized machines; containers standardize application packaging; Kubernetes orchestrates container lifecycles; serverless FaaS provides a way to run functions on triggers without the team managing execution servers themselves. Each model has its own strengths and costs.

For Java applications, decisions should start from workload characteristics: triggers, processing duration, state, latency requirements, retry behavior, traffic patterns, and supporting service limits. When those factors align with event-driven execution, FaaS reduces infrastructure burden. When long-lived processes or deep control are needed, VMs, containers, or Kubernetes may be the better fit.
