# Default Values, Optional Parameters, and Missing Data in Spring Boot

## 1. The Core Problem: "Not Sent" Does Not Equal "Sent an Empty Value"

When designing a REST API, a client may omit a field completely, send an empty string, send JSON null, send 0, send false, or send an empty collection. These states **do not necessarily share the same business meaning**. If the server treats all of them as "not provided", a search API may filter incorrectly; worse, a partial-update API may overwrite or accidentally clear existing data.

Spring MVC and Spring WebFlux support request binding via @RequestParam, @RequestHeader, @CookieValue, @PathVariable, @RequestBody, @RequestPart, and corresponding request objects. Spring Boot auto-configures many of these components, but **cannot decide on its own** whether an absent field should use a default, keep existing data, or be rejected.

Example GET /api/books contract:

- page absent: use page=1.
- size absent or passed as empty size=: use size=20 via @RequestParam(defaultValue).
- size=0: an actual number was sent; if size must be 1 to 100, return HTTP 400.
- sort absent: use createdAt; sort=unknown: return an error or handle per documented policy.
- includeArchived absent: may mean "do not filter by archive status" rather than false.
- includeArchived=false: the client explicitly selected false.

Example PATCH /api/profile contract differs:

- displayName omitted: keep the current name.
- displayName=null sent: may request clearing the name (if permitted by the API), or return an error.
- displayName="" sent: may be invalid because it is empty.
- active=false sent: must persist false, not treat it as "not entered".

**The goal of this lesson** is to choose appropriate Java types, annotations, defaults, and validation so requests have unambiguous meaning right at the HTTP boundary while preserving the distinction between missing values and valid values.

## 2. Table of Data States to Distinguish

| State | HTTP/JSON example | What to understand |
|---|---|---|
| Absent query parameter | GET /books | Key page is not in the query |
| Empty query parameter | GET /books?page= | Key page is present with an initially empty value |
| Whitespace query parameter | GET /books?q=%20%20 | String of two spaces; not the same as absent |
| Zero query parameter | GET /books?page=0 | Client actively passed the number 0 |
| False query parameter | GET /books?archived=false | Client actively passed Boolean false |
| Query parameter with literal "null" | GET /books?q=null | String "null", not JSON null |
| Missing header | No X-Mode header | Header absent |
| Empty header | X-Mode: | Header present but empty, depending on HTTP client |
| Missing cookie | No theme cookie | Cookie absent |
| JSON object missing field | {} | Field missing |
| JSON field with null | {"name":null} | Field present with JSON null |
| JSON field with empty string | {"name":""} | Field present with empty String value |
| JSON field as empty array | {"tags":[]} | Field present with an empty collection |
| JSON field as false or 0 | {"active":false,"count":0} | Meaningful values, not missing |
| HTTP body not sent | POST with no body | Entire body content is absent |
| HTTP body contains JSON null | POST body is null | JSON null token is present; Java may receive null |

There are three distinct concepts:

1. **Presence**: did the data appear in the HTTP request?
2. **Parsed value**: after conversion/deserialization, what Java type/value was produced?
3. **Business semantics**: should the application apply a default, keep existing state, clear it, accept it, or reject it?

Do not infer presence reliably from a Java null variable alone. Java null can come from a missing JSON field, an explicit JSON null, a missing query parameter, or conversion/binding returning null.

### 2.1. Empty and Blank Are Different

In Java 17:

~~~java
"".isEmpty();     // true
"  ".isEmpty();   // false
"  ".isBlank();   // true
"0".isBlank();    // false
~~~

These are illustrative expressions, not a standalone program. A whitespace-only value may be treated as invalid by the domain even though at the HTTP level it is a non-empty String. @RequestParam(defaultValue=...) applies to missing/empty per annotation rules; **it is not a tool for normalizing all whitespace strings**.

### 2.2. Query Parameters Do Not Have a JSON-Style Null

URL query values parse as strings. The string q=null remains the characters n-u-l-l unless the application defines a custom sentinel. If clients need to express explicit null inside an object, a JSON body expresses it better; however, how null applies in CREATE/PATCH operations is still governed by the contract.

## 3. @RequestParam: required=true, required=false, and defaultValue

An annotated controller method can declare:

~~~java
@GetMapping("/books")
String books(@RequestParam(name = "page") int page) {
    return "page=" + page;
}
~~~

This snippet must reside inside an appropriate @RestController. @RequestParam defaults to required=true; a client omitting page normally triggers a missing-parameter error and HTTP 400 under default error handling. If page=abc, conversion to int fails, also typically returning 400, but due to a type mismatch rather than a missing parameter.

### 3.1. required=true Is Not Complete Validation

Required only enforces that the parameter can be bound under binding rules. It does not ensure the value is positive, in a whitelist, free of whitespace, or valid for the domain.

For example, GET /books?page=-2 provides a syntactically valid int for page that is invalid for paging. You must validate page >= 1 or configure Bean Validation/method validation appropriately.

### 3.2. required=false and Nullable Types

~~~java
@GetMapping("/books")
String books(@RequestParam(name = "q", required = false) String q) {
    return q == null ? "all" : q;
}
~~~

When q is omitted, the controller receives null. When q=, it may receive an empty string depending on conversion. When q=%20%20, it receives a whitespace string.

If a primitive such as int or boolean can genuinely be absent without a default, a problem arises because primitives cannot hold null. **Prefer Integer, Boolean, or Optional<T>** when a parameter is optional and you need to know whether a value was provided.

### 3.3. defaultValue: Basic Usage

