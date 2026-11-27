# Deprecation and End-of-Support Criteria for Old Contracts

In a microservices architecture, a producer may want to change an API to reduce technical debt, improve data design, or release a new version. However, **a producer stopping old behavior does not mean every consumer is ready**. If Billing Service still reads `totalMinor` while Order Service returns only `amount.minor`, a producer deployment can break the consumer even if producer v2 works flawlessly.

**Deprecation** announces that an old contract is **no longer recommended for new integrations** while usually still being served during a transition window. **End of support (EOS / end of life)** is a conditional operational decision: when is the producer permitted to stop guaranteeing old behavior, delete old code, or stop publishing supporting artifacts? The answer must rest on **published policy, evidence of consumer migration, compatibility testing, and rollback readiness**—never merely a gut feeling that "it's past the deadline."

This lesson belongs to the **Versioning and Compatibility** chapter of the **SPRING_CLOUD_CONTRACT** module. Spring Cloud Contract lets teams define HTTP or messaging contracts using the **Groovy/YAML DSL**, generate **producer verification tests**, publish **stubs**, run **Stub Runner** in consumer tests, and integrate CI to detect incompatible API changes. The focus of this lesson is governing the **lifecycle of old contracts** within that exact workflow.

## 1. Distinguishing Four Contract States

| State | Does Producer Still Serve It? | What Should Consumers Do? | Tests to Retain |
| --- | --- | --- | --- |
| **Active** | Yes, under current SLA/contract. | Safe for new integrations. | Producer contract tests and consumer tests. |
| **Deprecated** | **Yes**, unless docs state otherwise; support level must be public. | Do not build new integrations; begin migrating. | **Continue testing the old contract** throughout the committed support window. |
| **Sunset scheduled** | Yes until the announced date, unless extended per policy. | Complete migration; verify deployed environments. | Test both old and new; track remaining consumers. |
| **Retired / unsupported** | No longer committed to serving the old contract. | No longer depend on that version. | Legacy support tests may be dropped once EOL criteria are approved; retain historical evidence. |

**Deprecated does not mean "deleted."** While the producer still claims support for v1, a PR causing v1 to return the wrong schema is a **contract violation**, even after v2 exists. Conversely, "retired" does not necessarily mean deleting all documentation or old stub JARs from repositories: you need a retention policy and the ability to reproduce historical incidents.

Common terms:

- **Deprecation announcement:** notice specifying from which date an old version should no longer be used for new development.
- **Migration window:** period during which consumers are supported while moving to the new version.
- **Sunset date:** planned date when the old interface ceases to be provided; subject to extension per policy/conditions.
- **End of support:** end of commitments for bug fixes, compatibility, or operations on the old contract per policy.
- **Removal / retirement:** deleting endpoints, message publishers, routes, or related decoders after completing EOL procedures.
- **Rollback window:** period preserving the ability to restore the old contract if retirement rollout hits issues.

Not every organization defines these states identically. **Your team's API docs/ADRs must clearly explain** what security fixes, bug fixes, and SLAs a "deprecated" version still receives, and when old behavior actually stops.

## 2. API Version Differs from `stubs` Artifact Version

A very common misconception: assuming `order-service:2.0.0:stubs` JAR contains only API v2, while `order-service:1.0.0:stubs` JAR guarantees producer 2.0 still serves API v1. Those two versions **mean different things**.

| Version Type | Example | Question It Answers |
| --- | --- | --- |
| **API contract version** | `/api/v1/orders/{id}`, `/api/v2/orders/{id}` | Which interface/semantics is the consumer calling? |
| **Producer artifact version** | `com.acme:order-service:2.0.0` | Which build/release of Order Service is deployed? |
| **Stub artifact version** | `com.acme:order-service:2.0.0:stubs` | Which set of mappings/contracts was published alongside that producer build? |
| **Consumer application version** | `billing-service:3.4.0` | Which Billing build is running and has it migrated yet? |
| **Message schema version** | `eventType=OrderCreated`, `schemaVersion=2` | Under which schema must the message payload/headers be decoded? |

Producer release `2.0.0` **may still support both API v1 and API v2**. If so, the **stub artifact for release 2.0.0 must express all contracts that producer commits to serving**, including legacy v1 where applicable. Keeping `1.0.0-stubs.jar` in the Maven repository only lets you verify/trace the old producer release; **it does not test producer 2.0.0's implementation** if v1 accidentally broke.

**Rule:** artifact version is a **build trace**; active/deprecated/retired status is an **interface support policy**. The two axes are related yet not interchangeable.

## 3. Running Example: Order Service v1 and v2

Suppose **Billing Service** reads order payment details from **Order Service**.

**Active HTTP v1 contract:**

~~~http
GET /api/v1/orders/42
Accept: application/json
~~~

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{"id":42,"status":"PAID","totalMinor":125000}
~~~

**Target HTTP v2 contract:**

~~~http
GET /api/v2/orders/42
Accept: application/json
~~~

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "orderId": "ORD-42",
  "state": "PAID",
  "amount": {
    "minor": 125000,
    "currency": "VND"
  }
}
~~~

In v2, the designer decided:

- Numeric `id` is replaced with business-meaningful string `orderId`.
- `status` is renamed to `state`.
- `totalMinor` moves into an `amount` object with currency.
- Paths carry explicit versions: `/api/v1/` and `/api/v2/`.

**This would be a breaking change if applied to the v1 response**, because old clients might fail to parse it. Adding an **independent v2 endpoint** while preserving **v1 with its old semantics** is a safer migration strategy.

### 3.1. No Single Versioning Scheme Is Mandatory

The example uses **URL path versioning** for readability. In other systems, versions may live in media types, headers, GraphQL schemas, or another explicit convention. What matters is that consumers **can identify which interface they are using**, the producer can serve both concurrently when needed, and tests protect each variant.

