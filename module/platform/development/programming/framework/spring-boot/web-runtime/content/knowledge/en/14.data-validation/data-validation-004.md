# Validation Groups and Differences Between Create and Update

In a Spring Boot REST API, **create** and **update** operations often use different data validation rules. When creating a product, both name and price may be required. When performing a partial update, a client might send only the price; the omitted name field is normal, yet if the client sends a name, it must not be empty or whitespace-only. **Bean Validation groups** allow applying different constraint sets on the same data type by selecting a group at validation time.

This lesson belongs to the **Data Validation** topic and focuses on **Spring Boot 3.x, Spring MVC, Jakarta Bean Validation, and Java 17+**. We will distinguish the default group from custom groups; demonstrate `@Validated` for HTTP POST/PATCH; check required and optional fields; discuss PUT, nested validation, group ordering, 400 error handling, and when to use separate DTOs instead of validation groups.

## 1. Problem: Same Field, Different Rules by Operation

Suppose a book management API has two operations:

- `POST /api/books`: create a new book. The client must send a non-blank `title` and a non-negative `priceCents`.
- `PATCH /api/books/{id}`: partial update. The client may send only `title` or only `priceCents`. An omitted field means **keep unchanged** under the demo contract. However, any field that is present must still be valid.

Examples:

~~~json
{
  "title": "Spring in Action",
  "priceCents": 2500
}
~~~

This is a valid creation body.

~~~json
{
  "priceCents": 1999
}
~~~

This is a valid PATCH body under the partial-update contract; `title` may be absent.

~~~json
{
  "title": "   "
}
~~~

This is an invalid PATCH: even though `title` is optional, once provided it cannot consist solely of whitespace.

If you apply `@NotBlank` to `title` and `@NotNull` to `priceCents` in every context, a PATCH request containing only the price will be rejected for missing title. If you drop both constraints completely, POST requests missing required data can slip through. Validation groups choose **which constraints run for which operation**, rather than changing Java types or automatically turning POST into PATCH.

## 2. How Does Bean Validation Work in Spring Boot?

Jakarta Bean Validation (Jakarta Validation) defines constraint annotations and the `Validator` contract; Hibernate Validator usually supplies the implementation when adding the validation starter.

Gradle dependencies in a Spring Boot 3.x project:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-validation'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

This is the `dependencies` block of a project with the Spring Boot plugin, Java toolchain, and Gradle wrapper; not a complete `build.gradle` file.

Common annotations in Boot 3.x live in the `jakarta.validation.*` namespace, such as:

- `@NotNull`: value must not be null.
- `@NotBlank`: for `CharSequence`, must not be null/empty/whitespace-only.
- `@NotEmpty`: must not be null or empty for supported types, but lacks the whitespace semantics of `@NotBlank`.
- `@Size(min=..., max=...)`: limits string/collection/array/map size; **null remains valid** if only `@Size` is used.
- `@Positive`, `@PositiveOrZero`, `@Min`, `@Max`: restrict numeric ranges; typically **null is valid** without `@NotNull`.
- `@Pattern`: regex check for `CharSequence`; null is considered valid.
- `@Email`: validates email format per the validator; if email is required, typically combine with `@NotBlank`.
- `@Valid`: triggers validation/cascaded validation in supported contexts; does not define a constraint itself.

Spring also provides `org.springframework.validation.annotation.Validated`. This annotation accepts **validation group hints**, making it very useful with `@RequestBody`, `@ModelAttribute`, and corresponding Spring contexts.

**Important condition:** Bean Validation only works as expected if an implementation and validation pipeline are configured. In Spring Boot 3.x, do not assume having only the web starter activates every validation annotation; add `spring-boot-starter-validation` for proper Jakarta Bean Validation support.

## 3. What Is a Validation Group Actually?

A group is a **marker type**, typically an interface with no methods:

~~~java
interface OnCreate {}
interface OnUpdate {}
~~~

These interfaces **contain no checks of their own**, hold no logic, and know nothing about HTTP methods. They serve merely as labels for constraints:

