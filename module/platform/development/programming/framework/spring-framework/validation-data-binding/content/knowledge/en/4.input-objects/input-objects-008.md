# Keeping Input Data Independent from Entities and Internal State

## 1. Why Is a Boundary Needed Between Requests and Entities?

An HTTP request is externally controlled data. A persistence entity and the application's internal state, by contrast, contain many properties that the caller **must not** arbitrarily decide: primary key, owner, role, workflow status, assignee, creation timestamp, quotas, computed results, version number, and more.

For example, a support-ticket creation API needs only two fields supplied by the customer:

~~~json
{
  "title": "Unable to log in",
  "description": "The app shows an error after entering the password"
}
~~~

If the controller accepts an entity directly that has setters for `id`, `status`, `assignedAgentId`, and `createdAt`, a requester can try adding:

~~~json
{
  "title": "Unable to log in",
  "description": "The app shows an error after entering the password",
  "id": 9001,
  "status": "RESOLVED",
  "assignedAgentId": 123,
  "createdAt": "2000-01-01T00:00:00Z"
}
~~~

The issue here is **mass assignment**, also known as *over-posting*: automatic mapping allows unintended data to flow into internal properties. The API's state can be altered, integrity broken, or authorization boundaries bypassed even when the request is valid JSON syntax.

A dangerous design often looks like this:

~~~java
// UNSAFE EXAMPLE: for analysis only; do not use in an application.
@PostMapping("/tickets")
TicketEntity create(@RequestBody TicketEntity incoming) {
    return ticketRepository.save(incoming);
}
~~~

The snippet above accepts the entire entity from outside and passes it straight to persistence. If the entity can be deserialized into sensitive properties, the client gets a chance to write those properties. Having `@Valid` or `@NotNull` constraints does **not** determine write permissions for individual fields.

**Core principle:** a request represents **intent and allowed declared values**; an entity represents **managed business domain state**. The application must explicitly convert between the two models while checking permissions and state-transition rules.

## 2. Object Roles at the Boundary

| Kind | Who Decides Which Fields Exist? | What It Should Contain | What Not to Do |
| --- | --- | --- | --- |
| Request DTO / Form object | Server-defined API contract; client supplies values | Only fields allowed for the specific operation | Include `isAdmin`, `ownerId`, `status` if the client has no authority over them |
| Entity / Aggregate | Domain and persistence model | Identity, state, relationships, invariants, version, audit | Bind all properties directly from requests |
| Service / Domain operation | Server-side business code | Create/update decisions, status policy, trusted value sources | Blindly copy all DTO properties onto an entity |
| Response DTO | Public data contract the server intends to expose | Enough data for UI/clients | Automatically return every internal entity property |

Recommended flow:

~~~text
HTTP/form/JSON (untrusted)
           |
           v
  Request DTO containing only valid inputs for the operation
           |
           v
  Binding / deserialization + type conversion
           |
           v
  Syntactic and data-constraint validation
           |
           v
  Service: verify permissions, load current state,
  check business rules, map intentionally
           |
           v
   Entity/Aggregate + Repository + transaction
           |
           v
   Response DTO (only exposed fields)
~~~

One entity type may participate in many operations, yet request DTOs should generally be **specific to each purpose**: `CreateTicketRequest` is different from `UpdateTicketRequest`, `AssignTicketRequest`, or `CloseTicketRequest`. Separating by action stops callers from supplying business fields outside their authority.

For example, on a ticket:

- **Client may input on creation:** `title`, `description`.
- **Server assigns/sets:** `id`, `createdAt`, `status = OPEN`, `version`.
- **Only users with specialized roles may manipulate:** `assignedAgentId`, transitioning `status` from `OPEN` to `RESOLVED`.
- **Returned data:** only necessary attributes; do not expose internal fields or secrets by default.

Also separate **input DTOs** from **response DTOs**: letting an API display `status` does not imply allowing clients to edit it.

## 3. Binding in Spring: Two Different Paths

### 3.1. `@ModelAttribute`: DataBinder Binds Form Data

