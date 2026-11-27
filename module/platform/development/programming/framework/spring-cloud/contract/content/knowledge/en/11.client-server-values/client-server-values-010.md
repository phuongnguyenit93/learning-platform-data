# Reading Generated Tests and Mappings to Catch Swapped Sides

## Learning Objectives

In the **Two-Sided Values** chapter of **Spring Cloud Contract**, a Groovy/YAML contract describes an interaction between a **producer** (the service providing the API or emitting messages) and a **consumer** (the service calling the API or receiving messages). Spring Cloud Contract uses the DSL to **generate producer-side tests** and **generate stubs** for consumer testing via **Stub Runner**.

The most common confusion arises when a contract contains **dynamic values**: the same field may need a **concrete value** on one side yet a **matching rule** on the other. To know whether the DSL was understood correctly, inspect the actual **generated test** and **stub mapping** after building.

After this lesson, you will be able to:

- Accurately explain the roles of `consumer(...)` and `producer(...)` in **request** and **response** in Groovy DSL.
- Predict **which value** the producer test will send, **what it will assert**, and **how the stub will match requests** and **what response it will return**.
- Locate generated test files, WireMock mappings, and stub artifacts after running Spring Cloud Contract with Maven or Gradle.
- Compare the source DSL against both outputs to catch swapped sides, overly broad regexes, type-mismatched fixtures, or wrong stub versions.
- Apply equivalent thinking to **YAML DSL**, and integrate checks into CI to detect incompatible API changes.

## 1. Why Does One Contract Have Two Views?

Suppose **Checkout Service** is the consumer sending a reservation creation request to **Reservation Service**, the producer:

~~~http
POST /api/reservations HTTP/1.1
Content-Type: application/json
Accept: application/json

{
  "requestId": "REQ-1001",
  "sku": "SKU-101",
  "quantity": 1
}
~~~

Producer returns:

~~~http
HTTP/1.1 201 Created
Content-Type: application/json

{
  "reservationId": "RSV-98241",
  "accepted": true
}
~~~

Both `requestId` and `reservationId` can vary between interactions. The consumer must be allowed to send **different valid requestIds**; the producer test needs **one concrete request** to actually invoke the application. Conversely, the producer is allowed to generate many valid `reservationId` values; the consumer test needs **one concrete, stable response** from the stub to test its logic.

Spring Cloud Contract solves this difference using **two-sided values**. In **Groovy DSL**, the pair:

~~~groovy
$(consumer(...), producer(...))
~~~

expresses the same field from both sides' perspectives. The function names indicate **roles in the contract**, yet **how outputs use them differs depending on whether the field is in the request or response**.

### The Most Important Rule Table

| Where Declared | What Is `consumer(...)` Used For? | What Is `producer(...)` Used For? |
|---|---|---|
| **Request** | Rule/value **the stub uses to accept requests from consumer** | Concrete value that the **generated producer test sends** to producer |
| **Response** | Concrete value that the **stub returns to consumer** | Rule/value that the **generated producer test uses to assert the real response** |

Read the table by **concrete actions** instead of mechanically memorizing "consumer is client, producer is server". Specifically, `consumer(...)` appearing in **response** still governs *the stub's response*, even though in live communication the response is sent by the producer.

~~~mermaid
flowchart TB
    D["Contract DSL<br/>consumer(...) / producer(...)"] --> T["Generated producer test"]
    D --> M["WireMock stub mapping"]
    T --> TR["Request from producer(...) side"]
    T --> TA["Assert response per producer(...)"]
    M --> MR["Match request per consumer(...)"]
    M --> MS["Return response per consumer(...)"]
~~~

**Easy rule to remember:** the generated test needs a request to *send* and an expectation to *verify*; the stub needs a condition to *accept a request* and a response to *return*. The two tools have different jobs, so they use different sides of the same contract.

## 2. Complete Groovy DSL Example

In a producer configured with Spring Cloud Contract, create a file such as `src/test/resources/contracts/reservations/createReservation.groovy`:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    description 'Create reservation with valid requestId'

    request {
        method 'POST'
        url '/api/reservations'

        headers {
            contentType(applicationJson())
            accept(applicationJson())
        }

        body(
            requestId: $(
                consumer(regex('REQ-[0-9]{4}')),
                producer('REQ-1001')
            ),
            sku: 'SKU-101',
            quantity: 1
        )
    }

    response {
        status 201

        headers {
            contentType(applicationJson())
        }

        body(
            reservationId: $(
                consumer('RSV-1001'),
                producer(regex('RSV-[0-9]+'))
            ),
            accepted: true
        )
    }
}
~~~