~~~java
@GetMapping("/books")
String books(
        @RequestParam(name = "page", defaultValue = "1") int page,
        @RequestParam(name = "size", defaultValue = "20") int size) {
    return "page=" + page + ",size=" + size;
}
~~~

When @RequestParam(defaultValue) is specified, required is implicitly false. For @RequestParam, the default value is used when the parameter is **absent** or considered **empty**.

Common example cases:

| Request | Bound page | Bound size |
|---|---:|---:|
| GET /books | 1 | 20 |
| GET /books?page=&size= | 1 | 20 |
| GET /books?page=3&size=50 | 3 | 50 |
| GET /books?page=0 | 0 | 20 |
| GET /books?page=abc | Type conversion error | Normal handler result not reached |
| GET /books?size=-1 | 1 | -1 |

**Do not use defaults to hide type errors.** page=abc does not mean "page omitted". size=0 is not missing either, even if the domain decides to reject it.

Default values must be convertible to the corresponding Java type; defaultValue="abc" on an int is an API definition/configuration bug. If a default or parameter contains spaces, test actual conversion; do not assume every whitespace string triggers the default.

### 3.4. Optional<T>

~~~java
@GetMapping("/books")
String books(@RequestParam(name = "sort") Optional<String> sort) {
    return sort.filter(s -> !s.isBlank())
            .orElse("createdAt");
}
~~~

This snippet requires importing java.util.Optional and placing it inside a controller. Spring supports Optional across multiple argument resolvers, including @RequestParam. Optional.empty represents an absent value in Java and helps avoid manual null checks.

Optional **does not automatically preserve wire-level presence metadata** if conversion already collapsed empty and missing. Avoid overusing Optional as a field type across every JSON DTO or JPA entity merely because @RequestParam supports it.

### 3.5. Optional Booleans Should Use Wrappers When Three States Are Needed

~~~java
@RequestParam(name = "includeArchived", required = false)
Boolean includeArchived
~~~

Binding to the Boolean wrapper allows the application to receive true, false, and null. This matters if:

- null = do not filter by archive status;
- true = return only archived items;
- false = return only non-archived items.

If you write Boolean.TRUE.equals(includeArchived) and immediately use it to filter false, you have **intentionally collapsed null into false**. That is only right when the contract defines missing as equivalent to false.

### 3.6. Multiple Values for the Same Query Key

A client may send:

~~~text
GET /books?tag=java&tag=spring&tag=web
~~~

With @RequestParam(name="tag", required=false) List<String> tags or MultiValueMap, Spring can bind multiple values according to type conversion rules. However, do not assume a missing list is always an empty list or that duplicate parameters are always processed in the expected order. If an API permits only a single value, enforce a policy rejecting duplicates where required.

## 4. @RequestHeader, @CookieValue, @PathVariable, and Multipart Data

### 4.1. Optional Headers or Headers with Defaults

~~~java
@GetMapping("/client-mode")
String clientMode(
        @RequestHeader(name = "X-Mode", defaultValue = "standard")
        String mode) {
    return mode;
}
~~~

When the header is omitted, standard is used. A header that is present but treated as empty can also trigger defaultValue. Never use client-controlled headers to decide roles, tenants, or access permissions without a proper authentication mechanism.

### 4.2. Optional Cookies

~~~java
@GetMapping("/theme")
String theme(
        @CookieValue(name = "theme", required = false)
        String theme) {
    return theme == null || theme.isBlank() ? "system" : theme;
}
~~~

A cookie may be absent. Falling back to theme="system" is an acceptable business choice for a UI preference, but never create unsafe defaults for login session cookies or access rights.

### 4.3. @PathVariable(required=false) Does Not Automatically Add a New URL

A mapping /orders/{id} requires an id path segment for the route to match. Even though @PathVariable(required=false) is supported during argument resolution, it **does not make /orders automatically match /orders/{id}**.

If both list and detail endpoints are needed, define both routes:

~~~java
@GetMapping("/orders")
String listOrders() {
    return "all orders";
}

@GetMapping("/orders/{id}")
String findOrder(@PathVariable long id) {
    return "order " + id;
}
~~~

These are two methods to place in the same controller; the code compiles with proper imports/annotations. If business logic wants to share a handler, declare the corresponding URL patterns explicitly and test them rather than using an optional path variable to mask a missing route mapping.

### 4.4. Multipart Files: Not Sent Differs from Zero-Byte File

In Spring MVC, @RequestPart(name="avatar", required=false) MultipartFile avatar receives null when the client omits the part. If the part is present but empty, MultipartFile.isEmpty() is true. "Keep avatar unchanged" and "delete avatar" should have distinct semantics.

In reactive WebFlux, use the corresponding multipart type such as FilePart instead of copying Servlet MultipartFile into a reactive controller. Multipart uploads also require checking size limits, content type, filenames, and storage security.

## 5. @RequestBody: Whole Body vs. Individual JSON Fields

@RequestBody decodes the HTTP message body, typically from application/json into a Java object. There are two independent questions:

1. Is the overall request body present and decodable into an object?
2. Is each field inside the JSON object present, valid, and permitted to be null?

Example JSON:

~~~json
{"title":"Spring Boot","copies":2,"published":false}
~~~

This differs from:

~~~json
{"title":"Spring Boot"}
~~~

and differs from:

~~~json
{"title":"Spring Boot","copies":null,"published":null}
~~~

If a Java record only has String title, Integer copies, and Boolean published, Jackson maps both an omitted field and an explicit JSON null to Java null. Thus **inspecting a null DTO field alone is not enough to tell whether the field was omitted or explicitly sent as null**.

### 5.1. @RequestBody Defaults to required=true

