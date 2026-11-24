# Reading Startup Logs to Understand Configuration and Generated Filter Chains

## 1. Why Are Startup Logs Important in Spring Security?

In Spring Security, simply seeing a Java configuration snippet such as `.httpBasic(...)`, `.formLogin(...)`, or `.authorizeHttpRequests(...)` is **not enough** to know which filters a request will ultimately pass through. Each `SecurityFilterChain` is built from multiple configurations, matchers, ordering, and framework defaults. Each chain can apply to a different set of URLs.

When a Spring Boot application starts up, Spring Security can log DEBUG lines describing the `SecurityFilterChain` instances that were created, such as lines starting with:

```text
DefaultSecurityFilterChain : Will secure ... with [...]
```

This line serves as **startup configuration evidence**: it tells you that the security chain was built, which `RequestMatcher` it uses, and the ordered list of `Filter` instances placed in the chain. When you encounter a 401, 403, a redirect to the wrong login page, or a custom filter that does not run, this is one of the first places to check.

The learning goal is to answer five questions:

1. How many `SecurityFilterChain` instances were created for the Servlet application?
2. Which **scope matcher** does each chain have, for example `/api/**` or any request?
3. Which filters are inside each chain, especially for authentication, CSRF, and authorization?
4. When a URL is called, **which chain is actually selected**, and which filters are invoked?
5. Which information **cannot be concluded from startup logs alone** and requires inspecting the configuration or sending test requests?

**Scope:** the primary examples use **Java 17+, Spring Boot 3.x / Spring Security 6.x, Spring MVC on Servlet**. In Spring Boot 4.x / Spring Security 7.x, filter names, sets, or log formatting may differ. For reactive WebFlux, the chain is `SecurityWebFilterChain` composed of `WebFilter` instances; do not use the Servlet filter list in this guide to reason directly about the reactive stack.

## 2. Architectural Picture Before Reading Logs

Servlet-based Spring Security typically sits between the Servlet container and `DispatcherServlet`.

```text
HTTP client
   |
   v
Servlet container / Servlet FilterChain
   |
   v
DelegatingFilterProxy ("springSecurityFilterChain")
   |
   v
FilterChainProxy
   |---- SecurityFilterChain #1: matcher /api/**
   |        [security Filter A, security Filter B, ...]
   |
   |---- SecurityFilterChain #2: matcher any request
            [security Filter C, security Filter D, ...]
   |
   v
DispatcherServlet -> Controller -> Service
```

The different roles to recognize:

| Component | Role | When Reading Logs |
| --- | --- | --- |
| `DelegatingFilterProxy` | Bridge from the Servlet container filter to the Spring Bean `springSecurityFilterChain` | Not every DEBUG line about a filter represents a filter registered independently by the container |
| `FilterChainProxy` | Manages and selects the `SecurityFilterChain` for each request | `Securing GET /...` lines or TRACE logs for invoking individual filters during a request |
| `SecurityFilterChain` | Holds a scope matcher and a list of security filters | `DefaultSecurityFilterChain` DEBUG lines when the chain is created |
| `RequestMatcher` | Checks whether a request falls within a chain's scope | The first matching chain is used |
| `HttpSecurity` | Java DSL used to build `SecurityFilterChain` instances in Servlet | Calls like `.formLogin` / `.httpBasic` / `.csrf` result in different filters |
| `AuthorizationFilter` | Checks authorization decisions for the request | Its presence shows an authorization filter exists, **not all role rules** |
| `ExceptionTranslationFilter` | Translates many authentication/authorization exceptions to an entry point or access-denied handler | Can explain why a security failure becomes 401/403/redirect |
| `SecurityContextHolderFilter` | Manages the security context for the request in the configured pipeline | Not proof that the caller is authenticated |

An application can have **multiple** `SecurityFilterChain` instances inside the same `FilterChainProxy`. Chains are tried in order; **the first chain whose matcher matches handles the request**. Chains do not automatically "run sequentially" just because multiple beans exist.

### Two Types of Ordering Not to Confuse

- **Order between SecurityFilterChain instances:** determined by `@Order` and bean precedence. It affects which chain is selected for a URL.
- **Order of filters within a single SecurityFilterChain:** positioned by Spring Security and how custom filters are added. It affects when the security context is restored, CSRF is checked, authentication runs, and authorization is enforced.

`@Order(1)` on a `SecurityFilterChain` bean does **not** mean the first filter in that chain also has order 1. Likewise, seeing `AuthorizationFilter` at the end of the list does not allow concluding that all controllers are guaranteed to be properly protected.

## 3. Enabling the Right Log Level at Startup

### 3.1. Simple Approach: DEBUG for Spring Security

In `src/main/resources/application.properties` of a Spring Boot project:

```properties
logging.level.org.springframework.security=DEBUG
```

