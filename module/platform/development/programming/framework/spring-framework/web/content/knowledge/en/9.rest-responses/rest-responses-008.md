# Keeping API Contracts Stable When Data Structures Change in Spring MVC

## 1. An API Contract Is a Promise to Clients

A REST API may continue running fine on the backend after changing a DTO, entity, or database structure while **older clients stop working**. This happens when the structure or meaning of data over HTTP changes outside what clients were promised.

Example initial JSON contract:

```http
GET /api/v1/products/7 HTTP/1.1
Accept: application/json
```

```http
HTTP/1.1 200 OK
Content-Type: application/json

{"id":7,"name":"Notebook","price":129000}
```

Clients may rely on the following assumptions:

- The URL and HTTP method remain `GET /api/v1/products/{id}`.
- On success, status is `200` and body is a JSON object.
- Field `id` is a stable identifier number.
- Field `name` always contains the product name.
- Field `price` is a number meaning **Vietnamese đồng (VND)**, not suddenly turned into a string or cents.
- When the product does not exist, the endpoint returns `404` in a documented way.
- Clients are not forced to parse new fields, and the server does not arbitrarily remove published fields.

Suppose the backend renames the Java property from `name` to `displayName`, switches money from `BigDecimal` to `Money`, and moves the database to a new table. These internal changes **do not force the old JSON to change**. The API contract is a public representation layer independent of domain models and persistence schemas.

If the server silently replaces the old JSON with:

```json
{
  "id": 7,
  "displayName": "Notebook",
  "pricing": {"amount": 129000, "currency": "VND"}
}
```

then clients looking for `response.name` and `response.price` will break. This is a **breaking** change for clients depending on the old fields, even though the data still describes the same product.

**Focus of this lesson:** managing the evolution of request/response structures in **Spring Web MVC** so the system can grow without disrupting consumers using supported contracts. Mechanisms used include request/response DTOs, JSON serialization with Jackson, versioning, adapter mapping, OpenAPI documentation, and contract tests.

## 2. What Does a "Contract" Include Beyond JSON Fields?

An API contract is not merely class or DTO names. Observable client-facing aspects must be specified:

| Contract aspect | Example | What must stay stable |
| --- | --- | --- |
| Endpoint | `GET /api/v1/products/7` | URL, path params, HTTP method |
| Request headers | `Content-Type`, `Accept`, auth headers | Required headers, supported media types |
| Request body | `{"name":"Notebook"}` | Field names, types, required/optional, constraints |
| Response status | `200`, `201`, `400`, `404` | Success/failure semantics |
| Response body | `{"id":7,"name":"Notebook"}` | JSON shape, types, nullability, and meaning |
| Error shape | `{"code":"PRODUCT_NOT_FOUND",...}` | Stable fields that clients read |
| Pagination | `items`, `nextCursor` | Shape, ordering, cursor/offset semantics |
| Time, money, IDs | ISO-8601, VND, opaque IDs | Units, timezone, precision, formatting |
| Response headers | `ETag`, `Location`, cache headers | Client caching, redirect/creation semantics |
| Behavioral rules | Pricing, inventory, sorting | Business rules affecting clients |

For example, keeping the JSON key `price` while changing its meaning from **VND** to **cents** is still a breaking change. Keeping the enum name `ACTIVE` while interpreting the state differently than before can also break clients. Changing a response code from `404` to `200` with an error body can trick consumers into treating failures as success.

**Distinguishing two directions of compatibility:**

- **Server backward compatibility:** requests from older clients are still accepted and responses understood by older clients preserve the contract.
- **Client forward compatibility:** clients are designed to ignore unknown new fields, handle unknown enum values, and not depend on JSON key order, where the contract allows.

A server wanting to add response fields within the same version must know its published **extensibility policy** and verify clients can tolerate them. For strict-deserializing clients or closed-schema generated SDKs, "just adding a new field" can still fail. Compatibility is therefore a **joint property of both producer and consumer**, not just how JSON looks by eye.

## 3. Classifying Data Structure Changes