For HTML forms or request parameters, Spring MVC uses `WebDataBinder` data binding to construct or update a model attribute. This mechanism can include constructor binding and property binding. If the model object is an entity with many setters, unintended fields can be bound onto the entity.

To reduce risk:

1. Prefer a form object/DTO describing only user-editable fields, or an immutable object with constructors/records and controlled parameters.
2. When property binding must be used, declare a whitelist with `WebDataBinder.setAllowedFields(...)`; do not rely on a blacklist as the primary defense.
3. Inspect `BindingResult` to handle type-conversion errors, validation errors, and—when needed—blocked fields via `getSuppressedFields()`.
4. Never feed a JPA-managed entity directly into request binding; load the entity in the service only after resolving identity, access rights, and permitted operations.

Illustrative example for a **form object with setters** (controller excerpt, not a standalone application):

~~~java
@InitBinder("ticketForm")
void configureTicketForm(WebDataBinder binder) {
    binder.setAllowedFields("title", "description");
}

@PostMapping("/tickets/form")
String submit(
        @Valid @ModelAttribute("ticketForm") TicketForm form,
        BindingResult result) {

    if (result.hasErrors()) {
        return "ticket-form";
    }
    // Call service to map allowed fields explicitly.
    ticketService.createFromForm(form);
    return "redirect:/tickets";
}
~~~

In this excerpt, `TicketForm` and `createFromForm` represent existing application components; the runnable section 5 demo uses JSON instead. `BindingResult` must sit **immediately after** its model attribute if the controller intends to handle errors inline. `setAllowedFields` restricts **property binding**; allowing a field name is only an extra safeguard and does not replace business permission checks.

### 3.2. `@RequestBody`: JSON Deserialized by Message Converters

For JSON `@RequestBody` in Spring MVC, an `HttpMessageConverter` (usually Jackson) reads the body into a Java object. This path is **not simply the same `WebDataBinder` property binding used for forms**. Consequently, whitelists in `@InitBinder` are not the mechanism that blocks unexpected JSON properties.

Recommended pattern:

~~~java
@PostMapping("/tickets")
ResponseEntity<TicketResponse> create(
        @Valid @RequestBody CreateTicketRequest request) {
    return ResponseEntity.ok(ticketService.create(request));
}
~~~

This is an illustrative snippet inside an existing controller; the full runnable example in section 5 also returns `201 Created`.

- Jackson can only populate fields permitted by the DTO/deserializer contract. A simple Java `record` request with two components does not have a `status` component to write onto an entity.
- `@Valid` triggers Bean Validation on the request DTO when validator infrastructure is configured. Constraints like `@NotBlank`, `@Size`, and `@Email` describe **valid data shapes**, which is insufficient to decide whether a caller may modify a resource.
- In standard Spring MVC, Bean Validation failures on `@Valid @RequestBody` produce `MethodArgumentNotValidException` (HTTP 400 under default handling), or a controller can handle them directly using `Errors`/`BindingResult` immediately after the parameter if desired. Unparseable JSON, severe type mismatches, or unknown properties under strict Jackson settings typically raise `HttpMessageNotReadableException`.
- By default, many Jackson setups ignore unknown JSON properties; to **reject** rather than merely **ignore** out-of-contract data, enable `FAIL_ON_UNKNOWN_PROPERTIES` and review any project `@JsonIgnoreProperties` exceptions/settings.
- Do not use `@JsonIgnore` as the sole security fence. JSON annotations govern serialization/deserialization, whereas a far more reliable boundary is **dedicated DTOs + explicit mapping + business authorization**.

### 3.3. Bindable and Valid Does Not Mean Authorized

Distinguish at least three kinds of checks:

| Question | Typical Layer | Example |
| --- | --- | --- |
| Can the value convert to the Java type? | Converter / binder / Jackson | `"abc"` cannot become a number |
| Does the data satisfy DTO constraints? | Bean Validation / Spring Validator | Title must not be blank, max length 100 |
| Is the caller authorized to act and change state? | Service/domain/security | User A cannot close User B's ticket; closed statuses cannot be arbitrarily edited |