**Never assume** bumping a Java library's patch/minor version corresponds to API version changes. An API can suffer a breaking change inside a release named "minor" if governance is weak; conversely, a major application release can keep serving legacy contracts.

## 4. The Expand → Migrate → Contract Strategy

Three-phase transitions reduce risk:

~~~mermaid
flowchart TD
    A["Expand: add API v2, keep v1 working"] --> B["Verify v1 + v2 on current producer"]
    B --> C["Publish stub with release: v1 + v2 mappings"]
    C --> D["Migrate: consumers deploy v2 client"]
    D --> E["Collect usage evidence and owner confirmations"]
    E --> F{"v1 EOL criteria met?"}
    F -->|No| G["Keep serving v1, investigate blockers"]
    G --> E
    F -->|Yes| H["Contract: controlled retirement rollout"]
    H --> I["Monitor errors and keep rollback ready"]
~~~

**Expand:** producer adds the new interface **without breaking the old interface**. Both v1 and v2 contracts coexist and are verified in the active release.

**Migrate:** consumers update HTTP clients, DTOs, validation, error handling, feature flags, and release pipelines. The producer monitors usage to locate un-migrated consumers.

**Contract:** only after passing the agreed **EOL gate** does the producer remove old endpoints/behavior. Legacy contract tests leave the build only after an end-of-support decision, not the moment a developer finishes coding the v2 endpoint.

This model does not force projects to maintain **two separate backend codebases**. The producer can share an internal application service and use two response mapping layers v1/v2 to avoid duplicating business logic, provided **each interface is tested independently**.

## 5. Groovy DSL: Keeping the v1 Contract in a Release That Already Has v2

In a producer repository supporting both APIs, you can store:

~~~text
src/test/resources/contracts/
└── orders/
    ├── get_paid_order_v1.groovy
    └── get_paid_order_v2.groovy
~~~

**The v1 contract must keep working:**

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    name 'shouldKeepLegacyOrderV1'
    description 'API v1 still returns committed schema during deprecation'

    request {
        method 'GET'
        url '/api/v1/orders/42'
        headers {
            header('Accept', 'application/json')
        }
    }

    response {
        status 200
        headers {
            contentType(applicationJson())
        }
        body(
            id: 42,
            status: 'PAID',
            totalMinor: 125000
        )
    }
}
~~~

**The v2 contract is added:**

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    name 'shouldReturnOrderV2'
    description 'API v2 returns orderId, state, and amount with currency'

    request {
        method 'GET'
        url '/api/v2/orders/42'
        headers {
            header('Accept', 'application/json')
        }
    }

    response {
        status 200
        headers {
            contentType(applicationJson())
        }
        body(
            orderId: 'ORD-42',
            state: 'PAID',
            amount: [
                minor: 125000,
                currency: 'VND'
            ]
        )
    }
}
~~~

Both contracts generate **two independent verification suites**. Any PR changing the v1 response at `/api/v1/orders/42` into the v2 format must make the **generated v1 producer test FAIL**. That is the practical point of **keeping legacy contracts in the build**.

**Never overwrite `get_paid_order_v1.groovy`'s contents with v2 while keeping the v1 filename.** To transition, create a separate v2 contract, identify consumers using v1, and wait out the deprecation window. Also never exclude v1 from plugin scanning while the producer still commits to serving v1.

### 5.1. Legacy Contracts Often Need More Than the Happy Path

The producer must preserve **all committed scenarios**, not just one 200 sample response. For example:

| Case | Should v1 Contract Still Check It? | Why |
| --- | --- | --- |
| Order exists, status PAID | **Yes** | Happy path used by consumers. |
| Order missing, returns 404 with old error schema | **Yes if committed** | Old clients may parse error code/body. |
| Required query/header | **Yes if part of contract** | Silently tightening requirements can break old clients. |
| Unauthorized, returns 401/403 | **Yes if supported behavior** | Migration must not break v1 auth. |
| Pagination/sort/filter | **Yes if v1 has conventions** | Changing order or default sort can be breaking. |
| Runtime throughput/SLA | Test separately per policy | Contract status/body checks do not replace performance tests. |

**A single passing v1 generated test does not automatically prove all v1 consumers work.** You need contracts covering critical behaviors plus confirmation from supported consumer tests.

## 6. YAML DSL: Equivalent Examples Without Duplicate Loading

Teams choosing YAML can write v1:

~~~yaml
description: API v1 still served during migration window
request:
  method: GET
  url: /api/v1/orders/42
  headers:
    Accept: application/json
response:
  status: 200
  headers:
    Content-Type: application/json
  body:
    id: 42
    status: PAID
    totalMinor: 125000
~~~

And v2 in a separate file:

~~~yaml
description: API v2 with new amount schema
request:
  method: GET
  url: /api/v2/orders/42
  headers:
    Accept: application/json
response:
  status: 200
  headers:
    Content-Type: application/json
  body:
    orderId: ORD-42
    state: PAID
    amount:
      minor: 125000
      currency: VND
~~~

These are **two distinct contracts**, not two duplicate ways to write the same endpoint. However, if you also leave equivalent Groovy files for the same v1/v2 in the plugin's scan path, you can generate duplicate tests/mappings. **Pick one authoritative DSL per case**, keep version mappings explicit, and inspect generated tests.

## 7. Producer Implementation: Serving Both in Parallel Without Mixing Schemas

Minimal Spring MVC controller example:

~~~java
package com.acme.orders;

import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api")
public class OrderController {

    @GetMapping(
        value = "/v1/orders/{id}",
        produces = MediaType.APPLICATION_JSON_VALUE
    )
    public OrderV1 getOrderV1(@PathVariable long id) {
        if (id != 42L) {
            throw new org.springframework.web.server.ResponseStatusException(
                org.springframework.http.HttpStatus.NOT_FOUND);
        }
        return new OrderV1(42L, "PAID", 125000L);
    }