Read the two dynamic value pairs by position:

**In the request:**

~~~groovy
requestId: $(
    consumer(regex('REQ-[0-9]{4}')),
    producer('REQ-1001')
)
~~~

- The stub will accept a request whose `requestId` matches `REQ-` plus four digits, e.g., `REQ-4321`.
- The generated test will actually send `"requestId":"REQ-1001"` to the producer.
- Seeing only the regex in the DSL file and believing the generated test sends **the regex string** means you mixed up the sides.

**In the response:**

~~~groovy
reservationId: $(
    consumer('RSV-1001'),
    producer(regex('RSV-[0-9]+'))
)
~~~

- The stub returns `"reservationId":"RSV-1001"` so the consumer has a stable response.
- The generated test verifies that the real response has a `reservationId` matching `RSV-[0-9]+`, e.g., `RSV-98241`.
- Assuming the real producer must always return exact `RSV-1001` simply because that is the `consumer(...)` value means you misunderstood the DSL.

`sku` and `quantity` have no dynamic value pairs, so they stay fixed examples in both outputs. `accepted` is a boolean; do not turn it into the string `"true"` if the consumer expects a boolean type.

**Note:** the example above intentionally tests only one valid scenario. For malformed requests, quantity equal to 0, or non-existent SKUs, create separate contracts/test scenarios if the consumer depends on those branches.

## 3. Inspecting the Generated Producer Test: Actual Request and Assertions

After configuring the plugin and running the test-generation step, Spring Cloud Contract generates test code from the DSL. Paths depend on the build tool, plugin, and configuration, but commonly look like:

~~~text
# Maven (common configuration)
target/generated-test-sources/contracts/

# Gradle (common configuration)
build/generated-test-sources/contracts/
~~~

Class names, test framework (RestAssured, MockMvc, WebTestClient, and variants), imports, matchers, and output locations can differ by Spring Cloud Contract version. Therefore, **open the actual generated Java/Groovy test file in your project** instead of assuming the output is identical to examples in docs.

### Shape of the Generated Test to Recognize

An illustrative behavior-level reading of a test might look like (**pseudocode describing steps, not a verbatim copy from a specific generator version**):

~~~text
TEST "createReservation":
  GIVEN
    POST /api/reservations
    Content-Type: application/json
    Accept: application/json
    request body:
      requestId = "REQ-1001"
      sku       = "SKU-101"
      quantity  = 1

  WHEN
    send request to real producer test environment

  THEN
    HTTP status = 201
    Content-Type = application/json
    response.accepted = true
    response.reservationId MATCHES "RSV-[0-9]+"
~~~

Look for two exact facts:

1. **The generated request has sample value `REQ-1001`** from the `producer(...)` side of the DSL, not the regex from `consumer(...)`.
2. **The response assertion checks regex `RSV-[0-9]+`** from the `producer(...)` side, rather than forcing the producer to always return `RSV-1001`.

Example Java snippet illustrating the **assertion intent**, not line-for-line code guaranteed by the generator:

~~~java
// Illustration of what to look for when reading the generated test:
String sentRequestId = "REQ-1001";
int expectedStatus = 201;

assertThat(actualStatus).isEqualTo(expectedStatus);
assertThat(actualBody.get("accepted")).isEqualTo(true);
assertThat((String) actualBody.get("reservationId"))
        .matches("RSV-[0-9]+");
~~~

The producer test requires a **base test class/test configuration** and proper background data to hit the real implementation. If the test environment generates a different ID each run while matching the regex, the contract test passes validly. If the regex is too loose (such as `.*`), the test fails to catch meaningless IDs; that is a contract-quality issue, not a generator bug.

### Signs of Swapped Sides Right Inside the Generated Test

| Observation When Reading Test | Interpretation | Action |
|---|---|---|
| Test sends `REQ-1001` | Matches designed example | Proceed to check response assertions |
| Test tries to send literal string `REQ-[0-9]{4}` as normal data | Likely swapped values or misplaced matcher | Re-check `request.body.requestId` and how the generator converts values |
| Test asserts response ID **equals exact `RSV-1001`** | Contract is locking down a fixed value | If ID is dynamic, review `response` and producer-side matcher |
| Test only asserts ID exists or matches any string | Rule is too loose | Write a matcher describing the format/semantics consumer needs |
| Test ignores `accepted` field that consumer relies on | Contract or verification step is incomplete | Review DSL, configuration, and generated test |
| Test fails even though response is valid outside fixture | Constraints may be overly rigid | Separate stub example from producer rule using two-sided values |

