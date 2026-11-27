# How HTTP Stubs Are Generated from Contracts

## 1. The problem: consumers need the API before the producer is ready

In a multi-service system, **Checkout Service** needs to call **Inventory Service** to check whether a product is in stock. If every time Checkout is tested it has to start Inventory, connect to a database, and spin up a full environment, the feedback loop becomes slow, fragile, and dependent on another team's deployment schedule.

**Spring Cloud Contract (SCC)** solves part of this problem by turning **communication contracts** into testing assets:

- **Generated producer tests:** verify that the actual Inventory Service implementation returns the agreed status, headers, and body.
- **HTTP stubs:** simulate the described HTTP behaviors so Checkout Service can test its client when Inventory Service is not running.

In the SCC ecosystem, HTTP stubs are typically represented as **WireMock mappings** and related response resources. They can be packaged into an artifact with the **`stubs`** classifier, and then **Stub Runner** is used to download and start the stub inside the consumer's test suite.

This lesson belongs to the **Stub Generation and Packaging** chapter, focusing on answering the exact question: **"How are HTTP stubs generated from contracts?"**. We will follow the flow from Groovy/YAML DSL to mappings, the stubs JAR, Stub Runner, producer/consumer tests, and CI gates.

### What you will learn

1. Distinguish **contract source**, **generated producer test**, **WireMock stub mapping**, and **stubs JAR**.
2. Explain which contract fields produce **request matching** conditions and which become the **stubbed response**.
3. Look at a Groovy/YAML example and understand the corresponding WireMock JSON structure.
4. Know how to verify headers, query parameters, JSON body matchers, response status, and body files.
5. Understand **consumer/producer values**, dynamic data, and the limitations of stub generation.
6. Package, identify, publish, and download the right stub version with Maven/Gradle and Stub Runner.
7. Diagnose errors such as "stub does not match", "stale stub", "overlapping mappings", and false-green pipelines.
8. Integrate stub generation, verification, and publishing into CI to catch incompatible API changes.

## 2. One contract, two different generation directions

~~~mermaid
flowchart TD
    A["Contract Groovy DSL / YAML DSL"] --> B["Spring Cloud Contract plugin"]
    B --> C["Generated producer tests"]
    B --> D["Generated HTTP stub mappings"]
    C --> E["Run against real producer application"]
    E --> F{"Does producer satisfy contract?"}
    F -- "No" --> X["Block change"]
    F -- "Yes" --> G["Allow packaging/publishing candidate stub"]
    D --> H["WireMock mappings + body files"]
    H --> I["JAR with stubs classifier"]
    I --> J["Artifact repository"]
    J --> K["Stub Runner in consumer tests"]
    K --> L["Real HTTP client of consumer"]
    L --> M{"Does consumer handle it properly?"}
    M -- "No" --> X
    M -- "Yes" --> N["Pass compatibility gate"]
~~~

Both branches originate from the contract, but serve opposite goals:

| Branch | Who executes it? | What is verified |
|---|---|---|
| **Producer tests** | The producer's test framework, against real producer code | The current producer **complies with** the contract |
| **HTTP stubs** | WireMock started by Stub Runner for the consumer | The consumer **sends valid requests** and **handles sample responses properly** |
| **Combined CI** | Service pipelines | Producer changes do not break supported consumers |

**A stub is not a live replica of the producer.** It does not invoke `InventoryController`, does not read the Inventory database, and does not automatically apply full business logic. The stub only simulates **the scenarios that were described**, by matching requests and serving configured responses.

Producer tests cannot be skipped either: if you only generate mappings and get green consumer tests, the contract and stub can agree with each other while the real producer application has already changed and returns different data.

## 3. Running example: checking inventory via HTTP GET

Suppose Checkout sends:

~~~http
GET /api/inventory/SKU-123 HTTP/1.1
Host: inventory.example.test
Accept: application/json
X-Client-Id: checkout-service
~~~

Inventory Service commits to returning:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "sku": "SKU-123",
  "available": true,
  "quantity": 12
}
~~~

When that product's inventory is not found, the API may return `404` under a separate contract. In this first example, we only examine **a fixed success scenario** to make stub generation easy to follow.

The contract contains parts that the tooling turns into WireMock behavior:

| Contract | Meaning mapped in the stub |
|---|---|
| `request.method: GET` | Only accepts HTTP GET |
| `request.url: /api/inventory/SKU-123` | Only accepts a URL/path matching the condition |
| Request header `Accept: application/json` | Checks the required header if the mapping is generated with that constraint |
| Request header `X-Client-Id` | Distinguishes callers if this is part of the contract |
| `response.status: 200` | Stub returns HTTP 200 |
| Response header `Content-Type: application/json` | Stub returns the JSON header |
| Response body containing `sku/available/quantity` | Stub returns the sample JSON body |

If the client uses POST instead of GET, calls a different URL, or sends an incorrect required header, WireMock may fail to find a matching mapping. **The actual conditions must be verified in the generated mapping JSON**, not just by reading the DSL.

## 4. Writing the contract in Groovy DSL

Sample file on the producer side:

~~~text
src/test/resources/contracts/inventory/get-inventory.groovy
~~~