    @GetMapping(
        value = "/v2/orders/{id}",
        produces = MediaType.APPLICATION_JSON_VALUE
    )
    public OrderV2 getOrderV2(@PathVariable long id) {
        if (id != 42L) {
            throw new org.springframework.web.server.ResponseStatusException(
                org.springframework.http.HttpStatus.NOT_FOUND);
        }
        return new OrderV2(
            "ORD-42", "PAID", new Amount(125000L, "VND"));
    }

    public record OrderV1(long id, String status, long totalMinor) {}
    public record Amount(long minor, String currency) {}
    public record OrderV2(String orderId, String state, Amount amount) {}
}
~~~

This controller illustrates only **two HTTP representations of the same order**. A real implementation should share one service/domain model and map to two DTOs rather than duplicating logic. ID 42 is a fixture, not how production controllers are written.

If one day a developer changes `getOrderV1` to return `OrderV2` to "clean up duplicate code," **the v1 contract test must fail**. Never delete the v1 test to turn the build green while consumers still depend on it. Migrate consumers and complete EOL first.

### 7.1. Do Not Treat Deprecation Annotations as Proof of Migration

Annotations like `@Deprecated` on a Java method warn only **Java compilers/callers**; they **do not notify** HTTP consumers written in other languages, do not version the API, and do not force consumers to migrate.

Marking code deprecated is helpful for the producer team, yet it must be paired with **public notices to consumers, changelogs, docs, and usage evidence**.

## 8. Deprecation Notices: Clear on Who, What, and When

A minimum-quality notice should answer:

1. **Which contract** is deprecated: exact method/path/header/media type/message destination/schema version.
2. **Effective date** when deprecated status begins.
3. **Replacement version** and key differences in fields, error schemas, auth, and semantics.
4. **Target sunset date** or conditions determining it, with explicit timezone.
5. **Responsible team**, support channel, and how consumers report blockers.
6. **Migration guide** with code examples, matching contracts/stubs, tests, and rollback instructions.
7. **Scope of v1 commitment during the migration window**: security fixes, critical defects, bug fixes, SLA.
8. **How consumer migration will be verified**, including infrequent scheduled jobs.

Example **hypothetical learning timeline**, not a notice for a real service:

| Milestone | Example Date | Explanation |
| --- | --- | --- |
| Publish v2 + keep v1 | 2027-01-15 | Producer has both contracts; consumers can start testing migration. |
| Announce v1 deprecated | 2027-02-01 | No new v1 integrations accepted; migration plan published. |
| Per-consumer progress review | 2027-04-01 | Reconcile deployments and live requests; resolve blockers. |
| Planned sunset | 2027-06-30 | **Applied only if EOL gates pass and are approved**. |
| Post-retirement monitoring | After closing v1 | Retain monitoring/rollback readiness per policy window. |

**A sunset date is a communication commitment, not sufficient technical grounds to delete code.** If critical consumers have not migrated or unresolved incidents remain, manage exceptions and adjust plans explicitly rather than deleting the API merely because the calendar date arrived.

## 9. HTTP Signals and API Documentation

Beyond email/changelogs/portals/ADRs, a producer can publish the **planned sunset timestamp** via standard HTTP response headers when API policy supports it.

Example v1 response once a sunset date is scheduled:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Sunset: Wed, 30 Jun 2027 23:59:59 GMT

{"id":42,"status":"PAID","totalMinor":125000}
~~~

The `Sunset` header indicates **when a resource is expected to become unavailable** per API conventions; it **does not automatically turn off the endpoint** and does not replace migration docs. When adding deprecation/link metadata, follow syntax and standards supported by your clients/tooling rather than inventing custom headers and expecting consumers to understand them.

If the producer commits to the **`Sunset` header** as part of the interface, add an assertion in the Groovy contract:

~~~groovy
response {
    status 200
    headers {
        contentType(applicationJson())
        header('Sunset', 'Wed, 30 Jun 2027 23:59:59 GMT')
    }
    body(id: 42, status: 'PAID', totalMinor: 125000)
}
~~~

**Note:** add this to the contract **only when the producer actually emits the header** and the expected value is policy-approved. Deprecation/sunset headers carry policy metadata; if the date changes, update notices and contracts in a controlled way to avoid test failures from stale dates.

To ensure consumers actually notice, combine API documentation (such as OpenAPI descriptions or changelogs), direct outreach to owners, and monitoring of deprecation headers. Never assume every HTTP client automatically parses or surfaces this header to operators.

## 10. EOL Criteria Must Be Measurable, Not Just "90 Days Have Passed"

An end-of-support decision should enforce **mandatory evidence-backed gates**. Below is a practical set of criteria to adapt to your organization's SLAs and risk profile:

| Gate | Verification Question | Suitable Evidence | Owner |
| --- | --- | --- | --- |
| **G1. Policy communicated** | Were consumers notified of timelines and migration path? | Changelog/announcement/ADR and delivery confirmation. | API owner. |
| **G2. Working replacement** | Does v2 provide feature parity for required use cases? | Producer verification + functional/security tests. | Producer team. |
| **G3. Complete consumer inventory** | Do we know who uses v1, who owns them, and which versions run? | Service catalog, access logs, tracing, registries, owner sign-off. | Platform + consumers. |
| **G4. Migration deployed** | Are critical consumers actually running v2 across all supported environments? | Deployment evidence, release records, consumer stub tests. | Consumer owners. |
| **G5. No non-exempt v1 traffic** | Is there real usage or missed batch/offline jobs? | Metrics/logs over an adequate window, reconciled with job schedules. | SRE/Platform. |
| **G6. Errors & compatibility verified** | Are v2 error handling, auth, timeouts, and business semantics right? | Contract tests, integration tests, and migration validation. | Producer + consumers. |
| **G7. Rollback plan exists** | If removing/disabling v1 breaks prod, how do we recover? | Playbook, feature flag/gateway route, canary, rehearsal. | Release/SRE. |
| **G8. Retirement approved** | Do risk owners and stakeholders agree with zero blockers left? | Approved EOL decision record, deploy schedule, final notice. | API owner/change authority. |

