# Procedure for Reading Contracts, Generated Tests, Mappings, and Actual Requests

## 1. Why Inspect All Four Layers Instead of Just the Failing Test Line?

In **Spring Cloud Contract (SCC)**, producer and consumer describe HTTP or message communication using **Groovy/YAML DSL**. From contracts, Contract Verifier generates **producer verification tests** to test the real provider implementation, and also generates **stub mappings** that can be packaged into a JAR and served via **Stub Runner/WireMock**. Consumers use stubs to verify clients or handlers before services are deployed together.

When a test fails, the root cause can lie in any link:

- The contract specifies the wrong method, URL, body, matcher, or response status.
- The contract is right, yet generated tests use a base class/test mode that does not reach the real producer.
- Generated tests are stale or never executed.
- The generated mapping does not reflect the constraints the author thought were in the DSL.
- An old stubs JAR was loaded by Stub Runner from a `LOCAL`/`REMOTE` repository.
- The consumer client sends a different request than the developer assumed.
- WireMock has another mapping with higher priority, or a fallback masks an unmatched request.
- The response came from a different server/port, not the instance holding candidate stubs.
- The consumer mishandles the response due to deserializer, error mapping, or business logic bugs.

Therefore, asking “**Is the contract wrong or the code wrong?**” is rarely enough. You need a **procedure reading from the agreed source down to the actual bytes/request**.

This lesson belongs to the **Troubleshooting** chapter and walks step-by-step through inspecting the four core layers:

~~~text
[1] Contract DSL
      ↓ generation
[2] Generated producer test
      ↓ assertion against real producer implementation
[3] Generated WireMock mapping + stubs artifact
      ↓ resolution / Stub Runner
[4] Actual consumer request and received response
~~~

During diagnosis, **never assume these four layers come from the same revision**. Prove their linkage via file paths, commits, versions, and artifact digests.

### Learning Objectives

After this lesson, you will be able to:

1. Read a Groovy/YAML contract to pinpoint the exact **accepted request** and **promised response**.
2. Read generated producer tests to see **which assertions actually execute**.
3. Open generated WireMock mappings and stubs JARs to confirm method/path/headers/`bodyPatterns`, response, and priority.
4. Capture the consumer's **actual raw request** instead of guessing from code.
5. Use the WireMock request journal and near-miss diagnostics to separate **unmatched requests** from **business 404s**.
6. Distinguish producer bugs, generation/configuration bugs, packaging/cache bugs, consumer bugs, and test-harness bugs.
7. Link logs across CI jobs using contract revision, producer commit, candidate stubs version, and checksums.
8. Create negative/mutation tests ensuring an incompatible API change **turns tests red**.
9. Write evidence-backed incident reports and fix at the right layer rather than loosening matchers or mocking to force a green build.

## 2. Investigation Principle: From Source-Near Evidence to Real Behavior

A pipeline can contain two fundamentally different test types:

| Check | Key Input | What Does It Execute? | What Does It Prove? |
|---|---|---|---|
| **Producer contract verification** | Contract DSL → generated test | **Real** controller/service/message producer | Implementation satisfies behaviors generated as assertions |
| **Consumer stub testing** | Contract → generated stubs JAR → WireMock | **Real** consumer HTTP client/message handler | Consumer understands loaded stub scenarios |
| **Integration/E2E** | Multi-service environment | Producer, consumer, network, DB, broker | Integration within the test environment's scope |

Never treat a consumer stub PASS as proof the producer implementation is right: WireMock does not invoke the real producer. Likewise, never treat a producer test PASS as proof an older consumer understands a new response.

**Recommended investigation order:**

1. Pinpoint **where the test failed**: producer verification, consumer/Stub Runner, CI artifact resolution, or a live environment.
2. Lock down **candidate identity** and the four evidence layers.
3. Read the contract source.
4. Read the generated producer test and **test execution report**.
5. Read the generated stub mapping and the JAR the consumer actually downloaded.
6. Capture raw request/response from the exact server instance.
7. Compare field by field: method → URL → query → headers → body → response → deserialization.
8. Run a control test, fix the **first broken layer**, and rerun the right scope.
9. Update CI/traceability to prevent recurrence.

This is a **diagnostic workflow**, not a runtime execution order of every tool. For a specific consumer error, you may start with the request journal to gather evidence fast, yet conclusions must still tie back to the contract and artifact.

## 3. Running Example: Checkout Calling Reservation Service

Suppose Checkout is the **consumer** and Reservation Service is the **producer**. The contract requires:

~~~http
POST /api/reservations HTTP/1.1
Content-Type: application/json
Accept: application/json
X-Request-Id: req-1001

{
  "sku": "SKU-123",
  "quantity": 2
}
~~~

Promised response for a fixture with sufficient stock:

~~~http
HTTP/1.1 201 Created
Content-Type: application/json

{
  "reservationId": "R-1001",
  "status": "RESERVED",
  "sku": "SKU-123",
  "quantity": 2
}
~~~

A bug in the consumer might turn the actual request into:

~~~http
POST /api/reservations HTTP/1.1
Content-Type: application/json
Accept: application/json

{
  "productCode": "SKU-123",
  "quantity": "2"
}
~~~

Differences include:

- Missing `X-Request-Id` if required by the contract.
- `sku` renamed to `productCode`.
- `quantity` changed from JSON number to JSON string.
- URL, method, and content type stayed right.

A WireMock mapping matching only `method+path` would return 201 for **both requests**. Thus status 201 alone is **insufficient** to prove the client obeys the contract.

## 4. Evidence Table to Capture at the Start of an Incident

| Category | Question | Evidence to Save |
|---|---|---|
| **Contract source** | Which scenario and revision? | Full path, Git commit/contract artifact, DSL snippet |
| **Generated test** | Which method, body, status, headers asserted? | Generated Java source, test report, test count |
| **Generated mapping** | What does WireMock match? | JSON mapping from exact candidate, body files, mapping ID |
| **Stubs artifact** | Which build did Stub Runner actually resolve? | Group/artifact/version/classifier, JAR checksum, timestamp |
| **HTTP request** | Which bytes did client send to which server? | Method, URL, redacted headers, raw JSON body |
| **HTTP response** | Which status/headers/body did server return? | Raw HTTP response and mapping name/ID if known |
| **Test runtime** | How are base test, Stub Runner, WireMock configured? | Test mode, ports, startup logs, extension versions |
| **Consumer assertion** | What behavior does the test prove? | Assertions, deserializer/error mapper, outcome |
| **CI state** | Any skips, stale caches, or mixed builds? | Job IDs, timestamps, executed test counts |

**Do not start by wiping all caches.** If the real URL is wrong while the mapping is right, refreshing the local Maven repository solves nothing.

## 5. Reading Contract DSL: Outside-In Inspection Order

When opening a Groovy/YAML contract, read in order:

1. **Scenario identity:** description/name/label and source path; does it match the failing testcase?
2. **Request method:** GET, POST, PUT, PATCH, DELETE; does it differ from consumer code?
3. **URL:** exact URL vs. regex/path pattern; are path variables encoded properly?
4. **Query params:** names, types, multi-values, encoded spaces, optional/required.
5. **Headers:** `Content-Type`, `Accept`, auth placeholders, version headers, correlation IDs.
6. **Body:** JSON structure, required fields, data types, null/empty/missing, enums/ranges.
7. **Request matchers:** equality, regex, JSONPath, type, priority; any overly broad matcher?
8. **Response status:** which HTTP status is promised for this scenario?
9. **Response headers:** content type, `Location`, retry/correlation headers.
10. **Response body:** JSON schema, dynamic fields, `bodyFile` references, error codes.
11. **Response matchers:** what specifically will generated tests assert?
12. **Consumer/producer sides:** do dynamic values or `value(consumer(...), producer(...))` give the two sides different inputs?

Specifically, **a sample body does not mean every generated assertion compares the entire body verbatim**. Matchers may relax certain JSONPaths or use regexes. Inspect the generated Java test to see what actually happens.

## 6. Reading a Concrete Groovy Contract

Illustrative contract in SCC Groovy syntax:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    description 'Checkout creates reservation for SKU-123'

    request {
        method POST()
        url '/api/reservations'

        headers {
            contentType(applicationJson())
            header('Accept', 'application/json')
            header('X-Request-Id', 'req-1001')
        }

        body(
            sku: 'SKU-123',
            quantity: 2
        )
    }

    response {
        status CREATED()

        headers {
            contentType(applicationJson())
        }

        body(
            reservationId: 'R-1001',
            status: 'RESERVED',
            sku: 'SKU-123',
            quantity: 2
        )
    }
}
~~~