~~~java
@NotNull(groups = OnCreate.class)
String requiredOnlyWhenCreating;
~~~

When the validator is asked to run the `OnCreate` group, constraints belonging to that group are evaluated. When running only `OnUpdate`, constraints belonging solely to `OnCreate` are not evaluated, unless group relationships or sequences are declared accordingly.

A constraint can belong to multiple groups:

~~~java
@Size(max = 120, groups = {OnCreate.class, OnUpdate.class})
String title;
~~~

Thus the title length limit applies to both operations.

Groups should be named after **validation contexts** or **use cases**, such as `OnCreate`, `OnUpdate`, `OnPublish`, `OnSubmit`. Do not create excessive groups merely to avoid designing separate DTOs when requests differ substantially.

## 4. The Default Group Is the Most Common Trap

If `groups` is not specified on a constraint:

~~~java
@NotBlank
String title;
~~~

the constraint defaults to `jakarta.validation.groups.Default`.

A common check:

~~~java
@Valid @RequestBody BookRequest request
~~~

triggers validation under the default group (`Default`) when used in a standard request body flow. However:

~~~java
@Validated(OnCreate.class) @RequestBody BookRequest request
~~~

requests checking the `OnCreate` group. **Do not assume constraints in Default automatically run alongside OnCreate.**

Table:

| Declared Constraint | Runs `Default` | Runs `OnCreate` | Runs `OnUpdate` |
|---|---:|---:|---:|
| `@NotBlank String name` | Yes | Not by default | Not by default |
| `@NotNull(groups=OnCreate.class)` | No | Yes | No |
| `@PositiveOrZero(groups={OnCreate.class,OnUpdate.class})` | No | Yes | Yes |
| `@Size(groups=OnUpdate.class)` | No | No | Yes |

There are three ways to keep shared constraints:
1. Explicitly list `groups = {OnCreate.class, OnUpdate.class}` for constraints applying to both.
2. Create a `Common` group and validate `@Validated({Common.class, OnCreate.class})` or `@Validated({Common.class, OnUpdate.class})`.
3. Intentionally include `Default` in the call, e.g., `@Validated({Default.class, OnCreate.class})`.

Approaches 2 and 3 do not guarantee the **execution order** of groups. If ordering is required, use `@GroupSequence` (covered later). Do not name an interface and expect the framework to automatically know related groups.

## 5. Same DTO, Separate Rules for Creation and Partial Update

For the partial-update example, we design:

~~~java
interface OnCreate {}
interface OnUpdate {}

record BookInput(
    @NotBlank(groups = OnCreate.class)
    @Pattern(regexp = "(?s).*\\S.*", groups = OnUpdate.class)
    @Size(max = 120, groups = {OnCreate.class, OnUpdate.class})
    String title,

    @NotNull(groups = OnCreate.class)
    @PositiveOrZero(groups = {OnCreate.class, OnUpdate.class})
    Integer priceCents
) {}
~~~

Field-by-field explanation:

| Field | On POST / OnCreate | On PATCH / OnUpdate |
|---|---|---|
| `title` | `@NotBlank` requires meaningful text | `@Pattern` allows null, but if present must contain at least one non-whitespace character |
| `title` max 120 | Enforced | Enforced |
| `priceCents` | `@NotNull` required | May be null/omitted |
| `priceCents` non-negative | Enforced when present | Enforced when present |

The regex `(?s).*\\S.*` looks for at least one non-whitespace character with dot-all enabled. This is one way to illustrate the rule “if the field is provided, it must not contain only whitespace”. Real applications should define Unicode/trim normalization policies and may replace this with a custom `OptionalNotBlank` constraint if requirements grow complex.

**Why `Integer` instead of `int` in the body?** Because `int` defaults to 0 in many object-creation mechanisms, making it hard to represent “not provided”; `Integer` allows null. With PATCH, null in this DTO means **do not update the field** by the example's convention.

