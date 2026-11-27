# Extracting Large Body Payloads into Resource Files

## 1. Context: Why Shouldn't Every Payload Be Embedded Inline in the Contract?

In **Spring Cloud Contract (SCC)**, a contract describes a communication commitment between a **producer** and a **consumer**: which request is accepted, which response is returned, or which message is emitted. Contracts can be written in **Groovy DSL** or **YAML DSL**. SCC uses contracts to generate producer-side tests and produce stubs for consumers to verify via **Stub Runner**. A CI pipeline can run both sides to detect incompatible API changes early.

Early on, a response with just a few fields is often written inline in the DSL:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    request {
        method GET()
        url '/api/inventory/SKU-123'
    }
    response {
        status OK()
        headers {
            contentType(applicationJson())
        }
        body(
            sku: 'SKU-123',
            available: true,
            quantity: 12
        )
    }
}
~~~

This approach is short and readable. However, if a response spans hundreds of lines of JSON, contains deeply nested arrays, localized text, or complex message structures, the **behavioral** part of the contract becomes obscured by **sample data**. Reviewers have a hard time seeing whether an actual change is in the path, status, headers, data types, or merely a single value inside the body.

One solution is to put the body into a **separate resource file** and have the contract **reference** that file. Then the DSL keeps describing the communication rules while the resource file holds the concrete payload. Crucially, both parts must still be reviewed and tested together.

### Learning Outcomes

After this lesson, you will be able to:

1. Decide when to keep a body inline in the DSL and when to extract it to a separate file.
2. Organize contracts and JSON/XML/text fixtures in a structure that is easy to locate and review.
3. Use **Groovy DSL** with `file(...)` and **YAML DSL** with `bodyFromFile`.
4. Distinguish a file holding **static example data** from **body matchers** used for dynamic values.
5. Verify paths, contents, generated producer tests, stub artifacts, and consumer tests when integrating fixtures into CI.

## 2. Distinguishing Contracts, Payload Fixtures, and Matchers

Three related concepts have distinct responsibilities:

| Component | What Does It Contain? | Example |
|---|---|---|
| **Contract** | Method, URL, status, headers, body reference, matchers, message destination, and trigger condition | `stock-available.groovy` or `stock-available.yml` |
| **Payload fixture** | Sample request/response/message content in JSON, XML, text, or binary bytes | `payloads/stock-available.json` |
| **Matcher** | Rules validating values that may vary while remaining valid | `transactionId` must be a valid UUID, `items` has the right data type |

For example: the contract expects GET `/api/inventory/SKU-123`, HTTP 200 response, and `Content-Type: application/json`. The fixture stores an inventory object including a list of warehouses. A matcher can allow an update timestamp field to vary without failing tests due to a hardcoded value.

A resource file **does not replace a contract**: having only JSON without DSL means SCC does not know which request triggers the stub, which HTTP status to return, or which scenario the response belongs to. Conversely, if the DSL references a non-existent file, the contract cannot be processed as expected.

## 3. When Should You Extract a Body into a File?

Consider extracting payloads when one or more of these signs appear:

- A long body forces readers to scroll through multiple screens just to see status, headers, or matchers.
- The JSON/XML object has **deep nesting**, many array elements, or multiple data branches.
- You want to view/edit payloads with a JSON/XML formatter, compare samples against a schema, or validate data with standalone tools.
- You need to manage multiple response scenarios such as **in stock**, **out of stock**, **not found**, and **business error**.
- A message has a large payload with many fields that must be verified between producer and consumer.

Conversely, if a body has only 2–3 fields and makes the contract's meaning crystal clear, keeping it inline in the DSL remains appropriate. Avoid extracting every tiny response into a separate file, as that forces reviewers to open too many files to understand a simple behavior.

**Guiding principle:** extract to improve readability and verifiability; do not extract solely to satisfy an arbitrary line-count limit.

## 4. Suggested Directory Structure

Example for **Inventory Service** using a Groovy contract and a JSON fixture:

~~~text
inventory-service/
└── src/
    └── test/
        └── resources/
            └── contracts/
                └── inventory/
                    ├── stock-available.groovy
                    ├── stock-unavailable.groovy
                    └── payloads/
                        ├── stock-available.json
                        └── stock-unavailable.json
~~~

In this example:

- `contracts/` is the directory Contract Verifier scans for contracts when the build uses the default location.
- `inventory/` groups contracts by API context or bounded context.
- `stock-available.groovy` defines the request and response for the in-stock scenario.
- `payloads/stock-available.json` stores the sample response referenced by that contract.
- If using **YAML DSL**, `stock-available.yml` can be used instead of `stock-available.groovy`. Avoid accidentally keeping both in the same directory when they merely duplicate the same scenario; build tooling may treat them as two separate contracts.

Paths inside `file(...)` or `bodyFromFile` must resolve according to the rules of your active **DSL and SCC version**. The simplest way to start is to **place fixtures in a subfolder near the contract** and use clear relative paths; verify immediately with actual test/stub generation. If a project customizes the contract location in Maven/Gradle, verify how paths resolve rather than copying blindly.

### Naming Conventions

| Recommended | Why? |
|---|---|
| `stock-available.json` | Conveys the business scenario, easy to find when a test fails |
| `stock-unavailable.json` | Clearly contrasts with the in-stock response |
| `reservation-created.json` | Tied to the API state and outcome |
| `inventory-changed-event.json` | Indicates a payload intended for a message |
| `payloads/` | Separates sample data files from contract files |

Avoid generic names like `body1.json`, `data-final.json`, or `sample-new-2.json`. Filenames should indicate **which contract and scenario the data belongs to**, not merely the file format.

## 5. Complete Example with Groovy DSL

Suppose consumer **Checkout Service** calls:

~~~http
GET /api/inventory/SKU-123 HTTP/1.1
Accept: application/json
~~~

The producer returns warehouse-level inventory data and product attributes.

### 5.1. Extracting the Body to a JSON File

Contents of **`src/test/resources/contracts/inventory/payloads/stock-available.json`**:

~~~json
{
  "sku": "SKU-123",
  "available": true,
  "quantity": 12,
  "warehouses": [
    {
      "code": "HCM-01",
      "quantity": 7,
      "priority": 1
    },
    {
      "code": "HN-02",
      "quantity": 5,
      "priority": 2
    }
  ],
  "attributes": {
    "unit": "piece",
    "allowBackorder": false,
    "tags": [
      "ready-to-ship",
      "standard"
    ]
  }
}
~~~

The advantage is that the JSON content can be formatted, validated, and reviewed as a standalone data document. The example uses a fixed value `SKU-123` for straightforward verification while showing how nested arrays and objects quickly bloat inline DSL.

### 5.2. Referencing the File in the Contract

Contents of **`src/test/resources/contracts/inventory/stock-available.groovy`**:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    description 'Checkout reads stock availability for SKU-123'

    request {
        method GET()
        url '/api/inventory/SKU-123'
    }

    response {
        status OK()
        headers {
            contentType(applicationJson())
        }

        body(file('payloads/stock-available.json'))
    }
}
~~~

Notable points:

1. `body(file('payloads/stock-available.json'))` instructs SCC to read the body from the file instead of declaring the entire object inline in the contract.
2. `status OK()` and `contentType(applicationJson())` remain in the contract because they are essential parts of HTTP behavior.
3. Fixtures sit close to the contract so reviewers see all related changes together in the same PR.
4. Request, response, and payload all belong to **the same scenario**. Do not reference an out-of-stock fixture in an in-stock contract simply because the JSON structure looks similar.

This is an **illustrative file pair**. In practice, create both the contract and the JSON file in the location configured for the plugin; adding only the JSON file without updating the DSL will not make tests use the new data.

## 6. Equivalent Approach with YAML DSL

If a team uses **YAML DSL**, SCC supports the **`bodyFromFile`** property to specify a body file, for example **`stock-available.yml`**:

~~~yaml
description: Checkout reads stock availability for SKU-123

request:
  method: GET
  url: /api/inventory/SKU-123

response:
  status: 200
  headers:
    Content-Type: application/json
  bodyFromFile: payloads/stock-available.json
~~~

Here, `bodyFromFile` serves the same role as `file(...)` in Groovy DSL. The JSON payload remains identical to the previous section.

**Syntax note:** the `bodyFromFile` field belongs to the **Spring Cloud Contract DSL**, not standard YAML self-interpretation. A plain YAML parser only reads a path string; Contract Verifier interprets that it should load the body from the file. Check the exact DSL documentation for **your active SCC version**, especially when converting between Groovy and YAML or upgrading major versions.

### Quick Comparison

