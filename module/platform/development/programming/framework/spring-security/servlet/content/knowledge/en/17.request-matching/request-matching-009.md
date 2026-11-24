# Testing Trailing Slashes, Encoded Paths, and MVC Alignment in Spring Security Servlet

## Lesson Objectives

In a Spring Security Servlet application, access rules are often configured by HTTP path, such as `GET /api/records/{id}`. Spring MVC also has a system for mapping URLs to controllers. These two layers must interpret **the same request compatibly**: if Spring Security considers a request part of a public path while Spring MVC interprets it as a protected path, the system can accidentally misgrant permissions. Conversely, if Security blocks a URL that MVC only treats as a non-existent resource, developers easily mistake a 403 error for a permission issue instead of a matcher mismatch.

Three special scenario groups are especially worth testing:

1. **Trailing slashes:** does `/api/records/A123` differ from `/api/records/A123/`?
2. **Encoded paths (URL encoding):** how are `%2F`, `%5C`, `%2E`, `%25`, and multi-layer encoding handled by the container, firewall, matcher, or MVC?
3. **Consistency:** are Spring Security RequestMatcher, Spring MVC HandlerMapping, servlet mappings, and reverse proxies applying the same rules?

After this lesson, you will know how to:

- Distinguish raw request URI, Servlet-container-processed path, servlet path, context path, and URI template variables.
- Explain why **default trailing-slash matching changed in Spring Framework 6** and why legacy behavior should not be copied blindly.
- Use MvcRequestMatcher with HandlerMappingIntrospector to reduce discrepancies between security matching and MVC matching.
- Understand the role of StrictHttpFirewall and why requests with dangerous encoded characters can be rejected **before** reaching the controller.
- Write a Java 17+, Spring Boot 3.x / Spring Security 6.x example with a SecurityFilterChain and controller sharing the same path pattern.
- Run MockMvc tests verifying canonical URLs, trailing `/` URLs, non-matching paths, different methods, and user permissions.
- Design real HTTP tests when inspecting container/proxy behavior toward percent encoding.
- Avoid using firewall relaxation or broad `permitAll` as a way to "fix" URL errors.

Scope: **Servlet stack** (Spring MVC, Spring Security HTTP), not WebFlux. Examples use compatible Spring Boot 3.3.x and Spring Security 6.x via dependency management. Percent-encoding behaviors can depend on the Servlet container, version, and proxy; areas without a fixed contract are explained via **security invariants** rather than asserting a single HTTP status code.

## 1. One URL Can Look Different at Different Layers

Consider a client-sent request:

~~~text
GET /shop/api/records/A%2F123?view=full HTTP/1.1
Host: example.test
~~~

If the application is deployed under context path `/shop`, each layer may see:

| Component | Relevant Info | What to Watch Out For |
| --- | --- | --- |
| Client / reverse proxy | Request target has `%2F` and query | Proxy may reject, normalize, or forward per config |
| Servlet container | Request URI, context path, servlet mapping | Container may enforce encoded-slash policy before invoking filters |
| Spring Security HttpFirewall | Firewalled/normalized request for matchers | May reject unsafe URLs before controllers ever see them |
| RequestMatcher | Does it match `/api/records/{id}`? | May use servlet path, path info, MVC matching semantics |
| Spring MVC HandlerMapping | Does a controller accept the request? | Path pattern rules and decoding affect routing |
| Controller `@PathVariable` | How is `id` bound? | Not guaranteed to match raw request target byte-for-byte |
| Authorization/service | Is caller allowed to access the real record? | Never infer permissions solely from raw URL strings |

Therefore, **never call `request.getRequestURI()` and manually `split("/")` to construct access decisions**, especially when URLs contain context paths, matrix parameters, percent encoding, or repeated slashes.

Useful concepts:

- **Request URI** typically includes the path portion presented by the Servlet API, possibly still escaped depending on method/container; distinct from the query string.
- **Context path** is the application deployment prefix, e.g., `/shop`.
- **Servlet path** and path info reflect servlet mapping, not necessarily the raw public URL.
- **URI template variable** is the value extracted by a matcher or HandlerMapping from a pattern like `/api/records/{id}`.
- **RequestMatcher** decides whether a security rule matches.
- **Controller mapping** decides which controller runs after security filters.

You cannot assume a controller having `@GetMapping("/api/records/{id}")` automatically creates an equivalent permission rule in SecurityFilterChain. Both configurations must be designed and tested together.

## 2. Trailing Slashes: `/items/42` vs. `/items/42/`

A tiny difference at the end of a URL can change the execution path:

~~~text
GET /api/records/A123      -> /api/records/{id}
GET /api/records/A123/     -> extra trailing /
GET /api/records/A123//    -> two trailing /
~~~

In many older Spring MVC applications, configurations could enable an optional trailing separator so `/users/{id}` also matched `/users/123/`. **Starting in Spring Framework 6, default path matching no longer treats trailing-slash and non-trailing-slash variants as equivalent.** Thus in Spring Boot 3.x with standard MVC settings, `/api/records/A123` normally matches `@GetMapping("/api/records/{id}")`, whereas `/api/records/A123/` does **not** match that controller.

This differs from a configuration using a wildcard or another matcher that matches both. If security rules and MVC rules interpret paths differently, two superficially similar requests can take different authorization paths.