This contract models a **fixed** scenario. If production business rules permit arbitrary SKUs, add appropriate scenarios/matchers rather than loosening every field so one contract represents the entire domain.

**What to verify:** whether your plugin version supports `CREATED()`/`contentType(applicationJson())` DSL helpers and how the generator translates request headers/bodies into tests/stubs. Examples here are not generated output from a live build.

### Requirement and Consequence Pairs

| Contract | Producer Test Must Do | Consumer Stub Must Match |
|---|---|---|
| POST | Send real POST via test adapter | Must not mistakenly match GET |
| `/api/reservations` | Send exact path | Match only configured path/pattern |
| JSON body `sku`, `quantity` | Send valid fixture | Reject bad body if mapping constrains it |
| Header `X-Request-Id` | Test setup sends header | Require header if contract/pattern guards it |
| Response 201 | Assert 201 | Return 201 per mapping |
| `status=RESERVED` | Assert value per actual matcher | Simulated response contains that value |

## 7. YAML: Reading Structure as the Same Agreement

Alternative YAML example for the **same scenario**:

~~~yaml
description: Checkout creates reservation for SKU-123
name: create_reservation_sku123

request:
  method: POST
  url: /api/reservations
  headers:
    Content-Type: application/json
    Accept: application/json
    X-Request-Id: req-1001
  body:
    sku: SKU-123
    quantity: 2

response:
  status: 201
  headers:
    Content-Type: application/json
  body:
    reservationId: R-1001
    status: RESERVED
    sku: SKU-123
    quantity: 2
~~~

**Do not store both Groovy and YAML for the same scenario**, as that generates duplicate tests/mappings. Standardize on one format managed by the team.

When the YAML parser fails to generate expected tests, inspect indentation, key names, and matcher syntax for your **exact SCC version**. Never edit YAML using WireMock JSON syntax: YAML here is the **contract DSL**, while WireMock JSON is the **generated mapping output**.

## 8. Read Matchers Before Concluding “Wrong Response Yet Green Test”

A contract might contain:

~~~groovy
response {
    status CREATED()
    body(
        reservationId: 'R-1001',
        status: 'RESERVED',
        sku: 'SKU-123',
        quantity: 2
    )
    bodyMatchers {
        jsonPath('$.reservationId', byRegex('R-[0-9]+'))
        jsonPath('$.status', byType())
        jsonPath('$.sku', byType())
        jsonPath('$.quantity', byType())
    }
}
~~~

In this scenario, `status` and `sku` are checked only by type. Response:

~~~json
{
  "reservationId": "R-9999",
  "status": "FAILED",
  "sku": "SKU-WRONG",
  "quantity": -100
}
~~~

satisfies most type/regex matchers despite completely wrong business logic.

Four diagnostic questions:

1. Does this field have an **invariant value** for the fixture?
2. Does a format-only regex ignore request/response correlation?
3. Could a deserializer coerce JSON numbers/strings/booleans?
4. Is there a separate contract for error/boundary statuses the consumer relies on?

**Fix at the source:** update `bodyMatchers`/scenarios in the contract to guard real invariants, then regenerate producer tests and mappings; **never add temporary assertions in the consumer to mask a weak producer contract**.

## 9. Dynamic Value Syntax: Identify Producer and Consumer Sides

When responses hold dynamic values like IDs or timestamps, SCC provides ways to express distinct values for **producer tests** and **consumer stubs**, depending on Groovy/YAML DSL version.

Mental model:

~~~text
Real producer:
  returns any reservationId formatted as R-[0-9]+

Consumer stub:
  returns sample reservationId R-1001 for reproducible tests
~~~

Inspect not only `body()`, but also `value(...)`, `consumer(...)`, `producer(...)`, regular expressions, `byRegex`, and `byCommand` when used by the contract.

Common pitfalls:

- A stub-intended value is asserted as equality on the producer, causing false FAILS.
- A producer-intended dynamic expression leaks into the stub, making consumer tests flaky.
- Overly broad regex such as `.*` lets broken enums/statuses slip past.
- Test expects an exact ID when the producer legitimately generates fresh IDs.
- A dynamic field is matched in response, yet the consumer asserts a hardcoded sample ID outside the contract.

**Never guess the direction of `value` in an unfamiliar DSL version**; verify in both outputs: **generated Java tests and WireMock JSON mappings**.

## 10. Where Do Generated Producer Tests Live?

SCC Maven/Gradle plugins generate Java test sources, typically under **build output** directories depending on plugin version and configuration:

~~~text
Producer Maven (typical example paths):
  target/generated-test-sources/contracts/...

Producer Gradle (typical example paths):
  build/generated-test-sources/contracts/...
  or build/generated-test-sources/...
~~~

**These are illustrative paths, not fixed rules for every build.** When debugging for real, inspect **plugin task logs/generated test compile inputs** to locate the output directory, and open the test file generated for the **exact contract name/scenario**.

If tests are missing:

- Were contract files discovered?
- Does `contractsDirectory` point to the right module/source?
- Which **producer module** applies the plugin?
- Did the test-generation task/goal actually execute?
- Did generated sources compile and get discovered by the test runner?
- Are skip flags, naming patterns, or JUnit mismatches interfering?

Do not conclude “no generated tests exist” solely by checking one default folder; the output directory may have been customized.

## 11. Reading Generated Tests: Locate Request Setup and Response Assertions

**Pseudocode Java example illustrating what to look for**, not verbatim output from a specific SCC version:

~~~java
@Test
void shouldCreateReservation() {
    // Test adapter may be RestAssured, MockMvc, or WebTestClient.
    HttpResponse result = testClient.post("/api/reservations")
        .header("Content-Type", "application/json")
        .header("Accept", "application/json")
        .header("X-Request-Id", "req-1001")
        .json("""
            {"sku":"SKU-123","quantity":2}
            """);

    assertThat(result.status()).isEqualTo(201);
    assertThat(result.header("Content-Type"))
        .contains("application/json");
    assertThat(result.json("$.reservationId"))
        .isEqualTo("R-1001");
    assertThat(result.json("$.status"))
        .isEqualTo("RESERVED");
    assertThat(result.json("$.sku"))
        .isEqualTo("SKU-123");
    assertThat(result.json("$.quantity"))
        .isEqualTo(2);
}
~~~

In the **actual** generated file, check:

1. Which contract corresponds to the test method/class name?
2. Does the request adapter hit the real app context, a live HTTP server, MockMvc, or a mock?
3. How are method/path/headers/body serialized?
4. Is the response status assertion exact or a range?
5. Are JSON body assertions equality, regex, type, or custom commands?
6. Do assertions verify the whole response or only selected JSONPaths?
7. Do assertions exist for separate error scenarios?
8. Which test base class is extended?
9. Do test counts/execution reports prove the method actually ran?

**Distinguish generated test sources existing from executed tests PASSING.** Generated code that JUnit/Surefire/Gradle never ran proves nothing about the producer.

## 12. Generated Tests “Syntactically Valid” Yet Calling the Wrong Implementation

With Spring MVC, a base test like:

~~~java
import io.restassured.module.mockmvc.RestAssuredMockMvc;
import org.junit.jupiter.api.BeforeEach;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
public abstract class ReservationContractBase {

    @Autowired
    MockMvc mockMvc;

    @BeforeEach
    void setup() {
        RestAssuredMockMvc.mockMvc(mockMvc);
    }
}
~~~

routes generated tests through the real Spring MVC context. Yet if base setup uses:

~~~java
// Anti-pattern: fake controller always returning expected body.
RestAssuredMockMvc.standaloneSetup(
    new FakeReservationController()
);
~~~

tests pass even when the production controller/service is broken.

When diagnosing:

- Does the base class use `@SpringBootTest`/`@AutoConfigureMockMvc` with proper injection?
- Is there a `@MockitoBean`/`@MockBean` replacing the **very business service under verification**?
- If an external dependency is mocked, does it skip critical business logic?
- Does producer state/setup seed data rather than returning canned expected responses directly?
- Does test setup execute before generated methods?

A mutation check: temporarily change the production controller to return 200 instead of 201. **The generated test must turn red.** If it stays green, suspect fakes/mocks, unexecuted tests, or missing assertions.

## 13. Read Execution Reports Instead of Reading Only “BUILD SUCCESS”