**Never edit generated tests directly to "fix bugs".** When tests are regenerated on the next build, those edits vanish. Fix the source DSL, fixture data, or test-generation config, then regenerate and inspect the new output.

## 4. Inspecting the Stub Mapping: Request Matcher and Returned Response

On the consumer side, Spring Cloud Contract typically generates **WireMock mappings** as part of the stub artifact. When **Stub Runner** downloads and starts the artifact, mappings define which requests are accepted and which responses are returned.

Typical output locations to check:

~~~text
# Maven, a common layout:
target/stubs/META-INF/<groupId>/<artifactId>/<version>/mappings/
target/<artifactId>-<version>-stubs.jar

# Gradle, a possible layout:
build/stubs/META-INF/<groupId>/<artifactId>/<version>/mappings/
~~~

No need to guess exact JSON filenames. Check plugin output, or inspect the contents of `*-stubs.jar` and the `mappings` folder inside it. If your project uses custom paths or a different plugin version, take the location **from your actual build**.

### What Does a WireMock Mapping Look Like?

Below is a **simplified mapping illustrating semantics**, not a claim that the generator always emits the exact same keys, ordering, or expressions:

~~~json
{
  "request": {
    "method": "POST",
    "url": "/api/reservations",
    "headers": {
      "Content-Type": {
        "contains": "application/json"
      }
    },
    "bodyPatterns": [
      {
        "matchesJsonPath": "$[?(@.requestId =~ /REQ-[0-9]{4}/)]"
      }
    ]
  },
  "response": {
    "status": 201,
    "headers": {
      "Content-Type": "application/json"
    },
    "jsonBody": {
      "reservationId": "RSV-1001",
      "accepted": true
    }
  }
}
~~~

In actual mappings, the generator may use `matchesJsonPath`, `equalToJson`, string bodies, `jsonBody`, or other WireMock matchers; it may also include conditions for `sku` and `quantity`. **What must be verified is behavior**, not one single JSON syntax:

- **Request matcher:** does it accept `requestId` matching `REQ-[0-9]{4}`? Does it check the right method, URL, headers, and key fields?
- **Response:** does it return `201`, `reservationId: "RSV-1001"`, and `accepted: true`?
- **Data type:** is `accepted` truly a JSON boolean, or accidentally serialized as a string?
- **Specificity:** does the mapping accidentally match requests belonging to other contracts?

In this example, the consumer test can send `REQ-4321`. If the stub is right, the response still carries `RSV-1001`. That is **not a producer bug**: the stub intentionally returns a fixture so the consumer can test its handling branch, while the generated producer test verifies the real implementation.

### Quick Comparison Table

| Question | Read Generated Test | Read Stub Mapping |
|---|---|---|
| What must request `requestId` look like? | Sends `REQ-1001` | Matches `REQ-[0-9]{4}` |
| What must response `reservationId` look like? | Asserts regex `RSV-[0-9]+` | Returns sample `RSV-1001` |
| What type must `accepted` be? | Asserts boolean `true` | Returns boolean `true` |
| Which endpoint is called? | Calls `POST /api/reservations` | Matches `POST /api/reservations` |
| Is the test calling the real application? | Yes, if the producer test environment is configured properly | No; stub simulates response |

This is why you must **read both outputs**: a green producer test alone does not confirm the consumer can call the stub as intended, and a valid stub mapping does not prove the real producer complies with the contract.

## 5. Four Places Where Values Are Easily Swapped and Their Symptoms

Use this table when reviewing pull requests containing `consumer(...)` / `producer(...)`:

| Location in DSL | Correct: Consumer Side | Correct: Producer Side | Symptoms When Swapped or Misused |
|---|---|---|---|
| Request path / query | Pattern accepted by stub | Concrete path / query sent by generated test | Stub matches only one hardcoded path, or test sends a regex as the path |
| Request header | Pattern/value checked by stub | Concrete header sent by test | Dynamic header fails to match stub, or test sends invalid value |
| Request JSON/body | Pattern/value accepted by stub | Concrete body sent by test | Stub rejects valid requests; producer test fails to build valid sample data |
| Response body / header | Concrete value returned by stub | Matcher/value asserted by test | Stub returns regex string instead of ID; test wrongly asserts one fixed ID |