| Need | Groovy DSL | YAML DSL |
|---|---|---|
| Inline JSON body | `body(...)` | `body:` |
| Body loaded from file | `body(file('payloads/stock-available.json'))` | `bodyFromFile: payloads/stock-available.json` |
| HTTP status | `status OK()` | `status: 200` |
| Content type | `contentType(applicationJson())` in `headers` | `Content-Type: application/json` in `headers` |
| Dynamic field checks | `bodyMatchers` and appropriate matchers | `matchers` configurations in YAML DSL |

A contract only needs **one** of the two formats. The two snippets above show alternative syntaxes for learning purposes and should not both exist in the project.

## 7. Extracting Both Request Body and Response Body

Not only responses—**requests with large bodies** should also be organized into fixtures when doing so improves clarity.

Suppose a service creates inventory reservations:

~~~http
POST /api/reservations HTTP/1.1
Content-Type: application/json
~~~

File `payloads/reservation-request.json`:

~~~json
{
  "requestId": "REQ-1001",
  "customerRef": "CUSTOMER-DEMO",
  "items": [
    {
      "sku": "SKU-123",
      "quantity": 2
    },
    {
      "sku": "SKU-456",
      "quantity": 1
    }
  ],
  "options": {
    "allowPartial": false,
    "warehouseRegion": "south"
  }
}
~~~

File `payloads/reservation-created.json`:

~~~json
{
  "reservationId": "RSV-1001",
  "status": "CREATED",
  "reservedItems": 2
}
~~~

Groovy contract:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    description 'Create reservation successfully'

    request {
        method POST()
        url '/api/reservations'
        headers {
            contentType(applicationJson())
        }
        body(file('payloads/reservation-request.json'))
    }

    response {
        status CREATED()
        headers {
            contentType(applicationJson())
        }
        body(file('payloads/reservation-created.json'))
    }
}
~~~

Same idea in YAML DSL:

~~~yaml
description: Create reservation successfully
request:
  method: POST
  url: /api/reservations
  headers:
    Content-Type: application/json
  bodyFromFile: payloads/reservation-request.json
response:
  status: 201
  headers:
    Content-Type: application/json
  bodyFromFile: payloads/reservation-created.json
~~~

Separating request and response lets reviewers immediately distinguish **what input the producer must accept** from **what output the producer must guarantee**. At the same time, a change making the request payload invalid can affect consumer-side stub matching; inspect both sides rather than only the response.

## 8. How Do Static Fixtures Differ from Dynamic Data?

Extracting a body into a file **does not automatically make fields in the file flexible**. If the JSON says:

~~~json
{
  "reservationId": "RSV-1001",
  "status": "CREATED"
}
~~~

then `RSV-1001` remains a concrete sample value. For a producer generating a dynamic ID on each run, a strict equality check can fail even though production behavior is valid.

Specify each category deliberately:

- **Invariant values:** e.g., `status` must be `CREATED` for the success creation scenario.
- **Constrained dynamic values:** `reservationId` is a non-empty string with a defined format; `updatedAt` is a valid timestamp.
- **Values correlated with the request:** SKU or request ID echoed back according to business logic.
- **Ordering and element sets:** when consumers depend on array order, express that constraint; otherwise consider an appropriate matcher.

In Groovy DSL, **`bodyMatchers`** can describe rules instead of forcing every run to return the exact same hardcoded ID. Example illustrating matchers inside the **response** block of the contract using the JSON above:

~~~groovy
response {
    status CREATED()
    headers {
        contentType(applicationJson())
    }
    body(file('payloads/reservation-created.json'))

    bodyMatchers {
        jsonPath('$.reservationId', byRegex('RSV-[0-9]+'))
    }
}
~~~

Matchers express constraints on dynamic fields; still verify **actual behavior of generated producer tests and stubs** under your active SCC version. Regex validation in **producer tests** and **response generation in consumer stubs** do not necessarily work identically. For instance, a stub might return the sample value from the fixture while producer tests accept any ID matching the pattern.

In YAML, use the `matchers` configuration section supported by your DSL version; do not embed arbitrary placeholders in JSON assuming SCC will interpolate them automatically. Expressions valid in one DSL may not be handled identically in the other.

## 9. Should the Same File Be Reused Across Multiple Contracts?

Reusing a fixture helps when **two contracts genuinely commit to the exact same payload**. However, overly broad sharing means editing one JSON file unintentionally alters the behavior of many contracts.

Examples:

| Situation | Recommended Action | Reason |
|---|---|---|
| Two contracts share a generic error response with identical semantics | Can share `error-invalid-request.json` | Reduces duplication without blurring behavior |
| In-stock and out-of-stock share a schema but differ in `available` | Create two clearly named fixtures | Reviewers see business differences and distinct contracts |
| Product GET and product-updated event share several fields | Consider **separating files by communication channel** | HTTP responses and events have different lifecycles, schemas, and consumers |
| Multiple contracts differ only by dynamic IDs | Use matchers or an appropriate contract structure | Copying many files just to swap one ID is hard to maintain |

**Do not turn fixtures into an unowned shared data dump.** In contract testing, every file must tie to a specific behavior and identifiable change scope.

When a shared fixture is needed, name it clearly and assess the impact on **every referencing contract** before editing it.

## 10. Where Do Body Files Live for Messaging Contracts?

Spring Cloud Contract also supports **messaging** contracts, where a producer emits a message instead of returning an HTTP response. Long event bodies can be extracted similarly.

Example `payloads/inventory-changed-event.json`:

~~~json
{
  "eventId": "EVT-1001",
  "eventType": "InventoryChanged",
  "sku": "SKU-123",
  "after": {
    "available": true,
    "quantity": 12
  },
  "source": {
    "service": "inventory-service",
    "region": "south"
  }
}
~~~

A Groovy contract describing the output message:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    label 'inventoryChanged'

    input {
        triggeredBy('triggerInventoryChanged()')
    }

    outputMessage {
        sentTo('inventory.events')
        body(file('payloads/inventory-changed-event.json'))
    }
}
~~~

This is a **learning sample**; the `triggerInventoryChanged()` method must be provided by the test base class and messaging setup configured by the project. When integrating Kafka, RabbitMQ, or Spring Cloud Stream, also verify destination/topic, headers, serialization, schema, and triggering rather than checking only the JSON file.

If the message payload contains dynamic fields or must correlate with a prior request/event, add appropriate matchers. Using external files makes payload inspection easier, yet **does not replace messaging environment configuration**.

## 11. Text, XML, and Binary Data

Not every body is JSON. Extracting to files becomes even more valuable when exact newlines, significant whitespace, or specialized formats must be preserved.

### XML or Plain Text

An XML response can use `payloads/stock.xml`:

~~~xml
<stock>
    <sku>SKU-123</sku>
    <available>true</available>
    <quantity>12</quantity>
</stock>
~~~

The contract still references `file('payloads/stock.xml')` or `bodyFromFile`, while declaring the matching `Content-Type`, such as `application/xml`.

### Binary Data

For PDFs, images, or other byte payloads, **do not use plain text string loading** if raw bytes must remain intact. SCC versions support mechanisms such as **`fileAsBytes(...)`** in Groovy DSL or **`bodyFromFileAsBytes`** in YAML DSL for byte-array bodies. Check exact syntax and support in your locked version.

Illustrative reference example:

~~~groovy
response {
    status OK()
    headers {
        header('Content-Type', 'application/pdf')
    }
    body(fileAsBytes('payloads/invoice-demo.pdf'))
}
~~~

Binary files must be placed within contract resources accessible to the build. When packaging stubs, verify that raw bytes are returned intact, headers are accurate, and size/checksum match. Do not put a Base64 string in a text file and assume it represents PDF bytes unless the contract describes decoding.

## 12. From Body File to Generated Producer Tests and Stubs

Moving a payload from inline DSL to a file **does not change the contract's purpose**. For HTTP, the processing pipeline looks like:

~~~mermaid
flowchart TD
    A["Groovy/YAML contract"] --> C["Spring Cloud Contract"]
    B["JSON/XML/text/bytes fixture"] --> C
    C --> D["Generated producer test"]
    C --> E["Stub mappings / stub artifact"]
    D --> F{"Does real producer satisfy contract?"}
    E --> G["Consumer test via Stub Runner"]
    F -- "No" --> H["Fix code, contract, or fixture"]
    F -- "Yes" --> I["Evaluate consumer results"]
    G --> I
    I --> J{"Do all supported consumers pass?"}
    J -- "No" --> H
    J -- "Yes" --> K["Eligible to proceed with release"]
~~~

For example, Checkout Service currently reads `available`. If someone edits `stock-available.json` from:

~~~json
{
  "sku": "SKU-123",
  "available": true
}
~~~

to:

~~~json
{
  "sku": "SKU-123",
  "inStock": true
}
~~~

