# PathPattern, Specificity Selection Rules, and Duplicate Mapping Errors in Spring MVC

## 1. Objectives and Scope

In Spring MVC, a single URL can match multiple `@GetMapping` or `@RequestMapping` annotations. The framework must check all request conditions, compare the specificity of valid mappings, and select exactly one controller method. This lesson helps you:

- Understand `PathPattern`, `PathPatternParser`, and how they match each `path segment` of a URL.
- Distinguish literal paths, `{id}` variables, `{id:...}` regexes, wildcards `?`, `*`, `**`, and remaining-path catch-all variables `{*path}`.
- Predict the winning mapping when multiple endpoints match; know when `Ambiguous mapping` happens at startup versus `Ambiguous handler methods` when receiving a request.
- Write routes without unintended overlaps, verifying them with HTTP requests and `MockMvc`.

**Scope:** annotation-based controllers in **Spring MVC (Servlet stack)**, illustrated with Spring Framework 6.x / Spring Boot 3.x and Java 17+. Since Spring MVC 6.0, parsed `PathPattern` is the default path-matching mechanism. Legacy applications may use `AntPathMatcher` due to differing configurations/versions; do not apply every conclusion about syntax and priority order verbatim to that mode.

## 2. From Request to Handler Method

Class-level and method-level `@RequestMapping` annotations combine into a complete route. For example, `@RequestMapping("/api/orders")` on a class plus `@GetMapping("/{id}")` on a method creates endpoint `GET /api/orders/{id}`.

Simplified handler-selection flow:

```text
HTTP request
  → DispatcherServlet
  → RequestMappingHandlerMapping
  → find RequestMappingInfo with matching conditions:
      path, HTTP method, params, headers, consumes, produces, ...
  → if multiple candidates: compare priority in request context
  → select best handler if unique
  → convert @PathVariable, bind parameters, invoke controller method
```

`PathPatternParser` compiles URL patterns into `PathPattern`s and compares them against the parsed request path (`RequestPath`/`PathContainer`). Processing each path segment individually avoids certain bugs caused by decoding an entire URL into one string before matching. `PathPattern` is the **URL-matching** component, whereas `RequestMappingInfo` also includes HTTP methods and other request conditions.

Two things to separate clearly:

1. **Match or no match:** one pattern may accept a given request and reject another. For instance, `/users/{id:[0-9]+}` does not match `/users/alice`.
2. **Who wins when both match:** if both `/users/current` and `/users/{id}` match `/users/current`, the literal pattern wins. Matching only answers "which candidates are valid"; specificity determines the order among them.

Java parameter names, method declaration order in a class, and controller scan order are **not** route priority rules.

## 3. Quick Review of PathPattern Syntax Before Comparing Specificity

To compare two matching patterns, first know **how many path segments each pattern accepts**. With `PathPatternParser` in Spring MVC 6.x, the essential forms are:

| Pattern | Scope and captured value |
| --- | --- |
| `/users/me` | Literal: accepts only the `me` segment. |
| `/users/{id}` | Accepts one segment, assigning the value to variable `id`. |
| `/users/{id:[0-9]+}` | One segment must satisfy the numeric regex; regex **restricts matching** and does not automatically boost priority when two patterns both match. |
| `/files/*.png`, `/files/a?.txt` | `*` and `?` match characters within **one** segment only (multiple characters and exactly one character, respectively). |
| `/assets/**` | Unnamed catch-all, accepting multiple segments at the **end** of the path. |
| `/assets/{*path}` | Named catch-all, e.g., `/assets/css/app.css` sets variable `path=/css/app.css`. |

Do not place `**` or `{*path}` in the middle of a pattern with `PathPatternParser`: `/a/**/b` is an invalid pattern. Query strings are not counted as path segments, so `?` in a request URI differs from `?` in a pattern. Also distinguish a URL **failing a regex match** from a Java conversion failure such as `@PathVariable long id` failing on a value outside `long` range.

