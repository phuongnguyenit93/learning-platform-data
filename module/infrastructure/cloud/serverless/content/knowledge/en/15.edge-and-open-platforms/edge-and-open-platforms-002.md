# Runtime Limits, Data Locality, and Latency at the Edge

Edge computing moves part of request processing closer to users or devices instead of doing everything in a single regional data center. In a serverless application, an edge function can inspect requests, validate tokens, route traffic, normalize headers, apply caching, or select a backend before a request enters deeper into the system. This approach can reduce response times and origin traffic, but it is effective only when the runtime, data placement, and network paths are designed properly.

Running code at the edge does not mean every component of the application is close to the user. A function can run at a Point of Presence (PoP) near the client while the database still resides in a distant Region. In that case, the request is processed quickly in the initial step but still travels a long distance to read or write data. Compute location, data location, and user location must be treated as three separate factors.

In the **CLOUD_SERVERLESS** module, learners develop and deploy Java functions triggered by HTTP, messages, or events, while handling access control, state, retries, idempotency, cold starts, scaling, and cost. This lesson explains runtime limits at the edge, data locality, and latency, and then establishes how to split work between the edge and Java functions running in a Region.

## 1. Edge Computing in Serverless Architecture

The edge is a distributed infrastructure layer located close to users, devices, or access networks. Providers can deploy code across many PoPs, edge locations, or network zones. When a request arrives, the system routes it to a suitable location and executes logic there.

Tasks suited for the edge typically share these characteristics:

- Fast, low-state processing that does not require querying complex business data.
- Decisions can be made from information in the request, tokens, headers, or cached data.
- Reduces calls to the origin or reduces the payload size sent back to the client.
- Benefits from executing close to users across multiple countries/regions.
- Short execution duration with minimal OS library dependencies.

Typical examples include geo-based redirects, URL rewrites, token verification, bot filtering, adding security headers, cache key normalization, origin selection, serving static content, or serving cached public data.

Workloads typically better suited for a Region or a dedicated backend:

- Operations requiring transactions and strong consistency.
- Multi-table queries or joins against a centralized database.
- Long-running tasks, batch processing, multi-step workflows, or waiting for callbacks.
- Large file processing, heavy ML inference, or GPU workloads.
- Java applications relying on a full JVM, reflection, native libraries, or large frameworks.
- Workloads requiring arbitrary TCP connections, a persistent filesystem, or long-lived background threads.

### Request Flow Through the Edge and Region

~~~mermaid
flowchart LR
    C[Client / device] --> P[Edge PoP]
    P --> E[Edge function]
    E -->|Cache hit| K[Edge cache]
    K --> C
    E -->|Cache miss / business request| R[Regional API / Java Function]
    R --> D[(Regional database)]
    R --> Q[Queue / workflow]
    Q --> W[Background workers]
    R --> E
    E --> C
~~~

The edge can terminate the request from cache or run lightweight logic before forwarding to the Region. The regional API and Java functions typically own business logic, authoritative data, and controlled side effects.

## 2. How Are Runtimes Constrained at the Edge?

There is no single edge runtime shared across all providers. One platform may use JavaScript isolates, while another runs WebAssembly, native sandboxes, or small containers. The runtime determines the supported languages, system APIs, memory model, and how resources are bounded.

Common categories of limits:

| Limit category | What to check | Design impact |
|---|---|---|
| CPU time | Actual CPU time permitted | Avoid heavy loops, large encryption/decryption, or sustained computation |
| Wall-clock duration | Total time an invocation is allowed to stay active | Limit chained network calls and long waits |
| Memory | Heap/linear memory and total memory | Bound payloads, in-process caches, and data structures |
| Request/response size | Header, body, and response sizes | Stream data, cap uploads, or send files directly to object storage |
| Subrequest/network | Number of fetch calls, connections, allowed protocols | Batch requests, cache, and avoid fanning out to many services from the edge |
| Artifact/package | Bundle, module, or dependency size | Remove unused libraries and split code by concern |
| Runtime APIs | Available APIs such as fetch, crypto, cache, timers | Do not assume full Linux or JVM APIs are available |
| Concurrency | Concurrent requests or per-tenant limits | Avoid shared mutable state and protect the origin |
| Storage | Capacity, latency, consistency, and quotas of KV/cache | Do not treat local memory as durable storage |
| CPU architecture/ABI | Binary architecture and interface | Native executables must match the deployment environment |

