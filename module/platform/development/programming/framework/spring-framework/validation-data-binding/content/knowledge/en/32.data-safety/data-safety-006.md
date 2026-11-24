# Input Size Limits and Regular Expression Cost in Spring Framework

An API can validate `@NotBlank`, `@Size`, and `@Pattern` accurately for business rules and still become overloaded if it **accepts an oversized request**, **builds an unnecessary object graph**, or **runs an expensive regex against untrusted data**. These three issues are distinct and must be addressed across multiple layers:

1. **HTTP transport size:** body bytes, header bytes, URL length, form parameter count, multipart parts, and request concurrency.
2. **Post-decode/post-binding object size:** `String` length, `List`/`Map` size, JSON nesting depth, nested property paths, and memory allocated to build DTOs.
3. **Validation execution cost:** regex backtracking, match count, pattern compilation frequency, custom validator logic, and I/O calls inside validation.

In **Spring Framework**, Bean Validation is a **semantic defense layer after data has been read/decoded**, not a global HTTP server byte limit. Specifically, `@Size(max = 128)` detects strings longer than 128 Java length units, yet **does not stop** the server, JSON decoder, or application framework from having already ingested the payload before the validator runs.

This Knowledge lesson belongs to the **Data Safety** series of the **Spring Framework — validation-data-binding** module. It covers the threat model, request-limiting layers, `@Size`, `@Pattern` and ReDoS, Spring MVC extension points, safe regex design, a complete **Java 17+ / Spring Boot 3.5.x / Spring Framework 6.2.x** example, testing, observability, and common configuration mistakes.

## 1. Threat Model: Small Inputs Can Still Burn CPU

Consider a resource-labeling service:

~~~http
POST /api/labels HTTP/1.1
Host: localhost:8080
Content-Type: application/json

{"label":"invoice_2026-11"}
~~~

Validation rules: `label` length from 1 to 128, allowing only ASCII letters, digits, underscore, and hyphen. An under-protected design can suffer multiple flaws:

- Allowing a tens-of-MB JSON body before `@Size(max=128)` ever runs.
- Accepting a tiny `label` field alongside hundreds of thousands of elements in a `tags` field; the deserializer allocates huge numbers of objects.
- Using a regex with **nested repetition** such as `(a+)+$`; when an input nearly matches yet fails at the end, the Java regex engine can explore huge numbers of ways to partition the `a...a` segment.
- Compiling a new regex on every request instead of reusing an immutable `Pattern`.
- Running the match repeatedly across logging, DTO validation, service policy, and persistence.
- Using `Matcher.find()` over the whole input when the rule requires matching the **entire** value.
- Trying to "rescue" a dangerous regex with an HTTP timeout, even though CPU can keep burning inside the regex engine.

**ReDoS (Regular Expression Denial of Service)** is a denial-of-service attack exploiting regex execution cost. It does not require a client to send a massive payload: an unsafe expression can exhaust CPU on relatively short strings, especially with overlapping backtracking branches.

### An illustrative expression to avoid

~~~regex
(a+)+$
~~~

This is an **anti-example**; never use it to validate real inputs. If a string contains many `a` characters ending with `!`, a backtracking engine can explore vast numbers of ways to segment the `a`s before concluding no match. Do not run unbounded-growth benchmarks against real systems; stress-testing a dangerous regex inside a live web server serving traffic can itself cause an outage.

Instead of trying to fix it by raising timeouts, **eliminate ambiguous structure**. For the label format above, use an explicit character class and bounded length:

~~~regex
\A[A-Za-z0-9_-]{1,128}\z
~~~

No nested ambiguous alternatives, no backreferences, and a finite character bound. `\A` and `\z` anchor the start and end of the **entire input** in Java regex; do not confuse `\z` with `\Z` when trailing newlines exist.

## 2. Which Limit Protects Which Resource?

| Layer | Quantity to bound | Tool / control point | What if you use `@Size` alone? |
|---|---|---|---|
| Reverse proxy / API gateway | Body bytes, URL/header size, upload rate, concurrency | Ingress, proxy body cap, rate limit | Oversized requests already reach the app |
| Servlet container | Request line/headers, parameter count, form body, multipart parts | Tomcat/Jetty/Undertow config | Container still parses large inputs |
| HTTP multipart | Per-file bytes and total multipart bytes | `spring.servlet.multipart.*` | File uploads are not capped by DTO `@Size` |
| JSON decoder | JSON strings, nesting depth, element counts, bytes | Jackson stream constraints, ingress/body cap | JSON can build huge graphs before validation |
| Spring WebDataBinder | Nested object/collection growth, property allowlist | `setAutoGrowCollectionLimit`, `setAllowedFields` | Form indices can grow binder collections if permitted |
| DTO constraint | String length, element count, value range | `@Size`, `@NotBlank`, `@Max`, custom constraints | Checks post-decode only; never replaces transport caps |
| Regex engine | State/backtracking count, scan length | Simple regex, pre-gate, finite quantifiers | Dangerous `@Pattern` can still burn CPU |
| Service/domain | Queries, batch size, processed object count | Business limits, pagination, budgets, concurrency | DTO validators do not bound DB or downstream work |
| Observability | 400/413 counts, request duration, CPU/timeouts | Cardinality-bounded metrics, traces, alerts | Attacks or misconfigurations go unseen |

**Order matters:** drop excessive bytes as early as possible; bound parsers/binders before huge structures are allocated; bound inputs before expensive regexes; run costly business work last. In production, these layers should reinforce each other rather than relying on a single annotation.

## 3. String Length, Bytes, Code Points, and User-Perceived Characters

A requirement for "at most 128 characters" can mean at least four distinct things:

1. **UTF-8 bytes** on the wire: relevant to bandwidth, proxies, and storage bytes.
2. **Java UTF-16 code units**: `String.length()`.
3. **Unicode code points**: `String.codePointCount(0, value.length())`.
4. **Grapheme clusters**: user-perceived glyphs, which can span multiple code points.

Example with a common emoji:

~~~java
String emoji = "😀";
int units = emoji.length();                     // 2
int points = emoji.codePointCount(0, units);   // 1
int bytes = emoji.getBytes(
    java.nio.charset.StandardCharsets.UTF_8).length; // 4
~~~

This is a plain Java snippet requiring no Spring. Because UTF-16 encodes the emoji as a surrogate pair, `String.length()` is **2**, the Unicode code point count is **1**, and UTF-8 requires **4 bytes**.

A Vietnamese accented letter can be represented as a precomposed code point or a base letter + combining mark; code point count and Java length do not necessarily match reader-perceived glyphs. If a business rule truly counts *grapheme clusters*, define and test counting with an appropriate Unicode library/mechanism. Never claim `@Size(max=128)` enforces 128 graphemes.