| Change | Usually safe? | Conditions/recommendations |
| --- | --- | --- |
| Rename internal Java field while keeping JSON key | Usually yes | Use DTOs and mapping/`@JsonProperty`; test wire format |
| Add optional field to response | Conditional | Clients ignore unknown fields and contract permits expansion |
| Add optional field to request | Conditional | Server must apply sensible defaults when older clients omit it |
| Add a new endpoint | Usually yes | Older endpoints keep working |
| Change key order inside a JSON object | Usually yes | JSON objects guarantee no semantic key order |
| Remove/rename a published response field | Breaking | Keep v1 or create v2 |
| Change `price: number` to `price: string` | Breaking | Consumer parsers and logic may fail |
| Change flat field to nested object | Breaking | E.g., `price` to `pricing.amount` |
| Change value meaning/unit under the same key | Breaking | Must version and document clearly |
| Add a required request field | Breaking | Older clients lack the field; make optional/default or create v2 |
| Turn an optional field into required | Breaking | Previously valid requests may be rejected |
| Change non-null to nullable / vice versa | Potentially breaking | Consumers dereferencing or validating may depend on it |
| Add an enum response value | Conditional | Do clients handle unknown enum values? |
| Change status/error code or error schema | Potentially breaking | Preserve semantics and publish migration |
| Enforce pagination on an endpoint that returned the full list | Potentially breaking | Older clients might fail to fetch full data |
| Change ordering of a result array | Potentially breaking | If the contract promised sorting by specific criteria |
| Tighten validation, lower size limits, or rate limits | Potentially breaking | Previously valid requests may fail |

This table is an **impact assessment**, not an automatic rule for every client. Microsoft and other major API ecosystems emphasize that breaking-change definitions must be explicit: some treat adding a JSON field as compatible, others treat it as a contract change. Pick a policy, document it, and apply it consistently.

### Stability of "Shape" and "Meaning"

Compare two responses:

```json
{"amount": 15.75, "currency": "USD"}
```

```json
{"amount": 1575, "currency": "USD"}
```

Same field names, same JSON numbers, yet one API uses **dollars** and the other uses **cents**. Switching without versioning the contract can make clients miscalculate money by 100x. Documentation must therefore describe **units, rounding, range, and meaning**, in addition to JSON types.

Similarly, `null`, absent fields, empty string `""`, number `0`, and empty array `[]` are not always equivalent. Clients may distinguish "none", "unknown", and "present empty value"; substituting one for another must be evaluated as a contract change.

## 4. Do Not Use JPA Entities/Domain Objects Directly as the Public API

A common cause of breaking changes is letting JSON responses mirror entire internal objects:

```java
@GetMapping("/users/{id}")
public UserEntity getUser(@PathVariable long id) {
    return repository.findById(id).orElseThrow();
}
```

This is an **anti-pattern example** illustrating the principle, not a standalone program. If `UserEntity` renames columns/properties, adds relationships, or contains `passwordHash`, the JSON structure can change accidentally or leak data. Lazy loading/circular references can also cause serialization failures.

A more stable design:

```text
Database schema / JPA entities
           |
           v
Domain model + business services
           |
           v
API mapper for each contract
           |
     +-----+-----+
     |           |
     v           v
ProductV1Dto   ProductV2Dto
     |           |
     v           v
JSON v1       JSON v2
```

**Input DTOs** are also separated from **response DTOs**. Inputs contain only fields clients are allowed to supply; responses expose only promised fields. Java 17 `record`s conveniently express immutable structures, though using records **does not automatically guarantee an unchanged API**: component names, types, Jackson annotations, and mapper settings all affect the wire format.

Avoid automatic reflection copying from entire entities to DTOs if adding a property could silently alter JSON. Explicit mappers take a few more lines yet are easy to review and test.

## 5. Mechanisms to Preserve JSON Names When Renaming Java Fields

Spring MVC uses `HttpMessageConverter` to read/write bodies, typically the Jackson JSON converter in Spring Boot Web apps. If you refactor Java property `name` to `displayName` while wanting clients to still see JSON `"name"`, declare:

```java
public record ProductV1(
        long id,
        @JsonProperty("name") String displayName,
        BigDecimal price) {}
```

This snippet requires importing `com.fasterxml.jackson.annotation.JsonProperty` and `java.math.BigDecimal`. `new ProductV1(7L, "Notebook", new BigDecimal("129000"))` is serialized by Jackson with **JSON key `name`**, not `displayName`. The annotation pins the external name while Java code can use `displayName()`.

Another case is **accepting an alternate name in request input** during a transition period:

```java
public record PreviewRequest(
        @JsonAlias("displayName") String name,
        BigDecimal price) {}
```

In Jackson 2, `@JsonAlias` allows deserializing from `"displayName"` or the primary name `"name"`, while **not changing the serialized output name**: the primary name remains `name`. This helps when only changing how clients submit a field and the server supports both. However:

- Do not treat `@JsonAlias` as a complete versioning strategy: it does not handle nested structures, new types, units, or different business semantics.
- If both `name` and `displayName` appear in one JSON payload, input order can make the later value overwrite the earlier one. Define an explicit policy rejecting ambiguous payloads if required, rather than silently accepting both.
- Never use aliases to accidentally expose fields clients are not authorized to control.
- Keep annotations, mapper settings, and contract tests aligned with the API version.

Another way to preserve the legacy structure is building a separate DTO and mapping explicitly. That is usually easier to control for larger changes.

## 6. Runnable Example: Maintaining v1 and Expanding v2 in Spring MVC

Illustrative goals:

- `GET /api/v1/products/{id}` preserves the legacy JSON containing `id`, `name`, `price`, even when the Java DTO uses component `displayName`.
- `GET /api/v2/products/{id}` publishes the new representation with `displayName`, `pricing: {amount, currency}`, and `sku`.
- `POST /api/v1/products/preview` accepts request field `name` or alias `displayName`, while still returning JSON field `name`.
- `MockMvc` tests block regressions that would unintentionally alter `v1`'s shape.

Storage is simulated with in-memory objects only; the example has no database, authentication, distributed cache, or real commerce logic.

### 6.1. Maven Structure

```text
api-contract-demo/
├── pom.xml
└── src/
    ├── main/java/example/contract/
    │   ├── ApiContractApplication.java
    │   └── ProductController.java
    └── test/java/example/contract/
        └── ProductContractTest.java
```

**`pom.xml`**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>

    <groupId>example</groupId>
    <artifactId>api-contract-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-validation</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

**`src/main/java/example/contract/ApiContractApplication.java`**

```java
package example.contract;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ApiContractApplication {
    public static void main(String[] args) {
        SpringApplication.run(ApiContractApplication.class, args);
    }
}
```

### 6.2. Two Response DTOs Backed by One Business Data Source

**`src/main/java/example/contract/ProductController.java`**

```java
package example.contract;

import com.fasterxml.jackson.annotation.JsonAlias;
import com.fasterxml.jackson.annotation.JsonProperty;
import jakarta.validation.Valid;
import jakarta.validation.constraints.DecimalMin;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

import java.math.BigDecimal;

@RestController
public class ProductController {

    // Internal model; not returned directly over HTTP.
    private record Product(
            long id, String name, BigDecimal price, String sku) {}

    // JSON v1 contract: id, name, price.
    // Java component renamed to displayName, JSON still keeps "name".
    public record ProductV1(
            long id,
            @JsonProperty("name") String displayName,
            BigDecimal price) {}

    // JSON v2 contract: id, displayName, pricing, sku.
    public record Money(BigDecimal amount, String currency) {}

    public record ProductV2(
            long id, String displayName, Money pricing, String sku) {}

    // Supports request-side alias during migration.
    public record PreviewRequest(
            @NotBlank @JsonAlias("displayName") String name,
            @NotNull @DecimalMin("0.01") BigDecimal price) {}

    // Output v1 continues keeping the legacy name.
    public record PreviewResponse(String name, BigDecimal price) {}

    @GetMapping(path = "/api/v1/products/{id}",
                produces = MediaType.APPLICATION_JSON_VALUE)
    public ProductV1 getV1(@PathVariable("id") long id) {
        Product product = load(id);
        return new ProductV1(
                product.id(), product.name(), product.price());
    }

    @GetMapping(path = "/api/v2/products/{id}",
                produces = MediaType.APPLICATION_JSON_VALUE)
    public ProductV2 getV2(@PathVariable("id") long id) {
        Product product = load(id);
        return new ProductV2(
                product.id(),
                product.name(),
                new Money(product.price(), "VND"),
                product.sku());
    }

    @PostMapping(
            path = "/api/v1/products/preview",
            consumes = MediaType.APPLICATION_JSON_VALUE,
            produces = MediaType.APPLICATION_JSON_VALUE)
    public PreviewResponse preview(
            @Valid @RequestBody PreviewRequest input) {
        return new PreviewResponse(input.name(), input.price());
    }

    private Product load(long id) {
        if (id != 7L) {
            throw new ResponseStatusException(
                    HttpStatus.NOT_FOUND, "Product not found");
        }
        return new Product(
                7L, "Notebook", new BigDecimal("129000"), "NB-007");
    }
}
```

**Decisions ensuring stability:**