Exact limits vary by provider, pricing tier, runtime version, and product type. Numbers from outdated docs or a free tier cannot be used as production assumptions. Before deploying, check current quotas for the exact service, Region, runtime, and plan; also measure using the real artifact.

### CPU Time vs. Wall-Clock Time

CPU time is the time code actually spends using the CPU. Wall-clock time is the elapsed time from invocation start to completion, including time spent waiting on network or I/O. A function can use very little CPU and still exceed the wall-clock limit while waiting on a slow API. Conversely, a compute loop can exhaust the CPU limit even without making any network calls.

Do not optimize blindly by merely reducing lines of code. Identify whether the bottleneck is CPU, network, storage, cold start, or origin wait time, then choose the appropriate fix.

### Operating System and Runtime APIs

Some edge isolates do not provide processes, arbitrary filesystems, raw sockets, native threads, JNI, or the full Java Standard Library API. APIs such as `fetch`, Web Crypto, and streams may be exposed according to the runtime's own model.

Code written for the JVM may depend on:

- Reflection, classpath scanning, and dynamic class loading.
- JNI or native libraries compiled for a specific OS/architecture.
- Long-lived threads, executors, and schedulers.
- Filesystems or temporary files.
- Arbitrary TCP/UDP sockets.
- OS-level TLS, DNS, or certificate stores.
- Frameworks that initialize a large application context.

Therefore, you cannot assume a Java JAR can run as-is inside an edge isolate. Only deploy Java directly when the edge product explicitly documents support for a suitable Java/JVM runtime. If the platform only supports JavaScript or WebAssembly, you must build and test an artifact compatible with that runtime/ABI; compiling to native or WebAssembly does not automatically guarantee that all Java libraries will work.

## 3. Should a Java Function Live at the Edge or in a Region?

Java is most naturally deployed in a managed runtime inside a Region, where a JVM, frameworks, and familiar libraries are available. Some edge platforms can run WebAssembly or native artifacts, but that is a different deployment model requiring separate compatibility verification.

Responsibilities can be divided as follows:

| Task | Edge | Regional Java function |
|---|---|---|
| Redirects, URL rewrites | Very well suited | Possible, but typically adds a network hop |
| Simple JWT signature/claim checks | Suitable if keys and policies can be distributed securely | Suitable for complex policies or introspection |
| Caching public content | Very well suited | Origin generates content and cache policies |
| Authorization against complex tenant data | Preliminary checks only if sufficient context exists | Should run in the service that owns the data |
| Database transactions and updates | Usually unsuitable | Well suited |
| Large file processing | Should route uploads directly to storage | Suitable for orchestration or stream processing |
| Batches, workflows, long-term retries | Unsuitable | Well suited with queues/workflows |
| Full Java framework/JVM | Only when explicitly supported by the runtime | Usually the natural choice |
| Selecting Region/origin and adding headers | Very well suited | No need for a separate step if the edge already handles it |

A practical architectural pattern is having the edge handle cheap, stateless checks and then forward normalized requests to a Java API in the Region. The Java service enforces authorization against authoritative data, executes transactions, and emits messages for asynchronous work.

### Do Not Replicate Authoritative Business Rules Across Many Edge PoPs

If each PoP holds its own copy of business rules or cached business data, they may not update simultaneously. Two closely timed requests routed through two different PoPs could receive different decisions. Decisions involving balances, order statuses, usage quotas, or access permissions must rely on a data source with appropriate consistency, usually the service/database owning the business domain.

The edge can enforce static policies or signed/time-bounded data, but those artifacts need explicit expiration, versioning, and revocation mechanisms.

## 4. Data Locality: Compute Location Is Not Data Location