Some DSL/generator versions include checks that reject combinations unable to produce stubs/tests, or auto-generate sample values with certain constraints. Thus, **never mechanically assume** every side-swapping error produces one specific output failure. The surest confirmation is **regenerating tests and mappings and inspecting the actual files**.

### Case A: Request Puts Regex on the Producer Side

~~~groovy
// Does not fit the goal "test sends a concrete requestId".
requestId: $(
    consumer('REQ-1001'),
    producer(regex('REQ-[0-9]{4}'))
)
~~~

This can cause the stub to accept only a fixed ID instead of all properly formatted IDs; meanwhile the generated test lacks the intended concrete request value or depends on how the generator handles regexes. If the consumer needs to send many requestIds, use:

~~~groovy
requestId: $(
    consumer(regex('REQ-[0-9]{4}')),
    producer('REQ-1001')
)
~~~

### Case B: Response Puts Regex on the Consumer Side

~~~groovy
// Does not fit the goal "stub returns a stable sample ID".
reservationId: $(
    consumer(regex('RSV-[0-9]+')),
    producer('RSV-1001')
)
~~~

The stub needs **concrete response data** to return, while the producer test needs to verify dynamic ID format. A better contract:

~~~groovy
reservationId: $(
    consumer('RSV-1001'),
    producer(regex('RSV-[0-9]+'))
)
~~~

### Case C: Data-Type Confusion After Switching DSL

~~~yaml
# If accepted is boolean per contract:
body:
  reservationId: 'RSV-1001'
  accepted: true
~~~

Differs from:

~~~yaml
# accepted is now string "true" in YAML:
body:
  reservationId: 'RSV-1001'
  accepted: 'true'
~~~

Even when tests and stubs generate cleanly, a `boolean -> string` type change can break consumer deserialization. When reading mappings, check whether response JSON has `true` or `"true"`. When reading generated tests, check which type the assertion expects.

### Case D: Overly Broad Request Matcher, Overlapping Mappings

Suppose two contracts both match `POST /api/reservations` and differ only in `accepted=true` versus `accepted=false`, while both request matchers accept any body. Stub Runner/WireMock cannot tell which scenario the author intended from that request alone. One mapping will "swallow" requests meant for the other.

The fix is giving each scenario's request **a meaningful distinguishing condition** (SKU code, status field, header, or interface-valid body). Never rely on mapping load order as an accidental way to pick responses.

## 6. YAML DSL: Reading `matchers` Instead of Groovy Value Pairs

In **YAML DSL**, the same two-sided idea is usually expressed via **sample values in `body`** and **matchers in `request.matchers` / `response.matchers`**.

A YAML example equivalent in intent for creating a reservation:

~~~yaml
description: 'Create reservation with valid requestId'
request:
  method: POST
  url: '/api/reservations'
  headers:
    Content-Type: 'application/json'
    Accept: 'application/json'
  body:
    requestId: 'REQ-1001'
    sku: 'SKU-101'
    quantity: 1
  matchers:
    body:
      - path: '$.requestId'
        type: by_regex
        value: 'REQ-[0-9]{4}'
response:
  status: 201
  headers:
    Content-Type: 'application/json'
  body:
    reservationId: 'RSV-1001'
    accepted: true
  matchers:
    body:
      - path: '$.reservationId'
        type: by_regex
        value: 'RSV-[0-9]+'
~~~

**Do not mistakenly believe every matcher runs on both sides:**

- `request.body.requestId: 'REQ-1001'` is the **concrete sample value** sent by the generated producer test.
- `request.matchers.body` is the **rule the stub uses to match consumer requests**.
- `response.body.reservationId: 'RSV-1001'` is the **concrete value returned by the stub**.
- `response.matchers.body` is the **rule the generated producer test uses to check the real producer response**.

Comparison:

| YAML DSL | Corresponding Intent in Groovy DSL |
|---|---|
| `request.body.requestId` | Value `producer('REQ-1001')` in request |
| `request.matchers.body` | Rule `consumer(regex(...))` in request |
| `response.body.reservationId` | Value `consumer('RSV-1001')` in response |
| `response.matchers.body` | Rule `producer(regex(...))` in response |

JSONPaths `$.requestId` and `$.reservationId` must point to exact fields in JSON. Even a typo in the path can stop the matcher from checking what the author thinks is protected. Valid YAML alone is not enough; the generator must accept the **DSL schema of the active Spring Cloud Contract version**.

## 7. Reading Outputs Step by Step: A Repeatable Inspection Workflow

When reviewing a PR that modifies dynamic values, follow this order.