this is **not merely a test-data tweak**; it may represent a contract change that breaks consumer compatibility. If the producer already updated its code to match the new fixture, generated producer tests may stay green. **Consumer tests running against stubs generated from the new fixture** reveal whether existing clients can still read the response.

Therefore, when reviewing payload changes, ask two questions:

1. Did the fixture change **sample values** or change the **API/message commitment**?
2. Have candidate stubs built from that change been verified by **actual consumers**?

Never treat a PR labeled "just updating a JSON fixture" as safe if fields, types, nested structures, or semantics changed.

## 13. Verifying Fixtures and Paths Before CI Integration

An effective verification sequence can be applied step by step:

**Step 1 — Validate source format.** JSON must parse cleanly without trailing commas or invalid comments; XML must be well-formed; text needs proper encoding/line endings; binary files must preserve raw bytes. Use synthetic data; never put personal data or real tokens in fixtures.

**Step 2 — Verify referenced paths.** Confirm filenames and casing match, especially when CI runs on Linux while contract authors use Windows. When renaming or moving files, update every contract referencing them.

**Step 3 — Run producer contract generation.** Confirm SCC actually finds and reads the fixture. Inspect generated tests to verify body assertions are included, rather than merely seeing the build succeed with zero generated tests.

**Step 4 — Run producer tests.** Tests must exercise producer code with suitable fixture data; mismatches in JSON, status, or messages must fail the test.

**Step 5 — Inspect generated stubs.** Open the artifact or packaging output to verify stub bodies reflect the fixture. When loading bodies from files, confirm referenced files/mappings are included in build outputs as required by your plugin version.

**Step 6 — Run consumer tests against candidate stubs.** Pin exact group, artifact, version, and classifier; Stub Runner must pull the newly built artifact rather than accidentally picking up stale stubs from a local cache.

Example **reference commands for learners to run in an SCC-configured producer project**:

~~~bash
# Maven: generate, run tests, and verify build lifecycle.
./mvnw clean verify

# Gradle: run tests, including generated tests if plugin tasks are wired properly.
./gradlew clean test
~~~

On Windows, use the respective wrappers (`mvnw.cmd`, `gradlew.bat`). These commands are starting points: how stub JARs are built, generated source paths, and exact task names depend on the project's plugin/build setup.

**Key verification point:** a green build is trustworthy only when contracts are discovered, body fixtures are read, generated tests run, and new stubs are actually built and tested.

## 14. Common Errors and How to Fix Them

| Symptom | Common Cause | How to Investigate |
|---|---|---|
| Build reports body file not found | Wrong relative path, rename, or file placed outside where the DSL loader reads | Check contract path, fixture path, and resolution rules of your SCC version |
| Passes on Windows, fails on Linux CI | Case mismatch, path separator issue, or uncommitted file | Check exact filenames and paths in Git |
| JSON fixture parse error | Missing brace, trailing comma, comment, or incompatible BOM/encoding | Validate JSON independently before running Contract Verifier |
| Producer test fails due to varying ID/timestamp | Fixture holds a static value for an inherently dynamic field | Use an appropriate matcher instead of enforcing a sample value |
| Producer tests pass while consumer fails | New fixture changed structure that older consumers rely on | Run consumer tests against stubs from the candidate commit; plan migration |
| Consumer tests stay green after fixture edit | Stub Runner pulled an old artifact; pipeline did not repackage stubs | Pin version/commit, inspect artifact download logs and stub contents |
| Multiple contracts suddenly change results | A shared fixture was edited | Find all referencing contracts and consider splitting files by scenario |
| Binary body has wrong size/content | Text-reading method used instead of bytes, or encoding corruption | Use file-as-bytes mechanism; check checksum/Content-Type |
| Message never appears despite valid JSON | Missing trigger setup, broker/test binder, destination, or serializer config | Inspect test base class, messaging adapter, and contract outputMessage |
| Review misses breaking changes | Diff shows only a long JSON file with no API change summary | Require description of changed fields/semantics and consumer verification evidence |

## 15. Sample Team Review Guidelines

A team supporting multiple consumers can adopt rules like:

- **Every fixture is named after its scenario** and lives close to its related contract.
- **Every PR editing a fixture** must state what is a test-data tweak versus a public API/message behavior change.
- **Referenced paths** must be verified in the build, including on case-sensitive filesystems.
- **No sensitive production data** in fixtures; use synthetic values preserving the required structure.
- **Never edit a shared fixture** without inspecting all impacted contracts and consumers.
- **Dynamic fields require proper matchers**; do not hardcode timestamps, UUIDs, or generated IDs just to make tests green.
- **Candidate stubs must be regenerated** whenever a contract or fixture changes, and consumer tests must run against that candidate artifact.
- **CI retains evidence**: commit/revision, generated test reports, stub coordinates, and consumer verification results.