**No gate may be marked PASS on unverified assumptions.** A 24-hour metric window does not prove a monthly cron job migrated. A green Stub Runner test does not prove consumer v2 is deployed in production. A sent email does not prove clients received it with sufficient time to act.

### 10.1. Higher-Risk Systems Need Additional Gates

- **Legal compliance or customer contracts:** minimum notice windows, extension options, or partner sign-offs.
- **On-prem/offline software:** customers may be offline and invisible to traffic metrics; require supported-version certification and release policies.
- **Long-lived event data:** ensure stored v1 data remains readable/replayable.
- **Mobile/embedded apps:** slow rollouts and low update rates; you cannot force every device to upgrade at once.
- **Multi-region systems:** monitoring and deployments must cover every region/tenant, not just the highest-traffic zone.

These gates make EOL a **risk-controlled decision** rather than mere code cleanup.

## 11. How Do You Know Which Consumers Still Use v1?

No single signal works in every system. Combine **declared dependencies** with **runtime observation**:

~~~mermaid
flowchart TD
    A["Consumer inventory + owners"] --> D["Migration status table"]
    B["Gateway/access logs by version/path"] --> D
    C["Tracing, analytics, scheduled jobs, offline users"] --> D
    D --> E["Owner interviews/confirmations and release evidence"]
    E --> F{"Any consumer still dependent on v1?"}
    F -->|Yes or unknown| G["Keep v1, open blocker/exception"]
    F -->|No + sufficient evidence| H["Review EOL gates"]
~~~

Commonly useful sources:

| Source | What It Measures | Limitations |
| --- | --- | --- |
| API gateway logs / route metrics | Requests by path/header/API version, rate, and errors. | May lack owner attribution, short retention, internal traffic bypassing gateway. |
| Distributed tracing | Consumer service and downstream call paths. | Sampling can miss rare tasks. |
| Service catalog/ownership | Registered dependencies, environments, and contacts. | May be incomplete or stale if onboarding is inconsistent. |
| Consumer CI contract tests | Whether consumer codebase works with v2 contract. | **Does not prove the code is deployed**. |
| Deployment/release records | Which consumer version runs in each environment. | Cannot prove no rogue old binary lingers elsewhere. |
| Batch/scheduled jobs | Weekly/monthly/quarterly jobs still hitting v1. | Observation window must span rare job cadences. |
| External partner confirmations | Whether external integrations have switched over. | Relies on self-reporting; needs contractual windows. |

**"Zero observed v1 requests" is not "zero v1 consumers."** A client might be installed yet execute only on rare business events, or fail due to network errors during the observation window. Before EOL, align your **observation window with business frequency** and resolve unidentified consumers.

### 11.1. Example Owner Tracking Table

| Consumer | Owner | Active Interface | v2 Test | v2 Deployed | Recent v1 Usage | Verdict |
| --- | --- | --- | --- | --- | --- | --- |
| Billing Service | Billing team | v2 in staging, v1 in prod | PASS | Not yet | Yes | **BLOCKER** |
| Analytics batch | Data team | v1 | None yet | Not yet | None in 7 days | **BLOCKER**: batch runs monthly. |
| Checkout Service | Checkout team | v2 | PASS | Yes | None | Likely ready after full observation window. |
| External partner X | Partner engineering | Unclear | No info | Unconfirmed | Sporadic | **BLOCKER**: needs permission/version confirmation. |

This is **illustrative data**, not the state of real services. An "Unknown" entry must never auto-flip to "Done" simply because it didn't show up in a log query.

## 12. Consumer Migration Checks More Than a New DTO

When Billing switches to `/api/v2/orders/{id}`, work typically covers:

1. **URL/headers/media type**: send requests to the v2 interface properly.
2. **DTO/schema**: read `orderId`, `state`, `amount.minor`, `amount.currency`.
3. **Business meaning**: which currency unit is used; do states keep v1 meanings?
4. **Error responses**: handle 400/401/403/404/409/5xx per v2 conventions.
5. **Auth/permissions**: have token audiences/scopes or policies changed?
6. **Timeouts/retries/rate limits**: did SLAs, idempotency, or retry rules change?
7. **Telemetry**: tag whether the consumer calls v1 or v2 without logging secrets/PII.
8. **Deployment**: roll out to prod, regions, tenants, and related batches/workers.
9. **Fallback**: if v2 misbehaves, can you revert cleanly without corrupting data?

A consumer that changes only the URL while keeping a v1 DTO may receive v2's **200 OK** yet fail to read fields, or silently fall back to `null`/`0`. **Contract tests must assert core content and semantics**, not just status 200.

### 12.1. Consumer Test with v2 Stub Runner

An illustrative JUnit 5 example:

~~~java
import java.net.URL;
import java.util.Objects;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.contract.stubrunner.StubFinder;
import org.springframework.cloud.contract.stubrunner.spring.AutoConfigureStubRunner;
import org.springframework.cloud.contract.stubrunner.spring.StubRunnerProperties;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
@AutoConfigureStubRunner(
    ids = "com.acme:order-service:2.0.0:stubs",
    stubsMode = StubRunnerProperties.StubsMode.LOCAL
)
class BillingUsesOrderV2Test {
    @Autowired
    private StubFinder stubFinder;

