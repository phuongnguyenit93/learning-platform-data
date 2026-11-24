# Building a Risk Matrix for a Resource Creation Flow

## Goal: Risk-Based Testing of a Resource Creation Flow

A resource creation flow in a Spring application typically passes through multiple layers: HTTP controller, validation, authorization, business service, database, external service, message broker, and an asynchronous processing worker. A request may return success while the resource has not been fully created; conversely, an external resource may already have been created even though the database transaction failed.

If you only write a test for the successful creation case, many critical bugs can still slip through: two concurrent requests creating duplicate resources, a user creating resources beyond their quota, a provider timing out after already creating the resource, a lost event, a message processed twice, or one test's data being deleted by another test.

A risk matrix helps the testing team answer three questions:

1. What can go wrong at each step of the flow?
2. If it happens, how severe are the consequences for data, security, or users?
3. Which tests and controls provide evidence that the risk has been addressed?

The matrix does not replace test cases. It is a way to connect business requirements, failure modes, priorities, and testing strategy into a reviewable plan.

## Choosing a Sample Flow as a Baseline

To illustrate, suppose the system provides an API to create a Workspace. A Workspace is a resource belonging to a user or organization; after saving metadata, the system needs to create a storage area on an external provider. Provisioning can take time, so it is handled asynchronously.

Sample request:

~~~http
POST /api/workspaces
Authorization: Bearer <access-token>
Idempotency-Key: 9a4f...
Content-Type: application/json

{
  "name": "finance-reports",
  "region": "ap-southeast-1",
  "plan": "STANDARD"
}
~~~

A typical flow:

~~~text
HTTP request
    |
    v
Authentication and authorization
    |
    v
Validate payload, region, plan, and quota
    |
    v
Check idempotency key and unique name
    |
    v
Create Workspace in PENDING state
    |
    v
Write outbox event in the same transaction
    |
    v
Return HTTP 202 + resource id
    |
    v
Outbox publisher / message broker
    |
    v
Provisioning worker calls external provider
    |
    +------ success ------> update to READY
    |
    +------ failure ------> retry or FAILED
~~~

This example assumes the API returns 202 Accepted when it has accepted the resource creation request but provisioning is not yet complete. If the application creates the resource synchronously and returns 201 Created, you can keep the same matrix approach while adjusting intermediate states, verification points, and HTTP expectations accordingly.

Responsibility boundaries should be clear:

- Controller handles HTTP protocol, request validation, and response.
- Service decides creation permissions, quota, uniqueness, idempotency, and business state transitions.
- Repository stores metadata and outbox records.
- Adapter communicates with the provider or broker.
- Worker coordinates provisioning, retries, and status updates.

Each layer does not necessarily need its own test class. Test boundaries should follow the behavior to be verified and the risk level, not the number of classes in the code.

## Defining a Risk Scoring Scale

A simple approach is to score each risk along two axes:

- **Probability (P):** the likelihood of the failure occurring under expected operating conditions or code changes.
- **Impact (I):** the severity of the consequences if the failure occurs.

Score each axis from 1 to 5:

| Score | Probability | Impact |
| --- | --- | --- |
| 1 | Rare, unlikely to occur | Minor impact, easy to recover |
| 2 | Low likelihood | Limited impact, workaround exists |
| 3 | Possible | Breaks part of the flow or requires intervention |
| 4 | Likely under certain conditions | Causes data loss, significant disruption, or affects many users |
| 5 | Frequent or common trigger conditions | Very severe: security breach, major data loss, or unacceptable side effects |

Basic risk score:

\[
R = P \times I
\]

Example priority thresholds for planning:

| Score R | Suggested Priority | Handling Approach |
| --- | --- | --- |
| 15–25 | Critical | Requires controls and test evidence before release |
| 8–14 | High | Requires explicit tests; consider making them mandatory in CI |
| 4–7 | Medium | Test according to change scope and exposure |
| 1–3 | Low | Can be checked at an appropriate level or monitored |

This is an illustrative scale, not a universal standard for every organization. Teams should calibrate it based on risk tolerance, data sensitivity, system scale, and compliance requirements.