**Important limitation of this example:** when Jackson maps JSON onto a nullable record, an **omitted** field and an **explicit `null`** both become Java null. Thus this DTO *cannot distinguish* “leave unchanged” from “intentionally clear the value”. If an API must support clearing fields via null, use a presence-aware design such as JSON Merge Patch/JSON Patch, JsonNode, or a dedicated wrapper type per contract, rather than just switching validation groups.

## 6. @Validated Selects Groups at Each Endpoint

Jakarta Validation's `@Valid` annotation **has no groups parameter**. Spring's `@Validated` allows selecting groups at the method parameter position:

~~~java
@PostMapping("/api/books")
ResponseEntity<BookView> create(
        @Validated(OnCreate.class) @RequestBody BookInput request) {
    // ...
}

@PatchMapping("/api/books/{id}")
ResponseEntity<BookView> patch(
        @PathVariable long id,
        @Validated(OnUpdate.class) @RequestBody BookInput request) {
    // ...
}
~~~

This is an **illustrative snippet**; the full runnable controller follows in a later section.

Key point: `@Validated(OnCreate.class)` applies to the POST body; `@Validated(OnUpdate.class)` applies to the PATCH body. Spring MVC uses a message converter to deserialize JSON, then validates the DTO using the chosen groups.

Do not add `@Validated` at the controller class level just to validate request bodies by group: in Spring Framework 6.1+, class-level `@Validated` can trigger **AOP method validation**, which differs from built-in Spring MVC method validation. Place the annotation directly on the parameter to be validated and distinguish validation errors across the two mechanisms.

Putting both `@Valid` and `@Validated(OnCreate.class)` on the same body without reason obscures the group-selection intent. Use the most appropriate annotation and test explicitly.

## 7. Create, PUT, and PATCH Should Not Be Merged Mechanically

| Operation | Typical Contract | Validation Implication |
|---|---|---|
| **POST create** | Creates a new resource; server assigns ID | Required fields must be present; internal ID/owner/status should not be client-controlled |
| **PUT replace** | Replaces the representation of the resource identified by URI | Usually requires all mandatory fields of the new representation; use `OnReplace` or a separate DTO |
| **PATCH partial update** | Updates only stated fields | Fields may be absent, yet if sent must still be valid; uses `OnUpdate` in the demo |

`OnUpdate` **does not mean “every update permits missing fields”**. That is merely a group name **chosen by the application**. For a full-replacement PUT, allowing all fields to be omitted can cause unintended data deletion. Base your choice on API semantics, not group names.

POST usually returns HTTP `201 Created` with `Location`; a successful PATCH may return `200 OK` with the updated body or `204 No Content` with no body. An ID not found during update is normally `404 Not Found`. Version/data conflicts may be `409 Conflict` or `412 Precondition Failed` depending on `ETag`/`If-Match` policy.

Validation groups only check constraints on data; they **do not determine HTTP status or transaction semantics**.

## 8. Complete Spring Boot Example: POST Create, PATCH Partial Update

Uses Java 17+, Spring Boot 3.3.x, `spring-boot-starter-web`, and `spring-boot-starter-validation`. Data is stored in a `ConcurrentHashMap` purely for demonstration without durable persistence.

Create `src/main/java/com/example/demo/BookGroupApplication.java`:

~~~java
package com.example.demo;

import java.net.URI;
import java.util.Optional;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.util.concurrent.atomic.AtomicLong;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.PositiveOrZero;
import jakarta.validation.constraints.Size;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.stereotype.Service;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PatchMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class BookGroupApplication {
    public static void main(String[] args) {
        SpringApplication.run(BookGroupApplication.class, args);
    }
}

interface OnCreate {}
interface OnUpdate {}

record BookInput(
    @NotBlank(groups = OnCreate.class)
    @Pattern(regexp = "(?s).*\\S.*", groups = OnUpdate.class)
    @Size(max = 120, groups = {OnCreate.class, OnUpdate.class})
    String title,

    @NotNull(groups = OnCreate.class)
    @PositiveOrZero(groups = {OnCreate.class, OnUpdate.class})
    Integer priceCents
) {}