    @Test
    void readsNewOrderSchema() {
        URL baseUrl = Objects.requireNonNull(
            stubFinder.findStubUrl("com.acme", "order-service")
        );

        OrderV2Client client = new OrderV2Client(
            baseUrl.toExternalForm()
        );
        OrderV2Client.OrderDto order = client.getOrder(42L);

        assertThat(order.orderId()).isEqualTo("ORD-42");
        assertThat(order.state()).isEqualTo("PAID");
        assertThat(order.amount().minor()).isEqualTo(125000L);
        assertThat(order.amount().currency()).isEqualTo("VND");
    }
}
~~~

This example assumes `OrderV2Client` is Billing's real class, with matching `OrderDto` and `Amount` records; source classes and dependencies are supplied by the consumer. With `LOCAL`, `2.0.0:stubs` must exist in Maven local. In multi-machine CI, use `REMOTE` with appropriate repository/credentials.

**What this test proves:** Billing code can call and decode the **HTTP v2 sample in the artifact**. **What it does not prove:** that Billing deployed that version in production or that producer release 2.0.0 still serves v1 accurately while v1 remains committed. Gather separate evidence for those.

## 13. Verifying Both Legacy and New Contracts in the Same Producer Release

An important case: Order Service release `2.0.0` still supports **both v1 and v2**. After producer verification, artifact:

~~~text
com.acme:order-service:2.0.0:stubs
~~~

should contain **mappings/contracts for both still-supported interfaces**, provided the plugin scans both. Old consumers can run v1 tests against the **new producer release's stub artifact**, while new consumers run v2 tests against the same release.

Matrix goal:

| Producer Release | V1 Contract | V2 Contract | Why |
| --- | --- | --- | --- |
| `order-service 1.0.0` | PASS | Not yet present | Historical baseline. |
| `order-service 2.0.0` during migration | **PASS** | **PASS** | Preserves old consumers while enabling new ones. |
| `order-service 2.1.0` still committed to v1 | **PASS** | **PASS** | Producer upgrades must not break legacy. |
| Approved retirement release | v1 no longer committed | PASS | Only after EOL gates pass and notice takes effect. |

**Do not test consumer v1 solely against old `1.0.0-stubs.jar`** when production producer has moved to `2.1.0`: that verifies only the **past** contract, not whether the current release still produces valid v1 responses. Test against **the actual producer release's stubs**, or better yet, **generated producer tests inside that exact release**.

## 14. Deprecation Does Not Mean "Producer Can Prettify the Old Response"

Commonly misjudged changes:

| Change to v1 | Can It Break Old Consumers? | Right Approach |
| --- | --- | --- |
| Rename `totalMinor` to `amountMinor` in v1 response | **Yes** | Keep old field or add separate v2. |
| Change number `125000` to string `"125000"` | **Yes** | Protect JSON number type and contract. |
| Drop `status` because new DTO uses `state` | **Yes** | Never drop v1 fields during support window. |
| Change 404 error body/code | **Yes** | Preserve legacy error rules or version it. |
| Add optional field when consumer uses strict parser | **Possibly** | Test old consumers and unknown-field policy. |
| Optimize repository/service without changing HTTP | Usually **no** | Contract tests must still PASS. |
| Reorder JSON object keys | Usually **no**, unless canonical order required | Use semantic JSON assertions, not key-order checks. |
| Reorder JSON array elements with committed sort order | **Yes** | Preserve ordering or version semantics. |
| Tighten auth policy rejecting old tokens | **Possibly** | Coordinate security transition, test 401/403. |
| Replace business 404 with WireMock unmatched 404 | Tests may **falsely pass** | Contract error body explicitly and assert request mapping. |

**Compatibility is more than parseable schemas.** If v1 still returns `totalMinor=125000` yet switches its meaning from minor units to major units, JSON stays valid while Billing miscalculates money. Contracts and tests must protect **essential business semantics**.

## 15. Messaging Deprecation Is Harder Than HTTP

In event-driven architectures, Order Service may emit `OrderCreated` under v1 and v2 schemas. Two milestones must be distinguished:

- **Stop publishing v1 events:** producer stops emitting new messages in v1 schema.
- **Stop supporting reading v1 events:** consumers/deserializers can no longer read **stored or replayable v1 messages**.

These two points **can be separated by a wide gap** due to Kafka retention, queue backlogs, dead-letter queues, outboxes, audit logs, or long-term event archives.

Example v1 message:

~~~json
{
  "eventId": "evt-001",
  "orderId": "ORD-42",
  "amountMinor": 125000
}
~~~

V2:

~~~json
{
  "eventId": "evt-001",
  "orderId": "ORD-42",
  "amount": {
    "minor": 125000,
    "currency": "VND"
  }
}
~~~

You can use `schemaVersion`, a new event type, a new topic, or a Schema Registry depending on agreed protocols. **No single messaging versioning mechanism is mandatory**; what matters is that consumers can distinguish payloads and have a compatibility/migration strategy.

### 15.1. Groovy Output Message Contract for v1

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    label 'orderCreatedV1'
    description 'v1 event still emitted during migration phase'

    input {
        triggeredBy('publishOrderCreatedV1()')
    }

    outputMessage {
        sentTo('orders.created.v1')
        headers {
            header('contentType', 'application/json')
            header('schemaVersion', 1)
        }
        body(
            eventId: 'evt-001',
            orderId: 'ORD-42',
            amountMinor: 125000
        )
    }
}
~~~

### 15.2. Groovy Output Message Contract for v2

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    label 'orderCreatedV2'
    description 'v2 event with amount including currency'

    input {
        triggeredBy('publishOrderCreatedV2()')
    }

    outputMessage {
        sentTo('orders.created.v2')
        headers {
            header('contentType', 'application/json')
            header('schemaVersion', 2)
        }
        body(
            eventId: 'evt-001',
            orderId: 'ORD-42',
            amount: [
                minor: 125000,
                currency: 'VND'
            ]
        )
    }
}
~~~

