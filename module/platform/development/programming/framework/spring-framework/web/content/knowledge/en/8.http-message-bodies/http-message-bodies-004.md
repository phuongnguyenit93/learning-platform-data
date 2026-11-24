# Spring MVC: JSON Serialization, DTOs, Generic Types, and Circular References

## 1. Lesson Objectives

In a REST API with Spring MVC, controllers receive JSON data from clients and return JSON back. This is not merely string conversion: the system needs to know Java types, DTO contracts, validation rules, and how to represent an object graph without infinite recursion.

After this lesson, you will:

- Explain **serialization** (Java object → JSON) and **deserialization** (JSON → Java object) with Jackson through Spring MVC.
- Distinguish `@RequestBody`, `@ResponseBody`, `@RestController`, `ResponseEntity`, and `HttpMessageConverter`.
- Design request DTOs and response DTOs to avoid leaking internal data or accidentally serializing JPA entities.
- Use generic containers such as `List<BookResponse>` and `ApiResponse<List<BookResponse>>`; use `TypeReference`/`JavaType` when reading JSON directly.
- Recognize bidirectional circular references, and choose between bounded DTOs, `@JsonIgnore`, `@JsonManagedReference`/`@JsonBackReference`, or `@JsonIdentityInfo`.
- Accurately test status codes, JSON structure, validation, and error handling.

The hands-on examples use **Java 17+, Spring Boot 3.5.0, Spring Framework 6.2, and Jackson 2** (`com.fasterxml.jackson.*` imports). Snippets are marked when illustrative only; the complete project is in Section 9.

## 2. JSON Data Flow in Spring MVC

A request:

~~~http
POST /api/books HTTP/1.1
Content-Type: application/json
Accept: application/json

{"title":"Spring MVC","pages":240}
~~~

A minimal handler:

~~~java
@PostMapping("/books")
public BookResponse create(@RequestBody CreateBookRequest input) {
    return new BookResponse(1, input.title(), input.pages());
}
~~~

This handler is an illustrative snippet, assuming the records are already declared and the controller has `@RestController`.

**Data flow:**

1. MVC selects a handler by path, HTTP method, and mapping conditions.
2. `@RequestBody` requires reading the request body; an appropriate `HttpMessageConverter` is selected based on Content-Type and Java target type.
3. For JSON with Spring Framework 6.2/Jackson 2, the converter is typically `MappingJackson2HttpMessageConverter`, using `ObjectMapper` to parse and construct `CreateBookRequest`.
4. If the controller declares `@Valid`, Bean Validation runs after deserialization succeeds.
5. The handler executes business logic and produces a return value.
6. `@ResponseBody` (directly or via `@RestController`) causes Spring to use a converter to write the object as JSON in the HTTP response.

**Distinctions to remember:**

| Concept | Role | Example |
| --- | --- | --- |
| Serialization | Java object → JSON bytes | `BookResponse` returned to browser |
| Deserialization | JSON bytes → Java object | `@RequestBody CreateBookRequest` |
| DTO mapping | Domain/entity → API contract | `BookEntity` → `BookResponse` |
| Bean Validation | Checks rules on the object after parsing | `@NotBlank`, `@Min` |
| `ResponseEntity<T>` | Controls status, headers, and body | `201 Created` + `BookResponse` |
| `HttpMessageConverter` | Reads/writes HTTP body by media type | Jackson JSON converter |
| `ObjectMapper` | Jackson API mapping JSON ↔ Java object | `readValue`, `writeValueAsString` |

`@RestController` is equivalent to using `@Controller` together with `@ResponseBody` at the class level. With a plain `@Controller`, a `String` return value may be interpreted as a **view** name rather than a JSON string. `ResponseEntity` wraps status and headers at the HTTP layer; it does not serialize itself into a JSON body by default.

### 2.1. Content-Type and Accept

- `Content-Type: application/json` tells the server that the body sent by the client is JSON.
- `Accept: application/json` asks the server to return JSON.
- A handler with `consumes = "application/json"` may return **415 Unsupported Media Type** if the client sends another Content-Type.
- If the client only accepts a media type the server cannot produce per `produces`/converters, it may return **406 Not Acceptable**.
- Malformed JSON syntax or values that cannot convert to the target Java type usually result in **400 Bad Request** before the handler runs.
- A **serialization** error while writing the response (such as a circular graph) is a server-side failure, not automatically a client JSON input error.

Spring Boot 3.x with `spring-boot-starter-web` usually already provides Jackson and configures the JSON message converter. You do not need to instantiate a new `ObjectMapper` in every controller.

## 3. How Are Java Objects Represented as JSON?

