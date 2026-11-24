# Designing Response DTOs and Separating HTTP Models from Persistence Objects in Spring MVC

## 1. Lesson Objectives

When building REST APIs with Spring MVC, Java objects read from and written to the database often carry plenty of information **that does not belong in the HTTP contract**: foreign keys, internal state, administrative metadata, secret fields, lazy relations, or column names chosen for storage optimization. Returning JPA entities directly from `@RestController` tightly couples your API data and structure to the database schema and ORM behavior.

The goal is to design a **Response DTO (Data Transfer Object)** as an intentional public representation model, and keep HTTP handling in the controller instead of leaking `ResponseEntity`, status codes, or Servlet APIs into the persistence layer.

After this lesson, you will be able to:

- Distinguish domain models, persistence entities, request DTOs, response DTOs, and HTTP representations.
- Choose the right fields, structure, data types, nullability, and formats for responses that clients actually need.
- Convert entity → DTO at the service/controller boundary using explicit mappers without exposing internal fields or JPA relationship graphs.
- Use `@RestController`, `@ResponseBody`, `ResponseEntity<T>`, `Location`, statuses `200`/`201`/`204`/`404`, and appropriate error handling.
- Understand consequences regarding transactions, lazy loading, N+1 queries, pagination, security, versioning, and testing.
- Practice with **Java 17+, Spring Framework 6.x/Spring Boot 3.x, Spring Data JPA, and H2**.

The runnable examples below assume a Spring Boot project with dependencies: **Spring Web**, **Spring Data JPA**, **Validation**, **H2 Database**, **Spring Boot Test**. If the application uses Spring Boot 4/Spring Framework 7, most principles still hold, but cross-check dependencies and test APIs against your version.

## 2. Models That Should Be Separated

Do not use the word "model" for everything without defining its role:

| Type | Responsibility | Example | Return directly over HTTP? |
| --- | --- | --- | --- |
| **Persistence entity** | Database mapping, relations, ID, version, lazy loading | `CustomerEntity` with `internalMemo` | Usually **no** |
| **Domain model / business object** | Business rules, state, and invariants | `Customer`, `Money`, `Order` | Usually mapped to DTO |
| **Request DTO** | Contract for data the client is allowed to send | `CreateCustomerRequest` | Input only; must validate |
| **Response DTO** | Contract for data the client is allowed to receive | `CustomerResponse` | **Yes**, as public representation |
| **HTTP envelope** | Status, headers, media type, cache, Location | `ResponseEntity<CustomerResponse>` | Belongs to HTTP/controller boundary |
| **Error response** | Public error structure, error codes, safe messages | `ProblemDetail` or `ApiError` | Yes, under its own policy |

In the demo, a persistence object might include `id`, `displayName`, `email`, `internalMemo`, `createdAt`. The Response DTO contains only `id`, `displayName`, `email`, `createdAt`; `internalMemo` is not public data.

### Boundary Diagram

```text
                  HTTP / JSON
                      |
                      v
           CustomerController
         @RequestBody request DTO
      @Valid / status / headers / URI
                      |
                      v
             CustomerService
          business logic + transaction
          entity -> response DTO
                      |
                      v
           CustomerRepository
                JPA/Hibernate
                      |
                      v
                   Database

      Response DTO -> HttpMessageConverter/Jackson
                  -> HTTP body
```

A common organization pattern is a dedicated mapper (`CustomerMapper`), invoked in the service or application layer. The core principle is **intentional mapping before the object goes through HTTP serialization**. Controllers can handle mapping if the app is small and dependency direction stays clean; however, never push `HttpServletRequest`, `ResponseEntity`, or HTTP statuses down into repositories.

## 3. Why Not Return a JPA Entity Directly?

### 3.1. Data Exposure Risk

```java
// Example to avoid if entity contains internal fields:
@GetMapping("/customers/{id}")
public CustomerEntity find(@PathVariable long id) {
    return repository.findById(id).orElseThrow();
}
```

Jackson can serialize properties that have recognized getters; adding a getter/field to the entity in the future could accidentally expose it in JSON. Fields such as `passwordHash`, `resetToken`, `secretKey`, `internalMemo`, `riskLevel`, or tenant-private data must never be guarded merely by "hoping clients don't know they exist."

`@JsonIgnore` on an entity can block certain fields, but it forces the **persistence schema to carry HTTP contract responsibilities**. It also fails to solve the broader problem: a single entity may need different response views depending on endpoint, user role, and API version.

**A DTO restricts the serializable data surface; it does not replace authorization.** Before mapping a DTO, the service still needs to verify whether the caller is permitted to read the resource and each sensitive field. If an endpoint returns email addresses, define clearly which roles are allowed to see them.

### 3.2. Exposing Database Details and Breaking Contract Stability

Entities often evolve for performance/schema needs: renaming columns, splitting tables, adding `@OneToMany` relations, indexing, adding `@Version` fields. If response = entity, storage changes can break clients. A DTO creates an anti-corruption layer, allowing you to:

- Rename a storage field while keeping JSON `displayName`.
- Aggregate data from multiple tables into a simple response.
- Hide internal IDs or foreign keys clients do not need.
- Evolve JPA/Hibernate without forcing clients to change their structure.
- Maintain older API versions via older mappers as the domain evolves.

### 3.3. Lazy Loading, JSON Cycles, and Uncontrolled Queries

Suppose `OrderEntity` has relations to `CustomerEntity` and `OrderLineEntity`; returning the entity may cause Jackson to read a lazy relation after the transaction ends and hit `LazyInitializationException`, or trigger uncontrolled extra queries. Bidirectional relationships (`Order -> Customer -> Orders -> ...`) can cause serialization loops, massive JSON payloads, or require coupling via Jackson annotations.

