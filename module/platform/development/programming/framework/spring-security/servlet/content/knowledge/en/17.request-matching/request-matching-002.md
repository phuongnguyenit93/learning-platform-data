# Distinguishing Context Path, Servlet Path, and Application-Internal Path — Spring Security Servlet

When configuring **request matching** in Spring Security Servlet, a URL visible in the browser is not necessarily the string that `RequestMatcher` inspects. There are three components to distinguish: **context path** (the path where the application is deployed in the servlet container), **servlet path** (the path segment used by the container to route to a servlet), and **path info** (the remaining portion after a prefix servlet mapping, if any). Spring MVC also has a **path relative to DispatcherServlet** for looking up `@GetMapping`, `@PostMapping`, etc.

Confusing these parts easily causes two types of bugs: a Spring Security configuration blocking permitted endpoints, or worse, writing a matcher that fails to cover a sensitive endpoint while assuming it is protected. In particular, **never drop `request.getRequestURI()` or an external proxy path straight into `requestMatchers("...")` without knowing which part of the request the matcher compares against**.

Key example:

~~~text
URL:  https://example.org/catalog/mvc/orders/42?view=full
      └─ host ─┘ └────────────────────────────┘ └─────┘
                            path                 query

Assume:
  context path             /catalog
  servlet mapping          /mvc/*
  servlet path             /mvc
  path info                /orders/42
  MVC path inside servlet  /orders/42
  request URI              /catalog/mvc/orders/42
  query string             view=full
~~~

**Not every configuration splits paths like this example.** The container determines `servletPath` and `pathInfo` based on the mapping style. If `DispatcherServlet` uses the default `/` mapping, `servletPath` usually holds the entire remaining path within the application (e.g., `/orders/42`) and `pathInfo` is `null`. This lesson explains those two concrete cases and connects them to `MvcRequestMatcher`, `AntPathRequestMatcher`, and `SecurityFilterChain`.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Distinguish the values of `getRequestURI()`, `getContextPath()`, `getServletPath()`, `getPathInfo()`, `getQueryString()`, and `getRequestURL()`.
2. Correctly predict the three path components when an application runs at the root context, at context `/catalog`, under servlet mapping `/mvc/*`, and with extension mapping.
3. Explain why Spring MVC `@GetMapping("/orders/{id}")` usually does **not** include the context path or DispatcherServlet mapping prefix.
4. Know when a Spring Security matcher compares the **servlet-relative path**, when it compares **servletPath + pathInfo**, and why you must identify the **RequestMatcher type** before writing URL patterns.
5. Distinguish `securityMatcher(...)` for selecting a `SecurityFilterChain` from `requestMatchers(...)` for selecting an authorization rule within a chain.
6. Build a Java 17+ / Spring Boot 3.3.5 application demonstrating a real context path and test with MockMvc using accurate HTTP request metadata.
7. Recognize risks from reverse proxies, servlet path prefixes, multiple servlets, encoded paths, path normalization, and tests missing context/servlet information.

## 2. Four Layers of a URL Seen in the Browser

An HTTP request has multiple representations:

~~~text
https://api.example.org/catalog/mvc/orders/42?sort=latest#details
└────── origin ──────┘└───── URI path ────────┘└─query─┘└fragment┘
                       /catalog/mvc/orders/42
                            |
               HTTP request on server
                            |
                  +---------+-----------+
                  |                     |
              contextPath         path in context
               /catalog            /mvc/orders/42
                                       |
                            +----------+----------+
                            |                     |
                        servletPath             pathInfo
                           /mvc                 /orders/42
~~~

Several points to remember:

- The URL fragment `#details` is only client-side navigation; browsers do not send that fragment in a normal HTTP request target.
- A query string like `sort=latest` **is not inside `getRequestURI()`**. It is read separately via `getQueryString()` or parameters.
- `getRequestURL()` can provide scheme/host/port/path, but **does not include the query string**; host/scheme metadata behind a reverse proxy may require proper forwarding handling.
- `getContextPath()` is the prefix that the servlet container assigns to the web application. For a root deployment, it is typically the empty string `""`, not `"/"`.
- `getServletPath()` and `getPathInfo()` **are not simply the result of `String.split("/")`**. The servlet mapping chosen by the container determines the boundary between the two parts.
- Some containers/filters may expose decoded or normalized paths per API contract. **Do not use these methods as a hand-rolled security canonicalization mechanism**; the matcher/framework must apply a consistent path-parsing policy.

### 2.1. context path: Where Is the Application Mounted?

Suppose the server hosts the application at `/catalog`. External paths might look like:

~~~text
GET /catalog/public/ping
GET /catalog/orders/42
GET /catalog/admin/report
~~~

In the servlet request, `getContextPath()` typically returns `"/catalog"`, while the path inside the application excludes `"/catalog"`. When deployed at the root context, `getContextPath()` is `""`.

Spring Boot configuration example:

~~~properties
server.servlet.context-path=/catalog
~~~

Result: the browser accesses `http://localhost:8080/catalog/public/ping` instead of `http://localhost:8080/public/ping`. Yet the controller can still declare:

~~~java
@GetMapping("/public/ping")
public String ping() {
    return "pong";
}
~~~

**Do not add `/catalog` to `@GetMapping` just because the server mounted the app at `/catalog`.** That is a web application deployment prefix, not a business route.

When using a Spring Security string request matcher for an MVC endpoint, the general rule also **omits the context path**. However, the rest of the pattern depends on the matcher and servlet mapping. Do not equate "omits context path" with "every matcher omits servlet path".

### 2.2. servlet path: Which Servlet Did the Container Select?

A servlet container can map servlets in several ways:

- **Default mapping `/`:** requests belonging to the application and not claimed by another exact/prefix/extension mapping are handled by the default servlet. With DispatcherServlet mapped to `/`, `servletPath` is typically the path within the context such as `/orders/42`; `pathInfo` is typically `null`.
- **Prefix mapping `/mvc/*`:** request `/catalog/mvc/orders/42` has `servletPath="/mvc"` and `pathInfo="/orders/42"`.
- **Extension mapping `*.do`:** request `/catalog/reports.do` may have `servletPath="/reports.do"`, `pathInfo=null`.
- **Exact mapping `/health`:** request `/catalog/health` typically has `servletPath="/health"`, `pathInfo=null`.

These cases illustrate servlet mapping rules; if there are multiple servlets or route mappings, inspect an actual request instead of guessing. In particular, a trailing slash, path parameters, or URL encoding can affect mapping selection.

### 2.3. pathInfo: The Remaining Part After Prefix Mapping

With servlet mapping `/mvc/*`:

~~~text
request URI:  /catalog/mvc/orders/42
contextPath:  /catalog
servletPath:  /mvc
pathInfo:     /orders/42
~~~

With default DispatcherServlet mapping `/`:

~~~text
request URI:  /catalog/orders/42
contextPath:  /catalog
servletPath:  /orders/42
pathInfo:     null
~~~

Both cases can route to a controller declaring `@GetMapping("/orders/{id}")`, yet **the values of `getServletPath()` and `getPathInfo()` are different**. That is why logging only `request.getServletPath()` and calling it the "full request path" is misleading.

### 2.4. Reference Table for Real Requests

| Context | Servlet mapping | Request URI | getContextPath() | getServletPath() | getPathInfo() |
| --- | --- | --- | --- | --- | --- |
| Root | `/` | `/orders/42` | `""` | `/orders/42` | `null` |
| `/catalog` | `/` | `/catalog/orders/42` | `/catalog` | `/orders/42` | `null` |
| `/catalog` | `/mvc/*` | `/catalog/mvc/orders/42` | `/catalog` | `/mvc` | `/orders/42` |
| Root | `/mvc/*` | `/mvc/orders/42` | `""` | `/mvc` | `/orders/42` |
| `/catalog` | `*.do` | `/catalog/reports.do` | `/catalog` | `/reports.do` | `null` |
| `/catalog` | Exact `/health` | `/catalog/health` | `/catalog` | `/health` | `null` |

This table reflects **common servlet mappings**, not a guarantee that every proxy/framework exposes the exact same metadata after URL rewriting. Query strings are excluded from the `requestURI` values in the table.

## 3. Which Concept Is the "Application-Internal" Path?

A common approximate description is:

~~~text
requestURI = contextPath + servletPath + (pathInfo or "")
~~~

For simple mapping examples, this concatenation reconstructs the path in the request URI. **This is a mental model, not security parsing code to implement manually with `substring`**: encoding, normalization, proxy rewrites, and Servlet API contracts must be handled consistently by the framework.

There are **two path portions** often loosely called the "application path":

1. **Path after context root:** `servletPath + pathInfo`, e.g., `/mvc/orders/42`. Some Spring Security RequestMatchers treat this as the path to match.
2. **Path inside DispatcherServlet:** after the servlet mapping prefix, e.g., `/orders/42`. Spring MVC handler mappings look up controller routes using this servlet-relative path.

If DispatcherServlet uses the default `/` mapping, both representations may look identical (e.g., `/orders/42`). That very similarity causes bugs to appear only later when switching to a `/mvc/*` mapping.

### 3.1. Path of a Spring MVC Controller

In an app with context `/catalog` and DispatcherServlet `/mvc/*`, the controller:

~~~java
@RestController
class OrdersController {
    @GetMapping("/orders/{id}")
    String getOrder(@PathVariable String id) {
        return "order-" + id;
    }
}
~~~

can be accessed via the external URL `/catalog/mvc/orders/42` when servlet mapping and MVC path matching are compatibly configured. `@GetMapping` does not need to declare `"/catalog/mvc/orders/{id}"`.

However, **do not treat manual concatenation of context + servlet prefix as an absolute rule** when gateway rewrites, `ForwardedHeaderFilter`, multiple DispatcherServlets, or custom URL mappings are involved. Inspect the actual request metadata and mappings.

### 3.2. getRequestURI vs. getQueryString

For the request:

~~~http
GET /catalog/mvc/orders/42?sort=price&page=3 HTTP/1.1
Host: example.org
~~~

typical values are:

~~~text
request.getRequestURI()   = "/catalog/mvc/orders/42"
request.getContextPath()  = "/catalog"
request.getServletPath()  = "/mvc"
request.getPathInfo()     = "/orders/42"
request.getQueryString()  = "sort=price&page=3"
~~~

Spring Security path matchers usually do not use the query string to determine the path. **Do not use query parameters as an authorization boundary in place of path/method/identity**; parameters like `tenantId`, `orderId`, or `ownerId` still require authorization logic to verify ownership/tenant.

### 3.3. Servlet Mapping Is an Input to Matching

To understand why `getServletPath()` is `/mvc` rather than `/mvc/orders/42`, look at the **mapping**, not `@Controller`. The container selected the servlet via `/mvc/*`; the remaining `/orders/42` part is exposed via `getPathInfo()`.

Hand-written middleware like:

~~~java
String path = request.getServletPath();
if (path.startsWith("/orders/")) {
    // ...
}
~~~

may work when DispatcherServlet maps `/`, but **breaks** when mapped to `/mvc/*` because `servletPath` is then only `/mvc`. If this is a security check, the bug can create a vulnerability or block the wrong paths. Use an appropriate Spring Security RequestMatcher instead of hand-rolled string comparisons.

## 4. Which Part Does Spring Security's RequestMatcher Compare?

You cannot answer accurately with just "Spring Security" without specifying the **matcher type and version**. Different APIs interpret patterns differently.

### 4.1. MvcRequestMatcher (Spring Security 6.x + Spring MVC)

`MvcRequestMatcher` uses `HandlerMappingIntrospector` to apply Spring MVC semantics. With DispatcherServlet mapped under `/mvc/*`, you can configure a **specific servlet path**:

~~~java
MvcRequestMatcher.Builder mvc =
    new MvcRequestMatcher.Builder(introspector)
        .servletPath("/mvc");

MvcRequestMatcher adminMatcher =
    mvc.pattern(HttpMethod.GET, "/admin/**");
~~~

This is an **illustrative code snippet**, requiring Spring MVC, Spring Security, a `HandlerMappingIntrospector` bean, and imports. The pattern `"/admin/**"` is interpreted as the path Spring MVC uses to match handlers; you declare `servletPath("/mvc")` separately to identify the servlet.

Do not write `mvc.pattern("/catalog/mvc/admin/**")` because `/catalog` is the context path and `/mvc` is already declared for the servlet mapping. When using MvcRequestMatcher with multiple servlets, specifying the servlet path prevents rules from mistakenly applying to another servlet. **If the application does not use MVC or has a different servlet mapping, do not use the MVC matcher out of habit.**

### 4.2. AntPathRequestMatcher and the servletPath + pathInfo Representation

Spring Security 6 versions also include `AntPathRequestMatcher`. For this matcher, the path to compare is usually formed by:

~~~java
request.getServletPath() + (request.getPathInfo() == null
    ? ""
    : request.getPathInfo())
~~~

For example, a request with `contextPath="/catalog"`, `servletPath="/mvc"`, `pathInfo="/orders/42"`:

- `AntPathRequestMatcher("/mvc/orders/**")` → **matches**.
- `AntPathRequestMatcher("/catalog/mvc/orders/**")` → **does not match**, because the context path is not part of the matched string.
- `AntPathRequestMatcher("/orders/**")` → usually **does not match** in this prefix-mapping example because `/mvc` is present.

This is a key difference from relative patterns in `MvcRequestMatcher`. **Do not copy a pattern between the two matchers without checking their semantics.**

Some older APIs become deprecated in newer releases; if an application is upgrading, check the current Spring Security version and prefer the matching API recommended for that version. Never assume every matcher class exists forever or keeps identical semantics.

### 4.3. String requestMatchers in the DSL

Familiar configuration:

~~~java
.authorizeHttpRequests(auth -> auth
    .requestMatchers("/admin/**").hasRole("ADMIN")
    .anyRequest().denyAll())
~~~

In Spring Security 6 versions with Spring MVC, the DSL can select an MVC-aware matcher for string patterns when auto-selection conditions are met. If a project has multiple servlets or custom setups, ambiguity or differences between matchers may arise. Therefore:

1. Know the exact framework version.
2. Know whether `DispatcherServlet` maps to `/` or `/mvc/*`.
3. Know whether the DSL created an `MvcRequestMatcher`, `AntPathRequestMatcher`, or another matcher.
4. When there are multiple servlets/prefixes, **construct explicit matchers** instead of relying on guesswork from a string path.

**Do not take "requestMatchers always omits the context path" and conclude it also always omits the servlet path.** Context path and servlet path are two different layers; whether the servlet path belongs in the pattern depends on the matcher.

### 4.4. PathPatternRequestMatcher in Newer Versions

Newer Spring Security releases provide `PathPatternRequestMatcher` with a builder supporting `basePath(...)` for prefix servlet mappings. Pattern declarations can be based on the **context-root-relative** path and require defining the proper prefix when the servlet is not at root. This is a version-sensitive API; **do not copy snippets from newer versions into Boot 3.3.5 without checking the bundled Spring Security dependency**.

The safe rule is: **use matchers appropriate to your exact version and verify with tests directly against requests under production mappings**. Especially during Ant/MVC/PathPattern migrations, an "identical" pattern does not imply identical behavior.

## 5. securityMatcher and requestMatchers: Two Separate Matching Levels

In Spring Security Servlet, there is also chain selection order.

~~~text
Request: GET /catalog/mvc/admin/report
                 |
                 v
          FilterChainProxy
                 |
       SecurityFilterChain #1
       securityMatcher matches?
                 |
       yes -> select CHAIN #1
                 |
       authorizeHttpRequests
       requestMatchers:
         rule A matches? -> permission check
         rule B matches? -> ...
                 |
       Controller / error response
~~~

- `http.securityMatcher(...)` decides **whether the SecurityFilterChain handles this request**. Multiple chains are evaluated in order and **the first matching chain** is selected.
- `authorizeHttpRequests(auth -> auth.requestMatchers(...))` decides the **authorization rule** for the request inside the selected chain.
- `anyRequest().denyAll()` only applies **after the chain has been selected**; it does not automatically protect URLs outside that chain's `securityMatcher`.

If you write `securityMatcher` with the wrong path (for example, including a context path that the matcher does not use), a specialized chain may **never be selected**. If a general/fallback chain permits all or authenticates too broadly, an admin endpoint could end up with weaker authorization than intended.

### 5.1. Example of Two Path-Based Chains

Illustrative configuration snippet, not a standalone Java file:

~~~java
@Bean
@Order(1)
SecurityFilterChain adminChain(HttpSecurity http) throws Exception {
    return http
        .securityMatcher("/admin/**")
        .authorizeHttpRequests(auth -> auth
            .anyRequest().hasRole("ADMIN"))
        .httpBasic(Customizer.withDefaults())
        .build();
}

@Bean
@Order(2)
SecurityFilterChain fallbackChain(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(auth -> auth
            .anyRequest().denyAll())
        .build();
}
~~~

This example assumes string matchers match the current servlet mapping and matcher semantics; in a multi-servlet app, use an explicit RequestMatcher. If you accidentally put `securityMatcher("/catalog/admin/**")` in an app with context path `/catalog`, the admin chain may fail to match. In that case, fix the **matcher**, not `@Order` or `hasRole`.

### 5.2. Wrong External Proxy URLs Are Even More Dangerous

For example, an external proxy adds the `/edge` prefix and forwards to the internal app at `/catalog`:

~~~text
External client:  GET /edge/catalog/admin/report
Reverse proxy:   GET /catalog/admin/report
Servlet app:     contextPath=/catalog
The security matcher must apply to the request as seen by the servlet container.
~~~

Never copy `"/edge/catalog/admin/**"` into Spring Security just because the browser sees that URL. If the gateway **does not rewrite** as in the example and instead forwards the prefix or uses forwarded headers, the request metadata may differ. **Observe the actual request and only trust proxy headers from trusted infrastructure.**

## 6. Lab: An Application With a Non-Root Context Path

To keep the example stable with Java 17+ and Spring Boot 3.3.5, the following runnable project uses the **default DispatcherServlet mapping `/`** while setting **context path `/catalog`**. This demonstrates that the context path is a deployment prefix and must not be placed into `@GetMapping` or MVC matchers.

The advanced section on the `/mvc/*` servlet prefix is in section 8 as a **standalone configuration example**; do not mix the two configurations and assume a property automatically fixes every matcher.

### 6.1. Project Structure

~~~text
request-path-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/
    │   ├── java/example/pathdemo/
    │   │   ├── PathDemoApplication.java
    │   │   ├── SecurityConfiguration.java
    │   │   └── PathController.java
    │   └── resources/application.properties
    └── test/java/example/pathdemo/
        └── PathMatchingTests.java
~~~

File `settings.gradle`:

~~~groovy
rootProject.name = 'request-path-demo'
~~~

File `build.gradle`:

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
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

File `src/main/resources/application.properties`:

~~~properties
server.servlet.context-path=/catalog
# Do not set spring.mvc.servlet.path: DispatcherServlet maps to / by default
server.port=8080
~~~

Once running, external URLs start with `/catalog`. The controller still does not declare that prefix.

### 6.2. Startup Class

File `src/main/java/example/pathdemo/PathDemoApplication.java`:

~~~java
package example.pathdemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class PathDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(PathDemoApplication.class, args);
    }
}
~~~

### 6.3. SecurityConfiguration: Matchers Without Context Path

File `src/main/java/example/pathdemo/SecurityConfiguration.java`:

~~~java
package example.pathdemo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfiguration {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {

        return http
            .authorizeHttpRequests(auth -> auth
                // Do not write /catalog/public/ping here.
                .requestMatchers(HttpMethod.GET, "/public/ping")
                    .permitAll()

                // Only admin can access report.
                .requestMatchers(HttpMethod.GET, "/admin/report")
                    .hasRole("ADMIN")

                // User with product-read scope.
                .requestMatchers(HttpMethod.GET, "/products/{id}")
                    .hasAuthority("SCOPE_products.read")

                // Endpoint to inspect HTTP path metadata, not public.
                .requestMatchers(HttpMethod.GET, "/whoami")
                    .authenticated()

                // Protect newly added undeclared paths.
                .anyRequest().denyAll())

            .httpBasic(Customizer.withDefaults())
            .build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        UserDetails reader = User.withUsername("reader")
            .password(encoder.encode("reader-pass"))
            .authorities("ROLE_USER", "SCOPE_products.read")
            .build();

        UserDetails admin = User.withUsername("admin")
            .password(encoder.encode("admin-pass"))
            .authorities("ROLE_ADMIN")
            .build();

        return new InMemoryUserDetailsManager(reader, admin);
    }
}
~~~

All patterns `"/public/ping"`, `"/admin/report"`, and `"/products/{id}"` describe MVC paths **inside the application**, excluding `/catalog`. Endpoints without a matching rule are rejected by `denyAll()`. `HttpMethod.GET` is part of the condition: a POST to the same path is not automatically allowed.

### 6.4. PathController: Inspecting the Servlet Request

File `src/main/java/example/pathdemo/PathController.java`:

~~~java
package example.pathdemo;

import java.util.LinkedHashMap;
import java.util.Map;

import jakarta.servlet.http.HttpServletRequest;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class PathController {

    @GetMapping("/public/ping")
    public String ping() {
        return "pong";
    }

    @GetMapping("/admin/report")
    public String report() {
        return "admin-report";
    }

    @GetMapping("/products/{id}")
    public String product(@PathVariable long id) {
        return "product-" + id;
    }

    @GetMapping("/whoami")
    public Map<String, Object> whoami(HttpServletRequest request) {
        Map<String, Object> path = new LinkedHashMap<>();
        path.put("requestURI", request.getRequestURI());
        path.put("contextPath", request.getContextPath());
        path.put("servletPath", request.getServletPath());
        path.put("pathInfo", request.getPathInfo());
        path.put("queryString", request.getQueryString());
        return path;
    }
}
~~~

**Security:** the `/whoami` endpoint is for learning only; never expose internal info, sensitive headers, or cookies in a public production response. It intentionally does not return session ids, Authorization headers, or CSRF tokens. Even this path metadata still needs access control if it reveals internal topology or user data.

### 6.5. MockMvc Tests: contextPath Must Be Simulated Accurately

File `src/test/java/example/pathdemo/PathMatchingTests.java`:

~~~java
package example.pathdemo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.security.web.util.matcher.AntPathRequestMatcher;
import org.springframework.test.web.servlet.MockMvc;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class PathMatchingTests {

    @Autowired
    MockMvc mockMvc;

    @Test
    void publicPathMatchesWithoutContextPrefixInSecurityRule()
            throws Exception {
        mockMvc.perform(get("/catalog/public/ping")
                .contextPath("/catalog")
                .servletPath("/public/ping"))
            .andExpect(status().isOk())
            .andExpect(content().string("pong"));
    }

    @Test
    void protectedProductNeedsAuthentication() throws Exception {
        mockMvc.perform(get("/catalog/products/42")
                .contextPath("/catalog")
                .servletPath("/products/42"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void readerWithAuthorityCanSeeProduct() throws Exception {
        mockMvc.perform(get("/catalog/products/42")
                .contextPath("/catalog")
                .servletPath("/products/42")
                .with(httpBasic("reader", "reader-pass")))
            .andExpect(status().isOk())
            .andExpect(content().string("product-42"));
    }

    @Test
    void readerCannotSeeAdminReport() throws Exception {
        mockMvc.perform(get("/catalog/admin/report")
                .contextPath("/catalog")
                .servletPath("/admin/report")
                .with(httpBasic("reader", "reader-pass")))
            .andExpect(status().isForbidden());
    }

    @Test
    void adminCanSeeAdminReport() throws Exception {
        mockMvc.perform(get("/catalog/admin/report")
                .contextPath("/catalog")
                .servletPath("/admin/report")
                .with(httpBasic("admin", "admin-pass")))
            .andExpect(status().isOk())
            .andExpect(content().string("admin-report"));
    }

    @Test
    void servletMetadataShowsActualDecomposition() throws Exception {
        mockMvc.perform(get("/catalog/whoami")
                .contextPath("/catalog")
                .servletPath("/whoami")
                .with(httpBasic("reader", "reader-pass")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.requestURI")
                .value("/catalog/whoami"))
            .andExpect(jsonPath("$.contextPath")
                .value("/catalog"))
            .andExpect(jsonPath("$.servletPath")
                .value("/whoami"));
    }

    @Test
    void antMatcherUsesServletPathPlusPathInfoNotContext()
            throws Exception {
        MockHttpServletRequest request =
            new MockHttpServletRequest(
                "GET", "/catalog/mvc/orders/42");

        request.setContextPath("/catalog");
        request.setServletPath("/mvc");
        request.setPathInfo("/orders/42");

        assertEquals("/catalog", request.getContextPath());
        assertEquals("/mvc", request.getServletPath());
        assertEquals("/orders/42", request.getPathInfo());

        assertTrue(new AntPathRequestMatcher(
            "/mvc/orders/**").matches(request));

        assertFalse(new AntPathRequestMatcher(
            "/catalog/mvc/orders/**").matches(request));

        assertFalse(new AntPathRequestMatcher(
            "/orders/**").matches(request));
    }

    @Test
    void defaultServletRequestHasNoPathInfo()
            throws Exception {
        MockHttpServletRequest request =
            new MockHttpServletRequest(
                "GET", "/catalog/products/42");

        request.setContextPath("/catalog");
        request.setServletPath("/products/42");

        assertEquals("/products/42", request.getServletPath());
        assertNull(request.getPathInfo());
    }

    @Test
    void unknownUrlIsDeniedToAuthenticatedUser()
            throws Exception {
        mockMvc.perform(get("/catalog/not-configured")
                .contextPath("/catalog")
                .servletPath("/not-configured")
                .with(httpBasic("reader", "reader-pass")))
            .andExpect(status().isForbidden());
    }
}
~~~

In the manual test with `MockHttpServletRequest`, we **explicitly set** contextPath/servletPath/pathInfo to simulate servlet mapping. That unit test proves the semantics of `AntPathRequestMatcher` on a request fixture, but **does not prove that a production container automatically chooses the exact same mapping**. The remaining HTTP integration tests use MockMvc going through the Spring Security chain and Spring MVC controller.

Depending on the version, some older matchers may be deprecated; in a Spring Security 6.3.x demo they help illustrate behavior, but when upgrading you must check the replacement API. **Do not use AntPathRequestMatcher merely to avoid MVC path semantics if a project has multiple servlets and stricter clarity requirements.**

### 6.6. Running the Project

With Java 17+ and a compatible Gradle version:

~~~bash
gradle test
gradle bootRun
~~~

With the Gradle Wrapper, prefer `./gradlew test` and `./gradlew bootRun`; on Windows use `gradlew.bat test` and `gradlew.bat bootRun`. The project uses Spring Boot dependencies, so running plain `javac` and `java` alone will lack the classpath.

Try on localhost:

~~~bash
curl -i http://localhost:8080/catalog/public/ping
curl -i http://localhost:8080/catalog/products/42
curl -i -u reader:reader-pass \
  http://localhost:8080/catalog/products/42
curl -i -u reader:reader-pass \
  http://localhost:8080/catalog/whoami
curl -i -u reader:reader-pass \
  http://localhost:8080/catalog/admin/report
curl -i -u admin:admin-pass \
  http://localhost:8080/catalog/admin/report
~~~

Structural response of `GET /catalog/whoami` under the default servlet mapping configuration:

~~~json
{
  "requestURI": "/catalog/whoami",
  "contextPath": "/catalog",
  "servletPath": "/whoami",
  "pathInfo": null,
  "queryString": null
}
~~~

This is illustrative output based on the configured mapping, not runtime output executed inside this article. `curl` with `-u` is only for **demo** usernames/passwords; never put real credentials into shell history, process lists, or logs. Production must use HTTPS and proper auth policies.

## 7. Reasoning Through Each Request in the Test Matrix

| External Request | contextPath | servletPath in demo | Authorization matcher | Expected |
| --- | --- | --- | --- | --- |
| GET /catalog/public/ping | /catalog | /public/ping | GET /public/ping → permitAll | 200 |
| GET /catalog/products/42, anonymous | /catalog | /products/42 | GET /products/{id} → scope read | 401 |
| GET /catalog/products/42, reader | /catalog | /products/42 | GET /products/{id} → scope read | 200 |
| GET /catalog/admin/report, reader | /catalog | /admin/report | GET /admin/report → ROLE_ADMIN | 403 |
| GET /catalog/admin/report, admin | /catalog | /admin/report | GET /admin/report → ROLE_ADMIN | 200 |
| GET /catalog/whoami, reader | /catalog | /whoami | GET /whoami → authenticated | 200 |
| GET /catalog/not-configured, reader | /catalog | /not-configured | anyRequest → denyAll | 403 |

When getting a 403, do not jump to the conclusion "wrong path": the matcher may be right while the role/authority is insufficient; a POST can also be blocked by `CsrfFilter` before authorization. You must distinguish **whether the matcher matched**, **which chain was selected**, and **the authorization result**.

## 8. Advanced: DispatcherServlet Mapped Under /mvc/*

This is a **standalone configuration variant**; do not copy it directly into the runnable project in section 6 while ignoring other required changes.

Assume:

~~~properties
server.servlet.context-path=/catalog
spring.mvc.servlet.path=/mvc
~~~

Externally, a controller `@GetMapping("/orders/{id}")` can be called at:

~~~text
/catalog/mvc/orders/42
~~~

When the container uses prefix mapping `/mvc/*`, expected values are:

~~~text
getContextPath() = /catalog
getServletPath() = /mvc
getPathInfo()    = /orders/42
getRequestURI()  = /catalog/mvc/orders/42
~~~

**Note on Spring Boot 3.x:** how the `spring.mvc.servlet.path` prefix interacts with the MVC path matching strategy depends on version and configuration. Some Boot versions require adjusting `spring.mvc.pathmatch.matching-strategy=ant_path_matcher` when using a prefix; check the exact version's documentation and startup tests instead of assuming the prefix property is always compatible with the default PathPatternParser. Therefore, this section presents **how to reason about RequestMatcher and what configuration to inspect**, without claiming integration tests were run for this variant.

### 8.1. Configuring an MVC-Aware Matcher With servletPath

In Spring Security 6, you can create an `MvcRequestMatcher.Builder` from the `HandlerMappingIntrospector` bean and specify servletPath:

~~~java
@Bean
SecurityFilterChain mvcSecurity(
        HttpSecurity http,
        HandlerMappingIntrospector introspector)
        throws Exception {

    MvcRequestMatcher.Builder mvc =
        new MvcRequestMatcher.Builder(introspector)
            .servletPath("/mvc");

    return http
        .authorizeHttpRequests(auth -> auth
            .requestMatchers(mvc.pattern(
                HttpMethod.GET, "/public/ping"))
                .permitAll()
            .requestMatchers(mvc.pattern(
                HttpMethod.GET, "/admin/**"))
                .hasRole("ADMIN")
            .requestMatchers(mvc.pattern(
                HttpMethod.GET, "/orders/{id}"))
                .authenticated()
            .anyRequest().denyAll())
        .httpBasic(Customizer.withDefaults())
        .build();
}
~~~

This is a **code snippet**, requiring imports for `Bean`, `HttpSecurity`, `HandlerMappingIntrospector`, `MvcRequestMatcher`, `HttpMethod`, `Customizer`, and `SecurityFilterChain`. Only use it if the MVC matcher fits the current servlet configuration.

Note the two layers of information:

- `mvc.servletPath("/mvc")` specifies the servlet mapping itself.
- `mvc.pattern("/admin/**")` specifies the MVC path inside the servlet; **do not** write `/catalog/mvc/admin/**`.

If there is another `DispatcherServlet` mapped to `/legacy/*` or a non-MVC servlet, do not assume one builder will match every servlet. Distinguish each servlet path and choose the corresponding matcher.

### 8.2. Comparison With AntPathRequestMatcher

Same request `/catalog/mvc/admin/report` under mapping `/mvc/*`:

~~~text
requestURI     /catalog/mvc/admin/report
contextPath    /catalog
servletPath    /mvc
pathInfo       /admin/report

MvcRequestMatcher (with servletPath("/mvc") set):
  pattern("/admin/**")        -> typically matches per MVC semantics

AntPathRequestMatcher:
  pattern("/mvc/admin/**")    -> matches servletPath + pathInfo
  pattern("/admin/**")        -> does not match in this example
  pattern("/catalog/mvc/admin/**") -> does not match
~~~

Do not mechanically apply `"/admin/**"` to every matcher. When changing matcher types during a Spring Security upgrade, run negative/positive test cases because pattern vocabulary and base paths may change.

### 8.3. Multiple Servlets and Matcher Ambiguity

A web application might run:

- A main DispatcherServlet mapped to `/mvc/*`.
- A legacy servlet mapped to `/legacy/*`.
- A separate admin/internal servlet mapping.

If you use string matchers when the framework does not know which servlet to match, the configuration may be ambiguous or match differently from what you intend. With multiple servlets, solve this with **explicit matchers** per group, inspect `HttpServletMapping`, and write tests verifying servlet path and chain selection. Never resort to "a trick of prepending contextPath to the string" as a general solution.

### 8.4. Do Not Manually Construct a "Full Path" via Substring in Security Filters

The following snippet looks tempting but is error-prone:

~~~java
String path = request.getRequestURI()
    .substring(request.getContextPath().length());

if (path.startsWith("/mvc/admin")) {
    // make permission decisions manually...
}
~~~

It strips the context path as a string, yet leaves many risks: encoding, path separators, path parameters, prefix boundaries where `/mvc/administer` also starts with `/mvc/admin`, trailing slashes, case sensitivity, and URL normalization. That is why Spring Security provides `RequestMatcher` with controlled, testable semantics.

If you need a custom RequestMatcher, define clear logic using standard Servlet APIs/matchers and write tests covering both **positive** and **negative boundary cases**.

## 9. Reverse Proxy and External Prefix: Adding Another Path Layer

When an app sits behind Nginx/Ingress/Gateway, the public URL may differ from the URI received by the servlet container:

~~~text
Client:     https://example.org/gateway/catalog/orders/42
Proxy:      strip /gateway
Upstream:   http://app:8080/catalog/orders/42
Container:  contextPath=/catalog, servletPath=/orders/42
~~~

In this example, **/gateway does not appear in the internal requestURI**. If the proxy *does not* strip the prefix or uses Forwarded/X-Forwarded-Prefix, the Servlet request metadata seen by Spring may differ.

