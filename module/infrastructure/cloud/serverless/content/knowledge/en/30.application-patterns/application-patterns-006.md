# Building a Serverless Backend for Web and Mobile Applications

A web or mobile application typically needs a backend to authenticate users, enforce permissions, persist data, execute business logic, accept file uploads, send notifications, and synchronize state across devices. In a serverless architecture, backend capabilities are deployed as APIs, Java functions, event handlers, and workflows managed by the cloud platform. The engineering team focuses on API contracts, business logic, data modeling, and operations; the platform provides execution, scaling, and managed service integrations based on configuration.

Serverless does not eliminate backend architecture. An application still requires security boundaries, data models, authorization, load control, idempotency, observability, cost management, and deployment strategies. Merely turning every endpoint into a function without considering end-to-end business flows can lead to chatty invocations, inconsistent data, or unpredictable costs.

In the **CLOUD_SERVERLESS** module, learners build Java functions triggered by HTTP, messages, or events, handling state, permissions, retries, idempotency, cold starts, scaling, and cost to determine when FaaS is appropriate. This guide walks through building a serverless backend for both web and mobile clients—covering overall architecture, APIs, identity, data, realtime updates, offline sync, security, testing, and deployment.

## 1. Goals and Requirements of a Web/Mobile Backend

The backend must provide a stable set of capabilities across diverse client types:

- Web browsers running on desktop or tablet.
- Native iOS and Android applications.
- Cross-platform applications.
- Admin portals or internal tools.
- Partner integrations or webhooks from external systems.

Different clients have distinct characteristics. Browsers generally have relatively stable connectivity and can use cookies/sessions. Mobile clients face flaky networks, app suspension, offline usage, and requests retried after an app restarts. A resilient backend API must handle these conditions without assuming clients stay online or send each request only once.

Common capabilities:

| Capability | Backend Responsibility |
|---|---|
| Identity | Sign-in, token verification, session refresh/revocation |
| Profile | Reading and updating user information |
| Authorization | Enforcing permissions per user, tenant, resource, and action |
| Business APIs | Processing orders, payments, content, or domain logic |
| Data access | Persisting, querying, paginating, and ensuring consistency |
| File/media | Accepting uploads, validating, processing, and distributing files |
| Async processing | Queues, events, and workflows for long-running tasks |
| Realtime | Push events, WebSockets, or Server-Sent Events |
| Notifications | Sending emails, SMS, or mobile push notifications |
| Offline sync | Synchronizing changes and resolving conflicts |
| Observability | Logs, metrics, traces, audits, and alerts |
| Administration | Managing configuration, tenants, and operations |

Not every application needs all capabilities. Start from real user journeys and SLAs, then add components as requirements demand.

## 2. Reference Architecture

A common architecture places an API gateway in front of Java functions. Functions interact with databases, caches, object storage, and downstream services. Long-running tasks are offloaded to queues or workflows, and results can be delivered via push or realtime channels.

~~~mermaid
flowchart TD
    W[Web browser] --> EDGE[CDN / WAF]
    M[Mobile app] --> EDGE
    EDGE --> API[API Gateway]
    API --> AUTH[Identity provider / JWT validation]
    API --> F1[Java API functions]
    F1 --> DB[(Database)]
    F1 --> CACHE[(Cache)]
    F1 --> OBJ[(Object storage)]
    F1 --> Q[Queue / Event bus]
    Q --> F2[Worker functions]
    F2 --> WF[Workflow / orchestration]
    WF --> EXT[External services]
    F2 --> DB
    F2 --> OBJ
    F2 --> PUSH[Push / realtime service]
    PUSH --> W
    PUSH --> M
    F1 --> OBS[Logs / metrics / traces]
    F2 --> OBS
    API --> OBS
~~~

Each component can use managed cloud services or equivalent offerings. The diagram depicts logical responsibilities rather than requiring a separate service for every box. In smaller applications, a few functions can cover related use cases; as load, permissions, or lifecycles diverge, split them into separate functions or services.

### Synchronous Request Flow

1. Client calls the API over HTTPS.
2. Gateway checks TLS, routing, request size, and throttling.
3. Identity provider or authorizer verifies the token/session.
4. Java function validates input and enforces resource-level authorization.
5. Function executes a database transaction or calls dependencies.
6. Function returns a response conforming to the API contract.
7. Gateway and application emit telemetry carrying a correlation ID.

### Asynchronous Processing Flow

1. Client submits a command or task-creation request.
2. API function validates the request and persists initial state.
3. Function enqueues an event or starts a workflow.
4. API returns `202 Accepted` with an operation ID.
5. Worker processes the job, updates state, and stores outputs.
6. Client polls operation status or receives a push notification.
7. Client fetches the result via API once status reaches completion.

Never hold an HTTP request open for extended periods waiting on video transcoding, report generation, or multi-step workflows. Use an operation resource backed by durable state so clients can recover cleanly after timeouts or app restarts.

## 3. Choosing an API Gateway and Backend Boundaries

An API gateway serves as the entry point for HTTP APIs. Gateways typically handle routing, TLS, authentication integration, throttling, payload size limits, access logging, and function integration. Platforms offer REST, HTTP, WebSocket, or GraphQL gateways with varying features and pricing models.

Responsibilities suited for the gateway:

- TLS termination and custom domains.
- Routing and stages/versions.
- Request size limits and throttling.
- CORS policies.
- Token validation if supported by the gateway.
- WAF or abuse-prevention rules.
- Access logs and request correlation.
- Simple mappings between HTTP requests and backend targets.

Responsibilities belonging in the backend:

- Business validation.
- Resource- and tenant-level authorization.
- Transactions and data consistency.
- Idempotency.
- Domain rules and side effects.
- Error mapping per the API contract.

Never rely on the gateway to replace domain authorization. A valid token only proves identity or claims; it does not prove a user has permission to modify whatever resource ID the client supplies.

## 4. Choosing REST, GraphQL, and Backend-for-Frontend

REST suits explicit resources and commands: `GET` profile, `POST` orders, `PATCH` preferences, `GET` operation status. It is straightforward to cache, observe, and support across web and mobile clients.

GraphQL helps when clients need flexible queries across multiple resources and can reduce over-fetching. However, you must enforce query depth limits, complexity budgets, resolver fan-out controls, field-level authorization, and caching. A single GraphQL request can trigger numerous backend operations; simple HTTP request limits are insufficient protection.

A Backend-for-Frontend (BFF) is an API layer tailored to a specific client type or experience. Use a BFF when web and mobile clients have distinct payload shapes, authentication flows, or release cadences. Avoid creating separate BFFs per client if they merely proxy requests and multiply operational overhead.

| Option | When Suitable | What to Manage |
|---|---|---|
| Shared REST API | Web and mobile share similar resources and use cases | Versioning and response compatibility |
| GraphQL | Clients require flexible queries across multiple sources | Query cost, resolver authorization, and caching |
| BFF | Clients have distinct UX, payload, or release needs | Code duplication and ownership |
| WebSocket API | Bidirectional communication and continuous updates | Connection lifecycle and fan-out |
| Async operation API | Long-running or multi-step tasks | Durable status, retries, and polling |

## 5. Designing a Stable API Contract

An API contract is the agreement between client and backend. It should specify:

- HTTP methods and paths.
- Request and response schemas.
- Required, optional, and default fields.
- Validation rules.
- Authentication and authorization requirements.
- Error codes and error body formats.
- Pagination, filtering, and sorting.
- Idempotency semantics.
- Timeouts and asynchronous behavior.
- Versioning and deprecation policies.

Example:

~~~http
POST /v1/orders
Authorization: Bearer <access-token>
Idempotency-Key: 8d7e1a4c-...
Content-Type: application/json

{
  "items": [
    {"productId": "P-100", "quantity": 2}
  ],
  "shippingAddressId": "ADDR-8"
}
~~~

A successful response might be:

~~~http
HTTP/1.1 201 Created
Location: /v1/orders/ORD-9001
Content-Type: application/json

{
  "id": "ORD-9001",
  "status": "PENDING",
  "createdAt": "2026-11-17T10:15:30Z"
}
~~~

If the operation requires extended processing, the API can return:

~~~http
HTTP/1.1 202 Accepted
Location: /v1/operations/OP-3001
Retry-After: 3
Content-Type: application/json

{
  "operationId": "OP-3001",
  "status": "ACCEPTED",
  "statusUrl": "/v1/operations/OP-3001"
}
~~~

Never expose internal stack traces, SQL messages, or secrets in error responses. Clients need stable error codes and a correlation ID to assist users or file support requests.

## 6. Authentication for Web and Mobile

Authentication establishes which principal the client represents. For web and mobile apps, OpenID Connect (OIDC) or OAuth 2.0 via an identity provider is standard.

Principles:

- Use Authorization Code Flow with PKCE for native/mobile public clients.
- Browser apps should consider a BFF with `Secure`, `HttpOnly`, `SameSite` cookies to reduce token-theft exposure.
- Never embed client secrets in mobile apps or SPAs; public client binaries and bundles can be extracted.
- Access tokens should enforce appropriate audience, issuer, expiration, and scopes.
- Refresh tokens should use rotation and reuse detection when supported by the provider.
- Logout/revocation must have clear semantics; deleting tokens client-side does not automatically invalidate already-issued tokens.
- The backend must verify signature, issuer, audience, expiration, and claims per policy.
- Never accept a token merely because its JWT payload decodes cleanly.

### Access Tokens and Refresh Tokens

Access tokens typically have short lifetimes for calling APIs. Refresh tokens obtain new access tokens and require stricter protection. Avoid storing long-lived tokens in browser `localStorage` when safer alternatives exist. Mobile apps should store tokens in OS-provided secure storage.

Do not build custom password handling, token issuance, and cryptography when a battle-tested identity provider is available. If the backend manages identity directly, properly implement password hashing, MFA, account recovery, brute-force defenses, credential-stuffing mitigation, and session revocation.

## 7. Authorization and Tenant Isolation

Authentication does not replace authorization. After verifying the principal, functions must verify whether that principal is permitted to perform the requested action on the target resource.

An authorization decision may depend on:

- Subject: user, service, or role.
- Action: read, update, delete, approve.
- Resource: order, document, tenant, or project.
- Context: ownership, tenant, state, location, or risk level.
- Policy: role-based, attribute-based, or relationship-based.

For instance, a user with the `CUSTOMER` role may only read orders belonging to accounts/tenants they are authorized to access. Never trust a `tenantId` or `ownerId` supplied by the client without cross-checking verified claims and authoritative data.

### Enforcing Permissions on Every Request

1. Verify the token at the gateway or backend.
2. Extract subject and tenant claims from the verified identity.
3. Load the resource using a tenant-scoped key.
4. Check whether the action is allowed on that resource.
5. Execute changes within a transaction when possible.
6. Emit an audit event for sensitive actions.

Default to deny. Direct access paths to functions, databases, object storage, or queues must also be locked down via IAM and network policies; never assume all traffic passes through the API gateway.

## 8. Designing Java Functions for APIs