### Policy Example

Suppose only users with role `READER` may read records:

~~~java
.requestMatchers(profileMatcher).hasRole("READER")
.anyRequest().denyAll()
~~~

`profileMatcher` is a specific matcher for `GET /api/records/{id}`.

- `GET /api/records/A123` by READER: specialized matcher matches; proceeds to MVC and returns the record if valid.
- `GET /api/records/A123/` by READER: if the MVC-style matcher **does not match** under default Boot 3 / Spring Framework 6, the request hits `denyAll`; the result is typically **403** for an authenticated user.
- `GET /api/records/A123/` in a system with `anyRequest().authenticated()`: the request may pass authorization yet MVC has no matching controller, typically yielding **404**.
- `GET /api/records/A123/` for an unauthenticated user: the same `denyAll` can trigger an entry point/challenge (e.g., HTTP Basic 401), not necessarily 403.

**Key point:** 403 does not prove MVC found a controller; 404 does not prove SecurityFilterChain matched the URL as intended. Pinpointing the root cause requires inspecting each layer.

### Should Both Forms Be Accepted?

There are three valid policies; pick one consistently:

1. **Single canonical URL:** `/api/records/A123` is valid; `/api/records/A123/` is rejected/404. This is the simplest choice for APIs with clear URL contracts.
2. **Explicitly define both mappings:** only when business rules genuinely require both forms, configure both MVC and Security for **both**, with tests verifying equivalent permissions.
3. **Redirect to canonical form:** for GET/HEAD, design controlled redirects and ensure both original and target requests are handled safely; never assume redirects on POST/PUT/DELETE preserve method, body, and CSRF identically.

Do not enable trailing-slash matching system-wide just to make one controller test pass, as it can alter route authorization for many other endpoints. When upgrading from Spring Framework 5 to 6, treat trailing slashes as a behavior change requiring tests.

## 3. Encoded Paths: `%2F` Is Not Simply a Normal `/`

URL percent-encoding represents bytes as `%HH`. Examples:

| Form | Common Meaning | Issue to Check |
| --- | --- | --- |
| `%2F` or `%2f` | `/` character | Is it rejected by container/firewall? Does it create a new segment? |
| `%5C` or `%5c` | Backslash | Is it treated as a separator at any layer? |
| `%2E` | Dot | Does it participate in dot-segment normalization? |
| `%2E%2E` | Double dot | Does it alter the path during normalization? |
| `%25` | `%` character | Is there a risk of double decoding into a new escape sequence? |
| `%20` | Space | How do matchers and validation interpret the input? |
| `%3B` | Semicolon | Do matrix/path parameters affect path matching? |
| `%3F` | `?` character | Is it treated as a path character or a query separator? |
| `%252F` | Single-encoded `%2F` | If decoded a second time, a `/` can emerge |

**There is no safe rule like "decode all URLs early and compare strings".** Containers, reverse proxies, Spring Security's firewall, and Spring MVC can enforce different policies on suspicious URLs. Some requests are rejected at the infrastructure layer before reaching AuthorizationManager; others are accepted but must be rejected by application-layer validation or authorization.

Examples:

~~~text
/api/records/part%2Fother
/api/records/part%252Fother
/api/records/part%5Cother
/api/records/%2E%2E/admin
/api/records/A%20B
/api/records/A;v=1
/api//records/A123
~~~

These requests are **test inputs**, not a list of URLs guaranteed to work or return one fixed status. Tomcat, proxies, and StrictHttpFirewall may process them before MVC receives the request.

### Why Are Encoded Slashes Sensitive?

`/` separates path segments. If the Security layer evaluates a request as a single segment containing `%2F`, while MVC or a proxy decodes it into two segments and routes to another handler, a mismatch in access decisions can arise.

Conceptual example:

~~~text
Client sends: /public/abc%2Fprivate
Layer A sees: /public/{name}       (one segment)
Layer B sees: /public/abc/private  (multiple segments)
~~~

This is a **risk model**, not a claim that the sample Spring Boot configuration below is bypassable. Spring Security and Servlet containers provide defenses, notably the default firewall. Never turn off those defenses just because a URL "looks normal" in a browser.

### Where Does Double Encoding Matter?

Suppose a client sends `%252F`. After one decode, it becomes `%2F`; after a second decode, it becomes `/`. If layers decode a different number of times, access logic and routing logic can disagree.

Practical rules:

- Never manually decode a second time on a value already bound by MVC into `@PathVariable`.
- Never construct internal downstream URLs by concatenating unvalidated path strings.
- If a business identifier contains separator characters, pass it in query/body, use URL-safe opaque IDs, or establish a system-wide canonical encoding contract.
- Test both single and double encoding against a **real HTTP port** behind the proxy, not just MockMvc.

## 4. StrictHttpFirewall Is the Guardrail for Dangerous Requests

Spring Security Servlet passes through FilterChainProxy, where HttpFirewall inspects URL patterns that could cause container/matcher discrepancies. A commonly used default implementation is **StrictHttpFirewall**, which applies conservative policies against many dangerous characters or path representations.