Restart the application. Setting `DEBUG` for this package typically displays the `DefaultSecurityFilterChain` construction lines as well as some request-processing logs. This is the intentional approach when you want to see which security configuration was actually created.

If you only want to narrow logging to printing filter chains at startup, you can use:

```properties
logging.level.org.springframework.security.web.DefaultSecurityFilterChain=DEBUG
```

The second line only enables the logger for the filter chain builder class; it is **not equivalent** to enabling DEBUG for all of `org.springframework.security`. If another logging file has suppression rules or appender configuration, inspect the logging system as well.

### 3.2. Getting Deeper Logs Per Request: TRACE

When you need to see each filter invoked for a Servlet request:

```properties
logging.level.org.springframework.security.web.FilterChainProxy=TRACE
```

Or for broader investigation in a **development/test** environment:

```properties
logging.level.org.springframework.security=TRACE
```

At TRACE, log volume increases rapidly and may include path, principal, header, or security context details depending on configuration/version. **Do not leave broad DEBUG/TRACE enabled long-term in production** without evaluating data controls, log access permissions, retention, and operational cost. Never write passwords, access tokens, cookies, session IDs, or sensitive request bodies to logs using a custom filter to make debugging "easier."

### 3.3. Why Spring Boot's `--debug` May Not Be Enough

The command:

```bash
./gradlew bootRun --args='--debug'
```

enables Spring Boot's **debug mode**, which focuses on selected core loggers and can print the **Condition Evaluation Report**. This is not a guarantee that DEBUG is enabled for **every** logger in `org.springframework.security`. To inspect the filter list, configure the `DefaultSecurityFilterChain` or `org.springframework.security` logger explicitly. The condition report answers "why auto-configuration was or was not applied," which differs from "which security filter chains were created."

You can enable logging via application arguments instead of editing a file:

```bash
./gradlew bootRun --args='--logging.level.org.springframework.security=DEBUG'
```

For a packaged application:

```bash
java -jar build/libs/security-chain-lab.jar \
  --logging.level.org.springframework.security=DEBUG
```

The JAR name here is an **example artifact name** and depends on your project's build configuration. To run a project freshly generated with Gradle Wrapper, `./gradlew bootRun` is the simplest way.

## 4. Complete Example: Creating Two Security Chains with Different Scopes

We will create a Spring Boot application with:

- `/api/**`: uses **HTTP Basic**, `GET /api/ping` is public, `GET /api/admin` requires role `ADMIN`. No form login in the API chain.
- The rest of the web app: uses **form login**, `GET /web/public` is public, `GET /web/admin` requires role `ADMIN`, and all other URLs require authentication.
- Two in-memory accounts for testing the flows: `reader` with role USER and `admin` with role ADMIN.

The key thing to observe is **the difference in the filter lists at application startup**, rather than building a complex web application.

### 4.1. Initializing the Project

Create a project using Spring Initializr with **Java 17+**, **Spring Boot 3.x**, dependencies **Spring Web** and **Spring Security**, and Gradle selected.

Java file location:

```text
src/main/java/demo/filterlogs/SecurityChainLogApplication.java
```

All the code below lives in **a single Java file**; compile/run it inside a project with Spring Boot 3.x/Security 6.x dependencies. It cannot be compiled with standalone `javac` without the Spring classpath.

```java
package demo.filterlogs;

import java.util.Map;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.core.annotation.Order;
import org.springframework.http.MediaType;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.savedrequest.NullRequestCache;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class SecurityChainLogApplication {

    public static void main(String[] args) {
        SpringApplication.run(SecurityChainLogApplication.class, args);
    }

    @Bean
    @Order(1)
    SecurityFilterChain apiChain(HttpSecurity http)
            throws Exception {
        http
            .securityMatcher("/api/**")
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/ping").permitAll()
                .requestMatchers("/api/admin").hasRole("ADMIN")
                .anyRequest().authenticated()
            )
            .httpBasic(Customizer.withDefaults())
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS)
            )
            .requestCache(cache ->
                cache.requestCache(new NullRequestCache())
            );

        return http.build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain webChain(HttpSecurity http)
            throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(
                    "/web/public", "/login", "/error"
                ).permitAll()
                .requestMatchers("/web/admin").hasRole("ADMIN")
                .anyRequest().authenticated()
            )
            .formLogin(Customizer.withDefaults());

        return http.build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
            User.withUsername("reader")
                .password(encoder.encode("reader123"))
                .roles("USER")
                .build(),
            User.withUsername("admin")
                .password(encoder.encode("admin123"))
                .roles("ADMIN")
                .build()
        );
    }

    @RestController
    public static class DemoEndpoints {

        @GetMapping("/api/ping")
        public Map<String, String> ping() {
            return Map.of("status", "ok");
        }

        @GetMapping("/api/admin")
        public Map<String, String> apiAdmin() {
            return Map.of("message", "api-admin-ok");
        }

        @GetMapping(
            value = "/web/public",
            produces = MediaType.TEXT_HTML_VALUE
        )
        public String webPublic() {
            return "<!doctype html><html><meta charset=\"UTF-8\">"
                + "<body><h1>Trang cong khai</h1></body></html>";
        }

        @GetMapping(
            value = "/web/admin",
            produces = MediaType.TEXT_HTML_VALUE
        )
        public String webAdmin() {
            return "<!doctype html><html><meta charset=\"UTF-8\">"
                + "<body><h1>Trang quan tri</h1></body></html>";
        }
    }
}
```