### How `@Size` measures size by data type

Jakarta Bean Validation `@Size` applies to supported types, such as:

- `CharSequence`: size/length as implemented by the provider for strings (with Hibernate Validator on `String`, based on Java length).
- `Collection`: number of elements.
- `Map`: number of entries.
- Array: number of elements.

Do not use `@Size` on an `int` to bound numeric magnitude; use `@Min`/`@Max` for integers and `@DecimalMin`/`@DecimalMax` or business rules for `BigDecimal`.

**Do not confuse them:** `@Size(max=128)` on a `String` **does not cap input at 128 UTF-8 bytes**. For ASCII-only labels, one valid character equals one UTF-8 byte, whereas for unrestricted Unicode the counts diverge sharply.

## 4. Spring MVC and Input-Limit Enforcement Points

In Spring MVC Servlet, a basic JSON or form request flows through:

~~~text
Client
  |
  v
Ingress / proxy (byte and rate limits)
  |
  v
Servlet container: request line, headers, body
  |
  +-- form URL-encoded: container parameter parsing
  +-- multipart: multipart resolver/servlet parts
  |
  v
DispatcherServlet
  |
  v
HandlerMethodArgumentResolver
  |
  +-- @RequestBody: HttpMessageConverter/Jackson
  |       +-- parse JSON -> DTO
  |
  +-- @ModelAttribute: WebDataBinder
  |       +-- form/query parameter binding
  |
  v
@Valid / @Validated (if enabled)
  |
  +-- @Size / @Pattern / custom validators
  |
  v
Controller/service
~~~

For `@RequestBody`, **Jackson/`HttpMessageConverter` reads JSON before Bean Validation evaluates the DTO**. If the JSON is huge, `@Size` arrives too late to protect bandwidth or the decoder.

For `@ModelAttribute`, `WebDataBinder` can instantiate nested objects and collections from request parameters. `DataBinder.setAutoGrowCollectionLimit(...)` and `setAllowedFields(...)` help bound workload and property binding permissions.

**Do not confuse MVC with WebFlux:** WebFlux uses `HttpMessageReader`/reactive codecs, with `maxInMemorySize` governing buffering, yet its semantics and configuration points differ from Servlet MVC. For the hands-on lab, we explicitly choose Spring MVC and embedded Tomcat.

## 5. Spring Boot 3.5 Configuration: Real Limits and Their Scopes

Example in `src/main/resources/application.properties`:

~~~properties
# HTTP request headers: not a body cap.
server.max-http-request-header-size=8KB

# Embedded Tomcat: FORM POST size limit.
server.tomcat.max-http-form-post-size=16KB

# Number of GET/POST parameters parsed by Tomcat.
server.tomcat.max-parameter-count=128

# Multipart: per-file and total multipart request limits.
spring.servlet.multipart.max-file-size=2MB
spring.servlet.multipart.max-request-size=4MB
~~~

These properties exist in Spring Boot 3.5, yet **each has a specific scope**:

- `server.max-http-request-header-size` limits **headers**, not JSON bodies.
- `server.tomcat.max-http-form-post-size` caps **form content** when Tomcat processes HTTP POST forms; **never advertise it as a universal JSON request-body limit**.
- `server.tomcat.max-parameter-count` caps how many parameters Tomcat parses (container-parsed query and POST form parameters), not elements inside a JSON array.
- `spring.servlet.multipart.max-file-size` caps **each file** in a multipart upload.
- `spring.servlet.multipart.max-request-size` caps the **total multipart request**.
- Values like 8KB/16KB/128/2MB/4MB are **demo policy choices**, not defaults or universal recommendations for every system.

If the application runs on Jetty, Undertow, or standalone Tomcat/another proxy, use the corresponding server settings. For example, `server.tomcat.*` applies only to embedded Tomcat.

### Where should the JSON body limit live?

For JSON APIs, enforce **max request body bytes** at the ingress/proxy/API gateway or a genuine **streaming byte-counting layer** in front of the JSON decoder. Example **NGINX** reverse proxy configuration:

~~~nginx
server {
    listen 8088;

    # Cap request body bytes passing through this server.
    client_max_body_size 8k;

    location / {
        proxy_pass http://127.0.0.1:8080;
    }
}
~~~

This is an **illustrative NGINX config**, not a file in the Spring Boot demo project. For real NGINX deployments, add production settings such as TLS, logging, upstream health checks, and environment-appropriate headers. Requests exceeding the body limit are typically rejected by the proxy with **HTTP 413 Content Too Large/Payload Too Large**, and may **never reach Spring controllers or `@ControllerAdvice`**.

**Important:** `MockMvc` tests run directly inside the Spring test context, **bypassing NGINX**. To prove a proxy body-byte cap works, write an **integration/system test routed through the real ingress**, not `MockMvc` alone.

### Should you check Content-Length alone?

No. `Content-Length` can be absent (chunked transfer encoding or HTTP/2 framing), may not accurately reflect payload size after intermediate processing, and does not replace actual read-stream limits. Checking `request.getContentLengthLong() > limit` is only a **conditional fast-reject**, not complete enforcement. A safe cap must count bytes actually read or be enforced by the server/gateway directly on the request stream.

## 6. JSON Decoder: String Length, Depth, and Element Count

A JSON object with a short `label` field can still be oversized if it contains:

~~~json
{
  "label": "OK",
  "items": [
    {"nested": {"value": "x"}}
  ]
}
~~~

This is a small structural JSON illustration; risk arises when arrays or nested graphs grow abnormally large. Limits to evaluate:

- **Document bytes**: entire JSON input.
- **String token length**: size of individual string tokens.
- **Nesting depth**: object/array depth to prevent recursion/stack exhaustion.
- **Number token length**: numbers with excessive digits.
- **Collection item count**: decoded element count, requiring explicit contracts and bounds.
- **Object property count**: key count on objects/maps if the schema is flexible.
- **Duplicate keys, unknown properties**: decide whether to reject or ignore per security policy.

Jackson Core provides **`StreamReadConstraints`** to configure parser limits such as maximum string length, number length, and nesting depth. When integrating Jackson with Spring Boot, ensure the settings apply to the **`ObjectMapper/JsonFactory` actually used by `MappingJackson2HttpMessageConverter`**. A standalone `new ObjectMapper()` created inside a service does not replace MVC's mapper.

**Do not cite a single parser limit as proof that all array elements or HTTP bytes are bounded.** Each Jackson constraint targets a different dimension; collection item counts and total request body bytes may require limits at separate layers.

### Post-decode size can differ from wire bytes

JSON contains escape sequences, metadata, and nested structures. Decoded data can occupy much more memory than its compressed or wire representation, especially if requests are compressed or packed with many objects. When request decompression is enabled, enforce limits both **before** and **after** decompression to mitigate decompression bombs.