Statuses to distinguish:

| Status | Meaning | Action |
|---|---|---|
| **PASS** | Generated method executed and assertions held | Reconcile source/commit and test count |
| **FAIL** | Assertion mismatched actual response | Compare expected vs. actual on method/status/body |
| **ERROR** | Setup/context/connection/compile/runtime failure | Fix environment/test wiring first |
| **SKIPPED** | Test skipped | Do not treat as producer-verified |
| **NOT_RUN** | No generated execution report | Check test discovery or pipeline tasks |
| **STALE** | Report from an older commit/contract | Do not use as candidate evidence |
| **ZERO_TESTS** | Zero tests executed | Fail closed when module requires contracts |

A log showing:

~~~text
BUILD SUCCESS
Tests run: 0, Failures: 0, Errors: 0, Skipped: 0
~~~

**is not verification evidence** when the producer requires contract tests.

In CI, enforce that executed generated producer tests are **greater than 0**, unskipped, and PASSING—never count module-wide unit tests alone.

## 14. From Generated Tests to Mappings: Understanding Both Sides

One contract produces:

~~~mermaid
flowchart LR
    A["Contract request+response"] --> B["Generated producer test"]
    A --> C["Generated WireMock mapping"]
    B --> D["Send fixture request to real producer"]
    D --> E["Assert real response"]
    C --> F["WireMock matches consumer request"]
    F --> G["Return stub response per contract"]
~~~

Remember:

- **Generated producer test:** sends concrete inputs and checks real responses via matchers.
- **WireMock mapping:** consumer requests must match generated predicates; server returns the sample (or templated) response.
- If request matchers are too loose, consumers send broken bodies and still get success.
- If response matchers are too loose, producers emit wrong business semantics yet tests PASS.
- If generated mappings differ from current contract sources, check **plugin version, source revision, stale build outputs, or customizations** before editing the client.

A failure on one side does not automatically prove the other side is broken. Inspect both outputs **independently** and pin them to the same contract revision.

## 15. Reading Generated WireMock Mappings: Key Fields

An illustrative mapping for `POST /api/reservations`:

~~~json
{
  "name": "create-reservation-sku123",
  "request": {
    "method": "POST",
    "url": "/api/reservations",
    "headers": {
      "Content-Type": {
        "contains": "application/json"
      },
      "X-Request-Id": {
        "equalTo": "req-1001"
      }
    },
    "bodyPatterns": [
      {
        "equalToJson": "{\"sku\":\"SKU-123\",\"quantity\":2}"
      }
    ]
  },
  "response": {
    "status": 201,
    "headers": {
      "Content-Type": "application/json"
    },
    "jsonBody": {
      "reservationId": "R-1001",
      "status": "RESERVED",
      "sku": "SKU-123",
      "quantity": 2
    }
  }
}
~~~

**This is illustrative WireMock JSON, not a claim SCC generates this exact structure.** Depending on contract DSL, matchers, and WireMock version, mappings may use `urlPath`, `urlPattern`, `matchesJsonPath`, `equalToJson`, `bodyFileName`, or other forms.

In the **real** mapping, read in order:

| Field | Question |
|---|---|
| `name`/`id` | Does it correspond to the contract scenario and candidate artifact? |
| `priority` | Is a higher-priority mapping intercepting the request? |
| `request.method` | Is it really POST or `ANY`/`GET`? |
| `request.url`/`urlPath`/`urlPattern` | Exact match or regex; is path exact? |
| `request.queryParameters` | Optional/required, encoding, multi-values? |
| `request.headers` | Do `Content-Type`, version headers, `X-Request-Id` match? |
| `request.bodyPatterns` | JSON field names, number/string, null/array? |
| `response.status` | 201 or 200/400/404/503? |
| `response.headers` | Content type, `Location`, correlation headers? |
| `response.body`/`jsonBody`/`bodyFileName` | Does the body match expected schema/values? |
| `scenarioName`/`requiredScenarioState` | Is the server in the expected state? |
| `transformers`/`metadata` | Do custom extensions alter behavior or provenance tags? |

Never inspect only one success mapping. Inspect **all potentially overlapping mappings** for that method and path.

## 16. Why Can a Valid Contract Produce an Unexpected Mapping?

Common causes:

1. **Generated from an older revision:** uncleaned build output or job reading different source.
2. **Different plugin settings:** DSL/extension version controls how matchers convert.
3. **Dynamic value direction:** producer/consumer values differ per DSL rules.
4. **Body file reference:** mapping uses `bodyFileName` while payload sits in `__files`.
5. **Custom mapping overlay:** a post-generation build step overwrote or added mappings.
6. **WireMock extension/templating:** runtime transformers alter effective responses.
7. **Wrong scenario file:** opened a `reservation` mapping that belongs to an error case or another scenario.
8. **Wrong JAR:** local generated file is fresh while consumer Stub Runner downloaded an old JAR.
9. **Wrong build module config:** Gradle/Maven generated stubs from another module or source set.

**Never edit generated mappings inside `target`/`build` as a temporary fix.** If behavior belongs to the contract, update the DSL; if it is a valid customization, keep it under controlled source and clarify merge order/versioning.

## 17. Inspect the Packaged Stubs JAR, Not Just Workspace Mapping Files

An artifact is commonly distributed under coordinates:

~~~text
groupId:    com.example
artifactId: reservation-service
version:    1.4.0-rc.pr173.a1b2c3d4
classifier: stubs
type:       jar
~~~

With a JDK available, inspect JAR contents:

~~~bash
jar tf target/reservation-service-1.4.0-rc.pr173.a1b2c3d4-stubs.jar
~~~

An illustrative structure:

~~~text
META-INF/
  com.example/
    reservation-service/
      1.4.0-rc.pr173.a1b2c3d4/
        contracts/
          reservation/create-reservation.groovy
        mappings/
          create-reservation.json
        __files/
          reservation-body.json
~~~

**Paths are examples only**; check real output because plugin versions and `contractsPath`/packaging configs alter layouts.

If the mapping contains:

~~~json
{
  "response": {
    "status": 201,
    "headers": {
      "Content-Type": "application/json"
    },
    "bodyFileName": "reservation-body.json"
  }
}
~~~

confirm `reservation-body.json` exists inside the **actually downloaded JAR** at the resource root WireMock reads. Seeing it in the producer working tree is not enough.

## 18. Stub Runner `LOCAL`/`REMOTE` and Fetching the Exact Version

A consumer test might configure:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.contract.stubrunner.spring.AutoConfigureStubRunner;
import org.springframework.cloud.contract.stubrunner.spring.StubRunnerProperties;

@SpringBootTest
@AutoConfigureStubRunner(
    ids = "com.example:reservation-service:1.4.0-rc.pr173.a1b2c3d4:stubs:18081",
    stubsMode = StubRunnerProperties.StubsMode.REMOTE,
    repositoryRoot = "https://repo.example.invalid/repository/candidates"
)
class CheckoutReservationContractTest {
    @Test
    void runsWithStubs() {
        // Call Checkout's real ReservationClient against the Stub Runner port.
    }
}
~~~

`example.invalid` is a placeholder URL. This is an **illustrative test skeleton**: add client wiring, method assertions, repository credentials, and verify annotation properties against your SCC version.

- **LOCAL:** resolves from the local Maven repository; producer `package` does not necessarily install the JAR there.
- **REMOTE:** downloads from a Maven-compatible repository, subject to metadata/mirrors/credentials and proxy caches.
- **Port 18081:** must match the URL the client uses. With dynamic ports, inject the allocated port rather than hard-coding it in the client.
- **New vs. old consumer:** identical client code can pass against stub A and fail against stub B; verify which producer candidate artifact B corresponds to.

An `artifact not found` `404` during **resolution** differs from an HTTP `404` returned by WireMock on an unmatched request. Separate them by timing: before server startup vs. after the client calls the server.

## 19. SNAPSHOTs, Caches, and Freshness: Check Evidence, Never Assume from Names

Suppose the producer publishes sequentially:

~~~text
09:00  reservation-service:1.4.0-SNAPSHOT
       mapping A requires numeric quantity

09:30  reservation-service:1.4.0-SNAPSHOT
       mapping B updates headers/matchers

09:35  consumer Stub Runner still holds mapping A from 09:05
~~~

Logical coordinate `1.4.0-SNAPSHOT` **can point to multiple timestamped builds**. A consumer test referencing that version string is not guaranteed to have fetched build B.