Detectability or difficulty of detection can also be recorded to support discussion. However, do not multiply by an extra D score and call the result RPN unless the team has defined a consistent scale and usage rules. This table uses P × I to keep prioritization simple and easy to explain.

## Risk Matrix for the Workspace Creation Flow

The table below is a sample risk register. The scores assume a resource creation API with quota, database, external provider, and asynchronous processing. When applying this to a real system, adjust P/I based on actual incidents, traffic, architecture, and data.

| ID | Failure mode / risk | P | I | R | Test evidence and controls |
| --- | --- | ---: | ---: | ---: | --- |
| R01 | Invalid or missing payload fields still create a resource | 3 | 3 | 9 | MVC test for invalid body, validation error, and service not called |
| R02 | User without permission creates a Workspace for another tenant | 3 | 5 | 15 | Security integration test for 401/403; verify tenant/owner is taken from authenticated principal |
| R03 | Resource created beyond quota or using invalid plan | 3 | 4 | 12 | Unit/service test for quota boundaries; repository integration test for existing resource count |
| R04 | Two requests with the same name unintentionally create two Workspaces | 4 | 4 | 16 | Unique constraint in DB; integration test sending competing requests and verifying only one valid resource |
| R05 | Retrying the same request creates multiple resources due to missing idempotency | 4 | 5 | 20 | Test repeating the same Idempotency-Key; verify same resource id and no duplicate side effects |
| R06 | Database saves Workspace but outbox event is not written | 3 | 5 | 15 | Transaction integration test verifying metadata and outbox commit or roll back together |
| R07 | Provider creates resource but response times out, causing app to record failure | 3 | 5 | 15 | Adapter contract test for timeout/ambiguous result; worker retry must be idempotent or reconcile by provider key |
| R08 | Provider rejects or has transient error, leaving Workspace stuck in PENDING forever | 3 | 4 | 12 | Worker test for retry/backoff, retry limit, and transition to FAILED or intervention-needed state |
| R09 | Message delivered at least once and worker processes duplicate | 4 | 4 | 16 | Duplicate delivery test; verify idempotent processing by event/resource id |
| R10 | Worker updates to READY before provider confirms resource is usable | 2 | 5 | 10 | State transition test; transition to READY only after success signal or appropriate readiness probe |
| R11 | Parallel tests share names, keys, or queues, causing data pollution | 4 | 3 | 12 | Separate namespace per suite/test; run in parallel and verify scoped cleanup |
| R12 | Cleanup accidentally deletes resources outside suite or leaves billable resources behind | 3 | 4 | 12 | Namespace-based cleanup test; verify other suites' prefixes/schemas/resources are not deleted |
| R13 | Slow request or provider causes random test timeouts | 4 | 3 | 12 | Wait with deadline, well-founded test timeouts; do not use fixed sleep |
| R14 | Provider error leaks credentials or sensitive payload in logs | 2 | 5 | 10 | Test/log assertion for sensitive data; configure redaction and do not log secrets |

Under the assumptions above, R05, R04, R09, and R02 are the highest-priority risks. That does not mean ignoring lower-scoring risks: a bug with very high impact still needs attention even if its probability is low.

## Turning Risks into Executable Test Cases

Each row in the risk register should map to one or more test cases. A test case must specify initial conditions, action, and observable evidence. A phrase like "tested Workspace creation" is too vague to prove that a specific risk is controlled.

Mapping examples:

| ID | Condition | Action | Key Assertion |
| --- | --- | --- | --- |
| R01 | Payload missing name | POST request | 400; validation error; service not called |
| R02 | Principal belongs to tenant A | Create resource for tenant B | 403; no DB write; no event published |
| R04 | Workspace with same tenant/name already exists | Send creation request again | Contract conflict; only one row exists |
| R05 | Idempotency key K already created a resource | Resend same request and K | Same resource id; provider receives only one logical operation |
| R06 | Transaction is creating metadata | Trigger failure when writing outbox | No standalone committed metadata exists |
| R07 | Provider created resource but client timed out | Worker retries with same provider operation key | No second provider resource created; state reconciled |
| R09 | Same event delivered twice | Process duplicate event | One logical resource; no duplicate side effects |
| R12 | Resources exist for suites A and B | Clean up suite A | A is deleted; B remains intact |

