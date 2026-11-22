# Resource inventory and identifying the component responsible for management

When preparing a Java application for CRaC (Coordinated Restore at Checkpoint), the development team needs to know which resources the process is holding and which component is responsible for managing each resource. An application can use dozens of libraries, frameworks, and external clients. Each component can create sockets, connection pools, background threads, file handles, timers, caches, or environment-dependent state. If a resource is missed, the application may restore successfully at the process level but fail when handling the first request.

**Resource inventory** (*resource inventory*) is the process of creating a structured list of resources and state that affect checkpoint/restore. **Identifying the owner** is associating each item in the list with the component that has sufficient knowledge and control to prepare the resource before checkpoint, recover it after restore, and verify that it works.

The owner can be an application bean, an adapter written by the development team, a library, a framework, or a platform component. What matters is that responsibility must be clear: who stops using the resource, who closes or releases it, who recreates it, and who prevents the application from receiving traffic when recovery is not yet complete.

## 1. Why must resource inventory be done before using CRaC?

A checkpoint saves the state of a process at a point in time. Some state in the heap can continue to be used after restore, but many resources tied to the operating system or external services may have expired, changed, or are not allowed to be reused. For example, a TCP connection may be closed by the peer, a token may expire, DNS may change, or a background thread may be holding an unfinished transaction.

Without a resource list, teams often only discover issues after restore: the first request encounters a database error, a worker does not receive messages, the HTTP port cannot bind, or a scheduler runs twice. These errors are hard to trace if it is unknown which component created and owns the resource.

An inventory helps the team:

- Know which resources the application is opening or holding, including resources created indirectly by libraries.
- Distinguish state that can be retained from state that needs to be closed, refreshed, or recreated.
- Assign responsibility to the right component, avoiding multiple components closing or initializing the same resource.
- Determine the coordination order between interdependent components.
- Design CRaC callbacks that are controllable, observable, and testable.
- Create post-restore readiness criteria based on essential resources.

Inventory is not just counting sockets or threads. A value in memory also needs to be examined if it contains environment-dependent or time-limited information, such as tokens, instance addresses, timestamps, leases, or random number generator state.

## 2. Resources and state to include in the inventory scope

A useful approach is to divide the items to be inspected into groups. This categorization helps avoid focusing only on resources visible at the operating system level.

| Group | Examples | Risk on restore |
|---|---|---|
| Network connections | Socket, HTTP client, TLS session, database connection, broker channel | Closed connection, expired session, or changed endpoint |
| Files and operating system | File descriptor, file handle, temp directory, lock file, memory-mapped file | Path, mount, permissions, or handle state no longer valid |
| Threads and background execution | Executor, worker, thread pool, event loop | Thread processing halfway, holding a lock, or not resuming properly |
| Schedules and time | Timer, scheduler, deadline, lease, periodic task | Old schedule catching up or task triggered multiple times |
| Authentication data | Token, credential, secret, certificate | Expired, revoked, or no longer valid for the instance |
| Configuration and identity | Hostname, IP, port, instance ID, node metadata | Multiple instances sharing the same identity or stale configuration |
| Cache and metadata | DNS cache, business cache, ORM metadata, serializer cache | Expired or stale data, or needing synchronization across replicas |
| Synchronization state | Lock, semaphore, transaction, session, consumer offset | Unfinished state or no longer matching external service |
| Randomness source | PRNG state, seed, ID generator | Restored processes generating identical sequences or duplicate IDs |
| Native libraries | Native handle, C/C++ library context, GPU/device handle | Native resource without a lifecycle compatible with checkpoint |

Not every item in the table needs to be closed before checkpoint. Some only need verification, some need refreshing after restore, and some can be kept as is. The goal of the inventory is to determine the specific action based on the nature of the resource and the documentation of the component that creates it.

## 3. Distinguishing resources, in-memory state, and business data

These three concepts often overlap but need to be recorded separately.

