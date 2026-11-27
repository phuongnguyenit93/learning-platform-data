# API Versioning and Compatibility When Changing

An API is a contract between a party providing functionality (producer/provider) and the applications using it (consumers). When a producer changes requests, responses, business rules, or authentication, applications using an older version may continue running for days or months. If changes are unmanaged, a backend release can break un-updated mobile apps, partner integrations, or an internal service whose dependency the development team did not know about.

**API versioning** is the practice of managing API contract versions over time. **Backward compatibility** describes the ability of a new version to continue supporting older consumers; **forward compatibility** describes the ability of older consumers to handle new data or behavior from the producer. These two properties are related, but not identical.

In the **CLOUD_ARCHITECTURE** module, API versioning enables independent releases, scaling to multiple consumers, connecting cloud services and partners, and controlling trade-offs across reliability, security, performance, cost, and operations. The goal is to understand when a change remains compatible, when a new version is needed, and how to transition safely.

## 1. What is an API contract and why must changes be managed?

An API contract describes how a consumer interacts with a producer. For HTTP APIs, a contract typically includes:

- **Endpoints and methods:** URLs, HTTP methods such as GET, POST, PATCH, DELETE.
- **Requests:** Path/query parameters, headers, bodies, data types, and required fields.
- **Responses:** Status codes, headers, body structure, and field semantics.
- **Business rules:** Meaning of operations, success/failure conditions, and side effects.
- **Authentication and authorization:** Authentication method, required scopes/roles, and permissions per action.
- **Error contract:** Error codes, error structure, retryability, and how consumers handle them.
- **Operational contract:** Timeouts, rate limits, pagination, idempotency, and payload limits.

For example, a Booking API provides an operation to create a booking:

~~~http
POST /api/bookings
Content-Type: application/json
Authorization: Bearer <access-token>
Idempotency-Key: 1c7f...

{
  "resourceId": "ROOM-101",
  "startAt": "2026-12-01T09:00:00Z",
  "endAt": "2026-12-01T10:00:00Z"
}
~~~

The response might be:

~~~http
HTTP/1.1 201 Created
Content-Type: application/json
Location: /api/bookings/BK-9081

{
  "id": "BK-9081",
  "status": "CONFIRMED",
  "startAt": "2026-12-01T09:00:00Z",
  "endAt": "2026-12-01T10:00:00Z"
}
~~~

If you rename the required field resourceId to resourceCode, change status from a string to an object, or change the meaning of 201 Created, older consumers may stop working. API changes must therefore be evaluated against **all existing consumers**, not just the producer's code.

| Role | Responsibilities |
|---|---|
| **API producer/provider** | Publish contracts, maintain behavior, validate requests, support versions, announce changes and deprecations |
| **API consumer/client** | Send requests matching the contract, handle responses/errors, timeouts and retries, track changes, and upgrade when notified |
| **API owner/platform team** | Manage catalogs, policies, telemetry, gateways, versioning processes, and version lifecycles |
| **Security/operations** | Review permissions, data, logging, rate limits, SLOs, and incident response plans |

An internal API is still a contract between teams. Two services belonging to the same repository or organization does not guarantee they are deployed simultaneously.

## 2. Backward compatibility and forward compatibility

### 2.1. Backward compatibility

A change is **backward-compatible** when consumers using an older contract can still call the producer after the producer is updated, within the promised behavior.

Examples:
- Adding an optional response field when old consumers ignore unknown fields.
- Adding a new endpoint while keeping the old endpoint.
- Adding an optional header that old consumers do not need to send.
- Extending a response with new metadata without altering the meaning of existing fields.

These changes can usually be released within the same major version, provided the actual contract and consumers support that form of extension.

### 2.2. Forward compatibility

A consumer has **forward compatibility** if it can handle new data or behavior from the producer. For example, a consumer ignores unrecognized JSON fields instead of failing when encountering a new field.

However, consumers are not always forward-compatible:
- Generated clients may deserialize strictly and reject new fields.
- Enum parsers may fail when receiving a new value.
- Switch/case statements may lack a default branch.
- Schema validation may forbid undeclared fields.
- Business logic may assume only a fixed set of states exists.

