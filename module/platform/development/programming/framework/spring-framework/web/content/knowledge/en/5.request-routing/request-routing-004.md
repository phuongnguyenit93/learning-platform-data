# Path Variables, Regular Expressions, and Wildcard Paths in Spring MVC

Spring MVC uses URI patterns to decide which controller method handles a request. A route can match a fixed URL like `/products/search`, extract an identifier from a single segment like `/products/{id}`, constrain a segment with a regular expression like `/products/{id:[0-9]+}`, or match multiple segments via wildcards. The syntaxes look similar yet differ in **how broadly paths match**, **captured values**, **priority when multiple handlers match**, and **error handling**.

This lesson applies to Spring MVC on the Servlet stack, focusing on Spring Framework 6.x and Spring Boot 3.x with Java 17+. By default, Spring MVC 6 uses `PathPatternParser` with parsed `PathPattern`s. For legacy applications using `AntPathMatcher` or customized path-matching configuration, re-verify behavior before copying patterns.

## 1. Objectives and Routing Model

After this lesson, you should be able to:

- Explain `@PathVariable`, named path variables, regex constraints, `?`, `*`, `**`, and `{*path}`.
- Distinguish a single path segment from multiple segments and from query strings.
- Predict which specific route is chosen when literals, variables, and wildcards all match.
- Distinguish a non-matching route (usually 404) from a matching route whose data type cannot be converted (usually 400).
- Write and test controllers using Spring Boot 3 with Java 17+.
- Identify risks around trailing slashes, URI encoding, file extensions, reverse proxies, and untrusted paths.

Logic diagram:

~~~text
GET /api/products/42?lang=vi
            |
            v
Servlet container → DispatcherServlet
                         |
                         v
              RequestMappingHandlerMapping
              match method GET + URL path
                         |
                         v
              "/api/products/{id:[0-9]+}"
                         |
                         v
             URI variable id = "42"
                         |
                         v
             Argument resolver:
             @PathVariable long id → 42L
                         |
                         v
                   Controller
                         |
                         v
                 HTTP response
~~~

The query `?lang=vi` can be read via `@RequestParam`, but **is not a path segment** for `{id}`'s regex to inspect. Beyond path, `@RequestMapping` also has method, params, headers, consumes, and produces conditions; matching the path alone is not yet enough to invoke the controller.

## 2. What Does a URL Path Consist Of?

Consider the URL:

~~~text
https://api.example.test/store/api/products/42?lang=vi#details
|______ scheme/host ____| |____ path ________| |query| fragment
~~~

Assume the web application has context path `/store` and `DispatcherServlet` is mapped to `/` by default. The controller declares `@RequestMapping("/api/products")` and `@GetMapping("/{id}")`. Spring MVC matches the `/api/products/42` route within the application scope without putting the context path into annotations.

Path segments are the parts separated by slashes:

~~~text
/api/products/42
  |     |     |
 api products 42
~~~

A single path variable `{id}` captures **one segment**; it does not automatically capture `42/reviews`. The query string `?lang=vi` is carried separately; the fragment `#details` is managed by the client and is not sent in the HTTP request-target.

Distinguishing the question mark:

- In **pattern** `/files/v?.txt`, `?` means match exactly one character within a segment.
- In **request URL** `/files/v1.txt?download=true`, `?` starts the query string.

A Spring MVC URI pattern differs from Servlet container URL mapping: a `/**` pattern in a controller is not equivalent to a servlet `/*` pattern. The container selects the web context and servlet first, and only then does Spring's `RequestMappingHandlerMapping` select a method.

## 3. URI Pattern Syntax Table in PathPatternParser