**Runtime resource** is what the process uses to interact with the environment or perform work: socket, file handle, connection pool, executor, timer, or native handle. It usually has a clear creation, usage, and release process.

**In-memory state** is data residing in the heap or runtime structures. For example, caches, parsed configuration, counters, metadata, and object state. Part of it can be reused; part of it needs to be refreshed because it is stale or tied to the instance.

**Business data** is information meaningful to the system and usually must be stored in a durable source such as a database or message broker. A process checkpoint should not be treated as the primary storage mechanism for transactions or business work. If a request is in the middle of updating the database when a checkpoint occurs, it must be ensured that the transaction is completed or rolled back by design.

Example with an e-commerce application:

| Item | Classification | Question to answer |
|---|---|---|
| `HikariDataSource` | Runtime resource | Which component closes and recreates the pool? |
| Product code list in cache | In-memory state | Is the data immutable or still fresh after restore? |
| `instanceId` | Configuration/identity state | Does the value need to differ for each replica? |
| Order creation transaction | Business data | Has the transaction been committed or rolled back before checkpoint? |
| Scheduled executor | Runtime resource and schedule | Who stops the scheduler, who restarts it, and is there a risk of duplicate runs? |

Proper classification helps avoid a common mistake: trying to solve every problem by closing a Java object. There are cases that require refreshing data, cases that require synchronizing with external systems, and cases that require ensuring business consistency.

## 4. Who is the owner of a resource?

The owner is the component responsible for the entire lifecycle of the resource within the scope it controls. The owner needs to understand how the resource is created, who is using it, when it can be stopped, how to release it safely, and the conditions for recreating it.

The owner is not necessarily the place holding a reference variable to the resource. For example, a service may receive a `DataSource` via dependency injection but is not the owner of the connection pool if the pool is created and managed by infrastructure configuration or a library. The component that owns the pool is the one that understands how to close and recreate it.

Some common types of owners:

| Owner type | Examples | Typical responsibility |
|---|---|---|
| Application component | Service that opens files or creates an executor itself | Defines how to stop, close, and recreate the resource |
| Infrastructure/configuration component | Bean creating `DataSource`, HTTP client, or scheduler | Manages lifecycle of objects injected into multiple services |
| Library/framework integration | Driver, framework, or library with CRaC integration | Executes the vendor-supported procedure |
| Platform/orchestrator | Container runtime, secret provider, service discovery | Allocates or re-provides resources at the environment level |
| External service | Database, broker, API server | Manages server-side resources; the application must still manage its own clients and connections |

Assign one primary owner for each resource. Other components may be consumers or dependencies, but should not arbitrarily close a resource they are only using.

## 5. Principles for identifying the owner

### 5.1. Start from where the resource is created

Find where the API creating or opening the resource is called, such as `new`, `open`, `connect`, `build`, `start`, or a factory method. Record the component that creates it and where the reference is stored. This is usually the first clue to finding the owner.

However, the creation site is not always the final owner. A factory may transfer management authority to a container or framework. That handoff must be traced and the library's lifecycle contract read.

### 5.2. Identify who has the authority to stop usage

Closing a socket while multiple threads are still writing data can cause requests to fail. Stopping an executor while tasks are holding transactions can leave inconsistent state. Therefore, the owner needs to know the consumers and have a way to prevent them from starting new work before releasing the resource.

If the component that creates the resource cannot control the consumers, identify a coordinator responsible for quiescing the consumers first. The coordinator orchestrates the order; the resource owner still performs the close and reopen operations.

### 5.3. Prefer built-in CRaC integrations

Some frameworks, drivers, or libraries already provide CRaC integration. In that case, the library may register the resource itself and manage internal details that the application should not interfere with. Verify the version and scope of support. Do not register a second resource to close the same resource if the library integration already manages it.

If the library does not have integration, the application team can write an adapter or wrapper to coordinate the lifecycle. The adapter should use the library's public API and keep responsibility in one place.

### 5.4. Separate the owner from the coordinator