record BookView(long id, String title, int priceCents) {}

@Service
class BookService {
    private final AtomicLong nextId = new AtomicLong();
    private final ConcurrentMap<Long, BookView> books =
        new ConcurrentHashMap<>();

    BookView create(BookInput input) {
        long id = nextId.incrementAndGet();
        BookView created =
            new BookView(id, input.title().trim(), input.priceCents());
        books.put(id, created);
        return created;
    }

    Optional<BookView> find(long id) {
        return Optional.ofNullable(books.get(id));
    }

    Optional<BookView> patch(long id, BookInput input) {
        BookView result = books.computeIfPresent(id, (key, old) ->
            new BookView(
                old.id(),
                input.title() == null
                    ? old.title() : input.title().trim(),
                input.priceCents() == null
                    ? old.priceCents() : input.priceCents()
            ));
        return Optional.ofNullable(result);
    }
}

@RestController
@RequestMapping("/api/books")
class BookController {
    private final BookService service;

    BookController(BookService service) {
        this.service = service;
    }

    @PostMapping(
        consumes = MediaType.APPLICATION_JSON_VALUE,
        produces = MediaType.APPLICATION_JSON_VALUE)
    ResponseEntity<BookView> create(
            @Validated(OnCreate.class) @RequestBody BookInput input) {
        BookView created = service.create(input);
        return ResponseEntity
            .created(URI.create("/api/books/" + created.id()))
            .body(created);
    }

    @GetMapping(path = "/{id}",
                produces = MediaType.APPLICATION_JSON_VALUE)
    ResponseEntity<BookView> find(@PathVariable long id) {
        return service.find(id)
            .map(ResponseEntity::ok)
            .orElseGet(() -> ResponseEntity.notFound().build());
    }

    @PatchMapping(
        path = "/{id}",
        consumes = MediaType.APPLICATION_JSON_VALUE,
        produces = MediaType.APPLICATION_JSON_VALUE)
    ResponseEntity<BookView> patch(
            @PathVariable long id,
            @Validated(OnUpdate.class) @RequestBody BookInput input) {
        return service.patch(id, input)
            .map(ResponseEntity::ok)
            .orElseGet(() -> ResponseEntity.notFound().build());
    }
}
~~~

Design points:
- The ID belongs to the server, appears in the path for updates and in the response, and is excluded from the request DTO.
- `BookInput` shares a common shape while selecting constraints by group at each endpoint.
- `BookService` receives data that passed HTTP validation and applies the update policy. The demo uses atomic map updates within one JVM; production requires databases/transactions and proper concurrency handling.
- In PATCH, null fields mean no change. Sending `{}` changes nothing; if the API disallows no-ops, the service/controller needs a dedicated rejection rule.
- Services must not “blindly trust” controllers if other entry points exist. Important business invariants must still be verified at the domain/service and persistence layers.
- `priceCents` is an integer to avoid decimal representation issues; production still requires currency rules, price limits, and rounding policies.

### 8.1. Running the Application

In a Gradle project with wrapper:

~~~bash
./gradlew bootRun
~~~

On Windows PowerShell:

~~~powershell
.\gradlew.bat bootRun
~~~

### 8.2. Valid Creation

~~~bash
curl -i -X POST http://localhost:8080/api/books \
  -H "Content-Type: application/json" \
  -d '{"title":"Spring in Action","priceCents":2500}'
~~~

On a freshly started application for the first book creation request:

~~~http
HTTP/1.1 201
Location: /api/books/1
Content-Type: application/json

{"id":1,"title":"Spring in Action","priceCents":2500}
~~~

These are the key headers/body; the server may include additional headers. The ID may differ if creation requests occurred earlier.

### 8.3. POST Missing a Field Is Rejected

~~~bash
curl -i -X POST http://localhost:8080/api/books \
  -H "Content-Type: application/json" \
  -d '{"title":"Spring in Action"}'