### 9.1. Forwarded Headers Must Not Be Trusted Unconditionally

`Forwarded`, `X-Forwarded-Proto`, `X-Forwarded-Host`, `X-Forwarded-Prefix`, and similar headers can affect scheme/host/path when the framework processes them. Never trust values sent directly by internet clients if the gateway has not stripped or overwritten them.

For trusted infrastructure, Spring Boot provides ways to configure a forwarding strategy, for example:

~~~properties
server.forward-headers-strategy=framework
~~~

This is not "turn it on and it is secure": you need to establish proxy boundaries, header sanitization, URL rewrites, TLS termination, and environment-accurate tests. When debugging, record both the public URL and internal URI (without logging secrets) to avoid confusing boundaries.

### 9.2. Do Not Confuse Context Path With the Externally Displayed Path

Different deployment setups:

- WAR deployed at `/catalog` in Tomcat: contextPath can be `/catalog`.
- Spring Boot embedded server with `server.servlet.context-path=/catalog`: corresponding contextPath.
- Reverse proxy publishes app at `/gateway` while upstream server runs at root: container-side contextPath can still be `""`.
- Proxy configured with forwarding: request wrappers/framework may expose different paths depending on the strategy.

Looking only at the browser address bar is not enough to determine `request.getContextPath()`. Debug from the HTTP request to the container, and only then to the Spring Security matcher.