Even when a request DTO passes `@Valid` with no errors, the service must still verify policies, current state, and user ownership. Obtain `currentUserId` from the **authenticated security context**, never from an `ownerId` sent in JSON or query params treated as trusted identity.

## 4. Design the DTO Before Writing the Controller

Building an input contract starts with listing the fields the client is **genuinely permitted** to modify.

Example:

~~~java
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

public record CreateTicketRequest(
        @NotBlank @Size(max = 100) String title,
        @NotBlank @Size(max = 1000) String description
) {}
~~~

This is a standalone record definition that compiles in a matching source file. Two fields suffice for creation. Do not declare `id`, `status`, `createdAt`, or `assignedAgentId`, as clients do not own those inputs.

Using immutable request DTOs/records has clear benefits: it defines the data surface explicitly, minimizes setters that could be abused, and makes API reviews easier. However, **immutability does not replace validation or authorization**. If a record includes an `isAdmin` component, Jackson can still pass `true` into the constructor; thus **contract design** is what decides safety.

For nested inputs, continue using nested DTOs and matching validation. Avoid embedding JPA entities or arbitrary object graphs in DTOs (such as `List<DomainEntity>`), as that reopens unintended property binding. Bound request/list sizes, nesting depth, and element counts to realistic needs, especially when binding large collections.

## 5. Runnable Example: Spring Boot 3 + JPA + H2

The example below uses **Java 17+**, Spring Boot **3.5.8**, Spring MVC, Bean Validation, Spring Data JPA, and in-memory H2. The controller **accepts only a DTO**; the service creates the entity via an `open(...)` factory method and sets internal fields; the API returns a separate response DTO. The example illustrates data boundaries in a small app; production requires authentication, authorization, schema migrations, and a real database.

File structure:

~~~text
boundary-demo/
├── pom.xml
└── src/main/
    ├── java/demo/boundary/
    │   ├── BoundaryDemoApplication.java
    │   ├── domain/
    │   │   ├── TicketEntity.java
    │   │   └── TicketRepository.java
    │   ├── service/
    │   │   └── TicketService.java
    │   └── web/
    │       ├── CreateTicketRequest.java
    │       ├── TicketResponse.java
    │       └── TicketController.java
    └── resources/application.yml
~~~

### 5.1. `pom.xml`

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.8</version>
        <relativePath/>
    </parent>
    <groupId>demo</groupId>
    <artifactId>boundary-demo</artifactId>
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
            <artifactId>spring-boot-starter-data-jpa</artifactId>
        </dependency>
        <dependency>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <scope>runtime</scope>
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
~~~

### 5.2. `src/main/java/demo/boundary/BoundaryDemoApplication.java`

~~~java
package demo.boundary;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class BoundaryDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(BoundaryDemoApplication.class, args);
    }
}
~~~

### 5.3. `src/main/java/demo/boundary/web/CreateTicketRequest.java`

~~~java
package demo.boundary.web;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

public record CreateTicketRequest(
        @NotBlank @Size(max = 100) String title,
        @NotBlank @Size(max = 1000) String description
) {}
~~~

This record is the contract for the **create ticket** operation. The client enters exactly two fields, carrying no entity identity or workflow state. Bean Validation runs before the service when the controller uses `@Valid`.

### 5.4. `src/main/java/demo/boundary/domain/TicketEntity.java`

~~~java
package demo.boundary.domain;

import java.time.Instant;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import jakarta.persistence.Version;

@Entity
@Table(name = "tickets")
public class TicketEntity {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, length = 100)
    private String title;

    @Column(nullable = false, length = 1000)
    private String description;

    @Column(nullable = false, length = 16)
    private String status;

    @Column(nullable = false)
    private Instant createdAt;

    private Long assignedAgentId;

    @Version
    private Long version;

    protected TicketEntity() {
        // JPA requires a no-arg constructor.
    }

    public static TicketEntity open(
            String title, String description, Instant now) {

        if (title == null || title.isBlank()
                || description == null || description.isBlank()) {
            throw new IllegalArgumentException("Required ticket fields");
        }

        TicketEntity entity = new TicketEntity();
        entity.title = title;
        entity.description = description;
        entity.status = "OPEN";
        entity.createdAt = now;
        entity.assignedAgentId = null;
        return entity;
    }

    public Long getId() {
        return id;
    }

    public String getTitle() {
        return title;
    }

    public String getStatus() {
        return status;
    }

    public Instant getCreatedAt() {
        return createdAt;
    }
}
~~~

