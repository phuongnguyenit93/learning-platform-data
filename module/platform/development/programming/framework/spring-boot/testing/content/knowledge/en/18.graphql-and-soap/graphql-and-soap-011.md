# Choosing Between Contract Testing and Transport Integration by Risk

In Spring Boot, **both GraphQL and SOAP can run over HTTP**, yet their contracts differ significantly. GraphQL encodes most request semantics inside its **schema, operations, fields, arguments, and `data`/`errors` structure**. SOAP relies heavily on **WSDL/XSD, XML namespaces, SOAP Envelope/Header/Body, Faults, SOAPAction, and WS-\* policies**; HTTP is merely one possible transport.

An in-memory test running inside the framework dispatcher can guard schema or payload contracts very well, yet **it does not verify TLS, proxies, servlet mappings, Content-Type, SOAPAction, or open network ports**. A test hitting a live HTTP server proves transport, yet if it checks only `HTTP 200` without inspecting GraphQL `errors` or XML structure, it still lets severe contract bugs slip through.

Thus, the question is not "choose contract tests **or** transport integration tests for the whole project," but rather:

> **Which risk needs to be caught, which test actually exercises the boundary causing that risk, and is an additional test worth its cost and flakiness?**

This lesson belongs to the **Spring Boot – testing** module, **GraphQL and SOAP** section, using **Java 17+, Spring Boot 3.5.x, Spring GraphQL, Spring Web Services, JUnit Jupiter 5, Mockito, GraphQlTester, MockWebServiceClient, and TestRestTemplate**. The example exposes two endpoints backed by one internal pricing service to compare **contracts**, **HTTP transport**, and **real business logic**. It calls no database, payment gateway, or production partner.

## 1. Learning objectives

After this lesson, you will be able to:

- Distinguish **contract tests**, **transport integration tests**, **service/unit tests**, and **end-to-end tests** by what they actually prove.
- Identify distinct risks between GraphQL schemas/operations/errors and SOAP WSDLs/XSDs/namespaces/Faults.
- Select `@GraphQlTest` + `GraphQlTester`, `@SpringBootTest(RANDOM_PORT)`, `MockWebServiceClient`, `MockWebServiceServer`, and HTTP clients by goal.
- Know that **GraphQL returning HTTP 200 can still carry `errors`**, and a **SOAP Fault** cannot be evaluated solely from body/status without knowing the SOAP version.
- Design a test matrix driven by **impact × likelihood × detectability**, avoiding running every case over the network just because it feels "more integrated."
- Verify backward compatibility of GraphQL schemas and SOAP WSDL/XSDs before breaking production consumers.
- Separate request/response contracts from authentication, authorization, proxies, TLS, content negotiation, and timeouts.
- Build a Java 17+ example with schema, controller/resolver, SOAP endpoint, XSD, in-memory contract tests, and random-port HTTP tests.
- Design negative tests catching missing fields, wrong namespaces, authorization leaks, SOAPAction mismatches, partial GraphQL errors, malformed SOAP, and timeouts.
- Report test coverage honestly: **which tests run real logic, which mock collaborators, and which cross TCP**.

## 2. Four boundaries that must never be conflated

### 2.1. Unit/service tests

The SUT is a real policy or application service, such as `PricingService.quote(...)` computing unit prices, discounts, and input validation. No GraphQL, HTTP, or SOAP is involved. Tests run fast and catch calculation bugs, yet **know nothing about schema, XML, or transport**.

### 2.2. Contract tests

Tests guarding **the interface seen by consumers**. GraphQL: types/fields/arguments/non-null, data shapes, error shapes, field-level authorization. SOAP: WSDL operations/messages, XSD qualified names and types, payloads, Faults, WS-Addressing/SOAPAction when promised. These can run in-memory via framework dispatchers or validate published schema files. **Opening a socket is not required.**

### 2.3. Transport integration tests

Tests traversing a real transport or adapter: HTTP routing, content types, headers, serialization, raw body bytes, SOAP envelopes, servlets, TLS, or gateways depending on scope. `@SpringBootTest(RANDOM_PORT)` exercises the embedded HTTP server. It **does not automatically test reverse proxies, mTLS, load balancers, or external partners** unless those sit on the call path.

### 2.4. End-to-end/system tests

Tests spanning multiple deployed services and real resources. Costs and flakiness are higher; worthwhile when cross-system contracts or distributed behavior carry high risk. Never label a `RANDOM_PORT` test backed by an in-memory catalog as "production E2E."

Diagram:

```text
Domain/unit
   PricingService + real rules
           |
           v
Contract in process
   GraphQL schema/resolver  |  SOAP payload/XSD/endpoint
           |
           v
Transport integration
   POST /graphql via HTTP   |  SOAP Envelope via HTTP /services
           |
           v
Deployment/partner E2E
   gateway, TLS, identity, broker, DB, external partner

Each tier adds assurance; a broader tier does not automatically replace assertions from a narrower tier.
```

## 3. GraphQL: where does the "contract" live?

A GraphQL API is defined using **Schema Definition Language (SDL)**:

```graphql
type Query {
  quote(sku: String!, quantity: Int!, member: Boolean!): Quote!
}

type Quote {
  sku: String!
  quantity: Int!
  subtotalVnd: Int!
  discountVnd: Int!
  totalVnd: Int!
}
```

Contract changes that can break clients:

- Removing or renaming `Quote.totalVnd`.
- Changing `quantity: Int!` to an incompatible type.
- Adding a new **required argument** that legacy clients omit.
- Changing `Quote!` to another type, or changing nullable/non-null in ways that alter client handling.
- Changing enum values, scalar encoding, pagination cursors, or sort semantics.
- Changing access rules so existing clients see or fail to see previously accessible data.
- A resolver returning `null` at a non-null schema position, triggering **null propagation** and errors.

**Not every schema change is breaking.** Adding a new field is usually backward-compatible for existing clients; however, security, performance, or field-level authorization changes can still cause regressions. Checking schemas and operations against real consumer queries matters more than counting SDL diff lines.

### 3.1. The contract is the schema plus execution behavior

Compiling a schema **does not prove** `Quote.totalVnd` is accurate. Strong GraphQL testing covers:

1. Schema fields and arguments exist and coerce properly.
2. Resolvers map queries and mutations cleanly.
3. Response `data` includes the selected types, fields, and values.
4. Error paths, classifications/extensions, and access permissions honor the public contract.
5. Separate real-service tests guard math, repositories, and transactions.
6. Transport tests cover HTTP methods, paths, headers, cookies, auth, CORS, or gateways when required.

## 4. GraphQL-over-HTTP: do not guess HTTP status from a GraphQL error

Typical HTTP request:

```http
POST /graphql HTTP/1.1
Content-Type: application/json
Accept: application/graphql-response+json, application/json;q=0.9

{"query":"query { quote(sku:\"BOOK\",quantity:2,member:true) { totalVnd } }"}
```

Successful response:

```json
{
  "data": {
    "quote": {
      "totalVnd": 216000
    }
  }
}
```

**Key point:** Errors arise in different phases:

- **Request/parse/validation errors:** malformed JSON, invalid GraphQL syntax, unknown field, uncoercible variables; the operation may never execute.
- **Execution/field errors:** a resolver throws an exception or fails to fetch one field; GraphQL may return **partial `data`** alongside an `errors` array.
- **Transport/security errors:** disallowed HTTP method, wrong Content-Type, unauthenticated caller, gateway timeout, server down.

In the GraphQL-over-HTTP draft, `application/graphql-response+json` gives stricter status code guidance. Servers or legacy clients using `application/json` may return HTTP 200 even with `errors`, especially when partial data exists. **Never hardcode "GraphQL always returns 200 on errors" or "GraphQL errors must be HTTP 400."** Check your **media type, framework version, and deployment contract**.

`GraphQlTester` treats GraphQL `errors` as failures by default during data assertions unless explicitly handled by the test. `TestRestTemplate` or an HTTP client returns raw statuses and bodies to verify transport contracts.

**A GraphQL test asserting only `status().isOk()` passes even when the body contains:**

```json
{
  "data": {
    "quote": null
  },
  "errors": [
    {
      "message": "Internal error",
      "path": ["quote"]
    }
  ]
}
```