In a large application, a central component may need to coordinate multiple resources. The coordinator is responsible for starting the preparation process and determining when the system is eligible for checkpoint. Each owner is responsible for the details of its own resource.

For example: the coordinator tells the HTTP server to stop accepting requests, tells consumers to stop receiving messages, waits for in-flight transactions to complete, and then tells the owners to close connections. The coordinator should not close individual internal sockets itself without understanding the contracts of the libraries.

## 6. Identifying the owner in a real-world Java application

A good inventory usually combines multiple search methods. You should not just read the source code because some resources are created automatically by frameworks or native libraries.

### 6.1. Read startup configuration and dependency injection

Inspect configurations that create beans, factories, clients, and pools. With Spring, look at `@Configuration` classes, `@Bean`, initialization components, lifecycle methods, and auto-configuration. Identify which beans are created, the bean scope, and who closes the bean on context shutdown.

Example:

```java
@Configuration
public class ClientConfiguration {

    @Bean(destroyMethod = "close")
    public ExternalClient externalClient() {
        return ExternalClient.builder().build();
    }
}
```

In the example, `ClientConfiguration` creates and registers the bean; the container manages the bean lifecycle according to the configuration. `ExternalClient` is the created object. When integrating CRaC, it is necessary to determine which component can close and recreate the client, and how the services using the client are coordinated during the checkpoint/restore phase.

### 6.2. Find resource creation and release APIs

Search the source code for operations such as:

- `Socket`, `ServerSocket`, `SocketChannel`, `FileChannel`, `Files.new...`.
- `DataSource`, `Connection`, `HttpClient`, broker clients, and drivers.
- `ExecutorService`, `ScheduledExecutorService`, `Thread`, timers, and schedulers.
- APIs for opening files, native libraries, devices, or memory-mapped resources.
- `close()`, `shutdown()`, `stop()`, `disconnect()`, `dispose()`, and similar methods.

Cross-reference where resources are created with where they are released. If no close site is found, that is a sign to investigate. If multiple places close it, identify which place truly owns the lifecycle and eliminate overlapping management.

### 6.3. Read library and framework documentation

A framework may create resources internally that application code does not call directly. For example, a web server creates listening sockets and event loops; an ORM creates connection pools or metadata caches; a messaging library creates heartbeat threads and network channels.

Read the documentation for the exact dependency version to determine:

- Which resources are created automatically.
- How the framework manages the lifecycle.
- Whether there is an official CRaC integration.
- Which versions are supported and what limitations exist.
- How to enable/disable the integration or register callbacks as recommended.

Do not infer CRaC capability from a library having a `close()` method. Being able to close resources on shutdown does not mean the library fully supports checkpoint/restore.

### 6.4. Observe resources at runtime

When possible, run the application in a test environment and observe what the process is holding. Use operating system tools and JVM tools to inspect threads, sockets, file descriptors, stack traces, startup logs, and library activity.

Observation sources may include:

- Thread dumps to find workers, schedulers, event loops, and waiting threads.
- JFR or a profiler to understand thread activity, I/O, and allocations.
- Operating system tools to list sockets, file handles, PIDs, and resource limits.
- Startup/shutdown logs of frameworks and drivers.
- Metrics from connection pools, broker clients, executors, and HTTP servers.

A runtime snapshot only reflects the state at the time of observation. Observe at startup, after warm-up, under load, and before checkpoint to detect resources that only appear when a business path is invoked.

## 7. Resource inventory template

An inventory table needs enough information for someone else to understand the resource, its owner, and the actions to take. The template below can be used as a starting point:

| Field | Content to record |
|---|---|
| Resource ID | Unique identifier in the inventory document |
| Resource/type | Type of resource or state to manage |
| Creator | Component or library that creates the resource |
| Owner | Component responsible for the lifecycle |
| Consumers | Components that are using the resource |
| Scope | Process-wide, per-instance, per-request, or per-task |
| Lifetime | When created, when invalidated, and when closed |
| External dependency | Related service, file, endpoint, or device |
| Before checkpoint | Stop, drain, flush, close, keep as is, or not applicable |
| After restore | Recreate, refresh, verify, or not applicable |
| Ordering/dependency | Resources or components that must be ready before/after |
| Failure behavior | Behavior when closing/reopening fails |
| Verification | Log, metric, health check, or verification test |

Example of a partial inventory for a Java service:

| Resource ID | Creator / Owner | Before checkpoint | After restore | Verification |
|---|---|---|---|---|
| `db-pool` | Database configuration / `DataSource` owner | Stop issuing new connections, wait for tasks to finish, close pool per integration | Create new pool and check database | Pool active, test query succeeds |
| `http-server` | Web framework / server lifecycle owner | Stop accepting requests, drain in-flight requests, handle listening socket per integration | Restore server/listener via supported mechanism | Readiness endpoint and test request succeed |
| `broker-consumer` | Messaging configuration / consumer owner | Pause, process or roll back in-flight messages, close client if needed | Create new client, subscribe or join group | Consumer active and offset valid |
| `scheduler` | Scheduling configuration / scheduler owner | Stop new triggers, wait for tasks to complete, stop scheduler | Create schedule per instance/leader policy | Running job count metric and leader status |
| `instance-config` | Runtime configuration component | Do not save identity specific to the preparation process | Read new instance ID, address, and secrets | Verified identity and configuration logs |
| `local-cache` | Cache component | Keep base cache or flush per policy | Refresh TTL-bound or per-instance entries | Hit/miss, timestamp, and data validity |

This is only an illustrative example. Actual owners must be determined from the application structure and the contracts of the libraries in use. Do not copy component names from the table into your system without confirming they exist.

## 8. Evaluating actions for each resource

After identifying the owner, choose a concrete action. A simple classification consists of four groups:

| Strategy | When appropriate | Examples |
|---|---|---|
| Keep as is and verify | State valid across checkpoint, not tied to changing environment | Parsed immutable metadata |
| Close before, recreate after | Resources dependent on sockets, peers, or current environment | Database connection, HTTP client with network connections |
| Keep but refresh data | Object still usable but contains time-limited data | DNS cache, token, dynamic configuration |
| Stop and restart | Background execution component needing to restart in a clean state | Scheduler, consumer, worker pool |

Some resources require multiple actions. For example, a consumer must pause, wait for in-flight messages, commit offsets, close the client, and then create a new client and subscribe after restore. Specifying each step helps avoid vague descriptions like "reset consumer".

Do not close a resource just because it appears in the inventory. Closing at the wrong time can lose requests, transactions, or unflushed data. The owner needs a quiesce procedure before calling the close operation.

## 9. Identifying dependencies and coordination order

Resources often have dependency relationships. A request handler uses a service; the service uses a repository; the repository uses a connection pool. A scheduler may call a service and write to the database. If the database pool is closed before the scheduler stops running, the scheduler may continue calling into the closed pool.

Therefore, the inventory should also record dependency relationships:

```text
HTTP Server
    |
    v
Request Handler
    |
    v
Application Service
    |
    v
Repository ---------> Database Pool ---------> Database

Scheduler ----------> Application Service
Broker Consumer ----> Application Service
```

When preparing for a checkpoint, the system typically stops work-generating sources first (HTTP server, consumer, scheduler), waits for in-flight work to finish, and only then closes the dependencies they use (pools, clients, file handles). On restore, dependencies need to be ready before work sources are reopened.

The actual order depends on the framework, resource registration, and callback mechanism of the CRaC version in use. You should not assume callback ordering between resources without checking the API documentation. If ordering matters, use a coordinator or supported context structure to represent the relationship, and test the actual order.

## 10. Registering a CRaC resource and assigning responsibility

The CRaC API provides `org.crac.Resource` for the resource-managing component to implement callbacks before checkpoint and after restore. `Core.getGlobalContext().register(...)` is one way to register a resource with the global context in environments supporting the corresponding API.