`id`, `status`, `createdAt`, `assignedAgentId`, and `version` are internal properties. The `open(...)` factory sets status `OPEN` on the server; the entity exposes no public setters for internal fields. `@Version` supports optimistic locking if concurrent updates are added later; by itself it **does not enforce authorization** or automatically turn concurrency errors into a desired HTTP status code.

Note: primary key `id` is generated by JPA/H2, not taken from any submitted value. Checking `title`/`description` in the factory acts as a domain-rule guard when the service is called outside HTTP, complementing `@NotBlank` on the DTO.

### 5.5. `src/main/java/demo/boundary/domain/TicketRepository.java`

~~~java
package demo.boundary.domain;

import org.springframework.data.jpa.repository.JpaRepository;

public interface TicketRepository
        extends JpaRepository<TicketEntity, Long> {
}
~~~

### 5.6. `src/main/java/demo/boundary/web/TicketResponse.java`

~~~java
package demo.boundary.web;

import java.time.Instant;

public record TicketResponse(
        Long id,
        String title,
        String status,
        Instant createdAt
) {}
~~~

The response lets the UI read `status` without granting any ability to **edit** `status`. We intentionally omit `assignedAgentId`, `version`, and the raw entity from the public API.

### 5.7. `src/main/java/demo/boundary/service/TicketService.java`

~~~java
package demo.boundary.service;

import java.time.Instant;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.server.ResponseStatusException;
import demo.boundary.domain.TicketEntity;
import demo.boundary.domain.TicketRepository;
import demo.boundary.web.CreateTicketRequest;
import demo.boundary.web.TicketResponse;

@Service
public class TicketService {

    private final TicketRepository repository;

    public TicketService(TicketRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public TicketResponse create(CreateTicketRequest input) {
        TicketEntity entity = TicketEntity.open(
                input.title().strip(),
                input.description().strip(),
                Instant.now()
        );

        TicketEntity saved = repository.save(entity);
        return toResponse(saved);
    }

    @Transactional(readOnly = true)
    public TicketResponse get(long id) {
        TicketEntity entity = repository.findById(id)
                .orElseThrow(() -> new ResponseStatusException(
                        HttpStatus.NOT_FOUND, "Ticket not found"));
        return toResponse(entity);
    }

    private static TicketResponse toResponse(TicketEntity entity) {
        return new TicketResponse(
                entity.getId(),
                entity.getTitle(),
                entity.getStatus(),
                entity.getCreatedAt()
        );
    }
}
~~~

This is the most important part for understanding the **trust boundary**:

- `input.title()` and `input.description()` are parsed/validated inputs permitted for creation; the service intentionally reads only these two values.
- `Instant.now()` comes from **the server's clock**, `status = OPEN` comes from **domain policy**, and `id` comes from **the database**.
- `toResponse(...)` controls what is published; thus the API does not automatically depend on all entity properties, lazy relations, or persistence annotations.
- `@Transactional` establishes a transaction boundary for persistence. Transactions cannot replace permission checks on operations requiring an authenticated actor.

### 5.8. `src/main/java/demo/boundary/web/TicketController.java`

~~~java
package demo.boundary.web;

import java.net.URI;
import jakarta.validation.Valid;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import demo.boundary.service.TicketService;

@RestController
@RequestMapping("/tickets")
public class TicketController {

    private final TicketService service;

    public TicketController(TicketService service) {
        this.service = service;
    }

    @PostMapping
    public ResponseEntity<TicketResponse> create(
            @Valid @RequestBody CreateTicketRequest request) {

        TicketResponse created = service.create(request);
        return ResponseEntity
                .created(URI.create("/tickets/" + created.id()))
                .body(created);
    }