An HTTP-handling Java function should focus on a single use case or cohesive group of use cases sharing security, scaling, and deployment boundaries. Keep handlers thin: parse the request, verify context, invoke the application service, and map the response. Keep business rules inside the domain/application layer so they are easy to unit-test and reuse from event consumers.

Cloud-provider-agnostic handler example:

~~~java
public final class CreateOrderHandler {
    private final CreateOrderService service;
    private final RequestMapper mapper;
    private final ResponseMapper responses;

    public HttpResponse handle(HttpRequest request) {
        AuthenticatedPrincipal principal =
                request.authenticatedPrincipal();

        CreateOrderCommand command =
                mapper.toCommand(request.body());

        CreateOrderResult result =
                service.create(principal, command,
                        request.header("Idempotency-Key"));

        return responses.created(result);
    }
}
~~~

This is pseudocode; real adapters depend on the runtime and API gateway integration. Handlers must not trust actor or tenant fields parsed from the request body; rely on the identity context verified by the authorizer or middleware.

### Safely Reusing the Execution Environment

You can initialize SDK clients, serializers, or connection pools at class scope for reuse across invocations when the runtime preserves execution environments. However:

- Never store user-specific state in static fields.
- Never cache one request's access token for subsequent requests.
- Never assume an instance processes only one request at a time when concurrency is enabled.
- Connections can go stale after idle periods; implement bounded reconnects and retries.
- Avoid side effects during class initialization that slow cold starts or make deployments unpredictable.

## 9. Choosing a Data Storage Model

Choose databases based on access patterns and transaction requirements—not just the "serverless" label.

| Model | Suitable For | Considerations |
|---|---|---|
| Managed relational database | Relationships, ACID transactions, constraints, complex SQL | Connection management, capacity, and connection cold starts |
| Serverless relational | Variable traffic needing SQL and transactions | Scaling behavior, min/max capacity, and connection proxies |
| Key-value/document database | Key lookups, well-defined access patterns, high throughput | Partition keys, secondary indexes, and query flexibility |
| Object storage | Files, media, reports, immutable artifacts | Store metadata/indexes in a separate database |
| Cache | Sessions/cacheable data, latency reduction | TTLs, invalidation, never use as source of truth |
| Search index | Dedicated full-text search and faceted filtering | Index synchronization and eventual consistency |

Domain data with complex relationships typically fits a relational model. Event logs or aggregates with predictable access patterns often fit document or key-value stores. Object storage suits large binary content while databases track metadata, ownership, status, and object references.

Do not store large files directly inside databases or HTTP responses when object storage and direct uploads are more appropriate.

## 10. Data Models and Transaction Boundaries

A backend must define clear aggregates and transaction boundaries. For example, creating an order may require persisting the order header, line items, inventory reservation, and an outbox event. If all reside in a single transactional database, internal changes can commit atomically.

Never assume a transaction can span databases, queues, payment providers, and email services. For external side effects, use sagas/workflows, outbox/inbox patterns, and compensations.

An order creation flow:

1. Authenticate the user and verify purchasing permissions.
2. Create the order in `PENDING` state.
3. Reserve inventory or emit a reservation command.
4. Authorize payment.
5. Confirm the order or transition to a review/action state.
6. Emit an event to trigger notifications.
7. If a downstream step fails, execute business-rule compensations.

Persist explicit state transitions so clients always read consistent state. Never use a single boolean `isComplete` flag to represent a multi-state workflow.

## 11. Multi-Tenancy and Data Isolation

SaaS applications often serve multiple tenants. Define an explicit isolation model:

- Shared tables with a tenant key.
- Separate schemas per tenant.
- Separate databases per tenant.
- Dedicated accounts/projects for tenants or customer tiers with strict isolation requirements.

Shared tables reduce operational overhead but require every query and write to enforce tenant scoping. Design repository APIs that require a verified `TenantContext`, include tenant dimensions in unique keys, and enable database row-level security policies where appropriate.

Never build tenant context from arbitrary request headers. Gateways may forward verified claims, but functions must still confirm tenant membership. Treat cross-tenant access tests as a dedicated security test suite.

## 12. Caching and Content Delivery

CDNs can cache static assets, image derivatives, and public responses. Backend caches reduce database reads and external dependency calls.

Key design considerations:

- Cache keys must include every dimension that affects the response.
- Never cache private responses in a shared cache without strict partitioning.
- Align TTLs with data freshness requirements.
- Invalidate caches promptly when underlying data changes.
- Protect hot keys against cache stampedes.
- Consider `stale-while-revalidate` when brief staleness is acceptable.
- Never treat a cache as the authoritative source of truth.

For web and mobile apps, distribute static content via CDN whenever appropriate. Personalized API responses need explicit cache policies; misconfigured `Cache-Control` headers can leak data between users.

## 13. File Uploads from Web and Mobile

By default, do not route large uploaded files through API Gateway and functions. The standard pattern has the backend issue an upload session so the client uploads directly to private object storage using a short-lived, tightly scoped URL or token.

Upload flow:

1. Client calls `POST /uploads` to request an upload session.
2. Backend checks user identity, quotas, allowed file types, and size limits.
3. Backend generates a randomized object key in a quarantine area.
4. Backend returns a short-lived upload URL or multipart upload instructions.
5. Client uploads directly to object storage.
6. Client signals completion or storage emits an object-created event.
7. Backend verifies the object, checksum, size, and ownership.
8. Pipeline scans/validates and processes the file.
9. Metadata transitions to `READY` or `REJECTED`.
10. Client polls status and obtains an access-controlled download URL.

Never use the client-supplied filename as the object key. Never trust client-declared MIME types, extensions, or metadata. Inspect content signatures/magic bytes and enforce decompression limits.

### Upload Sessions

An upload session can track:

- `uploadId` and owner/tenant.
- Server-generated object key.
- Expected size and permitted content types.
- Checksum algorithm and value if provided.
- Expiration time and status.
- Multipart upload ID when applicable.
- Idempotency key and correlation ID.

A presigned URL is a bearer capability: anyone holding it can exercise its granted permissions until it expires or is revoked per provider mechanisms. Never log full presigned URLs, guard against referrer leakage, and scope permissions strictly to the target object, HTTP method, and TTL.

### Multipart and Resumable Uploads

For large files or unstable mobile networks, multipart/resumable uploads send chunks independently and resume after dropped connections. The backend must manage:

- Part sizes and maximum part counts.
- Per-part checksums or overall checksums per storage semantics.
- Expiration and aborting incomplete uploads.
- Idempotency of the completion operation.
- Cleanup of orphaned multipart uploads.
- Concurrent upload limits and overall storage quotas.

ETags are not always the MD5 of the entire object, especially with multipart uploads or encryption. Rely on checksum semantics documented by your storage provider.

## 14. Asynchronous Processing Pipelines

A completed upload does not mean a file is safe or ready for other users. Use queues and events to drive malware scanning, metadata extraction, thumbnailing, transcoding, or OCR.

~~~mermaid
flowchart TD
    A[Client requests upload session] --> B[API validates identity and quota]
    B --> C[Private quarantine object]
    C --> D[Object-created event]
    D --> E[Ingestion queue]
    E --> F[Validate size, type and checksum]
    F --> G[Malware / content scan]
    G -->|Accepted| H[Processing workflow]
    G -->|Rejected| R[Quarantine / reject]
    H --> I[Image / video / document workers]
    I --> J[Private derived objects]
    J --> K[Metadata and status update]
    K --> L[READY event]
    L --> M[Client status / notification]
~~~

Stages require durable state, retry policies, timeouts, and DLQs. Workers must be idempotent because events can be redelivered. Never make objects public or issue download URLs before inspection and processing succeed per policy.

## 15. Image Processing

Image processing typically covers:

- Verifying actual format and decoding cleanly.
- Enforcing width, height, pixel count, and file size limits.
- Applying EXIF orientation rotation.
- Stripping or sanitizing EXIF metadata, especially GPS coordinates.
- Generating thumbnails and responsive sizes.
- Converting formats based on client/browser support.
- Optimizing quality and compression.
- Recording metadata such as dimensions, color profile, and checksum.

Guard against decompression bombs: small compressed files that expand into massive bitmaps in memory. Cap pixel counts, memory, and processing time. Offload CPU/memory-heavy image work to dedicated workers rather than running synchronously in API functions.

Derived objects should carry keys/versions bound to the source object version and processor version. When algorithms change, new derivatives can be generated without overwriting versions currently read by clients.

## 16. Video and Long-Form Media Processing

Video consumes far more compute, time, and storage than images. A pipeline can:

1. Validate container/codec and duration.
2. Extract metadata and poster thumbnails.
3. Generate renditions or adaptive bitrate outputs.
4. Generate captions/subtitles if speech-to-text is enabled.
5. Detect decode errors or truncated files.
6. Record processing state and completion time.
7. Distribute via CDN or streaming origin.

Do not process long videos inside a single function invocation if it approaches timeout or memory limits. Use managed transcoding services, container/batch workers, or multi-step workflows. Track job state and support cancellation if a user deletes or replaces the media.

When outputs span multiple segments, manifests, and thumbnails, publish the completed version only after all required artifacts are verified. Never expose a manifest pointing to segments that have not finished uploading.

## 17. Document Processing and OCR

Document pipelines may perform:

- Detecting PDF, DOCX, XLSX, TXT, or other allowed formats.
- Malware scanning.
- Checking for encrypted or password-protected files.
- Extracting text and metadata.
- Running OCR on scanned pages/images.
- Splitting pages or chunking text.
- Classifying documents and extracting structured fields.
- Storing results with versions and confidence scores.
- Routing low-confidence extractions to human review.

PDF, Office, and archive parsers carry large attack surfaces. Run them in sandboxed environments or least-privilege workers with strict caps on memory, CPU, file descriptors, network egress, and execution time. Never allow parsers to fetch arbitrary URLs embedded inside documents, which introduces SSRF risks.

OCR and extraction outputs can contain errors. Store provenance, model/processor version, page references, and confidence scores; never treat unvalidated extracted fields as authoritative for critical decisions.

## 18. Queue and Event Design

Events should describe what happened or the command to execute, with an explicit schema version.

Example event:

~~~json
{
  "eventId": "evt-82c1",
  "eventType": "upload.accepted",
  "schemaVersion": 1,
  "occurredAt": "2026-11-17T10:15:30Z",
  "tenantId": "tenant-42",
  "uploadId": "upl-9001",
  "object": {
    "key": "quarantine/tenant-42/obj-random",
    "versionId": "v-17",
    "sizeBytes": 2457600,
    "checksum": "sha256:..."
  },
  "correlationId": "corr-31"
}
~~~

Never put raw file contents, access tokens, or presigned URLs inside events. Events carry object references and necessary metadata; workers read objects using least-privilege IAM roles.

Event contracts must define compatibility rules. Adding optional fields is usually safer than changing the meaning of existing fields. When breaking semantics or required fields, bump `schemaVersion` and plan the migration.

## 19. Idempotency and Duplicate Handling

Queues and event buses typically provide at-least-once delivery or retry after timeouts, meaning an event may execute multiple times. Idempotency ensures repeated processing does not duplicate side effects.

Useful keys:

- Stable producer-generated `eventId`.
- `uploadId + object version`.
- Business operation ID.
- Client `Idempotency-Key` for HTTP commands.

An inbox table with a unique constraint on `eventId` or a composite key blocks duplicates. Workers should persist state and results within the same transaction when side effects live in the same database.

Never track processed events solely in memory. A function can terminate after committing a side effect but before acknowledging the message. Upon redelivery, durable state determines whether work needs to run again.

For external services, pass idempotency keys if supported by the provider. Otherwise, record external references and reconcile before retrying operations that may have succeeded.

## 20. Workflows for Multi-Step Tasks

Workflows fit pipelines with multiple stages, branching, timeouts, retries, callbacks, or compensations.

Example document processing workflow:

1. `ValidateUpload`.
2. `ScanMalware`.
3. `ExtractMetadata`.
4. `DetectDocumentType`.
5. `RunOCR` if required.
6. `ValidateExtractedFields`.
7. `StoreDerivedContent`.
8. `MarkReady`.
9. `NotifyOwner`.

Keep each step's input and output small, with explicit timeouts and retry policies. Store large objects in object storage; keep only object references, IDs, and essential metadata in workflow state. Avoid embedding binary payloads in workflow state due to size limits, cost, and observability overhead.

Workflow engines do not automatically guarantee external side effects happen only once. Individual tasks still need idempotency, and compensations require clear business semantics. If a workflow restarts after a failure, already-committed tasks must not repeat side effects.

## 21. Realtime Updates: WebSockets, SSE, and Polling

Clients tracking orders, uploads, or processing jobs have several options:

| Mechanism | Suitable For | Trade-Offs |
|---|---|---|
| Polling | Simple, low-frequency updates | Repeated requests and interval-based latency |
| Long polling | Server holds request until update or timeout | Connection management and gateway timeouts |
| Server-Sent Events | Unidirectional server-to-browser push | Client-to-server actions still use separate HTTP requests |
| WebSockets | Bidirectional, low-latency realtime | Connection lifecycle, auth refresh, and fan-out |
| Mobile push | Alerts when app is backgrounded or offline | Non-instant delivery and tight payload limits |

Polling should use backoff: poll briefly right after submission, then increase intervals up to a cap. Return `Retry-After` so clients respect backend load. Stop polling once an operation reaches a terminal state.

WebSocket connections drop when mobile devices switch networks or background the app. Clients must reconnect, re-authenticate, and fetch a state snapshot before applying new events to avoid gaps.

## 22. Push Notifications

Push notifications alert mobile users when changes need attention. The backend stores device tokens/registrations per user and device, managing token rotation, unsubscribes, and invalid-token cleanup.

Never put sensitive data inside push payloads if lock screens can display them. Send a lightweight notification containing event type and reference; the client calls an authenticated API to load details.

Push providers do not guarantee the user read or the app processed a notification. Notifications can be delayed, duplicated, or dropped. Authoritative business state must live in the backend; push is merely a wake-up signal.

## 23. Offline-First and Mobile Sync

Mobile apps may generate mutations while offline. Apps should maintain a local operation queue and synchronize once connectivity returns.

A sync request can carry:

- Stable `operationId`.
- `entityId`.
- `baseVersion` or ETag.
- Operation type.
- Validated payload.
- Client timestamp and device/session reference if needed.
- Idempotency key.

The backend authenticates the user, checks versions, and applies conflict policies. Never trust client timestamps as authoritative ordering, since device clocks can be wrong.

### Conflict Resolution

Common strategies:

- Last-write-wins: simple, but risks overwriting critical edits.
- Optimistic concurrency via version/ETag: rejects updates if `baseVersion` is stale.
- Field-level merge: merges non-conflicting fields automatically.
- Domain-specific merge: suited for shopping carts, checklists, or collaborative data.
- Human resolution: prompts the user when automated merging is unsafe.

Never apply one strategy blindly to every entity. User preferences might use last-write-wins, whereas inventory or payments demand strict transactions and invariants.

### Delta Sync

Instead of re-downloading the entire dataset, the backend can return changes since a sync cursor. Cursors must be stable, carry expiration semantics, and never leak data across tenants. When a cursor expires or a client falls too far behind, provide a controlled full resync.

## 24. Pagination, Filtering, and Search

List APIs require pagination to prevent oversized responses. Cursor-based pagination suits continuously changing datasets better than offset pagination in most cases.

An example response:

~~~json
{
  "items": [
    {"id": "ORD-1", "status": "READY"}
  ],
  "nextCursor": "opaque-cursor-value"
}
~~~

Cursors should be opaque and either signed or looked up server-side; never allow clients to tamper with sort keys or tenant scopes. Cap page sizes and allowlist filter/sort fields. For complex search, use a dedicated search service or index instead of constructing arbitrary ad-hoc database queries.

## 25. Rate Limiting and Backend Protection

Gateways and backends should enforce limits across multiple dimensions:

- IP/network source.
- User/principal.
- Tenant/customer tier.
- API route and operation cost.
- Login attempts or OTP destinations.
- Upload sizes and concurrent uploads.
- WebSocket connections and message rates.
- Background job admission.

A single global rate limit is rarely enough: one large tenant can starve everyone else. Use per-tenant quotas and concurrency limits where fairness matters. Base limits on downstream capacity and SLAs.

Return `429 Too Many Requests` with `Retry-After` when appropriate. Clients should use exponential backoff with jitter rather than synchronized retries. Commands with side effects must always include an idempotency key.

## 26. API and Data Security

Essential controls:

- HTTPS/TLS for all clients.
- Appropriate OIDC/OAuth flows per client type.
- Full JWT or session validation.
- Resource- and tenant-level authorization.
- Input validation and context-aware output encoding.
- SQL/NoSQL injection prevention via parameterized queries.
- Strict CORS allowlists for browser origins.
- CSRF protection when using cookie authentication.
- XSS defenses in both frontend rendering and response handling.
- WAF, throttling, and bot/abuse controls.
- Secrets manager and least-privilege IAM.
- Encryption at rest and in transit.
- Audit logging for sensitive actions.
- Never logging tokens, passwords, secrets, or raw sensitive payloads.

CORS is not authorization. CORS is primarily browser enforcement; mobile apps and scripts can call APIs directly. The backend must still authenticate and authorize every request.

If using cookie sessions for browsers, configure `Secure`, `HttpOnly`, appropriate `SameSite` attributes, and CSRF tokens/defenses. If using bearer tokens, avoid storing long-lived tokens where untrusted JavaScript can read them.

## 27. Upload Security and Handling Untrusted Content

User-uploaded files are untrusted input. Required controls:

- Allowlist permitted content types and file sizes.
- Magic-byte and content inspection.
- Malware scanning or sandboxing.
- Limits on archive entry counts, nesting depth, and uncompressed size.
- Running parsers inside sandboxes or least-privilege workers.
- Disabling macro/script execution and arbitrary HTML rendering.
- Blocking parsers from making arbitrary network calls.
- Generating object keys server-side.
- Keeping files in private quarantine until accepted.
- Verifying ownership prior to downloads.
- Safe `Content-Disposition` and `Content-Type` headers when serving files.
- Lifecycle policies to delete rejected or abandoned files.

If previews are served, serve them from a separate origin/domain or sandboxed context so user-uploaded content never executes in the same origin holding application session cookies.

## 28. Privacy and User Data Management

Web/mobile backends commonly handle profiles, locations, devices, files, and user activity. Establish:

- Purpose for collecting each field.
- Data classification and sensitivity level.
- Consent or legal basis per applicable regulations.
- Data residency and cross-Region transfer rules.
- Retention and deletion lifecycles.
- Access logging and audits.
- Encryption and key ownership.
- Data export and account deletion workflows.
- Backup retention and how deleted user data is handled in backups.
- Data masking in dev/test environments and logs.

Do not collect data merely because it is easy to capture. Minimize personal data in logs. For account deletion, process databases, object storage, search indexes, caches, notification registrations, and downstream processors per policy, retaining only compliant audit evidence without keeping the deleted personal data.

## 29. Reliability: Timeouts, Retries, and Circuit Breakers

Every API and dependency call needs an explicit timeout. Client, gateway, function, and downstream timeouts must align. If the gateway times out before the function finishes, the client may retry even though the operation committed.

Principles:

- Short timeouts for synchronous requests.
- Offload long tasks to async operations.
- Retry only transient failures.
- Use exponential backoff with jitter.
- Enforce per-operation retry budgets.
- Apply circuit breakers or bulkheads around unstable dependencies.
- Enforce idempotency on commands.
- Route unprocessable messages to a DLQ.
- Implement compensations for multi-step workflows.
- Gracefully degrade non-critical capabilities.

Never retry validation, authorization, or schema errors without changing the input. Retry storms can overload a struggling backend far worse than the original incident.

## 30. Performance, Cold Starts, and Concurrency

Cold starts impact latency whenever a new execution environment spins up. For Java, measure class loading, dependency initialization, framework startup, connection establishment, and JIT warm-up.

Optimizations:

- Keep the dependency graph lean.
- Choose frameworks and startup modes suited to serverless runtimes.
- Reuse SDK/HTTP clients safely.
- Minimize reflection and classpath scanning where unnecessary.
- Keep deployment artifacts small and avoid eagerly initializing unused services.
- Measure p50/p95/p99 for both cold and warm invocations.
- Consider provisioned/warm capacity for routes with strict latency objectives.
- Benchmark memory/CPU profiles rather than picking the smallest setting.

Concurrency must be bounded by database connections, API quotas, and downstream capacity. Functions scaling faster than a relational database can cause connection storms. Use reserved concurrency, queue buffering, connection proxies/pools, and backpressure.

## 31. Observability and Correlation

A single user action can traverse the gateway, multiple functions, queues, workflows, databases, and push providers. Propagate a correlation ID or trace context across all components.

Monitor:

- Request rates, error rates, and p50/p95/p99 latencies.
- Authentication and authorization denials.
- Throttling and `429` responses.
- Function duration, cold starts, concurrency, and throttles.
- Database connections, query latency, and throttling.
- Queue depth, oldest message age, retries, and DLQ counts.
- Workflow durations and failed states.
- Upload sizes, scan durations, and processing status.
- Push delivery outcomes and invalid device tokens.
- Cost per successful business operation.

Emit structured JSON logs with `requestId`, `traceId`, tenant-safe references, `operationId`, and function version. Never attach access tokens or sensitive payloads to trace baggage. Avoid using high-cardinality `userId` or `objectId` values as metric labels.

## 32. Cost and Unit Economics

Backend costs span API gateways, function invocations/duration, workflow transitions/executions, queue operations, database capacity/IO, storage GB-months, storage requests, egress, caches, WAF, and observability.

Measure unit cost per business outcome:

\[
CostPerSuccessfulOperation =
\frac{TotalBackendCost}{SuccessfulBusinessOperations}
\]

For instance, one successful upload may trigger an API call for an upload URL, multiple storage operations, an event, several queue operations, three worker invocations, a workflow, and logs/traces. Counting only API requests severely underestimates true cost.

Optimizations:

- Upload directly to object storage rather than proxying binaries through functions.
- Batch messages where appropriate.
- Reduce polling in favor of callbacks or push updates.
- Keep large payloads out of workflow state.
- Apply storage lifecycle tiers matching access patterns.
- Curb duplicate/retry waste through idempotency.
- Trim verbose logs while keeping audit and security events.
- Enforce quotas and TTLs on temporary resources.
- Measure cost per order, upload, or user journey.

Never cut costs by removing security scans, critical audits, or reliability below SLA.

## 33. Testing a Serverless Backend

Test across multiple layers:

| Test Type | Objective |
|---|---|
| Unit tests | Domain rules, validation, mapping, and state transitions |
| Contract tests | Request/response schemas, error semantics, and API compatibility |
| Authorization tests | Users/tenants cannot access resources outside their scope |
| Integration tests | Databases, queues, storage, and identity adapters |
| Event tests | Duplicate, out-of-order, malformed, and replayed events |
| Workflow tests | Retries, timeouts, compensations, and resumes |
| Upload security tests | Spoofed file types, oversized files, archive bombs, and safe malware fixtures |
| Mobile network tests | Timeouts, offline usage, reconnects, and duplicate submissions |
| Load tests | Peak concurrency, throttling, and downstream capacity |
| End-to-end tests | User journeys from login through business outcomes |

Do not test only happy paths. Test request timeouts after commits, expired tokens, tenant mismatches, incomplete uploads, queue duplicates, and worker crashes between side effects and acknowledgements.

## 34. CI/CD and API Version Management

Deployment pipelines should include:

1. Java compilation and unit tests.
2. Static analysis and dependency/security scans.
3. Building immutable artifacts.
4. Generating IaC plans and running policy checks.
5. Integration and contract tests.
6. Deploying to staging.
7. Smoke tests and synthetic transactions.
8. Environment approvals.
9. Canary or gradual rollouts.
10. Monitoring error/latency metrics with automated or rapid rollbacks.

API changes must maintain backward compatibility. Adding optional fields is usually safer than removing or redefining existing fields. Old mobile app versions often remain in the wild for extended periods; the backend must support older clients according to your deprecation policy.

Version APIs via path, header, or schema per your convention. Track client versions to measure adoption before retiring old endpoints. Feature flags allow gradual capability rollouts, but require audits, owners, and expiration dates to avoid permanent flag sprawl.

## 35. Java Example: Idempotent Command for Web/Mobile

The example below shows how to process order creation using an idempotency key. The repository requires unique constraints and transactions; this is pseudocode rather than an adapter for a specific database.

~~~java
public CreateOrderResult create(
        AuthenticatedPrincipal principal,
        CreateOrderCommand command,
        String idempotencyKey) {

    if (idempotencyKey == null || idempotencyKey.isBlank()) {
        throw new ValidationException("Idempotency-Key is required");
    }

    String requestHash = canonicalHash(command);

    return transaction(() -> {
        IdempotencyRecord existing =
                idempotencyRepository.findForUpdate(
                        principal.subject(), idempotencyKey);

        if (existing != null) {
            if (!existing.requestHash().equals(requestHash)) {
                throw new IdempotencyConflictException();
            }
            return existing.resultAs(CreateOrderResult.class);
        }

        authorization.requireCanCreateOrder(principal, command);

        Order order = orderRepository.createPending(
                principal.subject(), command);

        outboxRepository.insert(
                OrderCreatedEvent.from(order));

        CreateOrderResult result =
                CreateOrderResult.accepted(order.id(), order.status());

        idempotencyRepository.insertCompleted(
                principal.subject(),
                idempotencyKey,
                requestHash,
                result);

        return result;
    });
}
~~~

In production implementations, idempotency records may require `PROCESSING`/`COMPLETED` states, leases, or unique inserts to handle simultaneous identical requests. Business updates, outbox inserts, and idempotency results need clear transaction boundaries. For asynchronous workflows, persist the operation ID and return the same operation reference on client retries.

Never use global idempotency keys without owner scoping. Keys should be scoped by principal/tenant and endpoint/operation to avoid collisions or cross-user replays.

## 36. Complete Order Creation Flow Example

~~~mermaid
sequenceDiagram
    participant C as Web/Mobile
    participant G as API Gateway
    participant F as Java API Function
    participant D as Database
    participant Q as Queue
    participant W as Worker/Workflow
    participant P as Push Service

    C->>G: POST /v1/orders + token + idempotency key
    G->>F: Authenticated request
    F->>D: Validate, authorize, create PENDING order
    F->>D: Save idempotency record and outbox
    F-->>G: 202 + operation/order ID
    G-->>C: Accepted
    Q->>W: OrderCreated event
    W->>D: Reserve inventory / update status
    W->>P: Notify client
    P-->>C: Status changed notification
    C->>G: GET /v1/orders/{id}
    G->>F: Authenticated read
    F->>D: Load tenant-scoped order
    F-->>C: Current order status
~~~

This flow demonstrates a fast request returning an operation/order ID, a worker executing asynchronous work, and the client reading authoritative state from the backend. Push only signals a state change; the `GET` API remains the authoritative source of truth.

## 37. Common Design Pitfalls