One risk may require tests at multiple layers. For example, R05 needs a unit test for the idempotency rule, a database integration test for the unique constraint, and a worker/adapter test for provider side effects. Do not force a single end-to-end test to prove all of these details.

## Test Layering in Spring

### Unit Tests for Business Rules

Unit tests are suitable for pure logic such as:

- Calculating remaining quota.
- Checking whether a plan allows the requested region.
- Determining valid states in the state machine.
- Generating or validating an idempotency fingerprint.
- Deciding whether to retry or transition to FAILED.

Dependencies such as repositories, clocks, and provider clients can be replaced with fakes or mocks. Assertions should verify business decisions and critical interactions, not merely that a method was called.

Example quota check:

~~~java
@Test
void rejectsCreationWhenQuotaIsReached() {
    WorkspaceQuota quota = new WorkspaceQuota(3);

    assertThat(quota.canCreate(2)).isTrue();
    assertThat(quota.canCreate(3)).isFalse();
}
~~~

This example tests the pure rule. It does not prove that two concurrent requests cannot exceed the quota; that requires an integration test with the synchronization mechanism or constraint used by the system.

### MVC Slice for the HTTP Contract

@WebMvcTest is suitable for verifying:

- Method/path and content type.
- Bean validation on the request body.
- Status code, Location, or response DTO.
- Authentication/authorization in the web security chain if the slice configuration is loaded.
- Errors translated into error responses.

Example:

~~~java
@WebMvcTest(WorkspaceController.class)
class WorkspaceControllerTests {

    @Autowired
    MockMvc mockMvc;

    @MockitoBean
    WorkspaceService workspaceService;