Proper approach:

1. Determine exactly what data the response needs, e.g., `OrderResponse(id, customerName, List<LineResponse>)`.
2. Fetch data using an appropriate query/fetch plan **inside the transaction** or via direct projection.
3. Map to a DTO containing only the desired fields.
4. Return the DTO out of the service once persistence access is complete.

Spring Boot has **Open Session in View** enabled in some servlet/JPA configurations, but you should not rely on the session remaining open so Jackson can accidentally fire database queries while rendering the response. DTOs separate query time from render time, though **they do not fix N+1 automatically**: you must still inspect the fetch plan.

### 3.4. Do Not Use Entities as Request DTOs

Client input could include `id`, `role`, `isAdmin`, or `ownerId` even if the API only intends to allow changing `displayName`. If you bind directly into an entity and call `save`, you risk **mass assignment/overposting**. A request DTO with only editable fields acts as an **input contract allowlist**; you still need operation authorization and validation afterward.

## 4. Which Fields Should a Response DTO Contain?

Design from **client needs and API commitments** first, then decide how to map from the database.

Reasonable JSON example for a customer:

```json
{
  "id": 42,
  "displayName": "Lan",
  "email": "lan@example.com",
  "createdAt": "2026-10-21T04:00:00Z"
}
```

Choices to weigh:

- **Stable field names:** `displayName` should carry meaning the client understands, independent of a column name like `full_name_v2`.
- **Correct data types:** numbers are JSON numbers when they represent safe quantities; long identifiers exceeding JavaScript precision limits should sometimes be strings in the API.
- **Timestamps:** `Instant` typically serializes as ISO-8601 when Boot/Jackson's Java Time module is configured; specify UTC and timezone clearly. In the example, `"Z"` indicates UTC.
- **Currency:** use decimal strings or an object with `amount` and `currency` per contract; avoid `double` for money when precision matters.
- **Null/missing:** JSON `"field":null` vs. omitting the key may carry different semantics; standardize the API and test Jackson's `NON_NULL`/`NON_EMPTY` configuration if used.
- **Lists:** consider `[]` rather than `null` for empty collections if the contract specifies so; never output ORM collection proxies directly.
- **Derived fields:** URLs or computed summary fields should be built where public routing/semantics are known; do not force entities to store everything clients see.
- **Access rights:** an admin DTO may differ from a public DTO; one DTO packed with role-dependent nullable fields makes the contract hard to understand.
- **JSON root:** choose a clean object shape; each endpoint's format should be independent of Java `ResponseEntity` mechanics.

A response DTO is an **API schema with its own lifecycle**, not just a "copy of an entity with fewer fields."

## 5. Java Records, Classes, and Immutability

Java 17 `record` fits small DTOs that are immutable in their field references:

```java
public record CustomerResponse(
        Long id,
        String displayName,
        String email,
        java.time.Instant createdAt) {}
```

Benefits: concise syntax, generated constructor/accessors/`equals`/`hashCode`/`toString`, easy to test; Jackson in modern Boot supports records. However, records do not make nested graphs automatically immutable: if it contains `List<MutableItem>`, you still need an immutable copy or nested immutable DTOs.

Class DTOs fit when a specialized framework/serializer requires constructors/setters, high customizability is needed, or you need different backwards-compatibility control. **Do not use records as standard JPA entities**: JPA entities have constructor and lifecycle-management requirements; records are suited for DTOs/projections instead.

Separating input/output:

```java
public record CreateCustomerRequest(
        @jakarta.validation.constraints.NotBlank
        @jakarta.validation.constraints.Size(max = 100)
        String displayName,

        @jakarta.validation.constraints.NotBlank
        @jakarta.validation.constraints.Email
        @jakarta.validation.constraints.Size(max = 254)
        String email) {}
```

Request DTOs carry constraints because they validate **incoming data**. Response DTOs describe **public returned data**; output constraints (if applied) serve a different purpose. Do not put server-generated `id` or internal `internalMemo` into `CreateCustomerRequest` if clients are not supposed to supply them.

## 6. Mapper: Entity -> Response DTO

Simple, explicit mapper:

```java
public final class CustomerMapper {
    private CustomerMapper() {}

    public static CustomerResponse toResponse(CustomerEntity entity) {
        return new CustomerResponse(
                entity.getId(),
                entity.getDisplayName(),
                entity.getEmail(),
                entity.getCreatedAt());
    }
}
```

This is an **illustrative snippet** using `CustomerEntity` and `CustomerResponse` defined in the runnable example section; it does not run standalone.

Benefits of an explicit mapper:

- Reviews clearly show exactly which fields leave the data layer.
- Adding an entity field does not automatically expand JSON output.
- Provides a place to convert internal enums to contract strings, adjust timestamps, units, or nested DTOs.
- Easy to unit-test the mapper separately when mapping is complex, especially as new/optional fields appear.

With many DTOs, MapStruct can generate mappers at compile time and catch mapping errors early. Even when using a library, review generated behavior, unmapped field settings, and sensitive field policies. **Do not map bidirectionally unconditionally**: request DTO → entity usually needs distinct create/update logic; "reversing" a response mapper could let clients overwrite forbidden fields.

When mapping nested collections:

```java
List<LineResponse> lines = order.getLines().stream()
        .map(line -> new LineResponse(
                line.getProductCode(), line.getQuantity()))
        .toList();
```

This is an **illustration inside a method where `order` and the DTO types already exist**. Calling `getLines()` may trigger a lazy query; fetch data intentionally beforehand and then map, avoiding N+1 when processing lists of orders.