JSON has objects, arrays, strings, numbers, booleans, and `null`. It carries no Java classes, packages, setters, constructors, generic parameters, or JPA types. Jackson uses metadata from Java types, accessors, and annotations to determine JSON fields.

JavaBean:

~~~java
public class BookBean {
    private long id;
    private String title;

    public BookBean() {}
    public long getId() { return id; }
    public void setId(long id) { this.id = id; }
    public String getTitle() { return title; }
    public void setTitle(String title) { this.title = title; }
}
~~~

Record in Java 17:

~~~java
public record BookResponse(long id, String title, int pages) {}
~~~

Jackson 2 in Spring Boot 3.x supports Java records. `new BookResponse(1, "Java", 300)` corresponds to JSON:

~~~json
{"id":1,"title":"Java","pages":300}
~~~

To deserialize a DTO, Jackson needs a suitable way to construct the object: the canonical constructor for records, or constructors/factories/getters-setters/fields per configuration for classes. Not every immutable class is supported automatically if it lacks creators and corresponding metadata.

**JSON object property order is not guaranteed as a contract.** When testing, compare fields with JSONPath or tree parsing instead of demanding character-for-character raw JSON strings.

### 3.1. Essential Jackson Annotations

~~~java
import com.fasterxml.jackson.annotation.JsonInclude;
import com.fasterxml.jackson.annotation.JsonProperty;

public record PublicUser(
        @JsonProperty("user_id") long id,
        String username,
        @JsonInclude(JsonInclude.Include.NON_NULL) String nickname) {}
~~~

For `new PublicUser(5, "lan", null)`, Jackson produces equivalent JSON:

~~~json
{"user_id":5,"username":"lan"}
~~~

| Annotation | Typical Effect | Notes |
| --- | --- | --- |
| `@JsonProperty("name")` | Renames property in JSON | Constitutes an API contract change |
| `@JsonIgnore` | Excludes property from JSON binding | Check effects on both read and write |
| `@JsonIgnoreProperties({...})` | Ignores specified properties | Does not replace authorization |
| `@JsonInclude(NON_NULL)` | Omits null fields from serialization | Does not enforce value presence |
| `@JsonFormat` | JSON formatting for dates/times, numbers, enums… | Handled by Jackson |
| `@JsonCreator` | Specifies constructor/factory for deserialization | Often paired with `@JsonProperty` |
| `@JsonView` | Selects property subset by view | Must test views and protect data |

JSON with a date example:

~~~java
import java.time.LocalDate;
import com.fasterxml.jackson.annotation.JsonFormat;

public record EventResponse(
        @JsonFormat(pattern = "yyyy-MM-dd")
        LocalDate eventDate) {}
~~~

With Spring Boot 3.x, the Jackson Java Time module is normally available via managed dependencies. `@JsonFormat` affects **Jackson JSON mapping**. `@DateTimeFormat` is mainly used in **Spring MVC request parameter / form binding**: do not mix the two annotations up and assume JSON is processed like a form.

### 3.2. Absent JSON Fields, Nulls, and Unexpected Fields

Suppose:

~~~java
public record CreateBookRequest(String title, Integer pages) {}
~~~

Bodies `{"title":"A"}` and `{"title":"A","pages":null}` usually both yield `pages == null` under standard configuration. If a field is required, use `@NotNull` with `@Valid`. For PATCH, where you need to distinguish "field omitted", "null provided", and "value provided", use an appropriate contract (JSON Merge Patch, a presence wrapper, or `JsonNode`) instead of treating null and absent identically.

Jackson may ignore unknown fields in typical Spring Boot configurations, though this policy is configurable. Unknown-field behavior should be defined and tested. Even if unknown fields are rejected, authorization must still be checked separately.

## 4. DTOs — Clear Contracts Between Client and Server

A **DTO (Data Transfer Object)** holds the data an API is allowed to receive/send. Entities/domain models can contain relationships and state that clients should never see.

Internal entity example (illustrative):

~~~java
class AccountEntity {
    long id;
    String displayName;
    String passwordHash;
    boolean administrator;
    TeamEntity team;
}
~~~

If a controller returns the entity directly, the serializer may expose the hash, admin flag, or traverse the `team` association. With JPA/Hibernate, it can also trigger lazy loading, N+1 queries, and circular references.

Response DTO:

~~~java
public record AccountResponse(long id, String displayName) {}
~~~

Request DTO:

~~~java
import jakarta.validation.constraints.NotBlank;

public record UpdateAccountRequest(@NotBlank String displayName) {}
~~~

Mapping in service:

~~~java
AccountResponse toResponse(AccountEntity account) {
    return new AccountResponse(account.id, account.displayName);
}
~~~

These snippets illustrate design and are not a standalone runnable file since `TeamEntity` and other required parts are omitted.

**Why separate request and response DTOs?**

- Clients must not be able to set `id`, `role`, `balance`, or `passwordHash` simply by adding properties to JSON.
- The service decides which fields are editable and performs authorization checks.
- Responses only include published fields; no internal object graphs or internal properties leak.
- DB schemas and entities can change without breaking the JSON contract.
- API versioning, validation, and OpenAPI documentation are easier to describe.

Record DTOs are concise and immutable, ideal for information snapshots. Class DTOs remain useful when special construction/mapping is required. **Do not bind `@RequestBody` directly to a JPA entity** if it has fields outside the user's edit permissions. Restricting DTO fields does not replace resource access/edit authorization checks in the service.

## 5. Generic Responses and Type Erasure

### 5.1. Simple and Nested Generic DTOs

~~~java
public record ApiResponse<T>(String status, T data) {}
~~~

Used for a single value:

~~~java
ApiResponse<BookResponse> one =
        new ApiResponse<>("ok", new BookResponse(1, "Java", 300));
~~~

Used for multiple values:

~~~java
ApiResponse<List<BookResponse>> many = new ApiResponse<>(
        "ok",
        List.of(
                new BookResponse(1, "Java", 300),
                new BookResponse(2, "Spring", 240)));
~~~

JSON of `many`:

~~~json
{
  "status": "ok",
  "data": [
    {"id":1,"title":"Java","pages":300},
    {"id":2,"title":"Spring","pages":240}
  ]
}
~~~

**JSON does not write "ApiResponse<List<BookResponse>>" into the body.** It only has objects and arrays. Java generics undergo **type erasure** at runtime, so when reading JSON manually you must supply the full element type.

Spring MVC can usually determine the generic target from the **handler signature**:

~~~java
@PostMapping("/batch")
public void receive(@RequestBody List<BookResponse> books) {
    // Spring knows the element type BookResponse from the method signature.
}
~~~

This is an illustrative signature only. Validating each list item also depends on container element validation/configuration; do not assume `@Valid` on every collection behaves identically to a plain request DTO.

### 5.2. Mistake: Using Raw List.class

~~~java
ObjectMapper mapper = new ObjectMapper();
List<?> rawBooks = mapper.readValue(
        "[{\"id\":1,\"title\":\"Java\",\"pages\":300}]",
        List.class);
System.out.println(rawBooks.get(0).getClass().getName());
~~~

Stdout with default Jackson 2:

~~~text
java.util.LinkedHashMap
~~~

Because `List.class` lacks element type info, a JSON object defaults to `LinkedHashMap`. Casting `(BookResponse) rawBooks.get(0)` directly will throw `ClassCastException`.

### 5.3. Right: TypeReference<T>

~~~java
import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.util.List;

ObjectMapper mapper = new ObjectMapper();
String json = """
    [{"id":1,"title":"Java","pages":300}]
    """;

List<BookResponse> books =
        mapper.readValue(json, new TypeReference<List<BookResponse>>() {});
System.out.println(books.get(0).title());
~~~

Stdout:

~~~text
Java
~~~

This snippet assumes the `BookResponse` record is already declared. With a generic wrapper:

~~~java
ApiResponse<List<BookResponse>> result = mapper.readValue(
        """
        {"status":"ok","data":[{"id":1,"title":"Java","pages":300}]}
        """,
        new TypeReference<ApiResponse<List<BookResponse>>>() {});
~~~

An anonymous subclass of `TypeReference` captures the concrete generic signature. If you instantiate `new TypeReference<List<T>>() {}` inside a generic method where `T` is still an unbound type variable, runtime cannot infer the concrete `T`.

### 5.4. Right: JavaType When Building Types at Runtime

~~~java
import com.fasterxml.jackson.databind.JavaType;

JavaType listType = mapper.getTypeFactory()
        .constructCollectionType(List.class, BookResponse.class);
JavaType nestedType = mapper.getTypeFactory()
        .constructParametricType(ApiResponse.class, listType);

ApiResponse<List<BookResponse>> parsed =
        mapper.readValue(json, nestedType);
~~~

The `json` variable here must contain an `ApiResponse` object as in the previous example. `JavaType` fits when the element type is a `Class<?>` known only at runtime. For Spring clients whose APIs accept `ParameterizedTypeReference<T>`, you can write:

~~~java
ParameterizedTypeReference<ApiResponse<List<BookResponse>>> responseType =
        new ParameterizedTypeReference<>() {};