| Pattern | Meaning | Matching example | Non-matching example |
| --- | --- | --- | --- |
| `/products/list` | Fixed literal route | `/products/list` | `/products/1` |
| `/products/{id}` | One segment, captured into `id` | `/products/42` | `/products/42/reviews` |
| `/pages/t?st` | `?` matches exactly one character in a segment | `/pages/test`, `/pages/t3st` | `/pages/tst` |
| `/images/*.png` | `*` matches 0 or more characters in one segment | `/images/logo.png` | `/images/icons/logo.png` |
| `/teams/*/members` | One wildcard segment | `/teams/java/members` | `/teams/java/core/members` |
| `/assets/**` | 0 or more segments at the end of a route | `/assets`, `/assets/a/b` | `/other/a/b` |
| `/assets/{*path}` | Catch-all at end of route capturing remaining path | `/assets/a/b.png` | `/other/a/b.png` |
| `/products/{id:[0-9]+}` | One segment of one or more ASCII digits | `/products/42` | `/products/abc` |

Rules to remember:

1. `?` and `*` **do not cross slashes**; they only constrain characters within a single segment.
2. `{name}` captures one segment accessible via `@PathVariable`.
3. `**` matches multiple segments but **creates no named variable**.
4. `{*path}` also matches multiple trailing segments and **does create a variable**.
5. With `PathPatternParser`, `**` and `{*path}` are only valid at the **end of a pattern**; do not place catch-alls in the middle of a route.

### 3.1. The `?` Symbol in Patterns

Illustrative snippet inside a controller:

~~~java
@GetMapping("/files/v?.txt")
public String oneLetterVersion() {
    return "one-char-version";
}
~~~

Results:

~~~text
/files/v1.txt     MATCH
/files/vA.txt     MATCH
/files/v10.txt    NO MATCH
/files/v.txt      NO MATCH
~~~

Here `?` is a wildcard character, unrelated to query strings. If the request also has `?download=true`, the path is still `/files/v1.txt`.

### 3.2. The `*` Symbol: Wildcard Within One Segment

Pattern:

~~~java
@GetMapping("/images/*.png")
public String png() {
    return "single-level-png";
}
~~~

Matching:

~~~text
/images/cat.png          MATCH
/images/logo-small.png   MATCH
/images/icons/cat.png    NO MATCH
~~~

In `/images/icons/cat.png`, there are two segments after `/images`, so a single `*` in `*.png` does not match. If the application needs hierarchical file management, use `{*path}` or design URIs with meaningful multi-part paths; do not assume `*` "matches everything".

### 3.3. The `**` Symbol: Catch-All

The pattern `/resources/**` can match `/resources`, `/resources/logo.png`, and `/resources/images/logo.png`.

The following patterns are **invalid** when using `PathPatternParser`:

~~~text
/resources/**/logo.png
/a/**/b
/a/{*rest}/meta
~~~

Requiring catch-alls at the end lets Spring compare route specificity with less ambiguity. If you need `/reports/{year}/export`, specify the actual required segments instead of forcing `**` into the middle.

One upgrade difference: the older `AntPathMatcher` allowed some patterns with `**` in the middle, whereas `PathPatternParser` rejects them. Check any existing routes using `/**/something`.

## 4. `@PathVariable`: Extracting Data from URI Templates

A controller can declare:

~~~java
@RestController
@RequestMapping("/api/products")
class ProductController {

    @GetMapping("/{id}")
    public String byId(@PathVariable("id") long productId) {
        return "product-" + productId;
    }
}
~~~

When a client calls `GET /api/products/42`, Spring extracts URI variable `id` as the text value `"42"`, converts it to Java `long`, and invokes the method. With the example above, the response body is:

~~~text
product-42
~~~

The snippet above illustrates a controller that must reside in a Spring MVC application with configured component scanning and dependencies. `@PathVariable("id")` states the variable name explicitly. If the Java parameter name is also `id`, you can write `@PathVariable long id` when compiled with parameter-name metadata such as `-parameters`; stating the name explicitly avoids depending on compiler settings.

### 4.1. Multiple Path Variables

~~~java
@GetMapping("/users/{userId}/orders/{orderId}")
public String order(
        @PathVariable("userId") long userId,
        @PathVariable("orderId") long orderId) {
    return userId + ":" + orderId;
}
~~~

