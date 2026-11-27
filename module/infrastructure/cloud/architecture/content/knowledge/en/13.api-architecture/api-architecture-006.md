# Idempotency Keys and Handling Duplicate Requests

In an API system, a request can be sent multiple times even if the user only clicked a button once. The network drops after the server has written data but before the response reaches the client; a mobile app automatically retries; an API gateway or SDK resends the request after a timeout; a webhook is redelivered by a provider that did not receive an acknowledgment. If each receipt creates a new transaction, customers can be double-booked, double-charged, or have duplicate orders created.

**Idempotency** is the property that allows an operation to be executed repeatedly while the observable outcome remains equivalent to a single execution under defined rules. For APIs that create resources or perform actions with side effects, an **idempotency key** is an identifier supplied by the client or calling system to identify a single business intent. The server uses that key along with scope and request data to recognize duplicate requests, avoid re-executing side effects, and return an appropriate result.

Idempotency is especially critical in cloud architectures because APIs often run across multiple instances, functions can receive duplicate events, load balancers can route requests to different backends, and retry layers can operate independently. A variable in one instance's RAM cannot protect the whole system. Deduplication mechanisms must have **shared scope, atomicity, and recoverability**.

This lesson belongs to the **API Architecture** section of the cloud architecture design module. Its goal is to turn business requirements into APIs and data models that operate reliably while balancing correctness, security, scalability, cost, and observability following a Well-Architected mindset.

After this lesson, you will be able to:

- Explain idempotency and distinguish it from retries, deduplication, and exactly-once delivery.
- Design idempotency keys scoped by tenant, operation, and business context.
- Handle concurrent requests, timeouts, and ambiguous outcomes using durable state and transactions.
- Distinguish same-key/same-payload from same-key/different-payload requests.
- Choose key retention periods, response replay, in-progress handling, and error policies.
- Apply idempotency to HTTP APIs, webhooks, queue consumers, and side-effecting workflows.
- Test, observe, and evaluate duplicate-request protection policies before production.

## 1. Why are requests duplicated?

Clients do not always know whether the server finished an operation. Consider an appointment-booking flow:

1. A customer sends a POST to book an appointment at 10:00.
2. The server writes the booking successfully to the database.
3. The network connection drops before the success response reaches the phone.
4. The client does not know the booking was created and resends the POST.
5. The server receives the second request and could create another booking.

From the user's perspective, the first attempt "never responded." From the server's perspective, the first attempt succeeded. This is an **ambiguous outcome** for the caller.

Common sources of duplicate requests:

| Source | Situation | Risk |
| --- | --- | --- |
| User | Double-clicks button, refreshes, or opens multiple tabs | Creates multiple resources |
| Mobile/web client | Retries after timeout, network loss, or app resume | Does not know whether prior request committed |
| SDK / HTTP client | Automatic policy-based retries | Resends side-effecting POSTs |
| API gateway / proxy | Retries or fails over backend after connection error | Prior request may have reached the application |
| Webhook provider | Replays event because acknowledgment was not received | Processes one event multiple times |
| Queue/event broker | Redelivery on consumer timeout or missing ack | Duplicate side effects |
| Workflow engine | Re-runs step after error or recovers execution | Re-invokes external service |
| Operations staff | Re-triggers job or replays message | Re-executes old operation |

Not every repeated request is an error. A user may intentionally buy two identical items; two bookings with different keys may represent two genuine intents. The goal is to distinguish **one intent sent multiple times** from **multiple independent intents**.

## 2. How does idempotency differ from retries and exactly-once?

These concepts are related, not synonymous:

| Concept | Meaning | What it does not guarantee |
| --- | --- | --- |
| **Idempotency** | Repeating an operation for the same intent creates no extra business outcomes beyond rules | Does not make requests succeed on its own, nor solve all distributed failures |
| **Retry** | Resending an operation upon a potentially recoverable error | Cannot know for sure whether the prior attempt executed |
| **Deduplication** | Detecting and ignoring previously seen messages/requests by key and window | Does not ensure two external side effects commit atomically together |
| **At-least-once delivery** | System delivers at least once, possibly repeatedly | Does not guarantee single execution |
| **At-most-once delivery** | System does not redeliver per published semantics | Can drop operations if failures occur |
| **Exactly-once effect** | Business outcome takes effect once within a defined boundary | Cannot be inferred solely from a queue or transport; requires coordinating data and side effects |