These rules turn body files into reviewable, traceable parts of the contract rather than an unmanaged pile of auxiliary test data.

## 16. Hands-On Exercise: Extracting JSON and Catching a Breaking Change

**Context:** Inventory Service returns warehouse-level inventory; Checkout Service inspects the `available` field to decide whether to place an order.

### Part A — Refactor Without Changing Behavior

1. Create an HTTP GET contract with a nested JSON response, initially written inline.
2. Move the response object into `payloads/stock-available.json`.
3. Update the Groovy contract to `body(file('payloads/stock-available.json'))` or YAML to `bodyFromFile: payloads/stock-available.json`.
4. Run generated producer tests and verify outputs/stubs still describe the exact same behavior as before.
5. Verify that consumer tests running against the new stub still read `available: true`.

**Expected outcome:** Cleaner, more readable project structure while communication behavior and test results remain unchanged.

### Part B — Detecting a Compatibility-Breaking Change

1. Edit the JSON fixture: remove `available` and replace it with `inStock`.
2. Update the producer to return the new field and run generated producer tests.
3. Package a candidate stub from this exact commit.
4. Run the existing Checkout Service with Stub Runner pointing to the candidate stub.
5. Observe the consumer test failing on the assertion or deserialization step expecting `available`.

**Expected outcome:** The producer satisfies the new contract while the existing consumer is incompatible. Learners must explain why modifying a resource file can still constitute a breaking change.

### Part C — Phased Remediation

1. Temporarily have the producer and fixture return **both** `available` and `inStock`.
2. Test the older consumer against the expanded stub version.
3. Upgrade the consumer to read `inStock` and rerun verification.
4. Remove `available` only once supported consumers no longer depend on it.

**Deliverables:** directory layout diagram, refactored contract, valid JSON fixture, generated producer test report, candidate stub coordinates, consumer test results, and an explanation of compatibility decisions.

## 17. Pre-Merge PR Checklist

- [ ] Contract clearly specifies request, response/message, and why it references a body file.
- [ ] Fixture file has a business-meaningful name and sits where the plugin can read it.
- [ ] JSON/XML/text/binary file is valid and uses proper encoding and loading mechanism.
- [ ] Path matches accurately in CI, independent of personal machine behavior.
- [ ] Dynamic fields are validated via matchers or an appropriate strategy.
- [ ] Fixtures contain no tokens, real customer data, or secrets.
- [ ] All contracts sharing a fixture have been impact-assessed.
- [ ] Generated producer tests actually run and verify body contents.
- [ ] New stub artifact accurately reflects the fixture from the candidate commit.
- [ ] Consumer tests ran against the right candidate stub before releasing API/message changes.

## 18. Self-Check Questions

**1. Why does extracting JSON bodies into files make contracts easier to maintain?**

Because the DSL stays focused on behavior such as method, URL, status, and matchers, while large JSON/XML payloads can be formatted, validated, diffed, and reviewed separately. Even so, contract and fixture must be managed as a single coordinated change.

**2. What is the basic difference between Groovy `body(file(...))` and YAML `bodyFromFile`?**

They are two syntaxes across two DSLs expressing the same idea of loading a body from a resource file. Use the syntax and path-resolution rules of your SCC version.

**3. Does moving a body into a file cause randomly generated IDs to be ignored during verification?**

No. Values in the file remain sample data. If dynamic values must be accepted, design matchers for valid constraints and verify how generated tests/stubs handle those matchers.

**4. Why can editing a JSON fixture be a breaking change?**

Because fixtures feed into generated producer tests and stubs; renaming or removing a field can alter the API/message contract consumers depend on. Producer tests may pass with the new contract while older consumers still fail.

**5. What proves the consumer actually tested the new change?**

Consumer tests ran against the **candidate stub artifact generated from the exact contract and fixture of the commit under test**, with a traceable version/commit, rather than reusing a stale cached stub.

---

**Key takeaway:** Extracting large body payloads into **resource files** keeps Spring Cloud Contract definitions clean and reviewable. However, JSON/XML/message files are **part of the communication commitment**, so any fixture edit must still flow through **contract → generated producer test → candidate stub → consumer verification → CI**.