Therefore, "adding a field is safe" only holds when **consumers, schemas, SDKs, proxies, and validators** accept that extension.

### 2.3. Compatibility is not just JSON structure

Even when the schema does not change, behavior can still break consumers.

Examples:
- An API previously returned bookings sorted by creation time, and now changes to update order.
- An API previously allowed idempotent retries, and now creates a new booking on every retry.
- An API previously returned 404 when not found, and now returns 200 with an empty body.
- An API previously treated timestamps as UTC, and now returns local time.
- An API previously allowed a page size of 100, and now caps it at 10 without notice.
- An API previously retained state for 30 days, and now deletes it after 24 hours.

These changes can break consumers without altering the JSON schema. When evaluating compatibility, check **syntax, semantics, security, timing, and operational behavior**.

## 3. Classifying API changes

A useful rule is to classify changes into **compatible extensions (additive)**, **changes requiring coordination (behavioral/conditional)**, and **contract-breaking changes (breaking)**.

| Change | Compatibility risk | Common handling approach |
|---|---|---|
| Add a new endpoint | Low if existing endpoints are unchanged | Keep old contract, publish new endpoint |
| Add an optional response field | Usually low, though consumers may deserialize strictly | Check SDKs/schemas; treat field as optional |
| Add an optional request field | Low if server applies a consistent default | Specify default and semantics clearly |
| Add a required request field | High | Support a default or create a new contract version |
| Remove a response field | High | Deprecate, measure consumers, migrate, then remove |
| Rename a field | High | Keep old field during transition or release new version |
| Change a data type | High | Usually breaking; add new field or new version |
| Narrow valid values | High | Can cause old requests to be rejected |
| Add an enum value | Depends on consumers | Consumers handle unknown values; check strict parsers |
| Change HTTP method/path | High | Keep old route or release new version |
| Change status code/error shape | Potentially high | Check client logic, retries, and error mapping |
| Change auth scopes or required permissions | Potentially breaking for security/ops | Notify, support new credentials, and migrate |
| Change pagination/default sort/limit | Can break business correctness | Evaluate semantics and announce changes |
| Change timeouts/rate limits | Can affect clients under real load | Notify, measure, and provide retry/backoff guidance |

### Commonly misunderstood cases

**Adding a response field:** Often treated as additive if consumers ignore unknown fields. Yet if a consumer uses strict schemas, generated models, or payload signatures, adding a field can cause failures. Verify against actual consumer contracts.

**Adding an enum value:** Can break consumers written to accept only the existing set of values. APIs should encourage consumers to include an unknown/fallback branch; consider open enums or strings instead of assuming an immutable set of values.

**Changing defaults:** If a query parameter previously defaulted to 20 results and now returns 100, the schema has not changed, but load, paging, and UI logic may break. Defaults are part of the behavioral contract.

**Tightening validation:** Going from accepting extra whitespace or non-standard fields to rejecting them can stop older consumers from sending valid requests. Security validation is necessary, but impact must be assessed and a clear migration provided.

## 4. Choosing a versioning strategy

No single versioning scheme fits every API. What matters is that versions are **discoverable, stable, backed by a support policy, and have a migration path**.

### 4.1. Version in the URL path

Example:

~~~text
GET /api/v1/bookings/BK-9081
GET /api/v2/bookings/BK-9081
~~~

Advantages:
- Easy to observe in logs, metrics, gateways, and dashboards.
- Easy to route to the appropriate handler or deployment.
- Easy to test a new version side by side.

Trade-offs:
- Version appears in the URL and can create multiple routes/endpoints.
- Requires managing deprecation and avoiding duplicating business logic.
- If each version is a separate deployment, operational costs can increase.

This is a popular choice for public APIs because it is straightforward to explain and operate.

### 4.2. Version via header

Custom header example:

~~~http
GET /api/bookings/BK-9081
API-Version: 2
Accept: application/json
~~~

Or using media type versioning:

~~~http
GET /api/bookings/BK-9081
Accept: application/vnd.example.booking.v2+json
~~~

Advantages:
- URLs stay focused on resources.
- Can route versions based on request metadata.
- Fits systems wanting formal content negotiation.

Trade-offs:
- Harder to observe if logs/gateways do not record headers.
- Caches/proxies must distinguish responses by header, e.g., configuring Vary: Accept appropriately.
- Consumers and debugging tools must know how to send the right headers.