Request:

~~~text
GET /users/7/orders/81
~~~

Result:

~~~text
7:81
~~~

The two variables `userId` and `orderId` come from **two distinct segments**. If the request appends `/details` without a supporting route, the method does not automatically absorb extra segments.

### 4.2. Type Conversion and Errors Occurring After Matching

A URI variable starts as text. Spring can use its `ConversionService` along with converters/formatters to convert it to `long`, `UUID`, `Enum`, or other supported types.

Example:

~~~java
@GetMapping("/orders/{id}")
public String uuid(@PathVariable("id") java.util.UUID id) {
    return id.toString();
}
~~~

With `/orders/not-a-uuid`, the `/orders/{id}` route can still **match**, and then converting String to UUID fails. Spring MVC's default error handling typically returns `400 Bad Request`. This is a different step from a regex constraint preventing the URL from **matching in the first place**.

### 4.3. `@PathVariable` vs `@RequestParam`

~~~java
@GetMapping("/products/{id}")
public String read(
        @PathVariable("id") long id,
        @RequestParam(name = "lang", defaultValue = "vi") String lang) {
    return id + ":" + lang;
}
~~~

Request `GET /products/42?lang=en` returns:

~~~text
42:en
~~~

Variable `id` belongs to the path, while `lang` belongs to query parameters. `/products/42?lang=en` and `/products/42?lang=vi` have **the same path** when Spring matches URL patterns. A mapping can also add a `params` condition if you truly want to select handlers based on query parameters, though that is a separate condition.

## 5. Named Catch-All `{*path}`: Capturing Multiple Segments

When you need the entire remaining path:

~~~java
@GetMapping("/files/{*path}")
public String file(@PathVariable("path") String path) {
    return path;
}
~~~

For request `GET /files/manuals/java/intro.pdf`, variable `path` receives:

~~~text
/manuals/java/intro.pdf
~~~

**The captured value includes the leading slash** of the remaining path in Spring's standard behavior. Therefore, do not assume the value is `manuals/java/intro.pdf`.

| Mapping | Matches across multiple segments? | Has named variable? |
| --- | --- | --- |
| `/files/{name}` | No | Yes: `name` |
| `/files/*` | No | No |
| `/files/**` | Yes | No |
| `/files/{*path}` | Yes | Yes: `path` |

Use `{*path}` for routes that genuinely need a path tree, such as hierarchical document paths inside a storage namespace. However, **never concatenate a client-supplied path onto an OS filesystem path and open the file directly**. Validate allowed roots, canonical paths, `..` path traversal, symlinks, URL encoding, and permissions. A named catch-all is only a URL matching mechanism; it **does not guarantee data security**.

## 6. Regex Constraints: `{name:regex}`

URI templates can constrain segment format right when searching for a handler:

~~~java
@GetMapping("/products/{id:[0-9]+}")
public String product(@PathVariable("id") long id) {
    return "id=" + id;
}
~~~

Regex `[0-9]+` accepts one or more ASCII digits. Cases:

~~~text
/products/42       MATCH
/products/007      MATCH
/products/abc      NO MATCH
/products/42abc    NO MATCH
/products/42/x     NO MATCH
~~~

The regex constraint applies to the **path segment**; it does not validate JSON bodies and does not check whether a resource exists in the database.

### 6.1. Regex and Java Types Are Two Independent Steps

Compare:

~~~text
Route 1: /books/{id:[0-9]+}
         GET /books/abc
         → regex does not match → check other routes or typically 404

Route 2: /books/{id}
         Java argument: @PathVariable long id
         GET /books/abc
         → route matches → String→long conversion fails → typically 400
~~~

A very large string like `99999999999999999999999999999` still satisfies `[0-9]+` yet **does not fit in a Java `long`**. In that case argument conversion fails even though the regex matched.