Therefore assert **no unexpected errors**, and in error cases assert `errors` classification, path, and public details without leaking stack traces or SQL.

## 5. GraphQL queries, mutations, and subscriptions require different tests

| Operation type | Primary risks | Contract checks | When transport tests are needed... |
|---|---|---|---|
| Query | Wrong fields, arguments, read permissions, N+1, caching | Schema, fields, data, errors, authorization | Auth headers, GET/POST support, gateway, CORS, caching |
| Mutation | Side effects, idempotency, transactions, optimistic locking | Input/output, error codes, post-mutation state | POST semantics, CSRF/auth, retries/timeouts and network ambiguity |
| Subscription | Event streams, ordering, cancellation, resource leaks | Event types/data, lifecycle, errors | WebSocket handshake, subprotocols, reconnects, backpressure, proxy idle timeouts |

If an app only uses queries and mutations over HTTP POST, `@GraphQlTest` plus a few live HTTP tests may suffice. If it uses WebSocket subscriptions, `POST /graphql` HTTP tests **do not guard** handshakes, auth refreshes, or disconnect semantics; add `WebSocketGraphQlTester`/stream integration tests.

### 5.1. DataLoader and N+1 bugs

A mocked resolver can return the expected payload while skipping batch loading. When DB latency or rate limits pose a risk, add performance or instrumentation tests with realistic dataset sizes asserting query/batch counts and cancellation instead of checking JSON alone.

### 5.2. Authorization goes deeper than URLs

A single `/graphql` endpoint often exposes many fields with distinct access policies. Permitting access to the URL **does not prove** users can read only authorized objects and fields. Test **object-level and field-level authorization**, including access via aliases, fragments, nested resolvers, and alternate query paths.

## 6. SOAP: WSDL, XSD, and wire messages

SOAP typically relies on **WSDL 1.1/2.0**, **XSD**, and bindings/policies. Generated clients are sensitive to these contract details:

- WSDL `portType`/operations, bindings, service addresses, style/use, and actions.
- Root element QName, XML namespace URI, and local name.
- XSD types: `xsd:string`, `xsd:int`, `xsd:decimal`, optional/required, occurrences, `sequence`, and enumerations.
- SOAP 1.1 vs. SOAP 1.2 envelope namespaces and media types.
- Standard headers: SOAPAction, WS-Addressing Action, correlation IDs, WS-Security signatures.
- SOAP Fault semantics (`Client`/`Server` in SOAP 1.1; `Sender`/`Receiver` in SOAP 1.2) and contractual fault details.
- MTOM/attachments, XML canonicalization/signatures if used, and character encoding/line endings on the wire.

Changing:

```xml
<q:QuoteResponse xmlns:q="urn:demo:pricing:v1">
  <q:totalVnd>216000</q:totalVnd>
</q:QuoteResponse>
```

to:

```xml
<q:QuoteResponse xmlns:q="urn:demo:pricing:v2">
  <q:totalVnd>216000</q:totalVnd>
</q:QuoteResponse>
```

breaks clients dispatching by **QName namespace URI**—they fail to parse or route even though local name `QuoteResponse` and the amount are unchanged. SOAP contract tests must catch this instead of merely grepping for substring `216000`.

### 6.1. XML prefixes differ from XML namespace URIs

Both snippets:

```xml
<a:QuoteResponse xmlns:a="urn:demo:pricing:v1" />
```

and:

```xml
<b:QuoteResponse xmlns:b="urn:demo:pricing:v1" />
```

share the **exact same QName** for the root element. Raw XML string comparison fails on `a` vs. `b` despite identical XML semantics. Use XML-aware comparison, namespace-aware XPath, or XSD validation. Conversely, changing the URI to `urn:demo:pricing:v2` is a real breaking change.

### 6.2. XSD validation is not the entire WSDL contract

`ResponseMatchers.validPayload(xsdResource)` proves the **output payload** conforms to the specified XSD. It does not check SOAPAction, endpoint URLs, WSDL `binding`s, mTLS, WS-Security, fault behavior, SOAP version, or partner policies. Published WSDL files need dedicated tests when clients generate code from WSDLs, and schema changes require compatibility reviews.

## 7. SOAP Envelope, Faults, and HTTP status

Example SOAP 1.1 envelope:

```xml
<soapenv:Envelope
    xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/"
    xmlns:q="urn:demo:pricing:v1">
  <soapenv:Header/>
  <soapenv:Body>
    <q:QuoteRequest>
      <q:sku>BOOK</q:sku>
      <q:quantity>2</q:quantity>
      <q:member>true</q:member>
    </q:QuoteRequest>
  </soapenv:Body>
</soapenv:Envelope>
```

In-memory SOAP tests usually pass the **payload** (`QuoteRequest`) to the dispatcher without raw HTTP headers or sockets. HTTP transport tests must send the full **envelope** with matching SOAP version and `Content-Type`.

Checkpoints:

- SOAP 1.1 typically uses `text/xml` and sends `SOAPAction` when required by binding/partner.
- SOAP 1.2 typically uses `application/soap+xml`, with action possibly in a media-type parameter. Never mix SOAP 1.1 namespaces with SOAP 1.2 Content-Type.
- A Fault is a **SOAP structure**; depending on SOAP version/binding, it pairs with HTTP 500 or another status. Never assert SOAP errors solely via `HTTP 500` while ignoring `Fault`, faultcode, and detail.
- An HTTP 200 carrying a SOAP payload can still have the wrong QName, invalid XSD types, or missing required headers.
- A `MockWebServiceClient` test does not test gateways, TLS, or network timeouts, even though it uses request/response terminology.

## 8. WS-Security, signatures, and MTOM require dedicated test levels

Failures that **cannot be proved** by comparing parsed payloads alone:

1. Invalid XML signatures after canonicalization or namespace edits.
2. Expired WS-Security timestamps or clock skew bugs.
3. Untrusted tokens/certificates or failed mTLS handshakes.
4. Ignored `mustUnderstand` headers.
5. Dropped MTOM attachments, wrong MIME boundaries, or wrong Content-IDs.
6. SOAPAction or WS-Addressing Action mismatching WSDL/policy.
7. Proxies rewriting Content-Type, chunking, or size limits.
8. XML parsers failing to block XXE/entity expansion or oversized payloads.

When these carry **high impact**, write **adapter/transport integration tests** traversing interceptors, the HTTP stack, TLS, or a partner sandbox per boundary. `MockWebServiceClient` protects only the interceptors loaded in the test context; if the WS-Security interceptor is absent, passing payload tests do not prove signatures are validated.

**Safety:** Never embed production keystores or credentials in fixtures, and never hit live partner URLs unless authorized on a sandbox. Use isolated test certificates/secrets and sanitize sensitive data from logs.

## 9. Risk-based selection rules: not by "annotation weight"

A useful prioritization heuristic:

**Priority = Impact × Likelihood × Escape/Detectability**, scoring each factor 1–5 within the team. This is a **relative ranking aid**, not a formal probabilistic metric.

- **Impact:** how severe is financial loss, data leakage, partner outage, or compliance violation?
- **Likelihood:** how often does this config change, how complex is the adapter/protocol, what does incident history show?
- **Escape/Detectability:** if we run only unit/slice tests, how easily does the bug escape to staging or production?

Illustrative table, not empirical statistics:

| Risk | Impact | Likelihood | Escape | Score | Tests needed |
|---|---:|---:|---:|---:|---|
| GraphQL field-level auth leaks internal price | 5 | 3 | 5 | 75 | Authorization integration, negative queries |
| SOAP namespace v1 accidentally changed to v2 | 4 | 4 | 4 | 64 | XSD/WSDL contract, namespace fixtures |
| Partner mTLS handshake fails | 5 | 2 | 5 | 50 | Transport/sandbox with test certs |
| GraphQL JSON key order differs | 1 | 4 | 1 | 4 | **Avoid** raw text snapshots |
| SOAP XML prefix differs with same URI | 1 | 4 | 1 | 4 | XML-aware assertions, not raw compare |
| Pricing service miscalculates discount | 5 | 3 | 3 | 45 | Real unit/service tests + a few integrated paths |
| Broker timeout on mutation publish | 4 | 3 | 4 | 48 | Failure injection at port + transport test |
| Wrong GraphQL HTTP Content-Type | 3 | 3 | 4 | 36 | A few real HTTP assertions |

