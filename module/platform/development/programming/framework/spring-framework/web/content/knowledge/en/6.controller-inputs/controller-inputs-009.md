# Null Values, Optional, and Distinguishing Missing vs. Empty Input in Spring MVC

## Objectives

In Spring MVC, **absent input**, **present but empty input**, **whitespace-only input**, **JSON null values**, and **values converted to null** can lead to different behaviors. This lesson helps you:

- Choose the right way to receive values via `@RequestParam`, `@RequestHeader`, `@PathVariable`, `@RequestBody`, and `@ModelAttribute`.
- Use `required=false`, `Optional<T>`, `defaultValue`, and `@Nullable` without losing important state distinctions.
- Distinguish `?name`, `?name=`, missing `name`, and `?name=%20` at the Servlet request parameter level.
- Distinguish a **missing JSON field**, a field with `null`, an empty string `""`, a whitespace-only string, an empty array `[]`, and an empty object `{}`.
- Design appropriate input validation and HTTP error codes; avoid overwriting data when handling partial updates (PATCH).

Scope: **Spring MVC (Servlet stack)**, Java 17+, Spring Framework 6.x / Spring Boot 3.x; many principles are similar in newer versions, though actual configuration changes must be verified. This is not a general Java `Optional` guide or about Spring WebFlux (WebFlux has different request-parameter rules).

## 1. Terminology table: how is "missing" different from "empty"?

Consider an input named `name`:

| Case | HTTP/JSON example | Initial meaning |
| --- | --- | --- |
| Missing/absent | `GET /items`, no `name` parameter | Client **did not send the parameter name** |
| Named, empty value | `GET /items?name=` or `?name` | Parameter is present; string value has length 0 |
| Named, whitespace only | `GET /items?name=%20` | Value is `" "`: **different from empty string** |
| Regular value | `GET /items?name=An` | Value is `"An"` |
| Missing JSON field | `{}` | Object has no `name` key |
| Explicit JSON null field | `{"name":null}` | Object **has the key**, but its value is JSON `null` |
| Empty string JSON field | `{"name":""}` | Object has the key; value is an empty string |
| Whitespace string JSON field | `{"name":"   "}` | Object has the key; value is a whitespace-only string |
| Empty JSON collection | `{"tags":[]}` | Array exists, containing 0 elements |
| Empty JSON object | `{"settings":{}}` | Object exists, containing 0 fields |

**Java `null` is not JSON `null` in the sense of "received".** Both an absent JSON field and a present JSON field with value `null` can land in a Java `String name` property as `null` after deserialization. If business requirements need to know *whether the client sent the field*, a plain Java `String` type is usually not enough.

A request parameter cannot inherently hold a "JSON null" value. The literal characters `null` in `?name=null` are just the string `"null"`, and do not automatically convert into `null` for a `String`.

## 2. `@RequestParam`: required, null, empty strings, and defaultValue

`@RequestParam` reads Servlet request parameters. In Spring MVC, parameters can come from the **query string or form data parsed by the Servlet container**; do not assume every `@RequestParam` only reads URL queries.

### 2.1. Required by default

```java
@GetMapping("/required")
public String required(@RequestParam("name") String name) {
    return "Hello " + name;
}
```

Under standard configuration:

- `GET /required` → `name` is missing → Spring returns `400 Bad Request` before running the method.
- `GET /required?name=` → `name` is `""`; the annotation **does not reject empty strings by default**.
- `GET /required?name=%20` → `name` contains a space; it does not automatically become an empty string.
- `GET /required?name=An` → `name` is `"An"`.

`required=true` is about **parameter presence/resolvability**, not a constraint meaning "must contain meaningful characters". To enforce non-empty or non-whitespace text, use business rules or Jakarta Bean Validation (`@NotBlank`) when validation is configured.

### 2.2. Allowing absence with `required=false`

```java
@GetMapping("/optional-string")
public String optionalString(
        @RequestParam(name = "name", required = false) String name) {
    return name == null ? "MISSING" :
            name.isEmpty() ? "EMPTY" :
            name.isBlank() ? "BLANK" : "VALUE";
}
```

With the default binder and no custom string-trimming editor applied:

| URL | Received `name` | Result |
| --- | --- | --- |
| `/optional-string` | Java `null` | `MISSING` |
| `/optional-string?name` | `""` | `EMPTY` |
| `/optional-string?name=` | `""` | `EMPTY` |
| `/optional-string?name=%20` | `" "` | `BLANK` |
| `/optional-string?name=An` | `"An"` | `VALUE` |