Contents:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    description 'Checkout can view inventory for product SKU-123'

    request {
        method GET()
        url '/api/inventory/SKU-123'

        headers {
            header('Accept', 'application/json')
            header('X-Client-Id', 'checkout-service')
        }
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

How to read it:

1. `Contract.make` creates a contract definition.
2. `request.method` and `url` serve as input to generate **the request in the producer test** and **the request matcher in the stub**.
3. `request.headers` specifies the headers the consumer is expected to send.
4. `response.status/headers/body` define what the producer must satisfy and what the stub will simulate.
5. In the Groovy map, `available: true` is a boolean; `quantity: 12` is a number, not a string.
6. SCC uses the contract to generate tests and mappings according to the configured plugin tasks/goals.

**Important:** the Groovy file is not a direct WireMock script. SCC first parses the DSL into a contract model, and then a code/mapping generator transforms that model into the appropriate outputs.

## 5. Equivalent contract in YAML DSL

If the project uses YAML, you can replace the Groovy file with `get-inventory.yml`:

~~~yaml
description: Checkout can view inventory for product SKU-123
name: get_inventory_sku123

request:
  method: GET
  url: /api/inventory/SKU-123
  headers:
    Accept: application/json
    X-Client-Id: checkout-service

response:
  status: 200
  headers:
    Content-Type: application/json
  body:
    sku: SKU-123
    available: true
    quantity: 12
~~~

| Concept | Groovy | YAML |
|---|---|---|
| Method | `method GET()` | `method: GET` |
| URL | `url '/api/inventory/SKU-123'` | `url: /api/inventory/SKU-123` |
| Request header | `header('Accept', 'application/json')` | `Accept: application/json` |
| HTTP status | `status OK()` | `status: 200` |
| Response JSON | `body(sku: ..., available: ..., quantity: ...)` | `body:` with properties |
| Optional contract name | File name / DSL metadata | `name: get_inventory_sku123` |

These are **two ways to represent the same contract**; you should not create both simultaneously in the same module if doing so merely generates duplicate tests and mappings. YAML has type-inference rules: `true` is a boolean and `12` is a number; writing `'true'` or `'12'` turns them into strings, which can cause the stub to return the wrong schema.

## 6. What steps does the stub generation process go through?

Depending on the Maven/Gradle plugin and SCC version, task/goal names may differ, but logically the process consists of:

~~~text
1. Discover contracts in the configured source directory
   ↓
2. Parse Groovy DSL or YAML DSL
   ↓
3. Validate structure and build the contract model
   ↓
4. Determine stub request matchers
   ↓
5. Build static or dynamic response data per the contract
   ↓
6. Generate WireMock JSON mappings and body resources (if needed)
   ↓
7. Assemble mappings/resources into a stubs JAR
   ↓
8. Install/publish the artifact for consumers to download
~~~

Key steps to understand:

- **Discovery:** the plugin must scan the right path and file extensions; if no contracts are discovered, no mappings may be produced.
- **Parsing:** valid YAML syntax can still contain keys outside the SCC schema; Groovy can fail when evaluating the DSL.
- **Mapping:** request conditions can be equality, URL patterns, JSON body patterns, headers, or query parameters depending on the contract.
- **Response:** can be a literal body, JSON, status, headers, file resource, or a form of templating supported by the tool.
- **Packaging:** accurate mappings only help consumers when packaged with the right structure and distributed under the right version.

**Generated mapping filenames and exact JSON formatting details are tool outputs**—consumer code should never depend on arbitrary filenames created by the plugin. Consumers rely on **HTTP behavior** and stub coordinates, not by directly calling "mapping number 3".

## 7. Anatomy of a WireMock stub mapping

Suppose the fixed GET contract above is generated into a mapping structured roughly like this:

~~~json
{
  "request": {
    "method": "GET",
    "url": "/api/inventory/SKU-123",
    "headers": {
      "Accept": {
        "equalTo": "application/json"
      },
      "X-Client-Id": {
        "equalTo": "checkout-service"
      }
    }
  },
  "response": {
    "status": 200,
    "headers": {
      "Content-Type": "application/json"
    },
    "jsonBody": {
      "sku": "SKU-123",
      "available": true,
      "quantity": 12
    }
  }
}
~~~

This is an **illustrative mapping using WireMock syntax**, not a guarantee that SCC will emit **these exact JSON fields and body format**. Depending on the version, the response may use `body` instead of `jsonBody`, the mapping may include `id`/`name`/`priority`, and header/body matchers may vary.

Read the mapping as two halves:

- **`request`**: predicates WireMock uses to decide whether an incoming request matches.
- **`response`**: if matched, WireMock returns the defined status/headers/body.

When the consumer runs, **no query is made to the real InventoryService**. WireMock simply looks up loaded mappings and returns the corresponding data.

### Illustrating an unmatched request

~~~http
GET /api/inventory/SKU-123 HTTP/1.1
Accept: text/plain
X-Client-Id: checkout-service
~~~

If the mapping requires an exact `Accept: application/json`, the request above **does not match**. Similarly, a client forgetting `X-Client-Id` can receive WireMock's unmatched response.

An HTTP 404 response from the stub when a mapping does not match **is not necessarily the business error "SKU does not exist"**. You must distinguish "WireMock has no matching stub" from "a stub matched and intentionally returned a 404 response". That distinction is critical when diagnosing consumer tests.

## 8. Which parts generate request matchers?

Fields in the contract's `request` block become **matching conditions**. For HTTP, common groups include:

| Element | Contract example | Idea in mapping |
|---|---|---|
| Method | GET/POST/PUT/DELETE | `request.method` |
| Exact URL | `/api/inventory/SKU-123` | `url` or equivalent exact URL mechanism |
| URL path | `/api/orders` | Matches path separately from query when the contract uses `urlPath` |
| Header | `Accept: application/json` | `headers.<name>.equalTo` or another matcher |
| Query parameter | `page=2` | `queryParameters.page` with equality/regex |
| JSON body | `{"sku":"SKU-123"}` | `bodyPatterns`, such as JSON equality/JSONPath |
| Raw body | `name=Minh+Anh` | Text/form content matcher |
| Request cookies | Session cookie or API option | Cookie condition if supported by the DSL/mapping version |
| Routing metadata | Contract-specific fields | Depends on DSL/adapter mechanism; does not automatically become a request matcher |

A contract that does not declare an `Authorization` header does not mean the stub will check authentication on its own. Nor does the stub execute real security filters unless other tests/infrastructure are attached.

**Verification rule:** if you want to reject a malformed request in consumer tests, you must verify that the generated mapping has **the corresponding condition**, or add separate validation/integration tests. Do not guess from field names in the payload.

## 9. Distinguishing exact URL vs. URL path with query

Consider these requests:

~~~http
GET /api/items?category=books&page=2 HTTP/1.1
~~~

~~~http
GET /api/items?page=2&category=books HTTP/1.1
~~~

In terms of query parameter semantics, the two requests may be equivalent. If the contract uses a **literal URL including the query string**, the stub may match more strictly than intended and depend on representation order. When an API actually uses query parameters, prefer the DSL structure for **`urlPath` + `queryParameters`** according to the corresponding syntax/version.

WireMock mapping concept:

~~~json
{
  "request": {
    "method": "GET",
    "urlPath": "/api/items",
    "queryParameters": {
      "category": {"equalTo": "books"},
      "page": {"equalTo": "2"}
    }
  },
  "response": {
    "status": 200,
    "jsonBody": {"items": []}
  }
}
~~~

Depending on the plugin, the mapping may include additional predicates. Query parameter names and values **both need to be matched** if the contract protects them.

A common mistake: placing POST form fields into `queryParameters`, while the real producer reads an `application/x-www-form-urlencoded` body. The generated stub will then match a different request than what the real consumer sends.

## 10. JSON request bodies and flexible matchers

A POST API that creates an inventory reservation:

~~~http
POST /api/reservations HTTP/1.1
Content-Type: application/json

{"sku":"SKU-123","quantity":2}
~~~

Groovy contract with a fixed body:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    description 'Create reservation for SKU-123'

    request {
        method POST()
        url '/api/reservations'
        headers {
            contentType(applicationJson())
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
            status: 'RESERVED'
        )
    }
}
~~~