An operation that is idempotent at the HTTP layer can be resent without extra side effects. For instance, PUT setting a resource to a specific state and DELETE removing the same resource are typically designed to be idempotent per HTTP semantics. POST creating a transaction is typically not idempotent without a dedicated mechanism.

**An idempotency key is not a system-wide exactly-once switch.** It helps the server recognize resends of the same intent within a defined scope and window. Databases, message brokers, and external services still retain their own transaction boundaries, retries, and failure modes.

## 3. Choosing keys and defining scope

An idempotency key must distinguish a single business intent and avoid collisions across callers. It can be a random UUID, a client-generated token, or a server-preallocated operation ID.

Example request:

~~~http
POST /v1/bookings
Authorization: Bearer <access-token>
Idempotency-Key: 3d7f5d6a-7d50-4f5b-9d5b-1e4b9b2a6f81
Content-Type: application/json

{
  "doctorId": "doc-42",
  "slotId": "slot-2026-11-18-1000"
}
~~~

The key in this example only illustrates format. Never use access tokens, emails, card numbers, or personal data as keys. Keys are not credentials and do not replace authentication or authorization.

### 3.1. Unique key scope

Using only the raw key as a globally unique key risks collisions or leaking results across callers. Scope usually needs to combine:

- **Principal or tenant:** authenticated customer, merchant, API client, or organization.
- **Operation:** operation type, endpoint, or business action.
- **Key:** intent identifier supplied by the caller.

A logical identifier might look like:

~~~text
scope = tenant_id + operation_name + idempotency_key
~~~

For example, if Tenant A and Tenant B accidentally use the same key string request-001, they must be treated as two independent scopes. Likewise, the same tenant using the same key for CreateBooking and CancelBooking is not necessarily the same intent.

Choosing specific scope components:

| Scope component | Question |
| --- | --- |
| Tenant/principal | Who owns the intent? Are keys shared among users in an organization? |
| Operation | Does the same key on two endpoints count as the same operation? |
| Resource/account | Does it need scoping to a payment account or specific order? |
| Environment | Could sandbox keys collide with production? |
| Version | Does an API semantics change require a new namespace/version? |

Scope must remain stable throughout the retry lifecycle. Never derive scope from unauthenticated client-controlled headers. The server must take tenant/principal from verified identity.

### 3.2. Client-generated or server-generated keys?

For APIs where clients resend after timeouts, clients typically generate the key **before the first attempt** and keep the same key across retries of the same intent. Generating a new UUID on every retry makes the server see independent operations and prevents deduplication.

For webhooks, the provider typically supplies an event ID or delivery ID. The server can use that ID as part of the idempotency scope after verifying signatures and origin.

For internal jobs, a scheduler/workflow can assign a durable operation ID rather than creating a new ID when retrying a step.

Keys should have sufficient unpredictability to avoid collisions and enumeration. Yet **key randomness never replaces access control**. A caller may only view or replay results belonging to data that principal is authorized to access.

### 3.3. Binding one key to one request payload

The server should compute a fingerprint/hash from the request's business-meaningful fields after normalization. Do not naively hash the raw JSON, because field ordering, whitespace, headers, or non-business metadata can vary.

For example, a fingerprint might be computed from:

~~~text
SHA-256(
  API operation version
  + normalized doctor_id
  + normalized slot_id
  + relevant booking options
)
~~~

Do not include secrets, bearer tokens, or unnecessary data in the fingerprint. If payloads are sensitive, avoid storing the full raw body; store only the hash and minimal result needed for replay.

**Same scope + same key + same fingerprint:** likely a retry of the same intent.

**Same scope + same key + different fingerprint:** reject or report conflict. Never silently treat a new payload as the old request and return an unrelated result.

## 4. Request-processing flow with an idempotency key

A common flow has four logical states:

1. **No record yet:** the key has not been used in this scope.
2. **In progress:** one request has claimed processing rights for the key; concurrent requests with the same key follow a wait or temporary-status policy.
3. **Completed:** side effects finished and the result is saved; retries with matching content can replay the result.
4. **Failed/retryable or terminal:** processing failed; policy dictates whether retries are allowed, the error is preserved, or a new key is required.