1. `Product` is the internal model. It never appears directly in HTTP responses.
2. `ProductV1` uses Java component `displayName` while `@JsonProperty("name")` preserves JSON key `name`. Because v1 clients still read the old name, refactoring Java alone causes no breaking change.
3. `ProductV2` is a **new** response contract: nested `pricing` and `currency`, without pretending v1 clients understand this representation.
4. Both v1 and v2 call the same `load` function to avoid creating two data sources; only the **API mapping** differs.
5. `PreviewRequest` includes only fields clients are allowed to send. `@Valid` + Jakarta Validation verify non-blank text, price presence, and price at least `0.01`. Clients cannot modify `sku`, `id`, or permissions through this DTO.
6. `@JsonAlias` softens **input** only. The preview response still uses `PreviewResponse.name`, so legacy clients see no response field change.
7. The example mocks a single product ID `7`. Other IDs receive `404` via `ResponseStatusException`. Real applications need services, persistence, and resource authorization.

### 6.3. Sending Requests and Comparing Responses

Run the project from the directory containing `pom.xml`:

```bash
mvn test
mvn spring-boot:run
```

The two commands run sequentially. `mvn test` should succeed before launching the application. When Spring Boot starts on the default port `8080`:

**API v1 preserves JSON:**

```bash
curl -i \
  -H 'Accept: application/json' \
  http://localhost:8080/api/v1/products/7
```

Response status and body (omitting unrelated HTTP headers):

```http
HTTP/1.1 200
Content-Type: application/json

{"id":7,"name":"Notebook","price":129000}
```

The key `name` appears thanks to `@JsonProperty` even though the Java record component is named `displayName`. Do not rely on JSON object key ordering when building clients.

**API v2 has the new structure:**

```bash
curl -i \
  -H 'Accept: application/json' \
  http://localhost:8080/api/v2/products/7
```

Main body:

```json
{
  "id": 7,
  "displayName": "Notebook",
  "pricing": {"amount": 129000, "currency": "VND"},
  "sku": "NB-007"
}
```

Whitespace/newlines in the JSON above are formatted for readability; the server may return a single line. These are two **parallel contracts**, not v1 clients automatically understanding v2.

**Requests from older clients still work:**

```bash
curl -i -X POST http://localhost:8080/api/v1/products/preview \
  -H 'Content-Type: application/json' \
  -H 'Accept: application/json' \
  -d '{"name":"Notebook","price":129000}'
```

Body:

```json
{"name":"Notebook","price":129000}
```

**Requests using the new alias are also accepted:**

```bash
curl -i -X POST http://localhost:8080/api/v1/products/preview \
  -H 'Content-Type: application/json' \
  -d '{"displayName":"Notebook","price":129000}'
```

Body remains:

```json
{"name":"Notebook","price":129000}
```

This is an example of controlled **tolerant input**, not a policy accepting arbitrary unknown fields. If a request sends both `name` and `displayName`, define an explicit rule (e.g., returning `400` when two values target the same property) in a real version; the example only illustrates clients sending **one** of the two names.

**Nonexistent ID:**

```bash
curl -i -H 'Accept: application/json' \
  http://localhost:8080/api/v1/products/999
```

Status is typically `404 Not Found`. Detailed error JSON comes from exception handlers, Spring Boot error configuration, or Spring MVC `ProblemDetail` depending on environment. **Do not depend on an undocumented ad-hoc error body**; if error responses are part of the contract, design and test a dedicated error schema.

## 7. Contract Tests with MockMvc: Verifying Real Shapes over HTTP

Unit-testing Java DTOs or mappers alone is not enough. Jackson config, controller annotations, converters, media types, and response statuses also shape the HTTP contract. A test sending requests through `MockMvc` catches regressions at the HTTP boundary without opening a real server port.

**`src/test/java/example/contract/ProductContractTest.java`**