    @Test
    void rejectsBlankWorkspaceName() throws Exception {
        mockMvc.perform(post("/api/workspaces")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {
                                  "name": " ",
                                  "region": "ap-southeast-1",
                                  "plan": "STANDARD"
                                }
                                """))
                .andExpect(status().isBadRequest());

        verifyNoInteractions(workspaceService);
    }
}
~~~

The @MockitoBean annotation is part of Spring Framework 6.2 and later. For projects using older Spring Boot/Spring Framework versions, use the compatible mock bean mechanism for the project, such as @MockBean in Spring Boot versions prior to migrating to the new API.

This test proves that an invalid payload is rejected before calling the service. It does not yet test quota, uniqueness, or database constraints.

### Service Integration Tests with a Real Database

Risks related to unique constraints, transactions, locking, and outbox need to be tested against the corresponding database engine. H2 or mock repositories may not fully reproduce the SQL behavior, isolation levels, and constraints of PostgreSQL/MySQL used in production.

Testcontainers can provide a database for tests:

~~~java
@Testcontainers
@SpringBootTest
class WorkspaceCreationDatabaseTests {

    @Container
    static final PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16");

    // DynamicPropertySource or ServiceConnection provides
    // URL, username, and password for the Spring datasource.
}
~~~

Once the context and migrations are ready, tests can verify:

- Unique constraint prevents two Workspaces with the same tenant/name.
- Outbox row is written in the same transaction as the Workspace.
- Transaction rollback leaves no partial metadata behind.
- Locks or optimistic versions handle concurrent updates properly.

With Testcontainers, wait for database readiness via the wait strategy and wait for migrations to complete before querying. A running container or open port does not prove the schema is ready.

### Adapter Tests for External Providers

You should not call the real cloud provider in every test. Adapters can be tested using a mock HTTP server or stub server to verify:

- URL, method, headers, and request body are correct.
- Authentication is sent properly while secrets do not appear in logs.
- Successful responses are decoded properly.
- 4xx, 5xx, timeouts, and invalid responses are mapped properly.
- Retries do not cause unintended duplicate side effects.

If using RestClient or RestTemplate, MockRestServiceServer is suitable for testing requests at the client boundary. With WebClient, use a mock web server or a corresponding HTTP test server to verify reactive request/response handling.

### Worker and Message Integration Tests

Workers should be tested for cases such as:

- Valid event creates the provider resource and updates the status.
- Duplicate event does not create additional resources.
- Transient provider errors are retried according to policy.
- Permanent errors transition the resource to FAILED or the prescribed business state.
- Messages are acked/nacked at the right time.
- Worker does not transition to READY when provisioning is incomplete.

If using a real broker in integration tests, create a dedicated queue/topic or consumer group for the suite. Use a namespace to prevent other tests from consuming this test's messages.

## The Risk Matrix Must Include Data and Side Effects

A resource creation flow does not merely write a single row in the database. There can be multiple side effects outside the transaction:

| Component | Side Effect | How to Isolate in Tests |
| --- | --- | --- |
| Database | Workspace, quota counter, outbox row | Separate schema/tenant or unique record id |
| Provider | Bucket, namespace, VM, external project | Fake provider or separate resource prefix in sandbox |
| Redis | Lock, cache, idempotency record | Separate key prefix per suite |
| Broker | Queue, topic, message | Separate queue/topic or consumer group |
| Filesystem/object storage | File, object, multipart upload | Separate directory/prefix |
| Scheduler/worker | Running task or retry | Controllable scheduler, correlation id, and completion signal |

A database rollback does not automatically undo side effects in Redis, the broker, the provider, or object storage. If a test calls real systems, namespace-based cleanup or an isolated sandbox is required.

For billable providers, prefer fakes/stubs for most tests. Only use sandbox integration tests with resource limits, timeouts, and explicit cleanup for risks that require verifying the real protocol.

## Treating Idempotency and Concurrency as Dedicated Risks

Two identical requests can arrive because a user clicks a button twice, a client retries after a timeout, or a broker redelivers a message. You cannot rely solely on identical request bodies to conclude they are the same operation; the system needs explicit idempotency rules.

A common design:

- Client sends an Idempotency-Key for a logical create operation.
- Server stores the key, owner/tenant, request fingerprint, and resource id.
- Repeated request with the same key and same payload returns the created result or current status.
- Same key with a different payload is rejected according to the contract.
- Unique constraint protects uniqueness in the database, even when two requests arrive concurrently.

Tests should cover:

1. Same key, same payload: only one logical resource.
2. Same key, different payload: returns conflict or the specified idempotency error.
3. Two different keys, same resource name: uniqueness rule is enforced.
4. Two concurrent requests with the same key: only one operation is created; the other request receives the appropriate result.
5. Client timeout after server commit: retry does not repeat the provider operation.

Concurrency tests should create real contention at the boundary under test, for example using two threads or two independent transactions on the test database. Calling two methods sequentially in a single test does not prove a race condition is handled.

## Transactions, Outbox, and Provisioning States

If the Workspace and outbox event must be written atomically, both should be in the same database transaction. Tests should verify:

- When writing the Workspace succeeds and writing the outbox succeeds, both commit together.
- If any step in the transaction fails, no Workspace is committed without an outbox event.
- Publisher only sends committed events.
- If the publisher sends a message and crashes before marking the outbox as processed, the message may be resent; the consumer must be idempotent.

Do not assume a database transaction covers an HTTP request to a provider. If the provider already created the resource and then the database rolls back, the system needs a reconciliation or compensation strategy. Tests must simulate timeout/ambiguous response cases and verify retries do not create additional resources.

A simple state machine might look like:

~~~text
PENDING
  | \
  |  \ permanent failure
  |   v
  |  FAILED
  |
  | provider confirms usable
  v
READY
~~~

Invalid state transitions must be rejected. For example, FAILED does not automatically transition to READY without an explicit retry/reconcile operation. Tests should cover both valid states and forbidden transitions.

## Prioritizing Tests by Risk Score

With the sample risk register, an execution plan can be divided into groups:

| Priority Group | Risks | Mandatory Tests to Have |
| --- | --- | --- |
| Critical | R02, R04, R05, R06, R07, R09 | Authorization, unique constraint, idempotency, transaction/outbox, provider ambiguity, duplicate delivery |
| High | R01, R03, R08, R11, R12, R13 | Validation, quota, retry/failure, namespace, cleanup, timeout |
| Conditional | R10, R14 | Readiness/state transition and log redaction when provider provisioning or sensitive data is involved |

Do not prioritize solely by total score. R02 has very high security impact; even if its probability is rated low, authorization tests are still necessary. Similarly, a bug that may be rare yet creates billable resources or leaks another tenant's data still deserves strong controls.

## Using the Matrix to Define Release Evidence

A risk register row is only useful when you can trace from the risk to the evidence:

| Field to Store | Content |
| --- | --- |
| Risk ID | Stable code such as R05 |
| Failure mode | What can go wrong |
| P / I / score | Basis for prioritization |
| Preventive control | Constraint, authorization rule, idempotency, timeout, or design control |
| Test case | Specific test name or test path |
| Expected evidence | Status, row count, event count, provider request count, state transition |
| Owner | Person responsible for the control |
| Residual risk | Remaining risk after controls |
| Status | Untested, in progress, passing, or risk acceptance needed |

Example with R05:

~~~text
Risk ID: R05
Failure mode: Retrying the same request creates multiple Workspaces
Control: Idempotency-Key + unique constraint + provider operation key
Test: sameKey_samePayload_returnsSameResource
Evidence:
  - same resource id in both responses
  - one Workspace row
  - one logical outbox operation
  - one provider resource
Residual risk: if provider does not support idempotency, reconcile by external reference is needed
~~~

The test name in the example is a suggested name; link to the actual test in the repository when applying. If no test exists yet, explicitly record the gap instead of marking the risk as handled just because a descriptive document exists.

## Definition of Done for a Resource Creation Flow

A test suite for this flow should provide evidence at the following boundaries:

1. **HTTP contract:** invalid requests are rejected; valid requests return the right status, headers, and body.
2. **Security:** only authorized principals/tenants can create resources.
3. **Business rules:** quota, uniqueness, plan, and region are properly enforced.
4. **Persistence:** transactions, constraints, and outbox keep data consistent.
5. **Idempotency/concurrency:** retries and concurrent requests do not create duplicate logical resources or side effects.
6. **External integration:** requests to the provider are correct; errors, timeouts, and ambiguous responses are handled.
7. **Async processing:** duplicate delivery, retries, readiness, and state transitions work properly.
8. **Isolation/cleanup:** parallel tests do not pollute data; test resources are cleaned up within scope.
9. **Observability:** logs and error responses do not leak secrets; correlation id enables tracing an operation.

Not every item requires an end-to-end test. Use unit tests for pure rules, slice tests for HTTP, database integration tests for constraints/transactions, adapter tests for external protocols, and a small number of end-to-end tests for cross-system paths.

## Process for Building a Risk Matrix

1. Diagram the resource creation flow from request until the resource reaches its final state.
2. Break the flow into steps and identify data, permissions, transactions, dependencies, and side effects at each step.
3. Write specific failure modes for each step; avoid generic descriptions like "service may fail".
4. Score Probability and Impact on a consistent scale; document assumptions and priority thresholds.
5. Select preventive controls and test evidence for each prioritized risk.
6. Map each test to the appropriate Spring layer: unit, MVC slice, database integration, adapter, worker, or end-to-end.
7. Add test data controls: namespaces, idempotency keys, cleanup, and side-effect limits.
8. Run tests in CI in priority order and record any remaining gaps or residual risks.
9. Update the matrix when the flow changes, a new incident occurs, or an external dependency changes its contract.

A good risk matrix does more than list what can break. It shows why a failure mode matters, which test proves the behavior is protected, and what risk still remains. For a resource creation flow, pay special attention to data ownership, idempotency, transaction/outbox, external providers, asynchronous processing, and cleanup; these are the points where a single happy-path test is unlikely to catch issues.