~~~java
@PostMapping("/books")
String create(@RequestBody NewBook body) {
    return body.title();
}
~~~

This method is a snippet requiring placement in a controller and a NewBook type definition. When a required body has no content to bind, Spring typically returns 400. Malformed JSON or mismatched types can also return 400 due to read/deserialization failure rather than a missing body. With an unsupported Content-Type, the server may return 415.

Do not set required=false just to hide client errors when a payload is required by the API contract.

### 5.2. @RequestBody(required=false) Makes the Whole Body Optional

~~~java
@PostMapping("/draft")
Map<String, Boolean> draft(
        @RequestBody(required = false) Map<String, Object> body) {
    return Map.of(
            "bodyPresent", body != null,
            "titlePresent", body != null && body.containsKey("title"));
}
~~~

This snippet requires importing java.util.Map. An absent body yields body==null; a JSON null token can also deserialize to null. Therefore bodyPresent=false in this code means **no Map object was bound**, not a guarantee that the byte-level HTTP body was completely empty.

Even when required=false, malformed JSON is still an error; optional does not mean ignoring parser errors.

### 5.3. Defaults in DTO Records

~~~java
public record BookInput(String title, Integer copies, Boolean published) {
    public BookInput {
        if (copies == null) copies = 1;
        if (published == null) published = false;
    }
}
~~~

Because Jackson supports Java records, a compact constructor can assign defaults when target values are null. This is reasonable if a CREATE contract treats missing and explicit null identically. However, it **does not distinguish** those two states, and must not be reused this way for PATCH when explicit null carries a different meaning.

Avoid primitive int/boolean in a DTO when you need to know whether a field appeared, because primitives only hold 0/false and discard presence information. When 0/false are meaningful values, do not treat them as a "missing sentinel".

### 5.4. Field Initializers Are Not a Universal Solution

~~~java
public class SearchDto {
    private Integer size = 20;

    public Integer getSize() { return size; }
    public void setSize(Integer size) { this.size = size; }
}
~~~

In a Java bean, an initializer can retain 20 when JSON omits size, yet sending "size":null causes the setter to assign null. Jackson offers policies such as @JsonSetter(nulls=Nulls.SKIP), though behavior depends on DTO style and deserialization setup. Define explicit rules and write tests rather than relying on an initializer to handle every case.

## 6. Bean Validation and the Limits of required

Java can convert data successfully while the resulting value still violates business constraints. For example, size=-100 is a valid int, yet a paging API may require 1..100.

With a DTO:

~~~java
public record CreateBookInput(
        @NotBlank String title,
        @Positive Integer copies,
        Boolean published) {}
~~~

A Bean Validation provider is needed, usually via spring-boot-starter-validation in Boot applications. @Valid @RequestBody activates validation.

Summary of key constraint meanings:

| Constraint | When null | When invalid |
|---|---|---|
| @NotNull | Fails | Does not ensure String is non-empty |
| @NotBlank | Fails | Fails on empty or whitespace-only Strings |
| @NotEmpty | Fails | Fails on empty Strings/collections/maps/arrays |
| @Positive | Usually passes on null | Fails on numbers <= 0 |
| @Min(1) | Usually passes on null | Fails if number is less than 1 |
| @Size(min=1) | Usually passes on null | Fails when size is smaller than required |

**@Positive and @Min do not imply required.** If a field must be present and positive, combine @NotNull with @Positive/@Min. If a field is optional, @Positive validates client-supplied values while the service can still apply a default when null.

Do not silently fall back to defaults whenever conversion or validation fails, unless that is a clearly published policy. For example, size=0 should be rejected rather than silently turned into size=20 if the contract requires size to be 1 to 100.

### 6.1. Order of Operations Matters

In a typical request flow:

~~~text
HTTP request
  |
  +-- Match appropriate handler
  |
  +-- Read query/header/body and perform type conversion
  |
  +-- Apply defaultValue / deserialize DTO
  |
  +-- Run validation if configured
  |
  +-- Invoke controller/service and apply business defaults
  |
  +-- Return HTTP response
~~~

This diagram is generalized, not exact bytecode order for every argument resolver. Annotation defaults can be applied **before** the controller receives Java variables. Defaults located only in the service are applied **after** data passes binding and validation. Place defaults at the right layer so you do not accidentally introduce conflicting rules.

## 7. Where Should Defaults Live?

| Layer | Example | When to use |
|---|---|---|
| HTTP annotation | @RequestParam(defaultValue="20") | Simple query/header/cookie defaults |
| DTO constructor | copies=1 if null | Consistent DTO deserialization/initialization rules |
| Service layer | Default sort to createdAt when absent | Business defaults shared across HTTP, batch, events |
| Domain model | Default entity state | Protecting domain invariants |
| Database | DEFAULT on omitted columns | Storage-level safeguards where appropriate |
| Client UI | Display page input as 1 | Better UX; does not replace server rules |

An important default should have **a single source of truth**. If an HTTP annotation chooses size=20 while an internal job uses 200, the same business operation may behave differently depending on the entry point. When a default is a domain rule, consider placing it in the service/domain layer and using annotations only for consistent HTTP convenience.

Changing a default can be a breaking behavioral change. Switching the default page size from 20 to 100 can increase query time, response payload size, and database load even though the endpoint URL stays identical. Add tests and update docs whenever defaults change.

## 8. Runnable Spring Boot MVC Example: Query, Headers, Body, and Validation

This example uses Java 17+, Spring Boot 3.x, Spring MVC (Servlet), and standard embedded Tomcat. Assume the project is generated with Spring Initializr/Gradle and the Spring Boot plugin, with these dependencies in build.gradle:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-validation'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