~~~

Import `org.springframework.core.ParameterizedTypeReference`. This is **Spring's** type token, distinct from **Jackson's** `com.fasterxml.jackson.core.type.TypeReference`; do not pass the Spring token directly into `ObjectMapper.readValue`.

| Context | How the Type Is Determined |
| --- | --- |
| Spring MVC handler `@RequestBody List<BookDto>` | Controller parameter signature |
| Controller returning `ResponseEntity<ApiResponse<List<BookDto>>>` | Return type signature alongside actual object |
| Jackson `readValue(json, List.class)` | Loses element type, typically yields Map |
| Jackson `readValue(json, new TypeReference<List<BookDto>>() {})` | Preserves element type |
| Jackson with dynamically constructed types | Use `JavaType`/`TypeFactory` |
| Spring HTTP client with generic API | Use `ParameterizedTypeReference<T>` when an overload supports it |

`ResponseEntity<T>` wraps the HTTP response, not an automatic JSON field. If you want a status in the body, declare it in `ApiResponse<T>`; HTTP status 201 and `"status":"ok"` are two separate things.

## 6. Circular References in Object Graphs

Consider a bidirectional relationship:

~~~java
class Team {
    public long id;
    public String name;
    public List<User> users = new ArrayList<>();
}

class User {
    public long id;
    public String username;
    public Team team;
}
~~~

Imports `java.util.List` and `java.util.ArrayList` are required. After `team.users.add(user)` and `user.team = team`, the graph becomes:

~~~text
Team
 └─ users[0] → User
                  └─ team → Team
                                └─ users[0] → User
                                                  └─ ...
~~~

When Jackson traverses properties without a cycle-breaking structure, it can recurse through `team.users[0].team.users[0]...`, triggering recursion/serialization errors or depth limit failures depending on the version. In an HTTP response, this can cause a server error. A Java object graph can reference the exact same instance back; plain JSON objects/arrays have no built-in Java pointer identity mechanism.

### 6.1. Preferred Solution: Bounded-Depth DTOs

Instead of returning the full entity graph:

~~~java
record TeamSummary(long id, String name) {}
record UserResponse(long id, String username, TeamSummary team) {}
~~~

JSON:

~~~json
{
  "id":10,
  "username":"lan",
  "team":{"id":3,"name":"Platform"}
}
~~~

`TeamSummary` does not contain `users`. For a GET team endpoint, use a separate DTO:

~~~java
record UserSummary(long id, String username) {}
record TeamResponse(long id, String name, List<UserSummary> members) {}
~~~

Thus the response has a clear stopping point. The service queries only the needed data; with JPA, appropriate projections/fetches can avoid N+1 queries. Creating DTOs does not automatically make SQL efficient, but it gives exact control over the contract.

### 6.2. @JsonIgnore: Dropping the Unneeded Direction

~~~java
import com.fasterxml.jackson.annotation.JsonIgnore;

class User {
    public long id;
    public String username;

    @JsonIgnore
    public Team team;
}
~~~

When serializing `Team` with its list of `User`s, `User.team` is omitted, breaking the cycle. However, `User` also loses its `team` info when serialized on its own under this mapping. If different endpoints need different JSON shapes, response DTOs remain clearer than toggling entity annotations per case.

### 6.3. @JsonManagedReference and @JsonBackReference

~~~java
import com.fasterxml.jackson.annotation.JsonManagedReference;
import com.fasterxml.jackson.annotation.JsonBackReference;

class Team {
    public long id;
    public String name;

    @JsonManagedReference
    public List<User> users = new ArrayList<>();
}

class User {
    public long id;
    public String username;

    @JsonBackReference
    public Team team;
}
~~~

When serializing `Team`, the `Team → users` direction is written, while the back-reference `User → team` is omitted:

~~~json
{
  "id":3,
  "name":"Platform",
  "users":[{"id":10,"username":"lan"}]
}
~~~

For appropriate parent-child structures, Jackson can also restore the backlink during deserialization. Managed/back pairs must match direction and name; if multiple independent relationships exist, name the pairs explicitly, e.g. `@JsonManagedReference("members")` and `@JsonBackReference("members")`.

**Limitation:** this is a directional rule. Serializing `User` alone omits `Team`; it is not mechanically suited for many-to-many or symmetric dual-list relationships. Define the JSON contract before using it.

### 6.4. @JsonIdentityInfo: Representing Objects by Identity

~~~java
import com.fasterxml.jackson.annotation.JsonIdentityInfo;
import com.fasterxml.jackson.annotation.ObjectIdGenerators;