**Explanation of key choices:**

1. `@Order(1)` places the API chain first. `securityMatcher("/api/**")` scopes **the entire chain**, not just a single authorization rule.
2. `@Order(2)` places the web chain second. The web chain does not declare `securityMatcher(...)`, so its default matcher is **any request not already matched by an earlier chain**.
3. `requestMatchers(...)` **inside `authorizeHttpRequests(...)`** selects authorization rules after the chain has been chosen. It does **not** cause `FilterChainProxy` to create another independent chain.
4. `httpBasic(...)` on the API adds the Basic authentication mechanism; `formLogin(...)` on the web chain adds the form login mechanism. Therefore, the filter logs of the two chains show distinct signatures.
5. `SessionCreationPolicy.STATELESS` and `NullRequestCache` keep the API example from relying on HTTP session/request cache; this does **not automatically disable CSRF**. All API checks here are GET requests.
6. `hasRole("ADMIN")` by default convention requires the `ROLE_ADMIN` authority, whereas `reader` only has `ROLE_USER`.
7. `PasswordEncoderFactories.createDelegatingPasswordEncoder()` encodes passwords properly for the example configuration. These accounts are for `localhost` only. Over a real network, HTTP Basic must go over HTTPS because Base64 does not encrypt credentials.

### 4.2. Enabling Logging and Starting Up

In `src/main/resources/application.properties`, add:

```properties
spring.application.name=security-chain-lab
logging.level.org.springframework.security=DEBUG
```

Start from the project directory:

```bash
./gradlew bootRun
# On Windows PowerShell:
# .\gradlew.bat bootRun
```

A Spring Initializr project may use Maven instead of Gradle; in that case, use the corresponding wrapper. Do not run `javac SecurityChainLogApplication.java` without putting all Spring dependencies on the classpath.

After startup, search the console for the `DefaultSecurityFilterChain` logger or the phrase **`Will secure`**. You should see **two filter chain configuration messages**, one for `/api/**` and one for the default matcher.

### 4.3. Reading Sample Logs for Two Chains

The Spring Security documentation illustrates a DEBUG line from `org.springframework.security.web.DefaultSecurityFilterChain` with this structure:

```text
DEBUG o.s.s.web.DefaultSecurityFilterChain :
Will secure any request with [DisableEncodeUrlFilter, WebAsyncManagerIntegrationFilter, SecurityContextHolderFilter, HeaderWriterFilter, CsrfFilter, LogoutFilter, UsernamePasswordAuthenticationFilter, DefaultLoginPageGeneratingFilter, DefaultLogoutPageGeneratingFilter, BasicAuthenticationFilter, RequestCacheAwareFilter, SecurityContextHolderAwareRequestFilter, AnonymousAuthenticationFilter, ExceptionTranslationFilter, AuthorizationFilter]
```

This is an **illustrative example line from the Spring Security architecture documentation**, not the verbatim predicted stdout for the code in section 4. In our program, **two separate lines** typically appear, which can be summarized as:

```text
[API chain] WEB matcher: /api/**
  Authentication: HTTP Basic
  Authorization: AuthorizationFilter
  CSRF: can contain CsrfFilter under defaults

[Web chain] WEB matcher: any request
  Authentication: form login
  Authorization: AuthorizationFilter
  CSRF: can contain CsrfFilter under defaults
```

The second snippet is a **reading-guide summary**, not a text format guaranteed by the framework. The exact filter list varies depending on the Spring Security version, auto-configuration components, enabled features, builder usage, and registered custom filters. **Do not compare logs against a fixed list of filter names copied from another article.**

### 4.4. How to Parse Each Part of a Will secure Line

A startup DEBUG line can be broken down as:

```text
DEBUG | DefaultSecurityFilterChain | Will secure | matcher | with | [filters...]
```

- **DEBUG**: the log level. If set only to INFO, this detailed line may not appear even though Security is still protecting requests.
- **DefaultSecurityFilterChain**: the class reporting that a filter chain has been built; it is not the name of a controller or URL.
- **Will secure**: this chain is intended to be used for requests accepted by its matcher.
- **Matcher**: may appear as `any request`, an `/api/**` pattern, or a representation like `Mvc [pattern='...']` / a composite matcher. The matcher's `toString()` syntax may vary by version.
- **with [filters]**: the list of security filters in configured order. This is the part to read to know which authentication/CSRF/authorization steps are present.
- **Filter names**: indicate the types of mechanisms installed in the chain, **not** every parameter, role expression, policy, or state of a specific request.