```java
package example.contract;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class ProductContractTest {

    @Autowired
    MockMvc mvc;

    @Test
    void v1KeepsPublishedNamesAndShape() throws Exception {
        mvc.perform(get("/api/v1/products/7")
                .accept(MediaType.APPLICATION_JSON))
            .andExpect(status().isOk())
            .andExpect(content()
                    .contentTypeCompatibleWith(MediaType.APPLICATION_JSON))
            .andExpect(jsonPath("$.id").value(7))
            .andExpect(jsonPath("$.name").value("Notebook"))
            .andExpect(jsonPath("$.price").value(129000))
            .andExpect(jsonPath("$.displayName").doesNotExist())
            .andExpect(jsonPath("$.pricing").doesNotExist());
    }

    @Test
    void v2PublishesNewStructure() throws Exception {
        mvc.perform(get("/api/v2/products/7")
                .accept(MediaType.APPLICATION_JSON))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.displayName").value("Notebook"))
            .andExpect(jsonPath("$.pricing.amount").value(129000))
            .andExpect(jsonPath("$.pricing.currency").value("VND"))
            .andExpect(jsonPath("$.sku").value("NB-007"))
            .andExpect(jsonPath("$.name").doesNotExist())
            .andExpect(jsonPath("$.price").doesNotExist());
    }

    @Test
    void requestOldNameStillWorks() throws Exception {
        mvc.perform(post("/api/v1/products/preview")
                .contentType(MediaType.APPLICATION_JSON)
                .accept(MediaType.APPLICATION_JSON)
                .content("{\"name\":\"Notebook\",\"price\":129000}"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.name").value("Notebook"))
            .andExpect(jsonPath("$.displayName").doesNotExist());
    }

    @Test
    void requestAliasDoesNotRenameV1Response() throws Exception {
        mvc.perform(post("/api/v1/products/preview")
                .contentType(MediaType.APPLICATION_JSON)
                .accept(MediaType.APPLICATION_JSON)
                .content("{\"displayName\":\"Notebook\",\"price\":129000}"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.name").value("Notebook"))
            .andExpect(jsonPath("$.displayName").doesNotExist());
    }

    @Test
    void invalidRequestIsRejected() throws Exception {
        mvc.perform(post("/api/v1/products/preview")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"name\":\"\",\"price\":0}"))
            .andExpect(status().isBadRequest());
    }

    @Test
    void missingProductHasNotFoundStatus() throws Exception {
        mvc.perform(get("/api/v1/products/999"))
            .andExpect(status().isNotFound());
    }
}
```

Run:

```bash
mvn test
```

Success means all test cases above pass and Maven exits with code `0`. Summary output typically resembles `Tests run: 6, Failures: 0, Errors: 0, Skipped: 0`; exact timing, logs, and test order vary by environment.

**Test scope:** these tests protect the **demo** v1, v2, and error paths above. In a real project, add tests for missing fields, nulls, unknown fields, enums, BigDecimal precision, timestamps, pagination, authorization, and error responses. Keep contract fixtures from an approved API release to catch unintended changes; tests newly generated alongside current code without comparing against the prior contract can "pass right alongside a breaking change."

## 8. How to Evolve While Still Serving Older Clients

An effective process is **expand → migrate → contract**:

1. **Inventory existing consumers and contracts.** List endpoints, fields, types, required/nullable flags, units, error codes, pagination, SDKs, and mobile apps that cannot update instantly. Identify which clients must be preserved.
2. **Identify changes that could affect clients.** Do not evaluate only from Java class diffs; compare old and new JSON/HTTP schemas as well as semantics. Flag major changes as breaking.
3. **Expand server capabilities without deleting v1.** Add v2 or a compatible feature; map both DTOs from the same domain model. For small request field renames, temporarily accept old/new aliases with explicit ambiguity rules.
4. **Publish new documentation, SDKs, and examples.** Publish JSON samples, OpenAPI schemas, units/timezones, API error contracts, and a v1-to-v2 upgrade path. For external partners, set a bounded support window for older versions.
5. **Migrate clients in waves.** Use traffic analytics, metrics, or version headers to check remaining v1 consumers; never assume "backend deployed" means clients have upgraded.
6. **Monitor real contract errors.** Track `400`/`404`/`406` rates, client-side deserialization failures, and legacy alias usage; avoid logging sensitive payloads. Support rollback during the transition window.
7. **Retire the old contract only under the published deprecation policy.** Act after confirming remaining clients and support milestones. Removing a v1 endpoint is an externally visible change requiring coordinated release.

During multi-instance rolling deployments, old and new servers coexist. A migration succeeds only if shared data/databases/message events tolerate both versions during rollout. That is why you should keep **both read and write paths** compatible when updating shared schemas, instead of upgrading the database and immediately dropping old fields.

### When You Rename a Field Without Needing v2

If you only rename Java fields for clarity, use `@JsonProperty("oldName")` or an API mapper to keep JSON identical. Do not automatically create a new API version for **every** internal refactor.

### When You Need v2

If `price: 129000` turns into `pricing: {amount:129000,currency:"VND"}`, older clients cannot guess the new path. A parallel v2 is an easy-to-explain choice. Do not delete `price` from v1 merely because v2 exists.

### When Adding an Optional Field