The core focus of this lesson is not listing more wildcards, but **comparing matched candidates**, explaining why literals beat single variables, why catch-alls rank last, and detecting duplicate/indistinguishable mappings. Test trailing slashes, encoding, and reverse proxies separately on real configurations: Spring MVC 6.x by default does not merge `/users` with `/users/`, and URLs containing `%2F` or `;` may be governed by container/proxy/security policies before reaching a handler.

## 4. Comparing Specificity When Multiple Patterns Match

With parsed patterns, Spring uses `PathPattern.SPECIFICITY_COMPARATOR` to order matching patterns. The design intuition is **exact literals first, variables or wildcards next, catch-alls last**.

Core principles:

1. Catch-all patterns like `/**` and `/{*rest}` rank after non-catch-all patterns. Between catch-alls, one with a longer/more specific prefix is generally preferred.
2. For regular patterns, Spring scores complexity based on URI variables and wildcards (`{x}` variables, `*`, `?` contribute to comparison under parser rules). Patterns with a **lower score** are more specific.
3. On tied scores, a **longer** pattern is preferred; if still tied, a pattern with **more URI variables than wildcards** may win.
4. If final candidate comparison still ties for a given request, Spring **does not arbitrarily pick the earlier-declared method**: an ambiguous handler selection error occurs.

Example with request `GET /users/me`:

| Candidate | Matches? | Explanation |
| --- | --- | --- |
| `/users/me` | Yes | Exact literal match, most specific |
| `/users/{id}` | Yes | Single-segment variable, more general than literal |
| `/users/*` | Yes | Single-segment wildcard |
| `/users/**` | Yes | Trailing catch-all, lower priority |
| `/teams/{id}` | No | Different prefix |

**Result:** `/users/me` wins. Without the literal route, `/users/{id}` normally beats `/users/*` when other factors tie.

Do not build a mental resolution engine based solely on "fewer wildcards always wins" in every case. Spring evaluates the full `RequestMappingInfo`: HTTP method, `params`, `headers`, `consumes`, `produces`, and other conditions before arriving at a final precedence order. Even a great path pattern is not a candidate if the request's HTTP method or `Content-Type` does not match.

### Other Conditions Beyond Path

```java
@RestController
@RequestMapping("/reports")
class ReportController {

    @GetMapping(params = "format=csv", produces = "text/csv")
    String csv() {
        return "id,name\n1,Ada\n";
    }

    @GetMapping(params = "format=json", produces = "application/json")
    String json() {
        return "{\"id\":1,\"name\":\"Ada\"}";
    }

    @PostMapping(consumes = "application/json")
    String create(@RequestBody String payload) {
        return "accepted";
    }
}
```

*The snippet above illustrates declaring mapping conditions; place it in a Spring MVC app with the corresponding imports/bootstrapping.* Two GET methods share `/reports` yet differ in `params` and `produces`, so they are not identical mappings. For example, `GET /reports?format=csv` with `Accept: text/csv` selects `csv()`; `POST /reports` with `Content-Type: application/json` selects `create()`.

Distinguish `@GetMapping(params = "format=csv")` from `@RequestParam String format`: the `params` attribute is a **mapping selection condition**; `@RequestParam` primarily handles **binding/checking arguments after the handler is chosen**. Likewise, `@PathVariable long id` does not make a route automatically prioritize "numbers" over a route taking `String`. To reject non-digits during URL matching, use a regex in the pattern or define distinct literal paths.

If a path exists yet the HTTP method is unsupported, Spring MVC typically responds with `405 Method Not Allowed` by default. A `Content-Type` mismatch against `consumes` can yield `415 Unsupported Media Type`, an `Accept` mismatch against `produces` can yield `406 Not Acceptable`, and an unmet `params` condition can yield `400 Bad Request`. A path with no mapping typically yields `404 Not Found`. Exception handlers, security filters, and app configurations can alter observed responses.