Data locality describes where data is stored, where it is read/written, and which network paths it traverses to reach where it is processed. When a function runs at the edge, the data may still reside in a database in a central Region.

For example, a client in Vietnam sends a request to a nearby regional edge PoP. The edge validates the token in a few milliseconds, then calls a database located in a more distant Region. Fast authentication does not eliminate the latency of querying the data.

At least four locations should be separated:

1. **Client location:** the user or device sending the request.
2. **Compute location:** the PoP or Region where code executes.
3. **Data location:** where databases, object storage, caches, or queues store data.
4. **Control/management location:** where logs, traces, secrets, backups, and the control plane are stored or processed.

Placing compute close to the client can reduce client-to-compute latency, but it does not automatically reduce compute-to-data latency. Additionally, logs and telemetry might be shipped to another Region even if business data is stored locally.

### Data Locality and Regulatory Requirements

Data residency requirements may apply to stored data, replicas, backups, logs, metadata, cross-border data transfers, or where personnel can access data. Processing an edge request in-country is not enough to prove that all data remains within the country.

When data location requirements apply:

- Identify which data is classified as personal, sensitive, or restricted to a jurisdiction.
- Check the storage locations of primary data, replicas, backups, caches, and logs.
- Determine whether request bodies, headers, cookies, and tokens are transmitted to external PoPs or services.
- Check where secrets, encryption keys, and audit logs are managed.
- Identify data processors/subprocessors and cross-border transfer terms.
- Design compliant deletion, retention, export, and incident response policies.

Do not infer data location solely from a Region name or PoP location. Verify the service configuration, contracts, and current compliance documentation from the provider.

## 5. Replication, Consistency, and Distributed Data

To reduce latency, a system can replicate data across multiple Regions or edge locations. However, distributed replicas raise questions about consistency and updates.

### Strong Consistency

Strong consistency requires clients to read the latest value according to a defined transaction order. This suits data where wrong decisions cause harm, such as account balances, final inventory counts, or payment statuses. In exchange, operations may need to coordinate with a remote authority/leader, increasing latency.

### Eventual Consistency

Eventual consistency allows replicas to differ temporarily while converging once updates stop. It suits public content, infrequently changing configuration, catalogs, or display data that can tolerate staleness for a bounded period. The application must account for TTL, replication lag, and how concurrent writes are handled.

### Read Local, Write Home

A common pattern is reading from a replica near the client while sending writes to a single data-owning Region. This lowers latency for read-heavy workloads while keeping write authority in one place to reduce conflicts.

However, local reads can return stale data immediately after a write. If the business flow requires read-your-writes, the client can be routed to the home Region after a write, use version tokens, or read from the primary for a short window.

### Conflicts and Idempotency

If multiple PoPs or Regions can write the same record, you must define conflict resolution: version/sequence numbers, compare-and-set, last-write-wins, or business merges. Timestamp-based last-write-wins can fail under clock skew and overwrite important changes.

Data-mutating events need an idempotency key and an event ID. When replication or retries redeliver an event, consumers must recognize that the operation has already completed. If side effects occur across multiple Regions, define where the idempotency key lives and how deduplication is synchronized.

## 6. What Makes Up Latency at the Edge?

End-to-end latency is not just edge function execution time. A single request can traverse many stages:

- DNS lookup and TCP/QUIC connection setup.
- TLS handshake or connection reuse.
- Client to edge PoP.
- Queueing and scheduling in the edge runtime.
- Cold start or isolate initialization.
- CPU time of the edge function.
- Edge to origin or regional API.
- Regional API to database/cache/supporting services.
- Response traveling back to the edge and client.

This can be modeled simply as:

~~~text
Total latency
  = client-to-edge network
  + edge queue/startup/compute
  + edge-to-origin network
  + origin compute
  + origin-to-data network and query
  + response transfer
~~~

Components can overlap when using streaming or parallel requests, so this is an analytical model rather than an exact sum in every case.

### Example of Two Paths

Suppose a client is close to a PoP:

- Edge validates the token and serves a cache hit: the request finishes near the edge without calling the Region.
- Edge validates the token and then calls the Java API and database in a distant Region: the request still incurs edge-to-region network latency and database query time.