### 4.3. Version via query parameter

Example:

~~~text
GET /api/bookings/BK-9081?version=2
~~~

This is easy to test and observe, but is often less explicit than path or media type versioning when the version is a major part of the contract. Cache keys and gateway policies must also be configured so responses are not served for the wrong version.

### 4.4. No explicit version

Some APIs only release compatible changes and omit versions from URLs/headers. This reduces the number of versions to support, but demands strong compatibility discipline and rigorous change management. If a breaking change occurs, it requires a coordinated upgrade strategy or a new channel.

| Strategy | Observability | Parallel support | Key considerations |
|---|---|---|---|
| URL path | High | High | Managing multiple routes and versions |
| Header | Medium unless logged fully | High | Caching, proxies, and observability |
| Media type | Medium | High | Consumers must negotiate content types |
| Query parameter | High | High | Cache keys and URL semantics |
| No explicit version | Depends on telemetry | Lower on breaking changes | Requires very strong compatibility discipline |

Pick one consistent convention for an API family. Do not put versions in the path, header, and body simultaneously without clear justification; multiple version sources create conflicts such as a v2 path alongside a header requesting v1.

## 5. Semantic versioning and API versions are two different concepts

**Semantic Versioning (SemVer)** usually takes the form MAJOR.MINOR.PATCH, describing the magnitude of change in a product/package:
- MAJOR: incompatible changes.
- MINOR: backward-compatible feature additions.
- PATCH: compatible bug fixes.

For HTTP APIs, a path like /v1 usually represents a **major contract line**, not necessarily every patch deployment. Do not change /v1.2.3 every time code is patched or a container image is updated if the public contract has not changed.

For example:
- API /v1 can have many backend releases—1.4.1, 1.4.2, 1.5.0—while keeping the same major contract.
- When changing response structures in a breaking way, the team can publish /v2.
- A client SDK has its own SemVer version; SDK versions and HTTP API versions do not automatically stay in lockstep.

Document these conventions explicitly:
1. Which contract does the API version represent?
2. To what extent can a patch/minor release add fields or endpoints?
3. When is a new major version required?
4. How long are versions supported?
5. Which API versions is an SDK compatible with?

## 6. Designing APIs for compatible evolution

### 6.1. Designing extensible responses

- Consumers should ignore unknown fields if schemas/SDKs permit.
- New fields should be optional or have clear defaults.
- Do not change the meaning of existing fields.
- Do not reuse deleted field names for a different meaning.
- Date/time and numeric formats must be stably defined.
- Enum consumers should have an unknown branch or sensible fallback.

Example response adding displayLabel:

~~~json
{
  "id": "BK-9081",
  "status": "CONFIRMED",
  "displayLabel": "Room 101"
}
~~~

Old consumers using only id and status can continue working if their parser ignores unknown fields. New consumers can additionally render the label.

### 6.2. Designing requests with safe defaults

Adding optional request fields is generally far less disruptive than making them immediately required:

~~~json
{
  "resourceId": "ROOM-101",
  "startAt": "2026-12-01T09:00:00Z",
  "endAt": "2026-12-01T10:00:00Z",
  "notifyByEmail": true
}
~~~

If notifyByEmail is absent, the server must determine a default. Defaults should be consistent and documented in the contract. Adding a required field without a compatible default will cause old consumers to be rejected.

### 6.3. Stable error contracts

Maintain an error structure with machine-readable codes and helpful messages:

~~~json
{
  "type": "https://api.example.com/errors/slot-unavailable",
  "title": "Slot is unavailable",
  "status": 409,
  "code": "SLOT_UNAVAILABLE",
  "detail": "The selected slot is no longer available.",
  "traceId": "trace-abc123"
}
~~~

Consumers should branch on the HTTP status and machine-readable code, not parse the detail string for control flow. Messages can be improved without changing business error codes; conversely, changing status codes or error codes can break retry/error mapping.

### 6.4. Unknown fields and enums

Robust consumers should:
- Ignore unknown fields where appropriate.
- Handle unknown enum values via fallback or by displaying an unrecognized state.
- Never assume JSON property ordering.
- Never assume optional fields are always present.
- Configure parser/schema settings to match the contract.