Example of an owner managing a file that needs to be closed and reopened:

```java
import org.crac.Context;
import org.crac.Core;
import org.crac.Resource;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

public final class FileResource implements Resource {
    private final Path path;
    private java.io.BufferedReader reader;

    public FileResource(Path path) throws IOException {
        this.path = path;
        this.reader = Files.newBufferedReader(path);
        Core.getGlobalContext().register(this);
    }

    @Override
    public void beforeCheckpoint(Context<? extends Resource> context)
            throws Exception {
        if (reader != null) {
            reader.close();
            reader = null;
        }
    }

    @Override
    public void afterRestore(Context<? extends Resource> context)
            throws Exception {
        reader = Files.newBufferedReader(path);
    }
}
```

The example only illustrates a simple file reader. In a real application, the owner needs to decide where to resume reading, how to handle unconsumed data, file permissions after restore, and cases where the file has changed or no longer exists. If the file is read-only data, it can be reopened from the beginning; if it is a stream with an offset, the offset must be persisted durably and consistency verified.

Each resource should be registered exactly once per process. If a bean is created multiple times or the context is initialized repeatedly, duplicate registration must be avoided. If a library already registers its own resource, the application should not create a second wrapper closing the same resource without a clear coordination design.

## 11. Handling resources shared across multiple components

A resource can be used by multiple components. For example, multiple services sharing one `DataSource`, multiple handlers sharing one HTTP client, or multiple tasks using one executor.

In this case, the owner is usually the component that creates and manages the shared resource. Consumers only borrow the resource under a contract. On checkpoint, the owner cannot close the resource immediately if consumers are still using it.

One way to organize responsibilities:

| Role | Responsibility |
|---|---|
| Consumer | Stop starting new work and finish in-flight work |
| Coordinator | Ask consumers to quiesce, track status, and orchestrate the checkpoint phase |
| Resource owner | Confirm no active consumers remain, close or prepare the resource |
| Restore coordinator | Initialize dependencies in order and only reopen traffic when conditions are met |

Do not let each consumer close the same `DataSource` itself. That easily leads to duplicate closes, race conditions, or one consumer breaking another consumer's operation. There must be a single entity managing the lifecycle of a shared resource.

If a resource can be recreated quickly and independently, you may choose a design where each component owns its own client. However, that choice must weigh connection costs, service limits, and pooling requirements.

## 12. Handling resources created automatically by libraries or frameworks

A large portion of resources in a Java application do not appear directly in business source code. Frameworks can create server sockets, event loops, thread pools, reflection caches, connection pools, or internal clients.

For each important library, record:

1. The version in use and supported CRaC integration features.
2. Which resources the library creates automatically and their scope.
3. Which component owns the lifecycle according to the library's design.
4. How the library requires handling before checkpoint and after restore.
5. Known limitations, such as not supporting a type of native handle or requiring additional configuration.

If an official integration exists, use the exact version and recommended configuration. If not, look for public lifecycle APIs or consult the vendor's documentation before writing an adapter. Avoid accessing private fields, reflecting into internals, or calling unsupported methods just to force-close a resource.

Frameworks may also manage beans according to their own lifecycle. If CRaC integration is integrated with the container, let the container manage the right beans and dependency order. If registering callbacks outside the container yourself, ensure that the beans still exist and are ready when the callbacks run.

## 13. Questions to answer when inventorying each item

To prevent the inventory from being just a list of names, answer a consistent set of questions for each resource:

**Creation and ownership:** Who creates the resource? Who is the primary owner? Is ownership transferred to a framework or container? Which components are using it?

**Scope and lifecycle:** Is the resource process-wide, per-instance, per-request, or per-task? Is it created at startup, on first use, or on a schedule? What invalidates it?

**Checkpoint:** Can the resource survive across a checkpoint? What needs to stop consumers, drain, flush, commit, close, or release? Is there unfinished work or any lock being held?