For dynamic requests, the edge helps only if it eliminates a round trip, shrinks transferred data, or routes to a better backend. If the edge adds a network hop without reducing downstream work, total latency can increase.

### Nearest Is Not Always Fastest

The geographically closest PoP does not always have the fastest network path. Routing, peering, congestion, ISPs, and origin health all affect real-world timing. Measure across real user regions and ISPs rather than relying solely on a provider's PoP map.

## 7. Caching as an Effective Way to Cut Round Trips at the Edge

Caching avoids calling the origin for repeatedly requested content. It is especially effective for public content, rarely changing data, or data where brief staleness is acceptable.

A cache key typically needs to consider:

- Scheme/host/path and meaningful query parameters.
- Language, encoding, or device class if responses differ.
- Content version or tenant when needed.
- Which headers genuinely change the representation.

Do not include every header in the cache key because high cardinality destroys the hit ratio. Conversely, omitting a header that affects content can cause clients to receive the wrong response.

### Cache-Control and Personal Data

Example of public content cacheable for a short duration:

~~~http
Cache-Control: public, max-age=60, s-maxage=300, stale-while-revalidate=30
ETag: "catalog-v18"
~~~

Example of a personalized response:

~~~http
Cache-Control: private, no-store
~~~

Do not cache user- or session-specific responses in a shared cache unless the cache key and policy are explicitly designed and tested. Watch out for `Authorization`, `Cookie`, `Set-Cookie`, and client-supplied headers.

### Cache Invalidation

When data changes, cached entries must be updated or invalidated. Common strategies:

- Short TTLs to bound staleness duration.
- Versioned URLs or content hashes so updated content gets a new cache key.
- Tag- or key-based purge/invalidation if supported by the platform.
- Stale-while-revalidate to serve old data while refreshing in the background.
- Event-driven invalidation from the system that owns the data.

A cache stampede occurs when many requests miss the same key simultaneously and hit the origin all at once. Use request coalescing, stale responses, TTL jitter, or cache pre-warming if supported by the runtime.

## 8. Routing Requests to Origins and Regions

An edge function can select a backend based on host, path, tenant, geo hints, health, or request type. Distinguish routing by user location from routing to where data is owned.

Examples:

- Public content: serve from the edge cache.
- Catalog read API: select a Region with a replica close to the client.
- Order update API: route to the home Region of the tenant/order.
- Admin requests: route to a tightly controlled backend.
- Origin failure: switch to a fallback only when the data semantics and action permit it.

Do not arbitrarily route write transactions to the nearest Region unless every Region has ownership and conflict resolution mechanisms. An order belonging to home Region A should continue to be processed in A or go through a controlled ownership-transfer protocol.

### Health Checks and Failover

Failover is not merely picking any live origin. Determine:

- Does the origin have sufficiently fresh data?
- Are only reads allowed during failover, or writes as well?
- Is there a risk of two Regions accepting writes simultaneously (split brain)?
- How long do DNS/edge routes take to converge?
- Can in-flight requests be retried safely?
- Should an explicit error be returned instead of routing to an inconsistent location?

For non-idempotent operations, the edge should not automatically retry a `POST` to another origin when it does not know whether the first origin committed. Use idempotency keys and reconciliation to establish the outcome.

## 9. Edge and Data Security

The edge expands the processing surface across many PoPs. This can improve attack resilience and reduce load on the origin, but it also requires consistent management of policies, secrets, and logs.

### Authentication and Authorization

The edge can verify JWT signatures, issuers, audiences, expirations, and simple claims. Ensure:

- Only configured algorithms and keys are accepted; never trust a JWT header to select a weak algorithm.
- Key rotation is distributed and cached with an appropriate lifetime.
- Access tokens, refresh tokens, and cookies are never logged.
- Resource-level authorization runs in the backend owning the data if the edge lacks sufficiently fresh permission sources.
- Geo-IP or forwarded headers are never treated as user identity.