Producers must also consider this: unknown fields in requests may be intentionally rejected for security or typo detection. There is no universal rule requiring every API to accept unknown request fields; what matters is specifying behavior explicitly and avoiding accidental changes.

## 7. OpenAPI and schemas as verifiable contract sources

For HTTP APIs, OpenAPI specifications document endpoints, methods, parameters, schemas, responses, and security requirements. Schema files should be under version control, reviewed alongside code, and used in pipelines to detect changes.

Abbreviated example:

~~~yaml
openapi: 3.1.0
info:
  title: Booking API
  version: 1.0.0
paths:
  /api/v1/bookings:
    post:
      operationId: createBooking
      security:
        - bearerAuth: []
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              required:
                - resourceId
                - startAt
                - endAt
              properties:
                resourceId:
                  type: string
                startAt:
                  type: string
                  format: date-time
                endAt:
                  type: string
                  format: date-time
                notifyByEmail:
                  type: boolean
                  default: true
      responses:
        "201":
          description: Booking created
        "409":
          description: Slot unavailable
components:
  securitySchemes:
    bearerAuth:
      type: http
      scheme: bearer
      bearerFormat: JWT
~~~

This is an illustrative example. A production schema must describe response bodies, error formats, headers, pagination, and other rules. The default keyword in JSON Schema/OpenAPI documents the default value, but not every validator or server enforces it automatically; the producer must implement the corresponding behavior.

### Contract diffs and compatibility checks

Pipelines can:
1. Diff the current OpenAPI schema against the previously released version.
2. Detect removed endpoints/fields, type changes, or fields becoming required.
3. Check for breaking changes according to organizational rules.
4. Run consumer contract tests.
5. Require review/ADRs for risky changes.
6. Store schema artifacts and release versions.

Diff tools do not fully understand business semantics. Changing the meaning of a string field does not alter the schema; changing defaults or sort order can also slip past. Therefore, contract diffs must be paired with tests and reviews.

## 8. Consumer-driven contract testing

**Consumer-driven contract testing** lets consumers explicitly state the parts of a contract they rely on, and then verifies whether the producer continues to satisfy them.

Workflow:
1. Consumers define the requests and responses needed for their use cases.
2. Contracts are stored and published in a pipeline or broker.
3. The producer runs provider verification to confirm actual behavior satisfies consumers' contracts.
4. When contracts change, consumers and producers coordinate updates before release.
5. CI blocks deployment if critical contracts are broken outside allowed policy.

Examples:
- Mobile app only needs id, status, startAt.
- Admin portal also needs customerName.
- Reporting service consumes published booking events.

The producer does not necessarily have to return the same payload to every consumer if API composition or projections are used, but it must uphold the committed contract for each consumer.

**Contract tests do not replace integration tests or end-to-end tests.** They verify interactions at contract boundaries; concerns such as network policies, IAM, timeouts, database consistency, and availability must be tested separately.

## 9. Versioning for event and message schemas

In cloud systems, APIs are not only HTTP. Queues, event buses, and streaming platforms also form contracts between producers and consumers. A producer emits an event:

~~~json
{
  "eventId": "evt-9381",
  "eventType": "BookingConfirmed",
  "occurredAt": "2026-12-01T08:00:00Z",
  "data": {
    "bookingId": "BK-9081",
    "resourceId": "ROOM-101"
  }
}
~~~

If an optional field is added to an event, consumers that ignore new fields can generally keep running. However, removing/changing field types, changing semantics, or emitting a new eventType can break older consumers.

Principles:
- Include a stable event ID so consumers can process idempotently.
- Include schema/version metadata or appropriate compatibility conventions.
- Do not change the meaning of existing fields or repurpose fields.
- Consumers handle unknown event types/fields according to policy.
- A schema registry or contract repository can enforce compatibility checks if supported by the platform.
- Define retention/replay windows and how long consumers must support reading older events.

For events, **forward compatibility** is especially important because old messages may remain in queues/logs and be re-read by newer consumers. New consumers must be able to read previously published events; new producers must also consider old consumers reading new events.

## 10. Changing databases while keeping APIs compatible

