# Mapping Conditions by HTTP Method, params, headers, consumes, and produces in Spring MVC

## 1. Goal: A Path Alone Is Not Enough to Identify a Controller Method

In Spring Web MVC, `@RequestMapping` and shorthand annotations like `@GetMapping` and `@PostMapping` do not select endpoints by URI alone. Spring can **simultaneously** require the right HTTP method, request parameters, headers, request content type (`consumes`), and client-accepted response content type (`produces`).

Suppose the application receives:

~~~http
POST /api/items?source=mobile HTTP/1.1
Host: localhost:8080
Content-Type: application/json
Accept: application/json
X-Client: mobile

{"name":"Notebook"}
~~~

Each part carries a distinct meaning:

- `POST`: **HTTP method**; describes the operation the client wants to perform.
- `/api/items`: **path** of the resource/endpoint.
- `source=mobile`: **request parameter** used to filter mappings via `params` if the endpoint contract requires it.
- `X-Client: mobile`: **header** used to filter mappings via `headers` if declared.
- `Content-Type: application/json`: representation type **sent by the client**; relates to `consumes`.
- `Accept: application/json`: representation type **the client wants the server to return**; relates to `produces`.
- JSON body: actual payload read by `@RequestBody`/message converters **after** a matching handler is selected. Body content is **not** a `params` condition and is not matched property-by-property by `consumes`.

**Lesson goal:** look at an HTTP request and predict which controller method will be selected, explain why a request is rejected (e.g., 405/415/406/400), and write clear mappings without duplicates or confusion. This lesson focuses on **Spring MVC annotated controllers**, without switching to details of building Spring WebFlux routers.

## 2. Overview Table of the Five Condition Groups

| Annotation attribute | Read from request | Example | Meaning |
| --- | --- | --- | --- |
| `method` / `@GetMapping` ... | HTTP method | `GET`, `POST` | Kind of HTTP operation allowed into the endpoint |
| `params` | Request parameters (typically query or form data) | `mode=full`, `debug`, `!debug` | Match mapping only when parameter condition holds |
| `headers` | HTTP headers | `X-Client=mobile`, `X-Tenant` | Match mapping only when header condition holds |
| `consumes` | Request `Content-Type` | `application/json` | Does the endpoint accept the incoming body's media type? |
| `produces` | Request `Accept` | `application/json`, `text/plain` | Can the endpoint produce a representation the client accepts? |

Example of a mapping with multiple conditions:

~~~java
@PostMapping(
    path = "/items",
    params = "source=mobile",
    headers = "X-Client=mobile",
    consumes = MediaType.APPLICATION_JSON_VALUE,
    produces = MediaType.APPLICATION_JSON_VALUE
)
public Item create(@RequestBody CreateItemRequest input) {
    // ... processing ...
}
~~~

This illustrative snippet requires `Item`, `CreateItemRequest`, an enclosing controller, and imports; a **complete standalone runnable** example is in section 9.

A request must satisfy **all declared condition groups**. If `POST`, URI, and `Content-Type` match, yet `source=mobile` is missing, this mapping still does not match. Spring may match another mapping, or return an error if no valid option exists.

### Distinguishing AND vs OR

- **Different condition groups** on the same mapping combine with **AND** semantics.
- An array `params = {"a=1","b=2"}` requires **both** conditions.
- An array `headers = {"X-Client=mobile","X-Feature"}` also requires **both**.
- Multiple media types in `consumes = {"application/json","text/plain"}` are **alternatives** within the same group (OR). `produces` behaves similarly.
- Multiple HTTP methods in `@RequestMapping(method = {GET, POST})` are **alternatives**. However, writing two dedicated methods is usually more readable and cleaner in HTTP semantics.
- Multiple paths in a mapping array are also URI alternatives; it does not mean all paths must match simultaneously.

Spring represents the condition set as a `RequestMappingInfo`, then uses the corresponding `RequestCondition` instances to evaluate requests and compare specificity.

## 3. Selecting by HTTP Method: GET, POST, PUT, PATCH, and DELETE

You can declare generically:

~~~java
@RequestMapping(path = "/items", method = RequestMethod.GET)
public List<Item> list() { ... }
~~~

Or use shorthand annotations that make intent clearer:

~~~java
@GetMapping("/items")
public List<Item> list() { ... }

@PostMapping("/items")
public Item create(@RequestBody CreateItemRequest input) { ... }
~~~

The two snippets above **only illustrate syntax**; method bodies and supporting classes are omitted. They cannot coexist with another identical `@GetMapping("/items")` without distinguishing conditions.