Deciding whether to use regex depends on the API contract:
- If you want to route numeric IDs and text slugs to two separate handlers, constraints are useful.
- If you want one endpoint accepting all inputs and returning a specific validation error message, leaving `{id}` unconstrained and validating/converting may make more sense.
- Do not assume malformed requests should always return 400 or 404; actual status depends on which layer fails and which handlers are registered.

### 6.2. Slug Regex

~~~java
@GetMapping("/articles/{slug:[a-z][a-z0-9-]*}")
public String article(@PathVariable("slug") String slug) {
    return "slug=" + slug;
}
~~~

This pattern requires the first character to be lowercase ASCII letter, followed by lowercase letters, digits, or hyphens.

| Path | Match? | Explanation |
| --- | --- | --- |
| `/articles/spring-mvc` | Yes | Contains only allowed characters |
| `/articles/a1` | Yes | Starts with a letter |
| `/articles/1st` | No | First character is a digit |
| `/articles/SPRING` | No | Uppercase letters are outside pattern |
| `/articles/lập-trình` | No | Accented letters are outside `[a-z]` |
| `/articles/a/b` | No | Two segments after `/articles` |

The regex above is only an example for **ASCII slugs**. If Vietnamese identifiers are required, choose consistent slug/Unicode normalization and encoding rules rather than forcing all Vietnamese input through this pattern.

### 6.3. Escaping Regular Expressions in Java Strings