## 7. ResponseEntity<T>: Where HTTP Decisions Live

Spring MVC supports:

- Returning `CustomerResponse` directly from `@RestController`: typically the framework serializes the body and returns `200 OK` on success.
- Returning `ResponseEntity<CustomerResponse>`: adds control over status/headers, such as `201 Created` with `Location`.
- Returning `ResponseEntity<Void>`: when there is no body, such as `204 No Content` for a successful DELETE.
- Returning `ResponseEntity.of(Optional<CustomerResponse>)`: `Optional.of(dto)` yields `200` with body; `Optional.empty()` yields `404` with empty body.

Example controller deciding status:

```java
@PostMapping("/customers")
public ResponseEntity<CustomerResponse> create(
        @Valid @RequestBody CreateCustomerRequest request) {
    CustomerResponse response = service.create(request);
    URI location = ServletUriComponentsBuilder.fromCurrentRequestUri()
            .path("/{id}")
            .buildAndExpand(response.id())
            .toUri();
    return ResponseEntity.created(location).body(response);
}
```

The snippet above illustrates a controller with imports, `service`, and DTO classes already defined; a full runnable version appears below.

**201 Created** fits when the server creates a new resource. The `Location` header should point to the resource URI; the response can include the new DTO body. **200 OK** fits successful GETs or data-returning operations per contract. **204 No Content** must have no response body; avoid putting JSON on status 204. **404 Not Found** applies when a resource is not found (after authorization checks per policy). **400 Bad Request** typically applies to malformed JSON payloads, missing required input/validation errors. **409 Conflict** applies when violating resource state/concurrency conditions if the contract defines it.

Do not embed `HttpStatus`/`ResponseEntity` inside JPA entities or repositories. Pure business services can return DTOs/Results/Optionals or throw domain exceptions; controllers/advice translate outcomes into HTTP semantics.

### Must Services Return Response DTOs?

Not strictly. Both architectures can be reasonable:

1. Service/application query returns `CustomerResponse` directly because the use case serves the API and knows the public projection. The controller handles only HTTP.
2. Service/domain returns business objects, and an adapter/controller maps them to DTOs. Useful when the same logic serves message consumers, batch jobs, or other transports.

What matters is **clean dependency direction** and ensuring persistence data is never serialized directly. If a service returns a response DTO, never let that DTO import `ResponseEntity` or Servlet APIs; that keeps the service decoupled from HTTP transport.

## 8. Runnable Example: Spring Boot 3 + Spring MVC + JPA + H2

This example demonstrates a customer system:

- `CustomerEntity` is the persistence model containing an internal field `internalMemo`.
- `CreateCustomerRequest` only allows clients to send `displayName` and `email`.
- `CustomerResponse` only exposes `id`, `displayName`, `email`, `createdAt`.
- `CustomerRepository` saves/reads entities using Spring Data JPA.
- `CustomerService` runs transactions, normalizes per demo rules, and produces response DTOs.
- `CustomerController` handles requests and returns `201 + Location` or `200/404`.

Generate a project from Spring Initializr with **Java 17+, Spring Boot 3.x**, Maven, and dependencies: `spring-boot-starter-web`, `spring-boot-starter-data-jpa`, `spring-boot-starter-validation`, `h2` (runtime), `spring-boot-starter-test` (test). No external database is needed when using embedded H2; the example uses JPA schema auto-ddl strictly for learning—**never enable arbitrary auto-ddl modes in production**.

### 8.1. Application Entry Point

File `src/main/java/com/example/demo/DemoApplication.java`:

```java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
```

### 8.2. Persistence Entity (Not Exposed Directly)

File `src/main/java/com/example/demo/CustomerEntity.java`:

```java
package com.example.demo;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

import java.time.Instant;

@Entity
@Table(name = "customers")
public class CustomerEntity {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, length = 100)
    private String displayName;

    @Column(nullable = false, length = 254)
    private String email;

    @Column(nullable = false)
    private String internalMemo;

    @Column(nullable = false)
    private Instant createdAt;

    protected CustomerEntity() {
        // JPA requires a no-args constructor.
    }

    public CustomerEntity(
            String displayName, String email, String internalMemo) {
        this.displayName = displayName;
        this.email = email;
        this.internalMemo = internalMemo;
        this.createdAt = Instant.now();
    }

    public Long getId() { return id; }
    public String getDisplayName() { return displayName; }
    public String getEmail() { return email; }
    public String getInternalMemo() { return internalMemo; }
    public Instant getCreatedAt() { return createdAt; }
}
```

Even though the entity has `getInternalMemo()`, the mapper/response DTO never puts this field into JSON. The entity is a JPA-managed class without `@JsonIgnore` or HTTP annotations. Placing an internal memo here demonstrates separation; in production you also need storage/access policies for sensitive data.

### 8.3. Repository

File `src/main/java/com/example/demo/CustomerRepository.java`:

```java
package com.example.demo;

import org.springframework.data.jpa.repository.JpaRepository;

public interface CustomerRepository
        extends JpaRepository<CustomerEntity, Long> {
}
```

The repository handles persistence and returns `CustomerEntity`/`Optional<CustomerEntity>`. It knows nothing about `ResponseEntity`, `HttpStatus`, `Location`, media types, or status codes.

### 8.4. Request DTO and Response DTO

File `src/main/java/com/example/demo/CreateCustomerRequest.java`:

```java
package com.example.demo;

import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

public record CreateCustomerRequest(
        @NotBlank @Size(max = 100) String displayName,
        @NotBlank @Email @Size(max = 254) String email) {
}
```