| Annotation | Equivalent mapping method | Typical HTTP semantics |
| --- | --- | --- |
| `@GetMapping` | `RequestMethod.GET` | Retrieve a representation; safe and idempotent per HTTP |
| `@PostMapping` | `RequestMethod.POST` | Submit data for processing/creating a resource; not idempotent by default |
| `@PutMapping` | `RequestMethod.PUT` | Create/replace target state per contract; idempotent |
| `@PatchMapping` | `RequestMethod.PATCH` | Partial update; not idempotent by default |
| `@DeleteMapping` | `RequestMethod.DELETE` | Request deletion; idempotent in intended effect |

**Easy-to-miss detail:** `@RequestMapping("/items")` at the **method level** **without `method`** does not restrict HTTP methods by default. Do not use it in place of `@GetMapping` if the endpoint should only allow reads.

### When the Method Is Invalid: 405

For example, only `@GetMapping("/api/items/7")` exists, yet the client sends `POST /api/items/7`. When the path matches but the HTTP method is unsupported, Spring MVC typically responds with **405 Method Not Allowed** and may include an `Allow` header. This differs from **404 Not Found**, where no path mapping matches.

**HEAD and OPTIONS:** `@GetMapping` supports HEAD via MVC/Servlet mechanisms in standard setups, without writing a separate method just to drop the body. Spring MVC also provides default OPTIONS handling based on mapped HTTP methods. Therefore, do not claim that `@GetMapping` can never accept HEAD regardless of framework support.

## 4. The `params` Condition: Presence, Absence, or Specific Values

`params` inspects **request parameters** to filter mappings. For example:

~~~java
@GetMapping(path = "/search", params = "mode=summary")
public String summary() { return "summary"; }

@GetMapping(path = "/search", params = "mode=full")
public String full() { return "full"; }
~~~

When sending:

~~~http
GET /search?mode=full HTTP/1.1
Host: localhost:8080
~~~

only the `full()` method matches the condition in the example.

Common expressions:

| Expression | Meaning | Example matching request |
| --- | --- | --- |
| `params = "mode"` | Parameter named `mode` is present | `?mode=full` or `?mode=` |
| `params = "!mode"` | Parameter `mode` is absent | `/search` |
| `params = "mode=full"` | Value equals `full` | `?mode=full` |
| `params = "mode!=full"` | Parameter is absent or value differs from `full` per Spring's condition semantics | `/search?mode=summary` |
| `params = {"mode=full", "page=1"}` | Both hold | `?mode=full&page=1` |

If you only want to forbid a parameter, use `!mode`; if you want to require the parameter to exist, use `mode`. Do not use `mode!=full` expecting it to require the parameter to exist with a value other than `full`: a negation expression may also match when the parameter is absent.

### How `params` Differs from `@RequestParam`

~~~java
@GetMapping(path = "/reports", params = "format=csv")
public String report(@RequestParam(defaultValue = "1") int page) {
    return "page=" + page;
}
~~~

- `params="format=csv"`: **condition for selecting the controller method**; if the request lacks `format=csv`, this method is not a candidate.
- `@RequestParam int page`: **resolves an argument for the already-selected method**; here `page` defaults to 1 if omitted by the client.
- You can use `@RequestParam("format") String format` to read the parameter value into the method body, but that does not automatically turn it into a mapping selection condition like `params="format=csv"`.

`params` evaluates request parameters, including those exposed by the Servlet API from URL-encoded forms depending on the request. JSON data inside `@RequestBody` does **not** become request parameters just because properties share names.

### Which Status Is Returned When a `params` Condition Fails?

If path and HTTP method match a mapping yet all candidates are eliminated **solely due to `params` conditions**, Spring MVC typically returns **400 Bad Request** via unsatisfied parameter reporting. Still, verify accurately with `MockMvc` or integration tests because custom exception handlers and other conditions can alter the status.

## 5. The `headers` Condition: Routing by HTTP Metadata

`headers` uses expressions similar to `params`, but checks HTTP headers.

~~~java
@GetMapping(path = "/clients", headers = "X-Client=mobile")
public String mobile() { return "mobile"; }

@GetMapping(path = "/clients", headers = "X-Client=web")
public String web() { return "web"; }
~~~

Request:

~~~http
GET /clients HTTP/1.1
Host: localhost:8080
X-Client: mobile
~~~

matches the `mobile()` method. Conditions can be written as:

- `headers = "X-Client"`: header named `X-Client` is present.
- `headers = "!X-Client"`: header is absent.
- `headers = "X-Client=mobile"`: header has the expected value.
- `headers = "X-Client!=mobile"`: value negation.
- `headers = {"X-Client=mobile", "X-Feature"}`: both conditions must hold.

HTTP header names are **case-insensitive**; header values depend on header semantics and how the matcher processes them. Therefore, do not mistake `X-Client` and `x-client` for two different headers.

**Do not use `headers` as a substitute for `consumes`/`produces`.** Spring may support expressions referencing `Content-Type`/`Accept` in `headers`, but those fields have media-type syntax, wildcards, and quality negotiation; using `consumes`/`produces` expresses intent properly and uses specialized matching logic.

### Header Matching Does Not Prove Access Rights

A client sending `X-Client: mobile` can spoof that value. Mapping conditions do not replace authentication, authorization, signature verification, or tenant isolation. If a header selects a privileged processing path, enforce security at the appropriate layer rather than trusting a client-supplied string.

## 6. `consumes`: Which `Content-Type` Does the Server Accept?

`consumes` is a condition on the **media type a handler can consume from the request body**, typically based on the request `Content-Type`.

~~~java
@PostMapping(
    path = "/items",
    consumes = MediaType.APPLICATION_JSON_VALUE
)
public void create(@RequestBody ItemInput input) {
    // ...
}
~~~

Matching request:

~~~http
POST /items HTTP/1.1
Host: localhost:8080
Content-Type: application/json

{"name":"Pen"}
~~~

A request that fails the condition above when sending:

~~~http
POST /items HTTP/1.1
Host: localhost:8080
Content-Type: text/plain

Pen
~~~

If path and method match yet the request media type is rejected by the mapping, Spring MVC typically responds with **415 Unsupported Media Type**. After mapping selection, the framework still needs a compatible `HttpMessageConverter` to read the body into a Java type; satisfying `consumes` **does not guarantee** deserialization succeeds.

### Media Types and Wildcards

`consumes` can use:

~~~java
consumes = "application/json"
consumes = {"application/json", "application/xml"}
consumes = "application/*"
consumes = "!text/plain"
~~~

- A list of media types specifies allowed alternatives; it does not require the body to be both JSON and XML.
- Wildcard media types should only be used when converters and data contracts genuinely support them.
- Negation excludes a media type, but **does not automatically grant** the ability to read all other media types.
- `application/json;charset=UTF-8` can be compatible with `application/json` under media-type rules; do not reimplement this logic with raw string comparisons.
- When a request has no body or omits Content-Type, matching behavior depends on context; do not assume `consumes="application/json"` behaves identically for a bodyless GET and a POST with a body. Typically only use `consumes` when the endpoint genuinely requires a request representation.

### Mapping Match Differs from Ability to Read Data

Even when `Content-Type: application/json` matches, malformed JSON such as `{"name":` can still produce **400 Bad Request** from `HttpMessageNotReadableException`. That is a **body-reading error**, distinct from **415** for an unsupported media type.

If an endpoint only accepts JSON, declare `consumes = MediaType.APPLICATION_JSON_VALUE` and an explicit `@RequestBody` type. Do not manually parse JSON from arbitrary strings when the framework already provides standard converters.

## 7. `produces`: Which Response Format Does the Client Accept?

`produces` is a condition on the **media type a handler can return**, typically selected based on the client's `Accept` header.

~~~java
@GetMapping(
    path = "/items/{id}",
    produces = MediaType.APPLICATION_JSON_VALUE
)
public Item get(@PathVariable long id) {
    return new Item(id, "Pen");
}
~~~

The client may send:

~~~http
GET /items/7 HTTP/1.1
Host: localhost:8080
Accept: application/json
~~~

The JSON mapping matches. If the client sends:

~~~http
GET /items/7 HTTP/1.1
Host: localhost:8080
Accept: application/pdf
~~~

and no mapping/converter can produce a matching representation, Spring MVC typically responds with **406 Not Acceptable**. This differs from **415**, because 406 concerns the **desired response**, whereas 415 concerns the **incoming request body**.

### `Accept` and `Content-Type` Sit on Opposite Sides

| Header | Who sends it? | What is it used for? | Mapping attribute |
| --- | --- | --- | --- |
| Request `Content-Type` | Client | Declares the format of the body **sent to the server** | `consumes` |
| Request `Accept` | Client | Declares response formats **the client accepts** | `produces` |
| Response `Content-Type` | Server | Declares the format of the body **the server returned** | Outcome of content negotiation/serialization |