~~~mermaid
flowchart TD
    A["Receive request and authenticate"] --> B["Compute scope + key + fingerprint"]
    B --> C{"Idempotency record exists?"}
    C -- "No" --> D["Atomic claim key"]
    D --> E{"Claim succeeded?"}
    E -- "No" --> C
    E -- "Yes" --> F["Execute business transaction"]
    F --> G["Save result and mark completed"]
    G --> H["Return response"]
    C -- "Yes, different fingerprint" --> X["409 Conflict"]
    C -- "Yes, in progress" --> Y["Wait or return in-progress status"]
    C -- "Yes, completed" --> Z["Check permissions and replay result"]
~~~

This diagram is a logical model; locking, transactions, wait durations, and error states must be defined for your specific system.

### Response for duplicate requests

When the key is completed and the fingerprint matches, APIs typically replay the stored outcome. You can store:

- HTTP status code.
- Response body or reference to the created resource.
- Essential headers such as Location, resource ID, or version.
- Completion timestamp and operation ID.

You do not necessarily need to store every response header. Avoid storing headers containing credentials, cookies, or per-call transient values. Specify clearly whether replayed responses preserve the original status/body or reflect the latest resource state.

For example, the first create-booking request returns 201 with the booking ID. Retries can receive that booking ID back—either replaying the original 201 or returning another documented status like 200 per API contract. What matters is **never creating a second booking** and ensuring clients know how to interpret the response.

### Requests with the same key while still in progress

Two nearly simultaneous requests can both observe "key does not exist" before a record is written if the design is not atomic. You need an **atomic claim** operation backed by a unique constraint, conditional write, or suitable locking primitive.

If a second request encounters an IN_PROGRESS record, the API can:

- Return 409/202 with operation status or Retry-After per contract.
- Wait briefly for the first request to finish, then replay.
- Return a transient error instructing the client to retry with the same key after a short delay.

Never hold an open database transaction or lock for a long duration just waiting on an external API. That quickly exhausts connections and locks. Long-running workflows should move to an operation-resource model with asynchronous processing.

## 5. Storing idempotency records durably and atomically

Deduplication records must reside where all instances can access them. Using static variables, local caches, or container-local files as the sole source of truth fails when the next request hits a different instance or the environment restarts.

An illustrative relational schema:

~~~sql
CREATE TABLE idempotency_record (
    tenant_id          VARCHAR(100) NOT NULL,
    operation_name     VARCHAR(120) NOT NULL,
    idempotency_key    VARCHAR(200) NOT NULL,
    request_hash       CHAR(64) NOT NULL,
    state              VARCHAR(20) NOT NULL,
    response_status    INTEGER,
    response_body      JSONB,
    resource_id        VARCHAR(120),
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at         TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (tenant_id, operation_name, idempotency_key)
);
~~~

This schema is a conceptual example. Database engine, key lengths, JSON types, indexes, and retention policies must fit your real engine and workload. Response bodies may hold sensitive data and thus require minimization, encryption, retention limits, and separate access controls.

### 5.1. Claiming keys via unique constraints

Simple execution pattern:

1. Authenticate request and validate input.
2. Normalize payload, compute fingerprint and scope.
3. Attempt to insert an IN_PROGRESS record.
4. If insert succeeds, the current request owns processing.
5. On unique key violation, read the existing record, compare fingerprint and state.
6. Only one request can claim the key per the constraint; concurrent requests do not re-run side effects.

Illustrative SQL example:

~~~sql
INSERT INTO idempotency_record (
    tenant_id, operation_name, idempotency_key,
    request_hash, state, expires_at
)
VALUES (
    :tenant_id, :operation, :key,
    :request_hash, 'IN_PROGRESS', :expires_at
)
ON CONFLICT DO NOTHING;
~~~

The application must check the inserted row count. If nothing was inserted, read the existing record in an appropriate transaction and decide between replay, conflict, or in-progress. Inserting and executing business operations must coordinate to handle crashes cleanly.

### 5.2. Writing idempotency records in the same business transaction

If the booking and idempotency record live in **the same database**, a strong approach is committing both in one transaction:

~~~text
BEGIN
  claim idempotency key
  validate business constraints
  create booking
  save response/resource reference
  mark idempotency record COMPLETED
COMMIT
~~~

If the transaction rolls back, both the booking and the claim record roll back; retries can try again. If commit succeeds but the response is lost, the completed record lets subsequent requests replay the result.

However, not all side effects live inside a single database transaction. Sending emails, calling payment gateways, or publishing to brokers are external side effects that cannot automatically commit atomically alongside an ordinary database transaction.

### 5.3. Using an outbox for asynchronous side effects

For a booking that must emit an event to send notifications, the same transaction can write the booking, the idempotency record, and an outbox event. A relay worker reads the outbox and publishes messages. The consumer maintains its own inbox/dedup record to prevent duplicate processing.

~~~mermaid
flowchart LR
    API["API request"] --> TX["Database transaction"]
    TX --> BOOK["Booking row"]
    TX --> IDEM["Idempotency completed"]
    TX --> OUT["Outbox event"]
    OUT --> RELAY["Outbox relay"]
    RELAY --> Q["Queue / event bus"]
    Q --> CONSUMER["Consumer"]
    CONSUMER --> INBOX["Inbox / processed event ID"]
    INBOX --> EFFECT["External side effect"]
~~~

An outbox closes the gap between database commit and event publishing, yet the relay can still double-publish if it sends a message and crashes before marking the outbox sent. Consumers must still be idempotent. This is **per-boundary deduplication**, not a global exactly-once guarantee across every service.

## 6. Handling failures and ambiguous outcomes

Idempotency design must answer what happens if a process dies at each point:

| Failure point | Possible leftover state | Handling approach |
| --- | --- | --- |
| Before claiming key | No record yet | Retry with same key can start |
| After claim but before business transaction | IN_PROGRESS record if claim was outside transaction | Use lease/timeout to recover orphaned records |
| Inside transaction before commit | Transaction rolls back if DB enforces properly | Retry based on record/constraints |
| After commit, before sending response | Business action completed, response never reached client | Replay result saved in record |
| After calling external provider, before saving result | Provider may have executed side effect | Use provider idempotency key or reconciliation |
| After publishing message, before marking outbox sent | Message may be republished | Consumer deduplicates by event ID |
| Inside consumer, after side effect before ack | Side effect may have occurred; message redelivers | Inbox/transaction or provider idempotency |

### Abandoned IN_PROGRESS records

If a claim is committed separately before processing, the process can die and leave an IN_PROGRESS record forever. Strategies include:

- **Lease:** records carry an ownership expiration and heartbeat/renewal; after lease expiry, another worker can conditionally take over.
- **Attempt token/fencing:** each ownership claim gets a monotonically increasing token; stale workers are prevented from writing results after ownership moved.
- **Recovery worker:** scans expired records, reconciles business state, and decides whether to resume, finalize, or flag needs-review.
- **Shared transaction:** when primary side effects sit in the same database, keep claim and business logic in one transaction to avoid orphaned records.

Never blindly delete expired IN_PROGRESS records and allow blind retries. Side effects may have already occurred in an external system without being recorded locally. Reconcile with the provider or business resource before retrying.

### External providers with their own idempotency

When calling a payment gateway, pass the same operation key to the provider if its API supports it. Persist the provider reference and outcome. On timeout, query the transaction by reference/key before issuing a new payment command.

Never generate a new key on each retry to a provider. Doing so turns a single payment intent into multiple independent transactions.

If a provider lacks reliable idempotency or lookup APIs, the design needs reconciliation, pending-verification states, and manual handling workflows for uncertain outcomes. Retries alone cannot solve every scenario.

## 7. TTL, retention, and key reuse

Idempotency records do not need to be stored forever in every system, yet deleting them too early allows duplicate side effects on late client retries.

Retention periods should be based on:

- Maximum retry duration across clients, gateways, SDKs, and jobs.
- Redelivery/replay windows from queues or webhook providers.
- Workflow recovery windows and how long operators may replay tasks.
- Audit obligations and transaction lookup requirements.
- Table size, record growth rate, and read/write/delete costs.

For instance, if a webhook provider retries for up to 72 hours and operations permit replays for 7 days, a 24-hour retention window is insufficient. You can keep full responses for a shorter window and retain tombstones/hashes longer, provided processing logic prevents expired keys from being unintentionally reused.