To verify:

1. Capture the intended producer commit, contract revision, and build/job ID.
2. Record the **exact group/artifact/version/classifier**.
3. For SNAPSHOTs, record the resolved timestamped version or SHA-256 digest.
4. Compare the producer-published JAR against the **JAR actually downloaded by the consumer**.
5. Inspect repository proxy/mirror/update policies if metadata is stale.
6. Check when Stub Runner/WireMock started: an already-running server does not reload old mappings just because a new JAR appeared.
7. Restart/refresh context properly if needed, then verify effective mappings and the request journal.
8. Only then conclude the consumer test covers that candidate.

`mvn -U` and Gradle `--refresh-dependencies` affect their respective resolvers; **they do not automatically refresh a running WireMock server or an unrelated resolver**.

In CI compatibility gates, **immutable commit-based candidate versions** are far more reproducible and race-free than shared SNAPSHOTs.

## 20. Checksums and Manifests Link Source to Runtime

To reconcile the packaged file with what the consumer downloaded, compute SHA-256:

~~~bash
sha256sum reservation-service-1.4.0-rc.pr173.a1b2c3d4-stubs.jar
~~~

In PowerShell:

~~~powershell
Get-FileHash -Algorithm SHA256 -Path .\reservation-service-1.4.0-rc.pr173.a1b2c3d4-stubs.jar
~~~

A provenance report might include:

~~~yaml
producer:
  service: reservation-service
  commit: a1b2c3d4
contract:
  revision: a1b2c3d4
  source: contracts/reservation/create-reservation.groovy
stubs:
  groupId: com.example
  artifactId: reservation-service
  version: 1.4.0-rc.pr173.a1b2c3d4
  classifier: stubs
  sha256Published: FROM_PRODUCER_CI
  sha256Resolved: FROM_CONSUMER_CI
test:
  consumerCommit: FROM_CHECKOUT_CI
  stubRunnerPort: FROM_RUNTIME
  producerContractsExecuted: FROM_PRODUCER_TEST_REPORT
  consumerTestsExecuted: FROM_CONSUMER_TEST_REPORT
~~~

`FROM_*` are placeholders filled by real pipelines. **A checksum alone does not prove “freshness”**; compare it against the trusted producer CI's expected checksum.

You can store provenance in a sidecar manifest/attestation linking the digest. If embedding a manifest inside the JAR, **package the manifest before computing the digest** to avoid the circularity of writing a JAR's own checksum inside itself.

## 21. When Should You Open the WireMock Request Journal?

When the consumer gets an unexpected response, the journal answers **what the server actually received** instead of guessing from client code.

Example details to inspect:

~~~text
Server: localhost:18081
Request:
  POST /api/reservations
  Content-Type: application/json
  X-Request-Id: <missing>
  Body: {"productCode":"SKU-123","quantity":"2"}

Match:
  matchedStubId: none
  nearestStub:
    create-reservation-sku123
  mismatch:
    header X-Request-Id absent
    body sku missing; quantity wrong type

Response:
  HTTP 404
  body: WireMock diagnostic (not business 404)
~~~

This is an **illustrative diagnostic log**, not verbatim output from every WireMock version.

An unmatched request receives default 404 or a fallback mapping. Hence **HTTP 404 does not prove a business `RESERVATION_NOT_FOUND`**. Verify status **plus error code/body** and the journal when needed.

**Security note:** the request journal can hold authorization tokens, cookies, or PII. Redact/sanitize before writing to CI reports; never publish raw secrets.

## 22. Fetching the Journal via the Admin API with Test-Server Access

WireMock provides an Admin API. On a test instance you control, query the request journal via standard paths:

~~~bash
curl -sS http://localhost:18081/__admin/requests
~~~

In supporting versions:

~~~bash
curl -sS http://localhost:18081/__admin/requests/unmatched
~~~

You can also use Java APIs `WireMock.verify(...)` or `findAll(...)` when tests hold matching client/server config.

**Do not assume Admin API paths and JSON schemas are identical across every WireMock version.** Check documentation matching your runtime and verify the journal is enabled. A server can disable journaling to save memory or protect data.

More importantly: point the Admin API at the **exact WireMock instance Checkout calls**. When a test starts multiple services/ports, querying the wrong server leads to a false “no requests received” conclusion.

## 23. Use `curl` as a Control to Separate Client Bugs from Stub Bugs

In the test network, send a valid request directly:

~~~bash
curl -i -X POST "http://localhost:18081/api/reservations" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json" \
  -H "X-Request-Id: req-1001" \
  --data '{"sku":"SKU-123","quantity":2}'
~~~

If WireMock returns the expected 201 mapping to this command while Checkout's client gets 404, inspect **Checkout's actual outgoing request** (not only the caller method). A bug may be the DTO serializer emitting `productCode` or omitting a required header.

Next send a deliberately broken request:

~~~bash
curl -i -X POST "http://localhost:18081/api/reservations" \
  -H "Content-Type: application/json" \
  -H "X-Request-Id: req-1001" \
  --data '{"productCode":"SKU-123","quantity":"2"}'
~~~

Expectation if the baseline mapping constrains request bodies: **must not match happy-path 201**. Actual output may be 404/unmatched diagnostics or a business-validation mapping per contract.

**If both the broken request and valid request return 201**, inspect `bodyPatterns`, mapping priorities, and custom fallbacks. Matchers may be overly broad or another mapping is returning success.

`curl` is a diagnostic probe, **never a replacement for real consumer tests**, because it bypasses client serialization, deserialization, and error mapping.

## 24. Compare Raw Requests Against DTO/Client Source: Do Not Guess Types

Suppose a Java DTO is:

~~~java
record CreateReservationRequest(
    String productCode,
    String quantity) {
}
~~~

and the client builds:

~~~java
CreateReservationRequest req =
    new CreateReservationRequest("SKU-123", "2");
~~~

Without annotations/serializer overrides renaming fields, JSON becomes:

~~~json
{"productCode":"SKU-123","quantity":"2"}
~~~

while the contract requires:

~~~json
{"sku":"SKU-123","quantity":2}
~~~

**The bug sits in the client contract**, not an “overly strict” mapping. Fix the DTO/wiring per agreement, e.g.:

~~~java
record CreateReservationRequest(
    String sku,
    int quantity) {
}
~~~

Still inspect actual raw JSON, as Jackson `@JsonProperty`, naming strategies, custom serializers, null inclusion, converters, WebClient/Feign/RestClient configs, and `Content-Type` all shape wire bytes.

Some deserializers coerce `"2"` to a number; payload type testing must enforce the **committed wire format**, not rely on the current producer happening to tolerate coercion.

## 25. Header Matching: Spot Differences Invisible in JSON

A common failure:

~~~text
Contract:
  X-Request-Id: req-1001
  Content-Type: application/json

Actual consumer request:
  X-Request-ID: absent
  Content-Type: text/plain; charset=UTF-8
~~~

**HTTP header names are case-insensitive**; `X-Request-Id` and `x-request-id` are the same header on the wire. However, a **missing header** or **wrong value** is different.

Items to check:

- Does `Content-Type` carry the right media type, and is an appended `charset` permitted by contract/matchers?
- Is `Accept` sent, and could a proxy/client library alter it?
- Is `Authorization` required in production, and do tests mock security filters?
- Does middleware inject/overwrite `X-Request-Id`?
- Did a redirect strip headers from the request?
- Does `Content-Encoding`/gzip affect how WireMock matches the body?

Never weaken a contract header matcher from exact to `.*` just to let missing/wrong requests pass. If the requirement is `application/json` with an optional charset, write a predicate expressing **that exact allowed scope**.

## 26. Query Params, Path Variables, and Encoding

Given URL:

~~~text
/api/items?search=red%20shoe&page=1
~~~

distinguish:

- URL path `/api/items`;
- Query parameter `search=red shoe` after decoding;
- `page` is query string `"1"` on the wire even though the server parses it as an integer;
- Spaces may be encoded as `%20` or `+` per URL encoding rules;
- Multi-value parameters `tag=red&tag=blue` need matching contracts/matchers;
- Path variables containing `/` or Unicode can be encoded/normalized differently by clients/proxies;
- Query order is usually non-contractual unless signing/canonicalization requires it.

If a contract uses an exact `url()` string when the API cares only about query semantics, generated mappings become brittle. Conversely, using `urlPathPattern` without checking required query params makes stubs too loose.