In a normal JSON response, the server sets `Content-Type: application/json`. Do not treat **response Content-Type** as an input condition for selecting a method because it does not exist at routing time.

### Quality Factors and Wildcards

Header:

~~~http
Accept: application/json;q=0.9, text/plain;q=0.5
~~~

can express media-type preference weights; `q` is the quality value. `Accept: */*` allows multiple formats to match, so if multiple mappings share path and method and differ **only by `produces`**, test selection/tie-breaking for broad Accept headers. For production APIs, prevent ambiguity through explicit Accept contracts, specific mappings, and tests.

Even when a mapping selects `produces="application/xml"`, the server still needs a converter to encode objects into XML. `produces` does not automatically install JAXB/Jackson XML; do not promise XML output solely via annotations when converters are missing.

## 8. How Spring Selects a Mapping When Multiple Candidates Share a Path

Conceptually, in Spring MVC:

~~~text
HTTP request
    |
    v
DispatcherServlet
    |
    v
RequestMappingHandlerMapping
    |
    +-- match path pattern?
    +-- match HTTP method?
    +-- match request params?
    +-- match request headers?
    +-- match consumes / Content-Type?
    +-- match produces / Accept?
    |
    +-- No candidates => handle mismatch / return appropriate HTTP error
    |
    +-- One candidate => return HandlerMethod
    |
    +-- Multiple candidates => compare specificity / RequestMappingInfo
    |                          if indistinguishable => ambiguity
    v
RequestMappingHandlerAdapter
    |
    +-- resolve arguments, invoke controller, handle return value
    v
HTTP response
~~~

This is a simplified educational diagram, not a specification of internal optimization check ordering in any particular source version. What matters is that **all declared conditions must be satisfied** and competing mappings are compared by specificity, rather than arbitrarily picking whichever method was declared first.

### Startup Conflicts vs Request-Time Ambiguity

Two mappings with completely equivalent configurations can trigger an **ambiguous mapping** registration error on application startup:

~~~java
@GetMapping("/same")
public String first() { return "A"; }

@GetMapping("/same")
public String second() { return "B"; }
~~~

This example is **invalid to run concurrently** in the same controller/application because path, method, and mapping conditions are identical. You cannot fix it by renaming Java methods: mapping evaluates request conditions, not method names.

Two mappings whose conditions are not completely identical might both become candidates for a specific request; Spring compares their priority. If they cannot be distinguished clearly enough, runtime ambiguity can occur. Make conditions mutually exclusive or differentiate paths/HTTP methods clearly, and write tests for overlapping requests.

### Class-Level and Method-Level Conditions

~~~java
@RestController
@RequestMapping(path = "/api")
class ExampleController {

    @GetMapping(path = "/items", produces = "application/json")
    List<Item> items() { ... }
}
~~~

The resulting path is `/api/items`. Class-level `@RequestMapping` is commonly used for base paths, and method-level shortcuts for exact methods/paths. For `consumes` and `produces`, a method-level declaration **overrides** the corresponding class-level condition instead of simply appending to a class-level list; do not assume they always accumulate. For other conditions, consult the Spring API and test combined mappings instead of guessing.

Do not stack two different mapping annotations on the same method, such as `@GetMapping` and `@PostMapping` together, hoping they combine as OR: Spring warns and only uses the first discovered mapping. If a single method truly needs multiple HTTP methods, use one `@RequestMapping(method = {RequestMethod.GET, RequestMethod.POST})` and handle business logic carefully.

## 9. Complete Spring Boot MVC Example Covering All Five Condition Groups

The following example is standalone, using Java 17+ and Spring Boot 3.3.5 (Spring Framework 6.1.x) for stable illustrative APIs. One controller holds endpoints with independent conditions, avoiding mapping conflicts. There is no database or library outside the Web starter.

### 9.1 Structure and Gradle

~~~text
mapping-conditions-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/example/mapping/MappingConditionsApplication.java
~~~

`settings.gradle`:

~~~groovy
rootProject.name = 'mapping-conditions-demo'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'example'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
}
~~~

Use JDK 17+ and a Gradle version compatible with the Spring Boot plugin. If the project includes a Gradle Wrapper, run the wrapper; otherwise, you need Gradle installed to run `gradle bootRun` or generate the wrapper. WebFlux is not required to implement these mappings.

### 9.2 Java Source

Create `src/main/java/example/mapping/MappingConditionsApplication.java`:

~~~java
package example.mapping;

import java.util.Map;

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
public class MappingConditionsApplication {

    public static void main(String[] args) {
        SpringApplication.run(MappingConditionsApplication.class, args);
    }