## 5. Runnable Application Example with Java 17 and Spring Boot 3

Create a Maven project as follows (Spring Boot 3.3.13 is used here as a fixed illustrative version for Spring Framework 6.x):

```text
path-pattern-demo/
├── pom.xml
└── src/
    ├── main/java/example/PathPatternDemoApplication.java
    └── test/java/example/ProductRoutesControllerTest.java
```

File `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>path-pattern-demo</artifactId>
    <version>1.0.0</version>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
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

File `src/main/java/example/PathPatternDemoApplication.java`:

```java
package example;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class PathPatternDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(PathPatternDemoApplication.class, args);
    }
}

@RestController
@RequestMapping("/api/products")
class ProductRoutesController {

    @GetMapping("/featured")
    String featured() {
        return "featured";
    }

    @GetMapping("/{id:\\d+}")
    String byId(@PathVariable("id") long id) {
        return "id:" + id;
    }

    @GetMapping("/{slug:[a-z][a-z0-9-]*}")
    String bySlug(@PathVariable("slug") String slug) {
        return "slug:" + slug;
    }

    @GetMapping("/files/{*path}")
    String file(@PathVariable("path") String path) {
        return "file:" + path;
    }
}
```

Commands to run with **JDK 17+ and Maven** installed:

```bash
mvn test
mvn spring-boot:run
```

In another terminal, send the following requests:

```bash
curl -s http://localhost:8080/api/products/featured
curl -s http://localhost:8080/api/products/42
curl -s http://localhost:8080/api/products/blue-mug
curl -s http://localhost:8080/api/products/files/guide/intro.pdf
```

Each command returns its exact corresponding body (none adds a trailing newline on its own):

```text
featured
id:42
slug:blue-mug
file:/guide/intro.pdf
```

Explanation:

- `/api/products/featured` matches both the literal and slug patterns, yet the literal wins.
- `/api/products/42` matches only `{id:\\d+}` between the `id`/`slug` patterns; `long` binding happens after route selection.
- `/api/products/blue-mug` matches the slug pattern; it does not match the numeric expression.
- `/api/products/files/guide/intro.pdf` is captured by `{*path}` under sub-route `/files`. The slug pattern cannot absorb multiple path segments.

With the example's default configuration, `GET /api/products/42/` with a trailing slash does not match `GET /api/products/42`; `POST /api/products/42` may return `405` because only GET is declared. When testing with `curl -i`, check the HTTP status code in addition to the body to distinguish 404, 405, and mapping condition errors.

## 6. Two Very Different Kinds of Duplicate Mapping Errors

### 6.1. Immediate Startup Error: Two Handlers with Identical Mappings

The **intentionally invalid example** below is an alternative controller—do **not** add it to the running project in section 5:

```java
@RestController
@RequestMapping("/api/duplicate")
class DuplicateController {

    @GetMapping("/{id}")
    String first(@PathVariable String id) {
        return "first";
    }

    @GetMapping("/{id}")
    String second(@PathVariable String id) {
        return "second";
    }
}
```

Both methods register the exact same `RequestMappingInfo` (HTTP GET, `/api/duplicate/{id}`, no other distinguishing conditions). When building the controller registry, `RequestMappingHandlerMapping` detects the conflict and can throw an `IllegalStateException` mentioning `Ambiguous mapping`/`Cannot map ... There is already ... mapped`. The application fails to finish starting up.

How to fix: remove the duplicate endpoint, merge logic into one method, or redesign the HTTP contract so the mappings genuinely differ in path, method, or meaningful conditions. Changing the **Java method name** or `@PathVariable` parameter name while keeping the same mapping annotation does not resolve an exact duplicate.

### 6.2. Request-Time Error: Two Different Patterns with Equal Priority

**Intentionally invalid example**—also do not add to the running project:

```java
@RestController
@RequestMapping("/api/ambiguous")
class AmbiguousController {

