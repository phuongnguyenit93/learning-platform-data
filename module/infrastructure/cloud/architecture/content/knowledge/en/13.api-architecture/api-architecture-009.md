# Contract Testing and API Lifecycle Management

## 1. Why do APIs need clear contracts and lifecycles?

An API is the communication boundary between components that can be developed and deployed independently: web/mobile clients, backend services, partner integrations, workers, data systems, and API gateways. A small change like renaming a field, changing a data type, or altering an error code can break active consumers even when the provider builds and deploys cleanly.

In the **CLOUD_ARCHITECTURE** module, API design connects to networking, compute, data, security, scalability, and operations. Therefore, an API does not just need to work today; it needs a verifiable contract, predictable change procedures, and consumer support policies across its entire lifecycle.

An **API contract** describes how two parties communicate: endpoints or operations, methods, parameters, request/response structures, data types, status codes, authentication, errors, and other critical rules. **Contract testing** verifies whether an implementation obeys the agreed expectations. **API lifecycle management** governs design, release, operations, evolution, deprecation, and retirement.

After this lesson, you will be able to:

- Distinguish API specifications, provider contracts, consumer expectations, and implementation tests.
- Design clear REST/HTTP contracts using OpenAPI and request/response examples.
- Choose appropriate schema validation, consumer-driven contract tests, provider verification, and integration tests.
- Evaluate whether a change is backward-compatible or breaking.
- Establish policies for versioning, deprecation, announcements, migration, and retirement.
- Integrate contract tests into CI/CD, API gateways, and governance workflows.
- Evaluate trade-offs across velocity, compatibility, security, cost, and operations using Well-Architected thinking.

## 2. What does an API contract include?

A good API contract must be concrete enough for two independent teams to implement without guessing each other's intent. For REST/HTTP, a contract typically describes:

| Component | What must be agreed upon | Example |
|---|---|---|
| Resources and operations | URI, HTTP method, business meaning | `GET /v1/bookings/{bookingId}` |
| Request | Path/query/header/body, data types, required fields | `bookingId` is a UUID; `Idempotency-Key` on creation |
| Response | Status codes, headers, bodies, nullability, and collections | `200` with Booking; `404` when not found/disallowed by policy |
| Error model | Stable error structure, machine-readable error codes | `code`, `message`, `traceId`, `details` |
| Authentication | How identity is proven | OAuth 2.0 bearer token |
| Authorization | Which permissions apply to which resources | Only the booking owner or authorized staff can view |
| Semantics | Idempotency, pagination, ordering, concurrency, retries | Retrying POST with same key does not create a second booking |
| Operational behavior | Timeouts, rate limits, quotas, caching, deprecation | `429` with `Retry-After` when appropriate |
| Compatibility | Rules for adding/removing/modifying fields, enums, and endpoints | New fields optional; old consumers ignore unknown fields |

Not every API uses REST. gRPC has Protocol Buffers and service definitions; GraphQL has schemas and operations; event APIs have event schemas, topics, keys, and delivery semantics. The universal rule is that **contracts must describe both the structure and the behavior consumers actually depend on**.

### 2.1. Distinguishing specifications from enforced contracts

- **API specification** (e.g., OpenAPI) is the machine-readable interface document.
- **Provider contract** is the set of rules the provider commits to fulfilling: endpoints, schemas, responses, errors, authorization, and semantics.
- **Consumer expectation** is what a consumer actually uses or requires: needed fields, handled status codes, event ordering, timeouts, and behavior.
- **Implementation** is the running code, gateway, middleware, service, and dependencies.
- **Contract test** verifies that the implementation conforms to the relevant specification/expectations.

Syntactically valid OpenAPI does not prove the actual server returns matching responses. Conversely, one successful endpoint test does not prove every consumer is supported. Contracts must be verified on both provider and consumer sides, alongside integration tests for dependency behavior.

## 3. Example API contract for BookingCloud

Suppose an equipment rental scheduling app has APIs to look up and create bookings. The contract should specify field types, states, and access permissions clearly.

### 3.1. Illustrative request and response

Create a booking:

~~~http
POST /v1/bookings HTTP/1.1
Host: api.booking.example.com
Authorization: Bearer <access-token>
Content-Type: application/json
Idempotency-Key: 6c78f6f0-12c3-4f25-8ed7-6c9c1f6e0101