Do not assume `?name` and `?name=` can be distinguished via `@RequestParam String`: both are typically seen by the Servlet API as a present parameter with value `""`. If a problem truly needs to distinguish the syntax of those two forms, you must parse the raw query string under a controlled contract (also accounting for encoding, repeated keys, `+`, and `%xx` sequences); most APIs **do not need** that distinction.

### 2.3. Default values replace *both missing and empty*

```java
@GetMapping("/with-default")
public String withDefault(
        @RequestParam(name = "name", defaultValue = "guest") String name) {
    return name;
}
```

| Request | Result |
| --- | --- |
| `/with-default` | `guest` |
| `/with-default?name=` | `guest` |
| `/with-default?name` | `guest` |
| `/with-default?name=An` | `An` |
| `/with-default?name=%20` | `" "` under default configuration, **not guest** |

`defaultValue` implicitly makes the parameter optional, but it **erases the distinction between missing and empty**. If business logic requires "use default when missing; return error or clear data when empty", do not use `defaultValue` directly: accept `required=false` and branch on presence/value yourself.

### 2.4. Type conversion can erase the initial state

```java
@GetMapping("/integer")
public String integer(
        @RequestParam(name = "count", required = false) Integer count) {
    return count == null ? "NO_COUNT" : count.toString();
}
```

With default converters, both an absent parameter and `?count=` can convert to Java `null`. `?count=abc` cannot convert to a number: it typically produces `400 Bad Request` due to a conversion error rather than becoming `null`. If using `@RequestParam("count") int count`, `null` cannot be assigned to primitive `int`, and Spring raises an error instead of passing `null` into the method.

The Spring documentation emphasizes: **an empty string that turns into null after conversion can be treated as missing**, triggering a required-parameter error even when the parameter name actually appeared. For instance, `@RequestParam("count") Long count` with `?count=` typically produces a 400 error for being "missing after conversion". Exact behavior depends on converters and custom `@InitBinder` configuration.

## 3. Using `Optional<T>` in controllers

Spring MVC supports `java.util.Optional` for controller method arguments whose annotation has a `required` attribute, such as `@RequestParam` and `@RequestHeader`. It is equivalent to allowing missing values.

```java
@GetMapping("/optional-count")
public String count(@RequestParam("count") Optional<Integer> count) {
    return count.map(String::valueOf).orElse("NO_COUNT");
}
```

- `/optional-count` → `Optional.empty()` → `NO_COUNT`.
- `/optional-count?count=7` → `Optional.of(7)` → `7`.
- `/optional-count?count=` → with default conversion, an empty string to `Integer` becomes null → `Optional.empty()`.
- `/optional-count?count=abc` → converter does not understand `abc` → typically HTTP 400, **not** `Optional.empty()`.

For `Optional<String>`, an empty string value is usually **`Optional.of("")`** because the converter preserves empty strings, whereas an absent value produces `Optional.empty()`; do not assume every `Optional<T>` collapses empty strings into `empty`. Custom formatters/binders can alter behavior. `Optional` only represents **present / absent value after binding**; it does not retain full history of why a value disappeared.

Practical rules:

1. If you only need the value or a fallback when absent: use `Optional<T>` or `required=false`.
2. If you need to distinguish missing vs. empty query parameters: keep the parameter as `String` and check key presence via `HttpServletRequest.getParameterMap()` when needed.
3. If you need to distinguish an empty number from an unsent number: receive the parameter as `String` first, inspect its state, then parse via `Integer.parseInt`/conversion and return appropriate errors.
4. Do not declare `Optional` as a **JSON DTO field** solely to represent three-state PATCH semantics; a missing JSON field and an explicit null can both turn into "empty" under many deserialization setups. Use a representation that tracks presence when three states are required.

**Java `Optional` does not replace validation.** `Optional.of("")` still holds an empty string; if meaningful characters are required, check or validate content after unwrapping.

## 4. Checking *whether the parameter name appeared* with the Servlet API

When `@RequestParam(required=false) String name` returns `null`, most applications can treat it as missing. If you have registered a formatter/binder that converts empty strings to `null`, additionally check **key presence**:

```java
@GetMapping("/inspect")
public String inspect(
        @RequestParam(name = "name", required = false) String name,
        jakarta.servlet.http.HttpServletRequest request) {

    boolean sent = request.getParameterMap().containsKey("name");
    if (!sent) {
        return "MISSING";
    }
    if (name == null) {
        return "PRESENT_BUT_CONVERTED_TO_NULL";
    }
    if (name.isEmpty()) {
        return "EMPTY";
    }
    return name.isBlank() ? "BLANK" : "VALUE";
}
```

`request.getParameterMap()` retrieves **present parameters**, even when the value string is empty. `request.getParameterValues("name")` is useful when clients repeat keys like `?name=a&name=b`; receiving a single `String` is usually unsuitable for deciding repeated-input semantics. For APIs that accept only one value, check and reject repeated parameters when that affects business logic.

Do not parse `getQueryString()` directly for routine decisions unless necessary: query strings involve encoding, repeated keys, and interactions with form binding. Use the Servlet API for **parameter-present / parameter-absent** checks; use raw queries only when the API contract requires byte-level syntax.

## 5. `@RequestBody` and JSON: missing field vs. explicit null

`@RequestBody` goes through an `HttpMessageConverter` (typically the Jackson JSON converter when Jackson is present). There are **two distinct levels of absence**:

- **No HTTP body**: the request sends 0 body bytes.
- **Has a JSON object body, but lacks a field**: e.g., `{}`. This is not "no request body".

### 5.1. Is the entire request body required?

```java
@PostMapping(path = "/receive", consumes = "application/json")
public String receive(@RequestBody(required = false) MyDto body) {
    return body == null ? "NO_DESERIALIZED_OBJECT" : "OBJECT_RECEIVED";
}

public record MyDto(String name) {}
```

With `@RequestBody` defaulting to `required=true`, an absent body typically leads to **HTTP 400** before the method runs. `required=false` allows missing bodies and can pass `null` into the method. However:

- The JSON literal `null` can also be converted by Jackson into Java `null`. The example above **cannot reliably distinguish** whether the request had zero body bytes or the client sent the four characters `null`.
- JSON `{}` is a valid object; for a DTO record with `String name`, `name` can be `null` while the DTO itself still exists.
- Body `{"name":null}` can produce a DTO with `name==null`, identical to `{}`. You have lost track of whether the field was sent.
- Malformed JSON syntax typically causes **400 Bad Request** (body read error), not "missing body".
- `required=false` does not bypass media-type (`Content-Type`) checks or JSON conversion errors; do not use it to legitimize invalid data.

When you need to check **actual HTTP body length** separately from JSON literal `null`, you must intentionally design a raw-body reading layer compatible with Servlet/request caching. Never read the input stream a second time after a converter has consumed it. Avoid treating `required=false` as a solution for distinguishing every state.

### 5.2. A simple Java DTO usually merges missing and null

```java
public record ProfileInput(String nickname, Integer age) {}
```

With standard Jackson, without special required configuration:

| Submitted JSON | `nickname` in DTO | `age` in DTO |
| --- | --- | --- |
| `{}` | `null` | `null` |
| `{"nickname":null}` | `null` | `null` |
| `{"nickname":""}` | `""` | `null` |
| `{"nickname":" "}` | `" "` | `null` |
| `{"age":0}` | `null` | `0` |

The core point is that a DTO only captures **values after deserialization**. Jackson has options for coercion, constructors, primitives, and null handling; results can differ under custom configurations. Do not rely on default DTO behavior as a PATCH contract if you need to distinguish "keep unchanged" from "clear".

### 5.3. `JsonNode` preserves field presence

If business logic requires distinguishing missing/null/empty, you can accept a JSON object using `JsonNode`:

```java
@PostMapping(path = "/field", consumes = "application/json")
public String field(@RequestBody com.fasterxml.jackson.databind.JsonNode root) {
    if (!root.isObject()) {
        throw new org.springframework.web.server.ResponseStatusException(
                org.springframework.http.HttpStatus.BAD_REQUEST,
                "JSON object required");
    }

    com.fasterxml.jackson.databind.JsonNode field = root.get("nickname");

    if (field == null) {
        return "MISSING";              // no "nickname" key
    }
    if (field.isNull()) {
        return "NULL";                 // {"nickname":null}
    }
    if (field.isTextual() && field.textValue().isEmpty()) {
        return "EMPTY";                // {"nickname":""}
    }
    if (field.isTextual() && field.textValue().isBlank()) {
        return "BLANK";                // {"nickname":"   "}
    }
    return "PRESENT_NONEMPTY";
}
```