Never place blind trust in a client-declared byte count.

## 7. WebDataBinder and Collection Growth

With form/query binding:

~~~http
POST /orders HTTP/1.1
Content-Type: application/x-www-form-urlencoded

items[0].code=A&items[500].code=B
~~~

if the binder allows collection auto-growth and the model structure supports it, a large index can force the framework to allocate many elements/objects during binding. Spring `DataBinder` provides:

~~~java
binder.setAutoGrowCollectionLimit(64);
binder.setAllowedFields("customer", "items[*].code");
~~~

This is an **`@InitBinder` snippet**, not a complete handler. `setAutoGrowCollectionLimit(64)` caps automatic collection growth during binding, yet **does not** replace overall HTTP body limits, form parameter counts, or caps on elements added by business code.

A controller-scoped example:

~~~java
@InitBinder("orderForm")
void configureOrderBinder(WebDataBinder binder) {
    binder.setAutoGrowCollectionLimit(64);
    binder.setAllowedFields("customer", "items[*].code");
}
~~~

Requires `@InitBinder` and `WebDataBinder` imports; applies only to the attribute named `orderForm`. Every allowed-field pattern must be verified against actual Spring binder behavior; never grant setter access to an entire entity when only a few fields are needed.

### Why not bind JPA entities directly?

An object with broad writable fields such as `role`, `price`, `ownerId`, or `admin` can suffer **mass assignment** when clients submit property names absent from the UI. Use a dedicated request DTO and explicit allowlist, preferring constructor binding/declarative binding where appropriate. Size limits are **one layer** of data protection and never replace controlling which fields are bindable.

### Validating lists with `@Size`

~~~java
public record OrderRequest(
    @Size(max = 64)
    List<@Valid OrderItem> items) {
}
~~~

This snippet requires an `OrderItem` definition and Jakarta imports. `@Size(max=64)` checks element count after the collection has been built; it **does not bound the parser or request body** prior to decoding. For endpoints handling large collections, pair explicit body-byte/streaming-parser quotas with business requirements.

## 8. Java Regex: Why Backtracking Becomes Expensive

`java.util.regex.Pattern` is a backtracking regex engine. It supports capturing groups, lookarounds, backreferences, greedy/lazy/possessive quantifiers, and atomic groups. That expressive power allows certain patterns to exhibit severe execution times on carefully chosen inputs.

### A dangerous nested-quantifier pattern

~~~regex
(a+)+$
~~~

It has nested quantifiers: `a+` inside and `(...)+` outside. When given many `a` characters followed by a failing character at the end, the engine can explore vast numbers of ways to partition the same sequence into groups before rejecting it.

This is a **structural analysis example**; never put it into a demo benchmark or live validator. A performance test on this regex with long inputs can peg CPU without yielding stable timings across JDKs or machines.

### Other patterns needing careful review

- Nested quantifiers: `(x+)+`, `(x*)*`.
- Alternatives with overlapping match regions under a quantifier: e.g., branches matching repeated `a`s.
- Patterns with multiple `.*`/`.+` and backreferences causing combinatorial explosion.
- Regexes invoked via `find()` on long strings when substring search is unnecessary.
- User-supplied regexes or regexes dynamically built from request data without proper quoting/filtering.

**Not every `.*` is dangerous, and not every regex with a lookahead causes ReDoS.** Risk depends on the combination of pattern, input shape, failure point, engine, and control over input length/work. Reviews must analyze worst-case mismatch paths, not merely count pattern characters.

### Lazy quantifiers do not automatically solve ReDoS

Changing `+` to `+?` (reluctant/lazy) alters branch exploration order without **guaranteeing** elimination of exponential backtracking. Analyze semantics and complexity rather than applying a mechanical syntax tweak.

### Possessive quantifiers and atomic grouping

Java supports:

~~~regex
a++
(?>a+)
~~~

`a++` is a **possessive quantifier**, and `(?>...)` is an **atomic group**. They suppress backtracking into the matched segment, which can mitigate risk for appropriate patterns. However, they can also **change the accepted language**, since the engine never gives characters back to trailing parts of the regex.

**Illustrative difference:**

~~~regex
a+a
a++a
~~~

On input `aa`, `a+a` matches because `a+` takes one character and the trailing `a` takes the second. `a++a` fails to match because `a++` consumes all `a` characters and refuses to backtrack. Never "fix" regexes by slapping on `+` without re-running semantic tests.

### Prefer simple structural validation

If the requirement is simply an ASCII label with one character class and bounded length:

~~~regex
\A[A-Za-z0-9_-]{1,128}\z
~~~

This is far clearer than pasting giant email/URL/ID regexes with overlapping branches. For email/URLs, prefer maintained libraries/parsers, basic validation, and business rules rather than copying complex RFC regexes of uncertain safety.

## 9. `Pattern` and `Matcher`: API and Lifecycle

Structure using `java.util.regex`:

~~~java
private static final Pattern SAFE_LABEL =
    Pattern.compile("\\A[A-Za-z0-9_-]{1,128}\\z");

boolean valid = SAFE_LABEL.matcher(input).matches();
~~~

Snippet inside a class with variable `input`, requiring `import java.util.regex.Pattern;`.

Key points:

- **Compiled `Pattern` instances are immutable** and safe to share across requests/threads.
- **`Matcher` instances are mutable and not thread-safe**; create a fresh one via `pattern.matcher(value)` per match.
- `Matcher.matches()` requires the **entire input** to match the regex, suited for validating a field's format.
- `Matcher.find()` matches **any substring**, unsuitable when the rule must validate the whole value.
- `String.matches(regex)` compiles a new pattern per API implementation; avoid calling it repeatedly on hot paths for fixed regexes at high throughput.
- In Java string literals, regex `\A` must be written `"\\A"` because Java uses backslash as its escape character. The same applies to `\z`, `\d`, `\s`, etc.

### Optimal check order for a field

~~~java
boolean acceptable(String value) {
    if (value == null || value.isEmpty()) {
        return false;
    }
    if (value.length() > 128) {
        return false; // Return before invoking regex.
    }
    return SAFE_LABEL.matcher(value).matches();
}
~~~

Snippet in a class containing `SAFE_LABEL`. Checking `length` before matching guarantees **this match call** sees strings of at most 128 Java UTF-16 units.

**However**, this runs only after the application **already holds the String**. It does not cap JSON bytes or decoding work. Moreover, if the DTO also declares `@Pattern` in Bean Validation, constraint annotations are **not guaranteed to run in declaration order**, so never claim `@Size` definitely runs before `@Pattern`. If a pattern is dangerous, fix the pattern or use an explicit validation group sequence/ordered validation rather than relying on `@Size` sitting one line above.