If the edge uses token introspection or calls the identity provider on every request, the network call can wipe out latency gains. Keys/JWKS can be cached safely with a TTL, provided revocation windows and key rotation are accounted for.

### Secrets and Outbound Access

Distributing secrets to many edge locations can widen the blast radius if compromised. Prefer short-lived credentials, narrow scopes, and the platform's secret management mechanisms. Never embed long-lived secrets in client-side code or responses.

Restrict outbound requests via host and protocol allowlists to prevent SSRF. Validate URLs before fetching; block metadata endpoints, private IPs, or redirects to hosts outside the allowlist per policy. Enforce TLS and never disable certificate validation to work around connection errors.

### Logs and Privacy

Requests at the edge can contain IPs, cookies, query strings, user agents, tokens, or personal data. Log only fields needed for operations; redact or hash identifiers per policy. Verify which Region logs are shipped to, retention periods, and who has access.

## 10. State and Storage in Edge Runtimes

Memory inside an edge instance is typically ephemeral. It may be reused across a number of requests, but it is not guaranteed to survive deployments, scaling, isolate eviction, or the very next request. Static fields in JavaScript/Wasm or global objects are not a database.

Distinguish types of state:

| State type | Appropriate storage | Examples |
|---|---|---|
| Per-request data only | Local variables/request context | Parsed headers, normalized paths |
| Short-lived cache safe to lose | Edge cache or in-memory cache with TTL | Public configuration, metadata |
| Data shared across PoPs | Platform-provided distributed KV/cache | Feature flags, routing metadata |
| State needing transactions/strong consistency | Regional database or aggregate-owning service | Payments, inventory, orders |
| Work that must survive retries | Queue, durable workflow, or database job | Emails, reports, file processing |
| Large payloads | Object storage | Uploads, media, archives |

Distributed KV at the edge typically has its own consistency model, replication lag, quotas, and size limits. Do not assume a write at one PoP becomes immediately visible at every PoP. Read the product's consistency documentation before using it for permissions, balances, or state requiring accuracy.

## 11. Large File Upload and Processing Pattern

Do not stream large files through an edge function if the platform enforces request body, memory, or duration limits. An effective pattern is:

1. The client calls a regional API to request upload authorization or a time-limited URL.
2. The client uploads directly to object storage in the appropriate Region.
3. Storage emits an event or sends a message.
4. A Java function in the Region processes the file as a stream or batch.
5. The edge serves status, metadata, or cached results.

The edge can verify tokens and issue upload URLs, provided scope, object key, content type, size, and expiry are tightly constrained. The backend must re-verify metadata and actual content; do not trust client-declared content types.

If data must remain in a specific country/Region, the upload URL must point to approved storage. Routing edge traffic near the client while uploading to storage in a different Region can increase egress costs and violate data residency requirements.

## 12. Example: Edge Validates Requests, Java Function Handles Business Logic

Suppose an e-commerce application serves users across multiple regions. The edge validates tokens and routes requests; a Java function in the Region processes orders.

### Edge Logic (JavaScript Pseudocode)

~~~javascript
async function handleRequest(request) {
  const url = new URL(request.url);

  if (url.pathname.startsWith("/assets/")) {
    return fetch(request); // CDN/cache policy handles static content.
  }

  const token = readBearerToken(request.headers);
  const claims = await verifyJwtLocally(token);

  if (!claims || !claims.sub) {
    return new Response("Unauthorized", { status: 401 });
  }

  const headers = new Headers(request.headers);
  headers.set("x-authenticated-subject", claims.sub);
  headers.set("x-request-region", selectRegion(request));

  // Origin must only accept traffic from a trusted edge or re-verify the token.
  return fetch(buildRegionalOrigin(url), {
    method: request.method,
    headers,
    body: request.body
  });
}
~~~

This is flow-illustrating pseudocode, not deployment-ready code for a specific edge provider. The `fetch` API, streaming request bodies, header forwarding, runtime limits, and JWT verification vary across platforms. The `x-authenticated-subject` header does not become trustworthy proof on its own if clients can call the origin directly or forge that header; the origin must block direct calls or verify a signature/credential from the edge.

### Regional Java Function