@JsonIdentityInfo(
        generator = ObjectIdGenerators.PropertyGenerator.class,
        property = "id")
class Team {
    public long id;
    public String name;
    public List<User> users = new ArrayList<>();
}

@JsonIdentityInfo(
        generator = ObjectIdGenerators.PropertyGenerator.class,
        property = "id")
class User {
    public long id;
    public String username;
    public Team team;
}
~~~

One JSON form that can be produced when serializing `Team` as root (traversal order and identity scope affect details):

~~~json
{
  "id":3,
  "name":"Platform",
  "users":[{"id":10,"username":"lan","team":3}]
}
~~~

The first time an object appears it can be serialized in full; subsequent references write its id instead of recursing further. This **changes the contract**: clients must understand where an object appears versus an id. Object ids must exist and be consistent. Deserializing an id reference without a corresponding object definition may require a custom resolver rather than querying the database automatically.

If using `@JsonIdentityReference(alwaysAsId = true)`, verify specifically whether the client has enough data and can reconstruct references. Never add identity annotations just to silence an exception without knowing the target JSON shape.

### 6.5. Which Approach to Choose?

| Approach | Effect | Suitable When | What to Avoid |
| --- | --- | --- | --- |
| Bounded DTOs | Outputs only selected data | Public APIs, stable contracts | Mapper must still query efficiently |
| `@JsonIgnore` | Drops one property | Field truly never needed in output | May drop fields needed by other endpoints |
| Managed/back | One-way parent → child serialization | Clear parent-child ownership | Does not fit arbitrary graphs |
| `@JsonIdentityInfo` | Replaces repeated object with id | Client understands identity references | Complex contract, needs id resolver |
| Switching all to EAGER | Does not break cycles | Not a solution | N+1 / bloated payloads |

**JPA/Hibernate note:** relationship cycles, lazy initialization errors, and N+1 queries are separate issues that often appear together when returning entities directly. Do not fix them by switching everything to eager fetch, enabling Open Session in View, or raising the JSON nesting limit. Design services to load the right data and map it to DTOs.

## 7. Validation vs. JSON Errors to Distinguish

Request DTO example:

~~~java
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Min;

public record CreateBookRequest(
        @NotBlank String title,
        @NotNull @Min(1) Integer pages) {}
~~~

Handler with `@Valid`:

~~~java
@PostMapping("/books")
public ResponseEntity<BookResponse> create(
        @Valid @RequestBody CreateBookRequest request) {
    // Service processes and builds response...
}
~~~

This handler snippet illustrates the signature; see Section 9 for complete runnable code.

| Input | Typical Error/Outcome |
| --- | --- |
| `{"title":"Java","pages":200}` | JSON parsing and validation OK |
| `{"title":"","pages":200}` | `@NotBlank` fails → HTTP 400 |
| `{"title":"Java","pages":0}` | `@Min(1)` fails → HTTP 400 |
| `{"title":"Java","pages":null}` | `@NotNull` fails → HTTP 400 |
| `{"title":"Java","pages":"abc"}` | Jackson String → Integer mapping error → HTTP 400 |
| `{"title":` | Malformed JSON syntax → HTTP 400 |
| Non-JSON body, handler `consumes=application/json` | HTTP 415 |
| Accept incompatible with converter/produces | HTTP 406 |

Bean Validation requires a provider; in Spring Boot, use `spring-boot-starter-validation`. JSON parsing errors are typically wrapped by Spring MVC in `HttpMessageNotReadableException`, whereas validation failures on `@Valid @RequestBody` in standard setups raise `MethodArgumentNotValidException`. Exception types also depend on method validation configuration; do not hardcode framework error messages as contracts.

If you want consistent error responses, use `@RestControllerAdvice` with `@ExceptionHandler` and a defined error DTO. Validation does not replace authorization, request size limits, collection length limits, or resource protection.

## 8. Distinguishing Jackson JSON from Form Binding

| Client Sends | Typical Annotation | Tooling |
| --- | --- | --- |
| JSON body `{"title":"Java"}` | `@RequestBody CreateBookRequest` | Jackson HTTP converter |
| Query string `?page=2` | `@RequestParam int page` | ConversionService/Formatter |
| HTML form `title=Java&pages=200` | `@ModelAttribute CreateBookForm` | WebDataBinder + Spring conversion |
| URL `/books/7` | `@PathVariable long id` | Spring conversion |
| Java DTO response → JSON | `@ResponseBody` or `@RestController` | JSON message converter |

