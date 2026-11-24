# Multiple DispatcherServlets and Exact Root Path Configuration Requirements

When a Spring MVC Servlet application has multiple `DispatcherServlet`s, each Servlet may be registered at its own URL prefix and have a `WebApplicationContext` containing different controllers/`HandlerMapping`s. A `SecurityFilterChain` matching the wrong path or an `MvcRequestMatcher` referencing the wrong `HandlerMappingIntrospector` can leave endpoints protected by unintended rules.

This lesson focuses on **RequestMatchers and servlet roots**, not merely how to place `@GetMapping`. Scope: Spring Security **Servlet**, Spring MVC, Java 17+, Spring Security 6.x. The example pins Spring Boot 3.3.5 for learning, without claiming it is the newest or still-supported version. For newer releases, read the matcher APIs and migration notes before updating.

## 1. Servlet Mapping Differs From Spring MVC Controller Mapping

Suppose a `ServletContext` registers two servlets:

```text
catalogDispatcher -> /catalog/*
officeDispatcher  -> /office/*
default servlet   -> /           (if the application still has one)

GET /catalog/products -> catalogDispatcher -> @GetMapping("/products")
GET /office/report    -> officeDispatcher  -> @GetMapping("/report")
```

The Servlet container selects the servlet first; the selected servlet then resolves the controller using MVC mappings inside its own context. A Catalog controller with `@GetMapping("/products")` does not automatically have full URL `/products`. The `/catalog` prefix is already defined at **Servlet registration**.

A DispatcherServlet can have its own child `WebApplicationContext`. The root context sees shared services, but does not automatically see every bean living only in another dispatcher's child context. Therefore, a `HandlerMappingIntrospector` from the root or Office context cannot by default represent Catalog controllers.

## 2. Distinguishing contextPath, servletPath, pathInfo, and requestURI

When an app is deployed under context path `/store` and the Catalog servlet maps `/catalog/*`, a typical request looks like:

```text
GET /store/catalog/products/42?view=full

getContextPath() = "/store"
getServletPath() = "/catalog"
getPathInfo()    = "/products/42"
getRequestURI()  = "/store/catalog/products/42"
getQueryString() = "view=full"
```

| Attribute | Meaning | Common Pitfall |
|---|---|---|
| `contextPath` | Root path of the web application | Mistakenly adding `/store` into matchers that inspect app-internal paths |
| `servletPath` | Path segment used by the container to select the Servlet | Assuming it equals `/products/42` even when mapping is `/catalog/*` |
| `pathInfo` | Remaining portion with Servlet prefix mappings | Forgetting this field can be `null` under other mapping styles |
| `requestURI` | URI path typically including contextPath | Taking the raw string and comparing against MVC-relative routes |
| MVC mapping | Path handled by handlers inside the servlet | Treating `@GetMapping("/products")` as the full external URL |

This example uses **prefix mapping**. Default mapping `/`, exact mapping, or extension mapping may split `servletPath/pathInfo` differently. Never fix security logic by guessing a mapping style from an external URL.

## 3. securityMatcher and requestMatchers Are Two Distinct Decisions

`FilterChainProxy` picks the **first SecurityFilterChain matching** the request, in order. Then `AuthorizationFilter` uses `requestMatchers` inside that chain to select permissions. Rules in an unselected chain have zero effect.

```text
GET /office/report
    |
FilterChainProxy
    |
catalogChain.securityMatcher(...) -> false
officeChain.securityMatcher(...)  -> true
    |
officeChain.authorizeHttpRequests(...)
    |
GET /office/report -> hasRole("ADMIN")
```

A common mistake:

```java
// May NOT select the chain when the actual URL is /catalog/products/42.
http.securityMatcher("/products/**")
    .authorizeHttpRequests(auth -> auth
        .requestMatchers("/products/**").authenticated()
        .anyRequest().denyAll());
```

Putting a `hasRole("ADMIN")` rule in a chain that does not match will not protect the request. Without a fallback chain, URLs matching no chain risk falling outside Spring Security. Therefore test both the **chain level** and **authorization level**, not just roles at the controller.