A `Will secure any request` line for a **fallback chain** does **not** mean it always handles every URL. If `/api/**` already matches the first chain, the fallback chain does not run for that request. To know which chain a specific URL selects, check `@Order`, `securityMatcher`, and **runtime** logs when issuing a request.

## 5. Identifying the Roles of Common Filters

Below is a "log reading dictionary" to quickly explain filter names **when they are actually present** in the chain:

| Filter | Observed Meaning | What Not to Infer |
| --- | --- | --- |
| `SecurityContextHolderFilter` | Sets up/manages the security context for the request | Does not prove the caller is authenticated |
| `CsrfFilter` | Contains CSRF verification logic according to configuration | Does not prove every endpoint requires a CSRF token; must check HTTP method/ignoring matcher |
| `HeaderWriterFilter` | Contains mechanism to add security response headers | Does not guarantee every header always appears (e.g., HSTS depends on secure connection/configuration) |
| `CorsFilter` | Contains CORS handling in this chain when configured | Does not mean all origins are allowed |
| `LogoutFilter` | Provides logout filter functionality | Does not prove logout endpoints/URLs are the same across all chains |
| `UsernamePasswordAuthenticationFilter` | Handles username/password authentication via form submission | Does not tell you which login page or custom failure handler is configured |
| `DefaultLoginPageGeneratingFilter` | Default Spring Security login page may be available | Does not prove a custom login form is active |
| `BasicAuthenticationFilter` | Processes HTTP Basic credentials | Does not mean every URL in the chain requires login |
| `BearerTokenAuthenticationFilter` | Provides Bearer token authentication path when a Servlet resource server is properly configured | Does not prove signature, issuer, audience, and every scope have been tested |
| `AnonymousAuthenticationFilter` | May establish an anonymous principal when unauthenticated | Must not treat anonymous as a verified user |
| `RequestCacheAwareFilter` | Contains logic related to saved requests/request cache | Does not by itself prove the chain creates sessions or that the request cache holds data |
| `ExceptionTranslationFilter` | Translates security exceptions to an authentication entry point/access-denied handler | Does not tell you whether all cases will return 401, 403, or 302 |
| `AuthorizationFilter` | Evaluates request authorization decisions | Does not tell you whether `permitAll`, `hasRole`, or owner/tenant rules are correct |

This list only describes **typical filters**; an actual chain may have many other filters, omitted filters, or new filters from a different version/framework. Filter names must be interpreted within the **exact chain** that was selected, without merging lists from multiple chains into one.

### Why Can an Endpoint Still Return 200 to Anonymous Users Even When Filters Are Present?

The presence of `AuthorizationFilter` does not prevent rules such as:

```java
.requestMatchers("/api/ping").permitAll()
```

Similarly, the presence of `BasicAuthenticationFilter` does not force every request to carry an Authorization header: public endpoints can still work without credentials. **Which filters are installed** and **which policy applies to a URL** are two separate questions.

### Why Does GET Still Succeed Even Though CsrfFilter Is Visible?

Default CSRF protection typically focuses on state-changing HTTP methods. For a normal GET request, missing a token does not necessarily trigger a 403. When adding POST/PUT/DELETE, you must inspect CSRF handling separately. Do not disable CSRF simply because you see `CsrfFilter` in the list or because a POST request without a token receives a 403; evaluate the authentication model and whether credentials are attached automatically by the client.

## 6. Using Real Requests to Verify Conclusions Drawn from Logs

After the application is running, test the requests. On PowerShell, use `curl.exe` instead of the `curl` alias present in some PowerShell versions.

```bash
# Public API, no Basic auth
curl -i http://localhost:8080/api/ping

# Admin API, missing Basic credentials
curl -i http://localhost:8080/api/admin

# Admin API, authenticated but only has USER
curl -i -u reader:reader123 \
  http://localhost:8080/api/admin

# Admin API, user with ROLE_ADMIN
curl -i -u admin:admin123 \
  http://localhost:8080/api/admin

# Admin web URL, no form-login session
curl -i http://localhost:8080/web/admin

# Public web URL
curl -i http://localhost:8080/web/public
```