`JsonNode.get("nickname") == null` indicates the field is absent. `root.has("nickname")` is true if the key exists **even when its value is explicit JSON null**. `root.hasNonNull("nickname")` is true only when the field exists and its value is not JSON null. `root.path("nickname")` returns `MissingNode` when absent, while explicit `null` is `NullNode`; if using `path`, you must check `isMissingNode()` and `isNull()` separately. Do not call `asText()` unconditionally and use the returned string to infer whether a key exists.

For complex PATCH operations, use a DTO with a mechanism that records which fields appeared (custom Jackson setters, presence flags, or JSON Merge Patch / JSON Patch under an explicit contract). Using `JsonNode` is an easy-to-understand choice for examples, but large systems require validation, whitelisting valid fields, and avoiding direct entity updates from arbitrary JSON.

## 6. Validation: `@NotNull`, `@NotEmpty`, and `@NotBlank` differ

Use Jakarta Bean Validation with Spring Boot 3 and the `spring-boot-starter-validation` dependency. When using `@Valid @RequestBody` on a suitable DTO, validation failures typically become **HTTP 400** via `MethodArgumentNotValidException` under default MVC configuration.

| Annotation | Semantic check | `null` | `""` | `"   "` |
| --- | --- | --- | --- | --- |
| `@NotNull` | Value is not null | Invalid | Valid | Valid |
| `@NotEmpty` | Not null and not empty; applies to supported strings/collections/arrays/maps | Invalid | Invalid | Valid |
| `@NotBlank` | Not null and string contains at least one non-whitespace character | Invalid | Invalid | Invalid |

Example creation DTO:

```java
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Positive;

public record CreateProfile(
        @NotBlank String nickname,
        @NotNull @Positive Integer age) {}
```

- Missing `nickname`, explicit null, `""`, or `"   "` are all invalid under `@NotBlank`.
- Missing/null `age` is rejected by `@NotNull`; `0` or negative numbers are rejected by `@Positive`.
- `Integer` allows representing missing/null before validation. With primitive `int`, Jackson may assign a default `0` (depending on coercion) and lose the null trace, so prefer wrapper types when a "required" rule is needed.
- `@Size(min=1)` is not equivalent to `@NotNull`: for many constraints such as `@Size`, `null` is considered valid so existence checks stay separate from length bounds.

If constraints are placed directly on controller method parameters (e.g., `@RequestParam @NotBlank String name`), that may trigger **method validation** with a different exception path (`HandlerMethodValidationException` in Spring MVC 6.1+). Check your actual Spring configuration; this lesson uses `@Valid` with DTOs for more predictable testing.

## 7. Complete application example: Java 17+ and Spring Boot 3.x

Below is a controller that **compiles in a Spring Boot project with Spring MVC, Jackson, and Jakarta Validation**. Place it at `src/main/java/com/example/demo/InputController.java`. To have a runnable app, a `@SpringBootApplication` class in the same or parent package and Web/Validation dependencies are required.