File `src/main/java/com/example/demo/CustomerResponse.java`:

```java
package com.example.demo;

import java.time.Instant;

public record CustomerResponse(
        Long id,
        String displayName,
        String email,
        Instant createdAt) {
}
```

The DTOs have clean structures independent of Hibernate. `@Valid` validates requests when declared on the controller. These constraints check basic syntax; whether an email is valid under business rules (such as uniqueness and ownership) is handled separately by the service/database.

### 8.5. Service and Mapping at the Transaction Boundary

File `src/main/java/com/example/demo/CustomerService.java`:

```java
package com.example.demo;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.Optional;

@Service
public class CustomerService {

    private final CustomerRepository repository;

    public CustomerService(CustomerRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public CustomerResponse create(CreateCustomerRequest request) {
        // This normalization policy is only a business example.
        String name = request.displayName().strip();
        String email = request.email().strip();

        CustomerEntity entity =
                new CustomerEntity(name, email, "INTERNAL_ONLY");
        CustomerEntity saved = repository.save(entity);

        return toResponse(saved);
    }

    @Transactional(readOnly = true)
    public Optional<CustomerResponse> findById(long id) {
        return repository.findById(id).map(this::toResponse);
    }

    private CustomerResponse toResponse(CustomerEntity entity) {
        return new CustomerResponse(
                entity.getId(),
                entity.getDisplayName(),
                entity.getEmail(),
                entity.getCreatedAt());
    }
}
```

Explanation:

- `@Transactional` applies to the write use case, `readOnly=true` to the read use case. This acts as an optimization hint and transaction boundary, not a replacement for authorization.
- `repository.save` returns the entity with an ID generated by the IDENTITY strategy used in the demo.
- `toResponse` mapping happens while the entity is still inside the use case/transaction, avoiding passing live entities to the serializer.
- `internalMemo` **never appears** in the response.
- `Optional<CustomerResponse>` expresses presence/absence of a customer without pulling `HttpStatus` into the service.
- Using `strip()` on input is an application normalization choice; production must specify this in the API contract. Do not silently lowercase email local-parts unless a proper policy exists.
- The demo omits tenant/authorization checks; real apps must enforce access control in the service/query before returning DTOs.

### 8.6. Controller Responsible for HTTP

File `src/main/java/com/example/demo/CustomerController.java`:

```java
package com.example.demo;

import jakarta.validation.Valid;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.servlet.support.ServletUriComponentsBuilder;

import java.net.URI;

@RestController
@RequestMapping("/api/customers")
public class CustomerController {

    private final CustomerService service;

    public CustomerController(CustomerService service) {
        this.service = service;
    }

    @PostMapping(
        consumes = MediaType.APPLICATION_JSON_VALUE,
        produces = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<CustomerResponse> create(
            @Valid @RequestBody CreateCustomerRequest request) {

        CustomerResponse result = service.create(request);
        URI location = ServletUriComponentsBuilder
                .fromCurrentRequestUri()
                .path("/{id}")
                .buildAndExpand(result.id())
                .toUri();

        return ResponseEntity.created(location).body(result);
    }

    @GetMapping(
        path = "/{id}",
        produces = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<CustomerResponse> find(
            @PathVariable("id") long id) {
        return ResponseEntity.of(service.findById(id));
    }
}
```

The controller has no knowledge of `internalMemo` on the entity or that the DB is H2. It only receives DTOs, delegates to the service, and builds `Location` and status. `ResponseEntity.of(Optional)` automatically picks `200` with body or `404` on `Optional.empty()`; the 404 response in the example has no custom body.

**Note on reverse proxies:** `ServletUriComponentsBuilder.fromCurrentRequestUri()` uses the request URI seen by the application; when running behind a gateway/proxy, only proper trusted forwarded-header configuration makes `Location` reflect the public URL. Never blindly trust `X-Forwarded-*` headers from untrusted clients. If you prefer relative paths, define the URL contract and Location generation accordingly.

### 8.7. Demo Database Configuration

File `src/main/resources/application.properties` for the **learning** app:

```properties
spring.datasource.url=jdbc:h2:mem:customers;DB_CLOSE_DELAY=-1
spring.datasource.driver-class-name=org.h2.Driver
spring.datasource.username=sa
spring.datasource.password=
spring.jpa.hibernate.ddl-auto=create-drop
spring.jpa.open-in-view=false
```

- `create-drop` is only suitable for test/demo environments because it drops/creates the schema with the application lifecycle.
- `open-in-view=false` enforces clear transaction boundaries; mappers convert objects before returning the response. Do not rely on lazy database reads during the rendering phase.
- In production, use managed migrations (Flyway/Liquibase) and a real database rather than embedded H2 or auto-dropping schemas.

Run the generated Maven Wrapper:

```bash
./mvnw spring-boot:run
```

Windows PowerShell:

```powershell
.\mvnw.cmd spring-boot:run
```

Note that Spring/JPA classes cannot be compiled standalone with `javac` without dependencies. The files and commands in this section are sufficient to set up the app **once you have created the Boot project with the dependencies and Maven Wrapper above**.

## 9. HTTP Request/Response of the Example

### 9.1. Create Customer: Status 201 and Location

```bash
curl -i http://localhost:8080/api/customers \
  -H "Content-Type: application/json" \
  -H "Accept: application/json" \
  --data '{"displayName":"Lan","email":"lan@example.com"}'
```

Example response (ID/timestamp are illustrative and vary per run):

```http
HTTP/1.1 201 Created
Location: http://localhost:8080/api/customers/1
Content-Type: application/json

{"id":1,"displayName":"Lan","email":"lan@example.com","createdAt":"2026-10-21T04:00:00Z"}
```