In the stub mapping, SCC can generate **`bodyPatterns`** with JSON matching, roughly equivalent to:

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
      "status": "RESERVED"
    }
  }
}
~~~

This is also a **conceptual mapping**, not an exact copy of plugin output. `equalToJson` has specific behavior regarding whitespace, key ordering, extra fields, and JSON equality options; you should **inspect the actual mapping** and run negative tests if rejecting extra fields matters.

### When the body contains dynamic data

For example, `quantity` is fixed while `sku` is allowed to match a pattern. In Groovy DSL, you can use matchers:

~~~groovy
bodyMatchers {
    jsonPath('$.sku', byRegex('SKU-[0-9]+'))
}
~~~

With request matchers, the generator can produce JSONPath/regex patterns or appropriate WireMock predicates depending on the version. A **concrete sample body** still needs to be provided so the generated producer test can send a valid request.

When writing YAML DSL, matcher configuration typically goes under `request.matchers.body`:

~~~yaml
request:
  method: POST
  url: /api/reservations
  headers:
    Content-Type: application/json
  body:
    sku: SKU-123
    quantity: 2
  matchers:
    body:
      - path: $.sku
        type: by_regex
        value: 'SKU-[0-9]+'
~~~

This example only illustrates the **request matcher**; it is not a complete YAML contract because the `response` section is omitted. When applying it, add the response and inspect the actual generated mappings/assertions.

## 11. Distinguishing consumer and producer values

Spring Cloud Contract provides a mechanism to describe **different values for each side** when a contract needs flexible matchers while generated tests still need concrete data.

A pattern in Groovy DSL:

~~~groovy
body([
    sku: value(
        consumer(regex('SKU-[0-9]+')),
        producer('SKU-123')
    ),
    quantity: 2
])
~~~

In the **request body**:

- **The consumer value** describes the request condition that **the stub** must accept—here, an SKU matching the regex.
- **The producer value** is the concrete sample data that **the generated producer test** sends to verify the real implementation.

In the **response body**, the direction should be understood from each side's perspective: the stub must provide data **the consumer can receive**, while the producer test validates the real response against **the producer-side condition**. Do not swap `consumer(...)`/`producer(...)` arbitrarily, as that can produce unexpected tests or stubs.

### Two common pitfalls

1. **Overly permissive** request matchers: a `.*` regex makes the stub accept empty SKUs, wrong types, or unauthorized paths.
2. **Invalid** sample response values: consumer tests pass with a hardcoded response that violates the schema or contains invalid values not guarded by producer tests.

When dealing with dynamic data such as IDs, timestamps, or random numbers, start by choosing **a valid concrete sample for the stub** and **a sufficiently strict matcher for the producer**. There is no need to turn every field into a regex.

## 12. How is the stub's response generated?

The `response` section of the contract determines what happens once a request matches:

~~~yaml
response:
  status: 201
  headers:
    Content-Type: application/json
    Location: /api/reservations/R-1001
  body:
    reservationId: R-1001
    status: RESERVED
~~~

From this, the stub can return:

~~~http
HTTP/1.1 201 Created
Content-Type: application/json
Location: /api/reservations/R-1001

{"reservationId":"R-1001","status":"RESERVED"}
~~~

During generation, SCC converts the body description into data that WireMock can serve. **JSON keys, data types, status, and headers** must be preserved according to the contract. Therefore:

- `status: 201` is different from `status: 200`; a consumer checking `Location` or branching on status will observe different behavior.
- `status: RESERVED` is a business string, not an HTTP status.
- `Location` can be part of the contract: if the consumer reads it, it must be tested.
- The body can be stored inline in the mapping or reference an external file resource.
- Responses that vary dynamically with the request may require dynamic properties or templating supported by your SCC/WireMock version; **do not assume** every `$`/placeholder in the body will be rendered.

The stub **does not infer** responses from the producer's database. Only when the contract defines multiple scenarios or valid transformation mechanisms will the stub exhibit corresponding behavior.

## 13. Stubs returning error codes also come from contracts

An endpoint with multiple outcomes should have **multiple clear contracts**. For example, GET for a non-existent SKU:

~~~yaml
description: Report missing product SKU-404
name: inventory_missing