~~~

Expect **400 Bad Request** because `priceCents` is required in the `OnCreate` group. The default error body depends on Boot configuration, Problem Details, and existing exception handlers.

POST with `"title":"   "` is also rejected due to `@NotBlank(groups=OnCreate.class)`.

### 8.4. PATCH Sending Only Price Is Valid

After creating resource ID 1:

~~~bash
curl -i -X PATCH http://localhost:8080/api/books/1 \
  -H "Content-Type: application/json" \
  -d '{"priceCents":1999}'
~~~

Expect status **200 OK**, body:

~~~json
{"id":1,"title":"Spring in Action","priceCents":1999}
~~~

The old title remains unchanged because `title` was omitted.

### 8.5. PATCH Sending an Invalid Field Is Rejected

~~~bash
curl -i -X PATCH http://localhost:8080/api/books/1 \
  -H "Content-Type: application/json" \
  -d '{"title":"   "}'
~~~

Expect **400 Bad Request** due to `@Pattern(groups=OnUpdate.class)`. Similarly, `{"priceCents":-10}` is rejected by `@PositiveOrZero`, which belongs to both groups.

**Outcome depends on selecting the right group.** If `@Validated(OnUpdate.class)` is accidentally changed to `@Valid`, constraints belonging only to `OnUpdate` will not run by default.

## 9. MockMvc Testing: Proving Create and Update Differ

Create `src/test/java/com/example/demo/BookGroupApplicationTest.java` in the same package:

~~~java
package com.example.demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.patch;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class BookGroupApplicationTest {

    @Autowired
    MockMvc mvc;

    @Test
    void createRequiresPriceAndTitle() throws Exception {
        mvc.perform(post("/api/books")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"title\":\"Book\"}"))
            .andExpect(status().isBadRequest());

        mvc.perform(post("/api/books")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"title\":\"   \",\"priceCents\":10}"))
            .andExpect(status().isBadRequest());
    }

    @Test
    void updateCanChangeOnlyPriceButCannotUseNegativeValue()
            throws Exception {

        String location = mvc.perform(post("/api/books")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"title\":\"Java\",\"priceCents\":1000}"))
            .andExpect(status().isCreated())
            .andExpect(header().exists("Location"))
            .andReturn().getResponse().getHeader("Location");

        mvc.perform(patch(location)
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"priceCents\":800}"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.title").value("Java"))
            .andExpect(jsonPath("$.priceCents").value(800));

        mvc.perform(patch(location)
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"priceCents\":-1}"))
            .andExpect(status().isBadRequest());

        mvc.perform(patch(location)
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"title\":\"   \"}"))
            .andExpect(status().isBadRequest());
    }

    @Test
    void unknownIdReturnsNotFound() throws Exception {
        mvc.perform(get("/api/books/999999"))
            .andExpect(status().isNotFound());
    }
}
~~~

Run:

~~~bash
./gradlew test
~~~

The tests use `@SpringBootTest` with `@AutoConfigureMockMvc` to exercise JSON deserialization, validation group selection, routing, and response statuses without opening a real HTTP socket. `location` is captured from the POST response instead of assuming a fixed ID, making tests less dependent on the state of other tests.

If the application uses Spring Security, security tests or authentication must be configured for the corresponding requests. This example omits the security starter to focus purely on validation groups.

## 10. Validating Groups Directly via Jakarta Validator

Outside HTTP, Bean Validation provides this API:

~~~java
Set<ConstraintViolation<BookInput>> errors =
    validator.validate(input, OnCreate.class);
~~~

`validator` is an instance of `jakarta.validation.Validator`, and `input` is the application DTO. When no group is passed, `validator.validate(input)` checks the `Default` group. Multiple groups can be passed, e.g., `validator.validate(input, Default.class, OnUpdate.class)`.

In `BookInput` above, **every constraint specifies an explicit group**, so validating only with `Default` will not evaluate the conditions of `OnCreate`/`OnUpdate`. This illustrates why you must verify the exact selected group, rather than implying omitting Default is mandatory in every project.