`id` and `createdAt` are server-generated; do not hardcode illustrative values in tests. **`internalMemo` is absent**, even though the DB stores that column. `Location` points to the newly created resource URI.

### 9.2. GET a Customer

```bash
curl -i -H "Accept: application/json" \
  http://localhost:8080/api/customers/1
```

If customer id=1 exists, status is `200` and the body uses the same `CustomerResponse` shape. If record id=9999 does not exist:

```bash
curl -i http://localhost:8080/api/customers/9999
```

Expected `404 Not Found` with no JSON DTO; `ResponseEntity.of(Optional.empty())` typically produces an empty body. Do not equate "not found" with "unauthenticated/unauthorized": in real products, whether to return 403 or mask resource existence with 404 is a separate security/contract decision.

### 9.3. Input Validation Rejects Invalid Record Creation

```bash
curl -i http://localhost:8080/api/customers \
  -H "Content-Type: application/json" \
  --data '{"displayName":"","email":"invalid"}'
```

With `spring-boot-starter-validation`, `@Valid` on the request DTO rejects empty names/malformed emails. By default this typically yields `400 Bad Request` (`MethodArgumentNotValidException`). **Do not rely on a fixed error body format**; Spring Boot can return different error JSON depending on `ProblemDetail`/ControllerAdvice configuration.

Sending `Content-Type: text/plain` to an endpoint that only `consumes=application/json` typically returns `415 Unsupported Media Type`, triggered by media-type matching before validation. Sending `Accept: application/xml` when the endpoint only `produces=application/json` typically returns `406 Not Acceptable`. These are protocol-level rejections, not entity-mapping bugs.

## 10. MockMvc Integration Tests: Proving the Boundary

Use the `spring-boot-starter-test` dependency (JUnit Jupiter, MockMvc). The integration test below runs with the demo H2 setup and covers the **HTTP response contract**. Place at `src/test/java/com/example/demo/CustomerControllerTest.java`:

```java
package com.example.demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;
import org.springframework.transaction.annotation.Transactional;

import com.jayway.jsonpath.JsonPath;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
@Transactional
class CustomerControllerTest {

    @Autowired
    MockMvc mvc;

    @Test
    void createsResourceWithLocationAndPublicDtoOnly() throws Exception {
        MvcResult created = mvc.perform(post("/api/customers")
                .contentType(MediaType.APPLICATION_JSON)
                .accept(MediaType.APPLICATION_JSON)
                .content(
                    "{\"displayName\":\"Lan\",\"email\":\"lan@example.com\"}"))
            .andExpect(status().isCreated())
            .andExpect(header().exists("Location"))
            .andExpect(jsonPath("$.displayName").value("Lan"))
            .andExpect(jsonPath("$.email").value("lan@example.com"))
            .andExpect(jsonPath("$.internalMemo").doesNotExist())
            .andReturn();

        Number id = JsonPath.read(
                created.getResponse().getContentAsString(), "$.id");

        mvc.perform(get("/api/customers/{id}", id.longValue())
                .accept(MediaType.APPLICATION_JSON))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.id").value(id.intValue()))
            .andExpect(jsonPath("$.internalMemo").doesNotExist());
    }

    @Test
    void missingCustomerReturns404() throws Exception {
        mvc.perform(get("/api/customers/{id}", Long.MAX_VALUE))
            .andExpect(status().isNotFound());
    }

    @Test
    void invalidInputReturns400() throws Exception {
        mvc.perform(post("/api/customers")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"displayName\":\"\",\"email\":\"bad\"}"))
            .andExpect(status().isBadRequest());
    }

    @Test
    void wrongRequestMediaTypeReturns415() throws Exception {
        mvc.perform(post("/api/customers")
                .contentType(MediaType.TEXT_PLAIN)
                .content("Lan"))
            .andExpect(status().isUnsupportedMediaType());
    }
}
```

Run:

```bash
./mvnw test
```

Windows:

```powershell
.\mvnw.cmd test
```

This is a **test code sample**, not a claim of having executed it in the current project. If the project enables Spring Security, CSRF, tenant filters, custom Jackson serialization, or DB constraints, tests and assertions must be configured to match that environment. In the test above, `@Transactional` normally rolls back DB changes on the test/MockMvc thread after each test; a real HTTP server runs in separate transactions, so do not assume end-to-end HTTP requests roll back automatically.

### Additional Tests for Complex Contracts

- Verify JSON **excludes internal fields** using `jsonPath("$.internalMemo").doesNotExist()`. This is a vital regression test if getters are added to the entity later.
- Verify `Location` actually points to a retrievable URI, not merely that the header exists.
- Verify statuses/response shapes when data is missing, input validation fails, or the requester lacks permissions.
- Verify `createdAt` parses as ISO-8601 instead of comparing timestamps against a fixed string.
- If using nested DTOs, test that no relations outside the public list are serialized.
- For list endpoints, test query count/pagination to catch N+1 issues as data grows.

## 11. Mapping DTOs with Relationships: Avoiding Cycles and N+1

Suppose `OrderEntity` has `@ManyToOne(fetch=LAZY) CustomerEntity customer` and `@OneToMany List<OrderLineEntity> lines`. A response contract might look like:

```java
public record OrderResponse(
        Long id,
        CustomerSummary customer,
        java.util.List<LineResponse> lines) {}

public record CustomerSummary(Long id, String displayName) {}

public record LineResponse(
        String productCode, int quantity) {}
```

These records are **illustrative DTO design snippets**, not standalone files with complete packages/imports. The mapper decides to expose only `customer.id`, `customer.displayName`, and a few line fields; it does not serialize `customer.orders`, `orderLine.order`, or administrative fields.