The `\` line continuation here is Bash syntax. In PowerShell, put each command on a single line; using `curl.exe` preserves curl syntax.

Expected results to compare:

| Request | Selected Chain | Typical Status | Meaning |
| --- | --- | --- | --- |
| `GET /api/ping` without auth | `/api/**` (Order 1) | **200** | `permitAll` in the API chain |
| `GET /api/admin` without auth | `/api/**` | **401** + `WWW-Authenticate` | HTTP Basic mechanism requires authentication |
| `GET /api/admin` with `reader` | `/api/**` | **403** | Authenticated, missing ADMIN role |
| `GET /api/admin` with `admin` | `/api/**` | **200** | Has ADMIN role |
| `GET /web/admin` without session | Web fallback (Order 2) | **302** to `/login` | Form login requires signing in |
| `GET /web/public` without session | Web fallback | **200** | Public web URL |

When using `curl -i` without `-L`, you see the **first status code**. If you use `curl -L` or a browser that follows redirects automatically, you might see `/login` return 200 and mistakenly think the admin resource was allowed, whereas the original request actually received a 302.

Open `http://localhost:8080/web/admin` in an incognito browser window; the browser will be redirected to the default login form. After logging in as `reader`, because ADMIN is missing, `/web/admin` will be denied with 403. With the `admin` account in a new session, the resource is permitted. A real form login may require a session cookie and CSRF token; do not try sending POST `/login` with curl without a token and assume the account is invalid.

## 7. Reading Logs During Request Execution: How Does DEBUG Differ from TRACE?

**Startup logs** show the **filter list of each created chain**. **Runtime logs** show **which request is being processed, which filters were invoked, and where the request was blocked**. Both complement each other.

With the configuration:

```properties
logging.level.org.springframework.security.web.FilterChainProxy=TRACE
```

when a request arrives, you may see logs like:

```text
DEBUG o.s.security.web.FilterChainProxy : Securing GET /api/admin
TRACE o.s.security.web.FilterChainProxy : Invoking DisableEncodeUrlFilter (1/...)
TRACE o.s.security.web.FilterChainProxy : Invoking SecurityContextHolderFilter (.../...)
TRACE o.s.security.web.FilterChainProxy : Invoking BasicAuthenticationFilter (.../...)
TRACE o.s.security.web.FilterChainProxy : Invoking AuthorizationFilter (.../...)
```

**The lines above are intentionally abbreviated to illustrate structure**; they are not actual captured stdout, not a complete filter list, and do not guarantee the exact `(n/N)` counts of any specific version. If you need exact counts, read the TRACE output printed by your actual application version.

When TRACE is enabled for the entire `org.springframework.security` package, logs can also show the exact failure point, for example:

```text
DEBUG FilterChainProxy : Securing POST /...
TRACE FilterChainProxy : Invoking CsrfFilter (n/N)
DEBUG CsrfFilter : Invalid CSRF token found for ...
DEBUG AccessDeniedHandlerImpl : Responding with 403 status code
```

The second snippet is also an **abbreviated illustrative format**, not proof that the example app received a POST at that URL. The investigative principle is to follow a specific request through `FilterChainProxy`, see the last filter invoked, and then read the logger that owns the 401/403 decision. If `CsrfFilter` blocked it first, do not immediately blame `hasRole`.

### Procedure for Reading a Failing Request

1. Record the actual **method + path + status** from `curl -i`/DevTools.
2. Check which **SecurityFilterChain** matches the URL in order, rather than just looking for a bean with a similar name.
3. Check whether `FilterChainProxy` logs start protecting the request with `Securing ...`.
4. At TRACE, read **which filters were invoked up to the stopping point** and the associated error message.
5. If it is 401, check the authentication entry point, credentials, and corresponding authentication filter.
6. If it is 403, distinguish between CSRF, authorization, or a rule in the service layer.
7. If it is 302, check form login, request cache, and which page the HTTP redirect points to.
8. Fix the **source rule** (matcher, role, CSRF, chain order), restart if needed, and verify both status and new logs.

**Warning:** a `Secured GET /...` log line, if it appears, means the request passed through a security stage per that logger message; it does not by itself prove the returned data does not leak another user's resource. BOLA/IDOR and service-layer authorization must still be tested separately.

## 8. Reading Multiple Chains: Priority, Matchers, and Common Configuration Mistakes

### 8.1. Two Will secure Lines Exist, Yet Requests Still Hit the Wrong Chain

Suppose you write a broad catch-all chain at `@Order(1)`:

```java
@Bean
@Order(1)
SecurityFilterChain broadChain(HttpSecurity http)
        throws Exception {
    return http
        .authorizeHttpRequests(auth ->
            auth.anyRequest().authenticated()
        )
        .formLogin(Customizer.withDefaults())
        .build();
}
```

This is a **wrong priority example if you intend to place a separate API chain after it**. Because the chain above matches every request by default and is evaluated first, `/api/admin` requests will never reach an API chain at `@Order(2)`. Startup logs may still print **both chains**, but that does not mean both are eligible for the request.

Fix: place `securityMatcher("/api/**")` on the API chain and give it `@Order(1)`; place the `any request` fallback after it. Do not look only at the count of `Will secure` lines and assume your matchers are right.

### 8.2. Confusing securityMatcher and requestMatchers

```java
// These are only rules inside a single chain:
.authorizeHttpRequests(auth -> auth
    .requestMatchers("/api/**").hasRole("ADMIN")
    .anyRequest().authenticated()
)
```

This snippet **does not automatically create a separate SecurityFilterChain for the API** and does not turn form login into Basic auth just for `/api/**`. To have two different filter sets, you must have two `SecurityFilterChain` beans and define an appropriate `securityMatcher(...)` for the API chain.

### 8.3. No Fallback Leaves Some URLs Bypassing Spring Security

Suppose an application only registers:

```java
http.securityMatcher("/api/**");
```

and no other SecurityFilterChain matches `/admin`. `FilterChainProxy` may **not apply Spring Security filters** to `/admin`. That is a serious risk if the application has other endpoints. The startup line `Will secure /api/**` **does not prove** every request to the server is protected. When designing multiple chains, you should have a fallback without `securityMatcher(...)` (or an intentionally comprehensive fallback scope) to govern the remaining URLs.

Do not confuse **being bypassed by Spring Security** with **being permitted by a `permitAll()` rule**: `permitAll` still runs inside a chain and other security filters can still apply; skipping all filters means none of that chain's protections run.

### 8.4. BasicAuthenticationFilter Is Present, Yet the API Still Redirects to Login

If the startup log of the **selected API chain** actually shows form login and a custom entry point, the result may be a 302 instead of a 401. It is also possible that the request was handled by the web chain due to a misconfigured matcher. Check all of the following together:

- `@Order` and `securityMatcher(...)` of each bean;
- which chain `FilterChainProxy` selects when a real request runs;
- which `AuthenticationEntryPoint` is triggered at the endpoint;
- whether there is a custom filter or exception handling.

Do not solve this by always returning 401 for **web pages that use form login**, because 302 redirecting to the login page is intentional behavior for browsers.

### 8.5. Custom Filter Missing from the List

If you use:

```java
http.addFilterBefore(
    myAuditFilter,
    org.springframework.security.web.authentication
        .UsernamePasswordAuthenticationFilter.class
);
```

this snippet **illustrates how to attach a filter**, and is not part of the program in section 4; `myAuditFilter` must be an actual filter instance created in the application. If you start with DEBUG and do not see the custom filter in the expected chain, check:

- Was `addFilterBefore/After/At` called **on the HttpSecurity of the right chain bean**?
- Is the custom filter inside the SecurityFilterChain bean returned by `http.build()`?
- Is the filter ordered relative to an appropriate reference class?
- Is a filter both a Servlet `@Component` and added to the Spring Security chain, causing **double registration**?
- Are there two chains and you are looking at the log line for the other chain?

The custom filter name shown in logs may be a concrete class or a proxy, so do not search for an overly rigid literal string. If it is present at startup but not invoked at runtime, inspect matcher/chain selection or an early handler that short-circuits the pipeline.

## 9. When Are Startup Logs NOT Enough to Confirm Correct Configuration?

A filter list is a **structural snapshot at startup time**, not a complete description of every policy. For example:

| What to Verify | Is Startup DEBUG Enough? | What Else Is Needed? |
| --- | --- | --- |
| How many SecurityFilterChain instances were built | **Can be seen** via the Will secure lines | Cross-check bean configuration and filter chain logs |
| Which chain carries HTTP Basic | **Strong hint** when BasicAuthenticationFilter is present | Inspect `httpBasic` and send requests with credentials |
| Which URLs are public | **No** | Inspect `authorizeHttpRequests` and test anonymously |
| `hasRole("ADMIN")` applies to the right paths | **No** | Inspect rules, matchers, ordering, and test USER/ADMIN |
| JWT has valid signature/issuer/audience | **No** | Test the token decoder/validation |
| CSRF properly blocks POST | **No** | Send POST with and without a token in tests |
| Custom filter is actually **invoked** on request | **No** | Request TRACE or instrumented tests |
| User is authorized to read the right record | **No** | Check owner/tenant authorization in the service layer |
| Whether any endpoint is unprotected | **Not from line count alone** | Inspect all matchers and test edge-case paths |
| Whether logging is safe long-term in production | **No** | Evaluate sensitive data, log ACLs, retention, and performance |

Do not confuse **having a filter** with **every decision inside the filter being right**. For example, `AuthorizationFilter` is created, yet a misplaced `permitAll` matcher can expose sensitive URLs. When a specific rule appears after `anyRequest()`, configuration may even be rejected at build time; read the exact startup exception rather than looking only for `Will secure` lines.

## 10. Distinguishing Startup Logs That Are Easily Misread

### 10.1. Generated Security Password

If Spring Boot creates a default account for development, startup may print a message about a randomly generated password. This is an **auto-configuration indicator for the default user**, not proof that `SecurityFilterChain` beans are configured as intended. If you declare your own `UserDetailsService` as in the example, Boot typically does not create that default account.

The generated password is still a **credential**—do not screenshot it or paste it into public tickets or chats. If you see this message outside a development environment, immediately review user and secret management in the application.

### 10.2. Condition Evaluation Report

When running with `--debug`, Spring Boot may print "matched/did not match" auto-configuration conditions. This helps explain why a bean or configuration was activated, but **does not replace** `DefaultSecurityFilterChain` logs listing specific filters. An application can have a security auto-configuration "matched" while a developer overrides the `SecurityFilterChain` bean details with custom configuration.

### 10.3. Servlet Container Startup

A line like "Tomcat started on port 8080" or "Started ...Application" means the application started and the server accepts requests; it tells you **nothing** about security matchers, roles, or CSRF. A controller that exists without a matching SecurityFilterChain can still return HTTP 200 once the server starts.

### 10.4. Missing DEBUG Logs Due to Logging Config, Not Missing Filters

If `Will secure` lines are absent, before concluding that security is inactive, check:

1. Did you enable DEBUG **before the application context initialized**?
2. Is the logger name exact: `org.springframework.security.web.DefaultSecurityFilterChain`?
3. Is a `logback-spring.xml`, logger policy, or appender suppressing DEBUG?
4. Are logs being shipped to a collector or file instead of the console?
5. Is the app running **Servlet or WebFlux**? WebFlux does not use the equivalent Servlet DefaultSecurityFilterChain class to print that exact format.
6. Is the running app using the exact JAR/build matching the code you are reading?

Additionally, if the app **does not use Servlet** and runs reactive instead, look for the mechanism and loggers for `SecurityWebFilterChain` / `WebFilterChainProxy`; do not treat the absence of Servlet logs as proof of missing security.

## 11. Debugging 401, 403, and 302 by Combining Startup and Request Logs

### 11.1. HTTP 401 from an API

Symptom:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Basic realm="Realm"
```

This is an **example HTTP Basic header format**; actual realm/header values may vary by configuration/version. Investigation steps:

1. Does startup show an `/api/**` chain containing `BasicAuthenticationFilter`?
2. Does the API chain accept the `/api/admin` request?
3. Is the `Authorization` header present with the right Basic scheme? **Do not log the header value.**
4. Are credentials verified by the user details service?
5. If credentials are valid yet 401 occurs, check the password encoder, locked/disabled account flags, and authentication provider.

### 11.2. HTTP 403 When Already Authenticated

A 403 response can result from:

- The account has `ROLE_USER`, while the endpoint requires `ROLE_ADMIN`.
- A missing or invalid CSRF token on a state-changing request.
- Method security or a custom `AuthorizationManager` denying access.
- A custom filter or handler producing a 403 response.

Startup logs tell you **which components were installed**, but runtime TRACE and tests are needed to distinguish the root cause. For a `POST` returning 403, check `CsrfFilter` before changing roles or disabling CSRF.

### 11.3. HTTP 302 Redirect to Login

For web form login, 302 is usually expected when there is no authenticated session. If an API returns an unexpected redirect, inspect matchers and entry points. Note that an HTTP client may automatically follow the 302 and receive 200 HTML from `/login`; do not look only at the final status and assume the API returned data.

### 11.4. HTTP 404 at /login Even Though formLogin Is Enabled

In a narrowly scoped chain configuration, a filter may provide endpoints **only within the scope of that chain's own matcher**. If you configure `formLogin` in a chain that only matches `/secured/**` while leaving the default login endpoint `/login` outside it, requests to `/login` may not be handled by the chain containing the login filter and may return 404. You must align the login endpoint with the scope and configure the URL accurately; startup logs show that the form-login filter exists, **not that every login URL is reachable**.

In the section 4 example, the web chain is the fallback, so `/login` is handled by that chain.

## 12. Automated Testing to Avoid "Reading Logs and Guessing"

Logs are an **observability** tool, whereas HTTP tests are proof of **behavior**. With Spring Boot 3.x and `spring-security-test`, you can use `MockMvc` to build a test matrix independent of log wording. Add the test dependency to `build.gradle` of your Initializr project:

```groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

Below is a dedicated test class for the sample application (Java 17+, Spring Boot 3.x), placed at:

```text
src/test/java/demo/filterlogs/SecurityChainLogApplicationTests.java
```

```java
package demo.filterlogs;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.status;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.redirectedUrlPattern;

@SpringBootTest
@AutoConfigureMockMvc
class SecurityChainLogApplicationTests {

    @Autowired
    MockMvc mvc;

    @Test
    void apiPingIsPublic() throws Exception {
        mvc.perform(get("/api/ping"))
            .andExpect(status().isOk());
    }

    @Test
    void anonymousApiAdminRequiresBasicAuth() throws Exception {
        mvc.perform(get("/api/admin"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void readerCannotAccessApiAdmin() throws Exception {
        mvc.perform(get("/api/admin")
                .with(httpBasic("reader", "reader123")))
            .andExpect(status().isForbidden());
    }

    @Test
    void adminCanAccessApiAdmin() throws Exception {
        mvc.perform(get("/api/admin")
                .with(httpBasic("admin", "admin123")))
            .andExpect(status().isOk());
    }

    @Test
    void anonymousWebAdminRedirectsToLogin() throws Exception {
        mvc.perform(get("/web/admin"))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrlPattern("**/login"));
    }

    @Test
    void webPublicIsAccessible() throws Exception {
        mvc.perform(get("/web/public"))
            .andExpect(status().isOk());
    }
}
```

**To create the real Java file, write each of the four static imports on a single line** (do not copy lines wrapped solely for README display):

```java
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.redirectedUrlPattern;
```

When authoring the test file, use these imports **instead** of the wrapped imports above; do not duplicate them. These tests verify the **behavior** of representative URLs in both chains, especially distinguishing the API returning 401 from the web returning 302. They do not exhaustively test BOLA, CSRF on POST, service-layer policies, or security on every URL; expand them for a real application.

Run with:

```bash
./gradlew test
# Windows:
# .\gradlew.bat test
```

The tests are expected to PASS when run against the declared project. This is not measured stdout captured in the documentation. To verify **specific filters**, combine startup DEBUG/runtime TRACE or controlled configuration introspection/tests, rather than asserting that "the string `BasicAuthenticationFilter` appears anywhere in stdout" (which is brittle across loggers and versions).

## 13. Do Not Expose Sensitive Data Through Logging

Enabling DEBUG/TRACE is a **time-bounded diagnostic tool**:

- Use dev/test profiles or logging settings restricted to authorized investigative environments.
- Never log `Authorization`, `Cookie`, credentials, access tokens, refresh tokens, session IDs, request bodies containing personal data, or `password` values.
- When forwarding logs to a collector, control read permissions, encrypt in transit and at rest as appropriate, and manage retention, copies, and redaction/deletion mechanisms.
- Be cautious with URLs/query strings containing emails, tokens, or personal information; `Securing GET /...` logs can expose paths if the app puts sensitive data in URLs.
- Never paste logs containing sensitive information into public issues. When sharing logs to troubleshoot, send only lines describing **matchers/filter classes** after reviewing the data.
- Once investigation finishes, lower logging back to an appropriate operational level; package-wide TRACE can overwhelm logs and drown out important signals.

An incident-support rule of thumb: **you only need to know the filter and the decision**, not the password or token values. For example, a "Basic authentication failed" log may be enough to narrow down the issue; for deeper analysis, use fake test credentials and controlled tracing rather than logging real secrets.

## 14. Quick Checklist When Onboarding to a Spring Security Project

1. **Identify the stack**: Servlet/MVC uses `HttpSecurity`, `SecurityFilterChain`, `FilterChainProxy`; WebFlux uses `ServerHttpSecurity`, `SecurityWebFilterChain`.
2. **Enable DEBUG on the right logger**: `org.springframework.security.web.DefaultSecurityFilterChain` or the `org.springframework.security` package, then restart.
3. **Find all `Will secure` lines**: count chains, read each chain's matcher and filter list; do not mix filters across chains.
4. **Draw a matcher–order map**: `/api/**` Order 1, fallback Order 2, etc.; check whether any URL matches no chain.
5. **Mark mechanisms in each chain**: Basic/form login/Bearer, CSRF, AuthorizationFilter, custom filters.
6. **Verify source policies**: `requestMatchers`, `hasRole`, `permitAll`, `access`, CORS/CSRF; startup logs do not contain all of this information.
7. **Send representative requests**: anonymous, regular user, admin, GET and POST when write operations exist.
8. **Enable FilterChainProxy TRACE purposefully** if results differ from expectations; read which filters actually ran and where the request was rejected.
9. **Automate tests** for each authorization scope and special URL, including negative cases.
10. **Lower logging after diagnosis**, review any data that may have been logged, and protect log read access.

**Conclusion:** the line `DefaultSecurityFilterChain : Will secure ... with [...]` shows **the security filter chains created at startup**. It is a structural map, not proof that every request is secure. To understand actual runtime behavior, always cross-check **matcher + @Order + filter list + authorization rules + request logs + HTTP tests**.

### Official Documentation

- [Spring Security 6.5 — Servlet Architecture, Printing the Security Filters & Logging](https://docs.spring.io/spring-security/reference/6.5/servlet/architecture.html)
- [Spring Security 6.5 — Java Configuration: Multiple HttpSecurity Instances](https://docs.spring.io/spring-security/reference/6.5/servlet/configuration/java.html)
- [Spring Security 6.5 — Authorize HttpServletRequests](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/authorize-http-requests.html)
- [Spring Boot 3.5 — Logging](https://docs.spring.io/spring-boot/3.5/reference/features/logging.html)
- [Spring Security — CSRF Protection](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html)