request:
  method: GET
  url: /api/inventory/SKU-404
  headers:
    Accept: application/json

response:
  status: 404
  headers:
    Content-Type: application/json
  body:
    code: SKU_NOT_FOUND
    message: SKU was not found
~~~

The corresponding stub mapping can return **HTTP 404 with error code `SKU_NOT_FOUND`** when the request matches.

This differs from a **WireMock unmatched request**, which also often surfaces as a 404 but **lacks the committed business error response body**. When a consumer test gets a 404, check:

1. Did the request match the `inventory_missing` mapping?
2. Is another mapping requiring different headers, URL, or body?
3. Does the response contain `code: SKU_NOT_FOUND` and the exact headers from the contract?
4. Is the test accidentally calling a different WireMock port?

If a consumer test needs to distinguish "product not found" from "missing mapping", it must assert the **error schema**, not just the HTTP status.

## 14. Body files, large payloads, and external resources

When a JSON response is very long, contains multiline text, or carries binary payloads, the contract can reference **an external resource file** instead of embedding the entire body.

Depending on the DSL/version, mechanisms such as `bodyFromFile` (YAML) or `body(file(...))` (Groovy) load data from a file at a configured resource path.

Conceptual YAML example:

~~~yaml
request:
  method: GET
  url: /api/reports/REPORT-123
response:
  status: 200
  headers:
    Content-Type: application/json
  bodyFromFile: report-123.json
~~~

If `report-123.json` exists in a location supported by the plugin, the generator can use its content to produce tests and stubs. WireMock can store returned data in a **response file**, referenced in the mapping via a property like `bodyFileName`:

~~~json
{
  "request": {
    "method": "GET",
    "url": "/api/reports/REPORT-123"
  },
  "response": {
    "status": 200,
    "headers": {
      "Content-Type": "application/json"
    },
    "bodyFileName": "report-123.json"
  }
}
~~~

**Note:** this is an illustrative mapping. SCC may inline the body or reorganize files according to the plugin version's rules; **do not assume** `bodyFromFile` always generates `bodyFileName` with the exact original filename.

When packaging stubs, verify that **both the mapping and the body file are present**. Copying only mapping JSONs while omitting files under the body directory causes the stub to fail at runtime or return invalid responses.

For binary payloads, check how your DSL/version supports file bodies, encoding, MIME types, and byte storage. Never convert binary data into UTF-8 strings arbitrarily.

## 15. Dynamic matchers and response templating are not the same

Two mechanisms are frequently confused:

- **Request matcher**: decides **whether an incoming request fits a scenario**.
- **Response templating**: computes part of the response **from request data** when the stub is called, if configured and supported.

For example, the consumer sends:

~~~http
GET /api/inventory/SKU-456 HTTP/1.1
~~~

If the mapping accepts `SKU-[0-9]+` while the response is hardcoded as:

~~~json
{"sku":"SKU-123","available":true,"quantity":12}
~~~

then the stub can accept the SKU-456 request and still return **SKU-123**. A regex in the request **does not automatically echo** the SKU into the response. If the consumer relies on `response.sku == request SKU`, you need to:

1. Use deterministic scenario contracts;
2. Or configure verified dynamic properties / response templating per your DSL/version;
3. Or add producer/consumer integration tests to verify this relationship.

Some WireMock versions support **response-template transformers** and variables such as request path or headers, though the SCC plugin may integrate them in specific ways. Do not copy templating syntax straight from WireMock docs into a contract and assume it will be processed. Inspect the **generated mapping** to confirm it contains the expected transformer and response body.

## 16. Multiple contracts become multiple stub scenarios

Real-world APIs have multiple outcomes:

~~~text
GET /api/inventory/SKU-123 -> 200, in stock
GET /api/inventory/SKU-456 -> 200, out of stock
GET /api/inventory/SKU-404 -> 404, not found
POST /api/reservations with valid body -> 201
POST /api/reservations with quantity=0 -> 400
~~~

You can write one contract for each important scenario. SCC will create the corresponding test/mapping assets according to the generator's capabilities and configuration.

However, multiple contracts sharing the **same method/path** can create **competing mappings**:

- Mapping A matches POST with an overly broad JSON body.
- Mapping B is intended for `quantity=0`, yet A also matches that request.
- WireMock picks one mapping by specificity/priority, causing the consumer to receive the wrong status.

Ways to reduce this risk:

1. Make request conditions sufficiently specific: method, path, headers, body/query matchers.
2. Inspect generated WireMock mappings, especially `bodyPatterns` and `priority` if present.
3. Run **negative** tests: a request meant for scenario B must not match A.
4. Do not rely on filename ordering or JAR load order to pick scenarios.
5. If stateful scenarios are needed, verify that your SCC/WireMock version and workflow support them, rather than assuming individual contracts automatically maintain state.

**Just because a mapping accepts a request does not mean it is the right business scenario.**

## 17. What does a stubs JAR contain?

HTTP stubs are typically packaged into a **JAR with the `stubs` classifier** to distinguish them from the application JAR. A sample set of Maven coordinates:

~~~text
groupId:     com.example
artifactId:  inventory-service
version:     1.3.0-rc1
classifier:  stubs
type:        jar
~~~

Illustrative artifact filename:

~~~text
inventory-service-1.3.0-rc1-stubs.jar
~~~

