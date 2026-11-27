# Designing Stateless Functions and Managing Dependencies

In a serverless architecture, a function can be launched to handle an HTTP request, a queue message, a file storage event, or a scheduled trigger. The platform may spin up multiple execution environments, reuse an environment across multiple invocations, pause it, or terminate it when demand drops. Therefore, function design must never assume a long-lived process, that one instance will always serve the same user, or that local memory is a durable data store.

Two foundational principles are **stateless execution** and **intentional dependency management**. Functions do not retain business state between invocations; required state is stored in an appropriate storage service or session management system. Libraries, connection clients, configurations, secrets, and external services are initialized, reused, and bounded according to the runtime's actual lifecycle.

This does not mean a function cannot use variables, allocate memory, or must recreate every object on every request. Execution environment memory remains useful for ephemeral data, optimization caches, and connection reuse while the runtime stays warm. However, that data can vanish, be shared across invocations in the same environment, or be absent in another environment. **Never use local state as the system of record or a correctness mechanism.**

This lesson belongs to the **Serverless Architecture** module of the cloud architecture track. The goal is to understand how to design applications from business requirements down to compute, data, networking, and operations, balancing trade-offs across reliability, security, scalability, cost, and controllability under the Well-Architected mindset.

After this lesson, you will be able to:

- Explain stateless functions and distinguish ephemeral runtime state from durable business state.
- Design functions that run across multiple replicas, handle duplicate events, and recover when execution environments terminate.
- Manage dependencies, SDK clients, connection pools, configurations, and secrets according to appropriate lifecycles.
- Control timeouts, retries, concurrency, idempotency, and downstream service limits.
- Design network access, observability, testing, and safe deployments for functions.
- Evaluate serverless function architecture across the six Well-Architected pillars.

## 1. What Does a Stateless Function Mean?

A stateless function does not rely on local state from a previous execution to process the current execution correctly. Each invocation receives the required inputs, validates and executes business logic, interacts with external state stores, and returns a result or emits subsequent events.

For example, the `CreateBooking` function receives `customerId`, `slotId`, and an idempotency key. It verifies permissions, checks slot availability, writes the booking to the database, and returns a booking ID. The "slot is booked" state lives in the database with appropriate transactions and constraints. If the next invocation runs in a completely different execution environment, the outcome remains correct.

Conversely, if the function stores booked slots only in a global variable or a temporary file on the execution environment's filesystem, another invocation may not see that data. Two concurrent invocations could also both believe a slot is available and overwrite each other.

### Distinguishing Types of State

| State type | Example | Appropriate place |
| --- | --- | --- |
| Canonical business data | Bookings, orders, ownership, balances | Database or durable datastore with the right consistency model |
| Session or interactive state | Temporary cart, verification step, web session | Session store, database, or cache with explicit policies |
| Long-running workflow state | Approval waits, retries hours later, next step | Workflow orchestration/state machine or durable datastore |
| Ephemeral per-invocation data | Intermediate variables, computed results, request buffers | Invocation memory |
| Optimization cache in execution environment | SDK metadata or infrequently changing data | Acceptable for cost/latency optimization, provided stale or lost cache is tolerated |
| Temporary files | Extracted archives or intermediate files | Temporary filesystem if supported by runtime; never treat as durable storage |

**Stateless does not mean a stateless business domain.** The application still persists business state; only the execution unit is designed not to own local state required for correctness.

## 2. Execution Environment Lifecycle and Design Consequences

The function runtime typically manages execution environments on behalf of the application team. An environment may go through:

1. **Provisioning:** the platform prepares the runtime, code, and configuration.
2. **Initialization/cold start:** the runtime loads modules and initializes libraries, clients, connections, or extensions.
3. **Invocation:** the function processes an event or request.
4. **Reuse/warm start:** the environment may be retained and reused for another invocation.
5. **Freeze/suspend or termination:** the platform may pause the process, close connections, or delete the environment according to its own policies.