{
  "deviceId": "dev-017",
  "slotId": "slot-2026-12-02-0900",
  "note": "Pickup at counter"
}
~~~

Successful response:

~~~http
HTTP/1.1 201 Created
Content-Type: application/json
Location: /v1/bookings/bkg-8124

{
  "id": "bkg-8124",
  "deviceId": "dev-017",
  "slotId": "slot-2026-12-02-0900",
  "status": "confirmed",
  "createdAt": "2026-11-18T09:00:00Z"
}
~~~

The values in this example are synthetic. An actual contract must clearly define:

- What format `deviceId` and `slotId` follow, whether they are case-sensitive, and length limits.
- Whether `note` is optional or nullable; length bounds and disallowed content.
- How long `Idempotency-Key` is retained, whether scoped by user or client, and what happens if the same key is sent with a different payload.
- `201 Created` is returned only after the order is durably committed; notification emails can be processed asynchronously.
- If the slot is already booked by someone else, return a contract-defined conflict error—never HTTP 200 with a free-form message string.

### 3.2. Stable error model

An error response can share a common structure:

~~~json
{
  "code": "SLOT_UNAVAILABLE",
  "message": "The time slot is no longer available.",
  "traceId": "01JCV2N7X5",
  "details": {
    "slotId": "slot-2026-12-02-0900"
  }
}
~~~

Never include stack traces, SQL, internal hostnames, tokens, or unnecessary personal data in responses. `message` is for appropriate display/logging; clients should branch on the stable `code` rather than parsing prose text.

| Status code | Meaning in example | What consumers should do |
|---|---|---|
| `400 Bad Request` | Invalid body or parameters | Fix input; do not retry verbatim |
| `401 Unauthorized` | Missing or invalid authentication credentials | Refresh/sign in per flow |
| `403 Forbidden` | Authenticated but unauthorized | Do not retry as a network error |
| `404 Not Found` | Resource does not exist or is hidden per policy | Handle according to agreed semantics |
| `409 Conflict` | Slot already taken or state conflict | Display conflict; choose another slot |
| `429 Too Many Requests` | Rate limit/quota exceeded | Back off and honor `Retry-After` if present |
| `5xx` | Provider or dependency failure | Bounded retry when operation is safe |

Status codes are part of the contract. Never change `409` to `400` merely to lump all errors together; consumers may rely on that code to display contention states.

### 3.3. Abbreviated OpenAPI specification

~~~yaml
openapi: 3.1.0
info:
  title: Booking API
  version: 1.0.0
paths:
  /v1/bookings:
    post:
      operationId: createBooking
      summary: Create a booking
      security:
        - bearerAuth: []
      parameters:
        - in: header
          name: Idempotency-Key
          required: true
          schema:
            type: string
            minLength: 16
            maxLength: 128
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: "#/components/schemas/CreateBookingRequest"
      responses:
        "201":
          description: Booking created
          content:
            application/json:
              schema:
                $ref: "#/components/schemas/Booking"
        "409":
          description: Slot conflict
          content:
            application/json:
              schema:
                $ref: "#/components/schemas/ApiError"
        "429":
          description: Rate limited
          headers:
            Retry-After:
              schema:
                type: string
          content:
            application/json:
              schema:
                $ref: "#/components/schemas/ApiError"
components:
  securitySchemes:
    bearerAuth:
      type: http
      scheme: bearer
      bearerFormat: JWT
  schemas:
    CreateBookingRequest:
      type: object
      additionalProperties: false
      required: [deviceId, slotId]
      properties:
        deviceId:
          type: string
          minLength: 1
        slotId:
          type: string
          minLength: 1
        note:
          type: string
          maxLength: 500
    Booking:
      type: object
      required: [id, deviceId, slotId, status, createdAt]
      properties:
        id:
          type: string
        deviceId:
          type: string
        slotId:
          type: string
        status:
          type: string
          enum: [pending, confirmed, cancelled]
        createdAt:
          type: string
          format: date-time
    ApiError:
      type: object
      required: [code, message, traceId]
      properties:
        code:
          type: string
        message:
          type: string
        traceId:
          type: string
        details:
          type: object
          additionalProperties: true
~~~