**How to apply:** Rank top risks, choose the *cheapest test capable of catching each specific risk*, and add targeted transport tests where in-memory tests are blind. Never turn every single operation and field into a full random-port test.

## 10. Matrix: "risk → right test type"

| Risk | GraphQL | SOAP | Why another layer alone isn't enough |
|---|---|---|---|
| Breaking schema/binding change | SDL/schema diff + consumer operations | WSDL/XSD diff + generated client tests | A single HTTP 200 scenario fails to guard compatibility |
| Argument/type mapping bug | `@GraphQlTest` + `GraphQlTester` | `MockWebServiceClient` + schema/XPath | Domain unit tests lack parsers/resolvers/dispatchers |
| Business logic bug | Service unit tests + real service integration | Service unit tests + real endpoint integration | Mocked services in slices hide algorithmic bugs |
| Header/media-type bug | HTTP integration | HTTP SOAP envelope integration | In-memory dispatchers bypass HTTP |
| Field-level authorization bug | GraphQL auth integration | SOAP interceptor/policy integration | Query success does not catch data leaks |
| SOAPAction/WS-Addressing | Rarely relevant except custom gateways | Transport tests with headers/actions | XSD payload checks ignore headers |
| Partial data + errors | `GraphQlTester` error assertions | SOAP Fault/detail assertions | Status-only checks miss payload errors |
| TLS/mTLS/proxy | Staging or transport integration | Staging/partner sandbox | Localhost HTTP `RANDOM_PORT` skips production TLS |
| N+1/load | Resolver + query count/perf tests | DB/client throughput tests | Correct schemas can still perform poorly |
| Retries/idempotency | Mutation/service failure injection | `WebServiceTemplate` failure injection | Happy paths never trigger partial failures |
| MTOM/attachments | File upload/multipart if used | SOAP MIME/attachment integration | XML payload-only tests ignore attachments |

**Minimal strategy:** Every critical contract gets **fast, readable contract assertions**; every critical transport boundary gets **at least one integration test actually crossing that boundary**; every critical business rule gets **unit/service tests running real logic**.

## 11. How one change affects GraphQL and SOAP differently

Suppose the same quoting domain is exposed over two protocols:

```text
            +------------------+
 GraphQL -->|                  |
            |  PricingService  |--> in-memory catalog
 SOAP ------|                  |
            +------------------+
```

If the discount changes from 10% to 5%:

- Real-logic service unit tests must turn red.
- Real-service full HTTP GraphQL and SOAP tests must turn red.
- `@GraphQlTest` with `@MockitoBean PricingService` may **stay green** because the response is stubbed.
- SOAP `MockWebServiceClient` turns red if wired to the real service; if its service is also mocked, it stays green.

If GraphQL field `totalVnd` is renamed to `amount`:

- GraphQL contract/schema compatibility tests must turn red.
- SOAP payload contracts **may be unaffected**.
- Service unit tests miss it because they know nothing of GraphQL SDL.

If SOAP namespace `urn:demo:pricing:v1` changes to `v2`:

- SOAP QName/XSD tests must turn red.
- GraphQL tests are usually unaffected.
- HTTP 200-only assertions miss it without XML inspection.

If the SOAP servlet URL or GraphQL HTTP media type is misconfigured:

- In-process contract tests can stay green.
- Live HTTP tests must catch it.

**That is why multi-protocol test matrices need orthogonal tests**, rather than mechanically repeating the same happy path at every layer.

## 12. Choosing the right `GraphQlTester` variant

Spring for GraphQL supports one testing workflow with **different transport bindings**:

- `ExecutionGraphQlServiceTester`: runs server-side execution **without HTTP**.
- `WebGraphQlTester`: runs through server-side `WebGraphQlHandler`.
- `HttpGraphQlTester`: uses `WebTestClient` over HTTP; can bind to a mock application context or a live HTTP server depending on setup.
- `WebSocketGraphQlTester`: fits subscriptions over WebSocket.
- `RSocketGraphQlTester`: used when the app runs over RSocket.

In Spring Boot 3.5:

- `@GraphQlTest` builds a GraphQL slice **without HTTP transport**, normally injecting `GraphQlTester`. `@MockitoBean` provides out-of-slice collaborators.
- `@SpringBootTest(RANDOM_PORT)` auto-configures `HttpGraphQlTester` when required test dependencies are present.
- `@SpringBootTest(MOCK)` can use `@AutoConfigureHttpGraphQlTester` to test the HTTP handler over a mock web environment; still **no real socket**.

**Never deduce "uses `HttpGraphQlTester` = uses a real HTTP server."** Check how the underlying `WebTestClient` is bound. In the example below, GraphQL contract tests use `GraphQlTester`, while transport tests use `TestRestTemplate` over `RANDOM_PORT` so boundaries stay unmistakable.

## 13. Spring-WS: `MockWebServiceClient` vs. `MockWebServiceServer`

Two similarly named utilities serve **opposite integration directions**:

| Tool | What is the SUT? | Where is the test double? | What does it prove? |
|---|---|---|---|
| `MockWebServiceClient` | SOAP **server endpoint** and dispatcher | No real HTTP transport opened | SOAP request payload → endpoint mapping → XML/Fault response in context |
| `MockWebServiceServer` | SOAP **client adapter** using `WebServiceTemplate` | Simulates remote SOAP server | Client marshals/requests properly and handles mock responses/faults without calling real partners |
| HTTP client + `RANDOM_PORT` | SOAP server and servlet/HTTP | Real partner/client per test | SOAP envelope, HTTP path, Content-Type, status, and live XML |
| Partner sandbox | Server/client and controlled remote protocol | Sandbox, never production | TLS/auth/actions/policies/interoperability within sandbox scope |

`MockWebServiceClient.createClient(applicationContext)` works against loaded endpoints/contexts using `RequestCreators.withPayload(...)`. Assert with `ResponseMatchers.payload`, `validPayload`, `xpath`, `noFault`, or fault matchers.

`MockWebServiceServer.createServer(webServiceTemplate)` pairs `RequestMatchers.payload`/`soapHeader` with `ResponseCreators.withPayload`/`withServerOrReceiverFault`, followed by `verify()` after invoking the SUT. These tests **do not replace** live HTTP checks when risks involve proxies, timeouts, or TLS.

## 14. Runnable example: one service, two protocols

To illustrate boundaries clearly, we build a **Spring MVC + Spring GraphQL + Spring Web Services** app in Spring Boot 3.5.x with fixed pricing data and zero DBs or external partners.

Demo rules:

- `BOOK`: 120,000 VND/unit, `PEN`: 20,000 VND/unit.
- `quantity` must be at least 1.
- `member=true` applies a 10% discount using integer division.
- Quote contains `sku`, `quantity`, `subtotalVnd`, `discountVnd`, and `totalVnd`.
- Monetary amounts use `int` purely to align with GraphQL scalar `Int` and XSD `xs:int`. GraphQL `Int` is **signed 32-bit**; real monetary systems should not assume `Int` fits large amounts—use Money/BigDecimal/custom scalars with explicit contracts.

The app exposes:

- `POST /graphql` via Spring GraphQL.
- SOAP 1.1 on Boot's default servlet mapping **`/services`**.
- GraphQL SDL and an XSD contract fixture.
- Socketless slice/contract tests and random-port HTTP tests.

### 14.1. File tree

```text
src/main/java/com/example/dualcontract/
    DualContractApplication.java
    Quote.java
    PricingService.java
    QuoteGraphQlController.java
    QuoteSoapEndpoint.java

src/main/resources/graphql/
    schema.graphqls

src/test/java/com/example/dualcontract/
    GraphQlSchemaContractTest.java
    GraphQlHttpTransportTest.java
    SoapPayloadContractTest.java
    SoapHttpTransportTest.java

src/test/resources/contracts/
    quote.xsd
```

**Scope of the runnable example:** These files suffice to test **GraphQL queries**, SOAP quote payloads, response XSD, and HTTP transport with the dependencies in section 15. The example does not publish a WSDL, implement WS-Security, or exercise SOAP 1.2, MTOM, or outbound SOAP clients; those topics are covered in dedicated recipes and must not be claimed as verified here.