### Is there a direct timeout for `java.util.regex.Pattern`?

In Java 17, `Pattern`/`Matcher` lacks a built-in **per-match time budget API** guaranteeing a regex terminates after N milliseconds. Running a match in a `Future` and calling `future.cancel(true)` is not reliable protection if the regex is CPU-bound and fails to respond promptly to interruption. The occupied thread can still keep draining system resources.

Preferred strategy:

1. **Rewrite patterns to have predictable cost**.
2. **Bound input length before matching**.
3. **Bound concurrency/rate** at the boundary.
4. **Evaluate alternative regex engines** with linear-time guarantees when needed (e.g., RE2/J) and compare supported regex features; this is a deliberate engine/API change, not a drop-in replacement for every Java regex.
5. Monitor p95/p99 CPU, rejection counts, and validation duration.

Never promote HTTP timeouts or cancellation as a complete solution to ReDoS.

## 10. Jakarta Bean Validation: `@NotBlank`, `@Size`, `@Pattern`

A Spring Boot 3 DTO uses:

~~~java
public record LabelInput(
    @NotBlank
    @Size(max = 128)
    @Pattern(regexp = "\\A[A-Za-z0-9_-]{1,128}\\z")
    String label
) {
}
~~~

This Java snippet is completed in the runnable section. Meaning:

- `@NotBlank`: `label` must not be null, empty, or whitespace-only.
- `@Size(max=128)`: string length must not exceed the specified limit.
- `@Pattern`: format permits only ASCII letters, digits, underscore, and hyphen; the quantifier itself also bounds length to 1..128.
- `@Valid @RequestBody LabelInput` on the controller instructs the framework to validate the DTO after JSON decoding succeeds.

**One object can violate multiple constraints:** for example, `label=""` violates both `@NotBlank` and `@Pattern`. If the error response emits a deduplicated list of field names, that does not imply only one constraint failed. The lab intentionally deduplicates field names to keep the demo API simple.

### Do `@Size` and `@Pattern` run in order?

Do not rely on annotation declaration order in source files. If an expensive validator runs on large input, adding `@Size` on the same field **provides no execution-order guarantee**.

Two strategies exist:

- **Safe in the pattern itself:** use a simple, bounded expression as shown so that even if `@Pattern` runs before `@Size`, cost remains controlled.
- **Two-stage validation:** place an explicit length guard before any expensive check, or design a **validation group sequence** so the size group runs before the format group, backed by tests. Group sequences add contract complexity and do not replace network-level body caps.

In real projects, if multiple forms share a complex check, put it into an audited service/validator rather than duplicating a hard-to-audit regex across many `@Pattern` annotations.

## 11. Complete Spring Boot 3.5 / Java 17+ Program

We build a REST endpoint:

- `POST /api/labels` accepts JSON `{"label":"invoice_2026"}`.
- Valid labels are **1 to 128 UTF-16 units**, ASCII letters, digits, underscore, or hyphen only.
- Valid input returns HTTP **201 Created**.
- DTO constraint failures return HTTP **400 Bad Request** with field names, without leaking rejected values.
- The service policy applies a length gate **before** the regex in its standalone check.
- HTTP body byte caps are **not** solved by Java/DTOs alone; section 5 showed how to configure ingress.

Files live in package `com.example.inputsafety`, using Spring Boot **3.5.x** and Java **17+**. You can generate the project via Spring Initializr with Spring Web and Validation.

### 11.1. Gradle dependencies

In `build.gradle` with a compatible Spring Boot plugin/version setup:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-validation'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

The Web starter here is Servlet Spring MVC (standard embedded Tomcat), not WebFlux. The Validation starter brings the Jakarta provider onto the classpath. The Test starter supplies JUnit 5 and MockMvc.

Do not compile Spring-importing classes with plain `javac` using only the JDK; use the dependencies above and a valid Boot project Gradle wrapper.

### 11.2. `InputSafetyApplication.java`

`src/main/java/com/example/inputsafety/InputSafetyApplication.java`:

~~~java
package com.example.inputsafety;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class InputSafetyApplication {

    public static void main(String[] args) {
        SpringApplication.run(InputSafetyApplication.class, args);
    }
}
~~~

### 11.3. `LabelInput.java`

`src/main/java/com/example/inputsafety/LabelInput.java`:

~~~java
package com.example.inputsafety;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;

public record LabelInput(
    @NotBlank
    @Size(max = 128)
    @Pattern(regexp = "\\A[A-Za-z0-9_-]{1,128}\\z")
    String label
) {
}
~~~

This is an immutable request DTO; never bind a domain/entity object directly. `@Pattern` is designed to be simple and bounded **even when annotation validators run in unspecified order**.

### 11.4. `LabelPolicy.java`

`src/main/java/com/example/inputsafety/LabelPolicy.java`:

~~~java
package com.example.inputsafety;

import java.util.regex.Pattern;

public final class LabelPolicy {

    static final int MAX_LABEL_UNITS = 128;

    private static final Pattern LABEL_PATTERN =
        Pattern.compile("\\A[A-Za-z0-9_-]{1,128}\\z");

    private LabelPolicy() {
    }

    public static boolean acceptable(String label) {
        if (label == null || label.isEmpty()) {
            return false;
        }
        if (label.length() > MAX_LABEL_UNITS) {
            // Ensure this method's regex never sees a long String.
            return false;
        }
        return LABEL_PATTERN.matcher(label).matches();
    }
}
~~~

This method intentionally **does not echo back invalid input**. `String.length()` checks UTF-16 units, followed by a simple regex verifying characters. `Pattern` is `static final` and thread-safe to share; each `matcher(...)` creates a fresh `Matcher`.

**Does this duplicate the annotation check?** Yes, **deliberately to teach the boundary**: the annotation expresses the declarative contract on the DTO; the policy illustrates an *explicit pre-match guard* for an application-initiated match. In a production codebase, consider avoiding running the regex twice by choosing a single source of truth with tests verifying security and performance. Having a guard in the policy **does not** force the earlier `@Pattern` annotation to run in a predictable order.

### 11.5. `LabelController.java`

`src/main/java/com/example/inputsafety/LabelController.java`:

~~~java
package com.example.inputsafety;

import jakarta.validation.Valid;

import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@RestController
@RequestMapping("/api/labels")
public class LabelController {

    @PostMapping(
        consumes = MediaType.APPLICATION_JSON_VALUE,
        produces = MediaType.APPLICATION_JSON_VALUE
    )
    public ResponseEntity<LabelReply> create(
            @Valid @RequestBody LabelInput input) {

        if (!LabelPolicy.acceptable(input.label())) {
            throw new ResponseStatusException(
                HttpStatus.BAD_REQUEST, "Invalid label");
        }

        return ResponseEntity.status(HttpStatus.CREATED)
            .body(new LabelReply(
                input.label(), input.label().length()));
    }