No database is needed for the demo. The code returns simulated responses without persisting to a real DB.

### 8.1. Main Class

File src/main/java/dev/example/input/RequestInputApplication.java:

~~~java
package dev.example.input;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class RequestInputApplication {

    public static void main(String[] args) {
        SpringApplication.run(RequestInputApplication.class, args);
    }
}
~~~

### 8.2. Complete Controller

File src/main/java/dev/example/input/RequestInputController.java:

~~~java
package dev.example.input;

import java.util.Map;
import java.util.Optional;
import java.util.Set;

import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Positive;

import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.CookieValue;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@RestController
@RequestMapping("/api")
public class RequestInputController {

    public record SearchResult(
            int page,
            int size,
            String keyword,
            String sort,
            Boolean includeArchived,
            boolean archiveFilterProvided) {}

    public record CreateBookInput(
            @NotBlank String title,
            @Positive Integer copies,
            Boolean published) {}

    public record BookResult(
            String title,
            int copies,
            boolean published) {}

    public record ClientHints(String mode, String theme) {}

    @GetMapping("/search")
    public SearchResult search(
            @RequestParam(name = "page", defaultValue = "1")
            int page,
            @RequestParam(name = "size", defaultValue = "20")
            int size,
            @RequestParam(name = "q", required = false)
            String q,
            @RequestParam(name = "sort")
            Optional<String> sort,
            @RequestParam(name = "includeArchived", required = false)
            Boolean includeArchived) {

        if (page < 1 || size < 1 || size > 100) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST,
                    "page must be >= 1; size must be 1..100");
        }

        String normalizedQ =
                q == null || q.isBlank() ? null : q.strip();

        String sortBy = sort
                .filter(value -> !value.isBlank())
                .map(String::strip)
                .orElse("createdAt");

        if (!Set.of("createdAt", "title").contains(sortBy)) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST,
                    "sort must be createdAt or title");
        }

        return new SearchResult(
                page, size, normalizedQ, sortBy,
                includeArchived, includeArchived != null);
    }

    @GetMapping("/client-hints")
    public ClientHints clientHints(
            @RequestHeader(
                    name = "X-Mode", defaultValue = "standard")
            String mode,
            @CookieValue(name = "theme", required = false)
            String theme) {

        return new ClientHints(
                mode,
                theme == null || theme.isBlank() ? "system" : theme);
    }

    @PostMapping(
            path = "/books",
            consumes = MediaType.APPLICATION_JSON_VALUE,
            produces = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<BookResult> create(
            @Valid @RequestBody CreateBookInput body) {

        int copies = body.copies() == null ? 1 : body.copies();
        boolean published = body.published() != null
                && body.published();

        BookResult result =
                new BookResult(body.title().strip(), copies, published);

        return ResponseEntity.status(HttpStatus.CREATED).body(result);
    }

    @PostMapping(path = "/draft",
                 consumes = MediaType.APPLICATION_JSON_VALUE)
    public Map<String, Boolean> optionalDraft(
            @RequestBody(required = false) Map<String, Object> body) {

        return Map.of(
                "bodyPresent", body != null,
                "titlePresent",
                body != null && body.containsKey("title"));
    }
}
~~~

Both Java files above contain the required imports and classes for a Spring Boot MVC Java 17+ project. Records are supported by Jackson in standard starter-web. The controller does not query a database; the defaults shown are illustrative policies.

**Read the design decisions carefully:**

- page=1 and size=20 are defaults only for missing/empty values; size=-1 or size=101 is rejected instead of falling back.
- q is optional; the code **intentionally** treats both missing and blank as normalizedQ=null, meaning no keyword filter.
- sort uses Optional, defaulting missing or blank to createdAt; an unknown sort value is rejected via whitelist. Never interpolate client-supplied sort strings directly into SQL.
- includeArchived uses Boolean to preserve three states (true/false/null), and archiveFilterProvided reports whether a value was bound.
- title requires @NotBlank. Null copies defaults to 1, while copies=0 fails @Positive; null published defaults to false, while explicit false remains false.
- optionalDraft allows an absent body not bound as a Map, though bodyPresent does not distinguish an absent body from a JSON null token.

### 8.3. Configuration and Run Command

File src/main/resources/application.yml:

~~~yaml
server:
  port: 8080
~~~

Run inside the Gradle project directory:

~~~bash
./gradlew bootRun
~~~

On Windows PowerShell:

~~~powershell
.\gradlew.bat bootRun
~~~

### 8.4. Testing GET Defaults, Valid, and Invalid Cases

~~~bash
curl -i "http://localhost:8080/api/search"
curl -i "http://localhost:8080/api/search?page=&size="
curl -i "http://localhost:8080/api/search?page=2&size=15&sort=title"
curl -i "http://localhost:8080/api/search?size=0"
curl -i "http://localhost:8080/api/search?page=abc"
~~~

The first two requests normally return HTTP 200 with page=1, size=20. The third returns page=2, size=15, sort="title". size=0 and page=abc normally return HTTP 400 from the business range check or type conversion. Do not rely on a fixed JSON error body structure: the error shape is determined by Spring Boot configuration and ControllerAdvice.

### 8.5. Testing That False Differs from Missing

~~~bash
curl -i "http://localhost:8080/api/search"
curl -i "http://localhost:8080/api/search?includeArchived=false"
curl -i "http://localhost:8080/api/search?includeArchived=true"
~~~