### 9.3. Generating URLs Inside the Application

When a form or redirect needs to point to a controller, do not hardcode URLs without the context path. In Spring MVC/Thymeleaf, context-aware URL helpers reduce deployment-prefix bugs. However, also test proxy prefixes if the ingress rewrites paths. A URL rendered properly for users **does not** mean `requestMatchers` patterns should use that same public URL.

## 10. Matching and Security: Edge Cases to Test

A matcher that looks right on normal paths can still fail when paths are normalized across multiple layers.

### 10.1. Query, Fragment, and Path Variables

- `GET /catalog/orders/42?sort=asc`: the query `sort=asc` is not a URL path segment for `requestMatchers("/orders/**")` to process.
- `#section` in a URL is not sent by the browser to the server in normal HTTP requests.
- `@GetMapping("/orders/{id}")` has a path variable; the matcher selects the URL scope. **After authentication**, business logic must still verify whether the user is authorized to view that specific `orderId`/tenant.

### 10.2. Encoded Slash, Double Slashes, Semicolons

Check how your environment handles forms like:

~~~text
/catalog/orders/%2F42
/catalog//orders/42
/catalog/orders/42;v=1
/catalog/orders/../admin/report
/catalog/ADMIN/report
~~~

Do not assume all paths above are accepted, decoded, or routed identically by the container: servlet containers, firewalls, proxies, MVC matchers, and Spring Security may reject or normalize them differently. **In particular, do not manually decode a URL a second time to find a "cleaner" path and grant access**. Double decoding/path traversal can lead to bypasses when proxy, firewall, and backend disagree.