When testing groups directly, assert only the set of failing fields/constraints and do not rely on the **order** of returned violations. Jakarta Bean Validation makes no general ordering guarantee for constraints within the same group.

## 11. Shared Groups, Inheritance, and @GroupSequence

### 11.1. Shared Groups

When multiple operations share a constraint, you can:
- Assign the constraint to both `OnCreate` and `OnUpdate`.
- Or create `interface CommonChecks {}` and validate `@Validated({CommonChecks.class, OnCreate.class})`.

Note: passing only `OnCreate.class` **does not automatically run CommonChecks** unless an inheritance/sequence relationship is declared or the full group list is provided.

Group inheritance is a Bean Validation feature: if `OnCreate` extends another group interface, validating `OnCreate` includes constraints belonging to the parent group. However, complex inheritance graphs are harder to read than explicit group lists; use them only when reuse structure is genuinely clear.

### 11.2. Ordered Validation with @GroupSequence

By default, Bean Validation **does not guarantee order** across groups or constraints when validating multiple groups in one call. When you have basic checks and expensive checks, you can use a group sequence:

~~~java
import jakarta.validation.GroupSequence;
import jakarta.validation.groups.Default;

interface ExpensiveChecks {}

@GroupSequence({Default.class, ExpensiveChecks.class})
interface OrderedChecks {}
~~~

This snippet illustrates the sequence concept, not a configuration used by the demo controller above. When validating `OrderedChecks.class`, the validator runs `Default` first; if the first group has violations, later groups are skipped. Within **a single group**, constraint ordering still has no general guarantee.

Do not create cycles between group sequences; cyclic definitions can raise `GroupDefinitionException`. When redefining the **default group sequence of a class**, the rule differs from an independent sequence interface: the class itself must appear in the sequence per the Jakarta Validation specification.

Group sequences do not replace transactions or database state checks.

## 12. Nested DTOs: @Valid and Group Propagation

If a request contains a child object:

~~~java
record AddressInput(
    @NotBlank(groups = OnCreate.class)
    String street
) {}

record CustomerInput(
    @Valid AddressInput address
) {}
~~~

This is an illustrative snippet; import `jakarta.validation.Valid` and the other annotations, and place them in an appropriate type scope.

`@Valid` on the `address` field enables **cascaded validation** into the child object. When validating `CustomerInput` with group `OnCreate`, that group is normally propagated down into `AddressInput` validation. Without `@Valid` on the relationship, do not assume constraints on the child object execute.

When you need to change the group propagated to a child object, Jakarta Validation supports `@ConvertGroup` at the cascaded validation site, e.g., translating a parent group to a child group. This is an advanced extension point and should only be used when the nested DTO truly needs different rules from the parent's group.

Selecting a group **does not automatically instantiate a null child object**. If the child object is required, add `@NotNull` in the appropriate group alongside `@Valid` to check both presence and inner fields.

## 13. Null, Omission, and JSON PATCH Issues

This is the most common source of data bugs in update APIs.

| JSON PATCH input | Demo's nullable Java record | Behavior in demo |
|---|---|---|
| `{"title":"Java 21"}` | title has text, price null | Updates only title |
| `{"priceCents":800}` | title null, price has number | Updates only price |
| `{}` | both null | Keeps unchanged, no error |
| `{"title":null}` | title null | Keeps unchanged, **does not clear title** |
| `{"title":""}` | title is empty string | Rejected by `@Pattern` |
| `{"priceCents":-1}` | price is negative | Rejected by `@PositiveOrZero` |

If the system must distinguish:
- **Field omitted:** keep unchanged.
- **Field sent as null:** clear value.

then a record with nullable fields is **not enough**. You can use JSON Merge Patch, JSON Patch, `JsonNode` + schema/field-presence handling, or a tri-state abstraction (absent/null/value) depending on the contract. Once field presence is determined, validate the new value and apply domain rules.