Both contracts illustrate **two separate destinations** for clarity. In practice, versions may be distinguished on the **same topic** via headers/Schema Registry; adapt `sentTo`/headers and consumer logic accordingly. `triggeredBy` invokes producer verification; to run generated tests, base tests and messaging adapters must match your plugin version.

**Stub Runner can trigger labels to emit sample messages**, yet it does not prove transactional outboxes, broker ordering, redelivery, retention, or replayability. To declare EOL for v1 events, verify **producer publishing**, **consumer decoding**, and **stored data across brokers/archives**.

## 16. Specific EOL Criteria for Old Message Schemas

Beyond G1–G8 in section 10, messaging contracts typically require:

| Messaging Gate | Mandatory Question |
| --- | --- |
| **Publisher readiness** | Has the producer stopped emitting v1 cleanly, and is v2 verified and accepted by consumers? |
| **Dual publish policy** | If emitting both v1/v2 temporarily, can consumers process duplicates? Are event IDs/idempotency in place? |
| **Consumer subscription** | Have all necessary consumers switched topics/destinations or decoded the new schema? |
| **Message backlog** | Are unconsumed v1 messages still sitting in queues/partitions? |
| **DLQ / retry** | Do dead-letter and retry topics hold v1 messages that may be replayed? |
| **Replay / audit** | Is historical v1 recovery required from long-term event stores/archives? |
| **Schema registry** | Do compatibility policies, schema IDs/defaults/field presence allow new consumers to read old data? |
| **Observability** | Are metrics segmented by `schemaVersion`/`eventType` and owner, not just total message count? |

One strategy is to **stop publishing v1** while retaining the **v1 consumer reader** long-term for replays. **Never delete old schemas/decoders** the instant the producer switches to v2 if old data can still be legitimately replayed per product requirements.

**Schema backward/forward compatibility** (especially Avro/Protobuf) must be checked against your registry/serializer definitions and read direction. A "valid" new schema does not automatically ensure old consumers can read it, nor does a new consumer "reading v2" guarantee it can replay v1.

## 17. Deciding Between 404, 410, or Disabled Routes After Retirement

Once v1 EOL is approved, the producer can:

- **Remove the route** `/api/v1/orders/{id}` so requests are not found (usually 404 under typical routing).
- **Return `410 Gone`** by design to signal the resource is permanently retired if infrastructure supports that convention.
- **Keep a gateway compatibility adapter** or controlled redirect if contracts/consumers permit.
- **Keep v1 in read-only mode** during an exception period if policy allows.

**There is no rule that deprecation must always return 410.** Throughout the support window, v1 must keep honoring the old contract; switching 200 to 410 mid-migration window is a **breaking change** for committed consumers.

Post-retirement, if you design an explicit 410 response, write **tests for that designed retirement behavior**, avoiding mistaking an **unmatched WireMock 404** for an official 404/410 contract.

### 17.1. Controlled Rollout Beats Immediate Code Deletion

A safe retirement process usually separates:

1. Final cutoff notice and confirmation of EOL gates.
2. Throttling or disabling v1 on a small cohort/controlled route where infrastructure allows.
3. Monitoring 4xx/5xx, customer incidents, and unidentified traffic.
4. Keeping a **rollback route/feature flag** or recovery plan per SLA.
5. Only after stability is confirmed, cleaning up active implementations/contracts and updating docs.
6. Archiving change evidence, approval records, and historical artifacts.

Do not turn an arbitrary sunset date into an automated code-deletion trigger lacking release controls and migration proof.

## 18. CI Pipeline Protecting v1 During Deprecation

During concurrent support, the producer pipeline must test **both v1 and v2**:

~~~mermaid
flowchart TD
    A["Producer PR modifies Order API"] --> B["Contract Verifier generates tests from v1 + v2"]
    B --> C["Run generated producer tests"]
    C --> D{"All still-supported contracts PASS?"}
    D -->|No| E["Block publish/deploy; investigate regression"]
    D -->|Yes| F["Package current release stubs containing v1 + v2"]
    F --> G["Publish versioned artifact"]
    G --> H["Consumer CI: legacy client + new client"]
    H --> I["Verify deployment + usage + migration gates"]
    I --> J{"Is v1 EOL approved?"}
    J -->|No| K["Continue protecting v1 on producer"]
    J -->|Yes| L["Roll out retirement and monitor/rollback"]
~~~

Concrete controls:

1. **Contract Verifier** loads v1/v2 files, generates, and runs tests on the **current producer implementation**.
2. **Test reports** show at least the key cases of **both versions** executed, not just total test count > 0.
3. **Consumer Stub Runner tests** run for supported consumer versions, pinning matching artifact versions.
4. **Compatibility checks** cover more than a happy path: error schemas, auth, pagination, and committed business semantics.
5. **EOL inventory** lives outside tests as structured data: owners, deployments, usage, exceptions, and approvals.
6. **Pull requests deleting v1** must link to an approved EOL decision, not merely say "deprecated."
7. **Release pipeline** blocks publishing if producer tests fail, stub artifacts mismatch, or retirement lacks approval.
8. **Post-deploy monitoring** tracks versions and errors with clear rollback triggers.

Any change causing `/api/v1/orders/42` to return a v2 body during migration must **FAIL producer verification**. Any change breaking v2 while v1 stays intact must also **FAIL** once v2 is a supported contract.

## 19. End-of-Support Decision Table: Practical Example

Suppose the change board reviews retiring `GET /api/v1/orders/{id}`:

| Gate | Required Evidence | Sample Result | Decision |
| --- | --- | --- | --- |
| Communicated | Changelog + list of notified owners | PASS | Proceed evaluating. |
| V2 meets use cases | Producer/consumer tests + auth/error reviews | PASS | Proceed evaluating. |
| Billing deployed v2 | Production release record | PASS | Proceed evaluating. |
| Analytics batch migrated | CI passes yet monthly batch not deployed | **FAIL** | **Do not EOL v1**. |
| External clients | One partner unresponsive | **UNKNOWN** | **Do not EOL**, verify/exception needed. |
| v1 traffic | Zero in 7 days yet monthly job exists | **INSUFFICIENT** | Extend observation. |
| Rollback | Route toggle exists yet unrehearsed | **PENDING** | Complete before cutoff. |
| Final decision | Insufficient evidence | **NOT APPROVED** | Retain v1 contract and v1 tests. |

In this hypothetical table, **v1 must not be deleted** despite a target date. A critical **FAIL** or **UNKNOWN** criterion must trigger extending support, remediation, or an **explicitly approved exception**—never silent bypass.

### 19.1. Checklist Attachable to a Retirement PR

~~~text
[ ] v1 contract, endpoint/event scope, and owners documented
[ ] Deprecation announcement and migration guide published
[ ] V2 producer verification and consumer tests passed
[ ] Complete list of consumers and partners audited
[ ] Critical consumers deployed versions free of v1
[ ] v1 usage monitored across business/retention cycles
[ ] Batch/offline/replay/DLQ evaluated if applicable
[ ] Exceptions and extensions resolved
[ ] Rollback/fallback prepared and rehearsed where suitable
[ ] SRE, API owner, and change authority approved
[ ] Plan exists to update docs, SDKs, stubs, and monitoring
[ ] Post-deployment evidence/results confirm EOL
~~~

This checklist is a **decision-making tool**, not an automated test suite. Checkboxes may be ticked only with **matching evidence and accountable owners**.

## 20. Managing Historical Artifacts and Data Post-EOL

Another misconception: deleting the v1 endpoint requires immediately deleting every old stub JAR. That causes trouble when:

- Reproducing an incident in an old Billing build.
- Auditing why a consumer behaved a certain way pre-migration.
- A maintenance branch is authorized to use an older version for a set window.
- Identifying which mapping/contract was published at a historical point in time.

**Artifact retention policy** differs from **API support policy**:

| Item | What to Do Post-EOL? |
| --- | --- |
| v1 route/handler code on new producer | Can be deleted after approval, rollout, and stabilization. |
| v1 generated producer tests on new dev branch | Drop only when new releases **no longer commit to v1** and EOL passed. |
| Old-version stub artifacts | Can be **retained read-only** per retention/audit policy. |
| Migration docs and changelogs | Retain historical milestones, clearly marking v1 retired. |
| Old SDKs/clients | Mark unsupported; clearly communicate end of updates. |
| v1-specific metrics/alerts | Retain for a post-rollout window, then clean up as planned. |
| Stored v1 messages | Continue supporting decoding/replay while retention/audit rules require it. |

**Never treat "the artifact is still downloadable" as a sign API v1 is supported.** A historical stub JAR can remain for debugging even when production producers no longer serve that endpoint. Conversely, a producer still hosting a v1 route does not mean v1 is supported if SLAs/security policies have ended; documentation must stay consistent.

## 21. Common Mistakes and How to Fix Them

| Mistake | Risk | Fix |
| --- | --- | --- |
| "It's deprecated, so delete v1 contract tests." | Producer v1 silently breaks before EOL. | Keep v1 generated tests until approved end-of-support. |
| "V2 exists, so everyone moved." | Billing/partners/batches still call v1. | Maintain consumer inventory and verify deployments/usage. |
| "Zero v1 traffic for 24 hours is enough." | Misses periodic batches and offline clients. | Observe full business cycles and confirm with owners. |
| Run v1 consumer tests only against old 1.0.0 stub. | Fails to check whether new producer releases still serve v1 properly. | Keep v1 in current producer generated tests and current release stubs. |
| Check only v2 status 200. | Wrong DTO/error/semantics slip through. | Assert schemas, data types, errors, and business meaning. |
| Change old header/path and call it a "refactor." | Old consumer requests stop matching. | Preserve old interface; add separate v2 for breaking changes. |
| Assume HTTP `Sunset` turns off the API. | No rollout/rollback; consumers remain un-updated. | Treat it as a policy signal; EOL needs dedicated gates. |
| Switch v1 responses to 410 immediately at announcement. | Old consumers break instantly. | Maintain v1 throughout the committed migration window. |
| Delete v1 event decoder the moment producer stops publishing. | Replays/queues/DLQs containing v1 become unprocessable. | Account for retention and historical data. |
| Dual publish v1/v2 without idempotency. | Consumers receive two events for one action and double-process. | Define event identity, deduplication, and migration tests. |
| Equate release artifact version with API version. | Stub 2.0 tests only v2, leaving still-supported v1 unprotected. | Manage the two version axes separately. |
| Change error response yet tests stay green. | Contracts lack negative cases or use overly broad matchers. | Add error contracts and consumer handling tests. |
| Delete v1 route in PR without linking EOL decision. | Unclear accountability and missing evidence. | Require approvals, checklist, and rollback plan. |
| Delete all old stubs immediately at EOL. | Cannot reproduce historical incidents. | Retain artifacts per retention policy, separate from support commitments. |
| Green v2 Stub Runner tests mean v2 is deployed. | Source code passes while old binary runs in prod. | Check deployment records, runtime telemetry, and owner sign-off. |

**When troubleshooting migration failures, trace the chain:** v1/v2 contracts → generated producer tests → release artifacts → consumer Stub Runner tests → deployment/runtime usage → EOL decision. Fix at the right layer; never edit contracts to mask deployment errors.