Run integration tests against the **real proxy and servlet container** to verify whether requests are rejected or matched properly; unit tests with MockHttpServletRequest are not a full substitute for system testing.

### 10.3. Path-Prefix Boundary

Do not use:

~~~java
path.startsWith("/admin")
~~~

as a security decision if you only intend to match the `/admin/` namespace. It also matches `/administrator` or `/administer`. Use a RequestMatcher with proper segment/pattern parsing, and add negative boundary tests.

### 10.4. Different HTTP Methods

A pattern `"/orders/**"` without specifying an HTTP method can match multiple methods. If only GET grants read permission, do not let that same permission cover POST/DELETE on another controller. For example:

~~~java
.requestMatchers(HttpMethod.GET, "/orders/{id}")
    .hasAuthority("SCOPE_orders.read")
.requestMatchers(HttpMethod.DELETE, "/orders/{id}")
    .hasAuthority("SCOPE_orders.delete")
.anyRequest().denyAll()
~~~

Choose method-aware matchers and test CSRF separately if the application uses cookie-authenticated browsers. CSRF can block POST/DELETE before authorization; it does not replace the delete permission rule.

### 10.5. Dispatcher Types

In Servlet, requests also have `DispatcherType.REQUEST`, `FORWARD`, `ERROR`, `ASYNC`, and `INCLUDE`. A forward/error dispatch can use a different path from the original request. Security filter registrations and matcher policies can affect access to error views or MVC forwards.