## 15. Dependencies and Gradle commands

In a Gradle project configured with **Spring Boot 3.5.x plugin/BOM, repositories, and Java 17+**, declare:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-graphql'
    implementation 'org.springframework.boot:spring-boot-starter-webservices'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.graphql:spring-graphql-test'
    testImplementation 'org.springframework.ws:spring-ws-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

This is an **additional dependency snippet**, not a complete `build.gradle`. The project needs real plugin versions and repositories. In Boot 3.5, `@GraphQlTest` uses `spring-graphql-test`, `TestRestTemplate` comes from Boot's test starter, and `MockWebServiceClient` comes from `spring-ws-test`. If multiple web starters exist, verify the application type; this example uses Servlet Spring MVC only, so `starter-webflux` is unnecessary here.

Run via the Gradle Wrapper:

```bash
./gradlew test --tests com.example.dualcontract.GraphQlSchemaContractTest --tests com.example.dualcontract.GraphQlHttpTransportTest --tests com.example.dualcontract.SoapPayloadContractTest --tests com.example.dualcontract.SoapHttpTransportTest
```

On PowerShell:

```powershell
.\gradlew.bat test --tests com.example.dualcontract.GraphQlSchemaContractTest --tests com.example.dualcontract.GraphQlHttpTransportTest --tests com.example.dualcontract.SoapPayloadContractTest --tests com.example.dualcontract.SoapHttpTransportTest
```

These four test classes appear in the following sections. **Excerpts labeled "snippet" are not standalone Java files**; create only the files listed in the file tree. In multi-module Gradle builds, invoke the matching `:module:test` task.

## 16. Java code: application and quote domain

**`src/main/java/com/example/dualcontract/DualContractApplication.java`**

```java
package com.example.dualcontract;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DualContractApplication {
    public static void main(String[] args) {
        SpringApplication.run(DualContractApplication.class, args);
    }
}
```

**`src/main/java/com/example/dualcontract/Quote.java`**

```java
package com.example.dualcontract;

public record Quote(
        String sku,
        int quantity,
        int subtotalVnd,
        int discountVnd,
        int totalVnd) {
}
```

**`src/main/java/com/example/dualcontract/PricingService.java`**

```java
package com.example.dualcontract;

import org.springframework.stereotype.Service;

@Service
public class PricingService {

    public Quote quote(String sku, int quantity, boolean member) {
        if (sku == null || sku.isBlank()) {
            throw new IllegalArgumentException(
                    "sku is required");
        }
        if (quantity <= 0) {
            throw new IllegalArgumentException(
                    "quantity must be positive");
        }

        int unitPrice = switch (sku) {
            case "BOOK" -> 120_000;
            case "PEN" -> 20_000;
            default -> throw new IllegalArgumentException(
                    "unknown sku");
        };

        int subtotal = Math.multiplyExact(unitPrice, quantity);
        int discount = member ? subtotal / 10 : 0;
        int total = Math.subtractExact(subtotal, discount);

        return new Quote(sku, quantity, subtotal,
                discount, total);
    }
}
```

`Math.multiplyExact` catches `int` overflow. Production requires input bounds and public error mapping; this code simply illustrates real logic invoked across both protocols. **Do not mock `PricingService` in HTTP transport tests**, so a business bug turns both GraphQL and SOAP integration tests red.

## 17. GraphQL schema and controller/resolver

**`src/main/resources/graphql/schema.graphqls`**

```graphql
type Query {
    quote(
        sku: String!
        quantity: Int!
        member: Boolean!
    ): Quote!
}

type Quote {
    sku: String!
    quantity: Int!
    subtotalVnd: Int!
    discountVnd: Int!
    totalVnd: Int!
}
```

**`src/main/java/com/example/dualcontract/QuoteGraphQlController.java`**

```java
package com.example.dualcontract;

import org.springframework.graphql.data.method.annotation.Argument;
import org.springframework.graphql.data.method.annotation.QueryMapping;
import org.springframework.stereotype.Controller;

@Controller
public class QuoteGraphQlController {
    private final PricingService pricing;

    public QuoteGraphQlController(PricingService pricing) {
        this.pricing = pricing;
    }

    @QueryMapping
    public Quote quote(
            @Argument String sku,
            @Argument int quantity,
            @Argument boolean member) {
        return pricing.quote(sku, quantity, member);
    }
}
```

`@QueryMapping` binds `Query.quote` in the schema to the method; `@Argument` binds query arguments. With a Java record return value, GraphQL Java/Spring GraphQL extracts fields via standard property data fetching.

**Checkpoints:** schema contract tests catch renamed fields or arguments. However, when the service is mocked in the slice, it does not verify the 10% discount math; the HTTP tests below exercise the real `PricingService`.

## 18. SOAP endpoint: payload by QName and real service

**`src/main/java/com/example/dualcontract/QuoteSoapEndpoint.java`**

```java
package com.example.dualcontract;

import javax.xml.parsers.DocumentBuilderFactory;
import javax.xml.transform.Source;
import javax.xml.transform.TransformerFactory;
import javax.xml.transform.dom.DOMResult;
import javax.xml.transform.dom.DOMSource;
import org.springframework.ws.server.endpoint.annotation.Endpoint;
import org.springframework.ws.server.endpoint.annotation.PayloadRoot;
import org.springframework.ws.server.endpoint.annotation.RequestPayload;
import org.springframework.ws.server.endpoint.annotation.ResponsePayload;
import org.w3c.dom.Document;
import org.w3c.dom.Element;
import org.w3c.dom.NodeList;

@Endpoint
public class QuoteSoapEndpoint {

    public static final String NS = "urn:demo:pricing:v1";
    private final PricingService pricing;

    public QuoteSoapEndpoint(PricingService pricing) {
        this.pricing = pricing;
    }

    @PayloadRoot(namespace = NS, localPart = "QuoteRequest")
    @ResponsePayload
    public Source quote(@RequestPayload Source request)
            throws Exception {

        Document in = DocumentBuilderFactory.newInstance()
                .newDocumentBuilder().newDocument();
        TransformerFactory.newInstance()
                .newTransformer()
                .transform(request, new DOMResult(in));

        Element root = in.getDocumentElement();
        String sku = child(root, "sku");
        int quantity = Integer.parseInt(child(root, "quantity"));
        boolean member = Boolean.parseBoolean(
                child(root, "member"));

        Quote value = pricing.quote(sku, quantity, member);

        Document out = DocumentBuilderFactory.newInstance()
                .newDocumentBuilder().newDocument();
        Element response = out.createElementNS(
                NS, "q:QuoteResponse");
        out.appendChild(response);

        append(out, response, "sku", value.sku());
        append(out, response, "quantity",
                Integer.toString(value.quantity()));
        append(out, response, "subtotalVnd",
                Integer.toString(value.subtotalVnd()));
        append(out, response, "discountVnd",
                Integer.toString(value.discountVnd()));
        append(out, response, "totalVnd",
                Integer.toString(value.totalVnd()));

        return new DOMSource(response);
    }

    private static String child(Element root, String localName) {
        NodeList matches =
                root.getElementsByTagNameNS(NS, localName);
        if (matches.getLength() != 1) {
            throw new IllegalArgumentException(
                    "expected one element: " + localName);
        }
        return matches.item(0).getTextContent().trim();
    }

    private static void append(
            Document doc, Element parent,
            String localName, String value) {
        Element child = doc.createElementNS(
                NS, "q:" + localName);
        child.setTextContent(value);
        parent.appendChild(child);
    }
}
```

This is a **demo endpoint for studying test boundaries**, not a recommended production XML processing implementation. XML parsers/transformers/WS-Security must be hardened against XXE, entity expansion, external DTDs, and oversized payloads, or replaced with schema-validated JAXB/typed bindings. `Boolean.parseBoolean(...)` treats any non-`"true"` string as `false`; production must perform **strict XSD validation and type coercion** before pricing.

**Key boundaries:**