In standard configurations, StrictHttpFirewall **rejects** potentially ambiguous forms such as URL-encoded slashes, backslashes, semicolons/path parameters, or suspicious percent encodings. The exact condition set and error handling may vary by version/framework config.

Distinguish:

1. **Firewall rejects the request:** authorization manager and controller may never run. The response may be determined by RequestRejectedHandler or the container, with no single status guaranteed across every infrastructure.
2. **Matcher misses the rule:** the request passed the firewall but hits another rule, e.g., `anyRequest().denyAll()`.
3. **MVC has no route:** authorization allowed it through, yet DispatcherServlet finds no controller; usually 404.
4. **Controller/service rejects the identifier:** the request matched the route, yet the ID is invalid per domain rules; possibly 400 or 404.

Do not fix a `RequestRejectedException` by immediately doing:

~~~java
// DO NOT COPY INTO SAMPLE CONFIGURATION:
// firewall.setAllowUrlEncodedSlash(true);
// firewall.setAllowBackSlash(true);
// firewall.setAllowSemicolon(true);
~~~

Those lines illustrate a **risky policy change**, not a recommendation. Relaxing the firewall can re-open URLs that containers, proxies, or MVC interpret differently. If a genuine requirement forces supporting such characters, test every layer, define the route contract, and assess security implications before granting a narrow allowance.

Never use `WebSecurityCustomizer.ignoring()` to bypass the Spring Security filter chain for poorly understood URLs. Beyond authorization, skipping the chain loses firewall controls, security headers, and other application filters.

### Status Codes When Rejected by the Firewall

A `RequestRejectedException` may be translated into HTTP 400 in many modern Spring Security setups, though exact handling depends on Spring Security version, RequestRejectedHandler, and container/proxy. **Do not hardcode** "`%2F` is always 400" or "`%2F` is always 403" in test suites meant for all environments.

The critical invariant for protected resources: **an abnormal URL must never bypass authentication/authorization checks or reach an unintended sensitive controller.**

## 5. Aligning URL Matching Between Security and Spring MVC

Both Spring Security and Spring MVC work with request paths, yet they do not use identical APIs.

- **Spring MVC HandlerMapping** selects controllers using `@GetMapping`, `@RequestMapping`, PathPatternParser, and MVC settings.
- **Spring Security RequestMatcher** selects rules in `authorizeHttpRequests`. Different implementations carry different path semantics.
- **MvcRequestMatcher** uses HandlerMappingIntrospector to follow MVC's matching mechanism where appropriate.
- **StrictHttpFirewall** inspects requests before matchers/security filters run; it does not replace MVC routing.
- **Servlet containers and proxies** may reject or transform requests before Spring receives them.

To reduce drift in a Spring MVC app with Spring Security 6, you can use **MvcRequestMatcher.Builder** with HandlerMappingIntrospector and matching controller patterns/methods:

~~~java
MvcRequestMatcher.Builder mvc =
        new MvcRequestMatcher.Builder(introspector);

MvcRequestMatcher readRecord =
        mvc.pattern(HttpMethod.GET, "/api/records/{id}");
~~~

Then use the same pattern in MVC:

~~~java
@GetMapping("/api/records/{id}")
public ResponseEntity<String> read(@PathVariable String id) {
    // Process record, validate data and business permissions.
}
~~~

These two snippets are not enough to form a standalone program; full Spring Boot code is in section 7.

**MvcRequestMatcher is not a promise that all abnormal URLs are automatically aligned.** It cannot control how reverse proxies and containers process raw paths earlier, nor does it turn arbitrary path variables into safe IDs. With multiple DispatcherServlets or non-standard servlet mappings, configure `servletPath` appropriately and test the actual SecurityFilterChain.

### Why Declare the HTTP Method?

`GET /api/records/A123` and `DELETE /api/records/A123` may require different privileges. A path-only matcher without a method constraint can apply a broad read policy to state-mutating methods.

Example:

~~~java
mvc.pattern(HttpMethod.GET, "/api/records/{id}");
~~~

lets you apply role `READER` for GET. For POST/PUT/PATCH/DELETE, create dedicated policies when corresponding endpoints exist. If sharing one URL pattern across methods, ensure sensitive actions enforce proper permissions.

### Authorization Rule Order Is Critical

The following configuration carries risk:

~~~java
.authorizeHttpRequests(auth -> auth
        .requestMatchers("/api/**").permitAll()
        .requestMatchers(readRecord).hasRole("READER")
        .anyRequest().denyAll())
~~~

If `/api/**` matches first, the `READER` rule below may never be evaluated. Never assume a later, stricter rule automatically overrides an earlier rule. **Put narrower matchers first and do not open overly broad wildcards that shadow URL variants.**

## 6. Sample Application and Expected Policy

We write a small Spring MVC API:

- `GET /public/ping` is accessible without login.
- `GET /api/records/{id}` requires role `READER`.
- Other URLs/methods are rejected by `anyRequest().denyAll()`.
- Valid record IDs in the demo consist only of ASCII letters, digits, underscores, and hyphens, length 1 to 40 characters.
- For user `READER`, `GET /api/records/A123` returns 200; `GET /api/records/A123/` does not match the MVC-style rule under Boot 3.3 / Spring Framework 6 defaults and usually hits `denyAll`.
- User `VIEWER` is denied even with a valid URL.
- Anonymous callers receive a Basic authentication challenge on protected resources.
- Encoded-path inputs are tested separately because statuses can depend on infrastructure.