~~~java
public final class OrderService {
    public OrderResponse createOrder(
            CreateOrderCommand command,
            AuthenticatedPrincipal principal,
            String idempotencyKey) {

        validateRequest(command);
        authorizeCustomer(principal, command.customerId());

        // Transactions and idempotency are protected in the data-owning service.
        return orderRepository.createOnce(
                command, principal.subject(), idempotencyKey);
    }
}
~~~

The Java service retains business rules, resource-level authorization, and transactions. The edge performs only checks that can be done safely from the request/token and routes the request to the appropriate Region.

### End-to-End Flow

~~~mermaid
sequenceDiagram
    participant U as User
    participant E as Edge Function
    participant C as Edge Cache
    participant J as Regional Java API
    participant D as Database
    participant Q as Queue

    U->>E: HTTPS request
    E->>E: Validate token and normalize request
    alt Public cache hit
        E->>C: Read cached object
        C-->>E: Cached response
        E-->>U: Response
    else Dynamic order request
        E->>J: Forward to home Region
        J->>J: Resource authorization
        J->>D: Transaction + idempotency
        D-->>J: Commit result
        J->>Q: Publish background event
        J-->>E: Order response
        E-->>U: Response
    end
~~~

## 13. Measuring Latency by User Region

A benchmark run from a single machine in one Region does not reflect global user experience. Measure from representative client locations, segmented by ISP and connection type when possible.

Key metrics:

- DNS, connect, and TLS handshake times.
- Time to first byte (TTFB).
- End-to-end p50, p95, and p99 latency.
- Edge compute duration and CPU time.
- Cache hit ratio, miss ratio, and origin fetch rate.
- Edge-to-origin latency per Region.
- Database query latency and dependency latency.
- Cold start/init duration if exposed by the runtime.
- Errors, timeouts, retries, and throttling by PoP/Region.

Propagate a request ID and trace context across the edge, regional API, and database. Avoid recording sensitive data in traces. When comparing edge against regional-only, use identical requests, cache states, and workloads to avoid skewed conclusions from warm caches or differing loads.

### Regional Breakdown

A global dashboard can hide high latency for a specific ISP or country. Segment by PoP/colo, client region, origin region, route, and cache status. If edge compute is fast but TTFB remains high, check networking or the origin; if cache hits are fast but misses are very slow, inspect the edge-to-origin and database path.

## 14. Costs and Trade-offs of Moving Processing to the Edge

The edge can cut origin egress and offload backends, but it can introduce charges for requests, CPU time, subrequests, storage replication, caching, logging, and data transfer. A request processed at the edge that then calls a regional API incurs both edge and origin costs.

Factors to account for:

- Monthly request count passing through the edge.
- CPU time and memory/duration of edge functions.
- Cache hit ratio and origin fetch count.
- Number of subrequests or external API calls.
- Data transfer costs between PoPs and Regions.
- Replication and distributed KV costs.
- Log/trace volume and retention.
- Operational cost of managing multiple Regions, secrets, and policies.

If the edge merely adds a network hop without yielding cache hits, reducing payload sizes, or improving routing, it can increase both latency and cost. Evaluate using end-to-end metrics and total system cost, not just edge invocation pricing.

## 15. Common Design Mistakes

| Mistake | Consequence | How to avoid |
|---|---|---|
| Assuming edge compute means data is near the client | Requests stay slow when calling a database in a distant Region | Measure edge-to-origin latency and data locality separately |
| Assuming a Java JAR runs in any edge runtime | Build or runtime failures from missing JVM/APIs/native ABI | Verify supported languages, ABI, and APIs |
| Putting transactions in eventually consistent edge KV | Stale reads/writes or business conflicts | Keep transactions in the owning service/database |
| Caching personalized responses in a shared cache | Data leakage across users/tenants | Safe Cache-Control and cache keys; `private`/`no-store` where needed |
| Trusting edge-added headers while the origin remains public | Clients forge identity headers and bypass the edge | Block direct origin access or sign/verify context |
| Retrying a `POST` to another origin after a timeout | Triggers side effects twice | Use idempotency keys and reconciliation |
| Streaming large files through an edge body | Exceeds memory/body/duration limits | Upload directly to object storage |
| Storing state in global/static memory | State disappears on isolate eviction or scaling | Use an appropriate durable store |
| Measuring from only one city | Misses latency issues across ISPs/PoPs | Multi-region synthetic and real-user monitoring |
| Replicating data without versioning/consistency rules | Users see stale data or overwrite changes | Versioning, TTLs, ownership, and conflict resolution |
| Logging entire requests | Leaks tokens, cookies, and PII | Redaction, sampling, and retention controls |
| Pushing all business rules to the edge | Distributed policies are hard to sync and audit | Keep the source of truth in the regional service |