If the contract states clients must ignore unknown response fields, adding optional `description` is usually accepted:

```json
{"id":7,"name":"Notebook","price":129000,"description":"A5"}
```

However, clients generated from closed schemas may fail when encountering unfamiliar fields. CI should therefore check consumer behavior, and organizations must publish a schema-extension policy rather than assuming additive changes are always 100% safe.

## 9. Choosing an API Versioning Approach

| Approach | Example | Strengths | What to manage |
| --- | --- | --- | --- |
| Version in URL | `/api/v1/products`, `/api/v2/products` | Easy to see and test, clear routing | Parallel URLs, multiple mappings |
| Version via header | `X-Api-Version: 2` | Stable URIs | Clients/proxies/caches must handle the header |
| Version via media type | `Accept: application/vnd.example.product-v2+json` | Ties version to representation | More complex Content Negotiation |
| Version via query param | `?version=2` | Easy to try | Cache policy, docs, and routing must align |

In Spring MVC 6.1, URL versioning is straightforward to demonstrate with separate `@GetMapping` handlers. Do not rely on specialized versioning annotations introduced in later Spring major versions for a runnable Boot 3.3.5 example.

Define **version scope** clearly: is it whole-API versioning, resource-representation versioning, or per-endpoint contracts? If only one field changes on one product type, resource-specific versioning may fit project policy, though avoid an unpredictable mix of URL, header, and query versioning. Never treat a `v2` label as license to make arbitrary breaking changes inside v2 later.

### Deprecation Does Not Mean Immediate Removal

Once v2 exists, v1 can be marked deprecated in docs/API catalogs, signaled via appropriate standard headers if the organization uses them, and given a sunset plan. Avoid announcing deadlines the operations team cannot uphold. Every client needs a migration guide, e.g., a field mapping:

| v1 | v2 |
| --- | --- |
| `name` | `displayName` |
| `price` (VND) | `pricing.amount` (VND) |
| No currency field | `pricing.currency = "VND"` |
| No SKU in v1 output | `sku` added in v2 |

The table illustrates only the example data; real contracts must also document nullability, units, error semantics, and other endpoints.

## 10. Areas Prone to Silent Breaking Changes

### 10.1. Required, Optional, Null, and Absent

JSON inputs:

```json
{}
```

```json
{"description":null}
```

```json
{"description":""}
```

These three inputs can have distinct meanings: no change requested, delete description, set description to an empty string. When designing PATCH, represent **absent** and **present null** explicitly; a plain DTO with only `String description` collapses both into Java `null`. Consider JSON Merge Patch, JSON Patch, or a command DTO with field-presence tracking when genuinely needed.

Never add `@NotNull` to a field older clients may omit and call it compatible. When adding a new field to v1 requests, usually make it optional with a default preserving prior behavior.

### 10.2. Numeric Types and Precision

`Integer`, `Long`, `BigDecimal`, and floating-point types behave differently. JavaScript clients have a limited safe integer range; large IDs may require **opaque identifier strings** if specified from the start. Never switch a live endpoint from JSON number to string.

For money, prefer explicitly documenting `amount`, `currency`, units, and rounding rules. `BigDecimal` avoids binary `double` errors, yet does not define a monetary contract on its own. Switching units from VND to minor units or USD is a semantic breaking change.

### 10.3. Date/Time and Timezones

`"2026-10-21"` (local date), `"2026-10-21T04:00:00Z"` (instant), and a timezone-less timestamp string are not freely interchangeable. Contracts should pick a type and specify timezone (e.g., UTC), fractional-second precision, and exact ISO-8601 format. Upgrading Jackson config for Java Time types can alter JSON output; keep serialized fixture tests when upgrading libraries.

### 10.4. Expanding Enums

Suppose a client writes:

```java
switch (status) {
    case ACTIVE -> showActive();
    case INACTIVE -> showInactive();
}
```

This is an **illustrative snippet** assuming `status` is an enum and helper methods exist in client code. Adding `SUSPENDED` in a response can break clients that cannot handle it, especially with strict enum parsers. For extensible enums, design unknown fallbacks from the start and document forward-compatibility policy. For closed enums, adding a value may be considered breaking.

### 10.5. Pagination and Arrays

An API that previously returned everything:

```json
[{"id":1},{"id":2},{"id":3}]
```

if changed to:

```json
{"items":[{"id":1},{"id":2}],"nextCursor":"abc"}
```

changes the top-level type from array to object and omits items older clients expect. This is a breaking change, even if done for performance. When adding new pagination, use v2 or a new endpoint; define page size, stable ordering, cursor semantics, and what happens when resources change during pagination.