`@DateTimeFormat` mainly configures Spring formatting for parameters/forms; `@JsonFormat` adjusts Jackson JSON. The same `LocalDate` across the two binding paths can be configured separately. Do not assume multipart/form or form-url-encoded payloads are parsed as JSON just because the controller accepts a DTO.

## 9. Complete Hands-On Example: Book REST API

Maven project, Java 17, Spring Boot 3.5.0. Data is stored in memory to focus on JSON. The controller has a separate request DTO, response DTO, and generic response wrapper. The domain entity has `internalNote`, which the client never sees.

Structure:

~~~text
json-dto-demo/
├── pom.xml
└── src/
    ├── main/java/demo/JsonDtoApplication.java
    └── test/java/demo/BookControllerTest.java
~~~

### 9.1. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>json-dto-demo</artifactId>
    <version>1.0.0</version>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>
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
~~~

### 9.2. JsonDtoApplication.java

Place all code below in `src/main/java/demo/JsonDtoApplication.java`. Java permits multiple package-private classes/records in the same file, with only one top-level public class matching the filename.

~~~java
package demo;

import java.util.Comparator;
import java.util.List;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicLong;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class JsonDtoApplication {
    public static void main(String[] args) {
        SpringApplication.run(JsonDtoApplication.class, args);
    }
}

// Clients may only pass title and pages; id is server-generated.
record CreateBookRequest(
        @NotBlank String title,
        @NotNull @Min(1) Integer pages) {
}

// API response excludes internal fields.
record BookResponse(long id, String title, int pages) {
    static BookResponse from(BookEntity book) {
        return new BookResponse(book.id(), book.title(), book.pages());
    }
}

// Generic wrapper: T can be BookResponse or List<BookResponse>.
record ApiResponse<T>(String status, T data) {
}

// Domain object must not be returned directly over HTTP.
record BookEntity(long id, String title, int pages, String internalNote) {
}

@RestController
@RequestMapping(path = "/api", produces = MediaType.APPLICATION_JSON_VALUE)
class BookController {
    private final Map<Long, BookEntity> books = new ConcurrentHashMap<>();
    private final AtomicLong ids = new AtomicLong(2);

    BookController() {
        books.put(1L, new BookEntity(1, "Java Basics", 200, "private-a"));
        books.put(2L, new BookEntity(2, "Spring MVC", 240, "private-b"));
    }

    @GetMapping("/books")
    public ResponseEntity<ApiResponse<List<BookResponse>>> list() {
        List<BookResponse> data = books.values().stream()
                .sorted(Comparator.comparingLong(BookEntity::id))
                .map(BookResponse::from)
                .toList();
        return ResponseEntity.ok(new ApiResponse<>("ok", data));
    }

    @GetMapping("/books/{id}")
    public ResponseEntity<ApiResponse<BookResponse>> one(
            @PathVariable long id) {
        BookEntity book = books.get(id);
        if (book == null) {
            return ResponseEntity.notFound().build();
        }
        return ResponseEntity.ok(
                new ApiResponse<>("ok", BookResponse.from(book)));
    }