Only configure `dispatcherTypeMatchers(...)` based on real requirements and assess the impact. Do not open all paths with `permitAll()` just because an error page returned 403; analyze the dispatcher types, chain, and target URLs.

## 11. Layer-by-Layer Matcher Debugging Workflow

When an endpoint unexpectedly returns 401, 403, or is left open, inspect in order:

1. **What request actually reached the server?** Record the HTTP method, raw requestURI (with secrets filtered), contextPath, servletPath, pathInfo, queryString, and dispatcher type in your learning/test environment.
2. **Which servlet mapping was selected?** Does DispatcherServlet map `/`, `/mvc/*`, or another servlet?
3. **Did a proxy perform rewrites or send forwarded headers?** External URLs and internal paths can differ.
4. **Which RequestMatcher class is in use?** MVC-aware, Ant-style, PathPattern, or custom; do not guess from the string alone.
5. **Which chain matched first?** Check `@Order` and `securityMatcher`, including fallbacks.
6. **Which authorization rule matched first?** Check the order of `requestMatchers` inside the chain.
7. **What was the role/authority/ownership result?** A matching matcher can still deny due to missing permissions.
8. **Did a filter before authorization block it?** CSRF, authentication, request firewall, or HTTPS requirements can contribute.
9. **Did the mock test set contextPath/servletPath/pathInfo accurately?** Incorrect fixtures easily lead to wrong conclusions.
10. **Are encoded paths, trailing slashes, semicolons, or forwards involved?** Re-test on a real container/proxy.
11. **Are any requests falling outside all filter chains?** Add a fallback chain or default deny as needed.
12. **Fix the matchers and add regression tests**, instead of testing only a single happy path.