This is an abbreviated example illustrating how to describe an API, not a complete production specification. You must add servers, read/update/cancel operations, security scopes, full error responses, pagination, exact schema formats, and business rules. Notably, `additionalProperties: false` on requests can make adding fields count as breaking for strict validators/consumers; choose policies carefully.

## 4. Types of contract testing

### 4.1. Schema/specification validation

Checks whether OpenAPI/AsyncAPI/Protobuf definitions are valid: schema references, data types, required fields, response definitions, security schemes, and formats. It catches syntax errors or missing structures in docs, but does not verify that the live implementation complies.

### 4.2. Provider contract tests

Run tests directly against the provider implementation to verify actual endpoints:

- Response statuses and content types match the specification.
- JSON fields/types/required constraints match.
- Headers such as `Location`, `Retry-After`, and cache/security headers are proper.
- Authentication/authorization are enforced properly.
- Error responses maintain a stable structure.
- Critical semantics such as idempotency, pagination, and concurrency work.

Provider tests should run in CI or controlled test environments with synthetic data. Never use sensitive production data just for contract checks.

### 4.3. Consumer-driven contract testing

Consumer-driven contract (CDC) testing starts from what consumers genuinely need. Each consumer defines expectations for the requests/responses/events it relies on; the provider verifies those expectations before releasing.

For example, a mobile app reads only `id`, `status`, and `createdAt`. A consumer test catches if the provider removes `status` or changes `createdAt` into an unparseable type, even if the provider schema includes many other fields.

Typical flow:

~~~mermaid
flowchart LR
    C["Consumer test<br/>Mobile / Web / Partner"] --> PACT["Contract artifact"]
    PACT --> BROKER["Contract broker / registry"]
    PROVIDER["Provider verification<br/>Booking API"] --> BROKER
    BROKER --> COMPAT["Compatibility result"]
    COMPAT --> PIPE["CI/CD release gate"]
~~~

CDC is especially valuable when multiple teams deploy independently and the provider cannot run end-to-end tests with every consumer on every release. However, CDC only checks declared expectations; if a consumer never wrote tests for a behavior, the contract will not automatically catch regressions in that behavior.

### 4.4. Integration and end-to-end testing

Contract tests do not replace integration tests. They typically do not prove:

- That the real authentication provider, database, queue, or partner systems cooperate correctly in every scenario.
- Transactions, locking, consistency, timeouts, and retries across multiple dependencies.
- Performance under load, failover behavior, or whole-system resilience.
- That UI, DNS routing, network policies, WAF, and live deployments work end-to-end.

Choose tests by risk:

| Test type | Good at detecting | Limitations |
|---|---|---|
| Specification lint/validation | Malformed OpenAPI, missing fields | Does not test server runtime |
| Provider contract | Implementation violating contract | May miss real consumer perspectives |
| Consumer-driven contract | Breaking changes to declared consumers | Does not cover consumers without tests |
| Integration | Misaligned dependencies and protocols | Environments can be slow/hard to stabilize |
| End-to-end | Cross-system business journeys | Slow, flaky, hard to pinpoint root cause |
| Load/resilience | SLOs, saturation, timeouts, and failover | Resource-intensive; needs representative load models |

A balanced test pyramid has many small unit/schema/contract tests, targeted integration tests, and a small set of end-to-end tests for core business journeys.

## 5. Contract testing workflow in CI/CD

### 5.1. Provider pipeline

~~~mermaid
flowchart TD
    CHANGE["Pull request: code + API spec"] --> LINT["Lint / validate specification"]
    LINT --> DIFF["Diff against released version"]
    DIFF --> PTEST["Provider contract tests"]
    PTEST --> CDC["Verify consumer contracts"]
    CDC --> INT["Integration / security tests"]
    INT --> REVIEW["Review breaking changes and release notes"]
    REVIEW --> GATE{"Release gate passed?"}
    GATE -->|"No"| FIX["Fix implementation or version/plan"]
    FIX --> LINT
    GATE -->|"Yes"| DEPLOY["Deploy canary / staged rollout"]
    DEPLOY --> VERIFY["Smoke + telemetry + rollback check"]
~~~

One workflow arrangement:

1. Developer updates code and specification in the same pull request.
2. Linter checks naming, schemas, security definitions, and internal conventions.
3. Diff tool compares against the released contract to detect removed operations, type changes, newly required fields, or described behavior shifts.
4. Provider tests run against the built implementation.
5. Provider verifies active consumer contracts in the registry/broker.
6. Integration/security tests exercise critical boundaries.
7. Reviewers inspect release notes, migration guides, deprecation policies, and retirement dates if applicable.
8. Deploy via canary/staged rollout; monitor telemetry before expanding.