    @GetMapping("/{id}")
    public TicketResponse get(@PathVariable long id) {
        return service.get(id);
    }
}
~~~

The controller accepts a DTO and never uses an entity as a request parameter. The resource URL is built from the JPA-generated ID. The GET endpoint returns the exact response DTO built by the service.

### 5.9. `src/main/resources/application.yml`

~~~yaml
spring:
  jackson:
    deserialization:
      fail-on-unknown-properties: true
  jpa:
    hibernate:
      ddl-auto: create-drop
    open-in-view: false
~~~

H2 is auto-configured by Spring Boot for this example thanks to the classpath dependency. `create-drop` is only suitable for sample data: tables are created/dropped with the app lifecycle and data is ephemeral. Real projects should use schema migrations and an appropriate persistence strategy.

`fail-on-unknown-properties: true` tells Jackson to reject JSON containing properties absent from the DTO (unless overridden by type or deserialization ignore rules). This is **fail-closed behavior for the input contract**, catching requests with extra fields early. It still does not replace authorization when a caller accesses a resource they do not own.

### 5.10. Running the App and Testing HTTP Requests

In the `boundary-demo` directory, with JDK 17+ and Maven (the first run downloads dependencies online):

~~~bash
mvn spring-boot:run
~~~

Send a valid request:

~~~bash
curl -i -X POST http://localhost:8080/tickets \
  -H 'Content-Type: application/json' \
  -d '{"title":"Unable to log in","description":"Error after entering password"}'
~~~

Expected: HTTP **201 Created**; `Location` header pointing to `/tickets/{id}`; JSON response containing database-generated `id`, `title`, `status` equal to `OPEN`, and server timestamp `createdAt`. **ID and timestamp depend on each run**, so do not assert a hardcoded output. Use the URL from `Location` to call GET and inspect the ticket. The command above uses POSIX shell syntax; in PowerShell, use `curl.exe` or an equivalent HTTP client.

Try injecting an internal status:

~~~bash
curl -i -X POST http://localhost:8080/tickets \
  -H 'Content-Type: application/json' \
  -d '{"title":"New request","description":"Valid description","status":"RESOLVED"}'
~~~

Expected: HTTP **400 Bad Request** because `status` is a JSON property **not belonging** to `CreateTicketRequest` and Jackson is configured to reject unknown properties. Exact error payload format depends on the app's error-handling setup.

Try omitting a required field:

~~~bash
curl -i -X POST http://localhost:8080/tickets \
  -H 'Content-Type: application/json' \
  -d '{"title":"  ","description":"Valid description"}'
~~~

Expected: HTTP **400 Bad Request** due to `@NotBlank` on `title`. The service is not called for a syntactically valid request that fails validation, and no new record is created.

For valid creation requests, two guarantees come from **the example's design**: the client cannot pass `status` or `assignedAgentId` directly through this request DTO, and every ticket created by the service starts with `status = OPEN`. Protecting **read/update operations per user** is a separate responsibility; the sample app has no login mechanism yet and should not be used as a production API.

## 6. Entity Updates Must Go Through Business Operations

Creation is usually easy to separate: just a couple of inputs and many server-managed values. On updates, avoid shortcuts like:

~~~java
// UNSAFE EXAMPLE: do not use for actual updates.
BeanUtils.copyProperties(request, entity);
repository.save(entity);
~~~

Even if today's DTO has only a few properties, someone may add a field later and accidentally allow it to write onto the entity. Any automatic mapper matching by property name must have an explicit whitelist configured; never assume matching names alone justify permission to update.

Replace it with an intent-revealing business operation:

~~~java
// Illustrative service/domain design; requires matching classes and
// methods in a real application, not part of the runnable demo in section 5.
@Transactional
public TicketResponse changeTitle(
        long ticketId, ChangeTitleRequest request, AuthenticatedUser actor) {

    TicketEntity ticket = ticketRepository.findById(ticketId)
            .orElseThrow(TicketNotFoundException::new);

    if (!accessPolicy.canEdit(actor, ticket)) {
        throw new AccessDeniedException("Not allowed");
    }

    ticket.rename(request.title());  // Entity enforces invariants itself.
    return mapToResponse(ticket);
}
~~~

This snippet is **illustrative code** and will not compile standalone because `ChangeTitleRequest`, `AuthenticatedUser`, `TicketNotFoundException`, `accessPolicy`, `rename`, and `mapToResponse` belong to your application design. The key takeaway is the sequence: **load existing entity → check authorization → invoke permitted operation → enforce state invariants → return DTO**. Never accept `ownerId` from a request and treat it as proof of ownership; caller identity must come from trusted authentication.

For workflows, methods like `ticket.assignTo(agentId, actor)` or `ticket.resolve(actor)` can enforce valid state transitions: for instance, only `OPEN` can transition to `IN_PROGRESS`, and only authorized agents can resolve. Do not expose a public `setStatus(String)` setter for external code to mutate arbitrarily.

## 7. Common Pitfalls When Designing Create/Update APIs

### 7.1. Create DTO, Update DTO, and Patch DTO Differ

A `CreateTicketRequest` may require `title` and `description`. When editing the title, the corresponding DTO only needs `title`; when closing a ticket, a dedicated endpoint may need no body at all because the desired transition is expressed by `POST /tickets/{id}/resolve` and checked on the server.

For partial PATCH updates, distinguish three states:

1. **Field absent**: keep the existing value.
2. **Field present with `null`**: may mean a request to clear the value, or an error if null is disallowed.
3. **Field present with a value**: validate then update.

A plain Java record with nullable components cannot distinguish JSON *absent* from *explicit null* by itself. You can use a PATCH DTO with field-presence tracking (such as an absent/present wrapper or validated, strictly mapped `JsonNode` access). Never interpret every `null` as a delete command or replace the whole entity by default.

### 7.2. Do Not Put Trusted Data in Request DTOs

- `currentUserId`, `tenantId`, admin roles: obtain from authentication/security context and verified scope; a client may pass a target resource ID, but the server must verify access rights.
- `createdAt`, `updatedAt`: set on the server or via lifecycle auditing; do not trust client-supplied timestamps unless business rules allow it.
- `status`, `approvedBy`, `accountBalance`, `effectivePrice`: computed from business rules or authorized actions, never mass-bound.
- `version`: may be exposed via ETag/`If-Match` or deliberate concurrency controls, but should not be bound directly onto a managed entity as an ordinary property.

Even when a protected field is **not bound**, the API must still prevent callers from abusing path IDs, search parameters, or other operations to access someone else's resources (IDOR/BOLA).

### 7.3. Validation and Database Constraints

DTO validation such as `@NotBlank` and `@Size` improves UX and fails fast. Entities/domains still need invariants for operations arriving outside HTTP (batch jobs, schedulers, messaging, tests). Database constraints such as `NOT NULL`, `UNIQUE`, foreign keys, and transactions guarantee integrity under concurrency.

In particular, a "unique email" rule cannot be guaranteed solely by `repository.existsByEmail(...)` followed by an insert: a race condition can occur between the two operations. Enforce a database unique constraint and map conflict errors appropriately.

### 7.4. Optimistic Locking and Edit Permissions Are Separate Layers

`@Version` in JPA/Hibernate detects two concurrent update threads operating on a stale version when executing the corresponding SQL update. It does not replace permission checks. On conflict, the application must decide how to respond (e.g., HTTP 409, or 412 with `If-Match`) through implemented error handling; **do not assume** `@Version` automatically yields the right HTTP status on its own.

### 7.5. When Not to Return Entities

Returning an entire entity can accidentally leak internal properties, tokens/hashes, unwanted relationships, or cause lazy-loading failures and serialization cycles. A `Response DTO` defines the public API structure explicitly, insulating clients from versioning and persistence layout. **Read** permissions and **write** permissions on fields are two independent policies.

## 8. How to Test Input Boundaries in a Real API

These scenarios catch bugs early:

| Check | Expectation |
| --- | --- |
| Valid JSON with declared fields only | Create/update succeeds per policy; server-managed attributes are set by server |
| Client adds `isAdmin`, `status`, `ownerId` | Fields never alter internal values; if strict unknown-JSON mode is on, returns 400 |
| Blank `@NotBlank` field or exceeding `@Size` | HTTP 400 and entity is not persisted |
| Editing an ID belonging to another account | Server checks ownership on the loaded entity and rejects, typically 403 or 404 per API policy |
| Invalid workflow state transition | Service/domain rejects the invalid operation, not relying solely on DTO validation |
| Two concurrent updates | No silent lost updates; concurrency controlled via version/transaction as needed |
| PATCH field absent vs `null` | Both cases have clear semantics without accidental data deletion |
| Extending DTO in the future | Review API contract and mapping; new fields are not blindly copied onto entities |

In automated tests, include at least an **over-posting** test and an **authorization** test for real APIs. A "status is not overwritten" test should inspect the entity reloaded from the repository rather than checking only the 200/201 response. An authorization test should run with two distinct identities and two resources owned by different users.

For Spring MVC apps, depending on test layer, use `MockMvc` or HTTP integration tests combined with repository assertions. For authentication tests, never put a test identity in a custom header and trust it as a principal unless production has matching verified authentication middleware.

## 9. Common Misconceptions

1. **"DTOs are just extra boilerplate classes."** DTOs are reviewable contract boundaries versioned independently of persistence; they cut off automatic binding into internal fields.
2. **"Using records makes everything completely safe."** Records only make field references immutable; they can still contain sensitive components if the contract is poorly designed.
3. **"Adding `@Valid` is enough."** Validation checks formats and constraints; authorization and state transitions must be checked in service/domain code.
4. **"`@InitBinder.setAllowedFields` protects every JSON `@RequestBody`."** `@ModelAttribute` property binding and JSON `HttpMessageConverter` are two different paths; for JSON, use dedicated DTOs, Jackson settings, and explicit mapping.
5. **"Hiding a field during serialization blocks writes."** You must also inspect deserialization, other mappers, and all entity update paths.
6. **"Renaming a few DTO fields is enough."** Even differently named fields can be mapped erroneously by custom mappers; the path from request to entity must be explicit.
7. **"Entities have private fields so clients cannot modify them."** ORMs, reflection, Jackson field/setter visibility, constructor binding, and mapping libraries can access data depending on configuration; never rely on access modifiers alone for security.
8. **"Returning entities directly saves code."** It easily leaks unintended attributes and couples APIs to database schemas.
9. **"The server ignores extra fields so it is safe."** Ignoring fields may prevent over-posting on one field, yet when a strict protocol and client-bug detection are needed, rejecting unknown fields is a clearer choice.
10. **"Authorization at the controller alone is enough."** Permission checks must apply to the actual resource and state inside the transaction/service when mutating data; the controller is just one entry point.

## 10. Self-Check Questions

- When an endpoint takes `@RequestBody TicketEntity` instead of `CreateTicketRequest`, which properties could be bound unintentionally?
- Why can't `@Valid` on a DTO tell whether the caller is allowed to transition a ticket to `RESOLVED`?
- With `@ModelAttribute`, which kind of binding does `setAllowedFields` protect? For JSON bodies, which layer deserializes the data?
- Why should create DTOs, update DTOs, and response DTOs be separated even when all relate to one entity?
- In PATCH, why must "field omitted" and "field = null" be distinguished?
- How do you prove that a client-added JSON field cannot alter persisted state?

If you can answer these questions and trace the exact flow **request DTO → validation → service/domain → entity → response DTO**, you have mastered keeping input data independent from persistence entities and internal state.

## References

- Spring Framework, Data Binding (Model Design): https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-data-binding.html
- Spring Framework, `@ModelAttribute`: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/modelattrib-method-args.html
- Spring Framework, `@RequestBody`: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/requestbody.html
- Spring Framework, Validation: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-validation.html
- Spring Framework, Core Data Binding: https://docs.spring.io/spring-framework/reference/core/validation/data-binding.html
- Spring Boot 3.5.8 release: https://spring.io/blog/2025/11/20/spring-boot-3-5-8-available-now