    public record LabelReply(
        String label,
        int utf16Units
    ) {
    }
}
~~~

If input fails `@Valid`, Spring MVC typically raises `MethodArgumentNotValidException` before entering the handler; the advice below maps it to a 400 response. If the controller itself rejects via `LabelPolicy`, `ResponseStatusException` also produces 400, though its default body **need not match** the custom Bean Validation response. Under the current constraints, the policy is simply a redundant check; valid inputs reach 201.

### 11.6. `LabelValidationAdvice.java`

`src/main/java/com/example/inputsafety/LabelValidationAdvice.java`:

~~~java
package com.example.inputsafety;

import java.util.List;

import org.springframework.http.ResponseEntity;
import org.springframework.validation.FieldError;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class LabelValidationAdvice {

    @ExceptionHandler(MethodArgumentNotValidException.class)
    public ResponseEntity<InvalidLabelReply> invalidInput(
            MethodArgumentNotValidException ex) {

        List<String> fields = ex.getBindingResult()
            .getFieldErrors()
            .stream()
            .map(FieldError::getField)
            .distinct()
            .sorted()
            .toList();

        return ResponseEntity.badRequest()
            .body(new InvalidLabelReply(
                "INVALID_LABEL", fields));
    }

    public record InvalidLabelReply(
        String code,
        List<String> fields
    ) {
    }
}
~~~

The response exposes only field names and a stable error code; it never serializes `BindingResult`, `FieldError.getRejectedValue()`, or raw client input. If a product needs multiple constraint messages, add an `issues[]` field per a dedicated contract translated via `MessageSource`, avoiding loss of detail from field-level `distinct()`.

`ResponseEntityExceptionHandler` is **unnecessary** for this simple demo. If production advice **already extends `ResponseEntityExceptionHandler`**, override `handleMethodArgumentNotValid(...)` instead of declaring a duplicate `@ExceptionHandler(MethodArgumentNotValidException.class)` in a subclass.

### 11.7. `application.properties`

`src/main/resources/application.properties`:

~~~properties
# Caps headers, FORM POST, and multipart within their respective scopes.
server.max-http-request-header-size=8KB
server.tomcat.max-http-form-post-size=16KB
server.tomcat.max-parameter-count=128
spring.servlet.multipart.max-file-size=2MB
spring.servlet.multipart.max-request-size=4MB
~~~

**This is not yet a global JSON-body cap.** When exposing the endpoint to the Internet, add a proxy/gateway body limit or a streaming byte-enforcement layer ahead of the JSON decoder; never assume a `@Size` example solves payload DoS.

### 11.8. Running and curl

From the project root with Gradle wrapper:

~~~bash
./gradlew bootRun
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat bootRun
~~~

With the app on default port 8080, valid input:

~~~bash
curl -i -X POST "http://localhost:8080/api/labels" \
  -H "Content-Type: application/json" \
  -d '{"label":"invoice_2026-11"}'
~~~

Expected HTTP **201 Created**:

~~~json
{
  "label": "invoice_2026-11",
  "utf16Units": 15
}
~~~

Character count for `invoice_2026-11`: `invoice` (7), underscore (1), `2026` (4), hyphen (1), `11` (2) → **15** UTF-16 units total.

Input longer than 128:

~~~bash
python -c "import json; print(json.dumps({'label':'a'*129}))" \
  | curl -i -X POST "http://localhost:8080/api/labels" \
      -H "Content-Type: application/json" --data-binary @-
~~~

Illustrative shell command assuming Python is available locally. It generates 129 `a`s; both `@Size(max=128)` and `@Pattern` can report violations. Expected HTTP **400**, body from the advice:

~~~json
{
  "code": "INVALID_LABEL",
  "fields": ["label"]
}
~~~

When the request sends `{"label":"hello!"}`, `!` is invalid and returns HTTP 400. When `label=""`, `@NotBlank`/`@Pattern` fail; the response still lists `label` once because the advice uses `distinct()`.

**If a client sends a 100 MB body:** `@Valid`/`@Size` may reject it after the body has reached Spring MVC, yet that **does not prove** the network/parser avoided resource usage. Test the proxy cap via a dedicated test rather than sending giant payloads to a production server.

## 12. Testing with JUnit 5 and MockMvc

To test the *input contract*, run integration tests through Spring MVC. To test *guard ordering before regex*, call `LabelPolicy.acceptable` directly with a long string without benchmarking dangerous regexes.

### 12.1. `LabelPolicyTest.java`

`src/test/java/com/example/inputsafety/LabelPolicyTest.java`:

~~~java
package com.example.inputsafety;

import java.nio.charset.StandardCharsets;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class LabelPolicyTest {

    @Test
    void acceptsBoundariesWithAllowedAscii() {
        assertTrue(LabelPolicy.acceptable("a"));
        assertTrue(LabelPolicy.acceptable("a".repeat(128)));
    }

    @Test
    void rejectsTooLongBeforeCallingMatcher() {
        assertFalse(LabelPolicy.acceptable(
            "a".repeat(10_000)));
    }

    @Test
    void rejectsDisallowedCharacters() {
        assertFalse(LabelPolicy.acceptable("a!"));
        assertFalse(LabelPolicy.acceptable("a b"));
        assertFalse(LabelPolicy.acceptable("😀"));
    }

    @Test
    void utf16UnitsDifferFromBytesAndCodePoints() {
        String emoji = "😀";
        assertEquals(2, emoji.length());
        assertEquals(1, emoji.codePointCount(
            0, emoji.length()));
        assertEquals(4, emoji.getBytes(
            StandardCharsets.UTF_8).length);
    }
}
~~~

These tests avoid running `(a+)+$` or asserting wall-clock timings, which fluctuate across JDKs/CPUs/loads. `"a".repeat(10_000)` merely verifies that `acceptable` returns false via the length guard; it causes no bad-regex stress.

### 12.2. `LabelControllerTest.java`

`src/test/java/com/example/inputsafety/LabelControllerTest.java`:

~~~java
package com.example.inputsafety;