An API change may require database schema changes. If a new producer is deployed before the database is ready, or a migration drops a column before old consumers stop using it, the release will fail.

The **expand-contract** strategy:

~~~mermaid
flowchart LR
    A["1. Expand<br/>Add new field/column, keep old column"] --> B["2. Deploy compatible code<br/>Read both old and new"]
    B --> C["3. Migrate data<br/>Backfill and sync"]
    C --> D["4. Switch consumers<br/>Move to new field"]
    D --> E["5. Verify<br/>No remaining old access"]
    E --> F["6. Contract<br/>Drop old field/column in later release"]
~~~

Example renaming customer_name to display_name:
1. Add the display_name column without dropping customer_name.
2. New code writes both or uses a safe synchronization mechanism.
3. Backfill existing data.
4. New API reads display_name; consumers gradually migrate to the new field.
5. Monitor logs/traces to confirm no consumers still rely on the old contract.
6. Only after the support window expires, drop the old column in a separate migration.

Not every migration can do simple dual-writes. Race conditions, inconsistent writes, and storage overhead can arise. Define the authoritative source of truth and a clear rollback strategy.

## 11. Rollout, coexistence, and deprecation

When a breaking change is necessary, do not release v2 and immediately delete v1. Maintain a **coexistence period**:

1. Publish the new version and migration guide.
2. Deploy v2 without altering v1 behavior.
3. Migrate pilot consumers to v2.
4. Monitor traffic, errors, latency, and consumer identities by version.
5. Expand migration and assist consumers facing issues.
6. Announce deprecation for v1 with an expected deadline.
7. Track remaining traffic and work with consumer owners.
8. Retire v1 under the announced support policy after published criteria are met.

~~~mermaid
flowchart TD
    OLD["v1 serving consumers"] --> NEW["Deploy v2 in parallel"]
    NEW --> CANARY["Canary / pilot consumers"]
    CANARY --> METRICS["Measure traffic, errors, latency"]
    METRICS --> MIGRATE["Migrate consumers in waves"]
    MIGRATE --> DEPRECATE["Announce deprecation and deadline"]
    DEPRECATE --> VERIFY["Verify zero remaining v1 traffic"]
    VERIFY --> SUNSET["Retire v1 per policy"]
~~~

### Deprecation and Sunset

- **Deprecated:** The version/endpoint still operates but is no longer recommended; consumers should prepare to migrate.
- **Sunset:** The date or phase when the API stops being served according to the announced policy.
- **Migration guide:** Documents endpoint/field/error mappings, behavioral changes, auth updates, testing, and support windows.
- **Support window:** The duration the producer commits to maintaining a version or assisting consumer migration.

For public APIs, you can publish deprecation/sunset metadata using appropriate standards or headers—such as Deprecation, Sunset, and Link—if the ecosystem supports them. Headers are only useful when timestamps, timezones, semantics, and migration documentation are clear.

Never pick an arbitrary sunset date. Account for mobile app release schedules, procurement/partner cycles, security approval times, and consumer upgrade capabilities.

## 12. API Gateways and managing multiple versions

An API Gateway can route requests to backends by path, header, hostname, or other policies depending on the product. It assists with authentication, rate limiting, logging, routing, and migration, but does not automatically make two contracts compatible.

Examples:
- /api/v1/... routes to backend v1.
- /api/v2/... routes to backend v2.
- The gateway records version and consumer identity in telemetry.
- Specific consumers/traffic can be canaried to v2 if policies and semantics allow.

Things to avoid:
- Patching responses solely at the gateway without a clear contract.
- Hiding errors via transforms that drop fields or alter semantics.
- Relying on the gateway to sustain complex business logic for years.
- Having v1 and v2 share a database with incompatible migrations.
- Forgetting cache keys, CORS, auth scopes, and rate limits when running multiple versions.

**The version at the gateway and the version in the application contract must stay consistent.** If the gateway advertises v2 while the backend only supports a subset of v2 requests, consumers will encounter unstable behavior.

## 13. Observability: knowing who still uses older versions

You cannot deprecate safely if the producer does not know which consumers are calling old endpoints.