Diagram:

~~~text
HTTP request
    |
Servlet container (parses request target)
    |
Spring Security StrictHttpFirewall
    |
FilterChainProxy selects SecurityFilterChain
    |
HTTP Basic authentication (if header has credentials)
    |
MvcRequestMatcher(GET, "/api/records/{id}")
    |
    +-- matches -> hasRole("READER")
    |              |
    |              +-- authorized -> DispatcherServlet -> MVC @GetMapping
    |              +-- lacks permission -> 403 (authenticated)
    |
    +-- does not match -> anyRequest().denyAll()
                                  |
                                  +-- deny or challenge
~~~

The **denyAll outside known routes** policy is an educational choice to make differences obvious: if SecurityFilterChain does not match a URL, the request never reaches a controller or other resource. A real system with additional routes must add explicit rules rather than copying the sample config and wondering why other endpoints are blocked.

## 7. Java 17 + Spring Boot 3.3.x + Spring Security 6.x Example

### 7.1. Project Structure

~~~text
mvc-path-matching-lab/
  settings.gradle
  build.gradle
  gradlew / gradlew.bat (once Gradle Wrapper is generated)
  src/main/java/dev/example/pathmatching/
    PathMatchingApplication.java
    SecurityConfig.java
    RecordController.java
  src/test/java/dev/example/pathmatching/
    PathMatchingIntegrationTest.java
~~~

`settings.gradle`:

~~~groovy
rootProject.name = 'mvc-path-matching-lab'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'dev.example'
version = '0.0.1-SNAPSHOT'

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
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Place each Java file in its matching package and path. `./gradlew` requires an actual Gradle Wrapper in the project, generated from Spring Initializr or via `gradle wrapper` in a compatible Gradle environment before use.

### 7.2. Entry Point

File `src/main/java/dev/example/pathmatching/PathMatchingApplication.java`:

~~~java
package dev.example.pathmatching;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class PathMatchingApplication {

    public static void main(String[] args) {
        SpringApplication.run(PathMatchingApplication.class, args);
    }
}
~~~

### 7.3. SecurityConfig Using MvcRequestMatcher

File `src/main/java/dev/example/pathmatching/SecurityConfig.java`:

~~~java
package dev.example.pathmatching;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.servlet.util.matcher.MvcRequestMatcher;
import org.springframework.web.servlet.handler.HandlerMappingIntrospector;

@Configuration
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
                User.withUsername("reader")
                        .password(encoder.encode("local-reader-pass"))
                        .roles("READER").build(),
                User.withUsername("viewer")
                        .password(encoder.encode("local-viewer-pass"))
                        .roles("VIEWER").build());
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            HandlerMappingIntrospector introspector) throws Exception {

        MvcRequestMatcher.Builder mvc =
                new MvcRequestMatcher.Builder(introspector);

        MvcRequestMatcher publicGet =
                mvc.pattern(HttpMethod.GET, "/public/ping");

        MvcRequestMatcher recordGet =
                mvc.pattern(HttpMethod.GET, "/api/records/{id}");

        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers(publicGet).permitAll()
                        .requestMatchers(recordGet).hasRole("READER")
                        .anyRequest().denyAll())
                .httpBasic(Customizer.withDefaults())
                .formLogin(form -> form.disable())
                .build();
    }
}
~~~

Points to note:

1. Uses `MvcRequestMatcher.Builder(introspector)` so security matchers follow Spring MVC path semantics.
2. Explicitly declares GET. POST/PUT/DELETE on the same path do not implicitly receive READER access.
3. Public rule applies only to `GET /public/ping`. There is no `permitAll("/api/**")`.
4. The record rule uses `hasRole("READER")`; `User.withUsername(...).roles("READER")` creates authority `ROLE_READER`.
5. `anyRequest().denyAll()` guards unlisted paths, including many invalid URL variants.
6. `httpBasic` enables curl/MockMvc testing with demo accounts; never store real credentials in code.
7. Does not relax `StrictHttpFirewall`. Does not tweak trailing-slash matching just to "force" tests to pass.
8. Does not add a prefix-only Servlet `securityMatcher` without understanding fallback chains: the example's `SecurityFilterChain` covers requests by default.

In Spring Boot 3.x with Spring MVC, `HandlerMappingIntrospector` is supplied by the MVC configuration. In apps with multiple servlet mappings, you may need `MvcRequestMatcher.Builder.servletPath(...)` matching where DispatcherServlet handles requests; **context path and servlet path are two distinct concepts**.

### 7.4. Controller With ID Validation

File `src/main/java/dev/example/pathmatching/RecordController.java`:

~~~java
package dev.example.pathmatching;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class RecordController {

    @GetMapping("/public/ping")
    public String ping() {
        return "PUBLIC_OK";
    }

    @GetMapping("/api/records/{id}")
    public ResponseEntity<String> record(
            @PathVariable("id") String id) {

        if (!id.matches("[A-Za-z0-9_-]{1,40}")) {
            return ResponseEntity.badRequest().body("INVALID_ID");
        }

        return ResponseEntity.ok("RECORD:" + id);
    }
}
~~~