### 10.6. Error Schemas and Statuses

Clients typically handle errors by `status` and machine-readable `code`, not just human messages. Changing `404` to `200` with `{"success":false}` or renaming `error.code` to `reason` breaks retry logic and UIs. Design stable error responses with useful codes and without internal stack traces. If using `ProblemDetail` per RFC 9457, clearly define extension field contracts and how consumers read `type`/`status`/`detail`; do not mix error schemas arbitrarily.

### 10.7. Jackson Configuration and Response Advice

Changing `ObjectMapper`, global `@JsonInclude`, naming strategies, timezones, property visibility, polymorphic typing, or `ResponseBodyAdvice` can alter JSON **for every endpoint**. Before applying, test representative endpoints in every version.

`@JsonAlias` only supports deserialization aliases; `@JsonProperty` controls property names; `@JsonIgnore` can make fields vanish; `@JsonInclude(Include.NON_NULL)` can turn explicit null fields into absent fields. Never call these annotations "internal" when they affect the wire contract.

## 11. Documenting Contracts with OpenAPI and Testing in CI

OpenAPI describes endpoints, operations, parameters, request/response media types, status codes, and JSON schemas. An illustrative v1 schema excerpt:

```yaml
openapi: 3.0.3
info:
  title: Products API
  version: 1.0.0
paths:
  /api/v1/products/{id}:
    get:
      parameters:
        - in: path
          name: id
          required: true
          schema:
            type: integer
            format: int64
      responses:
        "200":
          description: Product v1
          content:
            application/json:
              schema:
                $ref: "#/components/schemas/ProductV1"
        "404":
          description: Product not found
components:
  schemas:
    ProductV1:
      type: object
      required: [id, name, price]
      properties:
        id: {type: integer, format: int64}
        name: {type: string}
        price:
          type: number
          description: Amount in VND
```

This is an **illustrative OpenAPI excerpt for one endpoint**; it does not describe the entire project in section 6 or a complete error schema. In real code, account for validation constraints, nullability, examples, response headers, auth, and all error statuses.

A change-control pipeline can:

1. Store published schemas as baselines without auto-updating baselines just to make tests pass.
2. Generate/maintain OpenAPI from the new build or versioned contract schemas.
3. Run **schema diff/compatibility checks** to catch removed/renamed/retyped fields, changed required flags, missing endpoints, or changed statuses.
4. Run `MockMvc` integration tests against legacy request/response fixtures.
5. Run **consumer-driven contract tests** encoding real assumptions of key clients.
6. Block merge/deploy or require a version bump when unapproved breaking changes appear.
7. On release, update docs, changelogs, SDKs, and migration guides.

Comparing OpenAPI schemas alone is insufficient: changing units from VND to USD, changing sort order, or changing total calculations can leave the JSON schema identical. Business-semantics tests and consumer tests are also required.

### Should Snapshot Tests Compare Raw JSON Strings?

Capturing the entire body and comparing character-by-character catches field changes, yet fails unnecessarily when JSON object key order or whitespace shifts. Usually it is better to parse JSON and compare the **JSON tree / JSONPath per contract**. For fields whose contract defines fixed order (such as sorted arrays), check exact array order. For currency/numbers/timestamps, assert both meaning and normalized values.

### Producer Tests and Consumer Tests Differ

Producer tests ask: "Does the server still return what it promised?" Consumer tests ask: "Do real clients still work with the new server's requests/responses?" If you only test the new server against new DTOs, a rename that breaks older clients can slip through. When multiple teams own multiple clients, share contract fixtures and run tests on both sides.

## 12. Review Process for a DTO/JSON Change

Suppose a developer proposes a PR: "Move `Product.price` to `Product.pricing.amount` because the backend changed its Money model."

Review in sequence:

- **Current public contracts:** which APIs return `price`? v1/v2, mobile, SDKs, partners?
- **Wire-format diff:** how do actual JSON keys/types/meanings differ before and after, for both success and error cases?
- **Consumer compatibility:** if older clients deserialize the new response, where could they fail?
- **Non-breaking option:** keep the v1 DTO mapper returning `price`, add v2 for `pricing`.
- **Request compatibility:** which fields do older clients send? Were any fields newly marked required?
- **Status and metadata:** did `Content-Type`, statuses, pagination, or error codes change?
- **Security:** does the new entity have sensitive fields accidentally exposed by the JSON serializer?
- **Tests:** do v1 fixtures still pass, new v2 fixtures pass, and validation/error cases match?
- **Release:** are docs and the v1 support window clear? Is telemetry tracking old clients?