Collect:
- Request counts by API version, endpoint, method, and consumer/app identity.
- Error rates and status codes by version.
- Latency p50/p95/p99 and timeouts.
- Percentage of requests using old fields/operations where safely measurable.
- Client SDK/app versions and integration sources.
- Rate limits, retries, and auth errors by version.

Never put tokens, passwords, or personal data into metric labels. Consumer identities should be controlled identifiers, not sensitive content.

A deprecation dashboard should answer:
- Which consumers are still on v1?
- Is that consumer's traffic trending down?
- Which owner is responsible for the migration?
- Is the new version meeting its SLOs?
- Did errors spike after migrating a consumer?
- Is there v1 traffic from unidentified consumers?

If the API cannot identify consumers, consider adding client IDs, scoped API keys, OAuth client IDs, or appropriate identification mechanisms. Never use raw IP addresses as long-term identifiers when traffic passes through NAT, proxies, or shared gateways.

## 14. Security and permission compatibility across versions

A new version may require additional scopes or change authentication methods. This is a major contract change even if the JSON body stays identical.

Examples:
- v1 uses scope booking.read; v2 requires booking.read:details.
- v1 masks phone numbers; v2 allows access to sensitive fields based on another role.
- v2 enforces mTLS while v1 uses bearer tokens.
- An older endpoint has a known vulnerability and requires emergency retirement.

Do not keep an exploitable version running indefinitely simply because consumers have not upgraded. When a severe security risk exists, establish a plan to retire or restrict the API based on risk level, notify stakeholders, and provide appropriate migration support. Security policies may require faster migration than standard deprecation schedules.

Verify:
- Do v1 and v2 share backend secrets and permissions?
- Can v1 consumers access new data they should not see?
- Is authorization enforced on every route, including both gateway and direct backend paths?
- Do audit logs distinguish versions and principals?
- Are rate limits applied appropriately per consumer/version?

## 15. Well-Architected trade-offs

| Aspect | What good versioning enables | Risks to control | Evidence |
|---|---|---|---|
| **Reliability** | Old consumers continue working during migration; canaries and rollbacks | Multiple versions can diverge in behavior or share incompatible DB dependencies | Consumer contract tests, error rates, rollback rehearsals |
| **Security** | Planned auth/scope upgrades; supports vulnerability patching and sunsetting | Older versions retain weak endpoints or overly broad permissions | Per-version security reviews, auth tests, audits |
| **Performance** | Ability to optimize versions individually and shift load gradually | Gateway routing, transforms, or multi-branch code adds latency | p95/p99 latency, throughput, and gateway metrics |
| **Scalability** | Consumers upgrade on their own schedules; producers release more independently | Growing version count complicates schemas, testing, and support | Version inventory, consumer usage, compatibility matrix |
| **Cost** | Reduces outages from breaking changes; proactive deprecation | Running v1/v2 in parallel increases compute, testing, and ops costs | Cost per version/consumer, sunset plan |
| **Operations** | Provides migration guides, telemetry, contract checks, and ownership | Unidentified consumers or doc-code drift drags out migrations | Version traffic dashboards, OpenAPI diffs, ADRs, owner list |

Key decisions to weigh:
- Keeping multiple versions longer gives consumers time to upgrade, but raises maintenance costs.
- Path versioning is easy to manage at gateways, but can duplicate endpoints and tests.
- Header versioning keeps URLs clean, but requires accurate logging/caching/proxying.
- Contract testing lowers risk between producers and consumers, but does not verify full infrastructure or out-of-contract behavior.
- Splitting backends per version isolates rollouts, but increases resource usage and data migration effort.
- Maintaining a shared backend reduces infrastructure cost, but requires compatible code and more test branches.

## 16. Decision process for whether a change needs a new version

Before any contract change, answer:

1. **Who is using the API?** Identify internal consumers, mobile/web apps, partners, and background jobs.
2. **What part is changing?** Path, method, request, response, enums, errors, semantics, auth, timeouts, rate limits, or data retention?
3. **How will old consumers react?** Can they ignore new fields? Strict parsers? Generated SDKs? Reliance on old defaults?
4. **Is there an additive approach?** Optional fields, new endpoints, new headers, or a parallel support window?
5. **If breaking, what does a new version solve?** Is a separate contract truly needed, or just compatible migration code?
6. **Is data migration safe?** Expand-contract, dual-read/write, or another approach?
7. **Can adoption be measured?** Consumer identity, version traffic, errors/latency.
8. **How long is deprecation/sunset needed?** Based on consumer upgrade cycles and support commitments.
9. **How do we roll back?** Can we revert to the old backend? Is the schema change reversible?
10. **Who approves and owns it?** API owner, consumer owners, security, and operations.