    @GetMapping("/{id}")
    String byId(@PathVariable String id) {
        return "id:" + id;
    }

    @GetMapping("/{slug}")
    String bySlug(@PathVariable String slug) {
        return "slug:" + slug;
    }
}
```

The two pattern strings `/{id}` and `/{slug}` are not identical in variable name, so they may register as two separate mappings. However, for `GET /api/ambiguous/123`, **both match one segment**, have equal specificity, and have no distinguishing condition. Spring MVC cannot tell which method to pick, throwing an `IllegalStateException` like `Ambiguous handler methods mapped for '/api/ambiguous/123'` when the request arrives. The HTTP outcome is typically 500 without custom exception handling.

**Easy-to-miss trap:** putting `@PathVariable long id` on the first method and `@PathVariable String slug` on the second does not resolve the conflict: Java argument conversion happens only after handler selection. Adding a regex to one route does not guarantee "absolute priority" if both still match; avoid overlapping URL sets or differentiate routes explicitly.

Two sensible fixes:

```java
// Option A: differentiate URLs clearly.
@GetMapping("/by-id/{id}")
String byId(@PathVariable long id) { return "id:" + id; }

@GetMapping("/by-slug/{slug}")
String bySlug(@PathVariable String slug) { return "slug:" + slug; }

// Option B: regexes with two disjoint value sets.
@GetMapping("/{id:\\d+}")
String numericId(@PathVariable long id) { return "id:" + id; }

@GetMapping("/{slug:[a-z][a-z-]*}")
String alphabeticSlug(@PathVariable String slug) { return "slug:" + slug; }
```

*These are two alternative options to put into an appropriate controller, not four methods to declare together.*

If a slug can consist solely of digits (e.g., `"123"`), define a product rule: prefer giving IDs and slugs separate namespaces instead of letting two routes fight over one URL. Do not rely on code ordering to "patch" an ambiguous mapping.

### 6.3. Diagnostic Checklist

1. Determine whether the failure happens **during startup** or **only when calling a URL**. Startup usually indicates duplicate mappings; request-time usually indicates different patterns tied in specificity for a specific URL.
2. Record full method + path + query string + `Content-Type` + `Accept` + relevant headers. Do not inspect only the URL.
3. Open the mapping entries for both handlers in the stack trace; combine class prefix and method path to compare the final URLs.
4. Check wildcards and variables that can accept the same path—especially `/{id}` vs `/{slug}`, overlapping regexes, `*`, and catch-alls.
5. Inspect the registered mappings list (e.g., `/actuator/mappings` when Spring Boot Actuator is present and permitted) or enable appropriate logging for `RequestMappingHandlerMapping`.
6. Write tests for URLs in the overlap zone as well as URLs that should not match; fix path/condition design and re-run.

## 7. Testing Routes with MockMvc

File `src/test/java/example/ProductRoutesControllerTest.java` (matching the project in section 5):

```java
package example;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(ProductRoutesController.class)
class ProductRoutesControllerTest {

    @Autowired
    private MockMvc mvc;

    @Test
    void literalBeatsVariableAndRegexSeparatesIdsFromSlugs() throws Exception {
        mvc.perform(get("/api/products/featured"))
                .andExpect(status().isOk())
                .andExpect(content().string("featured"));

        mvc.perform(get("/api/products/42"))
                .andExpect(status().isOk())
                .andExpect(content().string("id:42"));

        mvc.perform(get("/api/products/blue-mug"))
                .andExpect(status().isOk())
                .andExpect(content().string("slug:blue-mug"));
    }