Its structure may look roughly like this (always inspect the JAR **actually produced by your project's plugin**):

~~~text
inventory-service-1.3.0-rc1-stubs.jar
└── META-INF/
    └── com.example/
        └── inventory-service/
            └── 1.3.0-rc1/
                ├── mappings/
                │   ├── get-inventory.json
                │   ├── inventory-missing.json
                │   └── create-reservation.json
                └── contracts/
                    ├── inventory/
                    │   ├── get-inventory.groovy
                    │   └── inventory-missing.yml
                    └── reservations/
                        └── create-reservation.groovy
~~~

For response bodies stored in files, the JAR also includes the corresponding resources (commonly under a `__files` directory compatible with WireMock/Stub Runner). Names, directory nesting, and whether source contracts are included **depend on the plugin/version, DSL, and packaging configuration**.

The key requirement is that **mappings and required resources live where Stub Runner knows how to find them**. Consumers should not access the internal structure of the JAR directly.

### Why use the `stubs` classifier?

- Separates the **binary application artifact** from the **artifact used for communication testing**.
- Lets consumers download stubs without starting the application.
- Keeps contract/stub versions aligned with producer versions.
- Allows multiple consumers to share the producer's standardized set of communication mocks.

Do not confuse the `stubs` classifier with a Java package or a pre-running WireMock server. The JAR is a **configuration asset** that Stub Runner/WireMock loads and serves over HTTP when tests require it.

## 18. Maven: generating, verifying, and packaging stubs

In a Maven-based producer, basic configuration typically includes `spring-cloud-contract-maven-plugin` with `extensions`, alongside the Contract Verifier starter in test scope.

Illustrative plugin snippet:

~~~xml
<plugin>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-contract-maven-plugin</artifactId>
    <version>CONTRACT_PLUGIN_VERSION</version>
    <extensions>true</extensions>
    <configuration>
        <baseClassForTests>
            com.example.inventory.ContractTestBase
        </baseClassForTests>
    </configuration>
</plugin>
~~~

And the test dependency:

~~~xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-contract-verifier</artifactId>
    <scope>test</scope>
</dependency>
~~~

`CONTRACT_PLUGIN_VERSION` is a **placeholder**, not a real version. Use a version compatible with your project's Spring Boot, Spring Cloud Release Train, and Contract dependencies per the BOM. A Maven BOM manages dependencies, **not necessarily build plugin versions**.

In a properly configured project, a reference command flow is:

~~~bash
# Generate/compile/run contract verification per the configured Maven lifecycle.
./mvnw clean verify

# Install candidate artifact (including stubs if the plugin packages them properly).
./mvnw install
~~~

Running `install` separately after `verify` can re-run the lifecycle; in CI you may use a more streamlined sequence per your pipeline. Publishing to a remote repository typically uses a `deploy` stage with explicit credentials and policies.

**Do not guess results from the command:** inspect plugin logs to verify contracts were read, generated tests were created, tests passed, and `*-stubs.jar` was produced. If a project disables generation/tests or skips tasks, the build can still succeed without producing compatibility evidence.

### Inspecting the generated JAR

~~~bash
# Reference syntax for systems with the Java jar CLI.
jar tf target/inventory-service-1.3.0-rc1-stubs.jar
~~~

Obtain the actual artifact filename from build outputs. Check for mappings, contracts/fixtures if packaged by the plugin, and related resource directories. If the JAR has no mappings, revisit the discovery/generation step before letting consumers download it.

## 19. Gradle: equivalent steps

With Gradle, apply the appropriate Spring Cloud Contract plugin and configure contracts. Example **Groovy DSL** configuration snippet:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.cloud.contract' version 'CONTRACT_PLUGIN_VERSION'
}

contracts {
    baseClassForTests = 'com.example.inventory.ContractTestBase'
}
~~~

This is an **illustrative snippet**, not a complete build script. You must add dependencies, repositories/BOM, and the Spring Boot plugin as appropriate if the project uses Spring Boot; `CONTRACT_PLUGIN_VERSION` must be replaced with an actual version.

Tasks may involve:

- Generating tests from contracts;
- Generating HTTP stubs/WireMock mappings;
- Packaging the `stubs` classifier JAR;
- Running tests and publishing artifacts.

Task names and their dependencies **depend on the plugin version**. Check with:

~~~bash
./gradlew tasks --all
./gradlew clean build
~~~

Some versions use tasks like `generateClientStubs` and `verifierStubsJar`. Do not assume every project has those exact names or that `build` automatically publishes stubs. Inspect the task graph, build outputs, and configured publication targets.

When publishing via `maven-publish`, confirm that **the `stubs` artifact is declared in the publication** and the repository receives the right group/artifact/version/classifier. Do not publish only the application JAR and assume consumers can download stubs.

## 20. How does Stub Runner download and start stubs?

After the producer installs/publishes the `stubs` JAR, consumers can use Stub Runner to download the artifact automatically and start a WireMock server.

Example consumer test:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.contract.stubrunner.spring.AutoConfigureStubRunner;
import org.springframework.cloud.contract.stubrunner.spring.StubRunnerProperties;

@SpringBootTest
@AutoConfigureStubRunner(
    ids = "com.example:inventory-service:1.3.0-rc1:stubs:8081",
    stubsMode = StubRunnerProperties.StubsMode.LOCAL
)
class InventoryClientContractTest {

    @Test
    void checkoutCanReadInventory() {
        // Call the real InventoryClient against http://localhost:8081.
        // Assert sku, available, and quantity on the response.
    }
}
~~~

Coordinate breakdown:

~~~text
com.example : inventory-service : 1.3.0-rc1 : stubs : 8081
   groupId       artifactId         version      classifier  requested port
~~~

Port 8081 is just an example; in many projects, **a dynamic port** is better because it avoids collisions during parallel CI runs. When using a dynamic port, the client test must be configured to point to **the exact port assigned by Stub Runner**, typically via SCC injection/lookup mechanisms or test properties.

Two common distribution modes:

| Mode | Where stubs are fetched from | When to use |
|---|---|---|
| **LOCAL** | Local Maven repository or configured local source | Producer/consumer tests on the same machine or a CI stage where artifacts are already installed |
| **REMOTE** | Configured artifact repository | Separate CI jobs, multiple teams, or when candidate stubs need to be reused |

Repository configuration, authentication, snapshot/release handling, and caching depend on your infrastructure and versions. A passing Stub Runner run **does not prove** it used the right commit if versioning is loosely pinned.