    public record Item(long id, String name) {}
    public record NewItem(String name) {}

    @RestController
    @RequestMapping("/api")
    static class DemoController {

        // HTTP method + path + JSON output.
        @GetMapping(
                path = "/items/{id}",
                produces = MediaType.APPLICATION_JSON_VALUE)
        public Item byId(@PathVariable long id) {
            return new Item(id, "Pen");
        }

        // Two GETs on the same path, only the matching mode is selected.
        @GetMapping(
                path = "/find",
                params = "mode=summary",
                produces = MediaType.TEXT_PLAIN_VALUE)
        public String summary() {
            return "summary";
        }

        @GetMapping(
                path = "/find",
                params = "mode=full",
                produces = MediaType.TEXT_PLAIN_VALUE)
        public String full() {
            return "full";
        }

        // Distinguish present vs absent parameter.
        @GetMapping(
                path = "/flag",
                params = "debug",
                produces = MediaType.TEXT_PLAIN_VALUE)
        public String debugOn() {
            return "debug:on";
        }

        @GetMapping(
                path = "/flag",
                params = "!debug",
                produces = MediaType.TEXT_PLAIN_VALUE)
        public String debugOff() {
            return "debug:off";
        }

        // Two GETs on the same path, requiring different headers.
        @GetMapping(
                path = "/clients",
                headers = "X-Client=mobile",
                produces = MediaType.TEXT_PLAIN_VALUE)
        public String mobile() {
            return "client:mobile";
        }

        @GetMapping(
                path = "/clients",
                headers = "X-Client=web",
                produces = MediaType.TEXT_PLAIN_VALUE)
        public String web() {
            return "client:web";
        }

        // Same POST /items, consuming and producing different media types.
        @PostMapping(
                path = "/items",
                consumes = MediaType.APPLICATION_JSON_VALUE,
                produces = MediaType.APPLICATION_JSON_VALUE)
        public ResponseEntity<Item> createJson(@RequestBody NewItem input) {
            return ResponseEntity.status(HttpStatus.CREATED)
                    .body(new Item(101L, input.name()));
        }

        @PostMapping(
                path = "/items",
                consumes = MediaType.TEXT_PLAIN_VALUE,
                produces = MediaType.TEXT_PLAIN_VALUE)
        public ResponseEntity<String> createText(@RequestBody String input) {
            return ResponseEntity.status(HttpStatus.CREATED)
                    .body("created: " + input);
        }

        // Same GET /format, distinguished by Accept header.
        @GetMapping(
                path = "/format",
                produces = MediaType.APPLICATION_JSON_VALUE)
        public Map<String, String> json() {
            return Map.of("view", "json");
        }

        @GetMapping(
                path = "/format",
                produces = MediaType.TEXT_PLAIN_VALUE)
        public String plain() {
            return "view:text";
        }
    }
}
~~~

The example demonstrates all five main condition types: HTTP method (`GET`/`POST`), `params`, `headers`, `consumes`, and `produces`. With `@RestController`, `String` is written to the response body rather than interpreted as an HTML view name.

**Note on `@PathVariable`:** The Spring Boot Gradle plugin supplies suitable compiler metadata in standard setups. If a custom build setup does not preserve parameter names for reflection, explicitly write `@PathVariable("id")` and other parameter annotations to avoid relying on the `-parameters` compiler flag.

### 9.3 Run the App and Test

With the wrapper present:

~~~bash
./gradlew bootRun
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat bootRun
~~~

Without a wrapper, use `gradle bootRun` after installing a compatible Gradle version. The example assumes default port `8080` and no other application occupying it.

**A. GET JSON by method, path, and produces:**

~~~bash
curl -i -H "Accept: application/json" http://localhost:8080/api/items/7
~~~

Expected response: `200 OK`, JSON `Content-Type`, body:

~~~json
{"id":7,"name":"Pen"}
~~~

**B. `params` selecting summary or full:**

~~~bash
curl -i "http://localhost:8080/api/find?mode=summary"
curl -i "http://localhost:8080/api/find?mode=full"
~~~

The two bodies respectively:

~~~text
summary
full
~~~

If calling `/api/find?mode=other` or omitting `mode`, neither method matches the value condition. In standard configuration, cases failing only `params` usually return 400; real tests should account for custom exception handlers if present.

**C. `params` present and absent:**

~~~bash
curl -i "http://localhost:8080/api/flag?debug"
curl -i "http://localhost:8080/api/flag"
~~~

Bodies:

~~~text
debug:on
debug:off
~~~