- `@PayloadRoot` dispatches by **namespace URI and local name** of the root payload element.
- `@RequestPayload Source`/`@ResponsePayload Source` operates on XML payloads; Spring-WS handles the HTTP envelope and body.
- `PricingService` executes for real inside the SOAP endpoint.
- No WSDL bean is published in the example: XSD tests guard payload shape only; verifying WSDL interoperability requires configuring formal WSDL/XSD publication and testing it separately.

## 19. XSD fixture for SOAP responses/requests

**`src/test/resources/contracts/quote.xsd`**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<xs:schema
    xmlns:xs="http://www.w3.org/2001/XMLSchema"
    targetNamespace="urn:demo:pricing:v1"
    xmlns:q="urn:demo:pricing:v1"
    elementFormDefault="qualified">

  <xs:element name="QuoteRequest">
    <xs:complexType>
      <xs:sequence>
        <xs:element name="sku" type="xs:string"/>
        <xs:element name="quantity" type="xs:int"/>
        <xs:element name="member" type="xs:boolean"/>
      </xs:sequence>
    </xs:complexType>
  </xs:element>

  <xs:element name="QuoteResponse">
    <xs:complexType>
      <xs:sequence>
        <xs:element name="sku" type="xs:string"/>
        <xs:element name="quantity" type="xs:int"/>
        <xs:element name="subtotalVnd" type="xs:int"/>
        <xs:element name="discountVnd" type="xs:int"/>
        <xs:element name="totalVnd" type="xs:int"/>
      </xs:sequence>
    </xs:complexType>
  </xs:element>
</xs:schema>
```

This file **is a test-managed contract fixture**, and does not publish a WSDL endpoint. In real contract-first SOAP APIs, keep XSD/WSDL files in main resources/versioned artifacts and point tests to **the exact published file** rather than maintaining a drift-prone copy inside test resources.

`xs:int` and GraphQL `Int` align for demo numbers. In real systems, large or decimal monetary amounts should use `xs:decimal`, long/custom scalars, or dedicated money types with overflow and rounding review.

## 20. In-process GraphQL contract test without HTTP

**`src/test/java/com/example/dualcontract/GraphQlSchemaContractTest.java`**

```java
package com.example.dualcontract;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.graphql.GraphQlTest;
import org.springframework.graphql.test.tester.GraphQlTester;
import org.springframework.test.context.bean.override.mockito.MockitoBean;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

@GraphQlTest(QuoteGraphQlController.class)
class GraphQlSchemaContractTest {

    @Autowired
    GraphQlTester tester;

    @MockitoBean
    PricingService pricing;

    @Test
    void mapsArgumentsAndSelectedFields() {
        when(pricing.quote("BOOK", 2, true))
                .thenReturn(new Quote(
                        "BOOK", 2, 240_000, 24_000, 216_000));

        tester.document("""
                query Quote($sku: String!,
                            $quantity: Int!,
                            $member: Boolean!) {
                  quote(sku: $sku,
                        quantity: $quantity,
                        member: $member) {
                    sku
                    quantity
                    subtotalVnd
                    discountVnd
                    totalVnd
                  }
                }
                """)
                .variable("sku", "BOOK")
                .variable("quantity", 2)
                .variable("member", true)
                .execute()
                .path("quote.totalVnd")
                .entity(Integer.class)
                .isEqualTo(216_000);

        verify(pricing).quote("BOOK", 2, true);
    }