There is no universal guarantee on how long an environment survives, how many invocations it receives, or whether it will always be reused. Specifics depend on the runtime and provider.

~~~mermaid
flowchart TD
    A["Event / HTTP request"] --> B{"Execution environment ready?"}
    B -- "No" --> C["Provision + initialization<br/>Cold start"]
    B -- "Yes" --> D["Reuse runtime<br/>Warm start"]
    C --> E["Invocation"]
    D --> E
    E --> F["Process, call dependencies,<br/>read/write external state"]
    F --> G["Return result / ack / emit event"]
    G --> H{"Environment retained?"}
    H -- "Possibly" --> D
    H -- "No / idle" --> I["Freeze or terminate"]
~~~

### Assumptions You Must Never Make

- The next invocation will run on the exact same instance as the previous one.
- Two invocations of the same function will execute sequentially.
- Global variables or temporary files are shared across all replicas.
- Initialization code runs only once over the entire application lifetime.
- Database connections always remain alive after idle periods or after the environment resumes.
- The platform always terminates the execution environment immediately after the handler returns.
- A local cache can be used to enforce uniqueness or processing order.

A correct function must work when **started completely fresh**, when **reused**, and when **multiple replicas execute concurrently**.

## 3. Externalizing State to the Right Service

Stateless functions rely on one or more external services to store state. The choice depends on access patterns, data durability, consistency requirements, latency, retention, and cost.

| Need | Candidate service | Design considerations |
| --- | --- | --- |
| Business transactions, relational constraints | Managed relational database | Transactions, constraints, connection management, backup/restore |
| Fast key-value access, key-based scaling | Managed NoSQL database | Partition keys, consistency, conditional writes, hot keys, TTL |
| Reconstructible session or cache data | Managed cache/session store | TTL, invalidation, eviction, stale data, and security |
| Files, images, large objects | Object storage | Metadata, access permissions, lifecycle, checksums, signed URLs |
| Asynchronous processing, burst absorption | Queue/event broker | Retries, visibility/ack, dead-lettering, idempotency, ordering |
| Multi-step, long-waiting processes | Workflow orchestration/state machine | State transitions, timeouts, compensation, retries, audit |

Example booking flow:

~~~mermaid
flowchart LR
    USER["Client"] --> API["API Gateway / HTTP endpoint"]
    API --> FN["CreateBooking function"]
    FN --> DB[("Booking database<br/>System of record")]
    FN --> OUTBOX["Outbox / event record"]
    OUTBOX --> Q["Queue / event bus"]
    Q --> NOTIFY["SendNotification function"]
    NOTIFY --> EXT["Email/SMS provider"]
    FN --> OBS["Logs, metrics, traces"]
    NOTIFY --> OBS
~~~

The function only coordinates processing within a single invocation. The database holds the booking, while the queue and event record decouple notification work. The notification function can run multiple times without corrupting booking data.

### Consistency Decisions Must Belong to the Datastore

Suppose two customers attempt to book the same time slot simultaneously. Reading "slot is available" and then writing the booking in two separate steps creates a race condition. A global variable, in-process mutex, or local cache cannot solve this because the two invocations may run in two separate execution environments.

Perform the check and write using a **transaction or conditional write** in a data store capable of enforcing the business invariant. For example:

~~~sql
CREATE TABLE booking (
    booking_id UUID PRIMARY KEY,
    doctor_id UUID NOT NULL,
    slot_start TIMESTAMPTZ NOT NULL,
    customer_id UUID NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (doctor_id, slot_start)
);
~~~

This example assumes fixed time slots. If appointments have variable start/end times and overlapping rules are permitted or complex, a simple unique constraint above is insufficient; the data model and constraints must match the domain rules.

## 4. Managing Dependencies by Lifecycle

Functions often require SDK clients, database drivers, HTTP clients, secret providers, loggers, metrics exporters, or data-processing libraries. How they are initialized impacts cold starts, latency, memory, and connection stability.