**How to debug:** compare raw URLs from the journal, then switch to path/query matching aligned **with the contract**, rather than editing URLs just because a screenshot looks different.

## 27. Mapping Priority, Scenario State, and Custom Transformers

When a mapping looks right yet the response is wrong, inspect fields outside `request`:

~~~text
priority
scenarioName
requiredScenarioState
newScenarioState
transformers
metadata
bodyFileName
~~~

Suppose two mappings both match `POST /api/reservations`:

~~~text
Generated contract:
  priority: 5
  response: 201 RESERVED

Custom fallback:
  priority: 1
  response: 200 ACCEPTED
~~~

In WireMock, **smaller priority numbers usually take higher precedence**. Thus fallback priority 1 shadows generated mapping priority 5.

A scenario left in state `Depleted` can also alter responses; test A failing to reset state breaks test B. A response transformer or response templating can mutate body/headers after mapping selection.

Diagnose in sequence:

1. Which mappings can match the request?
2. What is each mapping's priority?
3. What scenario state is the server currently in?
4. Which extensions/templates are registered on that exact instance?
5. Which body file is actually read?
6. Did an earlier test add dynamic stubs via the Admin API?
7. Which mapping did the request journal record as winning?

**A valid generated mapping does not guarantee WireMock serves it** when runtime customizations exist. If a customization changes public semantics, review and test it explicitly rather than merely patching stubs.

## 28. Real Producer Responses vs. Stub Runner Responses Are Not Identical

A classic source of confusion:

~~~text
Producer (real HTTP):
  POST /api/reservations -> 200 ACCEPTED

Stub Runner (contract):
  POST /api/reservations -> 201 RESERVED
~~~

Producer contract tests should FAIL (if genuinely run against the producer), while consumer stub tests PASS. That is not a contradiction: **WireMock simulates the contract**, not whatever runtime code currently does.

To investigate the real producer:

- Verify generated producer tests ran on the **current code revision**.
- Use the test adapter/real HTTP against the right Spring context/configuration.
- Check controller routing, service behavior, exception handlers, and serializers.
- Compare the real HTTP response against generated assertions.
- Check whether filters/interceptors/`@ControllerAdvice` alter status or body.
- If producer tests PASS while runtime behaves wrongly, suspect a fake base test, a different profile/config, or a deployed binary different from the tested artifact.

**Never update a stub to match a buggy producer implementation** without checking contract and consumer requirements. Contract changes require review, especially breaking ones.

## 29. Diagnose from the First Point of Failure

A minimal decision tree:

~~~mermaid
flowchart TD
    A["Contract test / consumer test FAILS"] --> B{"Contract DSL discovered and parsed?"}
    B -- "No" --> B1["Fix source path / YAML-Groovy / plugin config"]
    B -- "Yes" --> C{"Did generated producer tests run?"}
    C -- "No" --> C1["Runner, skip flags, test count, base class"]
    C -- "Yes" --> D{"Did generated tests PASS against real producer?"}
    D -- "No" --> D1["Compare request fixture, actual response, and assertions"]
    D -- "Yes" --> E{"Stubs artifact right candidate/digest?"}
    E -- "No" --> E1["Generation/packaging/repository/cache"]
    E -- "Yes" --> F{"Did WireMock receive right client request?"}
    F -- "No" --> F1["Port/URL/method/headers/body/encoding"]
    F -- "Yes" --> G{"Was expected mapping selected?"}
    G -- "No" --> G1["Priority, state, fallback, custom extension"]
    G -- "Yes" --> H{"Did consumer handle response properly?"}
    H -- "No" --> H1["DTO, deserializer, status/error mapping"]
    H -- "Yes" --> I["Inspect assertions/CI report; confirm PASS scope"]
~~~

**This is a diagnostic decision tree, not a rule that every producer must have consumers on every branch.** If a failure happens on a draft contract with no producer implementation yet, the right status is Draft/Not verified, not a forced release.

### Principles for Fixing at the Right Layer

- Contract parser FAILS → fix DSL/plugin config; do not delete consumer assertions.
- Generated test FAILS due to wrong producer response → fix implementation or propose a reviewed contract change.
- Mapping misses a bad consumer request → fix client serializer/headers/path; do not delete `bodyPatterns`.
- Stub Runner loads the wrong artifact → fix resolution/provenance; do not edit the contract.
- WireMock mapping overridden by customization → fix priority/extension/isolation.
- Consumer gets valid raw response yet parses wrongly → fix DTO/handler or adjust compatibility plan.
- Test report has zero executed tests → fix CI runner; never treat build success as verification.

## 30. Distinguish HTTP 404 by Context

Three distinct failures can surface as `404`:

| Situation | Where It Happens | Interpretation |
|---|---|---|
| Repository returns 404 fetching stubs JAR | Artifact resolution before Stub Runner starts | Wrong coordinates/repository/classifier or unpublished artifact |
| WireMock returns 404 on unmatched request | Stub Runner serving HTTP | Client/protocol/mapping mismatch |
| Contract defines business 404 + error code | Stub Runner/producer returns scenario response | Valid business scenario |

Business error example:

~~~http
HTTP/1.1 404 Not Found
Content-Type: application/json

{"code":"RESERVATION_NOT_FOUND","message":"Reservation does not exist"}
~~~

If a consumer test checks only `status == 404`, an **unmatched stub 404** can masquerade as a business error. Assert **status + `error.code` + body schema**, and check the request journal when needed to confirm which mapping responded.

Never hardcode every 404 as “reservation not found” in the client when the API defines multiple error semantics or when WireMock unmatched responses should fail tests.

## 31. Distinguish Producer 400/422 from Unmatched Stub

A real producer may return 400/422 for a malformed body:

~~~json
{"productCode":"SKU-123","quantity":"2"}
~~~

Yet a stub modeling only the 201 happy path **lacks a 400/422 mapping** and returns an unmatched 404. Never conclude from that that the real producer returns 404.

To test validation contracts, add a **dedicated error scenario**:

~~~yaml
description: Wrong quantity type in request
name: reservation_invalid_quantity

request:
  method: POST
  url: /api/reservations
  headers:
    Content-Type: application/json
  body:
    sku: SKU-123
    quantity: "two"

response:
  status: 422
  headers:
    Content-Type: application/json
  body:
    code: INVALID_QUANTITY
    message: Quantity must be a positive integer
~~~

This YAML illustrates a **request validation case**. Returning 422 must match your project's API policy, not a universal HTTP rule. Producer code and generated tests must verify the real behavior, while Stub Runner consumer tests verify the error mapper.

If the producer returns 400 instead of the contract's agreed 422, that may be a regression. Never change the expected status to 400 without reviewing with consumers first.

## 32. JSON `null`, Missing, Empty, and Number/String: Compare Both Type and Semantics

JSON responses can look nearly identical in formatted logs:

~~~json
{"quantity":2,"reservationId":"R-1001"}
~~~

~~~json
{"quantity":"2","reservationId":"R-1001"}
~~~

~~~json
{"quantity":null,"reservationId":"R-1001"}
~~~

~~~json
{"reservationId":"R-1001"}
~~~

If a consumer DTO uses primitive `int`, missing/`null` may silently default per deserializer settings, hiding contract drift. A mapper might coerce string `"2"` into integer `2`. Therefore inspect **raw HTTP bodies** and write targeted assertions:

| Check | Purpose |
|---|---|
| JSON type/JSONPath assertion | Prevents mistaking strings for numbers |
| Field presence | Catches missing required fields |
| Nullability | Separates `null` from valid values |
| Fixture equality | Protects business values |
| Enum whitelist | Guards consumers against unknown values |
| Negative cases | Confirms consumer fails/falls back cleanly on invalid schemas |

**Never inspect only the deserialized object** to conclude the wire format is right. Deserializers can erase critical differences.

## 33. Extra Header/Body Fields in Requests Are Not Always Breaking

A request might include an optional field:

~~~json
{"sku":"SKU-123","quantity":2,"source":"checkout-mobile"}
~~~

If the contract/request schema **permits unknown fields**, a strict `equalToJson` mapping across all keys rejects valid consumer requests that the real producer accepts. Conversely, if the API specifies a **closed schema**, rejecting is right.

Separate in diagnosis:

- **Required fields:** missing `sku` must be caught.
- **Optional/additive fields:** allowed or disallowed per contract?
- **Unknown fields:** do producer/consumer enforce strict parsing?
- **JSON key order:** normally non-semantic unless signing/canonicalization requires it.
- **Whitespace/number formatting:** avoid raw string equality when the API promises semantic JSON, while preserving type distinctions.
- **Body matchers:** what `ignoreExtraElements`/array-order settings do `equalToJson`/JSONPath apply?

Do not relax matchers to “any JSON is valid” because of one extra field. Use policy-accurate matchers and run negative tests on required schema rules.

## 34. Message Contracts: Inspect Real Output and Handlers Instead of HTTP Journals

When SCC uses message contracts, there is no HTTP request journal. Groovy example:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    label 'reservationCreated'

    input {
        triggeredBy('triggerReservationCreated()')
    }

    outputMessage {
        sentTo('reservation.events')
        headers {
            header('eventType', 'ReservationCreated')
        }
        body(
            reservationId: 'R-1001',
            sku: 'SKU-123',
            quantity: 2
        )
    }
}
~~~

To diagnose producer message verification:

1. Which base-test method does `triggeredBy(...)` call?
2. Does that method invoke the **real production service/use case** or send a canned sample message?
3. Does the producer emit to destination `reservation.events` through the configured test binder/verifier?
4. Does the `eventType` header match expected value?
5. Does the payload have exact JSON types, required fields, and schema version?
6. Do generated tests include clear assertions/timeouts and actually execute?
7. Are stale messages sitting in test channels from an earlier run?

On the consumer side, run the **real message handler/deserializer** to verify parsing and business outcomes. Calling `ObjectMapper.readTree` on a fixture alone does not prove listener routing or state updates.

For broker partitions, retries, DLQs, ordering, and at-least-once delivery, add broker/integration tests when contract stubs do not cover those behaviors. **Do not apply HTTP-oriented diagnostics to messaging cases.**

## 35. WebFlux and Test Adapters: Catch Bugs at Request Initialization

A producer may use Spring MVC, WebFlux, or a live HTTP server. SCC supports different adapters/test modes by version; **generated test sources** and the base class reveal which mode ran.

For example, if generated tests use `WebTestClient` while the base class configures only `RestAssuredMockMvc`, requests will not reach the intended controller. Conversely, running a standalone fake handler does not prove production WebFlux routers, filters, or handlers work.

Checks:

- Which adapter do generated test imports use?
- Does the base class initialize `MockMvc`, `WebTestClient`, or a live HTTP port?
- Is the test server port injected properly, especially with `RANDOM_PORT`?
- Are filters/security configs enabled per contract scope?
- Is the `RouterFunction`/controller registered in the Spring test context?
- Is the reactive pipeline properly subscribed to and awaited?
- Could timeouts/cancellations finish tests early without checking output?

Never copy a Spring MVC base test into a WebFlux project and “fix” it by mocking responses. Pick an adapter/config compatible with your Spring Boot–Spring Cloud Contract release train and verify via mutation testing.

## 36. Compare All Four Layers in a Reviewable Diff Table

**Illustrative comparison table** when Checkout's reservation POST hits 404:

| Condition | Contract DSL | Generated Producer Test | WireMock Mapping | Actual Checkout Request |
|---|---|---|---|---|
| Method | POST | POST | POST | POST |
| Path | `/api/reservations` | Same path | Same path | Same path |
| Content-Type | `application/json` | Sends JSON | Matcher may verify | `application/json` |
| `X-Request-Id` | `req-1001` | Header sent | `equalTo` `req-1001` | **Missing** |
| `sku` | `SKU-123` | Field sent | `equalToJson`/JSONPath | **`productCode`** |
| `quantity` | JSON number `2` | `2` | Number `2` | **String `"2"`** |
| Expected status | `201` | Asserts `201` | Response `201` | **Unmatched 404** |
| Next action | Keep contract intact | Producer tests can PASS | Mapping is sound | **Fix Checkout client** |

This table reveals the **first diverging layer**. When source contract, generated test, and mapping all align while the actual request is wrong, never alter the contract/mapping just to return 201 to that broken request.

In a real incident, replace assumptions with exact data extracted from generated code, mapping bytes, and the actual request journal. Never fabricate fields before collecting them.

## 37. Case Study A — Producer Tests PASS, Consumer Receives 404

### Context

Groovy contract specifies POST `/api/reservations`, JSON `sku`, and numeric `quantity`; generated producer tests PASS.

### Consumer Symptom

~~~text
Checkout CI:
  expected: HTTP 201
  actual: HTTP 404
~~~

### Diagnostic Chain

1. Confirm 404 is an **HTTP response from WireMock**, not a JAR download failure.
2. Confirm Stub Runner serves Reservation Service on the port the consumer client calls.
3. Confirm the JAR/digest matches the target candidate.
4. Read the mapping's `bodyPatterns`/headers.
5. Query the request journal on that exact instance.
6. Inspect raw body: `{"productCode":"SKU-123","quantity":"2"}`.
7. Inspect client DTO: Java field `productCode` and `String quantity`.
8. Fix DTO/request serialization to send `{"sku":"SKU-123","quantity":2}`.
9. Rerun consumer tests and keep negative tests so malformed client requests turn red again.

### What Not to Do

- Do not delete `bodyPatterns` and claim tests PASS.
- Do not add a catch-all 201 for every POST.
- Do not edit the producer contract to match an unapproved consumer serialization bug.

## 38. Case Study B — Producer Returns Wrong Output Yet Generated Tests Stay Green

### Context

Contract requires:

~~~http
HTTP/1.1 201 Created
Content-Type: application/json

{"status":"RESERVED"}
~~~

Production producer implementation has a bug and returns:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{"status":"PENDING"}
~~~

Yet producer CI stays green.

### Investigation

1. Do generated Java tests assert status 201 and `status=RESERVED`?
2. Do test reports show **executed generated tests > 0**, or zero/skipped?
3. Does the base test use the real Spring context/controller or `standaloneSetup(new FakeController())`?
4. Is `ReservationService` mocked to always return the expected DTO?
5. Do tests run with a different profile/config than production or call a different mock endpoint?
6. Are runtime exception handlers/middleware bypassed in tests?
7. Test a mutation changing `201→200` and `RESERVED→PENDING` in producer code—tests must turn red.
8. If generated assertions are missing, fix contract matchers; if tests hit fake code, fix base wiring.

**Conclusion:** green tests can reflect an **execution-evidence** or matcher defect rather than bug-free producer code.

## 39. Case Study C — Mapping Right in Workspace, Stub Runner Uses Old Copy

### Context

Producer commit B updated a contract request header and generated a new mapping. Checkout CI keeps passing against a `1.4.0-SNAPSHOT` version.

### Investigation

1. Record commit B, expected stubs JAR, and checksum from producer CI.
2. Inspect the JAR resolved by the consumer; compare timestamped snapshot/digest.
3. Check whether Stub Runner started before or after B was published.
4. Inspect repository mirror/proxy metadata and local caches if digests mismatch.
5. Launch a fresh Stub Runner with the **exact candidate**.
6. Inspect effective mappings via Admin API/journal to verify commit B's header matcher.
7. Temporarily omit the required header in Checkout's client: tests must fail.
8. Log resolved identity/digest in CI reports to prevent recurrence.

**Conclusion:** never blame the DSL when the consumer has not loaded the exact artifact built from that DSL.

## 40. Troubleshooting Matrix: Symptom → Layer → Next Step

| Symptom | Suspected Layer | First Check |
|---|---|---|
| Contract file exists, no tests generated | Contract discovery/generator | File path, plugin config, task logs |
| Contract fails to parse | Groovy/YAML DSL | Syntax, indentation, version-specific matcher types |
| Generated test fails to compile | Generator/test base/version | Imports, JUnit, class/method names, plugin release train |
| Generated test PASSES with `Tests run: 0` | Test execution | Surefire/Gradle reports, skip flags |
| Test FAILS expected 201 actual 200 | Producer response | Controller/advice, business logic, assertions |
| Test PASSES despite mutating producer code | Fake base/weak matchers | Test path, mocks, `byType`/`byRegex` |
| Stub JAR missing mapping | Packaging | Generated outputs, classifier, `jar tf` |
| Mapping references missing `bodyFileName` | Packaging/resources | Inspect `__files` inside JAR |
| Stub Runner fails to start, artifact 404 | Resolution | Repo/classifier/version/credentials |
| Consumer gets 404 while Stub Runner runs | Request matching | Journal, `bodyPatterns`, headers, URL |
| Consumer gets wrong stub response | Priority/state/extension | Matched stub ID, overlapping mappings |
| Consumer gets 200 yet parse fails | Response schema/client DTO | Raw JSON, `Content-Type`, deserializer |
| Consumer sees old artifact | Cache/version | Timestamped SNAPSHOT, digest, server startup |
| Empty request journal | Wrong server/journal disabled/mocked client | Port, request journal config, client URL |
| E2E FAILS despite passing contracts | Runtime integration | Network/auth/DB/broker/config differing from tests |
| Rerun PASSES with no code change | Flakiness/state/cache | Test isolation, deterministic data, resolver |