### Illustrative ADR — Changing a response field

> **Context:** Booking API v1 returns the field customerName; the system wants to use displayName to reflect display names under a new policy. Both the Mobile App and Admin Portal currently use v1.
>
> **Option A:** Rename the field directly. Simple, but old consumers stop being able to read the data.
>
> **Option B:** Add displayName while keeping customerName during a transition period. New consumers use the new field; old consumers keep working.
>
> **Option C:** Release v2 with the new field while keeping v1 separate. Clear contracts, but increases parallel support costs.
>
> **Illustrative decision:** Choose Option B if both fields can coexist without violating data policies or semantics. If the data meanings differ or security requirements prohibit keeping the old field, choose Option C or a controlled migration plan.
>
> **Verification:** Contract tests for mobile/admin, measure old field traffic, verify data accuracy and access permissions, and set a deprecation date after consumer migration completes.
>
> **Revisit conditions:** Zero remaining traffic on the old field, confirmed consumer migration, and data-protection rules permitting field removal.

## 17. Practice exercise

A booking platform publishes API v1. Consumers include:
- An older Mobile App version updated only on app store release cycles.
- An Admin Portal that can deploy daily.
- An internal Payment service managed by another team.
- An external partner integrating via API key with a lengthy change process.

The current contract is GET /api/v1/bookings/{id} returning id, status, startAt. The team wants to change status into an object containing code and label, add customerEmail, and replace the bearer token requirement with a new scope.

**Requirements:**

1. Classify each change: additive, behavioral, or breaking.
2. Propose a plan so older consumers continue working.
3. Decide whether /v2 is needed; justify based on consumers and semantics.
4. Write a coexistence and deprecation plan.
5. Identify metrics to track whether the Mobile App, Admin Portal, and partner are still using v1.
6. Design contract tests and security tests.
7. Describe how to roll back if v2 fails after deployment.
8. Identify personal data risks from adding customerEmail.

### Solution guidance

- Adding customerEmail can be breaking from a privacy and authorization standpoint even though the schema only adds a field. Review per-consumer authorization, masking, and auditing before publishing.
- Changing status from a string to an object is breaking for older consumer parsers/models; you can add a statusDetails field during transition or use v2.
- Changing the bearer scope is an authentication/authorization change that can cause 401/403 errors for existing clients; support transitional credentials/scopes or a controlled version/policy rollout.
- Mobile App and partner need a longer migration schedule than Admin Portal. Never sunset v1 merely because v2 is deployed.
- Track traffic by client ID, version, endpoint, and status; never log access tokens or emails in metrics.
- Contract tests must verify v1 responses preserve the old shape while v2 uses the new schema; security tests must verify unauthorized consumers cannot read emails.
- Rollback requires keeping databases/schemas compatible with both v1 and v2 during coexistence; avoid migrations that drop old fields before dependencies vanish.
- Publish migration guides, deprecation notices, owners, and deadlines for each consumer group.

### Self-check questions

1. Why can adding a JSON field still break consumers?
2. How does backward compatibility differ from forward compatibility?
3. When should you use URL path versioning, header versioning, or no explicit versioning?
4. Why does API path /v2 not necessarily correspond to SDK version 2.0.0?
5. How does expand-contract prevent database outages during multi-version deployments?
6. Why do consumer-driven contract tests not replace end-to-end tests?
7. What data is needed before announcing a sunset date for a public API?
8. When changing auth scopes or uncovering a vulnerability in v1, why might the standard support schedule need to be shortened?

A good API versioning strategy keeps **contracts, consumers, and deployments evolving at a controllable pace**. Start with additive changes whenever possible; when breaking the contract is unavoidable, publish a new version, support them in parallel, measure consumer adoption, and retire the old version under a clear policy. Every decision should be backed by contract tests, telemetry, security reviews, and practical rollback capability.