### 5.2. Consumer pipeline

Consumers share responsibility too. When a consumer changes how it calls an API:

- Update expectations in the contract artifact.
- Verify the contract against supported provider versions.
- Run tests covering status codes, optional fields, timeouts, and error codes.
- Never assume fields outside what the consumer uses will always exist or remain unchanged.
- Verify the minimum provider version required by the new consumer release.

A broker/registry can store contract artifacts, verification results, and consumer/provider version mappings. Release pipelines consult those results to judge whether candidate version pairs are compatible.

### 5.3. Pre-deployment compatibility matrix

| Consumer | Current provider | Candidate provider | Required conclusion |
|---|---|---|---|
| Mobile v4 | API v1.2 | API v1.3 | Do consumer contracts pass? |
| Web v8 | API v1.2 | API v1.3 | Were any fields/behaviors altered? |
| Partner X | API v1.2 | API v1.3 | Does the consumer have published contracts or custom SLAs? |
| Internal worker v3 | API v1.2 | API v1.3 | Do retries/idempotency still hold? |

Not every consumer has to update at the same time. The goal is ensuring the candidate provider stays compatible with consumers inside the published support window, or follows an agreed transition plan.

## 6. Compatible changes and breaking changes

A change is **backward-compatible** when older consumers continue functioning properly per the committed contract. However, compatibility depends on how schemas are interpreted and how strict consumers are.

### 6.1. Examples of usually compatible changes

- Adding a new endpoint without altering existing endpoints.
- Adding an optional response field when consumers are expected to ignore unknown fields.
- Adding an optional request field when the server supplies an appropriate default/behavior.
- Adding an optional header that does not alter old semantics.
- Raising rate/size limits without violating other commitments/quotas.

Never assume every consumer ignores new fields. Generated clients or strict JSON validators can reject unknown properties. Always check the contract and how codegen/consumers behave.

### 6.2. Examples of typically breaking changes

- Removing or renaming a field actively used by consumers.
- Changing a data type from string to number, or making an incompatible format change.
- Turning an optional field into a required field.
- Altering enum semantics or removing an existing enum value.
- Removing an endpoint, changing HTTP method, path, or status codes consumers rely on.
- Changing auth scopes, access permissions, pagination, or ordering in ways that break prior assumptions.
- Tightening validation so previously valid requests are rejected.
- Changing defaults or business meaning even if the schema stays identical.

### 6.3. Rules for enums and response fields

Adding an enum value to a response can break consumers using exhaustive switches. For instance, if a client only knows `pending`, `confirmed`, and `cancelled`, and the provider adds `expired`, the client may crash or mishandle it. Contracts must stipulate that consumers include an unknown/default branch, and providers must treat enum additions as risk-bearing changes.

For request enums, adding a new value is usually safe if the provider accepts it while older consumers simply do not send it. For response enums, consumers receiving the new value must be verified.

### 6.4. Change matrix

| Change | Default assessment | Why review is required |
|---|---|---|
| Add optional response field | Usually compatible if consumers ignore unknown fields | Generated clients/strict parsers |
| Add optional request field | Usually compatible if server has a default | Validation, payload signing, strict schemas |
| Remove response field | Breaking | Old consumers may still read the field |
| Optional → required | Breaking | Old requests omit the field |
| Change string → integer | Breaking | Deserialization and client logic |
| Add response enum value | Risky | Exhaustive switches, unknown handling |
| Change status code | Risky or breaking | Retry/UI/business branching |
| Change field meaning while keeping schema | Semantically breaking | Consumers misinterpret values |
| Tighten rate limits | Potentially operationally breaking | Consumers hit more 429s |
| Change auth scopes/claims | Breaking for current consumers | Existing tokens and permissions fail |

Backward compatibility is not just diffing JSON schemas. Evaluate **semantics**, permissions, operations, and unwritten assumptions.

## 7. API versioning: choosing manageable evolution

### 7.1. URL/path versioning

Examples: `GET /v1/bookings` and `GET /v2/bookings`. Advantages are high visibility, clean routing/caching/logging separation, and explicit version selection by consumers. Drawbacks include maintaining multiple versions in parallel and potential code duplication if poorly managed.