**This matrix is a diagnostic starting point, not a final diagnosis.** Conclude only with evidence from the exact layer.

## 41. Logging and Protecting Sensitive Data During Investigation

Raw HTTP traffic speeds up debugging yet risks exposing sensitive data:

- Never print `Authorization`, access tokens, session cookies, API keys, or passwords in CI logs.
- Never log payloads containing PII or real customer accounts; use synthetic test fixtures.
- When enabling RestAssured/WebClient/Feign logging, configure redaction before raising log levels.
- For request journals/near misses, emit only diagnostic fields: method, normalized path, allowed headers, schema-safe bodies.
- Never expose WireMock Admin APIs to the public internet; restrict to authorized test networks.
- Use correlation IDs carrying no sensitive identifiers.
- Retain logs/reports with commits, artifact digests, and test names for audits without keeping raw secrets.
- Disable diagnostic verbosity or cap retention once the incident closes.

**More logs do not automatically produce better diagnoses.** Logging the right four layers, linked to the same candidate identity and with secrets redacted, provides real evidence.

## 42. Four-Layer Diagnostic Report Template

When an incident recurs between producer and consumer teams, use a structured report instead of scattered screenshots:

~~~yaml
incident:
  id: CONTRACT-INCIDENT-017
  scenario: create_reservation_sku123
  symptom: Consumer received unmatched HTTP 404
  environment: checkout-ci

source:
  producerService: reservation-service
  producerCommit: a1b2c3d4
  contractRevision: a1b2c3d4
  contractPath: contracts/reservation/create-reservation.groovy

generatedProducerTest:
  class: NAME_FROM_ACTUAL_GENERATION
  executed: COUNT_FROM_TEST_REPORT
  result: PASS_OR_FAIL
  baseTest: BASE_CLASS_NAME

stubArtifact:
  coordinates: com.example:reservation-service:1.4.0-rc.pr173.a1b2c3d4:stubs
  publishedSha256: PRODUCER_CI_DIGEST
  resolvedSha256: CONSUMER_CI_DIGEST
  mappingName: MAPPING_FROM_JAR
  loadedByWireMock: TRUE_OR_FALSE

wireRequest:
  method: POST
  path: /api/reservations
  contentType: application/json
  jsonBody: '{"productCode":"SKU-123","quantity":"2"}'
  matchedStubId: NONE_OR_REAL_ID
  actualHttpStatus: 404

diagnosis:
  firstDivergence: Consumer wire body differs from contract
  owner: checkout-team
  correction: Align request DTO and serializer with contract
  regressionTest: Require negative request with wrong field/type
~~~

All `NAME_FROM_*`, `COUNT_FROM_*`, `*_DIGEST`, and `TRUE_OR_FALSE` identifiers are **placeholders**. Never invent `PASS` or mapping IDs if the pipeline has not captured evidence.

A good report identifies the **first divergence**, **who owns that layer**, and **which test will guard against recurrence**. For multi-consumer systems, record the exact consumer version/commit rather than just `checkout-service`.

## 43. Rapid Triage Workflow in an Investigation Session

A practical sequence when a developer first sees Checkout tests turn red:

| Step | Action | If Evidence Is Missing |
|---|---|---|
| 1 | Read failing test name and stack trace | Inspect runner report; do not guess |
| 2 | Pin producer commit and contract revision | Pause compatibility conclusions |
| 3 | Read contract scenario | Confirm method/URL/headers/body |
| 4 | Open generated producer Java test | Inspect assertions and base wiring |
| 5 | Confirm executed tests > 0 | Fix generation/runner first |
| 6 | Open mapping inside **resolved JAR** | Fix artifact resolution/packaging |
| 7 | Fetch request journal from exact WireMock port | Fix client/server routing or enable diagnostics |
| 8 | Compare raw request against mapping and contract | Pinpoint first divergence |
| 9 | Inspect response/matched mapping | Check priority, fallbacks, scenario state |
| 10 | Add negative regression test, then fix | Rerun exact candidate, save report |

**Do not keep rerunning until green.** If every run hits a different SNAPSHOT or stateful WireMock server, PASS/FAIL outcomes are no longer comparable.

## 44. CI Guard: All Four Layers Must Link to the Same Candidate

A minimal quality gate should require:

~~~text
contract_revision_known
AND generated_producer_tests_executed > 0
AND producer_contract_tests_passed
AND produced_stubs_jar_exists
AND mapping_scenarios_present
AND published_sha256 == resolved_sha256
AND stub_runner_loaded_expected_artifact
AND consumer_tests_executed > 0
AND consumer_tests_passed
AND consumer_client_used_real_http_or_message_adapter
~~~

This is **policy pseudocode**, not a built-in SCC API.

In a release gate, add risk-based checks: supported consumer matrix, security, migration readiness, environment approvals, canaries. **Passing tests and deployment authorization are not the same thing.**

### When Using SNAPSHOTs

With mutable `1.4.0-SNAPSHOT`, capture resolved timestamps/digests and provenance. If an artifact cannot be verified, mark it `STALE/UNKNOWN` instead of defaulting to PASS. A consumer job passing against stub A proves nothing about candidate B.

### When Tests Are Skipped

Always inspect actual test reports. `BUILD SUCCESS` with **0 generated tests** never counts as producer-verified. A job missing reports or reusing an older build's report is also not evidence.

## 45. Hands-on Exercise A — Inspect Each Layer in an HTTP Scenario

**Goal:** complete the four-layer comparison table with a valid request.

1. Create a Groovy POST `/api/reservations` contract with `sku=SKU-123`, `quantity=2`, `X-Request-Id=req-1001`.
2. Implement the real producer controller/service and seed fixtures to return 201.
3. Configure the SCC plugin and generate producer tests.
4. Open the generated Java test; record method, URL, request JSON, and response assertions.
5. Run generated tests; confirm **executed count > 0** and PASS.
6. Open the generated WireMock mapping; record `bodyPatterns`, headers, and response.
7. Package the stubs JAR; confirm the mapping exists inside the JAR.
8. Start Stub Runner with that candidate JAR; record port and digest.
9. Send a valid request via Checkout's real client; compare journal and response.
10. Build a contract → generated Java → mapping → raw request table and record your conclusion.

**Deliverables:** four-layer table, producer test report, mapping JSON, artifact digest, and consumer test report.

## 46. Hands-on Exercise B — Diagnose Wrong Request Body Types

**Goal:** trace why the consumer receives unmatched 404 while producer tests PASS.

1. Keep the contract requiring `{"sku":"SKU-123","quantity":2}`.
2. On an experimental branch, make Checkout's DTO send `{"productCode":"SKU-123","quantity":"2"}`.
3. Run consumer tests against the candidate Stub Runner and record the HTTP status.
4. Open the exact WireMock server's journal; confirm the malformed raw body.
5. Inspect the mapping: does it enforce field `sku` and numeric type?
6. If the mapping fails to enforce types, update the **contract matcher** rather than hand-editing output JSON.
7. Regenerate the JAR and pin the candidate version.
8. With the broken request, tests must **not mistakenly receive happy-path 201**.
9. Fix the DTO/serializer, rerun the real consumer client, and confirm tests PASS.
10. Record request bytes, mapping diff, candidate digest, and test output.

**Do not treat every unmatched 404 as a business NotFound.** This is a request-matching failure unless the contract explicitly matches a business error scenario.

## 47. Hands-on Exercise C — Catch Fake Producer Tests and Stale Stubs

**Goal:** confirm neither producer nor consumer produces false greens.

1. Build a producer base test invoking the real Spring context/implementation.
2. Verify generated contract tests pass.
3. Intentionally change producer response status `201→200` in an experimental branch; tests must FAIL.
4. If they still PASS, inspect generated assertions, fake/mock base wiring, and executed test counts.
5. Restore the implementation.
6. Build a new candidate stubs JAR and record its SHA-256.
7. In consumer tests, intentionally point to an older version/digest.
8. Provenance checks must catch the candidate mismatch.
9. Rerun with the new artifact and confirm the server loaded the right mappings.
10. Write a report separating **producer verification** from **consumer compatibility**.