```java
package com.example.demo;

import com.fasterxml.jackson.databind.JsonNode;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Positive;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

import java.util.Map;
import java.util.Optional;

@RestController
@RequestMapping("/inputs")
public class InputController {

    @GetMapping("/query")
    public QueryView query(
            @RequestParam(name = "q", required = false) String q,
            @RequestParam(name = "count") Optional<Integer> count,
            HttpServletRequest request) {

        boolean supplied = request.getParameterMap().containsKey("q");
        String state;
        if (!supplied) {
            state = "MISSING";
        } else if (q == null) {
            state = "CONVERTED_TO_NULL";
        } else if (q.isEmpty()) {
            state = "EMPTY";
        } else if (q.isBlank()) {
            state = "BLANK";
        } else {
            state = "VALUE";
        }

        return new QueryView(state, q,
                count.map(String::valueOf).orElse("NO_COUNT"));
    }

    @GetMapping("/default")
    public Map<String, String> defaultQuery(
            @RequestParam(name = "q", defaultValue = "guest") String q) {
        return Map.of("q", q);
    }

    @GetMapping("/required")
    public Map<String, Long> required(@RequestParam("id") Long id) {
        return Map.of("id", id);
    }

    @PostMapping(path = "/json",
            consumes = MediaType.APPLICATION_JSON_VALUE,
            produces = MediaType.APPLICATION_JSON_VALUE)
    public FieldView inspectJson(@RequestBody JsonNode root) {
        if (!root.isObject()) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST, "JSON object required");
        }

        JsonNode nickname = root.get("nickname");
        String state;
        if (nickname == null) {
            state = "MISSING";
        } else if (nickname.isNull()) {
            state = "NULL";
        } else if (nickname.isTextual() && nickname.textValue().isEmpty()) {
            state = "EMPTY";
        } else if (nickname.isTextual() && nickname.textValue().isBlank()) {
            state = "BLANK";
        } else {
            state = "PRESENT_NONEMPTY";
        }

        String textValue = (nickname != null && nickname.isTextual())
                ? nickname.textValue() : null;
        return new FieldView(state, textValue);
    }

    @PostMapping(path = "/optional-body",
            consumes = MediaType.APPLICATION_JSON_VALUE)
    public Map<String, String> optionalBody(
            @RequestBody(required = false) JsonNode root) {
        return Map.of("state",
                root == null ? "NO_BODY_OR_JSON_NULL" : "HAS_JSON_VALUE");
    }

    @PostMapping(path = "/profiles",
            consumes = MediaType.APPLICATION_JSON_VALUE,
            produces = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<Map<String, String>> createProfile(
            @Valid @RequestBody CreateProfile body) {
        // Demo validates input without saving to a database yet.
        return ResponseEntity.status(HttpStatus.CREATED)
                .body(Map.of("status", "ACCEPTED"));
    }

    public record QueryView(String state, String q, String count) {}
    public record FieldView(String state, String value) {}

    public record CreateProfile(
            @NotBlank String nickname,
            @NotNull @Positive Integer age) {}
}
```

Requires `spring-boot-starter-web` (which provides Web MVC and Jackson in standard Boot setups) and `spring-boot-starter-validation` (for Jakarta Bean Validation). Create the bootstrap class if the project does not have one yet:

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

Second file: `src/main/java/com/example/demo/DemoApplication.java`. Run the Spring Boot-configured Maven project:

```bash
./mvnw spring-boot:run
```

On Windows PowerShell: `.\mvnw.cmd spring-boot:run`. Because the controller uses Spring, Jackson, and Jakarta Validation, **you cannot run it simply with `javac InputController.java` without libraries**; the command above applies to a Boot project with an appropriate `pom.xml` and Maven Wrapper. Default configuration runs on port 8080 unless `server.port` is changed.

## 8. Practicing with curl and verifiable results

The commands below use `curl` in bash/zsh; Windows PowerShell can use `curl.exe` on a single line.

### 8.1. Query parameter

**Without passing `q`:**

```bash
curl -s "http://localhost:8080/inputs/query"
```

Expected JSON under default Jackson:

```json
{"state":"MISSING","q":null,"count":"NO_COUNT"}
```

**Passing empty string `q=`:**

```bash
curl -s "http://localhost:8080/inputs/query?q="
```

```json
{"state":"EMPTY","q":"","count":"NO_COUNT"}
```

**Passing a URL-encoded space:**

```bash
curl -s "http://localhost:8080/inputs/query?q=%20"
```

```json
{"state":"BLANK","q":" ","count":"NO_COUNT"}
```

**Regular value and valid number:**

```bash
curl -s "http://localhost:8080/inputs/query?q=Lan&count=3"
```

```json
{"state":"VALUE","q":"Lan","count":"3"}
```

The JSON payloads above show **field values**, without guaranteeing serializer key order. If an application changes Jackson configuration to omit null fields, `"q":null` may not appear; the `state` field still demonstrates the distinction.

**Empty numeric parameter:** `GET /inputs/query?count=` → `count` is `Optional.empty()` per default converters, so the body `count` is `"NO_COUNT"`. **Malformed numeric parameter:** `GET /inputs/query?count=abc` → typically HTTP 400 because it cannot be converted to `Integer`.

### 8.2. Default values

```bash
curl -s "http://localhost:8080/inputs/default"
curl -s "http://localhost:8080/inputs/default?q="
curl -s "http://localhost:8080/inputs/default?q=Lan"
```

Respectively, `q` in the JSON is `"guest"`, `"guest"`, `"Lan"`. This example shows that `defaultValue` intentionally collapses missing and empty.

### 8.3. JSON fields: missing, null, empty, blank