The condition `params="debug"` only requires presence; it does not mean `debug=true`. `?debug=false` still has a parameter named `debug` and matches `debugOn` in the demo.

**D. `headers` selecting client:**

~~~bash
curl -i -H "X-Client: mobile" http://localhost:8080/api/clients
curl -i -H "X-Client: web" http://localhost:8080/api/clients
~~~

Bodies respectively:

~~~text
client:mobile
client:web
~~~

Omitting the header or sending `X-Client: other` satisfies neither mapping; do not assume a fixed status if the app adds other mappings or header rules.

**E. POST on the same URI, different Content-Type and Accept:**

~~~bash
curl -i -X POST "http://localhost:8080/api/items" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json" \
  -d '{"name":"Notebook"}'
~~~

Expected status: `201 Created`; body:

~~~json
{"id":101,"name":"Notebook"}
~~~

Switch to plain text:

~~~bash
curl -i -X POST "http://localhost:8080/api/items" \
  -H "Content-Type: text/plain" \
  -H "Accept: text/plain" \
  --data-binary "Pencil"
~~~

Expected status: `201 Created`; body:

~~~text
created: Pencil
~~~

The difference comes from **two `consumes` mappings**, each accepting only its matching request type; meanwhile each mapping's `produces` selects the response type.

**F. `produces` selecting format by Accept:**

~~~bash
curl -i -H "Accept: application/json" http://localhost:8080/api/format
curl -i -H "Accept: text/plain" http://localhost:8080/api/format
~~~

Corresponding bodies:

~~~json
{"view":"json"}
~~~

~~~text
view:text
~~~

These are two methods sharing GET/path whose media types are distinguished when the client sends a specific `Accept` header. Do not use the result of a request without `Accept` to claim the framework always prefers one method.

**G. Wrong Content-Type, Accept, or HTTP method:**

~~~bash
curl -i -X POST "http://localhost:8080/api/items" \
  -H "Content-Type: application/xml" \
  -H "Accept: application/json" \
  -d '<item><name>Notebook</name></item>'

curl -i -H "Accept: application/pdf" http://localhost:8080/api/format

curl -i -X DELETE http://localhost:8080/api/items/7
~~~

In the demo project without customized error handling, the expected statuses respectively are **415 Unsupported Media Type**, **406 Not Acceptable**, and **405 Method Not Allowed**. Exact error bodies and header lists may vary by Spring Boot configuration. These commands are HTTP test examples, not stdout from the Java program.

### 9.4 Short Demo Test Case Table

| Request | Expected mapping | Result |
| --- | --- | --- |
| `GET /api/items/7` + `Accept: application/json` | `byId` | JSON `{"id":7,"name":"Pen"}` |
| `GET /api/find?mode=full` | `full` | `full` |
| `GET /api/find?mode=summary` | `summary` | `summary` |
| `GET /api/flag` | `debugOff` | `debug:off` |
| `GET /api/flag?debug` | `debugOn` | `debug:on` |
| `GET /api/clients` + `X-Client: mobile` | `mobile` | `client:mobile` |
| `POST /api/items` + JSON Content-Type/Accept | `createJson` | 201 + JSON |
| `POST /api/items` + text/plain Content-Type/Accept | `createText` | 201 + text |
| `GET /api/format` + `Accept: text/plain` | `plain` | `view:text` |
| `GET /api/format` + `Accept: application/json` | `json` | JSON |
| `GET /api/format` + `Accept: application/pdf` | No matching produces | 406 typical |
| `POST /api/items` + `Content-Type: application/xml` | No matching consumes | 415 typical |
| `DELETE /api/items/7` | No DELETE mapping on path | 405 typical |

## 10. Common Routing Errors and How to Diagnose Them

| HTTP status / symptom | First diagnosis | Resolution direction |
| --- | --- | --- |
| **404 Not Found** | No matching path/handler; possibly due to context path/servlet mapping | Check actual URL, controller registration, logs/mappings |
| **405 Method Not Allowed** | Path has a mapping, but not for the request's HTTP method | Compare `GET/POST/PUT/PATCH/DELETE` and `Allow` |
| **400 Bad Request** when `params` fails | Path/method matched, yet required parameter condition is missing/wrong | Compare query/form parameters against `params` |
| **400 Bad Request** after handler selection | Wrong parameter type, malformed JSON, validation failure | Check `@RequestParam`, `@PathVariable`, `@RequestBody`, converter/validator |
| **415 Unsupported Media Type** | Request Content-Type does not match consumes/converter | Verify exact request `Content-Type` and codec |
| **406 Not Acceptable** | `Accept` does not match produces/cannot build representation | Check `Accept`, `produces`, body-writing converters |
| **500/ambiguous mapping** at startup | Identical registration conditions across multiple methods | Change mappings to differentiate, not just Java method names |
| **Ambiguous handler methods** at request time | Multiple equally prioritized candidates for a specific request | Design mutually exclusive conditions, add overlapping test cases |
| Right controller method entered, wrong body | Mapping succeeded; possible return-value handler/serialization bug | Check `@RestController`, `ResponseEntity`, converters |
| Header present yet still fails to match | Wrong value, whitespace, proxy stripping header, gateway policy | Log headers safely, trace across proxy |