## 16. Decision Process for Running a Task at the Edge

You can follow this process:

1. **Define the latency budget:** how fast do users need a response, and where is time currently spent?
2. **Identify required data:** can the task decide from the request, token, or cache, or does it need database queries?
3. **Check the runtime:** do language, CPU, memory, duration, APIs, networking, package size, and request size meet requirements?
4. **Check data locality:** where does data live, what consistency do replicas offer, and are there residency constraints?
5. **Split the processing:** stateless/lightweight work can run at the edge; transactions, stateful workflows, and Java business logic run in the Region.
6. **Design failure modes:** when the edge or origin fails, do you return an error, fail over, retry, or queue; are side effects idempotent?
7. **Review security:** are caches, tokens, forwarded headers, secrets, logs, and origin access secure?
8. **Run multi-region benchmarks:** compare regional-only vs. edge-enabled across p50/p95/p99, cache hits, errors, and cost.
9. **Roll out safely:** canary by route/region, monitor closely, and keep a rollback plan.
10. **Re-evaluate:** when runtime quotas, data placement, or traffic patterns change, recalculate latency and cost.

A task belongs at the edge when the gains from cutting round trips, caching, or routing outweigh the costs of distributing data, runtime constraints, and operating across many execution points.

## 17. Production Checklist

- **Runtime:** have you verified language, APIs, CPU, memory, duration, payload, and artifact limits for the exact edge product?
- **Java compatibility:** are JVM features, reflection, JNI, filesystem, threads, or native libraries required, and does the runtime truly support them?
- **Data locality:** where do compute, databases, caches, object storage, backups, and logs reside?
- **Consistency:** how stale can replica reads be; do writes have a home Region and conflict rules?
- **Latency:** have you measured client-to-edge, edge compute, edge-to-origin, and database timing separately?
- **Caching:** have cache keys, TTLs, invalidation, and personalized responses been tested?
- **Security:** can the origin be called directly; is forwarded identity verified; are secrets and logs protected?
- **State:** is local memory used only as ephemeral cache; does durable data have an appropriate store?
- **Retries:** do non-idempotent requests have keys and reconciliation; can the edge accidentally retry side effects?
- **Uploads:** do large files go straight to object storage instead of passing through an edge function?
- **Observability:** do trace IDs span edge/Region; are dashboards segmented by PoP, client region, and origin region?
- **Cost:** have invocations, CPU, subrequests, replication, egress, storage, and telemetry been factored in?
- **Recovery:** are canary rollouts, rollbacks, origin failover, and runbooks ready when a PoP/Region fails?

## 18. Conclusion

Edge computing moves logic closer to users, but its benefits depend on the runtime, the path to data, and the ability to cache or eliminate round trips. Edge runtimes typically impose strict limits on CPU, memory, duration, package size, OS APIs, and networking; full Java/JVM applications cannot be assumed to run unmodified on every edge platform.

Separate compute location from data location and measure latency per hop. The edge fits lightweight verification, rewrites, routing, caching, and stateless handling; Java functions in a Region fit business logic, transactions, databases, large files, and durable workflows. For distributed data, define ownership, consistency, replication lag, residency, and idempotency before pushing writes to multiple locations.

A solid edge/serverless architecture does not place everything in the nearest PoP. It places each part of the workload where the runtime fits, data is safely accessible, and total latency and cost meet user goals.