```bash
curl -s http://localhost:8080/inputs/json \
  -H "Content-Type: application/json" \
  --data '{}'
```

Expected `state`: `MISSING`.

```bash
curl -s http://localhost:8080/inputs/json \
  -H "Content-Type: application/json" \
  --data '{"nickname":null}'
```

Expected `state`: `NULL`.

```bash
curl -s http://localhost:8080/inputs/json \
  -H "Content-Type: application/json" \
  --data '{"nickname":""}'
```

Expected `state`: `EMPTY`.

```bash
curl -s http://localhost:8080/inputs/json \
  -H "Content-Type: application/json" \
  --data '{"nickname":"   "}'
```

Expected `state`: `BLANK`.

Here `JsonNode` preserves key presence: `get` returns Java null when **the key is absent**, while `{"nickname":null}` produces a node with `isNull() == true`.

### 8.4. Required body and validation

```bash
curl -i http://localhost:8080/inputs/profiles \
  -H "Content-Type: application/json" \
  --data '{"nickname":"","age":18}'
```

Expected **400** because `@NotBlank` rejects an empty nickname. With valid input:

```bash
curl -i http://localhost:8080/inputs/profiles \
  -H "Content-Type: application/json" \
  --data '{"nickname":"Lan","age":18}'
```

Expected **201 Created** and JSON body containing `"status":"ACCEPTED"`.

`POST /inputs/optional-body` with `Content-Type: application/json` and no body is accepted because `required=false`. If a JSON literal `null` body is sent, the converter can also yield Java `null`; the endpoint will return the same state `NO_BODY_OR_JSON_NULL`. This is an **intentional limitation** of the decoded type, not proof that the HTTP bodies were identical.

## 9. Testing with MockMvc: verifying each state

Add `spring-boot-starter-test` as a test dependency. The following example goes in `src/test/java/com/example/demo/InputControllerTest.java`, running on Boot 3.x without custom security/filters in the test environment:

```java
package com.example.demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(InputController.class)
class InputControllerTest {

    @Autowired
    MockMvc mvc;

    @Test
    void distinguishesMissingEmptyAndBlankQuery() throws Exception {
        mvc.perform(get("/inputs/query"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.state").value("MISSING"));

        mvc.perform(get("/inputs/query").param("q", ""))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.state").value("EMPTY"));

        mvc.perform(get("/inputs/query").param("q", " "))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.state").value("BLANK"));
    }

    @Test
    void optionalNumberKeepsValidValueButAllowsMissing() throws Exception {
        mvc.perform(get("/inputs/query").param("count", "3"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.count").value("3"));

        mvc.perform(get("/inputs/query").param("count", ""))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.count").value("NO_COUNT"));

        mvc.perform(get("/inputs/query").param("count", "abc"))
                .andExpect(status().isBadRequest());
    }

    @Test
    void defaultValueCollapsesMissingAndEmpty() throws Exception {
        mvc.perform(get("/inputs/default"))
                .andExpect(jsonPath("$.q").value("guest"));

        mvc.perform(get("/inputs/default").param("q", ""))
                .andExpect(jsonPath("$.q").value("guest"));
    }

    @Test
    void missingOrBlankRequiredNumberIsRejected() throws Exception {
        mvc.perform(get("/inputs/required"))
                .andExpect(status().isBadRequest());

        mvc.perform(get("/inputs/required").param("id", ""))
                .andExpect(status().isBadRequest());
    }

    @Test
    void jsonFieldPresenceIsPreservedByJsonNode() throws Exception {
        mvc.perform(post("/inputs/json")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.state").value("MISSING"));

        mvc.perform(post("/inputs/json")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"nickname\":null}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.state").value("NULL"));

        mvc.perform(post("/inputs/json")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"nickname\":\"\"}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.state").value("EMPTY"));

        mvc.perform(post("/inputs/json")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"nickname\":\" \"}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.state").value("BLANK"));
    }

    @Test
    void validatesProfileOnCreate() throws Exception {
        mvc.perform(post("/inputs/profiles")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"nickname\":\" \",\"age\":18}"))
                .andExpect(status().isBadRequest());

        mvc.perform(post("/inputs/profiles")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"nickname\":\"Lan\",\"age\":18}"))
                .andExpect(status().isCreated());
    }

    @Test
    void optionalBodyAllowsNoBody() throws Exception {
        mvc.perform(post("/inputs/optional-body")
                .contentType(MediaType.APPLICATION_JSON))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.state")
                        .value("NO_BODY_OR_JSON_NULL"));
    }
}
```