Watch out for:

- Reading `order.getCustomer().getDisplayName()` or `order.getLines()` can trigger lazy queries. Choose a fetch plan suited to the use case.
- Across a list of 100 orders, querying customer/lines per order causes N+1 even if the response DTO is tiny.
- Use **fetch joins**, `@EntityGraph`, projections, or batched queries depending on cardinality and pagination. Fetch-joining a collection alongside `Pageable` can cause duplicates/pagination issues; do not blindly add `JOIN FETCH` everywhere.
- Map inside the transaction where relationships can be safely accessed, then return the DTO. `open-in-view=false` helps catch accidental lazy dependencies crossing the boundary.
- Never expose `HibernateProxy`/`PersistentCollection` in JSON as DTO objects.

Keep JSON nesting moderate; clients can call related resource endpoints if payloads grow too large or read permissions differ.

## 12. DTO Projections for Query Optimization

Full-entity → DTO mapping is clean, but can waste RAM/queries when only a few columns are needed. Spring Data JPA supports **class-based DTO projections**, which can use Java records if the constructor matches.

Example JPQL constructor expression:

```java
public interface CustomerQueryRepository
        extends org.springframework.data.repository.Repository<CustomerEntity, Long> {

    @org.springframework.data.jpa.repository.Query(
        "select new com.example.demo.CustomerResponse(" +
        "c.id, c.displayName, c.email, c.createdAt) " +
        "from CustomerEntity c where c.id = :id")
    java.util.Optional<CustomerResponse> findPublicById(
            @org.springframework.data.repository.query.Param("id") Long id);
}
```

This is an **illustrative snippet** that must be placed in the right package with `CustomerEntity`/`CustomerResponse` declared; you can add it as a separate repository if you want to try it. The idea is to query only the columns the DTO needs instead of loading the entire entity and mapping afterward. JPQL `new` requires the **fully qualified class name** and a matching constructor with exact argument order and types; not all native queries map automatically into records.

Options:

| Read approach | When appropriate | What to watch |
| --- | --- | --- |
| Entity → manual mapper | Domain logic needs entities, small responses | Lazy loading, N+1, internal fields |
| Entity → MapStruct mapper | Many fields, repetitive DTOs | Unmapped fields config and nested mapping |
| Spring Data interface projection | Only a few properties/queries needed | Nested projections may trigger deep joins depending on structure |
| Class/record DTO projection | Pure read queries, only a few columns | Constructor mapping, JPQL/native queries |
| Optimized SQL query + manual mapping | Very complex read-heavy endpoints | SQL/database coupling and testing |

**Projections do not replace authorization**: if a projection query selects email, that data was still fetched from the DB even though the DTO differs from the entity. Apply tenant/user filters in the query or service per policy; restrict data as early as possible.

## 13. List Responses and Pagination

Returning a raw `List<CustomerEntity>` across tens of thousands of records creates heavy responses and exposes the schema. When an API returns lists, use a designed payload shape:

```json
{
  "items": [
    {"id":1,"displayName":"Lan","email":"lan@example.com",
     "createdAt":"2026-10-21T04:00:00Z"}
  ],
  "page": 0,
  "size": 20,
  "totalItems": 1
}
```

A dedicated DTO:

```java
public record PageResponse<T>(
        java.util.List<T> items,
        int page,
        int size,
        long totalItems) {}
```

This is a **standalone DTO design that can live in a Java file**, though not yet a runnable controller. Use `Pageable`/`Page<Entity>` in the repository, map each entity to a response DTO, and wrap the paging metadata. API documentation must state whether `page` is 0- or 1-based, stable sort order, and maximum `size`. Avoid exposing `PageImpl` or Hibernate internals directly merely because they happen to be serializable.

When paginating:

- Ensure sorting has a stable tie-breaker to prevent skipped/duplicate records when multiple rows share timestamps.
- Enforce a maximum page size, limit returned data, and use projections when appropriate.
- For large/rapidly changing datasets, consider cursor pagination; not mandatory when needs are simple.
- Monitor logs/query metrics; DTOs do not automatically reduce row counts or N+1 queries.

## 14. Nullability, Optional, Formatting, and Contract Evolution

### 14.1. Null and Absent Data

Suppose a customer has an optional `phoneNumber`. The API might return:

```json
{"phoneNumber":null}
```

or omit `phoneNumber` altogether depending on the contract. Jackson can be configured with `@JsonInclude(Include.NON_NULL)` to omit null fields; however, do not change the policy merely to make responses "look nicer", because clients may distinguish missing keys from explicit null.

- DTO design should state clearly which fields are required and which are optional.
- Avoid using `Optional<T>` as a DTO field just to represent nullability; across serializers/configs, behavior is less clear than a nullable field with explicit schema rules.
- `record` does not forbid `null` components. If clients must never receive null, enforce invariants in the mapper/service or via contract tests.
- Use `Instant` for UTC instants and `LocalDate` for timezone-less dates; do not return ambiguous epoch strings when the API specifies ISO-8601.
- Never pass `BigDecimal` through `double` and lose precision; document precision/scale for monetary amounts.

### 14.2. CREATE/PUT/PATCH Need Separate DTOs

Request and response DTOs are typically **asymmetric**:

- `CreateCustomerRequest` omits `id` and `createdAt` because the server generates them.
- `UpdateCustomerRequest` may require all user-editable fields.
- `PatchCustomerRequest` often needs to distinguish **absent** fields, explicit `null`, and new values. Plain nullable Java fields in a DTO collapse missing and null together after Jackson deserialization.
- `CustomerResponse` includes metadata showing the result without forcing clients to send every field back.