    @Test
    void rejectsFieldNotDeclaredBySchema() {
        tester.document("""
                { quote(sku:"BOOK",quantity:2,member:true) {
                    secretKey
                  } }
                """)
                .execute()
                .errors()
                .satisfy(errors -> assertFalse(errors.isEmpty()));
    }
}
```

**Value of this test:**

- Parses and validates the GraphQL schema; binds arguments into the real controller.
- `GraphQlTester` evaluates paths **relative to `data`**, without needing `$.data.quote.totalVnd`.
- Maps the return value to the schema selection set.
- Querying an undeclared field produces `errors`, catching contract mismatches.
- `PricingService` is a **Mockito mock**, so this test **does not prove the 10% discount math**. That keeps the web/schema slice fast and isolated by design.

**No HTTP socket, Content-Type, authentication gateway, or network serialization** runs here. Never call it transport integration.

## 21. Testing GraphQL over a real HTTP server

**`src/test/java/com/example/dualcontract/GraphQlHttpTransportTest.java`**

```java
package com.example.dualcontract;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.http.HttpEntity;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpMethod;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(
        classes = DualContractApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class GraphQlHttpTransportTest {

    @Autowired
    TestRestTemplate http;

    @Autowired
    ObjectMapper mapper;

    @Test
    void postsActualHttpAndRunsPricingService() throws Exception {
        String operation = """
                query Quote($sku: String!,
                            $quantity: Int!,
                            $member: Boolean!) {
                  quote(sku: $sku,
                        quantity: $quantity,
                        member: $member) {
                    sku
                    quantity
                    subtotalVnd
                    discountVnd
                    totalVnd
                  }
                }
                """;

        HttpHeaders headers = new HttpHeaders();
        headers.setContentType(MediaType.APPLICATION_JSON);
        headers.setAccept(List.of(MediaType.APPLICATION_JSON));

        HttpEntity<Map<String, Object>> request = new HttpEntity<>(
                Map.of(
                        "query", operation,
                        "variables", Map.of(
                                "sku", "BOOK",
                                "quantity", 2,
                                "member", true)),
                headers);

        ResponseEntity<String> response = http.exchange(
                "/graphql", HttpMethod.POST, request, String.class);

        assertEquals(200, response.getStatusCode().value());
        MediaType type = response.getHeaders().getContentType();
        assertNotNull(type);
        assertTrue(MediaType.APPLICATION_JSON.isCompatibleWith(type));

        JsonNode root = mapper.readTree(response.getBody());
        assertFalse(root.has("errors"));
        assertEquals("BOOK",
                root.required("data").required("quote")
                        .required("sku").asText());
        assertEquals(216_000,
                root.required("data").required("quote")
                        .required("totalVnd").intValue());
    }
}
```

**Why pick `Accept: application/json` in the demo?** To keep the test simple with a media type supported by Spring GraphQL/Boot 3.5; for newer APIs following the GraphQL-over-HTTP draft, also test negotiation for `application/graphql-response+json` and status policies matching your server version. Never assume both media types enforce identical status rules across servers.

**What this test proves:**

- A real embedded server opens a random port and receives POST `/graphql` over HTTP.
- HTTP JSON request/response encoding/decoding and Content-Type work.
- The GraphQL endpoint and schema are loaded.
- `PricingService` **runs for real**, calculating the total in code.
- Changing the discount formula from 10% to 5% alters the JSON output and turns the test red.

**What it does not prove:** tokens, mTLS, gateways/CDNs, DBs, WebSocket GraphQL subscriptions, rate limiting, persisted queries, or field-level security, since none are configured in the demo.

## 22. SOAP payload contract: runs the endpoint without opening a socket

**`src/test/java/com/example/dualcontract/SoapPayloadContractTest.java`**

```java
package com.example.dualcontract;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.core.io.ClassPathResource;
import org.springframework.ws.test.server.MockWebServiceClient;
import org.springframework.ws.test.server.RequestCreators;
import org.springframework.ws.test.server.ResponseMatchers;
import org.springframework.xml.transform.StringSource;

@SpringBootTest(
        classes = DualContractApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.MOCK)
class SoapPayloadContractTest {

    @Autowired
    ApplicationContext context;

    MockWebServiceClient client;

    @BeforeEach
    void setUp() {
        client = MockWebServiceClient.createClient(context);
    }

    @Test
    void matchesQualifiedResponseAndXsd() {
        StringSource request = new StringSource("""
                <q:QuoteRequest xmlns:q="urn:demo:pricing:v1">
                  <q:sku>BOOK</q:sku>
                  <q:quantity>2</q:quantity>
                  <q:member>true</q:member>
                </q:QuoteRequest>
                """);

        StringSource expected = new StringSource("""
                <q:QuoteResponse xmlns:q="urn:demo:pricing:v1">
                  <q:sku>BOOK</q:sku>
                  <q:quantity>2</q:quantity>
                  <q:subtotalVnd>240000</q:subtotalVnd>
                  <q:discountVnd>24000</q:discountVnd>
                  <q:totalVnd>216000</q:totalVnd>
                </q:QuoteResponse>
                """);

        client.sendRequest(RequestCreators.withPayload(request))
                .andExpect(ResponseMatchers.noFault())
                .andExpect(ResponseMatchers.payload(expected))
                .andExpect(ResponseMatchers.validPayload(
                        new ClassPathResource("contracts/quote.xsd")));
    }
}
```

**What this test guards:**

- SOAP payload root `{urn:demo:pricing:v1}QuoteRequest` is dispatched to `@PayloadRoot`.
- `QuoteSoapEndpoint` invokes the real service and builds XML with matching QNames, values, and sequence order.
- Response payload contains no SOAP Fault.
- Response XML passes the XSD fixture, catching missing elements, wrong types, or wrong namespaces declared in the schema.

**What it does not guard:** HTTP endpoint mapping `/services`, wire-level SOAPAction, actual envelope version, TLS, proxies, WSDL publication, MTOM, or partner policies. For WSDL compatibility, test the **actual published WSDL** rather than extrapolating from payload fixtures.

## 23. SOAP transport integration: envelope + HTTP + payload

**`src/test/java/com/example/dualcontract/SoapHttpTransportTest.java`**

```java
package com.example.dualcontract;

import java.io.StringReader;
import java.util.List;
import javax.xml.parsers.DocumentBuilderFactory;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.http.HttpEntity;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpMethod;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.w3c.dom.Document;
import org.w3c.dom.Element;
import org.w3c.dom.NodeList;
import org.xml.sax.InputSource;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(
        classes = DualContractApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class SoapHttpTransportTest {

    @Autowired
    TestRestTemplate http;

    @Test
    void soap11EnvelopeTravelsThroughRealHttp() throws Exception {
        String envelope = """
                <soap:Envelope
                    xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/"
                    xmlns:q="urn:demo:pricing:v1">
                  <soap:Header/>
                  <soap:Body>
                    <q:QuoteRequest>
                      <q:sku>BOOK</q:sku>
                      <q:quantity>2</q:quantity>
                      <q:member>true</q:member>
                    </q:QuoteRequest>
                  </soap:Body>
                </soap:Envelope>
                """;

        HttpHeaders headers = new HttpHeaders();
        headers.setContentType(MediaType.parseMediaType(
                "text/xml;charset=UTF-8"));
        headers.setAccept(List.of(MediaType.TEXT_XML));
        headers.set("SOAPAction", "\"urn:demo:pricing:v1/quote\"");

        ResponseEntity<String> response = http.exchange(
                "/services",
                HttpMethod.POST,
                new HttpEntity<>(envelope, headers),
                String.class);

        assertEquals(200, response.getStatusCode().value());
        MediaType contentType = response.getHeaders().getContentType();
        assertNotNull(contentType);
        assertTrue(MediaType.TEXT_XML.isCompatibleWith(contentType));
        assertNotNull(response.getBody());

        DocumentBuilderFactory factory =
                DocumentBuilderFactory.newInstance();
        factory.setNamespaceAware(true);
        factory.setFeature(
                "http://apache.org/xml/features/disallow-doctype-decl",
                true);
        factory.setFeature(
                "http://xml.org/sax/features/external-general-entities",
                false);
        factory.setFeature(
                "http://xml.org/sax/features/external-parameter-entities",
                false);
        factory.setXIncludeAware(false);
        factory.setExpandEntityReferences(false);

        Document document = factory.newDocumentBuilder().parse(
                new InputSource(new StringReader(response.getBody())));

        Element root = document.getDocumentElement();
        assertEquals("Envelope", root.getLocalName());
        assertEquals(
                "http://schemas.xmlsoap.org/soap/envelope/",
                root.getNamespaceURI());

        NodeList totals = document.getElementsByTagNameNS(
                "urn:demo:pricing:v1", "totalVnd");
        assertEquals(1, totals.getLength());
        assertEquals("216000", totals.item(0).getTextContent());
    }
}
```

**Test significance:** a real request travels through the `/services` HTTP servlet mapping (Boot 3.5 default), SOAP 1.1 envelope, and Content-Type into the Spring-WS endpoint and returns as SOAP XML. Fields are read **by namespace URI**, independent of prefix `q` or naive text matching.

**Exact limits:** the `SOAPAction` header is **sent on the wire**, yet the demo endpoint uses `@PayloadRoot` and enforces no SOAPAction match. This test **does not prove the server rejects a wrong SOAPAction**. If a partner/WSDL requires action matching, add `@SoapAction`, matching mappings/interceptors/policies, and negative tests. Likewise, this parser reads responses from our internal server; production XML security requires hardened config and resource bounds on request ingestion.

**Caution:** `TestRestTemplate` reads the body as a `String` here to focus on the SOAP Envelope; if byte-level charsets or XML signing are contractual, read `byte[]` and verify encoding and canonicalization explicitly rather than relying on decoded text display.

## 24. Important tests not yet included in the demo

The code above is intentionally minimal. In a real product, add these tests when **risk is high enough**:

### 24.1. GraphQL schema compatibility / consumer contracts

Use schema diff tools analyzing breaking changes against real client operations, including aliases, fragments, variables, and enum/scalar edits. A syntactically backward-compatible schema edit can still regress authorization or performance; verify behavior too.

### 24.2. GraphQL partial errors

A resolver returns data for `publicField` while throwing an exception on `restrictedField`. Verify `data` exposes only allowed details and `errors[].path`/`extensions.code` conform to the public contract without leaking internal exceptions. Do not assume HTTP 500 when execution returns a partial response.

### 24.3. GraphQL mutation idempotency

For order-creation or payment mutations, simulate retries with the same idempotency key, post-commit timeouts, and concurrent duplicate requests. Assert **a single side effect** and an explicit response contract. HTTP 200 and accurate `data` on one call do not prove protection against double charges.

### 24.4. GraphQL authorization negative cases

Query the same object across two users/tenants checking field-level access; exercise aliases, fragments, and nested paths to expose bypasses. Include full-context/security-filter tests when risks live in auth tokens or filter chains rather than mocking principals only.

### 24.5. SOAP WSDL/XSD backward compatibility

Serve the real WSDL or keep a versioned contract-first WSDL. Validate with partner-style code generation and compare `operation`, `message`, `binding`, `service`, namespaces, cardinalities, schema imports, and SOAPAction. Payload XSD unit tests cannot replace published WSDL checks.

### 24.6. SOAP Faults and error leakage

Send schema-invalid input, wrong namespaces, business exceptions, and downstream timeouts. Assert **SOAP Faults** matching the SOAP version with public fault codes/details and zero leaked stack traces or credentials. Differences between SOAP 1.1 and 1.2 must be tested against the right binding.

### 24.7. SOAP WS-Security and mTLS

Use test certificates/keystores and a sandbox server to verify signatures, timestamp replay/expiry, credential rotation, truststores, and mTLS. Mocked payloads do not protect transport identity. Never verify XML signatures merely by comparing deserialized XML: XML Signature depends on canonicalization and references.

### 24.8. SOAPAction / WS-Addressing

If the WSDL/policy requires `SOAPAction` and `wsa:Action`, send an invalid action and assert rejection. HTTP clients must transmit real headers; standalone `@PayloadRoot` tests check only the root QName, **not actions**.

### 24.9. Attachments and streaming

SOAP MTOM, multipart attachments, or GraphQL subscriptions require testing MIME parts, Content-IDs, ordering, cancellation, timeouts, and memory profiles. `MockWebServiceClient` with `withPayload` does not replicate full MIME transport; `GraphQlTester.document(...).execute()` does not test WebSocket handshakes.

### 24.10. Input data validation before SOAP services

Even when response XSD passes, inbound requests are not automatically validated without a validating interceptor. Real projects need inbound XSD validation tested with wrong `quantity` types, missing fields, repeated elements, wrong namespaces, and XML entity attacks—proving the business service is untouched on invalid contracts.

## 25. Testing SOAP client adapters with `MockWebServiceServer`

When your application **acts as a client calling a partner's SOAP service**, `MockWebServiceClient` is the wrong tool for the outbound adapter. Pair the real `WebServiceTemplate` with `MockWebServiceServer` to simulate the remote SOAP server.

Example **snippet** (not a standalone runnable Java file; requires a client class and matching `WebServiceTemplate` setup):

```java
MockWebServiceServer server =
        MockWebServiceServer.createServer(webServiceTemplate);

server.expect(RequestMatchers.payload(
        new StringSource("""
                <q:QuoteRequest xmlns:q="urn:demo:pricing:v1">
                  <q:sku>BOOK</q:sku>
                  <q:quantity>2</q:quantity>
                  <q:member>true</q:member>
                </q:QuoteRequest>
                """)))
        .andRespond(ResponseCreators.withPayload(
                new StringSource("""
                        <q:QuoteResponse
                            xmlns:q="urn:demo:pricing:v1">
                          <q:sku>BOOK</q:sku>
                          <q:quantity>2</q:quantity>
                          <q:subtotalVnd>240000</q:subtotalVnd>
                          <q:discountVnd>24000</q:discountVnd>
                          <q:totalVnd>216000</q:totalVnd>
                        </q:QuoteResponse>
                        """)));

Quote result = soapPartnerClient.getQuote("BOOK", 2, true);
assertEquals(216_000, result.totalVnd());
server.verify();
```

This snippet **demonstrates the approach**, without defining `soapPartnerClient` or marshallers; your project supplies the real outbound adapter. `MockWebServiceServer` intercepts partner transport so tests run offline while testing marshalling, parsing, and intentional SOAP Fault handling.

When risks involve connection pooling, HTTP auth, proxies, TLS, or network timeouts, add HTTP integration tests against a mock SOAP container or sandbox. Never replace all outbound unit tests with a live sandbox—that makes suites slow and flaky.

## 26. Cost of testing: optimize coverage, not integration test count

A common mistake is running 300 GraphQL queries and 300 SOAP payloads over random-port HTTP, bootstrapping full contexts across runs. That slows CI, invites shared-state race conditions, and obscures failures.

A balanced pyramid:

1. **Many cheap unit tests** for pricing rules, validation, Money math, and key mappings.
2. **Focused contract slice tests** for GraphQL fields, SOAP QNames/XSD/Faults, and boundary wiring.
3. **Selective HTTP transport tests** for media types, URLs, headers, serialization, servlet wiring, and key negative cases.
4. **Adapter/partner contract tests** for WSDLs, schema compatibility, generated clients, and wire formats.
5. **Very few E2E tests** covering critical high-value flows across systems you actually operate or are authorized to test.

There is no fixed universal ratio. A payment platform may prioritize transaction failures and SOAP Fault integrations, while a read-only GraphQL dashboard may emphasize authorization and N+1 performance tests over SOAP sandboxes.

**The goal is not "every method has an HTTP test."** The goal is ensuring high-risk bugs **cannot slip through just because tests mocked away the boundary where those bugs occur**.

## 27. Selecting tests for specific changes

| Change | Run first | Add when risk is high |
|---|---|---|
| Add nullable GraphQL field | Schema diff + field slice test | Consumer query test |
| Make GraphQL argument non-null | Breaking-change analysis | HTTP consumer compatibility |
| Modify `PricingService` discount | Real service unit tests | One GraphQL and one SOAP integration path |
| Change GraphQL endpoint URL | HTTP transport test | Gateway/ingress test |
| Change Content-Type/Accept policy | HTTP negotiation tests | Legacy client compatibility |
| Change SOAP namespace | XSD/QName payload test | Generated client/WSDL compatibility |
| Reorder XSD sequence elements | XSD validation | Partner generated client test |
| Change SOAPAction | HTTP header + action mapping | Partner sandbox |
| Enable WS-Security signatures | Interceptor test | Real HTTP/mTLS + cert test |
| Add MTOM | Attachment test | HTTP multipart/partner interoperability |
| Update GraphQL field-level security | Negative authorization tests | Real token/gateway integration |
| Migrate repository to R2DBC/JPA | Repository integration | Business HTTP path against test DB |

**Draw crisp lines:** `@GraphQlTest` does not open HTTP; `MockWebServiceClient` does not open HTTP; `@SpringBootTest(MOCK)` opens no server socket either. Claim "transport integration" only when traffic actually crosses the transport under test.

## 28. Negative tests: the most frequently missed slice

A suite covering only happy paths stays green right up until production fails. Prioritize negative tests by risk:

**GraphQL**

- Fields or arguments absent from the schema.
- `null` at a non-null position.
- Invalid enum/scalar values or variable coercion failures.
- User A reading User B's data.
- Resolver errors producing partial data without leaking secrets.
- Overly deep/complex queries triggering depth/complexity limits.
- Mutation retries and idempotency.
- WebSocket subscription disconnects, cancellations, and re-authentication.

**SOAP**

- Wrong payload root namespace.
- Missing mandatory XSD elements, wrong sequence order, invalid decimal/date values.
- SOAP 1.1 sent with SOAP 1.2 Content-Type, or vice versa.
- Wrong SOAPAction.
- SOAP Fault mapping for input, partner, and internal errors.
- Invalid or expired WS-Security signatures/timestamps.
- Missing attachments or mismatched Content-IDs.
- XXE, entity expansion, and oversized XML payloads.
- Partner timeouts and retries that could cause duplicate writes.

Not every scenario above runs in the minimal demo. Choose branches driven by your real **contracts** and **risk register**.

## 29. Debugging when contract tests pass yet HTTP integration fails

Investigate layer by layer:

**Step 1 — Did the client hit the right endpoint?** Check port, URL, HTTP method, path mapping, and Content-Type; never hardcode 8080 under `RANDOM_PORT`.

**Step 2 — Did JSON/XML parsing succeed?** For GraphQL, inspect the JSON envelope and GraphQL document separately; for SOAP, inspect envelope, namespace URI, XML encoding, and XML parser errors.

**Step 3 — Was the right framework handler selected?** For GraphQL check schema mappings/resolvers; for SOAP check `@PayloadRoot` and SOAPAction/WS-Addressing mappings.

**Step 4 — Real service or mock?** If a slice test uses `@MockitoBean` while HTTP uses the real service, diverging results make sense; run unit tests on the service to isolate business bugs.

**Step 5 — Error in body or transport?** GraphQL HTTP 200 + `errors` is completely different from HTTP 404 due to a wrong URL; a SOAP Fault is different from an HTTP 502 HTML page from a proxy.

**Step 6 — Security/interceptors/filter chain?** When production enforces auth, verify the test context loads the right filters/interceptors; mocked payload tests do not run JWT decoders or mTLS automatically.

**Step 7 — Serialization/types?** GraphQL 32-bit `Int`, custom date/scalars, SOAP XSD element order/namespaces/decimals; inspect schemas and raw response trees.

**Step 8 — External resources?** Network timeouts, DB transactions, Kafka, partner sandboxes, test cleanup; never update expected values to match broken output before verifying the contract.

### 29.1. Quick symptom table

| Symptom | Possible root cause | What to check |
|---|---|---|
| GraphQL response has `errors` yet status is 200 | Execution/field error; legacy media type | `data`, `errors`, public error policy |
| GraphQL HTTP 404 | `/graphql` route unmapped | Starter, endpoint property, HTTP path |
| GraphQL field test passes, production `totalVnd` is wrong | `PricingService` mocked in slice | Real service unit/full-context test |
| GraphQL schema passes, web UI fails | Field authorization, fragments, or client variables differ | Consumer operations, auth |
| SOAP response contains `216000` yet client fails | Wrong namespace/QName/XSD/action | XML-aware comparison, WSDL binding |
| SOAP payload mock passes, HTTP gets 415 | Wrong SOAP version/Content-Type | `text/xml` vs. `application/soap+xml` |
| SOAP mock passes, transport gets 404 | Wrong servlet mapping/path | `spring.webservices.path`, URL |
| SOAP HTTP 500 | SOAP Fault or server/proxy error | Parse envelope/Fault and inspect server logs |
| SOAP partner fails TLS | Truststore/certificate/hostname mismatch | mTLS integration with test certs |
| Schema test passes, WSDL client generation fails | Binding/operation/service address differs | Published WSDL and generated client |
| Test fails only on CI | Port, locale, timezone, shared DB, parallelism | Isolation, timeouts, deterministic fixtures |
| Updating snapshots "fixed" all tests | Expected updated from actual without review | Review contract baselines and versioning |

## 30. Risks of schema-driven snapshots that are too strict or too loose

**Too strict:**

- Enforcing JSON key order or whitespace as part of a GraphQL contract.
- Asserting raw SOAP XML prefix `q` instead of namespace URI.
- Asserting exact internal framework exception messages or volatile internal metadata counts.

**Too loose:**

- Checking only HTTP 200 while ignoring GraphQL `errors`.
- Asserting only that a SOAP response contains `"216000"` while ignoring QName, schema, and faults.
- Using `JsonCompareMode.LENIENT` on sensitive payloads without forbidding extra leaked fields.
- Accepting any SOAP Fault and claiming "error handling is tested."
- Mocking a business service while claiming business rules were verified.

**Right balance:** Strict on **public contracts and security invariants**, flexible on **equivalent representations** whenever the contract does not mandate byte-for-byte identity.

## 31. Versioning and partner contracts

### GraphQL

Schema evolution favors adding new fields, deprecating before removal, and tracking consumer operations via telemetry/registries. Adding nullable fields carries far less risk than adding required arguments, yet still demands auth and performance review. Avoid renaming fields or changing scalars without a migration path.

### SOAP

SOAP WSDLs/XSDs couple tightly to generated clients. Changing namespace versions, `minOccurs`, sequence ordering, or bindings can force client regeneration and break un-regenerated runtimes even when code compiles. Publish versioned WSDLs/XSDs, test generated clients, and test old/new versions side by side when compatibility is promised.

### Both

Never treat "the schema loaded" as proof that all consumers work. Contract tests must track **the actual operations and messages consumers send**. With multiple independent clients, combine schema diffs and consumer-driven contract tests with targeted sandbox transport/interoperability tests.

## 32. Risk-based hands-on exercises

### Exercise A — GraphQL 200 with errors

The API returns HTTP 200 with body:

```json
{
  "data": {"quote": null},
  "errors": [{"message":"Not authorized","path":["quote"]}]
}
```

If a test checks only `assertEquals(200,status)`, does it detect an unauthorized caller? Write assertions for `errors` and the data-hiding policy for that principal. Explain why status alone is insufficient.

### Exercise B — SOAP QName

A response changes prefix `q` to `x` while keeping namespace URI `urn:demo:pricing:v1`. A raw-string test fails. Is this a breaking change? Why are `ResponseMatchers.payload` and namespace-aware XPath better?

### Exercise C — WSDL change

A partner generates a client from WSDL v1. The team edits only the test XSD response fixture without testing the published WSDL. What bugs could escape? List the operation name, binding, SOAPAction, service address, and schema imports to verify.

### Exercise D — Choosing test levels

1. 10% discount math is wrong.
2. GraphQL HTTP `Content-Type` header is wrong.
3. SOAP `@PayloadRoot` fails to match namespace.
4. Partner mTLS handshake fails.

Pick the cheapest test level catching each bug. **Guided answer:** service unit test; real HTTP test; `MockWebServiceClient`/XSD; transport/sandbox TLS with test certificates.

### Exercise E — SOAP client adapter

An app uses `WebServiceTemplate` to call a partner. Should you use `MockWebServiceClient` or `MockWebServiceServer` to simulate remote SOAP? Why is a separate sandbox transport test still needed?

### Exercise F — GraphQL nullable vs. non-null

The schema defines `Quote!`, yet the resolver returns null. Describe null propagation, `errors`, and how to ensure confidential exception details are never exposed. Note that status codes depend on response media type and implementation rather than one fixed number without a contract.

### Exercise G — SOAPAction

A `@PayloadRoot` test passes even with a wrong SOAPAction. Why? Add action mapping/validation and a negative HTTP test when the WSDL requires a specific action.

### Exercise H — Suite cost

A team proposes turning 500 GraphQL contract assertions into `@SpringBootTest(RANDOM_PORT)` to "match production." Explain startup, state, and concurrency costs, and propose keeping many `@GraphQlTest` cases, a few transport smoke tests, and schema/consumer query contracts. Which test tier is still required to catch broken DB queries?

### Exercise I — Risk scoring

Score three risks using Impact/Likelihood/Escape (1–5): schema rename, auth leak, TLS certificate mismatch. Build a priority table and explain why scores are a conversation aid rather than a substitute for threat modeling or compliance mandates.

## 33. Pre-finalization strategy review checklist

- [ ] Does every test identify the specific bug or risk it exists to catch?
- [ ] Do I know which SUT and collaborators are real, mocked, or faked?
- [ ] Have I separated **contracts** from **transport**, keeping both where needed?
- [ ] For GraphQL, are schemas, arguments, field selection, and error shapes guarded?
- [ ] Are GraphQL `data` and `errors` asserted together without equating HTTP 200 to business success?
- [ ] For GraphQL HTTP, are method, path, Content-Type, and Accept verified per server media type/version?
- [ ] Are field/object-level authorization, query complexity, and mutation idempotency tested when high-risk?
- [ ] For SOAP, are XML root QNames, namespace URIs, XSD cardinalities/sequences, and response payloads verified?
- [ ] Is the published WSDL tested separately when clients generate from WSDL?
- [ ] Are SOAP 1.1/1.2 envelopes, media types, and SOAPAction/WS-Addressing checked against bindings?
- [ ] Are SOAP Fault codes/details verified without accepting generic HTML 500s as valid SOAP contracts?
- [ ] Does the SOAP client adapter use `MockWebServiceServer` while SOAP server endpoints use `MockWebServiceClient`?
- [ ] Are mocked payload tests never misreported as production HTTP/TLS/mTLS verification?
- [ ] Are WS-Security, certificates, signatures, timestamps, MTOM, attachments, and gateways tested per risk?
- [ ] Do domain/business tests exercise real logic rather than echoing stubbed mock returns?
- [ ] Do live-server HTTP tests use random ports and isolated environments without touching production?
- [ ] Do error messages avoid leaking stack traces, credentials, SQL, or customer data?
- [ ] Is test data deterministic, cleaned up, and free of execution-order dependencies?
- [ ] Does our breaking-change workflow pair schema diffs with consumer contract tests when serving multiple clients?
- [ ] Do I avoid inflating integration test counts when no extra fault-detection power is gained?
- [ ] Are untested risks and out-of-scope boundaries documented clearly?

**Key takeaway:** Select tests **based on risk and observability**, not tool labels. GraphQL schemas and resolvers can be protected thoroughly by `@GraphQlTest`; SOAP payloads, QNames, and XSDs can be protected by `MockWebServiceClient`. Yet whenever risks live in HTTP media types, SOAPAction, servlet mappings, TLS, or interoperability, send traffic across the **matching real transport**. And even when transport tests pass, business logic is proved only when **real business code runs and assertions verify the actual outcome**.

### References

- Spring Boot 3.5 — Testing Spring GraphQL `@GraphQlTest` and HTTP testers: https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html
- Spring for GraphQL — `GraphQlTester` and transport variants: https://docs.spring.io/spring-graphql/reference/testing.html
- Spring Boot 3.5 — Spring Web Services: https://docs.spring.io/spring-boot/3.5/reference/io/webservices.html
- Spring Web Services — `MockWebServiceClient`/`MockWebServiceServer` and XML assertions: https://docs.spring.io/spring-ws/docs/4.1.4/reference/html/
- Spring Web Services — `MockWebServiceClient` API: https://docs.spring.io/spring-ws/docs/current/api/org/springframework/ws/test/server/MockWebServiceClient.html
- GraphQL — Serving over HTTP, data/errors/media types: https://graphql.org/learn/serving-over-http/
- GraphQL-over-HTTP draft specification (review version/status before treating as a deployed MUST): https://github.com/graphql/graphql-over-http/blob/main/spec/GraphQLOverHTTP.md
- W3C SOAP 1.2 Part 1: https://www.w3.org/TR/soap12-part1/
- W3C XML Schema 1.1: https://www.w3.org/TR/xmlschema11-1/
- RFC 9110 — HTTP Semantics: https://www.rfc-editor.org/rfc/rfc9110