**Restore:** Who recreates the resource? What specific configuration or identity is needed? Can the resource be recreated repeatedly and safely? Are there rate limits or quotas on the external service?

**Errors and readiness:** If closing or reopening fails, how does the application handle it? Are there retries and timeouts? Which metrics or health checks prove the resource is ready? Is the application blocked from receiving traffic when essential resources are not yet operational?

**Testing:** Can connection loss, token expiration, missing files, occupied ports, or callback errors be simulated? How do you prove there are no duplicate side effects?

## 14. Process for conducting a resource inventory

A practical process can be divided into the following steps.

### Step 1: Define the application scope

List modules, frameworks, client libraries, external services, and background components. Start with critical flows such as HTTP requests, database, messaging, scheduled jobs, and file processing. Also record features that only run under load.

### Step 2: Gather evidence

Read configurations, factories, lifecycle methods, dependency documentation, and resource creation code. Combine with observing threads, sockets, file descriptors, and metrics while the application is running. Clearly note the source of evidence for each item so others can verify.

### Step 3: Identify owners and consumers

For each resource, trace back where it is created and where it is closed. List consumers, determine who can stop usage, and who has sufficient knowledge to recreate it. If there are multiple owner candidates, clarify responsibility boundaries before writing callbacks.

### Step 4: Classify checkpoint/restore actions

Choose keep as is, close then recreate, refresh data, or stop then restart. Specify preconditions before execution and behavior on error. Mark items that need verification with the library vendor.

### Step 5: Map dependencies and identify the coordinator

Represent work-generating components, resource-consuming components, and dependencies. Determine the order for quiescing, closing, recreating, and opening traffic. Choose a coordinator if multiple components need to coordinate.

### Step 6: Implement integration and test

Register resources according to supported APIs and frameworks. Test callbacks, callback failures, multiple restores, and scenarios where external services change. Check both logs and metrics to confirm behavior.

### Step 7: Maintain the inventory

The resource inventory needs to be updated when adding dependencies, upgrading frameworks, changing connection pools, adding workers, or changing deployment methods. Updating the inventory can be included in the review process for changes affecting the lifecycle.

## 15. Example inventory for a Spring Boot application

Suppose a Spring Boot service has an HTTP server, database, Redis cache, Kafka consumer, and scheduled job. The initial inventory can be organized as follows:

| Resource | Typical creation site | Owner to verify | Expected action |
|---|---|---|---|
| HTTP server and listening socket | Embedded server initialized by Spring Boot | Web server lifecycle integration | Drain requests and handle socket per CRaC integration |
| JDBC connection pool | Auto-configuration or datasource configuration bean | Datasource/pool bean | Close pool before checkpoint, create new pool after restore |
| Redis client | Cache/client configuration bean | Redis client bean or library with CRaC integration | Close old connections, create new client/connections if needed |
| Kafka consumer | Listener container | Messaging framework/container | Pause, finish messages, restore subscription |
| Scheduled job | Spring scheduling or custom scheduler | Scheduling component | Stop triggers, start according to leader/instance policy |
| Application thread pool | Executor bean | Executor bean | Drain, controlled shutdown, create new executor |
| Secret/token | Secret provider or auth client | Configuration/credential component | Fetch or refresh credentials after restore |
| Cache metadata | Cache manager and application | Cache component | Keep immutable part, refresh TTL-bound or per-instance part |

You cannot conclude the owner solely from a bean or framework name. Some versions have official CRaC integration; other versions may require configuration or adapters. Check the exact versions of Spring Boot, drivers, and libraries used in the application.

One way to organize is to create a responsibility table for teams:

| Area | Technical owner | Evidence to hand over |
|---|---|---|
| Web and request lifecycle | Team owning the web layer | How requests are drained, server state after restore |
| Database and cache clients | Team owning persistence/infrastructure | How pools are closed/opened and connections verified |
| Messaging | Team owning consumer/producer | Pause procedure, offsets, and resubscription |
| Background jobs | Team owning scheduler/worker | Leader rules, idempotency, and restart |
| Runtime configuration | Team owning configuration and secrets | How new identity, tokens, and endpoints are provisioned |