Use `./mvnw test` or on Windows `.\mvnw.cmd test`. This is a **runnable test suite in a Boot project with full dependencies**, not a result already executed in every environment. If custom security or Jackson customization is present, configure MockMvc accordingly. Tests intentionally assert the `state` field rather than assuming JSON key ordering or a fixed Spring Boot error body.

## 10. Other controller input types

### `@RequestHeader` and `@CookieValue`

`@RequestHeader("X-Trace-Id")` is required by default. Use `@RequestHeader(name = "X-Trace-Id", required = false) String traceId` to allow absence; `Optional<String>` is also supported. An absent header and a header present with an empty value are conceptually two different cases, though proxies, browsers, and HTTP libraries may normalize, strip, or reject empty headers. If `defaultValue` is used, this annotation type can merge missing with empty similarly to request parameters.

`@CookieValue` has related `required`/default/`Optional` mechanics; an absent cookie is not equivalent to a cookie with empty content. Pay attention to decoding, validation, and default values per cookie conventions.

### `@PathVariable`

`@PathVariable("id") Long id` is tied to a **matched URL pattern**, e.g., `/items/{id}`. The URL `/items` does not pass `id=null` to a mapping that only accepts `/items/{id}`; typically it is an **unmatched path (404)** rather than a method invocation with a missing ID. To support both URL forms, declare the corresponding mappings explicitly and consider `required=false`/`Optional`.

The value `/items/abc` with `Long id` can lead to 400 due to type conversion failure, whereas `/items/` may fail to match the path pattern. These are different errors: **no matching route** versus **matching route with unconvertible input**.

### `@ModelAttribute` and form data

An `@ModelAttribute` object can receive data from forms/queries through data binding. Unsent fields may remain `null` or keep their initialized values; fields sent empty are typically `""` for `String` (unless a custom binder applies), while numeric fields may become null or cause conversion errors. When you need to track which fields were actually present in the form, inspect request parameters or design the DTO to record presence. Use `@Valid` and `BindingResult` when binding/validation errors need to be handled inside the method.

In Spring MVC, `application/x-www-form-urlencoded` form data typically uses `@RequestParam`/`@ModelAttribute`. Do not expect `@RequestBody` to read form data via the Servlet API the same way it reads JSON in all environments.

### Multipart file

`@RequestParam(name="file", required=false) MultipartFile file`: if no part is sent, it usually receives `null`; if a part containing a 0-byte file is sent, you may receive a `MultipartFile` object with `file.isEmpty() == true`. `MultipartFile.isEmpty()` can also be true when no file was selected in a form; therefore, when business logic needs to distinguish "no upload" from "0-byte file upload", examine **part presence**, `getSize()`, filename, and actual HTTP/form rules rather than calling `isEmpty()` alone. Real uploads also require size limits and file-type verification.

## 11. Applying to CREATE, UPDATE, and PATCH

A partial update contract often uses three states:

| JSON request field | Example intent when PATCHing a profile |
| --- | --- |
| No `nickname` | **Keep** the currently stored nickname |
| Has `"nickname":null` | **Clear** the nickname, if business rules allow nullability |
| Has `"nickname":""` | **Set to empty string** or return a validation error, per API rules |
| Has `"nickname":"Lan"` | **Change** nickname to `Lan` |

If you deserialize directly into `record PatchProfile(String nickname)`, both missing and explicit null can yield Java `null`. Code like `if (nickname == null) skip` cannot fulfill "explicit null means clear".

Suitable solutions depend on the project:

- **Simple, few fields:** accept `JsonNode` and inspect `has`/`isNull`/`isTextual`, then convert into a validated command/DTO.
- **Typed DTOs with many fields:** use Jackson setters/presence flags or a three-state wrapper (`ABSENT`/`EXPLICIT_NULL`/`VALUE`) with tested converters.
- **Standards-based updates:** use JSON Merge Patch (RFC 7396) or JSON Patch (RFC 6902), declaring their dedicated `Content-Type` and semantics. Under JSON Merge Patch, `null` in a patch **removes the member**; read the specification carefully before choosing.
- **Full PUT:** contracts typically require a complete representation; missing/null field rules should be explicitly specified and validated against resource requirements—avoid applying PATCH semantics to PUT unintentionally.