**Deliverables:** evidence of the failing mutation, before/after resolved JAR digests, and Stub Runner instance logs.

## 48. Hands-on Exercise D — Message Contracts Without HTTP Request Journals

**Goal:** apply the same four-layer principle to messaging.

1. Write a `ReservationCreated` message contract with label, trigger, destination, headers, and payload.
2. Generate producer message tests and inspect Java assertions.
3. Ensure the trigger calls the real production use case rather than sending a hardcoded payload.
4. Inspect output messages in the test binder/verifier, including routing/destination and headers.
5. Build/publish the versioned messaging stub artifact.
6. Have the real consumer listener/handler process the corresponding contract message.
7. Intentionally mutate `eventType` or `quantity` number→string; tests must catch it.
8. Add broker integration tests if partition, ordering, or DLQ semantics need checking.
9. Record provenance linking contract revision, producer output, stub message, and consumer handler result.
10. Separate errors across generated tests, message routing/test binder, and handler deserialization.

**Never apply HTTP 404/journal assumptions mechanically** to message brokers; use message capture, headers, payload, and destination evidence instead.

## 49. Diagnostic Checklist Before Concluding

- [ ] Verified the exact **contract scenario/path/revision** under test.
- [ ] Read method, path, query, headers, body, and matchers in Groovy/YAML.
- [ ] Did not confuse contract YAML with WireMock JSON mappings.
- [ ] Generated Java producer test matches contract and uses the right adapter/test mode.
- [ ] Producer base test calls the real implementation, not a fake controller returning canned bodies.
- [ ] Generated tests actually executed (`executed count > 0`), unskipped.
- [ ] Compared expected vs. actual producer response status, headers, and JSON body.
- [ ] Stubs JAR carries the right classifier and artifact version.
- [ ] Read generated mapping from the **JAR the consumer actually uses**, not just `target`.
- [ ] Every `bodyFileName` has its corresponding file inside the artifact.
- [ ] For SNAPSHOTs, resolved timestamp/digest recorded and compared against producer candidate.
- [ ] Stub Runner server loaded the right mappings with aligned startup timing.
- [ ] No custom mapping priority/fallback/transformer shadows generated mappings.
- [ ] Stateful WireMock scenarios are reset/isolated.
- [ ] Consumer tests run the **real HTTP client/message handler**, without mocking the adapter itself.
- [ ] Consumer base URL/port targets the right server.
- [ ] Raw requests verified via the right WireMock journal or client wire logs.
- [ ] Method/path/query/headers/body and JSON types compared element by element.
- [ ] WireMock unmatched 404 is not confused with a business 404 error.
- [ ] Raw HTTP responses separated from deserialized objects.
- [ ] Error code/body asserted, not just HTTP status.
- [ ] Dynamic values and request–response correlation evaluated semantically.
- [ ] Negative/mutation tests turn a key regression red.
- [ ] CI evidence ties together commit, contract revision, version, digest, and test count.
- [ ] Configs/logs expose no tokens, cookies, or production PII.
- [ ] Fixed at the **first broken layer** and rerun against an immutable candidate.
- [ ] Conclusion explicitly states what tests proved and did not prove.

## 50. Self-Check Questions

**1. Why is reading the contract source alone insufficient to debug consumer tests?**

Because generated mappings, stubs artifacts, and raw requests can diverge from the current contract due to matcher translation, stale builds, caches, customizations, or client serialization.

**2. If generated tests exist yet `Tests run: 0`, does that prove the producer is compliant?**

No. Generated tests must actually execute and PASS against the producer implementation under protection.

**3. Why doesn't a consumer Stub Runner PASS prove the real producer implementation?**

WireMock responds from contract mappings without calling real producer code. Producer verification is a separate gate.

**4. Which distinct causes can produce a 404 on a request?**

Artifact repository 404 during resolution, WireMock unmatched 404 on method/path/header/body mismatch, or a contract-defined business 404. Separate them by timing, error body/code, and journal.

**5. Why can `quantity:"2"` be a breaking change even though it resembles `quantity:2`?**

One is a JSON string, the other a JSON number. Consumers/producers may apply strict validation or different deserializer coercion.

**6. Is opening a mapping in producer `target` enough to know what Stub Runner returns?**

No. Inspect the actual JAR resolved by the consumer, its digest, runtime mappings, server startup, and any custom overrides.

**7. If the request journal is empty, does that guarantee WireMock received no request?**

Not necessarily. You may be querying the wrong server/port, journaling may be disabled, the client may be mocked, or requests never ran. Verify instance, config, and client URL.

**8. Can a `priority:1` mapping shadow a `priority:5` mapping?**

Yes, when both match the request and WireMock prioritizes lower numbers first. Check matched stub IDs and overlapping mappings.

**9. Why run negative/mutation tests when both producer and consumer tests are green?**

To prove breaking changes such as `201→200`, missing fields, or bad request bodies actually fail the suite—preventing false confidence from loose matchers, fake code, or stale artifacts.

**10. When can you conclude the fault lies in Checkout rather than the Reservation producer?**

When the contract is agreed, generated tests/mappings share the same revision, and the artifact matches, yet Checkout's raw request **violates** contract constraints—such as sending `productCode` instead of `sku`. Conclusions need evidence, not just an HTTP 404.

## 51. References

- [Spring Cloud Contract Reference](https://docs.spring.io/spring-cloud-contract/reference/): Contract Verifier, generated tests, DSL, and stubs.
- [Spring Cloud Contract — Contract DSL](https://docs.spring.io/spring-cloud-contract/reference/project-features-contract.html): requests/responses, matchers, and dynamic values.
- [Spring Cloud Contract — Stub Runner](https://docs.spring.io/spring-cloud-contract/reference/project-features-stubrunner.html): `LOCAL`/`REMOTE`, artifact resolution, and consumer tests.
- [Spring Cloud Contract — Maven](https://docs.spring.io/spring-cloud-contract/reference/project-features-maven.html): generated tests and stubs packaging.
- [Spring Cloud Contract — Gradle](https://docs.spring.io/spring-cloud-contract/reference/project-features-gradle.html): Gradle test generation and integration.
- [WireMock — Stubbing](https://wiremock.org/docs/stubbing/): mapping JSON, responses, and priorities.
- [WireMock — Request Matching](https://wiremock.org/docs/request-matching/): method/path/query/headers/body matching.
- [WireMock — Verifying](https://wiremock.org/docs/verifying/): request journal, verification, and unmatched requests.
- [WireMock — Mismatches](https://wiremock.org/docs/mismatches/): near-miss diagnostics and debugging.
- [WireMock — Stateful Behaviour](https://wiremock.org/docs/stateful-behaviour/): scenario state lifecycle.
- [WireMock — Response Templating](https://wiremock.org/docs/response-templating/): dynamic responses and template behavior.
- [Apache Maven — Introduction to Repositories](https://maven.apache.org/guides/introduction/introduction-to-repositories.html): artifact resolution and local/remote caches.
- [Gradle — Dependency Caching](https://docs.gradle.org/current/userguide/dependency_caching.html): changing/dynamic modules and refresh.
- [Martin Fowler — Consumer-Driven Contracts](https://martinfowler.com/articles/consumerDrivenContracts.html): contracts between producers and consumers.

**Version note:** Spring Cloud Contract, Groovy/YAML DSL, generated test adapters, test output directories, Stub Runner, and WireMock mapping/Admin API differ across Spring Boot–Spring Cloud Release Train–SCC/WireMock versions. The Java tests, file paths, JSON mappings, ports, checksums, and logs in this lesson are **illustrative examples**, not actual output executed on a real system. When applying this, inspect the **generated sources, compiled test reports, JARs, and runtime journals of the exact versions in use**. Maven, Gradle, Python, or a dedicated Content QA pass was not executed during this authoring step.

---

**Key takeaway:** Effective Spring Cloud Contract diagnosis does not start with “fixing tests to go green,” but by **cross-checking four layers: contract DSL → generated producer test → WireMock mapping/stubs artifact → actual consumer request/response**. Pin them to the same revision and artifact digest, locate the **first broken layer**, fix the right owner, and run negative/mutation tests to ensure an incompatible change is genuinely caught in CI.