### What does TTL expiration mean?

Once the deduplication window expires, the system can:

- Delete the record entirely, when business rules accept that very late resends count as new operations.
- Transition to a minimal tombstone, keeping scope/key/hash and status to block old keys while purging sensitive bodies.
- Retain resource IDs and business state long-term if required as audit evidence.

The TTL of a deduplication record is **not** the lifetime of the booking or payment itself. The two lifecycles serve different purposes.

### Expired keys and client resends

The API contract must state the idempotency window clearly. For example: "the same key is recognized for at least 24 hours from the initial claim; after this window, clients must not reuse keys for new operations." For financial transactions, longer retention and reconciliation are needed per business policy.

If a key expires while an operation is still IN_PROGRESS, never simply delete it and accept a new request. Resolve the operation state first.

## 8. Security and privacy

An idempotency store can contain tenant IDs, payload hashes, resource references, responses, and transaction states. This can be business-critical or sensitive data.

Principles to enforce:

1. **Authenticate before accessing records:** never let unauthenticated callers probe keys to discover whether operations exist.
2. **Scope by principal/tenant:** never replay another tenant's response even if the key matches.
3. **Re-authorize resources:** an idempotency record does not replace permission checks to view bookings/transactions.
4. **Do not treat keys as bearer secrets:** knowing a key does not automatically grant permission to view results.
5. **Limit key size/format:** reject oversized inputs, control characters, or values that bloat indexes.
6. **Rate limit:** defend against key probing, record spam, and storage-exhaustion attacks.
7. **Minimize response storage:** prefer resource IDs or minimal outcomes; encrypt and set appropriate retention if storing bodies.
8. **Log safely:** log hashed/truncated identifiers for tracing, avoiding raw payloads or sensitive fields.
9. **Restrict idempotency store access:** grant read/write only to required services; audit admin and deletion actions.

If the API supports keys for payments or sensitive data, conduct a dedicated threat model and retention policy review.

## 9. Idempotency across API and event types

### Resource-creating HTTP APIs

POST usually creates a new resource. Keys allow clients to retry the same creation intent and receive the same resource ID. The server must bind the key to principal and operation.

### State-updating APIs

PUT setting a resource to a target state is often already semantically idempotent. Yet secondary side effects—like sending emails, incrementing counters, or emitting events—can still duplicate. Audit the entire behavior, not just the primary update statement.

### Webhooks

Use the issuer's event ID within a scope covering provider/account/event type. Verify signatures before trusting the event ID. Persist processed events with outcomes or use an inbox table. Different event IDs can still represent the same business event; deduplicate by business key too when needed.

### Queue consumers

Messages can be redelivered. Consumers must record processed event IDs, ideally inside the business transaction. Acknowledge only after durable processing state is persisted per broker semantics.

### Multi-step workflows

Each step needs a stable operation ID. If a workflow retries a step calling a provider, reuse the same key for that operation. In a saga, each action and compensation has its own ID; compensation does not erase side-effect history.

### Batch imports

Use source record IDs or file ID + row ID to identify already-applied rows. Define behavior when a file is re-uploaded with changed content, the same filename, or a new version.

## 10. Designing the API contract for idempotency

A solid mechanism must be documented clearly for clients. Endpoint documentation should specify:

| Contract element | What should be specified |
| --- | --- |
| Header/key location | Header or field name, format, and length limits |
| Required or optional | Which endpoints require keys vs. which do not |
| Scope | Principal, tenant, endpoint, operation, or account |
| Payload mismatch | Error returned when same key has a different request body |
| Duplicate completed | Status/body/headers returned on replay |
| In-progress duplicate | Return 409/202/Retry-After or how long to wait |
| Retention window | Minimum protection period and behavior after expiry |
| Error handling | Which errors retain the key, allow retries, or are terminal |
| Client retry | Reusing exact key, backoff, and never minting new keys for same intent |

### Example responses

Initial request:

~~~http
HTTP/1.1 201 Created
Location: /v1/bookings/bkg-9281
Content-Type: application/json

{
  "bookingId": "bkg-9281",
  "status": "CONFIRMED"
}
~~~

Duplicate request with matching scope, key, and payload can replay the result:

~~~http
HTTP/1.1 201 Created
Location: /v1/bookings/bkg-9281
Content-Type: application/json

{
  "bookingId": "bkg-9281",
  "status": "CONFIRMED"
}
~~~

Request reusing the key with a different slot can return:

~~~http
HTTP/1.1 409 Conflict
Content-Type: application/json

{
  "code": "IDEMPOTENCY_KEY_REUSED",
  "message": "Key has already been used with a different request payload."
}
~~~

Requests arriving while the initial operation is still running can receive 202 or 409 depending on the contract. If returning 202, provide an operation/status URL and polling instructions; if returning 409, clarify that the operation is in progress and the client should retry with the same key after the specified interval.

Never return a cached body before authenticating and checking current permissions. Having had permission to create an operation once does not mean the user always has permission to read the outcome.

## 11. Implementation example: creating a booking in one database transaction

The pseudocode below highlights logical ordering. It is not tied to any specific framework or engine:

~~~text
function createBooking(principal, key, request):
    authorize(principal, "booking:create")
    normalized = normalizeBusinessFields(request)
    fingerprint = hash(normalized)
    scope = (principal.tenantId, "create-booking", key)

    begin transaction
        record = tryInsertIdempotency(scope, fingerprint)

        if record already exists:
            if record.requestHash != fingerprint:
                rollback
                return 409 IDEMPOTENCY_KEY_REUSED

            if record.state == COMPLETED:
                result = loadReplayResult(record)
                commit or rollback read transaction
                authorizeResult(principal, result)
                return result

            if record.state == IN_PROGRESS:
                rollback
                return 202 OPERATION_IN_PROGRESS

        booking = insertBookingWithBusinessConstraint(normalized)
        response = buildCreatedResponse(booking)
        saveReplayResult(scope, response, booking.id)
        markCompleted(scope)
    commit

    return response
~~~

In production implementations, handle insert conflicts in concurrent transactions, isolation levels, serialization/deadlock retries, response serialization, and same-key IN_PROGRESS collisions. When records and bookings share a database, keeping business writes in the right transaction ensures a pre-commit crash rolls back everything cleanly.

## 12. Observing and operating idempotency

Do not merely count keys in the database. Verify whether deduplication is working and whether it creates bottlenecks.

| Metric / log field | Purpose |
| --- | --- |
| New key claims | Number of new intents accepted |
| Duplicate completed hits | Requests replayed instead of re-executed |
| Payload mismatch conflicts | Detect clients misusing/reusing keys |
| In-progress conflicts | Measure concurrent duplicates or slow operations |
| Orphaned in-progress count/age | Spot abandoned claims |
| Processing latency | Initial execution time and duplicate wait time |
| Replay latency | Latency fetching and returning stored outcomes |
| Expired/deleted record count | Monitor retention and cleanup |
| Provider reconciliation | Uncertain outcomes needing reconciliation |
| Duplicate side-effect incidents | Evidence of remaining business bugs |

Logs should include protected tenant identifiers, operation names, correlation IDs, and a hashed or truncated key trace. Avoid logging full keys if they could aid operation probing, and never log sensitive responses.

### Operational alerts

- IN_PROGRESS age exceeds normal thresholds.
- Sudden spike in payload mismatch rate.
- Duplicate hits surge after a network blip or deployment.
- Idempotency store latency, lock wait, or connection pool usage rises.
- Storage grows rapidly or cleanup stops running.
- Provider timeouts increase and reconciliation backlogs accumulate.

Rising duplicate hits are not necessarily an outage; they may reflect healthy client retries working as intended. Compare against timeout/error rates and duplicate side-effect counts to interpret accurately.

## 13. Testing idempotency

Testing one request sent twice sequentially is insufficient. Race conditions typically surface only under concurrent requests or crashes right around commit time.

Test categories:

1. **Sequential duplicate:** send identical key/body twice; only one resource or side effect exists.
2. **Concurrent duplicate:** send identical scope/key/body simultaneously from multiple clients/instances; only one claims and executes.
3. **Payload mismatch:** same key with one modified business field; server returns conflict.
4. **Cross-tenant collision:** two tenants use the same key string; no shared outcomes or data leakage.
5. **Timeout after commit:** server commits while test client closes connection before receiving response; retry returns original resource.
6. **Crash before commit:** kill worker mid-transaction; retry can re-execute cleanly without partial data.
7. **Crash after external side effect:** simulate provider succeeding while function times out; verify provider key or reconciliation.
8. **In-progress timeout:** terminate process after claim; verify lease/recovery and zero duplicates.
9. **TTL boundary:** retry before/after retention window; verify contract-compliant behavior.
10. **Authorization change:** revoke/change permissions between initial request and replay; response does not leak.
11. **Load test:** measure lock contention, record lookups, latency, and storage growth at peak load.
12. **Replay/recovery:** replay webhooks/messages/jobs via operational procedures and confirm identical outcomes.

### Example outcome matrix

| Call | Scope/key | Payload | Prior state | Expected outcome |
| --- | --- | --- | --- | --- |
| 1 | Tenant A / K1 | Slot 10:00 | None | Create booking B1 |
| 2 | Tenant A / K1 | Slot 10:00 | Completed | Replay B1 |
| 3 | Tenant A / K1 | Slot 11:00 | Completed | Conflict |
| 4 | Tenant B / K1 | Slot 10:00 | None in scope B | Create booking B2 if valid |
| 5 | Tenant A / K2 | Slot 10:00 concurrent with K3 | None | One transaction wins; the other is rejected per business constraints |
| 6 | Tenant A / K1 | Slot 10:00 after retention expires | Expired record | Policy-defined behavior; never assume infinite replay |

Tests must assert **actual side-effect counts in datastores/providers**, not just HTTP status codes. Two requests both returning 200 while creating two transactions is still a bug.

## 14. Common mistakes

**Minting a new key on every retry.** The server sees distinct intents and repeats side effects. Clients must keep the same key for the same operation.

**Storing keys in a single instance's memory.** Subsequent requests can hit another instance; scale-out and restarts wipe deduplication state.

**Treating keys as authentication proof.** Knowing a key does not grant permission to view results. Always authenticate principals and authorize resources.

**Failing to bind keys to payloads.** Same key with different payloads can return the wrong cached result or execute unintended actions.

**Non-atomic check-then-insert.** Two requests both read "not found" and both execute; use unique constraints/conditional writes/atomic claims.

**Writing records and business data in separate transactions without recovery.** Crashing between steps leaves a completed record without the resource, or vice versa.

**Calling external payment/email services assuming a DB transaction protects everything.** External side effects have separate boundaries; use provider idempotency, outboxes, reconciliation, or workflows.

**Blindly deleting IN_PROGRESS records.** Side effects may have occurred before the process died; verify state before allowing re-execution.

**TTL too short.** Valid late retries or replays can re-trigger side effects.

**Retaining responses with sensitive data indefinitely.** Response replay stores need data minimization, access control, encryption, and retention.

**Equating deduplication with exactly-once.** Deduplicating inside one database or queue does not create a global transaction across all external systems.

## 15. Practice lab: booking and payment API without duplicate transactions

**Hypothetical scenario:** A booking platform has a create-booking endpoint and a payment endpoint. Mobile clients send requests through an API gateway; services run across multiple instances or functions. Some clients on weak networks frequently retry after timeouts. Bookings are stored in a relational database; payments call an external payment provider. The provider supports idempotency keys scoped to a merchant account and offers an API to look up transactions by operation reference.

Lab requirements:

- A single booking intent never creates two bookings.
- A single payment intent is never charged twice on retry.
- Two tenants can use identical key strings without seeing each other's outcomes.
- Requests with the same key and different payloads must be detected.
- If the provider charged the card but the API timed out, the system never sends a new charge command with a different key.
- Deduplication records are retained long enough for retries, webhook replays, and policy-compliant audits.

Retention numbers, RPS, and processing windows are assumptions learners must choose; there is no single universal value for every provider or domain.

### Tasks