With Java regexes like `\d+`, because `\` sits inside a Java string literal, it must be escaped in source code as `\\d+`. Java source example:

~~~java
@GetMapping("/numbers/{id:\\d+}")
public String number(@PathVariable("id") long id) {
    return Long.toString(id);
}
~~~

If you want to avoid miscounting backslashes across Java string → URI template → Java regex layers, using `[0-9]+` in simple examples is often easier to read.

Never inject client-supplied regexes into route declarations. Routing metadata must be defined in a controlled manner at application startup; user input must never become arbitrary Java regexes at runtime to avoid ambiguity, unpredictable performance, and regex denial-of-service.

### 6.4. Caution with Complex Regexes

Spring can also extract multiple variables from a single path segment, such as artifact name, version, and extension. Syntax example per Spring docs:

~~~java
@GetMapping("/{name:[a-z-]+}-{version:[0-9]+}{ext:\\.[a-z]+}")
public String artifact(
        @PathVariable("name") String name,
        @PathVariable("version") String version,
        @PathVariable("ext") String ext) {
    return name + "|" + version + "|" + ext;
}
~~~

This is an **illustrative method inside a controller**, needing annotation imports; it is not a standalone Java program. If `name` is allowed to contain `-`, splitting components within the same segment can become confusing as real formats grow complex. Simpler URI designs like `/artifacts/{name}/versions/{version}` usually make documentation and authorization easier to read.

Use regexes to constrain **syntax**, and continue performing business validation after the controller receives arguments. A slug matching a pattern does not mean it exists or that the user is authorized to access it.

## 7. When Multiple Patterns Match: Specificity Rules

Suppose a controller declares two routes:

~~~java
@GetMapping("/products/search")
public String search() {
    return "search";
}

@GetMapping("/products/{id}")
public String byId(@PathVariable("id") String id) {
    return "id=" + id;
}
~~~

Request `GET /products/search` satisfies both `/products/search` and `/products/{id}`, yet **the more specific literal route is selected**. The order of the two methods in Java source **is not the priority rule**.

With `PathPatternParser`, Spring compares candidates using mechanisms like `PathPattern.SPECIFICITY_COMPARATOR`:
- More specific patterns with fewer wildcards/variables generally take precedence.
- Catch-alls `**` and `{*path}` rank below regular patterns that can match.
- When multiple candidates tie, pattern length/structure and other request mapping conditions are considered.
- If a winner still cannot be distinguished, the route may be deemed ambiguous, failing registration or request processing.

Never code under the assumption "whichever is declared first wins".

| Request | Patterns that can also match | Typically prioritized handler |
| --- | --- | --- |
| `GET /products/search` | `/products/search`, `/products/{id}` | Literal search |
| `GET /assets/logo.png` | `/assets/*.png`, `/assets/{*path}` | One-segment PNG |
| `GET /assets/icons/logo.png` | `/assets/{*path}` | Catch-all |
| `GET /users/42` | `/users/{id}`, `/users/{*rest}` | Single-segment variable |
| `GET /users/42/settings` | `/users/{*rest}` | Catch-all (if no more specific route exists) |

The table assumes HTTP method, headers, produces/consumes, and params conditions also match. A strong path match cannot win if the mapping rejects the request's method.

### 7.1. How Ambiguous Mappings Typically Appear

Example with two methods:

~~~java
@GetMapping("/items/{id}")
public String byId(@PathVariable("id") String id) {
    return id;
}

@GetMapping("/items/{name}")
public String byName(@PathVariable("name") String name) {
    return name;
}
~~~

Variable names `id` and `name` **are not enough to distinguish URLs**: any single segment matches both. Spring may detect equivalent mappings at startup or ambiguous handlers at request time, depending on registration/conditions. Better options:
- Separate namespaces: `/items/by-id/{id}` and `/items/by-name/{name}`.
- Or use **non-overlapping** regexes, e.g., `{id:[0-9]+}` and a slug starting with a letter.
- Or use a single endpoint `/items/{key}` and resolve key kind in business logic.

Do not add extra wildcards just to "silence ambiguous errors" if doing so makes URLs overly broad. Design the resource model first before picking syntax.

## 8. Complete Runnable Spring Boot 3 Example

Use a Spring Boot 3.x project on Java 17+ with the `spring-boot-starter-web` dependency. File `src/main/java/demo/routing/RoutingApplication.java` contains one public main class and one package-private controller in the same package for Spring Boot component scan to detect.

~~~java
package demo.routing;

import java.util.Map;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class RoutingApplication {

    public static void main(String[] args) {
        SpringApplication.run(RoutingApplication.class, args);
    }
}

@RestController
@RequestMapping("/api")
class RouteController {

    @GetMapping("/products/search")
    public Map<String, String> search() {
        return Map.of("route", "search");
    }

    @GetMapping("/products/{id:[0-9]+}")
    public Map<String, String> byId(@PathVariable("id") long id) {
        return Map.of("route", "by-id", "value", Long.toString(id));
    }

    @GetMapping("/products/{slug:[a-z][a-z0-9-]*}")
    public Map<String, String> bySlug(@PathVariable("slug") String slug) {
        return Map.of("route", "by-slug", "value", slug);
    }

    @GetMapping("/assets/*.png")
    public Map<String, String> png() {
        return Map.of("route", "one-png-segment");
    }

    @GetMapping("/assets/{*path}")
    public Map<String, String> asset(@PathVariable("path") String path) {
        return Map.of("route", "catch-all", "path", path);
    }

    @GetMapping("/reports/{year:[0-9]+}/{month:[0-9]+}")
    public Map<String, Integer> report(
            @PathVariable("year") int year,
            @PathVariable("month") int month) {
        return Map.of("year", year, "month", month);
    }
}
~~~

**Why this runs:** in a valid Spring Boot project with plugin, repositories, and dependencies, the public class `RoutingApplication` matches the file name, the controller lies in the same scanned package, `Map.of` is available since Java 9, and records are unnecessary. The JSON converter is typically Jackson bundled with the web starter. This is Spring-dependent application code, not a single file you can compile standalone with `javac` without a classpath.

In a `build.gradle` already configured with the Spring Boot plugin and repositories, required dependencies:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
}
~~~

Start on macOS/Linux:

~~~bash
./gradlew bootRun
~~~

Or Windows PowerShell:

~~~powershell
.\gradlew.bat bootRun
~~~

Assuming port 8080 and unchanged context path, call:

~~~bash
curl -i "http://localhost:8080/api/products/search"
curl -i "http://localhost:8080/api/products/42"
curl -i "http://localhost:8080/api/products/spring-mvc"
curl -i "http://localhost:8080/api/assets/logo.png"
curl -i "http://localhost:8080/api/assets/icons/logo.png"
curl -i "http://localhost:8080/api/reports/2026/10"
~~~

Expected JSON bodies, without fixing field order or response headers:

| Request | Handler | Equivalent JSON body |
| --- | --- | --- |
| `/api/products/search` | `search()` | `{"route":"search"}` |
| `/api/products/42` | `byId(42)` | `{"route":"by-id","value":"42"}` |
| `/api/products/spring-mvc` | `bySlug("spring-mvc")` | `{"route":"by-slug","value":"spring-mvc"}` |
| `/api/assets/logo.png` | `png()` | `{"route":"one-png-segment"}` |
| `/api/assets/icons/logo.png` | `asset(...)` | `{"route":"catch-all","path":"/icons/logo.png"}` |
| `/api/reports/2026/10` | `report(2026,10)` | `{"year":2026,"month":10}` |

For `/api/products/search`, the slug regex could also match because `search` is lowercase. However, the literal route is more specific and is selected.

Try requests that do not match any pattern:

~~~bash
curl -i "http://localhost:8080/api/products/Hello"
curl -i "http://localhost:8080/api/products/42/extra"
curl -i "http://localhost:8080/api/reports/2026/Oct"
~~~

If no other route matches, the result is typically 404: `Hello` matches neither the ID regex nor slug regex; `42/extra` has an extra segment; `Oct` is not digits. Actual error responses may come from Spring Boot error handling/static resource mapping or Spring Security depending on configuration.

Try an overly large numeric value:

~~~bash
curl -i "http://localhost:8080/api/products/99999999999999999999999999"
~~~

The regex `[0-9]+` accepts the digits, yet `long` cannot hold that number. Argument resolution can return 400. This shows that **regex matching does not replace type conversion**.

## 9. Testing Routes with MockMvc

In a Spring Boot project with the test dependency:

~~~groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

A test class `src/test/java/demo/routing/RoutingApplicationTests.java`, in the same package as the main application:

~~~java
package demo.routing;

import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class RoutingApplicationTests {

    @Autowired
    MockMvc mvc;

    @Test
    void literalWinsOverSlug() throws Exception {
        mvc.perform(get("/api/products/search"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.route").value("search"));
    }

    @Test
    void numberIsCapturedAndConverted() throws Exception {
        mvc.perform(get("/api/products/42"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.route").value("by-id"))
                .andExpect(jsonPath("$.value").value("42"));
    }

    @Test
    void nestedPathUsesCatchAll() throws Exception {
        mvc.perform(get("/api/assets/icons/logo.png"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.route").value("catch-all"))
                .andExpect(jsonPath("$.path").value("/icons/logo.png"));
    }
}
~~~

Run in a Gradle project with the wrapper and JUnit Platform:

~~~bash
./gradlew test
~~~

The three tests verify that the static route beats the slug route, the ID value is converted, and the catch-all captures multi-segment paths. `MockMvc` tests Spring MVC routing/responses without opening a real network port, yet **does not fully represent production proxies, Servlet containers, and URL encoding**. If security or ingress performs path rewriting, add integration tests running in a comparable environment.

## 10. Edge Cases and Version Changes

### 10.1. Trailing Slash

`/api/products/42` and `/api/products/42/` are distinct. Starting in Spring Framework 6.0, **optional trailing-slash matching is disabled by default**, unlike some earlier configurations/versions. Therefore, route `/api/products/{id}` does not automatically guarantee matching both forms.

Solutions include canonical URLs, explicit proxy/filter redirects per clear policy, or declaring additional supported paths. With POST, redirects can affect the HTTP method; choose an appropriate redirect status. Do not silently patch routes by adding overly broad catch-alls.

### 10.2. Dots, Suffixes, and Extensions

`/users/alice.json` can be captured by `/users/{name}` as a segment containing a dot. Modern Spring MVC **no longer performs `.*` suffix pattern matching automatically** by default since Spring 5.3. Use `Accept` and `produces` to negotiate JSON/XML explicitly rather than inferring from file extensions.

If a pattern explicitly declares `/images/*.png`, `.png` remains a normal part of the pattern, not a media-type guessing mechanism.

### 10.3. URL Encoding and Encoded Slashes

The sequence `%2F` represents an encoded slash. However, proxies, containers, and frameworks enforce different policies on accepting/decoding encoded slashes. `PathPatternParser` matches patterns segment-by-segment over `PathContainer` structures to avoid whole-path decoding bugs that alter structure; that **does not guarantee** every reverse proxy or Servlet container accepts encoded slashes or handles them identically.

Especially for authorization, security components and handler mappings must agree on path normalization. Test encoded slashes, double encoding, dot segments, and semicolons `;` on the actual ingress/container; do not rely solely on Spring MVC unit tests to conclude production safety.

### 10.4. Unicode, Case Sensitivity, and Slugs

Regex `[a-z]+` only permits lowercase ASCII letters. If slugs contain Vietnamese characters, emojis, or Unicode characters, decide consistently on normalization, percent-encoding, and format constraints. Path matching is normally case-sensitive unless configured otherwise.

Construct URLs using URI builders or HTTP libraries rather than concatenating unencoded raw client data into URLs. When changing slug rules, account for legacy URLs, external links, bookmarks, and redirects to avoid breaking public API contracts.

### 10.5. Semicolons and Matrix Variables

Paths can contain semicolon content, for example:

~~~text
/products/42;color=red;size=large
~~~

Spring MVC provides `@MatrixVariable` for path parameters. `PathPattern` supports parsing segments and semicolon content by design, yet containers/proxies/security layers may alter or reject such URLs. Only use matrix variables when the whole system has clear contracts and tests. Do not confuse them with query parameters like `?color=red&size=large`.

### 10.6. Context Path and Reverse Proxies

Suppose an application has `server.servlet.context-path=/store`, controller `@RequestMapping("/api")`, and `@GetMapping("/products/{id}")`; the direct URL is `/store/api/products/42`. The controller **does not write** `/store` into its mappings.

If a reverse proxy serves `/platform/store/api/products/42` yet forwards internally as `/store/api/products/42`, the `/platform` prefix belongs to the proxy. You must know whether the proxy preserves or strips prefixes when diagnosing 404s. Forwarded headers should only be trusted when coming from trusted proxies.

## 11. Common Mistakes and How to Debug

| Symptom | Possible cause | Investigation direction |
| --- | --- | --- |
| `/items/abc` returns 404 | ID regex allows digits only; route does not match | Mapping registry, regex, actual URL |
| `/items/abc` returns 400 | Route `{id}` matched, yet conversion to `long` failed | Argument resolver, exception handling |
| `/items/search` hits unexpected handler | Missing literal route or differing mapping conditions | Specificity, HTTP method, consumes/produces |
| `/files/a/b.png` fails to match `*.png` | `*` does not cross slashes | Path structure, whether `{*path}` is needed |
| App fails at startup | Catch-all in middle of pattern or ambiguous mapping | Startup logs and PathPatternParser |
| Trailing slash returns 404 | Trailing slash not matched by default | Canonical URL and route declarations |
| Fails only behind gateway | Different proxy rewrite/encoding/context path | External vs internal paths |
| Non-existent URL returns HTML 200 | Fallback/static resource catch-all matched | Selected handler, Content-Type, body |

Short investigation workflow:

1. Check the actual URL sent by the client, HTTP method, and context path.
2. Inspect registered `@RequestMapping` entries, including class prefix, method, params, and media types.
3. Determine whether the path **failed to match a pattern** or **matched yet failed argument conversion**.
4. If multiple routes are valid, check specificity/ambiguity; never infer from method order.
5. For routes with `**` or `{*path}`, check sub-paths unintentionally caught by the catch-all.
6. Inspect actual HTTP status/headers/body and handler/exception resolver logs.
7. For encoding/redirects/proxies, verify behavior end-to-end.

You can try:

~~~bash
curl -i "http://localhost:8080/api/products/42"
curl -i "http://localhost:8080/api/products/search"
curl -i "http://localhost:8080/api/assets/icons/logo.png"
~~~

If using Spring Boot Actuator and enabling the mappings endpoint with proper authorization, `/actuator/mappings` helps inspect registered handlers. Do not expose management endpoints publicly to the Internet.

## 12. Self-Check Knowledge Questions

**Question 1.** There are two routes `GET /members/latest` and `GET /members/{id}`. How is `GET /members/latest` selected?

**Question 2.** Why does `/files/*.csv` not match `/files/reports/2026.csv`? Which syntax should be used to capture the entire remainder?

**Question 3.** `/users/{id:[0-9]+}` with argument `long id`. Distinguish the typical outcomes when calling `/users/abc` vs `/users/999999999999999999999`.

**Question 4.** `/teams/{team}/members/{member}` receives request `/teams/core/members/lan`. What are the captured values?

**Question 5.** Why is `/resources/**/logo.png` invalid under `PathPatternParser`? How should it be designed?

**Question 6.** Named catch-all `/files/{*path}` receives `/files/docs/manual.pdf`; is `path` `docs/manual.pdf` or `/docs/manual.pdf`? Should the raw value be used as a filesystem path?

**Question 7.** Does regex `[a-z-]+` accept `Lập-trình`? What must be considered if Unicode is to be accepted?

### Explanatory Answers

1. Literal route `/members/latest` is more specific than variable `/members/{id}`, so it is normally prioritized.
2. `*` only spans a single segment. Use `/files/{*path}` to capture multiple segments, or `/files/**` if only matching is needed.
3. `abc` does not match the regex so it may return 404; a digits-only string exceeding `long`'s range matches the regex then fails conversion, typically returning 400.
4. `team="core"`, `member="lan"`, each variable receiving one segment.
5. `**` catch-alls must be at the end with `PathPatternParser`. Use constrained `/resources/{*path}` and verify the suffix in service logic if truly needed, or define explicit routes.
6. `path="/docs/manual.pdf"` includes the leading slash; never use it directly to open files. Validate traversal, normalization, and permissions.
7. No, the ASCII regex accepts neither uppercase nor accented characters. Design consistent slug/Unicode normalization and encoding compatible with proxies/containers.

## 13. Application Checklist

When building Spring MVC routes:

1. Prefer static URIs and single-segment `{id}` variables with clear semantics.
2. Use regex only when ID/slug formatting is part of the URL contract.
3. Remember `?` and `*` control characters **within a segment** only.
4. Place `**` or `{*path}` at the end of patterns and constrain the namespace.
5. Predict specificity where literals, variables, and wildcards intersect; avoid ambiguous routes.
6. Separate path matching from argument conversion for accurate error handling.
7. Test valid URLs, regex failures, conversion failures, multi-segment paths, and trailing slashes.
8. Test security and URL encoding against real containers/proxies when deploying publicly.

The core mindset is: **patterns decide route matching; argument resolvers turn captured data into Java values; controllers execute business logic; return-value handlers produce HTTP responses.** Understanding those boundaries helps you design accurate REST endpoints and debug 404/400 issues by their true root cause.

**Official documentation:** Spring Framework Reference, *Mapping Requests / URI Patterns / Pattern Comparison*: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-requestmapping.html ; Spring Framework Reference, *Path Matching*: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-config/path-matching.html ; Spring MVC reference on `@PathVariable` and `@RequestMapping`.