## 4. MVC-Aware Matchers Need the Right MVC Context and servletPath

`MvcRequestMatcher` can use `HandlerMappingIntrospector` to match paths per Spring MVC. With a prefix Servlet mapping:

```java
MvcRequestMatcher.Builder catalogBuilder =
    new MvcRequestMatcher.Builder(catalogIntrospector)
        .servletPath("/catalog");

MvcRequestMatcher getProduct =
    catalogBuilder.pattern(HttpMethod.GET, "/products/{id}");
```

This is an **illustrative code snippet**, not a standalone runnable class. The `catalogIntrospector` variable must be wired to **catalogDispatcher's MVC context**, not arbitrarily grabbed from office or root. `/catalog` is the servletPath, `/products/{id}` is the MVC-relative path, and `/store` (context path) must not be included here.

With multiple Servlets (including non-MVC servlets), a call to `requestMatchers(String...)` is sometimes insufficient for Spring Security to auto-select the right matcher; some versions may reject ambiguous configs at startup. Never fix this with `permitAll("/**")`. Choose explicit matchers and test. In newer versions, check `PathPatternRequestMatcher` and its base path builder if available. Never copy classes from newer versions into an older Boot release assuming they will compile.

If you cannot guarantee an introspector bound to the right child context, using a Servlet-API-based matcher at the root layer is a simple, testable alternative:

```java
RequestMatcher catalog = request ->
    "/catalog".equals(request.getServletPath());

RequestMatcher catalogRead = request ->
    "/catalog".equals(request.getServletPath())
    && "/products".equals(request.getPathInfo())
    && "GET".equals(request.getMethod());
```

This approach **only works for verified prefix Servlet mappings**; never replace it with `startsWith("/catalog")` because that could falsely match `/catalogue`. With dynamic routes, multiple path variables, URL aliases, or a default Servlet, use an appropriate framework matcher and test the entire scope.

## 5. Rules for Configuring Multiple DispatcherServlets

- Clearly inventory every `ServletRegistrationBean`, Servlet name, `/catalog/*`/`/office/*` mapping, and default servlet.
- Determine whether Security config lives in the root or an MVC child context; never assume a root `HandlerMappingIntrospector` knows all child routes.
- With multiple `SecurityFilterChain`s, put `@Order(1)` on specific chains and a **denyAll fallback** after specialized chains; never put a `/**` chain first.
- Within each chain, put specific method/path matchers first and `anyRequest().denyAll()` last. Do not rely on an existing 404/405 as a security policy.
- If you only want to protect MVC routes under `/catalog/*`, check both `servletPath` and `pathInfo` appropriately; if matching the whole servlet root, security rules must not over-grant permissions.
- `HEAD` is not automatically authorized just because an MVC GET handler can serve HEAD. `OPTIONS` requires proper CORS preflight policy; never open `permitAll("/**")` to work around CORS.
- With browser cookies/sessions and HTTP Basic, evaluate CSRF against the real trust boundary; a 403 from CSRF differs from a 403 from missing roles.
- If a proxy strips `/app`, the server may never see that prefix. Never treat client-supplied forwarded headers as authorization input; configure trusted proxies and verify the effective Servlet path.
- Never parse URL-encoded slashes, double slashes, `..`, or `;` manually with substrings in place of `HttpFirewall`/MVC path matching.

## 6. Runnable Example With Java 17+ and **Two Real DispatcherServlets**

The project uses Spring Boot 3.3.5 / Spring Security managed by Boot and Maven. The Catalog servlet registers `/catalog/*`, and the Office servlet `/office/*`. The root Spring Security config uses **RequestMatcher lambdas** to check `servletPath` and route, avoiding guessing the MVC context. HTTP Basic is only for testing 401/403 statuses. The example uses two dummy users; never use these credentials outside localhost/HTTPS tests.

### 6.1. Structure