Example appropriate diff:

```diff
- // V1 controller returns domain Product directly.
- return productService.find(id);
+ // V1 controller preserves the legacy JSON contract via mapping.
+ Product product = productService.find(id);
+ return new ProductV1(
+         product.getId(),
+         product.getDisplayName(),
+         product.getMoney().getAmount());
```

This is an **architectural illustration diff** depending on hypothetical service/domain classes and cannot be pasted straight into the runnable project in section 6. It shows that what must be protected is the representation at the HTTP boundary, not internal method names.

## 13. Practical Rules of Thumb

1. **Version public contracts, not database schemas.** One new schema can serve both v1 and v2 via mappers.
2. **Keep input DTOs and output DTOs separate.** This prevents over-posting while controlling response fields.
3. **Define "compatible" by real consumers.** Document unknown-field/enum fallbacks upfront; do not assume every SDK is tolerant.
4. **Never arbitrarily rename, retype, change units, or alter semantics of v1 fields.** When change is necessary, create v2 with migration.
5. **Make new request fields optional when backward compatibility is needed**, with defaults preserving old behavior; never silently add required request fields.
6. **Keep null/absent/empty rules consistent.** Especially critical for PATCH and DTOs with primitive defaults.
7. **Limit global Jackson settings and response wrappers.** Every global change needs contract regression tests.
8. **Publish enforceable deprecation/sunset dates.** Measure legacy version usage before removal.
9. **Test status, headers, content type, body, and error contracts.** Do not assert only that the controller returns the right Java class.
10. **Enforce security in the service layer.** Narrow DTOs, validation, and authorization are independent responsibilities; never rely on Jackson annotations for access control.

## 14. Self-Check Exercises

1. The backend renames Java field `displayName`, while clients still need JSON `name`. How can you use `@JsonProperty`, and when is a DTO mapper clearer?
2. Why is adding a response field generally safer than removing one, yet not guaranteed safe for every client?
3. Older clients send requests without `currency`. How can you add currency without turning old requests into `400`?
4. Keeping `price` as a JSON number while switching units to cents: is the contract preserved? Why?
5. Does `@JsonAlias("displayName")` make responses automatically output `displayName` instead of `name`?
6. Why can replacing an array response with `{"items":[...]}` be a breaking change?
7. Do you need to change the URL from `/v1` to `/v2` when only renaming internal variables?
8. Beyond Java classes, what elements should a controller's contract tests compare?
9. When two server versions run side by side during a rolling deploy, which database/message schema changes could break the older instance?
10. If `null` and an absent field previously carried two meanings, does a simple Java `String` DTO always preserve that distinction?

**Answer hints:** (1) Pin the JSON key or map DTOs; (2) strict clients and closed SDKs may reject unknown fields; (3) optional/default preserving legacy behavior or a new version; (4) no, semantics changed; (5) no, aliases apply on deserialization; (6) top-level type and pagination changed; (7) unnecessary if the wire contract stays identical; (8) URL/method/status/headers/media type/shape/meaning/errors; (9) schemas supporting only the new instance can break the old one; (10) no, presence-aware representation is needed when it matters.

## 15. References

- [Spring MVC: ResponseBody and HttpMessageConverter](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/responsebody.html)
- [Spring Framework: Jackson JSON](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/jackson.html)
- [Spring Boot 3.3: Testing Spring Boot Applications and MockMvc](https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html)
- [Jackson 2: JsonAlias Javadoc](https://fasterxml.github.io/jackson-annotations/javadoc/2.12/com/fasterxml/jackson/annotation/JsonAlias.html)
- [Microsoft: Web API Design Best Practices](https://learn.microsoft.com/en-us/azure/architecture/best-practices/api-design)
- [Microsoft: API Design and Versioning](https://learn.microsoft.com/en-us/azure/architecture/microservices/design/api-design)
- [OpenAPI Specification 3.0.3](https://spec.openapis.org/oas/v3.0.3)
- [GitHub REST API: Breaking Changes](https://docs.github.com/en/rest/about-the-rest-api/breaking-changes)

This lesson focuses strictly on **keeping REST API contracts stable when data structures change** and the Spring MVC techniques directly relevant to that goal. The illustrative program uses Java 17 and Spring Boot 3.3.5; compatibility/versioning strategies are design rules that must be decided according to actual contracts and consumers.