### 11.1. Controlled DEBUG Logging

In a learning/test environment, you can set:

~~~properties
logging.level.org.springframework.security=DEBUG
~~~

Do not rely on exact log wording staying identical across versions. Never log raw `Authorization`, `Cookie`, session ids, CSRF tokens, passwords, or token contents. Even path metadata logs should be redacted if they contain sensitive identifiers, such as tokens mistakenly placed in URLs.

### 11.2. Diagnostic Table

| Symptom | Possible Cause | Action to Take |
| --- | --- | --- |
| Changing context root causes public endpoint to return 401 | Matcher may have hardcoded context path | Inspect request metadata, remove deployment prefix from MVC matcher |
| `/catalog/mvc/admin/report` returns 404 | MVC servlet mapping/controller mismatch | Check `/mvc/*` mapping and `@GetMapping` |
| Admin chain does not run | `securityMatcher` has wrong prefix or chain order | Identify matcher class/order and test |
| Ant matcher fails on `/orders/**` when servletPath is `/mvc` | Ant path includes `/mvc` + pathInfo | Use the proper Ant pattern or an explicit MVC matcher |
| MVC matcher hits the wrong servlet | Builder did not specify servletPath with multiple servlets | Use appropriate `MvcRequestMatcher.Builder.servletPath` |
| GET works but POST returns 403 | Missing CSRF or method rule denies it | Distinguish CSRF filter from authorization |
| External gateway URL differs from app requestURI | Proxy rewrite/X-Forwarded-Prefix | Inspect upstream request and trusted forwarding |
| MockMvc passes but production fails | Test did not simulate context/servlet/proxy | Fix fixtures and add integration tests |
| Trailing `/` shifts rule matching | Matcher/handler mapping semantics differ | Test trailing slashes and actual patterns |
| `getServletPath()` lacks the after-prefix part | Prefix servlet mapping like `/mvc/*` | Read `getPathInfo()` and use an appropriate matcher |
| Unmatched paths are processed outside Spring Security | No protective fallback chain | Test FilterChainProxy coverage |
| User has valid auth yet still gets 403 | Authority/role/tenant or CSRF | Do not only change the URL pattern |