PATCH also does not solve concurrency by itself. If two clients update a resource simultaneously, consider version checks, `ETag`/`If-Match`, or optimistic locking (e.g., JPA `@Version`) when data integrity is required.

## 14. Instead of Groups, When Should You Use Separate DTOs?

Validation groups are useful when:
- Most of the request shape is identical.
- Differences between operations are relatively minor.
- Shared/specific rules are easily readable on the fields.
- Tests cover every group and all null/omitted cases.

Separate DTOs are usually better when:
- POST and PATCH have very different fields.
- Creation has no ID, while update includes path ID, status, or version.
- Edit permissions per field differ from creation permissions.
- Certain fields must never be updatable, such as `createdAt`, `ownerId`, or system-managed statuses.
- The API must distinguish absent from explicit null.
- Groups on a single DTO multiply, creating bloated annotations that are hard to audit for gaps.

Example split-type design:

~~~java
record CreateBookRequest(
    @NotBlank String title,
    @NotNull @PositiveOrZero Integer priceCents
) {}

record PatchBookRequest(
    String title,
    Integer priceCents
) {}
~~~

This is **illustrative code**; `PatchBookRequest` still needs a custom constraint or service check to reject a blank title if provided. Using separate DTOs **does not automatically solve** missing/null ambiguity. In return, the API contract and update model stay cleanly separated.

Do not let clients bind directly onto a JPA entity containing internal fields and rely on groups to control all write permissions. Separate DTOs and services remain a better boundary against mass assignment.

## 15. Validation Errors in Spring MVC

When `@RequestBody` has been deserialized into a DTO and bean validation fails, Spring MVC normally throws `MethodArgumentNotValidException`, which the framework converts to **400 Bad Request**.

With Spring Framework 6.1+, if a controller method has **constraints directly on method parameters** (e.g., `@Min` directly on `@RequestParam`) or return values, MVC uses a separate **method validation** mechanism and can throw `HandlerMethodValidationException`. This differs from bean validation of a standalone `@RequestBody`; if building a unified error handler, handle both cases appropriately.

A controller class with class-level `@Validated` may pass through AOP method validation depending on configuration, changing the exception type. Do not assume all validation errors always produce the same exception class.

If `BindingResult` or `Errors` sits **immediately after** the DTO parameter, the controller can handle field errors itself; in that case it must explicitly choose the status/response instead of ignoring errors and returning 200.

A REST API needing stable errors can standardize the body using `@RestControllerAdvice`, `ResponseEntityExceptionHandler`, or `ProblemDetail`. Return sensible field info and error categories, avoiding echoing passwords, tokens, stack traces, or raw rejected sensitive values.

| Case | Typical Status | Responsible Layer |
|---|---|---|
| Malformed JSON | 400 | Jackson/message converter |
| Request body fails group constraint | 400 | Bean Validation/MVC |
| Missing required `@RequestParam` | 400 | MVC argument resolution |
| Content-Type does not match consumes | 415 | Handler mapping/message conversion |
| Unsupported Accept/produces | 406 | Content negotiation |
| Resource to update does not exist | 404 | Controller/service mapping |
| Duplicate code/business invariant violation | 409 or contract status | Service/domain/persistence |
| Insufficient permission to update | 403 or appropriate security status | Authorization |

**Validation groups do not replace authorization.** A client sending a shape-valid request may still lack permission to modify the resource. IDs from the path must be verified by the service for ownership and business state.

## 16. Testing Edge Cases That Are Easily Missed

Beyond the MockMvc example, include tests for:
- POST missing `title`.
- POST missing `priceCents`.
- POST with whitespace-only title.
- POST with negative price, title exceeding 120 characters.
- PATCH with only price.
- PATCH with only valid title.
- PATCH sending whitespace title or negative price.
- PATCH with empty body `{}` per system policy.
- PATCH with explicit null field per contract.
- PUT, if present, requiring all mandatory fields for full replacement.
- Nested objects needing `@Valid` and proper group propagation.
- Constraints in `Default` explicitly included if the project intends to run them.
- Exception handlers returning 400 for Bean Validation failures, not confused with 409 business conflicts.