    @PostMapping(path = "/books",
                 consumes = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<ApiResponse<BookResponse>> create(
            @Valid @RequestBody CreateBookRequest request) {
        long id = ids.incrementAndGet();
        BookEntity book = new BookEntity(
                id, request.title(), request.pages(), "server-only");
        books.put(id, book);

        return ResponseEntity.status(HttpStatus.CREATED)
                .body(new ApiResponse<>("ok", BookResponse.from(book)));
    }
}
~~~

Key points in the code:

- `@RestController` enables serialization for responses.
- `@RequestBody` uses Jackson to construct `CreateBookRequest`; `@Valid` requests Bean Validation.
- Response methods return `ResponseEntity<ApiResponse<List<BookResponse>>>` or `ResponseEntity<ApiResponse<BookResponse>>` with explicit generic types.
- Only `BookResponse` is converted to JSON; `internalNote` in `BookEntity` is absent from the API payload.
- `ConcurrentHashMap` and `AtomicLong` keep the demo working under concurrent requests. Data exists in memory only and is lost on restart; this is not a production persistence example.
- GET list sorts by id so examples and tests have a deterministic array order.

### 9.3. Running and Testing over HTTP

From the directory containing `pom.xml`:

~~~bash
mvn spring-boot:run
~~~

GET list:

~~~bash
curl -i 'http://localhost:8080/api/books' \
  -H 'Accept: application/json'
~~~

HTTP **200 OK**, equivalent body:

~~~json
{
  "status": "ok",
  "data": [
    {"id":1,"title":"Java Basics","pages":200},
    {"id":2,"title":"Spring MVC","pages":240}
  ]
}
~~~

POST to create a book:

~~~bash
curl -i -X POST 'http://localhost:8080/api/books' \
  -H 'Content-Type: application/json' \
  -H 'Accept: application/json' \
  --data '{"title":"Modern Java","pages":310}'
~~~

On the first POST of a freshly started instance, returns **201 Created**, equivalent body:

~~~json
{
  "status": "ok",
  "data": {"id":3,"title":"Modern Java","pages":310}
}
~~~

Subsequent POSTs get higher ids. No `internalNote` appears in the body. GET `/api/books/1` returns the DTO with id 1, whereas `/api/books/999` (when absent) returns 404 with an empty body per the handler.

Testing invalid validation:

~~~bash
curl -i -X POST 'http://localhost:8080/api/books' \
  -H 'Content-Type: application/json' \
  --data '{"title":"","pages":0}'
~~~

HTTP is typically **400 Bad Request** due to `@NotBlank` and `@Min(1)`. Default error message bodies are not fixed, so do not expect verbatim text. Sending `{"title":"X","pages":"abc"}` fails before validation during `Integer` deserialization.

The shell examples above use Bash line continuation `\`. In Windows PowerShell, use `curl.exe` on one line or appropriate PowerShell line continuation; the `curl` alias may not point to the real curl binary.

### 9.4. Testing HTTP Contracts and Nested Generics

Create `src/test/java/demo/BookControllerTest.java`:

~~~java
package demo;

import java.util.List;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class BookControllerTest {
    @Autowired MockMvc mvc;
    @Autowired ObjectMapper mapper;

    @Test
    void getListHasOnlyDtoFields() throws Exception {
        mvc.perform(get("/api/books").accept(MediaType.APPLICATION_JSON))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.status").value("ok"))
            .andExpect(jsonPath("$.data[0].title").value("Java Basics"))
            .andExpect(jsonPath("$.data[0].internalNote").doesNotExist());
    }

    @Test
    void createReturns201AndHidesInternalData() throws Exception {
        mvc.perform(post("/api/books")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {"title":"Modern Java","pages":310}
                    """))
            .andExpect(status().isCreated())
            .andExpect(jsonPath("$.data.title").value("Modern Java"))
            .andExpect(jsonPath("$.data.pages").value(310))
            .andExpect(jsonPath("$.data.internalNote").doesNotExist());
    }

    @Test
    void invalidDtoReturns400() throws Exception {
        mvc.perform(post("/api/books")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {"title":"","pages":0}
                    """))
            .andExpect(status().isBadRequest());
    }

    @Test
    void readNestedGenericWithoutRawMap() throws Exception {
        String json = """
                {"status":"ok",
                 "data":[{"id":1,"title":"Java Basics","pages":200}]}
                """;
        ApiResponse<List<BookResponse>> decoded = mapper.readValue(
                json, new TypeReference<ApiResponse<List<BookResponse>>>() {});
        assertEquals("ok", decoded.status());
        assertEquals(BookResponse.class, decoded.data().get(0).getClass());
        assertEquals("Java Basics", decoded.data().get(0).title());
    }
}
~~~

Run:

~~~bash
mvn test
~~~

HTTP tests check status codes and JSONPath rather than property order. The generic test confirms Jackson instantiates `BookResponse` rather than a `Map`. Tests share a context so the POST test may add a new book; GET list still always starts with the two seeded books id 1 and id 2 when sorted by id.

## 10. JSON Cycles with JPA/Hibernate: Which Layer Handles Them?

JPA relationships:

~~~java
// Illustrates relationship shape, not standalone runnable entities.
@Entity
class Department {
    @OneToMany(mappedBy = "department")
    List<Employee> employees;
}

@Entity
class Employee {
    @ManyToOne(fetch = FetchType.LAZY)
    Department department;
}
~~~

Watch for four distinct risks:

1. **Graph cycle:** Department → employees → department → … if serializing bidirectional relationships.
2. **LazyInitializationException:** Jackson accesses an association after the persistence context has closed.
3. **N+1 queries:** each nested getter can trigger additional queries.
4. **Data exposure:** entities leak internal fields.

Switching everything to `FetchType.EAGER` does not fix cycles and can increase load. Scattering `@JsonIgnore` on entities can alter APIs across multiple endpoints. Design queries/projections to fetch the exact fields needed, map to DTOs while data is in scope, and return DTOs. Configuring a Hibernate module for Jackson (if present) does not replace JSON contract design.

## 11. Common Mistakes and How to Diagnose Them

| Symptom | Likely Cause | Resolution |
| --- | --- | --- |
| `LinkedHashMap cannot be cast to BookResponse` | Reading generic JSON with raw `List.class` | `TypeReference`/`JavaType` |
| 400 from JSON parse | Invalid JSON / mismatched field type | Check body, Content-Type, and root cause |
| 400 from validation | Parsed OK, constraint failed | `@Valid`, constraints, error handler |
| 415 | Wrong Content-Type | Check `consumes` |
| 406 | Wrong Accept/produces/converter | Check `Accept` and `produces` |
| 500 while serializing graph | Object cycle or getter exception | Bounded response DTO, check stack trace |
| LazyInitializationException | Touching JPA lazy relation outside context | Mapping/projection inside service |
| JSON leaks private field | Returning entity or DTO with unwanted field | Use an allowlisted response DTO |
| JSON date formatted wrong | Jackson date config | `@JsonFormat` / JavaTimeModule |
| JSON test fails on key order | Comparing raw JSON strings directly | JSONPath / tree comparison |

Several errors share the same HTTP status while originating in different steps. When diagnosing, verify whether the request reached the handler, whether failure happened in parse/validation/service/serialization, and fix the right layer.

Other anti-patterns:

- Do not use `Map<String,Object>` for every request when the structure is known; it hinders validation and loses type safety.
- Do not treat `@JsonIgnore` or DTOs as a substitute for resource authorization.
- Do not raise max JSON depth to hide object cycles caused by serializing entities directly.
- Do not deserialize polymorphic class names from untrusted JSON via broad default typing; use an explicit allowlist/discriminator.
- Do not embed `ResponseEntity` inside a DTO property expecting Jackson to understand HTTP headers.
- Do not guess unknown-field handling; document the policy and test it.
- Do not coerce `LocalDateTime` into a UTC instant when JSON carries no offset/zone.
- Do not assume null fields are omitted unless matching configuration/annotations are present.

## 12. Practice Exercises

**Exercise 1 — DTOs and security:** Entity `Customer` has `id, displayName, email, passwordHash, role`. Create `CustomerCreateRequest` accepting only `displayName,email` and `CustomerResponse` returning only `id,displayName`. State where role permissions should be checked.

**Exercise 2 — Generics:** Given `{"status":"ok","data":[{"id":1,"title":"Java","pages":200}]}`, write `TypeReference<ApiResponse<List<BookResponse>>>` and predict the runtime type of `data.get(0)` if using only `ApiResponse.class`.

**Exercise 3 — Cycles:** Diagram `Department ↔ Employee`. Design `DepartmentResponse` containing `List<EmployeeSummary>`, where `EmployeeSummary` omits `department.employees`. Why does this stop recursion?

**Exercise 4 — Annotations:** Compare `@JsonIgnore`, managed/back references, and identity. For an endpoint `GET Team` that includes users where users do not need `Team`, pick the reasonable option; for long-lived public APIs, consider DTOs.

**Exercise 5 — Validation:** Predict the failing step for `pages=0`, `pages=null`, and `pages="abc"`. Why is the validator not called in all cases?

**Exercise 6 — HTTP:** Distinguish 400 parse, 400 validation, 415, 406, and server-side serialization errors. Add tests to the project in Section 9.

**Exercise 7 — Compatibility:** Old clients only know `id,title`; new clients want `pages,language` added. Propose how to evolve the response DTO, versioning, and unknown-field policy.

## 13. References

- [Spring Framework 6.2 — HTTP Message Conversion](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/message-converters.html).
- [Spring Framework 6.2 — @RequestBody](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-methods/requestbody.html).
- [Spring Framework 6.2 — @ResponseBody](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-methods/responsebody.html).
- [Jackson 2 — ObjectMapper Javadoc](https://javadoc.io/doc/com.fasterxml.jackson.core/jackson-databind/2.18.4/com/fasterxml/jackson/databind/ObjectMapper.html).
- [Jackson 2 — TypeReference Javadoc](https://javadoc.io/doc/com.fasterxml.jackson.core/jackson-core/2.18.4/com/fasterxml/jackson/core/type/TypeReference.html).
- [Jackson 2 — JsonManagedReference](https://javadoc.io/doc/com.fasterxml.jackson.core/jackson-annotations/2.18.4/com/fasterxml/jackson/annotation/JsonManagedReference.html), [JsonBackReference](https://javadoc.io/doc/com.fasterxml.jackson.core/jackson-annotations/2.18.4/com/fasterxml/jackson/annotation/JsonBackReference.html), [JsonIdentityInfo](https://javadoc.io/doc/com.fasterxml.jackson.core/jackson-annotations/2.18.4/com/fasterxml/jackson/annotation/JsonIdentityInfo.html).