PATCH example:

| Input JSON | Example meaning |
| --- | --- |
| `{}` | Do not change email |
| `{"email":null}` | Clear email if policy allows |
| `{"email":""}` | Set empty string or validation error |
| `{"email":"new@example.com"}` | Replace email |

Do not use `if (request.email() != null) update` if the contract requires explicit null to delete: that loses the missing-vs-null distinction. You can use `JsonNode`/presence tracking/JSON Merge Patch per contract. In JSON Merge Patch (RFC 7396), null in the patch means removing the member. This is an **input** design and should not randomly alter response DTOs.

### 14.3. DTOs Are Contracts Requiring Versioning

Relatively safe changes can be **adding optional fields** if clients tolerate unknown fields; renaming fields, changing types, or changing value semantics can break clients. Some clients deserialize strictly, so even adding fields requires evaluation. Breaking changes need a compatibility strategy: endpoint versioning, media type versioning, or introducing a new DTO per contract.

Avoid entity-derived field names like `customerV3TableId` when clients have no reason to know. When refactoring the database, keep the JSON contract intact whenever possible; the mapping layer bridges the difference.

## 15. Where to Handle HTTP Errors: Business Outcomes in Service, Responses in Controller/Advice

In the example, `service.findById` returns `Optional<CustomerResponse>` and the controller returns `ResponseEntity.of(...)`: a simple design for 404.

Larger apps can use business exceptions such as `CustomerNotFound` or `CustomerConflict`, mapped at `@RestControllerAdvice` into standard error statuses/bodies. Then:

- Services express **business problems** instead of scattering `new ResponseStatusException(HttpStatus.NOT_FOUND, ...)` deep inside repositories if multi-transport reuse matters.
- Controllers/advice decide `404`, `409`, `400`, headers, `ProblemDetail`, and safe message formatting.
- `@Valid @RequestBody` validation typically triggers `MethodArgumentNotValidException` and 400 before entering the service; not every business rule is a validation annotation.
- Syntactically invalid JSON triggers a body-read failure (typically 400) before building the request DTO; mismatched `consumes` typically yields 415.
- Infrastructure/database exceptions must not be swallowed with `catch (Exception) { return 400; }`, which misreports internal 500 errors as client errors.

Spring Framework supports `ProblemDetail` (RFC 9457) and `ResponseEntityExceptionHandler` to customize structured errors. When building error bodies, keep `detail` free of sensitive data or table/query names. Public error codes and correlation IDs help clients debug without leaking internals.

## 16. Securing DTOs: Picking Fields Alone Is Not Enough

Protecting data has two independent but related steps:

1. **Authorization before or during the query:** does the current user have permission to read this customer? Are tenant ID and row-level scopes enforced properly?
2. **Field-level visibility:** once authorized to read the resource, is the user permitted to receive email, address, internal cost, or fraud status?

A DTO guarantees not serializing fields **omitted from that DTO**. If mapping populates email for a user lacking permission to view it, the DTO still leaks email. Across distinct permission tiers, use separate response schemas or explicit role-aware mappers; never serialize an "admin response" and rely on the client to hide fields.

Real-world risks:

- **Mass assignment** when binding entities from incoming JSON.
- **Broken Object Level Authorization (BOLA)** when a client swaps `/customers/42` for someone else's ID.
- **Sensitive Data Exposure** when an API returns raw entities or logs bodies.
- **Inconsistent projection** when GET uses a safe DTO but list/export endpoints return entities directly.
- **Caching personal data:** `Cache-Control` and private/public caching must match policy; DTOs do not prevent cache leaks on their own.
- **Debug leaks:** a DTO's or entity's `toString()` may print emails/tokens into logs; consider masking.

Tests should cover all endpoints of the same resource (create/get/list/export), not just a single GET happy-path.

## 17. Performance and Transaction Boundaries

Separating DTOs and entities typically improves control, though it does not automatically make an API faster. Things to measure:

- **SQL query count:** N+1 can occur when mapping relationships.
- **Data volume fetched from DB:** if only a few columns are needed, projections reduce I/O.
- **JSON size:** avoid stuffing unused relations/metadata into responses.
- **Nesting depth:** huge object trees consume CPU/RAM during serialization.
- **Transaction duration:** avoid holding transactions open while responses serialize or wait on the network; map DTOs inside the transaction and close it.
- **Pagination:** bound record counts and pair with stable sorting.
- **Caching:** stable public DTOs work well with conditional requests (`ETag`/`Last-Modified`) given a consistent strategy.

For example, HTTP status `304 Not Modified` pertains to the representation's cache validator, distinct from whether a persistence object changed. Do not expose raw JPA `@Version` as an HTTP `ETag` without considering privacy, response variants, and strong/weak ETag semantics. An ETag should represent the representation the client receives under the contract.

## 18. Anti-Patterns and Alternatives