## 21. Consumer tests must use the real HTTP client

Stub Runner is only meaningful when consumer tests invoke **the exact HTTP client used by the application**. Example client using `RestClient`:

~~~java
import org.springframework.http.MediaType;
import org.springframework.web.client.RestClient;

public class InventoryClient {

    private final RestClient client;

    public InventoryClient(String baseUrl) {
        this.client = RestClient.create(baseUrl);
    }

    public StockResponse getStock(String sku) {
        return client.get()
            .uri("/api/inventory/{sku}", sku)
            .header("X-Client-Id", "checkout-service")
            .accept(MediaType.APPLICATION_JSON)
            .retrieve()
            .body(StockResponse.class);
    }

    public record StockResponse(
            String sku, boolean available, int quantity) {}
}
~~~

A consumer test can configure `InventoryClient` to point to the stub URL and verify:

~~~java
InventoryClient client = new InventoryClient(
    "http://localhost:8081"
);

InventoryClient.StockResponse result =
    client.getStock("SKU-123");

org.assertj.core.api.Assertions.assertThat(result.sku())
        .isEqualTo("SKU-123");
org.assertj.core.api.Assertions.assertThat(result.available())
        .isTrue();
org.assertj.core.api.Assertions.assertThat(result.quantity())
        .isEqualTo(12);
~~~

These are illustrative snippets **placed inside an appropriate test setup/class**, not a complete JUnit test ready to copy into production code.

**Do not** simply fire requests with a tool other than the real client and conclude the consumer will work. The real client might omit headers, build the wrong path, serialize incorrectly, or mishandle error responses. Those exact discrepancies are what consumer contract testing is meant to catch.

When an API defines `404`, `400`, or `500` responses, the consumer must also test **error handling**, not just the happy path.

## 22. Candidate stubs must stay paired with the producer commit

A major issue in CI is consumers running against **stale artifacts**:

~~~text
Producer commit A: GET /inventory -> {"available":true}
Producer commit B: GET /inventory -> {"inStock":true}

Producer B:
  - new code
  - contract also changed to inStock
  - generated producer tests PASS

Old consumer:
  - still reads available
  - test downloads stub from commit A
  - consumer tests PASS (false green)
~~~

To catch breaking changes, consumer tests must use **the stub generated from commit B's contract/code**. Then the old client test can fail because `available` is no longer returned.

How to design the pipeline:

1. Producer builds a **unique candidate version** for each PR/commit or build.
2. Run generated producer tests before publishing the artifact.
3. Package that exact build's stub, recording the commit SHA and artifact coordinates.
4. Publish the candidate artifact to the appropriate repository.
5. Pass the **exact coordinates** to the consumer verification job.
6. Run consumer tests against those coordinates—avoid `latest` or uncontrolled floating versions.
7. Only promote/release once all required compatibility gates pass.

In parallel CI runs, avoid overwriting the same mutable version across two commits. Version-based caching can serve stale mappings even after the producer has changed.

## 23. A contract can generate valid stubs while the producer is still broken

An easily missed scenario:

- The contract is valid, and stubs are generated correctly;
- Consumer tests run against the stub and pass;
- Yet the producer implementation returns a different status/body due to a refactor.

Because stubs simulate **the contract** rather than **live producer code**, consumer tests can remain green. Therefore, **generated producer tests** must execute before or alongside publishing.

Example intentional mutation:

~~~java
// Old producer, compliant with contract:
return new StockResponse("SKU-123", true, 12);

// New buggy producer:
return new StockResponse("SKU-123", false, 12);
~~~

If the contract requires `available: true` and the generated test actually calls the production controller/service, the test must fail. If it does not, check whether the test base class is returning mock responses or generated tests are being skipped.

**Never alter the contract to match buggy code just to make the build green** when consumers still depend on the old behavior. If changing the contract intentionally, plan compatibility, migration, or versioning.

## 24. Not every contract generates a single simple stub

Keep these limitations in mind:

- One DSL file can describe multiple scenarios in ways supported by the plugin; the number of files **does not necessarily equal** the number of mappings.
- Dynamic matchers can be translated into multiple JSONPath/regex conditions rather than simple equality.
- Response bodies can be inlined, file-backed, or rendered via supported templating.
- Messaging contracts generate messaging test/simulation assets—**do not assume** they behave like HTTP WireMock mappings.
- Overly broad headers or matchers can cause multiple mappings to match the same request.
- Stateful behavior, long-lived streaming, dynamic pagination, transactions, auth/permissions, retries, or latency **do not appear automatically in stubs** unless described or covered by additional tests.
- Static stubs usually cannot fully replace a production service with rich business logic.

Thus, a stub's role is to **simulate the committed protocol to test clients**, not to serve as a full integration environment. For critical concerns such as Kafka routing, database semantics, security, or SLOs, add integration, resilience, and E2E tests.

## 25. Troubleshooting: why doesn't the stub match?