## 12. Practice Exercises

1. Given URI `/catalog/mvc/orders/42`, context `/catalog`, and mapping `/mvc/*`, write the exact values of `getContextPath()`, `getServletPath()`, and `getPathInfo()`.
2. With the **same URI**, if DispatcherServlet is mapped to `/` instead of `/mvc/*`, which parts of servletPath/pathInfo change?
3. Why is `getContextPath()` equal to `""` when the application runs at the root context rather than `"/"`?
4. Prove that `getRequestURI()` does not include the query string using a request with `?page=2`.
5. Diagram the relationship between public URL, reverse proxy, context path, servlet mapping, and Spring MVC `@GetMapping`.
6. In an app with context `/catalog`, why can `@GetMapping("/products/{id}")` serve `/catalog/products/42` without declaring `/catalog` in the annotation?
7. Does `AntPathRequestMatcher("/orders/**")` match a request with `servletPath="/mvc"` and `pathInfo="/orders/42"`? Why?
8. Create an `MvcRequestMatcher.Builder` with `servletPath("/mvc")` and `pattern("/orders/**")`. Explain which components are included and which are excluded.
9. State the difference between `http.securityMatcher(...)` and `authorizeHttpRequests().requestMatchers(...)`.
10. If a request matches no chain, does `anyRequest().denyAll()` inside a chain that only matches `/mvc/**` protect that request?
11. An app adds a legacy servlet `/legacy/*` alongside DispatcherServlet `/mvc/*`. How would you verify matchers and chains so permissions are not mistakenly granted?
12. How must a MockMvc test for `/catalog/products/42` specify requestURI, contextPath, and servletPath?
13. If a test manually sets `MockHttpServletRequest.setServletPath("/mvc")`, does that prove the production container will always return `"/mvc"`?
14. A URL has fragment `#comments`; does the Servlet API receive the fragment portion?
15. Why should you not write an access check using `requestURI.substring(contextPath.length()).startsWith("/admin")`?
16. When an external proxy uses prefix `/gateway` and strips it before upstream, which pattern should Spring Security consider? How do you verify it?
17. A POST missing a CSRF token returns 403 even though `@PostMapping` and the path matcher are correct; what debugging order should you follow?
18. When upgrading from AntPathRequestMatcher to a newer matcher type, which URI/servlet prefix cases need regression tests?
19. Design tests for encoded slashes, double slashes, path segment traversal, and semicolons to verify the application rejects or handles them consistently.
20. Explain why even after a matcher identifies `/orders/{id}`, the server still needs to check whether the user owns the order and belongs to the right tenant.