### 7.2. Header/media type versioning

Clients pass version in headers or media types, e.g., `Accept: application/vnd.example.booking-v2+json`. URIs stay more stable, though versions are harder to spot by eye and require gateway/tooling support. Define behavior when the version header is missing or unsupported.

### 7.3. Not versioning on every change

For APIs with strict compatibility policies, additive changes can ship under the same major contract. You do not need `v2` just for adding an optional field if consumer compatibility is verified. Conversely, breaking changes require a clear migration strategy: a new version, parallel support window, and retirement schedule.

| Approach | Advantages | Trade-offs |
|---|---|---|
| URL version | High visibility, clear routing | New URLs/versions, multiple code paths |
| Header/media type | Stable URIs, supports representation negotiation | Harder to debug, depends on gateway/client tooling |
| Backward-compatible evolution | Fewer versions, less fragmentation | Requires strict contract discipline and strong testing |

There is no single best versioning strategy for every API. What matters is publishing the policy, testing it, and ensuring consumers know how to select versions.

### 7.4. Never confuse API version with application version

Container image tags or service releases can increment on every deployment while the API contract stays v1.2. Every build does not need a new API version. Distinguish:

- Build/release version: version of the deployable artifact/service.
- API contract version: published interface compatibility level.
- Schema/event version: payload/event version with its own lifecycle.

## 8. Responsible deprecation and retirement

Deprecation means the provider announces an operation/version is no longer recommended and will lose support in the future. Retirement/sunset is when the provider stops serving it. **Marking something deprecated does not mean deleting it immediately**; consumers need time to migrate.

### 8.1. API lifecycle

~~~mermaid
stateDiagram-v2
    [*] --> Draft
    Draft --> Reviewed: contract + threat review
    Reviewed --> Released: tests pass
    Released --> Supported: production verified
    Supported --> Deprecated: migration plan announced
    Deprecated --> Retired: sunset date reached
    Deprecated --> Supported: deprecation cancelled
    Retired --> [*]
~~~

### 8.2. Contents of a deprecation notice

A useful notice includes the deprecated API/operation/version and affected consumer scope; rationale; replacement API and field/behavior mapping guide; deprecation start date and planned sunset date; how to get support; how to monitor usage; and the owning contact.

You can use `Deprecation` and `Sunset` response headers per organizational standards/tooling alongside documentation and dashboards; headers do not replace proactive outreach to key partners.

### 8.3. Phased migration plan

1. **Announce:** publish replacement version/operation, rationale, and sunset schedule.
2. **Prepare:** release docs, SDKs, samples, and migration guides.
3. **Dual support:** run old and new versions side by side during the announced support window.
4. **Measure:** use access logs/telemetry keyed by managed client IDs/API keys to spot consumers still calling the old version.
5. **Migrate:** coordinate consumer by consumer, running contract tests against the new version.
6. **Warn:** send pre-deadline warnings, optionally attaching deprecation headers/telemetry.
7. **Sunset:** stop accepting traffic per policy; return clear errors and link to status pages if appropriate.
8. **Remove:** clean up legacy code, routing, secrets, quotas, and infrastructure once zero dependencies remain.

### 8.4. Basing support windows on data

Never pick 30/60/90 days as an arbitrary blanket rule. Mobile consumers may take weeks for end users to update apps; B2B partners have release and approval cycles; internal services can deploy faster. Base deprecation windows on contractual commitments/SLAs, consumer upgrade velocity, security risk, remaining traffic, and the cost of running multiple versions.

If an older API has a critical vulnerability, the organization may have to sunset faster, paired with impact-mitigation plans and direct communication.

## 9. Schema management for asynchronous APIs

Not all communication is HTTP request/response. BookingCloud emits `booking.created` events via a queue to notification workers and reporting consumers. Event schemas are contracts too.

Example:

~~~json
{
  "eventId": "evt-9182",
  "eventType": "booking.created",
  "schemaVersion": 1,
  "occurredAt": "2026-11-18T09:00:00Z",
  "data": {
    "bookingId": "bkg-8124",
    "deviceId": "dev-017"
  }
}
~~~

Required rules:

- Consumers handle duplicate events via `eventId` or appropriate idempotency mechanisms.
- Events are emitted only after business state commits; transactional outboxes link DB transactions and publication.
- Payloads minimize personal data; consumers fetch additional authorized details when needed.
- Schema registries/contract repositories enforce compatibility rules such as backward, forward, or full compatibility.
- Changing required fields, enums, or semantics must account for all consumers; do not deploy incompatible producers before consumers can handle them if delivery happens immediately.
- DLQs/replays preserve schema versions and include upgrade procedures when consumers process older messages.

**Backward compatibility** for events usually means new consumers can read old events; **forward compatibility** means old consumers can safely ignore or handle new events. Clarify which direction and policy your schema registry enforces. A compatible schema check alone does not guarantee sound business semantics.

## 10. Security and governance of API contracts

API contracts must clearly state security requirements without embedding secrets. Key review areas:

### 10.1. Authentication and authorization

- Security schemes describe how callers authenticate; scopes/roles describe operation-level permissions where appropriate.
- APIs enforce **per-resource/object** authorization—User A must not view User B's booking merely by holding a valid JWT.
- Documentation distinguishes 401 vs. 403 per agreed behavior.
- Client secrets, signing keys, access tokens, and sensitive data must never be committed into OpenAPI examples or repositories.

### 10.2. Inputs, outputs, and error disclosures

- Bound payloads, string lengths, array counts, nesting depth, and data types.
- Specify validation, normalization, and handling of unknown fields.
- Responses return only data the consumer is authorized to see.
- Errors never expose stack traces, SQL, internal hostnames, or unnecessary PII.
- Audit critical changes; include trace/correlation IDs while avoiding logging tokens/sensitive request bodies.

### 10.3. API gateways do not replace provider contracts

Gateways can apply TLS termination, authentication, rate limiting, quotas, routing, schema validation, and observability. Still, gateway policies and provider code must stay aligned:

- Gateways must not accidentally transform statuses/bodies into a different contract.
- Gateway authentication never eliminates business-object authorization inside services.
- Version routing and deprecation behavior must be tested.
- Rate limits and timeouts must be propagated/interpreted consistently.
- Direct origin access must not bypass intended gateway policies.

## 11. API catalogs, ownership, and governance

As API counts grow, maintain a catalog answering who owns, who consumes, and the support status of each contract.

| Metadata | Purpose |
|---|---|
| API name / domain | Identifies the service and business domain |
| Provider owner / on-call | Team responsible for engineering and incidents |
| Consumer list | Applications/services/partners using the API |
| Spec location / version | Authoritative contract source |
| Lifecycle state | Draft, supported, deprecated, retired |
| Security classification | Data sensitivity and control requirements |
| SLOs/SLAs | Availability, latency, quota, or support commitments |
| Deprecation/sunset | Transition schedule and notification duties |
| Runbook/observability | Dashboards, alerts, remediation procedures |

An API with no clear owner or unknown consumers is very hard to deprecate safely. Access logs, API keys/client identities, and service catalogs must work together to attribute usage; never rely on raw IPs alone when consumers share NAT.

## 12. Measuring contract and lifecycle quality

Do not merely count contract tests. Measure whether they catch issues and enable safe change.

| Metric | Meaning | Usage |
|---|---|---|
| Consumer contract coverage | Percentage of key consumers with maintained contract tests | Identify blind spots |
| Provider verification pass rate | How consistently providers satisfy consumer contracts | Release gate |
| Breaking changes caught pre-release | Breaking shifts intercepted before production | Evaluate control effectiveness |
| Contract-related incidents | Outages caused by post-release incompatibility | Prioritize test/spec improvements |
| Deprecated version traffic | Remaining usage of deprecated APIs | Inform sunset readiness |
| Consumer migration completion | Percentage of consumers migrated | Manage retirement |
| Time to adopt new contracts | Effort/duration for consumers to adopt new versions | Assess migration friction |
| API error/latency by version | Operational behavior per version | Spot version-specific regressions/consumers |

Metrics need clear definitions and denominators. "100% of contract tests pass" does not mean 100% of production consumers are verified if only two of ten consumers maintain contract tests.

## 13. Well-Architected assessment