```text
multi-servlet-security/
├── pom.xml
└── src/
    ├── main/java/
    │   ├── demo/main/
    │   │   ├── App.java
    │   │   ├── ServletRegistrations.java
    │   │   └── SecurityConfig.java
    │   └── demo/child/
    │       ├── catalog/CatalogMvc.java
    │       └── office/OfficeMvc.java
    └── test/java/demo/main/MultiServletTest.java
```

The two MVC configs live in `demo.child.*` **outside the root package scan** `demo.main`, so Boot does not accidentally register their controllers into the default DispatcherServlet.

### 6.2. pom.xml

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>
    <groupId>demo</groupId>
    <artifactId>multi-servlet-security</artifactId>
    <version>1.0.0</version>
    <properties><java.version>17</java.version></properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-security</artifactId>
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

### 6.3. Spring Boot Main

`src/main/java/demo/main/App.java`:

```java
package demo.main;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class App {
    public static void main(String[] args) {
        SpringApplication.run(App.class, args);
    }
}
```

### 6.4. Servlet Registrations

`src/main/java/demo/main/ServletRegistrations.java`:

```java
package demo.main;

import demo.child.catalog.CatalogMvc;
import demo.child.office.OfficeMvc;
import org.springframework.boot.web.servlet.ServletRegistrationBean;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.context.support.AnnotationConfigWebApplicationContext;
import org.springframework.web.servlet.DispatcherServlet;

@Configuration
public class ServletRegistrations {

    @Bean
    ServletRegistrationBean<DispatcherServlet> catalogServlet() {
        AnnotationConfigWebApplicationContext ctx =
            new AnnotationConfigWebApplicationContext();
        ctx.register(CatalogMvc.class);
        ServletRegistrationBean<DispatcherServlet> bean =
            new ServletRegistrationBean<>(
                new DispatcherServlet(ctx), "/catalog/*");
        bean.setName("catalogDispatcher");
        bean.setLoadOnStartup(1);
        return bean;
    }

    @Bean
    ServletRegistrationBean<DispatcherServlet> officeServlet() {
        AnnotationConfigWebApplicationContext ctx =
            new AnnotationConfigWebApplicationContext();
        ctx.register(OfficeMvc.class);
        ServletRegistrationBean<DispatcherServlet> bean =
            new ServletRegistrationBean<>(
                new DispatcherServlet(ctx), "/office/*");
        bean.setName("officeDispatcher");
        bean.setLoadOnStartup(1);
        return bean;
    }
}
```

Each `DispatcherServlet` receives its own `AnnotationConfigWebApplicationContext`. The Servlet registration applies the prefix in the container; MVC controllers inside the child context use paths relative to the Servlet mapping.

### 6.5. Catalog MVC Context

`src/main/java/demo/child/catalog/CatalogMvc.java`:

```java
package demo.child.catalog;

import jakarta.servlet.http.HttpServletRequest;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.servlet.config.annotation.EnableWebMvc;

@Configuration
@EnableWebMvc
public class CatalogMvc {

    @Bean
    CatalogController catalogController() {
        return new CatalogController();
    }

    @RestController
    public static class CatalogController {
        @GetMapping("/products")
        public String products(HttpServletRequest request) {
            return "CATALOG:" + request.getServletPath()
                + ":" + request.getPathInfo();
        }
    }
}
```

### 6.6. Office MVC Context

`src/main/java/demo/child/office/OfficeMvc.java`:

```java
package demo.child.office;

import jakarta.servlet.http.HttpServletRequest;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.servlet.config.annotation.EnableWebMvc;

@Configuration
@EnableWebMvc
public class OfficeMvc {

    @Bean
    OfficeController officeController() {
        return new OfficeController();
    }

    @RestController
    public static class OfficeController {
        @GetMapping("/report")
        public String report(HttpServletRequest request) {
            return "OFFICE:" + request.getServletPath()
                + ":" + request.getPathInfo();
        }
    }
}
```

Controllers return actual Servlet paths for testing. Do not expose unnecessary internal routing info in production responses.

### 6.7. SecurityConfig

`src/main/java/demo/main/SecurityConfig.java`:

```java
package demo.main;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.util.matcher.RequestMatcher;

@Configuration
public class SecurityConfig {

    private static RequestMatcher servlet(String path) {
        return request -> path.equals(request.getServletPath());
    }

    private static RequestMatcher route(
            String servletPath, String pathInfo, String method) {
        return request ->
            servletPath.equals(request.getServletPath())
                && pathInfo.equals(request.getPathInfo())
                && method.equals(request.getMethod());
    }

    @Bean
    PasswordEncoder encoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
            User.withUsername("viewer")
                .password(encoder.encode("viewer-demo"))
                .roles("VIEWER")
                .build(),
            User.withUsername("admin")
                .password(encoder.encode("admin-demo"))
                .roles("ADMIN")
                .build()
        );
    }

    @Bean
    @Order(1)
    SecurityFilterChain catalogChain(HttpSecurity http) throws Exception {
        return http
            .securityMatcher(servlet("/catalog"))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(route("/catalog", "/products", "GET"))
                    .hasAnyRole("VIEWER", "ADMIN")
                .requestMatchers(route("/catalog", "/products", "HEAD"))
                    .hasRole("ADMIN")
                .anyRequest().denyAll())
            .httpBasic(Customizer.withDefaults())
            .formLogin(AbstractHttpConfigurer::disable)
            .build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain officeChain(HttpSecurity http) throws Exception {
        return http
            .securityMatcher(servlet("/office"))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(route("/office", "/report", "GET"))
                    .hasRole("ADMIN")
                .anyRequest().denyAll())
            .httpBasic(Customizer.withDefaults())
            .formLogin(AbstractHttpConfigurer::disable)
            .build();
    }

    @Bean
    @Order(3)
    SecurityFilterChain fallbackChain(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth.anyRequest().denyAll())
            .httpBasic(Customizer.withDefaults())
            .formLogin(AbstractHttpConfigurer::disable)
            .build();
    }
}
```

Explanation:

1. The Catalog chain is selected only when the Servlet API reports `servletPath=/catalog`, and Office when `/office`. With other mapping styles, adjust the logic.
2. Authorization compares **all three**: `servletPath`, `pathInfo`, and HTTP method; undeclared requests hit `denyAll()`.
3. Viewer may GET Catalog but not GET Office. Admin may GET Office and HEAD Catalog. GET does not automatically grant HEAD.
4. The fallback chain at the end blocks URLs outside both servlets. Putting the fallback earlier would shadow specialized rules.
5. `httpBasic` produces 401 when credentials are missing/wrong. CSRF is not disabled; the example uses GET/HEAD with no state-mutating operations.
6. Example passwords are hashed with BCrypt. HTTP Basic transmits credentials on each request, so HTTPS is mandatory in real environments; demo accounts must never be shipped to production.

### 6.8. Integration Tests on the Embedded Servlet Container

`src/test/java/demo/main/MultiServletTest.java`:

```java
package demo.main;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.http.HttpEntity;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class MultiServletTest {
    @Autowired
    TestRestTemplate http;

    @Test
    void anonymousNeedsAuthentication() {
        assertThat(http.getForEntity("/catalog/products", String.class)
            .getStatusCode()).isEqualTo(HttpStatus.UNAUTHORIZED);
    }

    @Test
    void viewerHitsTheCorrectCatalogServlet() {
        ResponseEntity<String> r = http.withBasicAuth("viewer", "viewer-demo")
            .getForEntity("/catalog/products", String.class);

        assertThat(r.getStatusCode()).isEqualTo(HttpStatus.OK);
        assertThat(r.getBody()).isEqualTo("CATALOG:/catalog:/products");
    }

    @Test
    void viewerCannotUseOfficeChain() {
        assertThat(http.withBasicAuth("viewer", "viewer-demo")
            .getForEntity("/office/report", String.class).getStatusCode())
            .isEqualTo(HttpStatus.FORBIDDEN);
    }

    @Test
    void adminHitsTheCorrectOfficeServlet() {
        ResponseEntity<String> r = http.withBasicAuth("admin", "admin-demo")
            .getForEntity("/office/report", String.class);

        assertThat(r.getStatusCode()).isEqualTo(HttpStatus.OK);
        assertThat(r.getBody()).isEqualTo("OFFICE:/office:/report");
    }

    @Test
    void headIsNotSilentlyGrantedByGetRule() {
        ResponseEntity<String> viewer =
            http.withBasicAuth("viewer", "viewer-demo").exchange(
                "/catalog/products", HttpMethod.HEAD,
                HttpEntity.EMPTY, String.class);

        ResponseEntity<String> admin =
            http.withBasicAuth("admin", "admin-demo").exchange(
                "/catalog/products", HttpMethod.HEAD,
                HttpEntity.EMPTY, String.class);

        assertThat(viewer.getStatusCode()).isEqualTo(HttpStatus.FORBIDDEN);
        assertThat(admin.getStatusCode()).isEqualTo(HttpStatus.OK);
    }

    @Test
    void otherPathsAndServeltsAreDenied() {
        TestRestTemplate admin = http.withBasicAuth("admin", "admin-demo");
        assertThat(admin.getForEntity("/catalog/report", String.class)
            .getStatusCode()).isEqualTo(HttpStatus.FORBIDDEN);
        assertThat(admin.getForEntity("/office/products", String.class)
            .getStatusCode()).isEqualTo(HttpStatus.FORBIDDEN);
        assertThat(admin.getForEntity("/unmapped/report", String.class)
            .getStatusCode()).isEqualTo(HttpStatus.FORBIDDEN);
    }

    @Test
    void invalidPasswordIsRejected() {
        assertThat(http.withBasicAuth("viewer", "wrong-password")
            .getForEntity("/catalog/products", String.class).getStatusCode())
            .isEqualTo(HttpStatus.UNAUTHORIZED);
    }
}
```

**Expectation:** 7 tests pass when files are placed properly, the embedded Servlet container starts, and Maven dependencies resolve. Results **have not been executed inside this article**; these are assertions for the learner to run. The tests use `RANDOM_PORT` to verify real Servlet container mappings, not just a `MockMvc` attached to a default DispatcherServlet.

The tests verify both path boundaries and HTTP methods: GET Catalog with the right role, isolated Office, unknown URLs blocked by denyAll, and HEAD not silently inheriting GET permissions. The controllers returning `CATALOG:/catalog:/products` and `OFFICE:/office:/report` prove how `servletPath`/`pathInfo` are split under the registered Servlet prefix mappings.

Run in the directory containing `pom.xml`:

```bash
java -version
mvn -version
mvn test
mvn spring-boot:run
```

When the dev server runs on port 8080 (if free):

```bash
curl -i http://localhost:8080/catalog/products
curl -i -u viewer:viewer-demo http://localhost:8080/catalog/products
curl -i -u viewer:viewer-demo http://localhost:8080/office/report
curl -i -u admin:admin-demo http://localhost:8080/office/report
```

Expected statuses: `401`, `200` with body `CATALOG:/catalog:/products`, `403`, and `200` with body `OFFICE:/office:/report`. Never use fixture passwords in public environments or in shell history containing real credentials.

## 7. Testing Non-Root Context Paths and Reverse Proxies

If configured with:

```properties
server.servlet.context-path=/store
```

external URLs become `/store/catalog/products` and `/store/office/report`. With the prefix mappings above, the Servlet API typically still returns:

```text
contextPath = "/store"
servletPath = "/catalog" or "/office"
pathInfo   = "/products" or "/report"
```

Therefore **do not** change `servlet("/catalog")` to `servlet("/store/catalog")`. To test a non-root context path, use a dedicated test profile and send requests containing `/store` in the URL; never run a root-path test suite against the wrong URL and conclude the matcher is buggy.

If a reverse proxy exposes external URL `/app/catalog/products` and strips `/app` before forwarding to Tomcat, the Servlet container may only see `/catalog/products`. If the proxy does not strip it, configure the context path accordingly. Forwarded headers can help with redirects and link generation, but require a trust boundary; never trust client-supplied headers for authorization decisions.

## 8. Common Issues and How to Handle Them