The request omitting includeArchived returns archiveFilterProvided=false; sending false yields includeArchived=false and archiveFilterProvided=true; sending true yields includeArchived=true and archiveFilterProvided=true. That is why optional Boolean should not be turned into primitive boolean when absence carries meaning.

### 8.6. Testing JSON Body Defaults

~~~bash
curl -i -X POST "http://localhost:8080/api/books" \
  -H "Content-Type: application/json" \
  -d '{"title":"Spring Boot"}'
~~~

Expected key result: HTTP 201 with body:

~~~json
{"title":"Spring Boot","copies":1,"published":false}
~~~

When all fields are sent:

~~~bash
curl -i -X POST "http://localhost:8080/api/books" \
  -H "Content-Type: application/json" \
  -d '{"title":"Web Runtime","copies":3,"published":true}'
~~~

Expected result:

~~~json
{"title":"Web Runtime","copies":3,"published":true}
~~~

With body {"title":"Book","copies":0} or {"copies":2} missing title, validation results in HTTP 400 under default configuration. An empty HTTP body with @RequestBody required=true is also rejected.

Headers such as Content-Length and Date are not fixed contract outputs; inspect only the status and logical body.

### 8.7. Testing Optional Headers and Cookies

~~~bash
curl -i "http://localhost:8080/api/client-hints"
curl -i "http://localhost:8080/api/client-hints" \
  -H "X-Mode: compact" -H "Cookie: theme=dark"
~~~

The first call returns mode=standard, theme=system; the second returns mode=compact, theme=dark assuming no proxy/filter modifies the request. Never treat X-Mode or the theme cookie as authentication data.

## 9. PATCH and the Difference Between Missing and Explicit JSON Null

For a CREATE API, omitting copies or sending null might both mean using default 1. But for PATCH, presence typically drives the update action:

~~~json
{}
~~~

may mean "keep existing fields unchanged".

~~~json
{"displayName":null}
~~~

may mean "clear the name"; or return 400 if null is disallowed.

~~~json
{"displayName":""}
~~~

may mean setting an empty string or failing @NotBlank. Never collapse these three cases without an explicit contract.

### 9.1. Why a Simple Nullable DTO Is Not Enough

~~~java
public record ProfilePatch(String displayName, String phone) {}
~~~

A deserializer can yield displayName=null both when JSON omits the field and when explicit null is sent. Code like:

~~~java
if (patch.displayName() != null) {
    entity.setDisplayName(patch.displayName());
}
~~~

cannot express "clear the name via explicit null". Conversely, always calling setDisplayName(null) would cause a request omitting the name to wipe the old value by mistake.

### 9.2. Using JsonNode to Track Presence

~~~java
import com.fasterxml.jackson.databind.JsonNode;

void applyPatch(JsonNode patch, Profile profile) {
    if (!patch.isObject()) {
        throw new IllegalArgumentException("Expected JSON object");
    }

    if (!patch.has("displayName")) {
        return;
    }

    JsonNode value = patch.get("displayName");

    if (value.isNull()) {
        profile.setDisplayName(null);
    } else if (value.isTextual() && !value.textValue().isBlank()) {
        profile.setDisplayName(value.textValue().strip());
    } else {
        throw new IllegalArgumentException("Invalid displayName");
    }
}
~~~

This is a snippet, not a standalone program: it needs a Profile class, Jackson, and a way to map IllegalArgumentException to HTTP 400. Key points:

- patch.has("displayName")==false: the field is absent from JSON, keep unchanged.
- has==true and value.isNull(): the field is present with JSON null.
- has==true, textual, and non-blank: valid String value present.

JsonNode.hasNonNull("displayName") **does not replace has(...)** when you need to detect explicit null, because hasNonNull returns false for NullNode.

### 9.3. JSON Merge Patch and JSON Patch Are Different

With JSON Merge Patch (RFC 7396), a member with value null generally means deleting that member from the target object; absent members remain unchanged. With JSON Patch (RFC 6902), explicit add, replace, and remove operations describe changes.

Spring Boot does not automatically implement full RFC semantics merely because a method uses @PatchMapping. Explicitly specify the Content-Type, validation, concurrency control (ETag/If-Match if needed), error handling, and response semantics.

### 9.4. False and 0 Are Valid Updates

Avoid the following check when 0 is a valid value:

~~~java
// Wrong when you want to allow setting count to 0
if (patchCount != 0) {
    entity.setCount(patchCount);
}
~~~

Similarly, if (patchActive) skips explicit false. For PATCH, check **whether the field was sent**, and only then inspect its value. A presence-aware representation or JsonNode is more suitable than primitives.

## 10. Collections, Enums, Dates, and Nested Data

### 10.1. Missing List Differs from Empty List

~~~json
{}
~~~

differs from:

~~~json
{"tags":[]}
~~~

In PATCH, omitting tags may mean keep unchanged; [] may mean clear all tags. In CREATE, [] may be valid or rejected by @NotEmpty. A DTO List<String> can distinguish [] from null in some cases, yet absent and JSON null still collapse to null without presence tracking.

Define limits on element counts, duplicate policies, ordering, string normalization, and how null elements are handled.

### 10.2. Enum Conversion and Validation

~~~java
public enum SortDirection {
    ASC, DESC
}
~~~

If accepting @RequestParam(name="direction", defaultValue="ASC") SortDirection direction, a matching string converts to the enum. Non-matching values like SIDEWAYS are rejected. Do not assume "asc" automatically maps to ASC across every converter or version. If case-insensitivity is required, configure an explicit converter and test it.

### 10.3. Dates and Timezones