**Do not use HTTP status as sole evidence:** `@ControllerAdvice`, filters/security, reverse proxies, or custom handler mappings can alter responses. Identify the actual request received after proxies and the actual mapping registry.

### Useful Logs for Debugging

In development, you can enable mapping logs at an appropriate level in `application.properties`:

~~~properties
logging.level.org.springframework.web.servlet.mvc.method.annotation.RequestMappingHandlerMapping=TRACE
logging.level.org.springframework.web.servlet.DispatcherServlet=DEBUG
~~~

Enable detailed tracing only when needed; do not leave it enabled permanently in production due to log volume, performance impact, and risk of logging sensitive data. With Spring Boot Actuator, the `/actuator/mappings` endpoint can show registered mappings **when Actuator is installed and configured**, though it is not exposed by default in the demo app.

## 11. Separating Mapping Conditions from Argument Resolution

Look at these two methods:

~~~java
@GetMapping(path = "/orders", params = "status=PAID")
public String paidOrders(@RequestParam String status) { ... }

@GetMapping(path = "/orders", params = "status=PENDING")
public String pendingOrders(@RequestParam String status) { ... }
~~~

`params="status=PAID"`/`"status=PENDING"` determines **which method is selected**. Afterward, `@RequestParam String status` supplies the argument to the chosen method.

Important comparisons:

- `@RequestMapping.params` is not `@RequestParam`.
- `@RequestMapping.headers` is not `@RequestHeader`.
- `@RequestMapping.consumes` is not `@RequestBody`.
- `@RequestMapping.produces` is not `@ResponseBody`.
- `consumes`/`produces` affect **mapping candidates**; `HttpMessageConverter` and return-value handlers govern actual Java body ↔ bytes conversion.
- `headers = "X-Client=mobile"` only filters requests; to read the header value inside the method, you still need `@RequestHeader("X-Client")` or to read the request context.

**Important example:** A POST mapping with `consumes="application/json"` where the method accepts `@RequestBody String` can still work depending on available converters; conversely `@RequestBody MyDto` requires a suitable converter. Do not infer the Java target type solely from `consumes`.

## 12. Misconceptions That Break API Contracts

| Misconception | Correct understanding |
| --- | --- |
| "Only one controller method can share a path" | Multiple mappings can share a path when distinguished by HTTP method/params/headers/media conditions |
| "`@RequestMapping` defaults to GET" | Method-level without `method` declared can match multiple HTTP methods |
| "`params` reads from the JSON body" | Evaluates request parameters, not individual JSON properties |
| "`@RequestParam` branches mapping automatically" | Argument resolvers run after handler selection |
| "`headers` authenticates users automatically" | Client-sent headers can be spoofed; authentication/authorization belong in another layer |
| "`consumes` reads Accept" | `consumes` relies on request Content-Type |
| "`produces` reads request Content-Type" | `produces` relies on request Accept/response representation |
| "Matching consumes guarantees body parsing succeeds" | Converters may still be missing or data malformed |
| "Declaring produces XML guarantees XML output" | An XML message converter supporting the Java type is required |
| "Every media type in the array must match at once" | Within consumes/produces, media alternatives are OR |
| "A params array only needs one expression to pass" | Expressions in a params array are AND |
| "Duplicate mappings pick the first method written" | Can trigger ambiguous mapping errors; fix the conditions |
| "`Accept: */*` always picks JSON" | Depends on candidates and content negotiation; test explicit contracts |
| "415 and 406 are the same" | 415 is about request media; 406 is about response acceptable media |
| "GET mappings never handle HEAD" | Spring MVC supports HEAD for GET mappings in standard configuration |
| "Method-level produces always appends to class-level produces" | Method-level produces/consumes override the corresponding class-level condition |

## 13. Self-Check Exercises on Conditions

**Exercise 1.** Given:

~~~java
@GetMapping(path = "/search",
            params = {"type=book", "page=1"},
            headers = "X-Client=mobile",
            produces = "application/json")