| Symptom | Possible cause | Resolution |
|---|---|---|
| WireMock returns 404 without business error body | No mapping matched | Inspect unmatched requests and loaded mappings |
| Stub always returns the wrong scenario's response | Multiple mappings share method/path with overly broad matchers | Check `bodyPatterns`, headers, priority; run negative requests |
| GET hits the right path yet fails to match | `Accept`/`X-Client-Id` header missing or incorrect | Inspect the actual outgoing HTTP request and matching predicates |
| POST JSON fails to match | Body has wrong field/type, Content-Type, or overly strict matcher | Compare serialized body and JSON/JSONPath matchers |
| Semantically valid query fails on ordering | Literal URL includes query string | Use `urlPath` + `queryParameters` if required by the DSL |
| Unicode/form body mismatch | Space `+` vs `%20`, `%2B`, double encoding | Inspect raw bytes and `Content-Type` |
| Response file not found | `bodyFileName` points to an unpackaged resource | Inspect the JAR; verify `mappings` + `__files` |
| Stub runs but lacks new contract changes | Consumer downloaded an older/cached artifact version | Verify exact coordinates, commit, and JAR mappings |
| Producer tests fail to catch a regression | Generated tests did not run or test base faked the producer | Inspect test sources/reports; test with an intentional fault mutation |
| Stub 404 mistaken for `SKU_NOT_FOUND` | Test only asserts HTTP 404 | Assert the error `code` body and business error headers |
| Parallel CI jobs collide on ports | Static port pinned across multiple workers | Use dynamic ports and proper injection |
| Maven/Gradle build passes yet stubs JAR is empty | Contracts were not discovered or generation was skipped | Check plugin config, directory paths, and mapping count |
| Stub passes yet consumer fails in production | Contract missed cases, dynamic responses, security, or other infra | Add consumer integration/resilience tests |

An effective diagnostic order: **artifact coordinates → Stub Runner logs → mapping JSON → raw request → response mapping → consumer client assertions → producer test report**.

### Inspecting unmatched requests in WireMock

WireMock provides request journaling and "near misses" diagnostics in many versions. Use the corresponding test API/logs to see the exact **method, path, query, headers, and body** WireMock observed. Do not look solely at the HTTP client's "404" exception, as it does not reveal which mapping was skipped.

When using a WireMock standalone server or Stub Runner with multiple stubs on the same port, verify which **server instance** received the request. You may have hit another service's stub or a WireMock instance left running from an earlier test.

## 26. Resolving request/response mismatches before editing the contract

A sound debugging workflow avoids "legalizing" bugs by editing the contract:

1. **Observe the real client:** method, URL, query, headers, body, and encoding before reaching WireMock.
2. **Compare against the mapping:** inspect the `request` conditions generated by the stub rather than relying on intuition from reading the DSL.
3. **Identify which side is wrong:** did the client violate the contract, is the contract lagging behind a valid API change, or is there a generator version quirk?
4. **Check the real producer:** did generated tests run and assert the response properly?
5. **Check the consumer handler:** does it handle statuses, errors, and responses properly?
6. **Fix the root cause:** fix the client, fix producer code, or update the contract per an agreed change.
7. **Regenerate the candidate artifact:** do not let the consumer keep using an old JAR.
8. **Run negative tests:** invalid requests should be rejected if required; business 404 cases must remain distinct from unmatched requests.

Never hand-edit mapping JSON **inside the Stub Runner cache** and declare the contract updated; mappings regenerated from source contracts are the version-controlled source of truth.

## 27. Security and data inside stub artifacts

Stubs JARs are often distributed more broadly than runtime services. Never place sensitive data inside contracts or fixtures:

- Never embed real tokens, API keys, passwords, session cookies, or private signing keys in sample requests/responses.
- Never use real customer data in body files/fixtures, including incompletely "anonymized" dumps.
- Use fake IDs, fake addresses, and shareable synthetic data.
- If a security header must be matched, use **test values** or an appropriate matcher rather than hardcoding production credentials.
- Control repository read/write permissions if stub schemas or payloads are sensitive internal assets.
- Avoid printing raw requests containing `Authorization` headers into CI logs; log minimal details and redact secrets.
- Do not treat Stub Runner as a server enforcing the producer's full auth mechanisms; stub tests typically simulate only configured conditions.

A consumer test may run on a developer laptop or CI runner without production secrets. That is a major benefit of stubs, provided fixtures are designed safely.

## 28. Practice A — From your first contract to a WireMock mapping

**Goal:** observe the "transformation pipeline" rather than just reading concepts.

1. Create an Inventory Service with a `GET /api/inventory/SKU-123` endpoint returning JSON as in section 3.
2. Configure the Spring Cloud Contract plugin and an appropriate producer test base class.
3. Write a Groovy or YAML contract in the proper contracts directory.
4. Run the generation build according to your project's plugin/version.
5. Open the generated producer test: examine the request and assertions.
6. Open the generated WireMock mapping: locate `request.method`, URL/header predicates, `response.status`, and body.
7. Make the producer return an erroneous `available:false` and verify the test fails.
8. Restore the code, re-run tests, and package `*-stubs.jar`.

**Evidence to submit:** contract file, generated test source/report, mapping JSON, and stubs JAR filename. Exact mapping filenames do not have to match the examples.

## 29. Practice B — Consumer calling the stub and handling responses

**Goal:** have the consumer use the stub as a substitute HTTP server.

1. Install/publish the candidate stubs JAR for Inventory Service.
2. Create a Checkout test with Stub Runner configured for `LOCAL` or `REMOTE` as appropriate.
3. Configure `InventoryClient` to point to **the stub's actual port**.
4. Call the real client for `GET /api/inventory/SKU-123` with valid `Accept` and `X-Client-Id`.
5. Assert `sku`, `available`, and `quantity` per the contract.
6. Intentionally omit `X-Client-Id`: observe whether the stub rejects the match.
7. Intentionally change the URL to `/api/inventory/SKU-456`: see which mapping handles it and distinguish unmatched requests from business 404s.
8. Inspect the request journal / near misses if available and explain the mismatch.

**Evidence to submit:** artifact coordinates, Stub Runner logs, actual request details, and consumer test report.

## 30. Practice C — Breaking changes and CI gates

**Context:** the producer wants to rename the response field `available` to `inStock`.

1. **Keep the old contract** and change the producer implementation: generated tests must fail if that field is protected.
2. If the contract is updated to match the new behavior, generated producer tests may pass, yet **the old consumer is not necessarily safe**.
3. Generate the candidate stub for the new commit using the exact candidate version.
4. Run the old Checkout client test against that stub: check for deserialization/logic errors or failing assertions.
5. Propose an expand–migrate–contract strategy: add the new field while keeping `available` during transition, or version the API if needed.
6. Add a `404 SKU_NOT_FOUND` case and prove it differs from an unmapped 404.
7. Add a CI gate that blocks builds when **generated producer tests do not run**, the stubs JAR contains no mappings, or consumer tests use the wrong artifact.