Validation for CREATE can be stricter than PATCH. For example, `@NotBlank` fits a required nickname on creation; PATCH must allow **absence** to leave it untouched, while still validating constraints whenever the field is present (unless explicit null is permitted to clear it). Avoid reusing the exact same DTO/constraints indiscriminately for both operations.

## 12. Checklist for diagnosing input data bugs

1. **Record the exact request**: method, encoded URL, `Content-Type`, raw body, repeated parameter names. Do not infer what the client sent solely from the post-binding Java object.
2. **Identify the source**: query/form uses `@RequestParam`; JSON body uses `@RequestBody`; path uses `@PathVariable`; header uses `@RequestHeader`. Absence behaves differently for each source.
3. **Separate two steps**: "parameter/field present in request" versus "value remaining after conversion/deserialization". Once an empty string converts to null, that information is gone.
4. **Check defaults and binders**: `defaultValue` merges missing/empty; `StringTrimmerEditor` or `@InitBinder` can turn `""` or whitespace strings into null; custom Jackson coercion can alter JSON values.
5. **Inspect status 400 and specific exceptions**: `MissingServletRequestParameterException` usually means a missing required param; conversion errors may be `MethodArgumentTypeMismatchException`; JSON parse errors usually involve `HttpMessageNotReadableException`; DTO validation errors are usually `MethodArgumentNotValidException`. Custom handlers can change body/status.
6. **Do not overuse primitives**: `int age` cannot represent null; use `Integer` + `@NotNull` when a required check is genuinely needed, while noting Jackson coercion.
7. **Do not treat Optional as a validator**: `Optional` represents presence after binding; you still must validate the inner value.
8. **Do not treat empty as null by default**: `""`, whitespace strings, `[]`, `{}`, `null`, and absent fields are distinct cases. Normalize only when the business contract permits.
9. **Do not put null values into `Map.of`**: Java's `Map.of` rejects null keys/values; if a response needs null fields, use a DTO/record (as in the demo) or `LinkedHashMap`/`HashMap` which allows nulls.
10. **Test against an explicit matrix**: at minimum missing, empty, blank, null (for JSON), valid, malformed, and multi-value (if query keys can repeat). Verify both returned status and business side effects.

## 13. Self-check questions

**Question 1.** What does `@RequestParam(required=false) String q` receive when `q` is absent and when `?q=` is sent?

**Answer:** With the default binder: `null` when missing; `""` when the parameter is present with no characters.

**Question 2.** Does `@RequestParam(defaultValue="all")` preserve the difference between missing and empty string?

**Answer:** No. Both typically receive `"all"`.

**Question 3.** Does `Optional<Integer> count` turn `?count=abc` into `Optional.empty()`?

**Answer:** No. Non-numeric strings typically cause an HTTP 400 conversion error; `Optional` only represents absence of a valid value after binding.

**Question 4.** Does `record Patch(String name)` distinguish JSON `{}` from `{"name":null}`?

**Answer:** Under standard deserialization, no: `name` is null in both. Use `JsonNode` or a field-presence tracking mechanism.

**Question 5.** Does `@NotNull String name` reject `""` or `"   "`?

**Answer:** No. Use `@NotBlank` if you want to reject null, empty, and whitespace-only strings.

**Question 6.** If a mapping `/items/{id}` has no `/items` route, does `@PathVariable(required=false)` guarantee `GET /items` invokes the method?

**Answer:** No. The URL must match a mapping before method parameters are resolved; declare a separate `/items` route or a mapping supporting both.

## References

- Spring Framework — `@RequestParam`: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/requestparam.html
- Spring Framework — Controller Method Arguments and `Optional`: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/arguments.html
- Spring Framework — Type Conversion (empty String → null after conversion): https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/typeconversion.html
- Spring Framework — `@RequestBody` and Validation: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/requestbody.html
- Spring Framework — `@ModelAttribute`: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/modelattrib-method-args.html
- Spring Framework — `@RequestHeader`: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/requestheader.html
- Jackson Databind `JsonNode` API: https://javadoc.io/doc/com.fasterxml.jackson.core/jackson-databind/latest/com/fasterxml/jackson/databind/JsonNode.html
- Jakarta Bean Validation `@NotNull`, `@NotBlank`, `@NotEmpty`: https://jakarta.ee/specifications/bean-validation/
- JSON Merge Patch (RFC 7396): https://www.rfc-editor.org/rfc/rfc7396