Why validate the ID again inside the controller?

- The authorization rule ensures the caller holds `ROLE_READER`; it **does not verify business ID formatting itself**.
- Allowing only ASCII alphanumeric characters, `_`, and `-` ensures the demo does not accidentally interpret `/`, `%`, dots, or control characters as a valid ID.
- This is only **input validation**, not ownership authorization. If a record belongs to a real user/tenant, the service must fetch the record and verify the caller is authorized on that record.
- If a request containing an encoded slash is rejected by the container/firewall before the controller, this regex is never reached; never treat regex validation as a replacement for the firewall.

A real application can use UUIDs for record IDs, or move complex identifiers into the body/query with consistent validation. Never try to support arbitrary characters inside a path segment just to preserve raw user input.

### 7.5. MockMvc Testing Cases With Stable Outcomes

File `src/test/java/dev/example/pathmatching/PathMatchingIntegrationTest.java`:

~~~java
package dev.example.pathmatching;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class PathMatchingIntegrationTest {

    @Autowired
    MockMvc mvc;

    @Test
    void publicEndpointIsAccessibleWithoutCredentials() throws Exception {
        mvc.perform(get("/public/ping"))
                .andExpect(status().isOk())
                .andExpect(content().string("PUBLIC_OK"));
    }

    @Test
    void readerCanUseCanonicalRoute() throws Exception {
        mvc.perform(get("/api/records/A123")
                        .with(httpBasic("reader", "local-reader-pass")))
                .andExpect(status().isOk())
                .andExpect(content().string("RECORD:A123"));
    }

    @Test
    void viewerCannotReadCanonicalRoute() throws Exception {
        mvc.perform(get("/api/records/A123")
                        .with(httpBasic("viewer", "local-viewer-pass")))
                .andExpect(status().isForbidden());
    }

    @Test
    void unauthenticatedCanonicalRouteChallengesForBasicAuth()
            throws Exception {
        mvc.perform(get("/api/records/A123"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void trailingSlashDoesNotMatchMvcPatternInDefaultConfig()
            throws Exception {
        mvc.perform(get("/api/records/A123/")
                        .with(httpBasic("reader", "local-reader-pass")))
                .andExpect(status().isForbidden());
    }

    @Test
    void extraSegmentDoesNotBypassSecurityRule() throws Exception {
        mvc.perform(get("/api/records/A123/extra")
                        .with(httpBasic("reader", "local-reader-pass")))
                .andExpect(status().isForbidden());
    }

    @Test
    void queryParameterDoesNotChangeThePathVariable() throws Exception {
        mvc.perform(get("/api/records/A123")
                        .queryParam("id", "B999")
                        .with(httpBasic("reader", "local-reader-pass")))
                .andExpect(status().isOk())
                .andExpect(content().string("RECORD:A123"));
    }

    @Test
    void differentHttpMethodIsNotAllowedByGetRule() throws Exception {
        mvc.perform(post("/api/records/A123")
                        .with(httpBasic("reader", "local-reader-pass")))
                .andExpect(status().isForbidden());
    }

    @Test
    void malformedBusinessIdentifierIsRejectedIfRouteMatches()
            throws Exception {
        mvc.perform(get("/api/records/A.123")
                        .with(httpBasic("reader", "local-reader-pass")))
                .andExpect(status().isBadRequest())
                .andExpect(content().string("INVALID_ID"));
    }
}
~~~

Run tests:

~~~bash
./gradlew test
~~~

This command requires the Gradle Wrapper in the project. On Windows PowerShell, you can use `.\gradlew.bat test`.

**Why does the trailing-slash test expect 403 instead of 404?** With the sample config's default MVC-style matcher, `GET /api/records/A123/` does not match `recordGet`. The remaining rule is `anyRequest().denyAll()`, so a user authenticated via HTTP Basic is denied inside Spring Security before the request reaches MVC. If you changed the config to `anyRequest().authenticated()`, a request from `reader` would pass HTTP authorization and get 404 from MVC because no controller matches. Those are **two different policies**, not a 403/404 framework bug.

**Why might the POST test need adjustment if the security chain adds CSRF checks?** In the sample config, POST is an unsafe method and default `CsrfFilter` can reject before `AuthorizationFilter`; either way the status is 403. The test only proves the request is disallowed, not that it specifically reached `denyAll`. To diagnose the method matcher in isolation, send a valid CSRF token in the test and verify authorization still denies it.

**Note on encoded URLs:** MockMvc is not a full Servlet container behind a reverse proxy. Never use a single MockMvc status to conclude Tomcat, Nginx, or cloud ingress will handle `%2F`/`%252F` identically.

### 7.6. Running the App and Testing URLs

After building the project:

~~~bash
./gradlew bootRun
~~~

In another terminal, send a few local requests:

~~~bash
curl -i http://localhost:8080/public/ping

curl -i -u reader:local-reader-pass \
  http://localhost:8080/api/records/A123

curl -i -u reader:local-reader-pass \
  http://localhost:8080/api/records/A123/

curl -i -u viewer:local-viewer-pass \
  http://localhost:8080/api/records/A123
~~~

On Windows, multiline commands with backslashes above are for Bash; you can enter each curl command on one line in an appropriate terminal. In PowerShell, you sometimes need `curl.exe` to avoid the alias for `Invoke-WebRequest`.

Expectations for the sample config:

| Request | Typical Result |
| --- | --- |
| `GET /public/ping` without credentials | 200, `PUBLIC_OK` |
| `GET /api/records/A123` as reader | 200, `RECORD:A123` |
| `GET /api/records/A123/` as reader | 403 via `denyAll` |
| `GET /api/records/A123` as viewer | 403 |
| `GET /api/records/A123` without credentials | 401 and Basic challenge |
| `GET /api/records/A.123` as reader | 400, `INVALID_ID` |
| `GET /api/records/A123/extra` as reader | 403 via `denyAll` |

The table lists stable cases in the demo project with Boot 3.3.x defaults. Response headers and error bodies may vary by version/web container. Never send real passwords in terminal history or documentation. HTTP Basic must only be used over HTTPS when carrying real data; Base64 in the `Authorization` header **is not security encryption**.

## 8. Testing Encoded Paths With a Real HTTP Stack Instead of Guessing Statuses

To test encoded slashes/double encoding, start the app with `bootRun` and send requests against a **real HTTP port**. If using curl, pass `--path-as-is` to prevent client-side URL transformations of dots/slashes; however, curl flags do not control how the server or proxy handles them.

~~~bash
curl --path-as-is -i -u reader:local-reader-pass \
  'http://localhost:8080/api/records/A%2FB'

curl --path-as-is -i -u reader:local-reader-pass \
  'http://localhost:8080/api/records/A%252FB'

curl --path-as-is -i -u reader:local-reader-pass \
  'http://localhost:8080/api/records/A%5CB'

curl --path-as-is -i -u reader:local-reader-pass \
  'http://localhost:8080/api/records/A;v=1'

curl --path-as-is -i -u reader:local-reader-pass \
  'http://localhost:8080/api//records/A123'
~~~

**Do not copy an assumed status into a checklist.** Record the actual result for each request on the target infrastructure: sent URL, status, `Location` header if any, which endpoint/controller actually ran, and which security rule matched. You may see 400, 403, or 404 depending on which layer rejected it. If a variant reaches the controller, the example's ID validation also rejects many invalid characters.

Invariant to preserve: abnormal requests must never silently bypass permissions or reach another sensitive endpoint due to cross-layer decoding differences. Some encodings may be valid for other URLs, but only when intentionally allowed by the product and tested across matchers, ID data, and policies.

### Testing Behind a Reverse Proxy

If production uses Ingress/Nginx/Apache/API gateway:

1. Test directly against the backend Servlet in a controlled environment to observe container and Spring Security behavior.
2. Test through the exact public domain/proxy to see which requests are rewritten, 301/308 redirected, or rejected.
3. Capture the client-side raw request target when possible, the URL forwarded to the backend, and the final handler.
4. Test trailing slashes, double slashes, encoded slashes, encoded percents, dot segments, matrix parameters, and Unicode as needed.
5. Never log credentials, session cookies, access tokens, or `Authorization` headers during investigation.
6. Verify no proxy rule bypasses authentication on one path while forwarding to a different protected path.

Crucial: if a proxy redirects `/api/records/A123/` to `/api/records/A123`, the **target** request must still pass through SecurityFilterChain normally. Never treat canonical redirects as a substitute for authorization.

## 9. Canonical URLs: Redirect or Reject?

An API should have a clear **canonical URL rule**.

Example:

~~~text
Canonical: /api/records/A123
Non-canonical: /api/records/A123/
~~~

If product requirements demand accepting both as one resource, one option is redirecting trailing-slash URLs to the canonical URL. Consider carefully:

- **GET/HEAD:** redirects usually work, though caching, relative URLs, and query strings must be handled properly.
- **POST/PUT/PATCH/DELETE:** 301/302 historically caused clients to change method/body; 307/308 preserve method in modern HTTP semantics, yet still require testing CSRF, idempotency, and authorization.
- **Sessions/Cookies:** redirects across hosts/schemes can alter cookie scope/SameSite and drop sessions or leak data if downgrading from HTTPS to HTTP.
- **Open redirects:** never construct `Location` directly from unvalidated URL input.
- **Authorization before/after redirect:** never let a public route act as an alias bypassing an auth-required route.
- **Proxy/CDN caches:** cache keys and redirects must align with private-data policies.
- **Client/API contracts:** changing canonical URLs is a behavioral change that can affect SDKs/mobile apps.

For security-sensitive APIs, a policy that **rejects non-canonical URLs** with a clear contract is usually simpler than building complex redirects. If you do use redirects, run end-to-end tests proving the final route enforces the same permissions.

## 10. Aligning Trailing Slashes and Matchers in Multi-Route Applications

Large apps often have public and private routes near each other:

~~~text
GET /public/info             public
GET /api/records/{id}        READER only
POST /api/records            EDITOR only
GET /api/records/{id}/audit  AUDITOR only
~~~

A rule like `/api/**.authenticated()` only verifies login; it does not enforce READER/EDITOR/AUDITOR. For routes with differing permissions, declare narrow rules with specific HTTP methods:

~~~java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers(mvc.pattern(HttpMethod.GET,
            "/public/info")).permitAll()
    .requestMatchers(mvc.pattern(HttpMethod.GET,
            "/api/records/{id}/audit")).hasRole("AUDITOR")
    .requestMatchers(mvc.pattern(HttpMethod.GET,
            "/api/records/{id}")).hasRole("READER")
    .requestMatchers(mvc.pattern(HttpMethod.POST,
            "/api/records")).hasRole("EDITOR")
    .anyRequest().denyAll());
~~~

This is a policy snippet for a larger app, **not** code to add directly to the demo project which only defines READER. Every new route needs tests for canonical URLs, trailing slashes, other methods, other roles, and ID validation. Put specialized matchers first whenever overlap is possible.

If the app uses multiple SecurityFilterChains with `@Order` and `securityMatcher`, inspect which chain matches the request first. A rule inside the `/api/**` chain has no effect on a request entering another web chain or matching no chain. **MVC ↔ Security alignment must hold at both chain selection and authorization matching.**

## 11. Context Path, DispatcherServlet Mapping, and servletPath

Two easily confused prefixes:

- **Context path**, e.g., `server.servlet.context-path=/shop`, is the web app's deployment root path.
- **Servlet mapping**, e.g., DispatcherServlet mapped at `/app/*`, creates `servletPath` distinct from context path and `pathInfo`.

If the app deploys at `/shop`, the public URL may be `/shop/api/records/A123`, yet MVC `@GetMapping` still typically declares `/api/records/{id}` relative to mapping/context. Do not add `/shop` to every `requestMatchers` just because the browser displays `/shop`.

For a DispatcherServlet not using the default mapping, `MvcRequestMatcher.Builder` provides `servletPath(...)` to specify the servlet path when needed:

~~~java
MvcRequestMatcher.Builder mvc =
    new MvcRequestMatcher.Builder(introspector)
        .servletPath("/app");
~~~

This configuration is **conditional**, used only when your DispatcherServlet is genuinely mapped to match servletPath `/app`. Do not add it to the default demo project. In apps with multiple Servlets, MVC-based security matchers must not be blindly applied to URLs handled by another servlet.

Verify:

1. Actual app context path;
2. Servlet mapping and `servletPath`/`pathInfo`;
3. Proxy-forwarded URL, scheme/host/path;
4. `HandlerMappingIntrospector` belonging to the right `ApplicationContext`;
5. Which chain `FilterChainProxy` selects;
6. Whether `RequestMatcher` matches;
7. Which controller MVC selects.

## 12. Diagnosing Differences Among 400, 401, 403, and 404

| Status | Common Cause | What Not to Assume |
| --- | --- | --- |
| 400 | Container/firewall/input validation rejected the path | Not necessarily from AuthorizationManager |
| 401 | Unauthenticated, HTTP Basic entry point challenge | Does not mean the route reached a controller |
| 403 | Authenticated but lacks permission, `denyAll`, or CSRF/firewall handler | Does not prove MVC has a route |
| 404 | Request reached MVC but no handler/resource exists | Does not prove the URL intentionally passed all security rules |
| 301/302/307/308 | Redirect/canonicalization/security entry point | Check `Location` and HTTP method on the next request |

Because status codes alone do not tell the whole path story, use bounded logging in development:

~~~properties
logging.level.org.springframework.security=DEBUG
logging.level.org.springframework.web.servlet.mvc.method.annotation.RequestMappingHandlerMapping=TRACE
~~~

Never leave full Spring Security TRACE enabled in production or log URLs containing tokens/credentials. Exact log classes/methods can change across versions; do not rely on fixed log text.

To isolate issues:

1. Verify HTTP method, raw URL, and query are right.
2. Determine whether the request reached the Servlet container or was rejected by a proxy.
3. Look for signs of `StrictHttpFirewall` / `RequestRejectedException`.
4. Identify the selected `SecurityFilterChain`, caller's `Authentication`, and `RequestMatcher` match.
5. Check authorization decisions, role/authority mappings, and `anyRequest` fallback.
6. If the request passed Security, check whether `HandlerMapping` picked the expected controller.
7. If the controller ran, check how `@PathVariable` was bound and validated.
8. Finally, verify permissions on the actual record in the service/repository.

Never debug by disabling all security or adding a broad `permitAll("/**")` in environments containing sensitive data.

## 13. Data-Level Security Remains Mandatory

A request matching `GET /api/records/{id}` from a caller with `ROLE_READER` does **not** prove they are allowed to read **every record**.

In a multi-tenant application, compare the loaded record's tenant/owner against the caller's verified identity. Service-layer pseudocode example:

~~~java
public RecordDto readRecord(String id, AuthenticatedUser caller) {
    Record record = repository.findById(id)
            .orElseThrow(NotFoundException::new);

    if (!record.getTenantId().equals(caller.getTenantId())) {
        throw new AccessDeniedException("Access denied");
    }
    return mapper.toDto(record);
}
~~~

Classes `Record`, `AuthenticatedUser`, `repository`, `NotFoundException`, and `mapper` in this snippet **only illustrate business logic**, not a standalone Java program. The rule to preserve is that **a client-chosen ID in the URL never establishes ownership**. Use a trusted principal/tenant ID, scoped queries, and appropriate transactions for sensitive data.

URL-matching techniques in this lesson protect the HTTP entry point. When services can also be invoked by message consumers, batch jobs, or internal methods, consider method/service-level authorization independent of HTTP `RequestMatcher`s to prevent IDOR/BOLA.

## 14. Regression Testing Checklist When Upgrading Frameworks

Especially when upgrading Spring Framework 5 to 6 or changing MVC/path matching:

1. **List critical endpoints** and each endpoint's canonical URL.
2. **Verify trailing slashes:** should `/route` and `/route/` behave identically per contract?
3. **Constrain HTTP methods:** GET, POST, PUT, PATCH, DELETE have proper dedicated rules.
4. **Test anonymous/roles:** owner, admin, other users; never test only valid credentials.
5. **Test encoded slash/backslash/percent/dot:** requests are rejected or handled safely; no bypasses.
6. **Test double encoding** like `%252F` through an environment with a real proxy.
7. **Test multiple slashes `//`**, semicolons, Unicode, and control characters if the product accepts such inputs.
8. **Ensure StrictHttpFirewall is active** and change policy only with documented justification and security review.
9. **Align MVC + security matchers**, using MvcRequestMatcher/HandlerMappingIntrospector matching the Servlet mapping.
10. **Avoid overly broad wildcards**, and never place `permitAll` ahead of protective rules.
11. **Test `denyAll` fallback** for undefined routes; if choosing an `authenticated` fallback, understand when MVC returns 404.
12. **Test through reverse proxy/CDN:** does the forwarded URL match expectations? Do canonical redirects preserve auth?
13. **Check context path, servletPath**, and selection among multiple SecurityFilterChains.
14. **Never skip validation/business authorization** even after a request passes HTTP authorization.
15. **Track version changes:** defaults in MVC, Servlet containers, and Spring Security can shift; keep tests as a contract.

A test suite containing only `GET /route` with an authorized user is insufficient. Regressions typically hide in **URL variants** or **mismatches between processing layers**, not in the standard case.

## 15. Self-Practice Scenarios

**Q1.** `GET /api/records/A123` matches the controller, while `GET /api/records/A123/` does not match in Spring Framework 6. Is the second request guaranteed to return 404?

**Answer:** No. If `SecurityFilterChain` has `anyRequest().denyAll()`, the request may be denied with 403 before MVC. 404 occurs only if it reaches MVC without a handler.

**Q2.** Why can `%2F` not always be treated like a regular `/`?

**Answer:** Containers, firewalls, proxies, and MVC may reject or decode it differently. Differences at segment boundaries can cause security matchers and controllers to interpret the URL differently.

**Q3.** Does MvcRequestMatcher solve all URL encoding risks?

**Answer:** No. It aligns matching with MVC semantics, yet containers/proxies/firewalls still enforce their own policies; input validation and data-level authorization remain necessary.

**Q4.** What happens if `permitAll("/api/**")` is placed before a rule with `hasRole("READER")`?

**Answer:** The broad rule matches first and can open endpoints meant to require `READER`. Place narrow rules first and do not expose wildcards beyond intent.

**Q5.** Does `POST /api/records/A123` with role `READER` inherit permissions from the GET rule?

**Answer:** No, if the matcher constrains `HttpMethod.GET`. POST may be blocked by CSRF or the authorization fallback.

**Q6.** Why cannot MockMvc tests replace testing `%2F` against a real port?

**Answer:** MockMvc does not run a full Servlet container and reverse proxy; those layers can reject or normalize URLs before Spring Security.

**Q7.** If a path has two consecutive slashes, should you manually run `String.replace("//", "/")` inside AuthorizationManager?

**Answer:** No. Ad-hoc normalization inside Security can diverge from MVC/proxies; prefer rejecting abnormal URLs or using canonicalization designed and tested end-to-end.

**Q8.** When an app deploys under `/shop`, must `@GetMapping` patterns include `/shop`?

**Answer:** Usually no: context path is the deployment scope, while MVC mappings are declared relative to the application/servlet mapping. Test carefully if custom `servletPath` or proxy rewrites exist.

**Q9.** When `reader` is allowed `GET /api/records/{id}`, does that user have permission to read every ID in the database?

**Answer:** Not automatically. Role rules only guard the HTTP layer. Services still must verify real owner/tenant/permission on the record.

**Q10.** An encoded-path request gets 400. Does that prove the role rule denied the right user?

**Answer:** No. The request may have been rejected by the Servlet container / `StrictHttpFirewall` before authorization. To verify rules, use URLs accepted by the framework and trace the execution path.

## Conclusion

**Paths are more than plain character strings:** trailing slashes, percent encoding, context paths, servlet mappings, and reverse proxies can all affect how a request is interpreted across layers. In Spring Security Servlet, use matchers whose semantics align with Spring MVC, prefer **MvcRequestMatcher + HandlerMappingIntrospector** in MVC apps where appropriate, keep `StrictHttpFirewall` active, and maintain deny-by-default rules for undeclared paths.

When upgrading to Spring Framework 6, explicitly test **`/route` and `/route/`**; for encoded slashes or double encoding, test through a real HTTP stack without guessing a single status code. A secure system is one where **valid requests are allowed for the right users, variant requests do not bypass policies, and MVC/services still validate real data**.