A useful rule of thumb:

- **Shared, reusable-safe dependencies:** initialize at module/runtime scope when initialization does not depend on invocation-specific data.
- **Invocation-specific data:** create inside the handler and prevent leakage into subsequent runs.
- **Bounded-lifetime connections:** use pools/clients with timeouts, keepalive, and recovery mechanisms when connections close.
- **Heavy dependencies:** measure cold start and memory impact; consider lazy initialization when only certain branches need them.
- **Security-sensitive dependencies:** never keep credentials in source code or objects whose lifetime exceeds policy limits.

### Java Example: Initializing a Reusable Client

The following example illustrates creating an HTTP client at class scope rather than per request. Reusing it can reduce connection overhead, while still requiring proper handling of timeouts and response bodies:

~~~java
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;

public final class PartnerClient {
    private static final HttpClient CLIENT = HttpClient.newBuilder()
            .connectTimeout(Duration.ofSeconds(2))
            .build();

    public String fetchStatus(URI endpoint) throws Exception {
        HttpRequest request = HttpRequest.newBuilder(endpoint)
                .timeout(Duration.ofSeconds(3))
                .GET()
                .build();

        HttpResponse<String> response = CLIENT.send(
                request, HttpResponse.BodyHandlers.ofString());

        if (response.statusCode() < 200 || response.statusCode() >= 300) {
            throw new IllegalStateException(
                    "Partner returned HTTP " + response.statusCode());
        }
        return response.body();
    }
}
~~~

`HttpClient` in this example is a shared dependency designed for reuse. In production implementations, distinguish connection errors, timeouts, retryable status codes, and invalid responses; do not log tokens or sensitive payloads. If endpoints are dynamically configured per tenant, never store tenant-sensitive data in shared static fields.

### Never Share Mutable Data Across Invocations

A static field holding a thread-safe client can be appropriate; a static field holding `currentCustomer`, a list of bookings, or request context is dangerous. If the runtime processes concurrent invocations within one process, mutable data can be overwritten or leaked across users.

Rules:

- Shared objects must be immutable or thread-safe.
- Never store requests, tokens, customer IDs, or personal data in shared singletons.
- Pass context via function parameters or invocation-scoped context objects.
- Never treat current runtime sequential execution as a permanent guarantee.

## 5. Database Connections in Function Environments

A common mistake is opening a new database connection on every invocation without bounding total connections. As functions scale out horizontally, connection counts can spike rapidly even if each invocation opens just one connection.

### Estimating Connections

Suppose the platform can run up to 80 concurrent execution environments, and each environment has a pool of up to 4 connections:

~~~text
Theoretical maximum connections = 80 × 4 = 320
~~~

This excludes connections from other workers, admin tasks, migrations, monitoring, and replicas. If the database only has 250 connections available for the application, this setup can exhaust resources. If the pool creates connections lazily, actual usage may be lower, but it must be measured under peak load.

### Common Strategies

1. **Limit function concurrency:** prevent concurrent invocations from exceeding downstream capacity.
2. **Keep per-environment pools small:** avoid idle connections; size pools according to concurrency and query duration.
3. **Use a connection proxy/pooling service:** when supported by the platform and semantics align, multiplex connections across many execution environments.
4. **Use a dedicated API/data access layer:** protect the database and centralize access logic in a controlled service.
5. **Choose datastores suited to the access model:** key-value APIs do not necessarily require long-lived relational connections.

A connection proxy can reduce backend connections, but introduces an extra network hop, quotas, cost, and transaction/session limitations. Certain transaction types or session-level settings may be incompatible with specific pooling modes. Verify against the actual database engine and proxy.

### Managing Stale Connections

An execution environment may be frozen, or connections traversing NAT/firewalls/databases may hit idle timeouts. Upon reuse, the client may hold a socket already closed by the server. Configure:

- Connection validation or check-on-borrow per driver/pool settings.
- Idle timeouts shorter than intermediate network layer timeouts where appropriate.
- Connect, read, and query timeouts.
- Bounded retries for recoverable connection errors.
- Proper resource closure at the end of an invocation if the client/pool is invocation-scoped.

Never retry indefinitely or automatically repeat write transactions without knowing whether the prior transaction committed. Use an idempotency key or outcome-verification mechanism before retrying.

## 6. External Dependencies: Timeouts, Retries, and Circuit Breakers

Functions frequently call APIs for email, payments, maps, authentication, or other internal services. When a dependency slows down, functions hold concurrency longer, driving up costs and exhausting quotas.

### Time-Budgeted Timeouts

If a function has a maximum timeout of 10 seconds, a downstream HTTP call must not wait 10 seconds to return, because time is still needed for parsing, validation, persistence, and responding. Allocate a time budget:

~~~text
T_function
  >= T_validate
   + T_database
   + T_dependency
   + T_persist_result
   + T_response_margin
~~~

This is a mental budgeting model, not an exact runtime guarantee. Each outbound call needs a timeout smaller than the invocation's remaining time; parallel calls must be budgeted by the critical path and slowest completion time.

### Conditional Retries

Retries are appropriate when errors are recoverable and the operation is idempotent or guarded against duplicates. For example, 429 or 503 responses can be retried using `Retry-After` or backoff; 400 validation errors generally should not be retried.

Recommendations:

- Use exponential backoff with jitter.
- Set a maximum retry count and overall deadline.
- Classify retryable vs. permanent errors.
- Avoid simultaneous retries across too many layers.
- Check queue retry limits, visibility timeouts, and redrive policies.
- Route persistently failing messages to a dead-letter queue for investigation.

### Circuit Breakers and Load Shedding

When a downstream service fails continuously, a circuit breaker can temporarily block new requests to the dependency, allowing recovery and preventing concurrency exhaustion. In serverless, breaker state in one execution environment's memory is not global state. If cross-instance coordination is needed, use a shared store or rely on an appropriate gateway, service mesh, or platform policy.

Do not turn a circuit breaker into a hard-to-synchronize state source. Configuration can reside at the gateway or dependency client layer provided its semantics and scope are clear.

## 7. Idempotency and Duplicate Event Handling

Event-driven platforms may redeliver events on timeouts, processing errors, or missing acknowledgments. An invocation can also commit to a database and lose connectivity before returning a response. The client or queue will retry, causing the same event to be processed multiple times.

**Idempotency** means processing the same request or event multiple times creates no additional side effects beyond the intended outcome.

### Key-Based Idempotency Pattern

For a booking creation API:

1. The client generates a unique idempotency key for the booking intent.
2. The function receives the key and checks the idempotency record.
3. If already processed, return the stored response.
4. If not, execute a transaction writing both the booking and the idempotency record together.
5. If requests arrive concurrently, a unique constraint or conditional write ensures only one transaction succeeds.

Example table:

~~~sql
CREATE TABLE idempotency_record (
    idempotency_key VARCHAR(128) PRIMARY KEY,
    request_hash VARCHAR(128) NOT NULL,
    response_json JSONB,
    status VARCHAR(20) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
~~~

This is only a conceptual model. A production design must define transactions, in-progress states, timeouts, request hashes, retention, handling of a reused key with a different payload, and recovery when an invocation crashes mid-flight.

### Do Not Equate Idempotency with Exactly-Once

A queue may deliver messages at least once; consumers must tolerate duplicates. Some services offer deduplication or ordering within bounded scopes, yet cannot guarantee all external side effects occur only once.

Sending customer email is a clear example: the function calls the provider successfully and then times out before recording the outcome. On retry, the email could be sent again. Use provider-level idempotency if supported, persist an operation ID, or design business rules that tolerate or coalesce duplicate notifications.

## 8. Configuration and Secrets

Functions need environment settings, endpoints, feature flags, connection details, and credentials. Always distinguish **non-sensitive configuration** from **secrets**.

| Data | Appropriate management | Notes |
| --- | --- | --- |
| Feature flags, queue names, timeouts | Environment/config service | Track versions and changes |
| Database passwords/API tokens | Secret manager | Per-function access control, rotation, auditing |
| Encryption keys | KMS or equivalent key management system | Never place plaintext keys in source/config/logs |
| Certificates | Certificate/secret management | Renewal, rotation, and read permissions |
| Tenant-specific credentials | Identity/tenant-scoped secret store or token exchange | Never keep in uncontrolled shared caches |

### Least Privilege

Each function should have a dedicated execution role/service identity or role scoped by capability. `CreateBooking` only needs permission to write bookings and emit events; `SendNotification` only needs permission to read messages and call the notification provider—not modify the entire database.

Never embed long-lived access keys in code, container images, or manually managed environment variables. Environment variables may carry secret references or configuration, while actual secrets should be delivered via protected mechanisms with minimal privileges. Clarify:

- Who can retrieve the secret and for how long?
- Will rotation break execution environments holding existing connections?
- How is a leaked secret revoked and investigated?
- Can logs or traces inadvertently print tokens or payloads?
- Does secret store latency or quota affect cold starts?

### Conditional Secret Caching

Fetching secrets on every invocation increases latency and cost. Secrets can be cached inside the execution environment with a short TTL if policy permits. However, rotation will not take effect in environments holding cached values until the cache expires or refreshes. Document maximum validity windows and revocation procedures.

## 9. Dependency Management in Build and Deploy

Beyond runtime services, dependencies include source libraries, runtime versions, native libraries, extensions, and packaged artifacts.

- Pin versions or use lockfiles/dependency constraints for reproducible builds.
- Keep dependencies minimal to reduce package size and cold starts.
- Scan for CVEs, license compliance, and artifact provenance.
- Build targeting the exact runtime and CPU architecture of the function target.
- Separate build-time dependencies from runtime dependencies where tooling supports it.
- Verify package shading, native libraries, classpaths, and deployment size limits.

For Java, verify JDK version, API compatibility, framework startup time, reflection/AOT behavior if applicable, timezone/locale, and memory profile. An artifact that runs on a developer laptop may fail in a serverless runtime with a different filesystem, CPU architecture, or permission model.

Every release should carry a version tag or digest, never downloading arbitrary dependencies during request handling. The build pipeline must scan, test, and sign or verify artifacts per organizational policy. On rollback, the team must know exactly which artifact and configuration were deployed.

### Dependency Graphs and Cold Starts

Large libraries, heavy static initialization, classpath scanning, and synchronous startup connections inflate cold starts. Initialize only what invocations require. Lazy initialization can cut startup time for rarely used branches, at the trade-off of extra latency on the first invocation hitting that branch.

Measure cold starts separately from warm invocations; never average them together and hide p99 latency.

## 10. Concurrency, Memory, and Function Limits

Serverless platforms can automatically spin up more execution environments as traffic rises. This simplifies scaling, but can amplify load onto databases or external APIs.

Limits to define:

- **Max concurrency:** maximum simultaneous invocations globally for a function or per event source.
- **Reserved/provisioned concurrency:** pre-allocated or kept-warm capacity per provider semantics.
- **Memory/CPU:** memory settings often govern CPU/network performance or pricing depending on the service.
- **Timeout:** maximum duration of a single invocation.
- **Payload/event size:** request/message size limits.
- **Retries and age:** maximum retry count or event age.
- **Account/region quotas:** total concurrency and resource limits at account level.

For example, if a function can scale up to 100 concurrent invocations and each opens 3 database connections, potential load reaches 300 connections. Concurrency caps must be coordinated with connection pools, quotas, and database capacity.

### Preventing Scale Storms

An abnormal event spike can trigger massive invocation volume. When a downstream service fails, queue retries or event redeliveries can compound the load. Design controls:

1. Cap concurrency to what downstream dependencies can handle.
2. Buffer bursts with queues and regulate consumer concurrency.
3. Apply retry/backoff with jitter; never retry indefinitely.
4. Monitor queue backlog and message age, not just invocation counts.
5. Maintain DLQ handling and safe replay procedures.
6. Set budgets/quotas and cost-spike alerts.

## 11. Networking and Connectivity to Dependencies

Functions often need to reach private databases, object storage, queues, or external APIs. Connectivity patterns affect security, latency, cost, and scalability.

If a function is placed inside a VPC/VNet or private network, specify:

- Subnets and IP addresses sufficient for concurrency, ENIs, or network interfaces per platform allocation rules.
- Routes to databases and private endpoints.
- Egress paths to the Internet/external APIs via NAT or network gateways when required.
- DNS resolvers and private DNS zones.
- Security groups/firewalls opening only necessary ports and destinations.
- Costs of NAT, private endpoints, and data transfer.

Not every function belongs in a private network. If it only calls managed services over endpoints protected by identity/service policies, placing the function in a VPC can add unnecessary complexity and cost. Conversely, private data requires explicit network paths and policies.

As concurrency rises, socket counts, ephemeral ports, NAT connection tracking, and IP consumption grow. Do not estimate solely by requests per second. Test burst concurrency, destination counts, socket lifetimes, and connection pool behavior.

Clients may cache DNS or keep connections open for long periods. When endpoints change, stale connections can fail. Configure sensible timeouts, connection refreshes, controlled retries, and proper endpoint discovery.

## 12. Observability for Stateless Functions

Execution environments are ephemeral and replicated, so logs and metrics must be centralized. You cannot SSH into a fixed instance to inspect overall workload health.

Each invocation should log appropriate fields:

- Function name/version, environment, invocation/request ID.
- Event/correlation ID and trace ID.
- Operation name, dependency name, outcome status.
- Duration, timeout, retry count, and error classification.
- Pseudonymized or sanitized tenant/customer identifier where required.

Never log access tokens, secrets, payment details, or full sensitive payloads. Perform redaction at the source before shipping logs to a centralized system.

| Category | Metrics |
| --- | --- |
| Invocation | invocation count, success/error, throttles, duration p50/p95/p99 |
| Runtime | cold starts, init duration, memory used, timeouts, OOMs |
| Concurrency | concurrent executions, reserved/provisioned utilization |
| Dependency | connect/query/API latency, timeouts, errors, retries |
| Event processing | queue depth, oldest message age, DLQ count, delivery failures |
| Business | bookings created, duplicates prevented, notifications delivered |
| Cost | invocations, duration, memory allocation, network, logs, and downstream |

A function with a 99.99% success rate while notifications sit in a queue for hours still fails business expectations. Combine technical telemetry with business metrics and end-to-end SLOs.

## 13. Testing and Deployment

Testing layers to consider:

1. **Unit tests:** pure logic, validation, mapping, and error handling.
2. **Contract tests:** event schemas, HTTP contracts, database access, and partner APIs.
3. **Integration tests:** run against real datastores/queues or faithful emulators, verifying auth and networking.
4. **Concurrency tests:** multiple invocations creating the same resource, delivering duplicate events, or updating concurrently.
5. **Failure tests:** slow dependencies, timeouts, connection resets, DLQs, secret rotation, and database failover.
6. **Performance tests:** cold starts, warm duration, p95/p99, concurrency, and downstream saturation.
7. **Security tests:** IAM least privilege, payload validation, secret exposure, SSRF, and network access.

### Testing Both Cold and Warm Paths

A benchmark running continuous invocations on a single warm environment hides cold starts and scale-out behavior. Test:

- First invocation after deployment or when no warm environments exist.
- Sudden traffic spikes forcing the platform to spin up many new environments.
- Long-running invocations and degraded dependencies.
- Retries/redeliveries after a function crashes at different workflow stages.
- Memory near configured limits and large payload processing.

### Safe Deployment

Functions can deploy via versions/aliases, traffic shifting, canary releases, or equivalent platform mechanisms. The workflow should:

- Build immutable artifacts and run security scans.
- Deploy the new version without immediately shifting 100% of traffic.
- Observe error rates, duration, throttling, and business metrics.
- Shift traffic incrementally if thresholds are met.
- Roll back the alias/version if errors exceed limits.
- Keep database schemas backward- and forward-compatible across old and new versions during transitions.

Rolling back code does not automatically roll back persisted data. Schema migrations require backward-compatible strategies or explicit recovery steps.

## 14. Common Mistakes

**Storing business state in global variables.** Another execution environment cannot see it; data can be lost upon termination.

**Assuming a function executes sequentially.** Concurrency can trigger parallel invocations; use transactions, conditional writes, and idempotency.

**Opening a new database connection per invocation without limits.** Scale-out creates connection spikes that can overwhelm the database.

**Holding connections indefinitely inside the environment.** Runtimes can freeze; NAT, firewalls, or databases may close idle sockets.

**Retrying every error.** Validation errors do not self-heal; retrying writes can create duplicates or amplify overload.

**Putting an entire long-running workflow in one function.** Timeout and memory limits may not fit; use queues/workflow orchestration for long, waiting, or multi-step processes.

**Treating local cache as authoritative data.** Caches can go stale, disappear, or diverge across environments; use only for optimization with proper invalidation.

**Leaving secrets in source code or logs.** Secrets can leak via artifacts, traces, or debugging; use a secret manager and redaction.

**Ignoring quotas and cost during scale-out.** Higher concurrency can drive up database, NAT, logging, and third-party API costs.

**Testing only warm invocations.** Overlooks cold starts, scale-out, runtime initialization, and post-freeze/thaw behavior.

## 15. Hands-On Exercise: Designing a Stateless Booking Function

**Hypothetical scenario:** A booking application runs on a function platform. An API receives booking requests, persists data to a database, and pushes a notification event into a queue. A separate function sends email/SMS. The system can receive 200 requests/second during peak hours; the same event can be redelivered; the database allocates only 120 connections to the application. The SLO for valid booking transactions is 99.9% over 30 days, with API p95 under 400 ms. These are practice figures that must be validated and measured in an actual project.

### Tasks

1. **Design state boundaries:** specify which data lives in invocation memory, cache, database, queue, and workflow store. Identify the system of record for bookings.
2. **Design dependencies:** decide which clients initialize at module/runtime scope and which per invocation; specify thread safety, connection lifetimes, and secret access.
3. **Calculate connections:** with max concurrency 60 and max pool size 2 connections/environment, calculate total potential connections. Compare against the 120-connection budget and leave headroom for workers/monitoring.
4. **Design idempotency:** handle two events with the same key, the same key with a different payload, and the case where database write succeeds but the invocation times out before responding.
5. **Design timeouts/retries:** allocate time budgets for the database, queue, and email provider; specify retryable errors, backoff, DLQ, and concurrency caps.
6. **Design security:** dedicated execution roles, secret manager, network access, and log redaction. List permissions the functions must not have.
7. **Design observability:** choose technical and business metrics to detect cold starts, throttling, duplicates, backlog, and downstream failures.
8. **Plan testing:** unit, integration, concurrency, cold/warm, scale-out, and failure tests.

### Suggested Solution Approach

Bookings are persisted in the database using transactions/constraints, never in a function's static map. The invocation accepts an idempotency key and records the deduplication result in the same transaction. Queue/event publishing uses a transactional outbox or equivalent mechanism to prevent committing a booking while losing the event.

Thread-safe HTTP and SDK clients can initialize outside the handler and be reused; request context, tenant data, and transaction objects remain invocation-scoped. The database pool is bounded; at 60 environments × 2 connections, the theoretical ceiling is 120, leaving no headroom for workers or maintenance tasks. Therefore, the team should shrink the pool, cap concurrency, or introduce a proxy/data access layer after measurement.

The notification function is idempotent by notification ID. If the provider supports idempotency, pass an operation key; otherwise, record delivery status and accept/control potential duplicate sends. The queue configures bounded retries, an appropriate visibility timeout, and a DLQ for poison messages.

This is a directional solution, not a complete production configuration. You must verify the exact semantics of your function platform, database, queue, connection proxy, and email provider.

### Acceptance Criteria

| Objective | Evidence |
| --- | --- |
| No double bookings | Concurrency tests prove only one booking succeeds for a single slot |
| No reliance on prior environment | Newly launched environments read and process bookings accurately |
| Duplicate event tolerance | Re-delivering the same event causes no unintended business side effects |
| Database protection | Connection count stays within budget at max concurrency |
| Downstream failure recovery | Bounded retries, alerted DLQ, safe replay |
| Secret protection | No credentials in code/logs; function permissions are scoped |
| Meets SLO | Load tests and telemetry show p95 and error rates meet targets under test load |

## 16. Well-Architected Evaluation

| Pillar | Questions for stateless functions and dependencies |
| --- | --- |
| **Operational Excellence** | Are builds reproducible, versions rollbackable, dependencies/runtimes inventoried, and logs correlated? |
| **Security** | Do functions have dedicated execution identities, least privilege, secret rotation, input validation, and proper network boundaries? |
| **Reliability** | Are duplicate events, timeouts, retries, DLQs, downstream failures, and environment terminations handled? |
| **Performance Efficiency** | Are cold starts, dependency initialization, connection pools, memory, concurrency, and p95/p99 measured? |
| **Cost Optimization** | Is concurrency capped, are retry storms prevented, and are log retention and network egress monitored? |
| **Sustainability** | Do functions avoid unnecessary polling/loops, bloated dependencies, and idle background resources? |

A solid design proves **correctness independent of execution environment**, ensures concurrency does not corrupt data or overload downstream systems, and gives the team clear signals on function behavior. Statelessness makes scaling and replacing execution environments easy; disciplined dependency management ensures those benefits are not eroded by cold starts, exhausted connections, stale secrets, or uncontrolled retries.

## 17. Pre-Production Checklist for Functions

- [ ] Required business data and session state reside in an appropriate datastore/workflow, not solely in local memory.
- [ ] Handlers behave correctly on cold environments, warm environments, and concurrent invocations.
- [ ] Shared variables hold only immutable/thread-safe dependencies; never request context or mutable tenant data.
- [ ] SDK/client initialization and lazy loading are measured for cold start, memory, and latency.
- [ ] Connection pools, idle timeouts, validation, retries, and max concurrency align with downstream quotas.
- [ ] Overall and per-dependency timeouts are budgeted explicitly; no unbounded retries.
- [ ] Write operations enforce idempotency keys or equivalent deduplication mechanisms.
- [ ] Queues have retry policies, appropriate visibility/ack settings, DLQs, alerts, and replay procedures.
- [ ] Secrets reside in a proper secret management system, scoped by least privilege, with rotation enabled.
- [ ] Build artifacts pin versions and verify vulnerabilities, runtime, and CPU architecture compatibility.
- [ ] Network routes, subnets, DNS, egress, NAT/IPs, and private endpoints are validated against concurrency.
- [ ] Logs/metrics/traces include correlation IDs, redaction, and business metrics.
- [ ] Cold/warm, concurrency, failure, load, security, and rollback tests are in place.
- [ ] Quotas, costs, retry storms, and scale-out conditions have limits, alerts, and owners.
- [ ] Architecture decisions, exceptions, and review conditions are documented.

Designing stateless functions is about more than removing global variables. It means placing the **system of record in durable storage**, making every invocation independently executable, managing dependencies by lifecycle, shielding downstream services from concurrency spikes, and handling duplicate failures safely. Only when these boundaries are explicit and tested can serverless scale elastically while maintaining correctness, security, performance, and predictable cost.