**Evidence to submit:** before/after producer and consumer result table, contract diff, per-commit stub coordinates, and migration plan.

## 31. Checklist when reviewing HTTP stub generation and packaging

- [ ] Contract source is in the right module, directory, and DSL supported by the plugin.
- [ ] Request method, URL/path/query, headers, and body are clearly specified.
- [ ] Response status, headers, body, JSON types, and body files carry the right meaning for consumers.
- [ ] Generated producer tests are actually generated, compiled, and executed against the **producer implementation**.
- [ ] Stub mappings have been generated and cover at least the required scenarios.
- [ ] Mapping matchers are **neither too broad nor too strict** relative to the contract.
- [ ] Unmatched requests and business 404s are distinguished in tests.
- [ ] Mappings sharing method/path are checked against overlap using negative tests.
- [ ] All required `bodyFileName`/fixtures are packaged inside the JAR.
- [ ] The stubs JAR has clear group/artifact/version/classifier coordinates, distinct from the application JAR.
- [ ] Candidate artifacts match the **exact producer commit** under test.
- [ ] Consumers use Stub Runner with the right repository mode and actual port.
- [ ] Consumer tests invoke **the real HTTP client**, rather than sending requests with another mock or test helper.
- [ ] Consumer tests cover both success responses and critical error scenarios.
- [ ] No secrets or real user data exist in contracts or stub artifacts.
- [ ] CI blocks builds if producer verification fails, contracts/generated tests are missing, or stubs are empty.
- [ ] Potentially breaking API changes are verified against old consumers before release.

## 32. Self-check questions

**1. Why generate both producer tests and HTTP stubs from the same contract?**

Because producer tests prove the producer code fulfills the commitment, while stubs let consumers test their client against sample behavior. Having only stubs does not verify the real producer implementation.

**2. How do the `request` and `response` sections of a contract enter the stub?**

`request` is converted into **WireMock matching conditions**; `response` becomes the status, headers, and body WireMock returns when a request matches.

**3. Does a stub query a database or run the real InventoryService?**

No. WireMock serves described responses or configured templating; it does not execute producer business logic.

**4. When are `equalToJson` and `matchesJsonPath` used?**

Both can check a request's JSON body in WireMock. `equalToJson` compares JSON content under equality rules; `matchesJsonPath` checks a condition by path. Inspect the actual generated mapping to see which approach the generator chose and how strict it is.

**5. Why is a `404` from WireMock not necessarily `SKU_NOT_FOUND`?**

Because it can be an **unmatched request**, rather than a contract-defined 404 error response mapping. Always inspect the response schema, mappings, and logs.

**6. Why are the `stubs` classifier and candidate versions needed?**

The classifier distinguishes the communication-mock artifact from the application JAR; candidate versions ensure consumer tests download the exact stub for the change under test, not stale mappings.

**7. If both producer and contract rename `available` to `inStock` and producer tests pass, is it safe?**

Not yet. Old consumers may still read `available`. You must generate the new commit's stub and run old consumer tests against that candidate stub, or plan a migration/versioning path.

**8. If a request for SKU-456 matches a regex yet the stub returns SKU-123, is the generator broken?**

Not necessarily. The request matcher only selects the mapping; a static response can still return the sample `SKU-123`. If the contract requires the response to depend on the request, configure an appropriate dynamic response mechanism or split scenarios explicitly.

## 33. References

- [Spring Cloud Contract Reference](https://docs.spring.io/spring-cloud-contract/reference/): HTTP/message contracts, Contract Verifier, stub generation, and Stub Runner.
- [Spring Cloud Contract — HTTP Contracts](https://docs.spring.io/spring-cloud-contract/reference/project-features-contract/http.html): request/response, HTTP DSL.
- [Spring Cloud Contract — Contract DSL](https://docs.spring.io/spring-cloud-contract/reference/project-features-contract.html): Groovy/YAML DSL, dynamic values, and matchers.
- [Spring Cloud Contract — Maven Plugin](https://docs.spring.io/spring-cloud-contract/reference/project-features-maven.html): Maven integration, test generation, stub packaging.
- [Spring Cloud Contract — Gradle Plugin](https://docs.spring.io/spring-cloud-contract/reference/project-features-gradle.html): Gradle tasks and configuration.
- [Spring Cloud Contract — Stub Runner](https://docs.spring.io/spring-cloud-contract/reference/project-features-stubrunner.html): downloading artifacts and running stubs on the consumer side.
- [WireMock — Stubbing](https://wiremock.org/docs/stubbing/): request/response mapping structure.
- [WireMock — Request Matching](https://wiremock.org/docs/request-matching/): URL, header, query, and JSON/body matching.
- [WireMock — Response Templating](https://wiremock.org/docs/response-templating/): when responses are built from requests, requiring an appropriate transformer configuration.

**Version note:** task/goal names, mapping formats, resource locations in the JAR, dynamic value usage, and Stub Runner configuration can vary across Spring Cloud Contract and WireMock versions. Always consult the documentation matching your **Spring Boot–Spring Cloud Release Train–Contract** versions, and inspect **generated sources, mappings, and actual artifacts**. Examples in this lesson are illustrative, not outputs from an executed build.

---

**Key takeaway:** SCC takes the **contract's request** to generate **WireMock matching** conditions, uses the **contract's response** to build stub return data, and generates **producer tests** to verify the real code. These mappings/resources are packaged into a versioned **stubs JAR**, which Stub Runner starts as an HTTP server for consumers. Only when **producer tests pass, the stub matches the exact commit, and consumer tests pass using the real client** does the workflow have a reliable basis for catching incompatible API changes.