| Anti-pattern | Problem | Solution |
| --- | --- | --- |
| `@GetMapping` returning `CustomerEntity` | May leak fields, lazy proxies, relation cycles | Map to `CustomerResponse` |
| `CreateCustomerRequest` reusing entity | Overposting, mixes in ID/server fields | Input DTO containing only client-editable fields |
| Repository returning `ResponseEntity<?>` | Persistence coupled to HTTP | Repository returns entity/projection; controller sets status |
| Service returning `HttpServletResponse` | Ties business logic to Servlet | Service returns result/DTO; controller/advice handles HTTP |
| Unconditional `BeanUtils.copyProperties` mapping | Copies unintended fields, loses control | Explicit/MapStruct mapper with clear rules |
| One "God Object" DTO for every endpoint | Too many null fields/hard to authorize | Specialized DTOs per use case/public role |
| Nested DTO holding a JPA entity | Still leaks lazy/proxy/internal fields | Nested DTOs must also be public-only |
| Building DTO after transaction closes then reading lazy fields | LazyInitializationException | Fetch/map inside the transaction |
| Enabling Open Session in View just to fix serialization | Hides query dependencies during rendering | Optimize fetching and explicit mapping |
| Returning entire `Page<Entity>` | Exposes implementation shape and entities | Page response DTO with a stable contract |
| Renaming JSON fields on every schema migration | Breaks clients | Preserve contract and update mapper |
| Skipping tenant checks because DTO dropped secret fields | Can still leak another user's data | Authorization + field visibility |
| Returning `204` with a DTO body | Violates no-content response semantics | Use `200/201` if a body exists, or `204` with empty body |
| Returning `500` as a validation error for every request | Hard for clients to handle and hides real bugs | Classify request/business/server errors at the right layer |

## 19. API Response Design Review Checklist

### Data Contract

1. Does JSON contain the exact fields clients need and zero internal fields?
2. Are field names, numeric types, timestamps, enums, nulls, and collections stably defined?
3. Do request DTOs contain only values clients may send, and response DTOs only data clients may receive?
4. Do nested DTOs have reasonable depth/bounds? Are there duplicated, overly broad, or accidental lazy-relation fields?
5. Can DB schema changes occur without altering the JSON response?

### Application Flow and HTTP

6. Does the controller own `ResponseEntity`, `Location`, HTTP status/headers?
7. Do services/repositories avoid direct dependencies on `HttpServletRequest`, `ResponseEntity`, and `HttpStatus` when unnecessary?
8. Does resource creation return `201` with accurate `Location`, successful GET `200`, missing resource `404`, and `204` no body?
9. Do validation, malformed JSON, business conflicts, and server failures have distinct response semantics?
10. Are response schemas and exclusion of private fields covered by tests?

### Data and Security

11. Have fetch plans/projections been measured to prevent N+1?
12. Are DTOs built before leaving the transaction when lazy data is read?
13. Are resource/tenant authorization and field-level checks applied?
14. Do list/export endpoints follow the same DTO policy as detail endpoints?
15. Could logs/caches/headers leak unauthorized public data?

## 20. Self-Check Questions

**1.** Why should a JPA entity not be returned directly from `@RestController`?

**Answer:** Entities can expose internal fields, couple the API to the persistence schema, trigger lazy queries/JSON cycles, and complicate versioning. A Response DTO explicitly defines the public contract.

**2.** How do input DTOs and response DTOs differ?

**Answer:** Input DTOs contain only client-submittable fields and need validation; response DTOs contain fields the server commits to returning. Server-generated values like `id`/`createdAt` typically appear only in responses.

**3.** Must a service return `ResponseEntity<CustomerResponse>`?

**Answer:** No. It can return `CustomerResponse`, `Optional<CustomerResponse>`, or a business result. HTTP statuses/headers should be handled in the controller/advice.

**4.** How do you return 201 and Location after a POST create?

**Answer:** Build the DTO containing the resource ID, construct the URI, and use `ResponseEntity.created(location).body(dto)`.

**5.** Once you have DTOs, do lazy loading and N+1 disappear automatically?

**Answer:** No. Mappers can still touch lazy relations and trigger extra queries. Proper transaction boundaries and fetch/query plans are still required.

**6.** Is simply omitting `internalMemo` from a DTO enough for security?

**Answer:** No. The DTO blocks that field from serialization, but you must still verify the caller is authorized to read the resource and the fields the DTO does include (such as email).

**7.** When a query only needs ID and name, do you have to fetch the full entity?

**Answer:** No. You can use Spring Data JPA DTO projections/JPQL constructor expressions when appropriate, while still ensuring the query enforces proper authorization.

**8.** If no record is found, the service returns `Optional.empty()`; what does `ResponseEntity.of(...)` in the controller do?

**Answer:** Returns HTTP 404; if a DTO is present, returns 200 with the DTO body.

**9.** Why not share the same nullable DTO for CREATE and PATCH when explicit null means "delete"?

**Answer:** A missing JSON field and an explicit null both deserialize to Java `null`, losing the caller's intent. PATCH needs presence tracking or a clear patch standard.

**10.** Does an automatic copy mapper replace a security review?

**Answer:** No. Explicit field allowlists, role-based policies, public response tests, and per-field reviews on additions remain necessary.

## 21. References

- Spring Framework — `@ResponseBody` and serializing responses: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/responsebody.html
- Spring Framework — `ResponseEntity`, status/headers/body: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/responseentity.html
- Spring Framework — `@RequestBody` and validation: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/requestbody.html
- Spring Framework — MVC Controller Return Types: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/return-types.html
- Spring Framework — Error Responses / ProblemDetail: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-rest-exceptions.html
- Spring Data JPA — Projections: https://docs.spring.io/spring-data/jpa/reference/repositories/projections.html
- Spring Data JPA — Transactionality: https://docs.spring.io/spring-data/jpa/reference/jpa/transactions.html
- Jakarta Persistence specification: https://jakarta.ee/specifications/persistence/
- RFC 9110 — HTTP Semantics (200, 201, 204, 404, Location, caching): https://www.rfc-editor.org/rfc/rfc9110.html
- RFC 9457 — Problem Details for HTTP APIs: https://www.rfc-editor.org/rfc/rfc9457.html
- OWASP — API Security Top 10: https://owasp.org/API-Security/editions/2023/en/0x11-t10/