public Object find() { ... }
~~~

Which request matches?

1. `GET /search?type=book&page=1` with `X-Client: mobile`, `Accept: application/json`.
2. `GET /search?type=book` with `X-Client: mobile`, `Accept: application/json`.
3. `GET /search?type=book&page=1` with `X-Client: web`, `Accept: application/json`.
4. `POST /search?type=book&page=1` with `X-Client: mobile`, `Accept: application/json`.

**Answer:** only (1), because all conditions must hold. The snippet is a mapping illustration (omitting class/return body definitions).

**Exercise 2.** A POST endpoint has `consumes="application/json"` and `produces="text/plain"`. The client sends `Content-Type: application/json`, `Accept: application/json`. Which condition prevents the endpoint from matching?

**Answer:** `produces`, because the client does not accept `text/plain`. To receive a text response, the client needs to send `Accept: text/plain` or an Accept type permitting it per contract.

**Exercise 3.** There are two GET `/report` handlers, one with `params="mode=fast"` and one with `params="mode=slow"`. If the client sends `?mode=fast`, which method is chosen? What happens if `mode` is omitted?

**Answer:** the fast mapping is selected. When `mode` is missing, neither mapping satisfies the `params` condition; in typical MVC configuration the status may be 400 due to unsatisfied params, though you should verify against actual configuration.

**Exercise 4.** An API wants to return JSON or CSV on the same path. Should it use a custom `format` header, query param, or `produces`?

**Hint:** if these are different representations of the same resource, `produces` and content negotiation with `Accept: application/json` or `Accept: text/csv` can be used, **provided** a converter/logic actually outputs CSV and broad Accept headers are tested. If the business operation exports a report file with significantly different requirements, a dedicated export endpoint or explicit format query parameter may be easier to operate.

**Exercise 5.** Why does simply changing `@RequestBody` to `@RequestParam` not necessarily solve a 415?

**Hint:** 415 happens at the `consumes` condition / media-type reading layer, potentially before arguments are resolved. Check `Content-Type`, mapping annotations, input contract, and converters rather than just swapping parameter annotations.

## 14. Checklist When Designing and Testing a Mapping

- [ ] Method matches HTTP semantics; use explicit `@GetMapping`/`@PostMapping`...
- [ ] Class base path and method path combine into the intended final URI.
- [ ] Use `params` only when selecting handlers by request parameters; keep clearly separate from `@RequestParam`.
- [ ] Use `headers` only when a genuine header condition is needed; never treat that condition as security.
- [ ] `consumes` reflects accepted request `Content-Type`, with a matching converter to read the body.
- [ ] `produces` reflects response representations matching `Accept`, with a matching converter to write the body.
- [ ] When using arrays, understand AND for params/headers and OR for media/method alternatives.
- [ ] Test requests with missing params/headers, wrong values, and mismatched Content-Type/Accept.
- [ ] Test 405, 400, 415, 406, and 404 under actual application configuration.
- [ ] If multiple mappings share method/path, verify they are clearly distinguished by conditions and non-ambiguous.
- [ ] If the class declares default consumes/produces, check method-level overrides.
- [ ] Test behavior with `Accept: */*`; never guess which format will be chosen.
- [ ] When errors occur, distinguish mapping mismatches from post-routing conversion/validation/serialization errors.
- [ ] Add `MockMvc`/integration tests for the exact combinations of method, headers, params, and media types.
- [ ] Document request headers/body, response Content-Type, and error statuses clearly in API docs.

**Practical conclusion:** In Spring MVC, the URL is only one component of `RequestMappingInfo`. A request is routed to a controller method when **HTTP method, params, headers, consumes, and produces** all satisfy the mapping requirements; if multiple methods compete, Spring evaluates specificity. Designing clear conditions lets the application route accurately, return HTTP errors for the right reasons, and avoid duplicate/hard-to-debug mappings.

### Official References

- [Spring Framework — Mapping Requests (Spring MVC)](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-requestmapping.html)
- [Spring Framework 6.1 — RequestMapping annotation API](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/web/bind/annotation/RequestMapping.html)
- [Spring Framework 6.1 — RequestMappingInfo API](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/web/servlet/mvc/method/RequestMappingInfo.html)
- [Spring Framework 6.1 — MVC Request Conditions API](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/web/servlet/mvc/condition/package-summary.html)
- [Spring Framework — HTTP Message Converters](https://docs.spring.io/spring-framework/reference/web/webmvc/message-converters.html)
- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110)