### Step 1: Pick a Contract and Write Expectations Before Building

For `createReservation.groovy`, note down:

~~~text
GENERATED PRODUCER TEST EXPECTATIONS
- Sends POST /api/reservations.
- Sends requestId = REQ-1001.
- Expects HTTP 201.
- Asserts reservationId matches RSV-[0-9]+.
- Asserts accepted = true (boolean).

STUB MAPPING EXPECTATIONS
- Matches POST /api/reservations.
- Matches requestId via REQ-[0-9]{4}.
- Returns HTTP 201.
- Returns reservationId = RSV-1001.
- Returns accepted = true (boolean).
~~~

Writing expectations beforehand prevents a common cognitive trap: looking at generator output and subconsciously assuming it is whatever you intended.

### Step 2: Generate Outputs via Producer Build

Reference commands when the producer module has the plugin configured properly:

~~~bash
# Maven: generate tests per plugin config; exact goal depends on version.
./mvnw generate-test-sources

# Maven: full build/verification per configured lifecycle.
./mvnw verify

# Gradle: inspect task names provided by the plugin.
./gradlew tasks --all
~~~

Exact goal/task names, whether stubs are built before or after tests, and output directories depend on the plugin. Use **the producer module's build log** as confirmation. Never assume success just because a process exits 0 when the plugin was not configured to read contracts.

### Step 3: Read the Generated Test

Locate the file matching the contract name. Confirm method, URL, request headers/body, status, and response assertions. If the test sends a string looking like a regex instead of a valid example, go back to the DSL and separate `consumer(...)` / `producer(...)`.

Specifically verify assertions:

- JSON types: string, number, boolean.
- Does the regex protect the exact format?
- Are required fields needed by the consumer checked?
- For error statuses, are the right status/error code asserted?
- For dynamic data, was a fixed ID or timestamp accidentally locked down?

### Step 4: Read the Stub Mapping

Find the contract's JSON mapping (usually under `mappings` inside the stub artifact). Confirm:

- `request.method`, path/path pattern, headers.
- Body/query rules fit what the consumer actually needs to send.
- `response.status`, headers, and concrete sample body.
- Do other contracts have duplicate or overlapping mapping conditions?

A mapping can be syntactically valid yet **fail to match real consumer requests** due to differences in path, headers, regex, or body type. That is a common cause of WireMock's "no matching stub mapping" response.

### Step 5: Run Consumer Tests with the Exact Artifact

The consumer uses Stub Runner to download/start the generated stub, then calls it with the **application's real HTTP client**. For instance, tests should verify that upon receiving `RSV-1001`, Checkout can read `reservationId` and persist/display the result without relying on a hardcoded value inside the app.

If the consumer test accidentally calls the real producer or uses an old stub version, a passing test **does not prove the contract in the PR is compatible**.

### Step 6: Record Conclusions in the PR

Record:

- DSL commit/revision.
- Which generated tests were inspected and producer test results.
- Which mappings are in the stub artifact, coordinates/version, and notable matching conditions.
- Which consumer tests ran against that exact artifact.
- Compatible or incompatible changes detected.

This report lets reviewers decide based on concrete evidence rather than eyeballing Groovy/YAML files.

## 8. When "Tests Are Green" Yet the Contract Is Still Wrong

Distinguish these verification levels:

| Evidence | What It Proves | What It Does Not Necessarily Prove |
|---|---|---|
| DSL parses cleanly | File is read and understood by tool at syntax/schema level | Two-sided role assignment matches intent |
| Generated test is produced | Plugin generated test code | Assertions are tight enough or test actually ran |
| Generated producer test passes | Producer satisfies cases described by the new contract | Older consumers remain compatible |
| WireMock mapping exists | Stub has simulation configuration | Real consumer requests will match |
| Consumer test with stub passes | Consumer parses and handles responses from **the stub used** | Real producer obeys contract or stub is the latest build |
| Both sides pass on same revision | Evidence for behaviors covered | Every business rule, boundary error, and production environment holds |

**An especially dangerous bug:** an author updates both the contract and producer implementation, producer tests pass, yet the new contract changed `reservationId` from string to number. Older consumers deserializing as string will break. Check compatibility and run consumer tests against the **candidate stub**, rather than looking only at producer test results.

## 9. Practice Exercise: Spotting Swapped Sides in a PR

A PR for `POST /api/reservations` contains the following Groovy snippet:

~~~groovy
request {
    method 'POST'
    url '/api/reservations'
    headers {
        contentType(applicationJson())
    }
    body(
        requestId: $(
            consumer('REQ-1001'),
            producer(regex('REQ-[0-9]{4}'))
        )
    )
}

response {
    status 201
    headers {
        contentType(applicationJson())
    }
    body(
        reservationId: $(
            consumer(regex('RSV-[0-9]+')),
            producer('RSV-1001')
        )
    )
}
~~~

Real business requirements:

- The consumer can send any `requestId` formatted as `REQ-` and exactly four digits.
- The producer test must send a concrete `requestId` such as `REQ-1001`.
- The real producer is allowed to generate many `reservationId` values matching `RSV-[0-9]+`.
- The stub must return a stable `RSV-1001` for consumer tests.

**Questions:**

1. How many places have swapped sides?
2. What symptoms can appear in the generated producer test and stub mapping?
3. How should the DSL be fixed so both outputs meet the requirements?

### Answer and Reasoning

**Two places are reversed**: `request.requestId` and `response.reservationId`.

Fixed version:

~~~groovy
request {
    method 'POST'
    url '/api/reservations'
    headers {
        contentType(applicationJson())
    }
    body(
        requestId: $(
            consumer(regex('REQ-[0-9]{4}')),
            producer('REQ-1001')
        )
    )
}

response {
    status 201
    headers {
        contentType(applicationJson())
    }
    body(
        reservationId: $(
            consumer('RSV-1001'),
            producer(regex('RSV-[0-9]+'))
        )
    )
}
~~~

**Reading expected outputs after fixing:**

| Check | Correct Outcome |
|---|---|
| Generated test sends request | `requestId = REQ-1001` |
| Generated test checks response | `reservationId` matches `RSV-[0-9]+` |
| Stub request matcher | Accepts `REQ-1001`, `REQ-4321`, and other valid values of the same pattern |
| Stub response | Returns `reservationId = RSV-1001` |

If generated tests do not match the table, verify the actual DSL file scanned by the plugin, version, matchers, and override configurations before blaming a generator bug.

### Try One More YAML Scenario

~~~yaml
request:
  method: POST
  url: '/api/reservations'
  body:
    requestId: 'REQ-1001'
  matchers:
    body:
      - path: '$.requestId'
        type: by_regex
        value: 'REQ-[0-9]{4}'
response:
  status: 201
  body:
    reservationId: 'RSV-1001'
  matchers:
    body:
      - path: '$.reservationId'
        type: by_regex
        value: 'RSV-[0-9]+'
~~~

Answer yourself: does `request.matchers` go into the **generated test** or the **stub mapping**? Which side's value does `response.matchers` verify?

**Answer:** `request.matchers` defines matching on the **stub**; `response.matchers` defines assertions in the **generated producer test**. Request and response bodies hold concrete examples for the opposite sides.

## 10. Review Checklist When Reading Generated Tests and Mappings

- [ ] Confirmed the exact DSL file, revision, and Spring Cloud Contract version used by the build.
- [ ] For **requests**, generated test sends **concrete producer value**; stub matches by **consumer value/rule**.
- [ ] For **responses**, generated test asserts by **producer value/rule**; stub returns **concrete consumer value**.
- [ ] Regexes enforce proper formats without accidentally widening to `.*`.
- [ ] JSON types of key fields are preserved (string, number, boolean, null, array/object).
- [ ] Header, URL, query, and body matchers are not omitted or overlapping across contracts.
- [ ] Generated tests actually run against a producer test environment with controlled state.
- [ ] Stub artifact contains the inspected mapping and is published with a traceable version.
- [ ] Consumer tests call the right Stub Runner port and run the real client against **the same candidate stub**.
- [ ] Changes risking breakage for older consumers have been evaluated with a migration plan.
- [ ] CI stores evidence of producer tests, stub artifacts, and consumer tests tied to the same revision.

## 11. Key Takeaways

When using two-sided values in **Spring Cloud Contract**, never guess behavior solely from the names `consumer(...)` / `producer(...)` in isolation. **In requests:** the stub uses the consumer side to match, while the generated producer test sends the producer side. **In responses:** the stub returns the consumer side, while the generated test verifies the producer side. With **YAML DSL**, sample values in `body` pair with `request.matchers` / `response.matchers` under the corresponding rule.

The surest way to catch mix-ups is **reading both the generated test and the WireMock stub mapping produced from the same revision**, then running producer and consumer tests with the exact stub version. Bringing this cross-check into reviews and CI lets teams catch swapped values, broken matchers, type mismatches, and incompatible API changes before release.