Service/domain tests must also verify invariants independent of HTTP: duplicate codes in the database, ownership, invalid state transitions, optimistic version control, and transaction consistency. Passing Bean Validation does not mean the entire business operation is valid.

## 17. Common Mistakes with Validation Groups

1. **Using `@Valid` and thinking it runs OnCreate.** `@Valid` does not select custom groups; for specific groups use `@Validated(OnCreate.class)` at the appropriate point.
2. **Defining a constraint without a group and expecting it to run in OnUpdate.** By default it belongs to `Default`.
3. **Using `@NotBlank` on an optional PATCH field.** Null gets rejected, defeating partial updates; use a “null or valid” constraint or separate DTOs.
4. **Using only `@Size` and assuming the field is required.** For null, `@Size` usually passes; pair with `@NotNull`/`@NotBlank` per group.
5. **Using `int` for optional fields.** Primitives cannot represent null cleanly and can confuse omission with 0.
6. **Adding unnecessary class-level `@Validated` on controllers.** Can alter the method validation mechanism and exception handling.
7. **Believing all passed groups execute in argument order.** Use `@GroupSequence` for ordering; within a single group there is no general order.
8. **Forgetting cascade `@Valid` on child objects.** Nested constraints may not run as expected.
9. **Merging PUT/PATCH DTOs without documenting semantics.** Full replacement and partial update are not the same.
10. **Using groups to replace business logic or authorization.** Bean Validation does not check DB uniqueness, ownership, transactions, or state machines.
11. **Failing to test both create and update.** A constraint accidentally left in Default can cause an endpoint using a custom group to accept bad data.
12. **Returning 200 on validation errors due to overly broad exception catching.** HTTP status must reflect the contract.

## 18. Implementation Checklist

- [ ] Distinguished POST create, PUT replace, and PATCH partial update as distinct contracts.
- [ ] Jakarta Bean Validation implementation present, e.g., `spring-boot-starter-validation`.
- [ ] Group markers defined and constraints assigned accurately per group.
- [ ] Understood that `Default` does not automatically run alongside custom groups.
- [ ] Used `@Validated(OnCreate.class)` and `@Validated(OnUpdate.class)` on appropriate request DTOs.
- [ ] For PATCH, allowed missing fields while rejecting invalid provided fields.
- [ ] Decided semantics for missing, explicit null, and empty string.
- [ ] Used DTOs to prevent clients from writing internal fields.
- [ ] Checked nested `@Valid`, group propagation/`@ConvertGroup` if needed.
- [ ] Added MockMvc tests for both PASS and 400 across create/update.
- [ ] Distinguished bean validation from resource existence checks, ownership, and business invariants.
- [ ] Avoided class-level `@Validated` on controllers when only request-body groups are needed.

## 19. References

- [Spring Framework — Spring MVC Validation](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-validation.html): `@Valid`, `@Validated`, `MethodArgumentNotValidException`, and `HandlerMethodValidationException`.
- [Spring Framework — @RequestBody](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/requestbody.html): deserialization and validation of request bodies.
- [Spring Boot — Validation](https://docs.spring.io/spring-boot/3.3/reference/io/validation.html): Jakarta Bean Validation and method validation integration.
- [Hibernate Validator — Reference Guide](https://docs.jboss.org/hibernate/validator/8.0/reference/en-US/html_single/): constraint groups, group sequences, group inheritance, and group conversion.
- [Jakarta Validation Specification](https://jakarta.ee/specifications/bean-validation/3.0/): standard contracts and semantics for constraints/groups.

**Remember:** Validation groups let the same DTO be validated differently between **create** and **update**, yet groups are only constraint labels—they do not alter HTTP methods or solve missing/null semantics, security, or business logic by themselves. Pick groups explicitly with `@Validated`, understand `Default`, keep the DTO/service boundary clean, and test both valid and invalid requests so your API never silently accepts bad data.