Assigning an owner within the team helps ensure the inventory is maintained. In the source code, the owner should still be expressed through concrete components and lifecycle boundaries, not just individual names in documentation.

## 16. Criteria for completing the inventory

An inventory can be considered sufficient for the integration phase when:

- Important modules and dependencies have been reviewed, including automatically created resources.
- Each resource has a clear creator, owner, and consumers.
- Scope, lifecycle, and environment dependencies are recorded.
- Actions before checkpoint and after restore are defined.
- Shared resources have a single clear lifecycle owner.
- Dependencies and quiesce/restore order are represented.
- There is handling for callback failures and readiness criteria.
- There is concrete verification via logs, metrics, health checks, or integration tests.
- Unclear items are recorded as questions to confirm with the vendor or library owner.

There is no need to wait for every item to be perfect before starting experiments. You can mark the confidence level of each item: verified by documentation, verified by experiment, assumption to test, or undetermined. This approach helps the team prioritize major risks first.

## 17. Common mistakes

**Inventorying only resources created directly by application code.** Frameworks and libraries can create sockets, threads, caches, and native handles. Read dependency documentation and observe runtime.

**Assuming the place holding a reference is the owner.** A service may only use a `DataSource` managed by a configuration bean. Find where it is created, the lifecycle contract, and who has authority to close/open it.

**Letting multiple components close the same resource.** Duplicate closes can cause race conditions and unpredictable errors. Assign one primary owner; consumers only coordinate stopping usage.

**Ignoring active consumers.** Closing a pool or client while requests are still running can lose transactions. Quiesce and drain before releasing.

**Registering a CRaC Resource that duplicates the library's integration.** Two callbacks closing/opening the same resource can cause errors. Check whether the library already manages it before writing an adapter.

**Testing only successful callbacks.** Resources can fail to reopen due to network, quota, or secrets. Test timeouts, retries, partial failures, and readiness.

**Not updating the inventory after upgrading dependencies.** A new version may change the lifecycle or add integration. Treat dependency changes as a reason to review the related inventory.

**Recording overly generic owners.** "Application" or "JVM" does not help operators know which component to fix. Record the specific bean name, module, library, and responsibility.

## 18. CRaC resource inventory checklist

- [ ] Have sockets, file handles, pools, clients, threads, executors, timers, and native resources been listed?
- [ ] Have time-limited or instance-bound heap states been reviewed?
- [ ] Have resources created automatically by frameworks and dependencies been examined?
- [ ] Does each item have a creator, owner, and list of consumers?
- [ ] Does the owner have authority to stop consumers and control the resource lifecycle?
- [ ] Have before-checkpoint and after-restore actions been defined for each item?
- [ ] Has it been checked whether the library has official CRaC integration?
- [ ] Have duplicate callback registrations for the same resource been avoided?
- [ ] Have dependencies and quiesce/restore order been mapped?
- [ ] Are error handling, timeouts, retries, and readiness in place for essential resources?
- [ ] Are there logs, metrics, or tests proving the resource works after restore?
- [ ] Does the inventory have evidence sources, an owner, and an update date?

## Conclusion

Resource inventory is the foundational step for a Java application to checkpoint and restore in a controlled manner. The list needs to include operating system resources, service connections, background threads, configuration state, caches, credentials, and time-limited data. For each item, the team needs to know who creates it, who uses it, who owns the lifecycle, and what must happen before checkpoint as well as after restore.

When owners are clearly identified, CRaC callbacks can be placed at the right management boundaries. The coordinator orchestrates components to stop work and recover according to dependencies; owners perform the specific operations on their resources. An inventory with clear evidence, actions, and verification will help reduce restore errors, avoid overlapping management, and make the resource lifecycle easier to operate.