## 13. Checklist for Configuring RequestMatcher in Production

- [ ] Know the application's context root in the servlet container, without confusing it with an external proxy prefix.
- [ ] Know whether DispatcherServlet maps `/`, `/mvc/*`, or whether multiple servlet mappings exist.
- [ ] Maintain a table of requestURI/contextPath/servletPath/pathInfo for representative endpoints.
- [ ] Know the exact `RequestMatcher` used and its path semantics for the Spring Security version.
- [ ] Ensure MVC handler mappings and Spring Security matchers use compatible servlet/pattern scopes.
- [ ] Do not include the deployment context path in MVC matchers out of habit.
- [ ] Do not copy Ant matcher patterns to MVC matchers without reviewing servlet prefixes.
- [ ] If multiple servlets exist, explicitly specify servlet paths/matchers and chain boundaries.
- [ ] Provide a fallback `SecurityFilterChain` or policy so unexpected URLs cannot bypass Spring Security.
- [ ] Place specific rules before broad rules; test both chain order and rule order.
- [ ] Include HTTP method conditions in matchers when permissions differ by method.
- [ ] Write positive/negative tests for roles/scopes, anonymous access, and multi-tenant/resource ownership.
- [ ] Ensure MockMvc fixtures accurately simulate contextPath/servletPath/pathInfo; add integration tests through proxy/container for critical cases.
- [ ] Handle encoded/traversal/semicolon/trailing-slash paths consistently across gateway/firewall/MVC.
- [ ] Do not manually parse URLs for permission checks; avoid prefix-boundary bugs and double decoding.
- [ ] Control trusted forwarded headers from the gateway; never trust client-supplied headers.
- [ ] Keep logs and path metadata debugging controlled without leaking tokens/passwords/cookies.
- [ ] Whenever changing context path, servlet mapping, or SecurityMatcher implementation, re-run the full authorization regression test suite.

## 14. Conclusion

**Context path** defines where the application is mounted; **servlet path** and **pathInfo** reflect how the container selects a servlet and the remaining path; **Spring MVC path** is the context DispatcherServlet uses to match controllers. In simple cases, these strings may look identical, but once an app has a servlet prefix or reverse proxy, the differences become a security factor.

To configure Spring Security accurately, first **observe real request metadata**, then **identify the RequestMatcher type**, write patterns according to the matcher's semantics, and verify with tests covering methods, paths, contexts, and servlet prefixes. Finally, ensure no request escapes the filter chains and that authorization rules properly enforce roles, scopes, owners, and tenants. Once you master these boundaries, you can deploy the same application at `/`, `/catalog`, or behind a gateway without accidentally exposing or locking out endpoints.