| Perspective | Review questions | Evidence |
|---|---|---|
| **Operational Excellence** | Who owns contracts, release gates, and deprecation outreach? | API catalog, pipelines, runbooks, change records |
| **Security** | Do contracts specify auth, authorization, and data classification; do errors avoid leaks? | Security tests, scopes, audits, log redaction |
| **Reliability** | Do old consumers stay working during provider deploys; are retries/idempotency sound? | CDC/provider tests, canaries, rollbacks, incident metrics |
| **Performance Efficiency** | Do payloads, pagination, rate limits, and timeouts handle load? | Load tests, per-version latency, throughput |
| **Cost Optimization** | What does maintaining multiple versions, gateway routes, and test environments cost? | Per-version usage, cost per API call, retirement plans |
| **Sustainability** | Are legacy/unused APIs, duplicate data, and idle test infra cleaned up? | Deprecation traffic, catalog cleanup, resource lifecycles |

An API contract can remain schema-compatible yet still breach performance targets if responses bloat or pagination disappears. Review across multiple perspectives before approving.

## 14. Practice lab: evolving contracts without breaking consumers

Booking API v1 is used by three consumers:

- Mobile app v4 reads only `id`, `status`, and `createdAt`.
- Web v8 also displays `deviceId` and `slotId`.
- Partner X creates bookings and handles `409` when slots are taken.

The provider proposes releasing:

1. Add an optional `pickupLocation` response field.
2. Change `status` from a string to an object containing `code` and `label`.
3. Add enum value `expired`.
4. Require `customerPhone` on create-booking requests.
5. Retire endpoint `/v1/bookings`.
6. Replace `409` with `400` for slot conflicts.

Complete these tasks:

**Exercise 1 — Classification:** mark each change as additive, risky, or breaking; identify which consumers could be impacted and why.

**Exercise 2 — Contract tests:** write at least three consumer expectations and three provider verification cases. Include one negative case for authorization or validation.

**Exercise 3 — Versioning:** choose how to roll out the status and required-field changes; explain whether v2 is needed or compatible evolution within v1 is possible.

**Exercise 4 — Migration:** draft a deprecation notice for v1 specifying replacement API, justified timeline, migration guide, and how remaining consumers will be measured.

**Exercise 5 — CI/CD:** design a release gate spanning OpenAPI linting, schema diffing, provider verification, consumer contracts, security/integration tests, and canary rollout.

**Exercise 6 — Operations:** define owners, per-API-version dashboards, sunset metrics, and criteria to end support.

### Self-check answer framework

| Change | Initial assessment | What must be proven |
|---|---|---|
| Add optional `pickupLocation` | Usually additive | Consumers ignore new fields; no PII leaks or oversized payloads |
| Change `status` to object | Breaking | Needs field mapping/new version or time-bounded transition |
| Add `expired` enum | Risky for exhaustive consumers | Consumers have unknown/default branches |
| Add required `customerPhone` | Breaking for old requests | Whether defaults/migration work; validate business and data justification |
| Remove `/v1/bookings` | Breaking | Consumers migrated and sunset announced |
| `409` to `400` | Semantically breaking | Consumers handle conflict explicitly; preserve semantics or version |

Never approve based solely on this table. Test real consumers, verify implementations, and review security/operational behavior.

## 15. Pre-release and deprecation checklist

- [ ] Specifications are versioned contract sources with assigned owners.
- [ ] Request/response/error/auth/authorization and business semantics are documented.
- [ ] Schema linting, provider contract tests, and consumer expectations run in CI.
- [ ] Integration/security tests verify critical dependencies and trust boundaries.
- [ ] Diffs against supported versions catch breaking changes.
- [ ] Unknown fields, enum evolution, optional/required, and nullability have clear policies.
- [ ] Idempotency, retries, pagination, timeouts, and rate limits are verified.
- [ ] Release gates block incompatible candidates; canaries have telemetry and rollbacks.
- [ ] The API catalog tracks provider owners, consumers, SLOs, security classifications, and runbooks.
- [ ] Deprecations include rationale, replacement APIs, migration guides, sunset dates, and support channels.
- [ ] Usage by version/consumer is measured prior to retirement.
- [ ] Post-retirement, legacy routing, code, secrets, quotas, docs, and infra are cleaned up safely.

Contract testing helps providers and consumers catch incompatibilities before release; lifecycle management ensures both sides know when and how to evolve. Combining testable specifications, contract tests, compatibility policies, telemetry, and clear governance lets APIs evolve independently while preserving the reliability of the entire cloud system.