| Pitfall | Consequence | Fix |
|---|---|---|
| Routing all binaries through API functions | Higher latency, memory pressure, and cost | Direct uploads/downloads via object storage |
| Trusting client-supplied `tenantId` | IDOR and cross-tenant data leaks | Derive tenant from verified identity and check resource ownership |
| Authenticating only at the gateway | Internal paths may bypass authorization | Enforce authorization inside domain/backend services |
| Storing long-lived tokens in apps | High impact from token theft | OIDC/PKCE, OS secure storage, and token rotation |
| Returning `200` before durable writes | Clients believe operations succeeded when lost | Commit state/outbox before responding |
| Holding HTTP requests open for long jobs | Timeouts and uncontrolled retries | `202` + async operation status |
| Omitting idempotency | Double submissions cause duplicate side effects | Stable keys and durable deduplication |
| Processing queues purely in memory | Crashes lose in-flight progress | Durable state, retries, and DLQs |
| Making uploads public immediately | Exposes malicious or unscanned files | Quarantine, scan, and controlled release |
| Treating push as source of truth | Clients miss events and go stale | Store backend state and expose sync APIs |
| Missing offline conflict policies | Overwrites user edits | Versions/ETags and domain-specific merges |
| Caching private responses with wrong keys | Cross-user data leakage | Partition caches properly or skip caching |
| Unbounded list/query endpoints | Expensive queries and huge payloads | Pagination, filter allowlists, and query budgets |
| Unbounded function scaling | Database connection storms | Concurrency caps and backpressure |
| Logging full request bodies | Leaks tokens/PII and inflates cost | Structured logging with redaction |
| Breaking older mobile clients | Outages after backend deployments | Backward compatibility and deprecation windows |
| Retrying all errors | Retry storms and surging costs | Error classification, backoff, and retry budgets |

## 38. Step-by-Step Serverless Backend Build Process

1. **Map user journeys:** identify required web/mobile capabilities and SLAs.
2. **Design API contracts:** methods, schemas, errors, pagination, and versioning.
3. **Choose identity flows:** OIDC/OAuth, sessions, token lifetimes, and refresh flows.
4. **Design authorization:** subjects, tenants, resources, actions, and policies.
5. **Select data models:** databases, object storage, caches, and transaction boundaries.
6. **Define execution boundaries:** Java functions for HTTP, event consumers, and workflow tasks.
7. **Design async flows:** queues, event schemas, idempotency, retries, and DLQs.
8. **Design file flows:** upload sessions, quarantine, scanning, processing, and controlled delivery.
9. **Design realtime/offline:** polling, push, WebSockets, sync cursors, and conflict resolution.
10. **Design security:** IAM, WAF, CORS/CSRF, encryption, privacy, and auditing.
11. **Design reliability:** timeouts, backoff, concurrency caps, backpressure, and compensations.
12. **Design observability:** correlation IDs, metrics, traces, and business outcomes.
13. **Model costs:** cost per successful operation and peak traffic scenarios.
14. **Test thoroughly:** contracts, authorization, duplicates, failures, mobile offline, and load.
15. **Deploy safely:** IaC, CI/CD, canaries, API compatibility, and rollbacks.
16. **Operate continuously:** alerts, runbooks, quota reviews, cost reviews, and deprecations.

## 39. Production Checklist

- **API contract:** schemas, error codes, pagination, idempotency, and versioning are documented.
- **Identity:** browser/mobile clients use proper auth flows; tokens are thoroughly verified.
- **Authorization:** resource- and tenant-level checks execute in the backend.
- **Gateway:** TLS, routes, throttling, CORS, request size limits, and access logs are configured.
- **Java functions:** handlers are stateless, dependencies are safely reused, timeouts and concurrency are bounded.
- **Data:** transaction boundaries, indexes, connection pools, and backups are established.
- **Multi-tenancy:** every query and write is tenant-scoped; cross-tenant tests pass.
- **Async:** queues/workflows maintain durable state, idempotency, retries, DLQs, and replay plans.
- **Uploads:** direct uploads, signed URL TTLs, quarantine, scanning, checksums, and cleanup are in place.
- **Media/documents:** processors enforce resource limits, sandboxes, timeouts, and versioned outputs.
- **Realtime:** reconnects, auth refresh, and snapshot resyncs are supported.
- **Mobile offline:** operation IDs, sync cursors, and conflict policies are defined.
- **Notifications:** device token lifecycles and invalid-token cleanup are automated.
- **Security:** secrets, encryption, WAF, abuse controls, CSRF/XSS defenses, and data minimization are enforced.
- **Privacy:** retention, export, deletion, and data residency are defined.
- **Reliability:** timeouts, retry budgets, backoff, circuit breakers, and compensations are tested.
- **Observability:** traces span gateway/functions/queues/workflows; alerts track business outcomes.
- **Cost:** gateway, compute, workflows, queues, databases, storage, network, and telemetry are forecasted.
- **CI/CD:** immutable artifacts, IaC reviews, canaries, smoke tests, and rollbacks are configured.
- **Compatibility:** backend supports active web/mobile versions per the deprecation policy.
- **Operations:** runbooks are ready for incidents, quotas, DLQs, data restores, and account recovery.

## 40. Conclusion

A serverless backend for web and mobile applications combines API gateways, Java functions, identity providers, databases, object storage, queues, workflows, realtime channels, and notifications tailored to business needs. Synchronous APIs suit fast operations; long-running work belongs in async operations with durable IDs and state. Direct uploads to object storage offload gateways and functions, while queues and workflows handle media, documents, and multi-step business processes.

The most critical architectural decisions center on API contracts, authorization, tenant isolation, transaction boundaries, idempotency, offline conflict resolution, and observability. Mobile clients may retry after timeouts or replay operations after reconnecting; the backend must tolerate duplicates and uncertain outcomes. Push notifications are only signals, while databases and APIs remain the authoritative source of state. Uploaded files must pass through quarantine and validation before release.

Start from user journeys, choose clear function and data boundaries, and design security, reliability, cost controls, and CI/CD from the outset. A great serverless backend not only scales with traffic, but preserves data correctness, proper access control, and a dependable experience when clients go offline, dependencies fail, or workloads spike.