import com.fasterxml.jackson.databind.ObjectMapper;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class LabelControllerTest {

    @Autowired
    private MockMvc mvc;

    @Autowired
    private ObjectMapper mapper;

    private String json(String label) throws Exception {
        return mapper.writeValueAsString(
            new LabelInput(label));
    }

    @Test
    void validAsciiLabelReturns201() throws Exception {
        mvc.perform(post("/api/labels")
                .contentType(MediaType.APPLICATION_JSON)
                .content(json("invoice_2026-11")))
            .andExpect(status().isCreated())
            .andExpect(jsonPath("$.label")
                .value("invoice_2026-11"))
            .andExpect(jsonPath("$.utf16Units")
                .value(15));
    }

    @Test
    void exactly128UnitsIsValid() throws Exception {
        mvc.perform(post("/api/labels")
                .contentType(MediaType.APPLICATION_JSON)
                .content(json("a".repeat(128))))
            .andExpect(status().isCreated())
            .andExpect(jsonPath("$.utf16Units")
                .value(128));
    }

    @Test
    void oneOverLimitIsRejected() throws Exception {
        mvc.perform(post("/api/labels")
                .contentType(MediaType.APPLICATION_JSON)
                .content(json("a".repeat(129))))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code")
                .value("INVALID_LABEL"))
            .andExpect(jsonPath("$.fields[0]")
                .value("label"));
    }

    @Test
    void invalidCharacterIsRejected() throws Exception {
        mvc.perform(post("/api/labels")
                .contentType(MediaType.APPLICATION_JSON)
                .content(json("hello!")))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.fields[0]")
                .value("label"));
    }

    @Test
    void blankLabelIsRejected() throws Exception {
        mvc.perform(post("/api/labels")
                .contentType(MediaType.APPLICATION_JSON)
                .content(json("")))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.fields[0]")
                .value("label"));
    }

    @Test
    void missingLabelIsRejected() throws Exception {
        mvc.perform(post("/api/labels")
                .contentType(MediaType.APPLICATION_JSON)
                .content(json(null)))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.fields[0]")
                .value("label"));
    }

    @Test
    void unicodeNotAllowedByAsciiPolicy() throws Exception {
        mvc.perform(post("/api/labels")
                .contentType(MediaType.APPLICATION_JSON)
                .content(json("😀")))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.fields[0]")
                .value("label"));
    }

    @Test
    void malformedJsonGetsClientError() throws Exception {
        mvc.perform(post("/api/labels")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{"))
            .andExpect(status().isBadRequest());
    }
}
~~~

Under Spring Boot 3.5 + Web/Validation/Test starters, **12 test methods** (4 unit + 8 MVC) are expected to pass. This is an analytical expectation from the sample code; it does not claim Gradle was executed. Using the Boot-provided `ObjectMapper` lets tests build JSON safely instead of concatenating and manually escaping strings.

**MockMvc does not verify proxy caps or network bandwidth.** It exercises Spring MVC controllers and validation without sending payloads through NGINX as in section 5. A real E2E test routed through the proxy is needed to verify HTTP 413 on oversized bodies.

### Testing 413 at the ingress layer

With NGINX `client_max_body_size 8k` in a test environment, send a JSON body slightly larger than 8 KiB, and observe the proxy HTTP status and upstream logs. Never assume every oversized response goes through `@RestControllerAdvice`; the proxy can respond directly without invoking the controller.

In production, verify limits on the **actual total payload**, including `Transfer-Encoding: chunked` where applicable, and confirm health/rate policies cannot be bypassed via alternate endpoints.

## 13. Designing Safe Regexes for Specific Problems

### ASCII labels

Requirement: 1..128 characters from a simple alphabet:

~~~regex
\A[A-Za-z0-9_-]{1,128}\z
~~~

Advantages: clear, bounded, no backreferences, no nested ambiguous repetition.

### Code consisting of exactly 8 ASCII digits

~~~regex
\A[0-9]{8}\z
~~~

If using `\d` in Java regex, Unicode semantics depend on flags and pattern settings. When business rules accept only ASCII digits, `[0-9]` is clearer.

### Format of 3 uppercase letters and 4 digits

~~~regex
\A[A-Z]{3}-[0-9]{4}\z
~~~

Valid example `ABC-1234`; invalid example `AB-1234`. No `.*` or alternation needed.

### Lowercase slug with hyphen-separated groups

You can use:

~~~regex
\A[a-z0-9]+(?:-[a-z0-9]+)*\z
~~~

This pattern matches a slug of alphanumeric tokens separated by at most one `-`; bound input length before applying it on untrusted traffic. Whenever reviewing patterns with nested quantifiers, inspect overlapping character sets and failure behavior rather than assuming safety just because it looks short.

An even easier-to-audit option is a **linear hand-written parser**: check length, iterate character by character, permitting ASCII alphanumerics and `-` when neither leading, trailing, nor consecutive. For simple grammars, an O(n) loop is often easier to prove bounded than a complex regex.

### Email, URLs, and international formats

Never grab a multi-page "full RFC regex" from the Internet to put in `@Pattern` for emails/URLs in public APIs. Prefer Jakarta Validation `@Email` (within its known limits) plus domain business checks, or proper URI/URL/IDN parsers. Always cap length before expensive steps, and never equate successful email/URL parsing with verified ownership or SSRF protection.

## 14. Separating Safety Policy from Error Messages

A well-designed API does not expose sensitive internals about engines, internal regex patterns, or object graphs to clients:

| Cause | Typical appropriate status | What public body should include |
|---|---|---|
| Field too long post-decode, schema invalid | HTTP 400 | `INVALID_FIELD_LENGTH`, field name, max length |
| Regex-format mismatch on a field | HTTP 400 | `INVALID_FIELD_FORMAT`, format guidance |
| Request body exceeds ingress byte limit | HTTP 413 | `PAYLOAD_TOO_LARGE` or generic |
| Multipart file exceeds limit | HTTP 413 or config-matched status | Max file/request size; never expose temp paths |
| Malformed JSON | HTTP 400 | `MALFORMED_JSON` |
| Missing/unsupported content type | HTTP 400/415 as applicable | Supported content types |
| Rate limit exceeded | HTTP 429 | Retry details if contract allows |
| Server or validator code bug | HTTP 500 | Generic message; internal logs separately |

**Do not hard-code every error to HTTP 400.** A request exceeding byte limits differs from a field failing validation rules. In Spring MVC, `MethodArgumentNotValidException` reflects DTO violations, whereas JSON parsing errors yield `HttpMessageNotReadableException` and multipart limit breaches yield `MaxUploadSizeExceededException`. Proxy body caps usually reject before Spring ever sees the request.

### Should rejected values be logged?

Not by default. Oversized requests can bloat logs rapidly and contain tokens/PII. Log **error code, route template, and length band** or byte buckets rather than full field values. For ReDoS concerns, record validation duration/CPU metrics and correlation IDs rather than raw payloads.

### Avoid leaking internal patterns

If an application uses a regex to validate a transaction code, return a message like "Code must be 8 digits" rather than returning the raw complex regex in the response. Regexes are implementation details, and overly technical errors do not help users fix input.

## 15. Rate Limiting and Time Budgets Complement, Not Replace, Regex Review

An attacker can send many small requests to consume resources. Beyond size caps:

- **Per-client rate limits** and global quotas at the gateway.
- **Connection/read timeouts** to curb slow-client abuse; semantics depend on the server.
- **Thread pool / concurrency bounds** and backpressure when upstream is overloaded.
- **Timeouts on downstream I/O** such as databases/network calls, without treating them as regex CPU timeouts.
- **Circuit breakers** for dependency failures, never as a substitute for input validation.
- **Batch element caps** and business-logic execution budgets.
- **p95/p99 metrics** for parsing, validation, and total requests; alert on anomalies.

A terrible regex can still let a single request pin a CPU thread for a long time. Rate limiting curbs amplification without fixing pattern complexity. **Bring single-request cost down to a predictable level first**, then use quotas to protect aggregate capacity.

## 16. If the Application Lets Users Supply Arbitrary Regexes

This carries higher risk than fixed developer-written regexes. Never pass user strings directly into:

~~~java
Pattern compiled = Pattern.compile(userPattern);
boolean match = compiled.matcher(userText).find();
~~~

This is an **anti-example**, as both pattern and input are untrusted. Merely placing `@Size(max=128)` on `userPattern` does not guarantee safety: even a short expression can trigger ReDoS.

Options:

1. **Disallow arbitrary regexes** if the product only needs simple prefix/suffix/exact/wildcard matching; implement a safe parser instead.
2. If regexes are mandatory, evaluate an engine with **linear-time guarantees** and restrict syntax features; clearly document lack of backreferences/lookarounds or other unsupported constructs.
3. Cap lengths of both **pattern** and **input**; bound attempt counts, search counts, and rates.
4. Enforce business/resource rules before compiling or executing.
5. Isolate execution with reliable time/memory budgets, cancellation support, and concurrency limits if complex evaluation is permitted.
6. Never use `Pattern.quote(...)` to "sanitize" a regex when the user actually expects regex syntax; `Pattern.quote` turns text into **literal text**, which is right for literal search yet breaks regex feature semantics.

### What should you use for literal search?

If you need to search for a client-supplied string **without regex syntax**, use `String.contains(...)`/`indexOf(...)` or:

~~~java
Pattern safeLiteral =
    Pattern.compile(Pattern.quote(userText));
~~~

Snippet requiring imports and variable `userText`. `Pattern.quote` ensures characters like `(`, `*`, `+`, and `[` act as literals rather than regex operators. For simple literal substring searches, `String.contains` is usually clearer and avoids the regex engine altogether.

## 17. Unicode, Normalization, and Pre-/Post-Normalization Checks

If the application permits Unicode labels, decide:

- Are emojis, combining marks, multiple scripts, and control characters permitted?
- Is length measured in bytes, UTF-16 units, Unicode code points, or grapheme clusters?
- Is NFC/NFKC normalization applied? Normalization can change string representation, and sometimes length or character sets.
- Is locale-sensitive or invariant case folding required?
- Are visually similar characters with distinct code points (homoglyphs/confusables) allowed?

**Never validate one representation and persist another without re-checking.** If the system normalizes Unicode before saving, establish the pipeline order: cap bytes before decode → decode safely → normalize under budget → enforce length and format on the normalized string → persist.

Identifiers tied to authorization or signatures also require consistent canonicalization across components. Syntactically valid regex matching does not solve homoglyph spoofing or path traversal on its own.

## 18. Comparing Spring MVC and WebFlux at the Resource Level

| Aspect | Spring MVC Servlet | Spring WebFlux |
|---|---|---|
| Body decoder | `HttpMessageConverter`/Jackson | `HttpMessageReader`/codecs |
| Backpressure/reactive types | Typically direct DTOs, Servlet I/O | `Mono<T>`/`Flux<T>` via resolvers |
| Annotation validation | `@Valid`/`@Validated` after binding/decoding | `@Valid`/`@Validated` with reactive resolvers |
| Multipart cap | Servlet multipart config and server/proxy | Separate codec/multipart server settings |
| Buffered data limit | Parser/server/proxy; no single Boot property for all JSON | Codec `maxInMemorySize` has a dedicated role |
| Regex CPU risk | Java `Pattern` still backtracks | Same: reactive wrappers do not make regex non-blocking |
| Large request cap | Needs ingress/proxy or real byte-counting | Needs ingress/proxy and reactor/codec limits |
| Blocking custom validator | Ties up a Servlet worker thread | Can block the event loop—even more critical to avoid |

WebFlux does not automatically solve ReDoS. `Mono<Dto>` or `Flux<Dto>` is an asynchronous data pipeline; a `ConstraintValidator.isValid(...)` invoking a backtracking regex still burns CPU on whatever thread executes it.

## 19. Common Issues and Diagnostics

| Symptom | Likely cause | Remedy |
|---|---|---|
| 20MB JSON body reaches controller despite `@Size(max=128)` | `@Size` runs after JSON decoder | Cap bytes at ingress and parser; keep DTO constraint as inner layer |
| `server.tomcat.max-http-form-post-size=16KB` does not block JSON | It caps form POSTs, not JSON bodies generally | Use proxy/streaming body byte cap |
| 128 emojis treated as longer than 128 "characters" | Java UTF-16 units differ from code points/glyphs | Define product length unit and test Unicode |
| Field has `@Size` yet regex is still slow | Constraint execution order is unguaranteed | Write safe regex, ordered validation, or explicit gate |
| Regex fails very slowly on nearly valid inputs | Nested/ambiguous quantifiers | Audit and rewrite pattern, check worst case |
| Changing `+` to `+?` did not help | Lazy quantifiers still backtrack | Simplify grammar; test semantics if using possessive/atomic |
| Adding `++` rejects valid inputs | Possessive quantifier never backtracks | Verify equivalence with unit tests |
| `Matcher.find()` accepts strings with forbidden content | Matches only a substring | Use `matches()` and full-string policy |
| Patterns compiled on every request | Repeated compilation | Use `static final Pattern` for fixed regexes |
| Sharing one `Matcher` across threads fails | `Matcher` is stateful | Create a new `Matcher` per input |
| `Future.cancel(true)` does not free CPU immediately | No guaranteed match-timeout contract | Never rely on cancel; rewrite pattern/bound CPU |
| File upload exceeds limit yet advice does not run | Multipart parser/container/proxy rejects before handler | Test end-to-end; map exception where thrown |
| Form with `items[99999]` consumes excessive memory | Collection auto-growth/binding policy | Bound autoGrow, allowedFields, parameter count |
| Deep JSON nesting | Parser/object graph lacks depth limit | Use Jackson `StreamReadConstraints` and byte caps |
| Custom validator queries DB per field | Synchronous I/O inside validator | Separate structural validation from policy/service checks |
| MockMvc passes yet ingress still accepts huge bodies | MockMvc bypasses reverse proxy | Add E2E traffic tests through real ingress |
| 400 response leaks long input/tokens | Serializing `FieldError` or logging raw bodies | Minimal error DTO, log size buckets |
| HTTP 429 active yet one request still pins CPU | Rate limiting does not fix regex complexity | Fix pattern, bound input/CPU |
| Byte cap checked only via `Content-Length` | Chunked/streaming requests may omit `Content-Length` | Enforce actual bytes on stream/proxy |

### Practical debugging workflow

1. Note the web stack: MVC/Servlet or WebFlux.
2. Identify input type: JSON, form, multipart, query, header, file.
3. Inspect **byte** limits at proxy/container before checking annotations.
4. Check parser limits: string tokens, nesting depth, item/parameter counts.
5. Confirm the Bean Validation provider is active.
6. Measure length in the exact unit (bytes/UTF-16/code points).
7. Read regexes for nested ambiguity, backreferences, and scan semantics.
8. Verify `Pattern` is reused and `Matcher` is never shared.
9. Test 0/1/max/max+1 and near-match failing inputs, **never running dangerous benchmarks in prod**.
10. Verify status codes: 400 for invalid fields, 413 for body-byte cap breaches, 429 for quotas.
11. Measure parser/validator timing and CPU; track p95/p99 and reject rates.
12. Verify ingress caps E2E, since unit/MockMvc tests bypass proxies.

## 20. Self-Check Questions

**1. Does `@Size(max=128)` block a 5 MB JSON request body before Spring reads it?**

No. It checks the DTO/field after decoding/binding; a byte cap is needed at ingress/parser layers.

**2. Does `server.tomcat.max-http-form-post-size` cap all JSON bodies at that same size?**

No. It is Tomcat's form POST content cap, not a universal JSON body cap.

**3. For `String emoji="😀"`, what are `emoji.length()` and UTF-8 bytes?**

`length()==2` UTF-16 code units; UTF-8 is 4 bytes; code point count is 1.

**4. Why does placing `@Size` before `@Pattern` in source code not guarantee the regex runs second?**

Jakarta Bean Validation does not guarantee constraint execution order based on annotation order.

**5. What is wrong with `(a+)+$`?**

Nested ambiguous repetition can cause massive backtracking on near-matching inputs that fail at the end.

**6. What is the primary fix if a regex has bad worst-case cost?**

Rewrite the regex/grammar to remove ambiguity, bound input length, and test semantics—not merely raising timeouts.

**7. Can `Pattern` or `Matcher` be shared across requests?**

A compiled `Pattern` is immutable and safe to share. `Matcher` is mutable and not thread-safe; create a new one per match.

**8. When validating an entire label, should you use `matches()` or `find()`?**

`matches()`. `find()` is appropriate when you genuinely want to search for a substring.

**9. Does `setAutoGrowCollectionLimit(64)` also bound the JSON array decoder?**

No. It governs data-binding collection auto-growth, not a universal JSON array cap.

**10. Why does a proxy body cap need its own integration test?**

Because `MockMvc` bypasses the proxy; it does not prove HTTP 413 is enforced ahead of the application.

**11. Is `Future.cancel(true)` a reliable regex timeout in Java 17?**

No. Never treat cancellation/interruption as a guarantee that regex CPU execution will halt on deadline.

**12. If clients only need to search for a literal string they supply, do you need arbitrary regexes?**

No. Use `String.contains`/`indexOf` or `Pattern.quote` to prevent input characters from acting as regex syntax.

## 21. Operations and Security Review Checklist

- [ ] Define max byte size per endpoint at ingress/proxy.
- [ ] Configure header/request-line sizes, parameter counts, form caps, and multipart limits.
- [ ] Configure parser limits for JSON strings, numbers, nesting depth, and collection sizes where needed.
- [ ] Bound `WebDataBinder` auto-grow and property allowlists for form binding.
- [ ] Use dedicated DTOs; never bind sensitive entities directly.
- [ ] Define `@Size` units clearly: UTF-16 length vs. product-specific Unicode semantics.
- [ ] Never rely on `@Size` running before `@Pattern` without explicit ordering.
- [ ] Audit regexes for nested quantifiers, overlapping alternatives, backreferences, and unanchored scans.
- [ ] For fixed regexes, use bounded character classes and full-string matching where appropriate.
- [ ] Compile `Pattern` once and create a dedicated `Matcher` per request.
- [ ] Never treat `Future.cancel`/HTTP timeouts as a guaranteed ReDoS defense.
- [ ] Have a dedicated strategy if clients can supply regexes; never use arbitrary Java `Pattern` by default.
- [ ] Never serialize rejected values, tokens, or stack traces in validation errors.
- [ ] Return proper status codes: 400 (field/schema), 413 (byte cap), 429 (quota), 500 (server).
- [ ] Test boundaries 0/1/max/max+1, Unicode, invalid fields, and malformed JSON.
- [ ] Verify transport request caps through real ingress, not `MockMvc` alone.
- [ ] Monitor latency, CPU, reject rates, rate limits, and behavior under load.
- [ ] Re-review limits/patterns whenever schemas, servers, JDKs, or Spring Boot versions change.

**Remember:** Input protection must be **multi-layered**. `@Size` validates length after binding and `@Pattern` validates format yet can trigger **ReDoS** if poorly designed; neither replaces **HTTP byte, JSON parser, and binder growth limits**. In Spring Boot 3.5, apply properties within their actual scopes (forms, multipart, headers), put JSON byte limits at the ingress/streaming layer, and keep regexes simple, bounded, and tested.

## Official References

- [Spring Framework — Data Binding](https://docs.spring.io/spring-framework/reference/core/validation/data-binding.html)
- [Spring Framework — Jakarta Bean Validation](https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html)
- [Spring Framework — Spring MVC Validation](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-validation.html)
- [Spring Framework — DataBinder Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/validation/DataBinder.html)
- [Spring Boot 3.5 — Common Application Properties](https://docs.spring.io/spring-boot/3.5/appendix/application-properties/index.html)
- [Spring Boot 3.5 — Spring MVC / Multipart](https://docs.spring.io/spring-boot/3.5/how-to/spring-mvc.html)
- [Java 17 — Pattern Javadoc](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/regex/Pattern.html)
- [Java 17 — Matcher Javadoc](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/regex/Matcher.html)
- [OWASP — Regular Expression Denial of Service](https://owasp.org/www-community/attacks/Regular_expression_Denial_of_Service_-_ReDoS)
- [Jackson Core — StreamReadConstraints Javadoc](https://javadoc.io/doc/com.fasterxml.jackson.core/jackson-core/latest/com/fasterxml/jackson/core/StreamReadConstraints.html)