~~~java
@GetMapping("/events")
String events(
        @RequestParam(name = "date", required = false)
        @DateTimeFormat(iso = DateTimeFormat.ISO.DATE)
        LocalDate date) {

    LocalDate selected =
            date == null ? LocalDate.now(ZoneOffset.UTC) : date;

    return selected.toString();
}
~~~

This snippet requires importing LocalDate, ZoneOffset, and DateTimeFormat and placing it in a controller. Defaulting to the current UTC date is an illustrative policy; a domain tied to a customer's timezone requires an explicit ZoneId. No fixed stdout can be shown because "today" depends on execution time.

### 10.4. Nested Objects Have Multiple Layers of Missingness

With {"preferences":{"language":"vi"}}, possible cases include:

- preferences is absent.
- preferences=null.
- preferences={}.
- preferences exists but language is missing.
- language=null or "".

In a PATCH API, do not blindly replace the entire preferences object just because the caller updated one child field. Define merge semantics and validate at each level.

## 11. Spring WebFlux: Same Problem, Reactive Pipeline

Spring WebFlux provides annotated @RequestParam, @RequestHeader, @RequestBody, and corresponding resolvers. However, it uses a non-blocking pipeline with Mono/Flux and differs in how form data is read. For WebFlux annotated controllers, @RequestParam focuses on **query parameters**; form/multipart request data uses separate reading/binding mechanisms.

A WebFlux reactive server project should include spring-boot-starter-webflux and omit starter-web if you want to avoid Boot defaulting to Servlet MVC in typical setups.

### 11.1. Runnable WebFlux Controller Example

File src/main/java/dev/example/reactive/ReactiveInputController.java in a Java 17+ Boot WebFlux project:

~~~java
package dev.example.reactive;

import java.util.Map;

import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/reactive")
public class ReactiveInputController {

    public record Payload(String text) {}

    @GetMapping("/search")
    public Mono<Map<String, Object>> search(
            @RequestParam(name = "page", defaultValue = "1")
            int page,
            @RequestParam(name = "q", required = false)
            String q) {

        if (page < 1) {
            return Mono.error(new ResponseStatusException(
                    HttpStatus.BAD_REQUEST, "page must be positive"));
        }

        return Mono.just(Map.of(
                "page", page,
                "q", q == null ? "" : q));
    }

    @PostMapping("/optional-body")
    public Mono<Map<String, Boolean>> optionalBody(
            @RequestBody(required = false) Mono<Payload> body) {

        return body
                .map(value -> Map.of("bodyPresent", true))
                .defaultIfEmpty(Map.of("bodyPresent", false));
    }
}
~~~

To run, place a @SpringBootApplication class in the parent package dev.example.reactive or the same package, add spring-boot-starter-webflux, and start Boot. The example has no database and never calls block() or subscribe() inside the controller.

GET /reactive/search without page returns JSON with page=1; GET /reactive/search?page=0 returns 400. POST /reactive/optional-body with a valid Payload returns bodyPresent=true; if the deserializer emits Mono.empty() due to an absent payload, the result has bodyPresent=false.

**Do not equate Publisher emptiness with byte-level absence of the HTTP body.** A JSON literal null may not produce a concrete Payload; if you need to distinguish them, design a separate representation or presence check.

### 11.2. Testing with @WebFluxTest and WebTestClient

Create src/test/java/dev/example/reactive/ReactiveInputControllerTest.java:

~~~java
package dev.example.reactive;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.WebFluxTest;
import org.springframework.test.web.reactive.server.WebTestClient;

@WebFluxTest(controllers = ReactiveInputController.class)
class ReactiveInputControllerTest {

    @Autowired
    WebTestClient client;

    @Test
    void missingPageUsesDefault() {
        client.get().uri("/reactive/search")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.page").isEqualTo(1);
    }

    @Test
    void explicitZeroIsInvalid() {
        client.get().uri("/reactive/search?page=0")
                .exchange()
                .expectStatus().isBadRequest();
    }
}
~~~

This test requires spring-boot-starter-test in a WebFlux project and does not require opening a real HTTP port. When code includes security filters or other service beans, additional test configuration or integration tests may be required. WebTestClient verifies the reactive routing/binding/response pipeline; testing real TLS, proxies, or network connectors requires an integration test with an actual server.

### 11.3. Avoid Confusing WebClient with a WebFlux Server

WebClient is a reactive HTTP client that can be used inside Spring MVC. A controller returning Mono or a project having WebClient does not prove the server uses WebFlux's DispatcherHandler. If both starter-web and starter-webflux are present, Boot usually favors Servlet/MVC unless configured otherwise via web-application-type.

Always verify the active web stack, argument resolvers, and package imports when diagnosing unexpected optional parameter behavior.

## 12. MockMvc: Testing Missing/Empty/False/0 States in MVC

For RequestInputController in Section 8, create src/test/java/dev/example/input/RequestInputControllerTest.java:

~~~java
package dev.example.input;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class RequestInputControllerTest {

    @Autowired
    MockMvc mvc;

    @Test
    void missingQueryUsesDefaults() throws Exception {
        mvc.perform(get("/api/search"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.page").value(1))
                .andExpect(jsonPath("$.size").value(20))
                .andExpect(jsonPath("$.sort").value("createdAt"))
                .andExpect(jsonPath("$.archiveFilterProvided").value(false));
    }

    @Test
    void emptyQueryUsesDefaults() throws Exception {
        mvc.perform(get("/api/search?page=&size="))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.page").value(1))
                .andExpect(jsonPath("$.size").value(20));
    }

    @Test
    void invalidTypeGets400() throws Exception {
        mvc.perform(get("/api/search?page=abc"))
                .andExpect(status().isBadRequest());
    }

    @Test
    void explicitZeroIsNotMissing() throws Exception {
        mvc.perform(get("/api/search?size=0"))
                .andExpect(status().isBadRequest());
    }

    @Test
    void falseIsAnExplicitValue() throws Exception {
        mvc.perform(get("/api/search?includeArchived=false"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.includeArchived").value(false))
                .andExpect(jsonPath("$.archiveFilterProvided").value(true));
    }

    @Test
    void missingJsonFieldsUseCreateDefaults() throws Exception {
        mvc.perform(post("/api/books")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"title\":\"Spring Boot\"}"))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.copies").value(1))
                .andExpect(jsonPath("$.published").value(false));
    }

    @Test
    void zeroCopiesFailsValidation() throws Exception {
        mvc.perform(post("/api/books")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"title\":\"Book\",\"copies\":0}"))
                .andExpect(status().isBadRequest());
    }

    @Test
    void missingRequiredTitleFails() throws Exception {
        mvc.perform(post("/api/books")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"copies\":2}"))
                .andExpect(status().isBadRequest());
    }

    @Test
    void missingBodyFails() throws Exception {
        mvc.perform(post("/api/books")
                .contentType(MediaType.APPLICATION_JSON))
                .andExpect(status().isBadRequest());
    }
}
~~~

From the Gradle project directory:

~~~bash
./gradlew test
~~~

These tests cover many distinct meanings of missing and invalid data. You do not need to assert the full default Spring Boot error body because its format can vary across versions and error handlers. For production APIs, define a stable error contract and test against it.

MockMvc verifies request binding and the MVC pipeline, but does not replace integration tests involving networking, proxies, or security. If an API relies on path rewrites, content negotiation, multipart handling, or custom Servlet configuration, verify it against a real server.

## 13. Recommended Input Test Matrix

| Input | Expected contract |
|---|---|
| page absent | page=1 |
| page= | page=1 via @RequestParam defaultValue |
| page=3 | page=3 |
| page=0 | HTTP 400 due to range constraint |
| page=abc | HTTP 400 due to type conversion |
| sort absent | sort=createdAt |
| sort=title | sort=title |
| sort=unknown | HTTP 400 due to whitelist |
| includeArchived absent | No filter applied, archiveFilterProvided=false |
| includeArchived=false | Keep explicit false |
| includeArchived=true | Keep explicit true |
| Header X-Mode missing | mode=standard |
| Cookie theme missing | theme=system |
| POST /books body missing | HTTP 400 via @RequestBody required |
| JSON field title missing | HTTP 400 via @NotBlank |
| JSON title has whitespace only | HTTP 400 via @NotBlank |
| JSON copies missing | copies=1 per create policy |
| JSON copies=null | copies=1 per illustrative create policy |
| JSON copies=0 | HTTP 400 via @Positive |
| JSON published=false | Keep explicit false |
| JSON published missing | published=false per create policy |
| PATCH {} | Keep existing data per contract |
| PATCH {"displayName":null} | Clear field or return error, per contract |
| PATCH {"tags":[]} | Clear all tags or keep empty set per contract |
| Malformed JSON | Body read failure, typically 400 |
| Wrong Content-Type | Possibly 415 depending on consumes and converters |

This test suite matters more than testing only a happy-path request with every field populated. Bugs like "optional treated as required", "0 treated as missing", and "PATCH accidentally deletes a field" rarely appear in happy paths.

## 14. Common Mistakes

**Mistake 1 — Using int/boolean for an optional field without a default.** Primitives cannot hold null; when missing during binding they can error out or lose the third state. Use Integer/Boolean/Optional when absence must be represented.

**Mistake 2 — Using defaults to mask invalid types.** page=abc is a parse failure, not "page missing"; size=-1 was sent explicitly, not omitted. Return 400 per the contract.

**Mistake 3 — Treating false and 0 as "user did not enter anything".** Both are valid values in many domains and in PATCH requests. Never use if (active) or if (count != 0) as presence checks.

**Mistake 4 — Using @PathVariable(required=false) without adding the matching URL pattern.** The annotation does not turn /items/{id} into /items. Declare routes explicitly.

**Mistake 5 — Thinking @RequestBody(required=false) ignores malformed JSON.** It allows the body to be absent; a present but invalid body still causes an error.

**Mistake 6 — Adding @Positive and assuming it makes the field required.** With null, @Positive normally passes; pair it with @NotNull if the field is required.

**Mistake 7 — Sharing identical DTO defaults between CREATE and PATCH.** CREATE may reasonably default omitted published to false; PATCH omitting published normally means keep unchanged. Use separate contracts and DTOs when semantics differ.

**Mistake 8 — Failing to distinguish a missing field from explicit null.** With plain nullable JSON DTOs, both map to null. When presence semantics matter, use JsonNode or a presence-aware representation.

**Mistake 9 — Placing conflicting defaults across layers.** Annotations, DTOs, services, and databases picking different defaults lead to inconsistency. Choose a single source of truth.

**Mistake 10 — Failing to protect client-supplied sort/filter values.** Optional does not mean trusted. Apply whitelists, length limits, range checks, and validation; never concatenate arbitrary strings into SQL.

**Mistake 11 — Using insecure default values.** Missing roles, tenants, or auth tokens must never default to elevated privileges or an arbitrary identity. Use the security context and deny-by-default.

**Mistake 12 — Testing only valid inputs with every field present.** Always test absent, empty, whitespace, null, false, zero, type mismatches, out-of-range values, and duplicate parameters where relevant.

**Mistake 13 — Assuming all Spring MVC code runs unchanged in WebFlux.** Annotation names may look similar, but form/body/multipart handling and reactive pipelines differ. Confirm the web stack before modifying code.

**Mistake 14 — Failing to update documentation when changing defaults.** Clients may rely on existing defaults; changing a default is a behavioral change even when the endpoint URL does not change.

## 15. Security and Trustworthiness of Defaults

Sensitive cases require extra care:

- A missing authentication token must remain unauthenticated, never assigned a demo token automatically.
- A missing tenantId must never default to another tenant unless grounded in the authenticated principal and server policy.
- Missing operation permissions must never default to admin privileges.
- Money-transfer APIs must not default amount/currency in a way that masks client mistakes.
- Never use query strings for identity verification when a security context is available.
- On PUT/PATCH, never apply defaults that overwrite data the client did not request to change.
- On validation failures, avoid logging full passwords, tokens, or sensitive personal data in error messages.

A good default is **intentionally designed and publicly documented**, not an unconditional fallback whenever code sees null.

## 16. Documenting with OpenAPI and Design Workflow

For every request field, specify:

1. Name and location: query, path, header, cookie, form, multipart, or JSON body.
2. Type: String, Integer, Boolean, enum, date, object, array, etc.
3. Is it required?
4. When absent, does it take a default, keep existing state, or fail?
5. Is JSON null permitted, and how does null differ from missing?
6. How are empty strings, blanks, 0, false, and [] handled?
7. Constraints: min/max/length/pattern/whitelist.
8. What status/error code is returned for wrong types or out-of-range values?
9. Do CREATE/PUT/PATCH share the same semantics?
10. Could older clients break if the default changes?

OpenAPI supports required, nullable, default, and constraints to describe the contract, though documentation does not replace runtime validation. Add tests for key states and keep documentation synchronized with the code.

A practical implementation workflow:

~~~text
Identify the request source
  -> List possible missing/empty/null/false/0/[] states
  -> Decide business rules for each state
  -> Choose Java types/DTOs/presence representation
  -> Place defaults at the right layer
  -> Add validation and error mapping
  -> Test absent, empty, invalid, and explicit values
  -> Verify security and compatibility
  -> Publish the contract
~~~

## 17. Self-Check Questions

**Question 1. Does @RequestParam(defaultValue="1") turn page=0 into 1?**  
No. 0 is an explicitly sent value. If invalid, return an error or handle it per the contract rather than falling back to the default.

**Question 2. Are required=false String and Optional<String> completely identical?**  
No. One typically uses null and the other uses Optional.empty for absence; conversion, blank handling, and normalization rules still must be defined.

**Question 3. Does @RequestBody(required=false) permit malformed JSON?**  
No. It permits an absent body per contract; a syntactically invalid body still triggers an error.

**Question 4. Why does @Positive Integer copies still allow missing copies?**  
Because null normally passes @Positive. If the field is required, add @NotNull; if optional, the service can apply a default.

**Question 5. Are JSON {"active":false} and {} identical during PATCH?**  
Not necessarily. false is an explicit value; missing usually means no change. A presence-aware DTO preserves that distinction.

**Question 6. Should a default tenant/role be derived from a client-sent query string?**  
Never create insecure defaults. Identity and authorization must come from the security context and server policies.

**Question 7. Does @PathVariable(required=false) automatically add the /items route alongside /items/{id}?**  
No. The matching route must be declared explicitly.

**Question 8. Why do we need both MockMvc and WebTestClient in this curriculum?**  
They test HTTP binding in two different stacks: MockMvc for Servlet MVC, and WebTestClient for reactive WebFlux. Neither verifies the full proxy/network environment by itself, so add integration tests when appropriate.

## 18. Key Takeaways

**Missing asks whether data is present; default decides what the application does when data is absent; validation decides whether provided data is acceptable.** Never collapse those three questions into a single null check.

In Spring Boot:

- @RequestParam(defaultValue=...) declares defaults for basic query/header inputs; with @RequestParam, missing/empty values can trigger the default.
- required=false with Integer, Boolean, or Optional represents optional inputs more cleanly than primitives without defaults.
- @RequestBody reads the whole body; a missing body differs from a missing JSON field. Plain Java DTOs may not distinguish missing JSON fields from explicit null.
- @Valid with Bean Validation enforces constraints; @Positive does not force presence, while @NotBlank rejects null/empty/blank.
- CREATE can apply defaults for missing fields, whereas PATCH must preserve presence semantics to avoid unintended deletions.
- Values such as 0, false, and empty collections are meaningful values, not sentinels for missing data.
- APIs with meaningful defaults require clear documentation, tests for missing/empty/invalid states, and appropriate security policies.

Clearly defining the behavior of every data state at the HTTP boundary makes applications more predictable, reduces request-binding bugs, and prevents incorrect updates caused by misinterpreting missing values.

## 19. References

- Spring MVC — @RequestParam: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/requestparam.html
- Spring MVC — @RequestBody: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/requestbody.html
- Spring MVC — Validation: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-validation.html
- Spring WebFlux — Annotated Controllers: https://docs.spring.io/spring-framework/reference/web/webflux/controller.html
- Spring WebFlux — @RequestParam: https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/requestparam.html
- Spring Boot — Validation: https://docs.spring.io/spring-boot/reference/io/validation.html
- Jakarta Bean Validation — Specification: https://jakarta.ee/specifications/bean-validation/
- IETF RFC 7396 — JSON Merge Patch: https://www.rfc-editor.org/rfc/rfc7396
- IETF RFC 6902 — JSON Patch: https://www.rfc-editor.org/rfc/rfc6902