## 22. Practice: Deprecating v1 Without Breaking Billing

Execute on Order Service (producer) and Billing Service (consumer) with two APIs `/api/v1/orders/42` and `/api/v2/orders/42`.

1. **Create v1 contract** in Groovy/YAML DSL returning `id`, `status`, `totalMinor`. Build v1 controller and generated producer tests.
2. **Run v1 producer verification**, confirming tests genuinely generate and execute. Intentionally change `totalMinor` to `amountMinor` to prove the test FAILS, then revert.
3. **Add v2 API and contract** returning `orderId`, `state`, and `amount.{minor,currency}`. Keep v1 untouched in the new release.
4. **Run Contract Verifier on the producer supporting both v1/v2**, checking both suites PASS, not just total test count.
5. **Package and publish `stubs` of the new release** containing all still-supported contracts; inspect actual JAR contents.
6. **Write `BillingV1Client`** and `BillingV2Client` (or versioned adapters), running each through Stub Runner against the chosen artifact. Verify paths, JSON schemas, and error handling.
7. **Build a hypothetical consumer inventory** including Billing, Analytics batch, Checkout, and external partner; record owners, prod deployments, last seen v1, and risk levels.
8. **Draft a sample deprecation notice** stating date, old API, replacement, migration guide, in-window support, and a **hypothetical** conditional sunset date.
9. **Simulate un-migrated Analytics:** even though v2 tests PASS, mark gates G4/G5 FAIL and conclude **v1 must not be removed**.
10. **Simulate complete evidence:** all owners confirm, v2 deployments finish, full job cycles observed, rollback rehearsed, and EOL approval active.
11. **Perform retirement on a test branch** using a controlled route toggle/removal; verify designed retirement behavior (404/410 if policy dictates), monitor post-deploy, and roll back if needed.
12. **Add a messaging scenario:** emit `OrderCreated` schema v1/v2; simulate DLQ/replay retaining v1 data to explain why old decoders often outlive v1 publishers.
13. **Wire CI:** during the migration window, every producer PR must PASS v1/v2 tests; only after approved EOL are v1 tests removed in a future release while historical artifacts stay retained.

**Completion Criteria:** learners can explain **why deprecation is not retirement**, write v1/v2 contracts running in parallel, prove the producer does not break v1 pre-EOL, distinguish API version from artifact version, build **evidence-backed EOL criteria**, and explain rollback/retention conditions after closing old contracts.

## 23. Self-Check Questions

1. What is the difference between active, deprecated, sunset scheduled, and retired?
2. Why can't you drop v1 generated producer tests as soon as v2 is announced?
3. Why might `order-service:2.0.0:stubs` need to contain both v1 and v2 mappings?
4. Why does keeping `1.0.0` stub JAR in the Maven repository not prove producer 2.0.0 serves v1 properly?
5. How can changing `totalMinor` → `amount.minor` on the same v1 endpoint break consumers?
6. Does `@Deprecated` on a Java method automatically notify HTTP consumers of deprecation?
7. Does the `Sunset` header automatically disable an endpoint after the announced date?
8. Why are 90 days or 7 days of zero observed traffic insufficient to declare EOL?
9. Which data sources are needed to build a consumer inventory and identify un-migrated callers?
10. Stub Runner consumer tests pass yet production still runs v1 clients: is EOL ready?
11. What are the eight fundamental gates before ending support for an old contract?
12. If a consumer has an unknown owner or an unconfirmed partner, what status should be recorded and what decision follows?
13. Post-EOL, is the producer required to return `410 Gone`?
14. Why retain a rollback plan even with complete migration reports?
15. In messaging, why might you stop publishing v1 events while keeping v1 decoders?
16. How can dual publishing v1/v2 cause duplicate-processing bugs?
17. Does serializer backward/forward compatibility replace checking business semantics?
18. Should historical stub artifacts be kept or deleted post-EOL, and why?
19. If v2 contract tests pass while v1 contract tests fail during the migration window, what should the producer pipeline do?
20. What evidence proves consumer v2 is **deployed**, rather than merely built/tested successfully?

## 24. EOL Decision Template for Development Teams

Use this concise framework when opening an end-of-support ticket/ADR for a contract:

| Field | Information to Provide |
| --- | --- |
| **Contract name** | Method/path/API version or event type/schema version/destination. |
| **Producer and owner** | Service name, owning team, approver. |
| **Replacement version** | New path/schema, contract link, and migration guide. |
| **Announcement date** | Specific date, timezone, and communication channel. |
| **Planned sunset** | Policy-aligned milestone, subject to extension criteria. |
| **Consumer list** | Owners, deployments, criticality, migration status, exceptions. |
| **Migration evidence** | Consumer tests, release/deployment records, metrics, batch/offline confirmations. |
| **Compatibility evidence** | v1/v2 producer contract tests and CI reports. |
| **Messaging risks** | Retention, replay, DLQ, Schema Registry, if applicable. |
| **Rollback and monitoring** | Toggle/route/rollback procedure, on-call owner, success/failure signals. |
| **Final decision** | GO/NO-GO, approver, approval date, evidence links. |
| **Post-retirement cleanup** | Date to clean code/docs/SDKs/metrics; historical artifact retention policy. |

**Conclusion:** **A deprecated contract must still be verified and served accurately for as long as the producer commits to supporting it.** Spring Cloud Contract helps protect v1 and v2 behavior through Groovy/YAML DSL, generated producer tests, and Stub Runner consumer tests; yet **an EOL decision requires additional operational evidence**, including consumer owners, actual deployments, usage across business cycles, stored messaging data, policy, and rollback readiness. Only after passing EOL gates should legacy commitments end and old interfaces be removed in a new release; historical artifacts are governed under a separate retention policy. That way, new versions can evolve without inadvertently breaking consumers still under support.