| Symptom | Possible Cause | How to Verify |
|---|---|---|
| MVC controller exists yet request returns 403 | Authorization chain matches wrong root or hits denyAll | Safely log selected chain; test servletPath/pathInfo |
| ADMIN rule does not take effect | Another chain matched first, or route matcher is wrong | Check `@Order` and both matcher levels |
| URL outside any servlet still returns 200 | Missing fallback chain or incomplete Servlet Filter registration | Test unknown URLs and default servlet |
| Server startup reports ambiguous MVC/Servlet matcher | Multiple servlets make auto-matcher selection ambiguous | Pick explicit matcher types, configure servletPath properly |
| Changing context path breaks endpoint access | Matcher wrongly included contextPath or client calls old URL | Distinguish contextPath from servletPath |
| Same pathInfo under different servlet has wrong role | Did not check servletPath | Test `/catalog/report` and `/office/report` independently |
| HEAD differs from GET | Security rule is method-specific | Test HEAD explicitly rather than inferring from GET |
| POST returns 403 despite valid role | Possibly missing CSRF token | Keep CSRF and test permissions with a valid token |
| Redirect has wrong host/path behind proxy | Misconfigured forwarded headers, context path, or proxy rewrite | Inspect proxy config and effective request path |
| Valid role accesses another tenant's data | Only URL protection without object-level authorization | Enforce permissions at service/resource layer |
| MockMvc passes but real deployment fails | MockMvc did not simulate child Servlet registrations | Run integration tests through a real container |

**Never turn a routing bug into an excuse to disable CSRF, the firewall, or authorization.** When observability is needed, enable `org.springframework.security` logging at DEBUG in development, without logging raw passwords, cookies, session IDs, or Authorization headers.

## 9. Checklist and Self-Check Questions

- [ ] Inventoried every DispatcherServlet, name, mapping, MVC context, and Servlet Filter registration.
- [ ] Confirmed `contextPath`/`servletPath`/`pathInfo` values on actual requests.
- [ ] Selected the right `MvcRequestMatcher` with the right MVC context's introspector, or an explicit Servlet-level matcher.
- [ ] Verified `securityMatcher` and `requestMatchers` separately.
- [ ] Placed specialized chains before the fallback; undeclared rules hit denyAll.
- [ ] Tested identical `pathInfo` across different Servlet prefixes and different HTTP methods.
- [ ] Included tests for unknown URLs, non-root context paths, proxy rewrites, and dispatcher types if used.
- [ ] Tested CSRF/CORS and resource-level authorization independently from URL matching.
- [ ] Used embedded Servlet container integration tests to verify real Servlet mappings.

**Q1.** For `/store/catalog/products`, app context path `/store`, and Servlet mapping `/catalog/*`, what is `servletPath`?  
**Answer:** Typically `/catalog`; `pathInfo` is `/products`.

**Q2.** Should `MvcRequestMatcher.Builder.servletPath("/catalog")` include `/store`?  
**Answer:** No. `/store` is the application's `contextPath`.

**Q3.** Why is `getRequestURI().startsWith("/products")` error-prone?  
**Answer:** The URI may contain `contextPath` and the servlet prefix, differing from MVC-relative paths.

**Q4.** What happens if `securityMatcher` does not match, even if `authorizeHttpRequests` has `hasRole("ADMIN")`?  
**Answer:** Rules inside an unselected chain do not run.

**Q5.** Why cannot the root `HandlerMappingIntrospector` automatically serve every DispatcherServlet?  
**Answer:** Each servlet can have its own child MVC context and handler mappings.

**Q6.** Why is a denyAll fallback needed?  
**Answer:** So URLs on the default or other servlets do not accidentally fall outside defined SecurityFilterChains.

**Conclusion:** With **multiple DispatcherServlets**, you must clearly understand **Servlet registration mappings**, **MVC-relative controller paths**, and **which part of the URL the Security RequestMatcher inspects**. Configure `servletPath` accurately, use an introspector from the matching MVC context when needed, order chains properly, and test real requests through the container — that is the foundation for avoiding misprotected or missed endpoints.