    @Test
    void catchAllOnlyAppliesUnderFilesPrefix() throws Exception {
        mvc.perform(get("/api/products/files/guide/intro.pdf"))
                .andExpect(status().isOk())
                .andExpect(content().string("file:/guide/intro.pdf"));

        mvc.perform(get("/api/products/42/"))
                .andExpect(status().isNotFound());

        mvc.perform(post("/api/products/42"))
                .andExpect(status().isMethodNotAllowed());
    }
}
```

Run `mvn test`. These assertions verify the **actual selected handler** via body content, while also checking trailing slashes and HTTP methods. In real projects, add cases for `params`, `headers`, `consumes`, `produces`, and requests capable of matching two routes.

To avoid false-green tests when an app has security, filters, servlet paths, or extra MVC configuration, combine `MockMvc` with integration tests running against the real deployment setup. If testing an intentionally ambiguous scenario, isolate the faulty controller into its own test context; never place it in the main demo app because it can prevent the context from starting.

## 8. Common Mental Traps and How to Avoid Them

| Misconception | More accurate rule |
| --- | --- |
| "Defining `@GetMapping` first makes it win." | Spring compares conditions and specificity, not source-code order as a contract. |
| "`/{id}` and `/{slug}` differ so they cannot conflict." | Two different variable names still match the exact same set of single-segment paths; requests can be ambiguous. |
| "`@PathVariable Long id` restricts the mapping to digits." | Type conversion runs after route selection; to filter paths, use regexes or separate prefixes. |
| "A narrower regex always beats a general variable." | Regex restricts **matching**; when both match, the comparator decides, rather than guessing from regex semantics. |
| "`*` matches any directory depth." | `*` stays within one segment; `**`/`{*path}` span multiple segments and must go at the end. |
| "Putting `/**` everywhere is safe." | Catch-alls easily blur routes; use only when needed and test boundary paths. |
| "`GET /a` is always identical to `GET /a/`." | Spring MVC 6.x does not automatically match optional trailing slashes by default. |
| "`@RequestParam` differentiates two `@GetMapping`s on the same path." | Use mapping condition `params=...` if you want query parameters to select the handler. |
| "Every request that misses a controller returns 404." | 405/400/406/415 or security/binding errors can appear depending on conditions and config. |

**Pragmatic design rule:** favor meaningful literal paths; assign distinct namespaces for two resource types prone to overlap; use regexes to constrain variables when value domains are truly known; avoid broad catch-alls; ensure every expected request has a unique winning handler. For systems with public APIs, verify URL compatibility before changing paths.

## 9. Self-Check

1. Given three GET mappings `/shop/new`, `/shop/{sku}`, and `/shop/**`, which does `GET /shop/new` pick? **Answer:** `/shop/new`, because the literal is more specific.
2. Does `/files/*` match `/files/icons/logo.svg`? **No**, because `*` spans only one segment.
3. If `GET /people/{id}` and `GET /people/{name}` coexist, why can `GET /people/7` fail at runtime? **Both patterns match with equal specificity**, while variable names do not distinguish values.
4. Does adding `@PathVariable Long id` fix question 3? **No**; you must change the URL contract or enforce disjoint patterns.
5. When do two methods with `@GetMapping("/sync")` and no differing conditions fail? **During mapping registration at startup**, typically with `Ambiguous mapping`.
6. Why does `POST /api/products/42` not enter the GET method even though the path matches? **HTTP method** is part of `RequestMappingInfo`; with the demo configuration Spring MVC responds with 405.

## 10. Official Reference Documentation

- [Spring Framework — Mapping Requests](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-requestmapping.html): URI patterns, selecting specific patterns, and mapping conditions.
- [Spring Framework — Servlet Path Matching](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-servlet/handlermapping-path.html): parsed `RequestPath`, `PathPatternParser`, differences from `AntPathMatcher`, and URL encoding handling.
- [PathPatternParser API (Spring 6.2)](https://docs.spring.io/spring-framework/docs/6.2.7/javadoc-api/org/springframework/web/util/pattern/PathPatternParser.html): case-sensitivity and trailing-slash defaults.
- [RequestMappingInfo API (Spring 6.2)](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/servlet/mvc/method/RequestMappingInfo.html): condition set used to identify, filter, and compare mappings.