1. **Design scope and fingerprint:** define scopes for CreateBooking and CapturePayment. Specify who generates keys, format/entropy, how keys persist across retries, and business fields hashed into fingerprints. Explain same key with a different slot or amount.
2. **Design schema and states:** sketch the idempotency record schema including tenant, operation, key, fingerprint, state, resource/provider reference, minimal response, created/updated timestamps, and expires_at. Define transitions among IN_PROGRESS, COMPLETED, FAILED_RETRYABLE, and FAILED_TERMINAL if used.
3. **Handle concurrency and failures:** describe the transaction claiming the key and creating a booking. For payments, describe reusing the provider key, storing the provider reference, and looking up status on timeout. Show crash handling at each step.
4. **Design the API contract:** write request/response examples for initial call, completed duplicate, in-progress duplicate, and payload mismatch. Specify status codes, Retry-After/operation status URLs, and retention window.
5. **Design tests:** run 50 concurrent requests with the same key and body; then send the same key with a different body; simulate a client timeout after database commit and successful provider charge. Verify booking count, actual charge count, response replay, audit logs, and reconciliation.
6. **Well-Architected review:** evaluate operations, security, reliability, performance, cost, and sustainability for the chosen design.

### Acceptance criteria

| Goal | Evidence |
| --- | --- |
| Only one booking created per intent | Database holds one resource and retries receive the same resource ID |
| No cross-tenant confusion | Identical keys across tenants never share records/responses |
| Payload mismatch detected | Same scope/key with different fingerprint returns conflict |
| No duplicate charges after timeout | Provider records only one charge under the same provider operation key |
| Safe under concurrent requests | 50 concurrent requests never create multiple side effects |
| Orphaned states recoverable | Leases/reconciliation determine whether the operation occurred |
| Contract-compliant retention | TTL boundary tests and replay procedures match policy |
| No data leakage via replay | Unauthorized tenants/principals cannot read responses |

## 16. Well-Architected assessment

| Pillar | Review questions |
| --- | --- |
| **Operational Excellence** | Are there duplicate metrics, orphaned IN_PROGRESS alerts, reconciliation runbooks, and replay capabilities? |
| **Security** | Is scope bound to principal, are keys treated as non-credentials, and does response replay enforce authorization and retention? |
| **Reliability** | Are post-commit crashes, provider timeouts, webhook redeliveries, and concurrent duplicates handled? |
| **Performance Efficiency** | Do unique lookups/locks create bottlenecks? Are proper indexes, latency, and peak load measured? |
| **Cost Optimization** | Are record storage, response retention, cleanup, and provider lookups accounted for? |
| **Sustainability** | Are retry storms, polling, and excess records minimized with controlled lifecycle cleanup? |

A solid design must prove that deduplication does not depend on a single execution instance, concurrency cannot corrupt data or downstream services, and the team has enough signals to catch stuck operations or ambiguous side effects.

## 17. Pre-production checklist for idempotency

- [ ] Every side-effecting endpoint has determined whether it needs an idempotency key or natural idempotent semantics.
- [ ] Clients generate keys once per intent and preserve them across all retries.
- [ ] Scopes include appropriate tenant/principal and operation; environment/version are accounted for.
- [ ] Servers authenticate callers before reading/replaying records.
- [ ] Fingerprints are computed from normalized business data.
- [ ] Same-key/different-fingerprint requests produce clear conflict responses with zero side effects.
- [ ] Atomic claims use unique constraints, conditional writes, or equivalent primitives.
- [ ] Business state and idempotency completion commit atomically when sharing a datastore.
- [ ] Off-database side effects use appropriate provider keys, outboxes, inboxes, or reconciliation.
- [ ] IN_PROGRESS states have timeouts/leases and recovery mechanisms.
- [ ] Completed duplicates have response replay defined in the API contract.
- [ ] Retries, timeouts, backoff, concurrency, and deadlines coordinate to avoid retry storms.
- [ ] Retention exceeds supported retry/replay windows; expired keys have clear semantics.
- [ ] Responses/keys/fingerprints are protected, encrypted, and cleaned up per data policy.
- [ ] Metrics, alerts, audits, runbooks, and concurrency/failure/TTL tests are in place.
- [ ] Actual side-effect counts in databases/providers are verified, not just HTTP responses.

An idempotency key is a contract between caller and API to recognize a single intent across multiple submissions. A reliable mechanism requires **proper scope, accurate fingerprints, atomic claims, durable deduplication data, and explicit handling for timeouts, concurrency, external side effects, and expiration**. When designed alongside transactions, outboxes/inboxes, retry policies, and observability, it helps APIs withstand unstable networks and distributed failures while preserving business correctness.
