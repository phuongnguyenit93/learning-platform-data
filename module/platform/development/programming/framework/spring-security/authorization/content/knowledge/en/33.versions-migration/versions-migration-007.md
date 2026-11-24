# Migrating antMatchers, mvcMatchers, and RequestMatcher Across Spring Security Versions

## 1. Objectives and Context

Spring Security authorizes HTTP traffic by **matching a request** against a path pattern, HTTP method, or custom condition, and then verifying the caller's roles/permissions. Across version upgrades, many projects must replace `antMatchers(...)` and `mvcMatchers(...)` with `requestMatchers(...)`. By Spring Security 7, the default matching mechanism shifts further to `PathPatternRequestMatcher`. Replacing the method name is only the first step: the same pattern string can be interpreted differently by Ant, Spring MVC, or PathPattern.

Suppose a reporting system requires:

- GET /api/reports/42: must have authority `report:read`.
- POST /api/reports/42/publish: must have authority `report:publish`.
- A logged-in user with only `report:read` must not publish.
- Undeclared paths and HTTP methods must not be opened automatically.

If a migration accidentally turns the publish rule into `authenticated()`, compilation may succeed while the business policy is already broken. You must **verify both matching accuracy and allow/deny decisions**.

After this lesson, you will be able to explain the differences among the `RequestMatcher` interface, the legacy DSL methods `antMatchers`/`mvcMatchers`, the new `requestMatchers` DSL, the `securityMatcher` chain selector, and the implementations `AntPathRequestMatcher`, `MvcRequestMatcher`, and `PathPatternRequestMatcher`. You will also be able to write Java 17+ code and regression tests to move from Spring Security 5.8 through 6.x to 7.x.

**Scope:** Spring MVC/Servlet. Spring WebFlux applications use `SecurityWebFilterChain` and `ServerWebExchangeMatcher`, and do not directly use the Servlet matchers illustrated here.

## 2. Version Map from 5.x to 7.x

| Version | Key API / Implementation | Action Required |
| --- | --- | --- |
| 5.7 and earlier | `antMatchers`, `mvcMatchers`, `regexMatchers` common in `authorizeRequests`; many apps still use `WebSecurityConfigurerAdapter` | Inventory legacy configs, rule order, servlet paths, and custom matchers |
| **5.8** | `antMatchers`/`mvcMatchers`/`regexMatchers` deprecated; new `requestMatchers` available | Migrate each rule to `requestMatchers` on the 5.8 line before upgrading to 6.0 and compare behavior |
| **6.0–6.4** | DSL methods `antMatchers`/`mvcMatchers` removed; use `SecurityFilterChain`, `authorizeHttpRequests`, `requestMatchers` | Update code and Jakarta Servlet imports; distinguish MVC/Ant inference in String overloads |
| **6.5** | `PathPatternRequestMatcher` available; `AntPathRequestMatcher` and `MvcRequestMatcher` deprecated for removal | Gradually switch to explicit `PathPatternRequestMatcher` and run tests on 6.5 |
| **7.x** | `AntPathRequestMatcher` and `MvcRequestMatcher` no longer supported; Java DSL matchers default to `PathPatternRequestMatcher` | Remove old imports/classes; check leading `/` in URLs, servlet prefixes, wildcards, and permission policies |

**Historical distinction:** The configuration method **`antMatchers(...)`** disappeared in Spring Security 6.0, whereas the **`AntPathRequestMatcher` class** remained present through most of 6.x and was only dropped in 7. Likewise, **`RequestMatcher`** remains an **interface**; only the ways to construct matchers and some implementations changed.

When upgrading from Spring Security 5.x to 6.x, also account for Spring Framework 6, **`javax.servlet → jakarta.servlet`**, and the Spring Boot 3.x dependency set. Migrating matchers does not replace a full framework upgrade plan; this lesson limits its focus to Servlet access control.

## 3. Decision Model: A Request Passes Through Two Matcher Levels

~~~text
HTTP request
     |
     v
FilterChainProxy
     |
     +-- securityMatcher of each SecurityFilterChain in @Order sequence
     |       |
     |       +-- first matching chain is selected
     |       +-- no chain matches: request is not protected by any Spring Security chain
     |
     v
AuthorizationFilter inside the selected chain
     |
     +-- requestMatchers(...) in declaration order
     |       |
     |       +-- first matching rule: hasAuthority / hasRole / permitAll / denyAll
     |       +-- anyRequest(): policy for the remainder
     |
     v
Controller / business logic (if permitted)
~~~

**securityMatcher** filters whether **the entire SecurityFilterChain** applies to the request. **requestMatchers** inside `authorizeHttpRequests` only select **authorization rules** once that chain has been chosen. Placing `anyRequest().denyAll()` inside a chain that only matches `/api/**` **does not mean** `/admin/**` requests are blocked, because that chain never handles `/admin`.

**RequestMatcher** is an interface with `matches(HttpServletRequest)` that determines whether a request satisfies a condition. It does not evaluate what authorities the user holds. **AuthorizationManager** or rules like `hasAuthority`/`hasRole` make the permission decision after the matcher selects the region.

Watch out for two ordering levels: **the order of SecurityFilterChains** and **the order of requestMatchers** inside each chain. An overly broad matcher placed before a sensitive matcher can prevent downstream rules from ever being evaluated.

## 4. Migrating Legacy APIs in Spring Security 5.8 and 6.x

### 4.1. Identifying legacy code

In a Spring Security 5.7 project, this configuration may appear:

~~~java
// Legacy Spring Security 5.x snippet, not for 6.x/7.x.
http.authorizeRequests(auth -> auth
    .antMatchers(HttpMethod.GET, "/api/reports/**")
        .hasAuthority("report:read")
    .antMatchers(HttpMethod.POST, "/api/reports/*/publish")
        .hasAuthority("report:publish")
    .anyRequest().denyAll()
);
~~~

On the 5.8 line, the old methods were marked deprecated. You can switch them to `requestMatchers` before upgrading to 6.x:

~~~java
// Snippet for 5.8+ / 6.x.
http.authorizeHttpRequests(auth -> auth
    .requestMatchers(HttpMethod.GET, "/api/reports/**")
        .hasAuthority("report:read")
    .requestMatchers(HttpMethod.POST, "/api/reports/*/publish")
        .hasAuthority("report:publish")
    .anyRequest().denyAll()
);
~~~

The `report:read` and `report:publish` permissions are preserved. However, **the matcher type chosen by `requestMatchers(String...)` in 6.x can differ** from the Ant matcher used by old `antMatchers`. According to Spring Security 6.x documentation, when Spring MVC is on the classpath, the String-based matcher builder may pick `MvcRequestMatcher`; without MVC, it may pick `AntPathRequestMatcher`. When multiple servlets exist or inference is insufficiently precise, pass an explicit `RequestMatcher`.

**Do not assume:** `requestMatchers("/foo/**")` equals `antMatchers("/foo/**")` in every detail of path normalization, slashes, servlet prefixes, or path variables. Differences must be measured with tests in each application.

### 4.2. authorizeRequests and authorizeHttpRequests

Many migrations also convert `authorizeRequests` to **`authorizeHttpRequests`**, using `AuthorizationManager` and `AuthorizationFilter`. For example:

~~~java
// New configuration: inside a SecurityFilterChain bean method.
http.authorizeHttpRequests(auth -> auth
    .requestMatchers("/api/admin/**").hasRole("ADMIN")
    .requestMatchers("/api/**").authenticated()
    .anyRequest().denyAll()
);
~~~

In the example, the `/api/admin/**` rule must stand **before** the `/api/**` rule. If reversed, a regular logged-in user passes the `authenticated()` rule before the ADMIN rule is ever checked. Switching DSLs does not automatically fix this ordering bug.

**hasRole("ADMIN")** is normally interpreted as authority `ROLE_ADMIN`; **hasAuthority("report:read")** checks the exact authority string. Never replace specific permissions with `authenticated()` just to simplify migration.

### 4.3. Old → new mapping by purpose

| Purpose | Pre-6.0 API | 5.8/6.x | 6.5+/7.x Target |
| --- | --- | --- | --- |
| URL matching | `antMatchers("/admin/**")` | `requestMatchers("/admin/**")` | `requestMatchers(PathPatternRequestMatcher.withDefaults().matcher("/admin/**"))` |
| URL + HTTP method | `antMatchers(GET, "/items/**")` | `requestMatchers(GET, "/items/**")` | `requestMatchers(path.matcher(GET, "/items/**"))` |
| Spring MVC route | `mvcMatchers("/orders/{id}")` | `requestMatchers("/orders/{id}")` or explicit `MvcRequestMatcher` during 6.x | `PathPatternRequestMatcher` with explicit servlet path |
| Regex | `regexMatchers("/x/[0-9]+")` | `requestMatchers(RegexRequestMatcher.regexMatcher("/x/[0-9]+"))` | Can continue using `RegexRequestMatcher` when regex is needed |
| Custom RequestMatcher | Custom-implemented matcher | `requestMatchers(customMatcher)` | Keep `RequestMatcher` interface, upgrade `javax` to `jakarta`, and test |
| Selecting security chain | `antMatcher(...)` / old way in `HttpSecurity` | `securityMatcher(...)` | `securityMatcher(PathPatternRequestMatcher)` when explicitness is needed |
| Default | `anyRequest()` | `anyRequest()` | Keep `denyAll` or `authenticated` per approved policy |

**Note:** In Spring Security 6.x, anyone needing to preserve exact legacy Ant matcher semantics can pass an explicit `AntPathRequestMatcher` as a transitional step. However, that approach is **not for a Spring Security 7 target** because `AntPathRequestMatcher` is no longer supported there.

### 4.4. Details easily missed when only renaming

- Old code might use **`mvcMatchers`** because controller/servlet path matching semantics were required, not just out of naming habit.
- Code with **`antMatchers(HttpMethod.GET,...)`** must not be changed to `requestMatchers("...")` and accidentally drop the HTTP method constraint.
- A Regex matcher must not be given an Ant pattern **`/**`** expecting regex to interpret it like Ant.
- An admin path shadowed by `/**` or `/api/**` is a severe authorization flaw.
- Matchers inside **custom filters** or login/logout processing URLs may require separate updates even after `authorizeHttpRequests` has been upgraded.

## 5. PathPatternRequestMatcher: Preparing for Spring Security 7

### 5.1. Explicit usage in Spring Security 6.5+

Example with exact URLs and HTTP methods:

~~~java
// Snippet used inside a Spring Security 6.5+ SecurityFilterChain.
PathPatternRequestMatcher.Builder path =
        PathPatternRequestMatcher.withDefaults();

http.authorizeHttpRequests(auth -> auth
    .requestMatchers(path.matcher(HttpMethod.GET, "/api/reports/{id}"))
        .hasAuthority("report:read")
    .requestMatchers(
        path.matcher(HttpMethod.POST, "/api/reports/{id}/publish"))
        .hasAuthority("report:publish")
    .anyRequest().denyAll()
);
~~~

`PathPatternRequestMatcher` is available in Spring Security 6.5 and is used by default in the Java DSL in Spring Security 7. Using it explicitly in 6.5 lets you test behavioral changes before upgrading dependencies.

Here **`matcher("/a")`** matches a path, and **`matcher(HttpMethod.POST, "/a")`** also constrains the HTTP method. With the builder, patterns start with **`/`** and exclude the application's context path. Paths to a non-root servlet may need the servlet prefix added via `basePath`.

### 5.2. PathPattern syntax is not identical to Ant-style

| Pattern | Meaning |
| --- | --- |
| `/reports` | One specific path only |
| `/reports/*` | One segment beneath `/reports` |
| `/reports/{id}` | One segment named `id` |
| `/reports/**` | `/reports` and subpaths under PathPattern semantics |
| `/reports/{id}/publish` | Publish path for a specific `id` |
| `/assets/{*rest}` | Captures the remaining path at the end of a pattern when needed |

**Do not mechanically convert** Ant patterns with `**` in the middle of a path, such as `/api/**/admin`, to PathPattern. `PathPatternParser` restricts where multi-segment wildcards can appear; redesign the scope or use another appropriate matcher. Broader path patterns can also alter permissions: `/api/reports/**` covers more actions than `/api/reports/{id}`.

Behavior for **`/reports`** vs. **`/reports/`** (trailing slash), URL-encoded characters, semicolons, and path handling can vary by Spring Framework version, MVC configuration, and matcher type. When clients use such variants, record explicit expectations and test each case.

### 5.3. Context path vs. servlet path

Suppose the app is deployed at **context path `/portal`**, `DispatcherServlet` is mapped at **`/mvc`**, and the controller has `@GetMapping("/orders/{id}")`. The external URI is **`/portal/mvc/orders/42`**.

For `PathPatternRequestMatcher`, **`/portal` is the context path and must be excluded from the pattern**. You can specify the servlet path using the builder:

~~~java
// Spring Security 6.5+/7.x snippet.
PathPatternRequestMatcher.Builder mvc =
        PathPatternRequestMatcher.withDefaults().basePath("/mvc");

http.authorizeHttpRequests(auth -> auth
    .requestMatchers(mvc.matcher(HttpMethod.GET, "/orders/{id}"))
        .hasAuthority("order:read")
    .anyRequest().denyAll()
);
~~~

This matches the path **including the `/mvc` servlet prefix** while **excluding `/portal` from the pattern**. If `/portal` is mistakenly included in the matcher, the rule may fail to match in live runs. Test with requests carrying exact `contextPath`/`servletPath`, not just root-path `MockMvc` calls.

In Spring Security 5.8/6.x, a configuration using `MvcRequestMatcher` with `HandlerMappingIntrospector` and a custom `servletPath` may look like:

~~~java
// Illustrative for 5.8/6.x only; not for Spring Security 7.
MvcRequestMatcher.Builder mvc =
        new MvcRequestMatcher.Builder(handlerMappingIntrospector)
                .servletPath("/mvc");

http.authorizeHttpRequests(auth -> auth
    .requestMatchers(mvc.pattern(HttpMethod.GET, "/orders/{id}"))
        .hasAuthority("order:read")
    .anyRequest().denyAll()
);
~~~

This is a **non-standalone snippet**: `handlerMappingIntrospector` must come from an appropriate Spring MVC application context, and `MvcRequestMatcher` must be imported. This setup shows why dropping `mvc` from the API without considering servlet prefixes can alter matching. When moving to 7.x, use `PathPatternRequestMatcher.Builder`.

### 5.4. Testing 7.x readiness while still on 6.5

The 7 migration docs allow opting into default `PathPatternRequestMatcher` usage via a `PathPatternRequestMatcherBuilderFactoryBean` bean on Spring Security 6.5:

~~~java
// Spring Security 6.5 - bean to prepare 7.x compatibility.
@Bean
PathPatternRequestMatcherBuilderFactoryBean requestMatcherBuilder() {
    return new PathPatternRequestMatcherBuilderFactoryBean();
}
~~~

This snippet requires importing the class from **`org.springframework.security.config.web`**. The bean affects matchers **created by the DSL**; it does not automatically replace places in the project that manually instantiate `AntPathRequestMatcher` or `MvcRequestMatcher`. After enabling it, run full regression tests before changing runtime versions.

`PathPatternRequestMatcher` must also align with the **`PathPatternParser`** used by Spring MVC's `HandlerMapping`. If the project customizes the MVC parser, verify and align them rather than blindly relying on defaults.

## 6. The RequestMatcher Interface and Custom Matchers

### 6.1. Do not equate the interface with legacy classes

**RequestMatcher** remains an interface in Spring Security 7. You can use built-in implementations, provide a lambda, or write a custom class. Example explicit PathPattern matcher:

~~~java
// 6.5+ snippet.
RequestMatcher reports = PathPatternRequestMatcher.withDefaults()
        .matcher(HttpMethod.GET, "/api/reports/{id}");

http.authorizeHttpRequests(auth -> auth
    .requestMatchers(reports).hasAuthority("report:read")
    .anyRequest().denyAll()
);
~~~

`RequestMatcher` **only matches**; `AuthorizationManager` makes the authorization decision. If the goal is "user has `report:read`," put that condition in `hasAuthority` or a manager instead of hiding role checks inside `matches(...)`.

### 6.2. RegexRequestMatcher

When regex is truly necessary, provide an explicit matcher object:

~~~java
// Snippet; requires importing RegexRequestMatcher and RequestMatcher.
RequestMatcher digits =
        RegexRequestMatcher.regexMatcher("/api/reports/[0-9]+");

http.authorizeHttpRequests(auth -> auth
    .requestMatchers(digits).hasAuthority("report:read")
    .anyRequest().denyAll()
);
~~~

Do not treat Ant `/**` strings and regex as having the same syntax. Verify how the matcher evaluates paths, query strings, and methods in your specific version; if the regex expression does not restrict the method, a GET rule could inadvertently expose other HTTP methods. Use a method-aware matcher or build a `RequestMatcher` specifying both path and method.

### 6.3. Combining query parameter conditions

For `GET /api/reports/42?print=true`, a user might also need `report:print`. A plain path matcher only inspects the path; you can combine a query condition:

~~~java
// Spring Security 6.5+ snippet; requires importing AndRequestMatcher.
PathPatternRequestMatcher.Builder paths =
        PathPatternRequestMatcher.withDefaults();

RequestMatcher printRequest = new AndRequestMatcher(
        paths.matcher(HttpMethod.GET, "/api/reports/{id}"),
        request -> "true".equals(request.getParameter("print"))
);

http.authorizeHttpRequests(auth -> auth
    .requestMatchers(printRequest).hasAuthority("report:print")
    .requestMatchers(paths.matcher(HttpMethod.GET, "/api/reports/{id}"))
        .hasAuthority("report:read")
    .anyRequest().denyAll()
);
~~~

The print condition must precede the general read rule; if reversed, a request with `print=true` matches the read rule first and skips the `report:print` requirement. This illustrates how **matcher order** directly impacts authorization.

Never trust client-supplied role, `userId`, or `tenantId` parameters as authorization sources unless verified/authenticated. If printing is a sensitive business action, consider a dedicated endpoint and service-layer checks.

## 7. Complete JUnit 5 Example for Spring Boot 3.5 / Security 6.5

The following test suite includes both a `SecurityFilterChain` and a controller in one class to verify **`PathPatternRequestMatcher` + HTTP method + permissions + `denyAll`**. This fixture targets **Spring Boot 3.5.x and Spring Security 6.5.x**, Java 17+; when moving to Boot 4/Security 7, verify starters, test packages, and updated configurations. Do not claim a file written for Boot 3.5 will compile unmodified on every other version.

### 7.1. Dependencies

In a Spring Boot 3.5 Gradle project already configured with the Gradle plugin, repositories, and JUnit Jupiter, include:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

Place the file at **src/test/java/demo/authorization/MatcherMigrationTest.java**:

~~~java
package demo.authorization;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.servlet.util.matcher.PathPatternRequestMatcher;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootTest(classes = MatcherMigrationTest.App.class)
@AutoConfigureMockMvc
class MatcherMigrationTest {

    @SpringBootConfiguration
    @EnableAutoConfiguration
    static class App {

        @Bean
        SecurityFilterChain securityFilterChain(HttpSecurity http)
                throws Exception {
            PathPatternRequestMatcher.Builder path =
                    PathPatternRequestMatcher.withDefaults();

            http.authorizeHttpRequests(auth -> auth
                .requestMatchers(path.matcher("/public/ping"))
                    .permitAll()
                .requestMatchers(path.matcher(
                        HttpMethod.GET, "/api/reports/{id}"))
                    .hasAuthority("report:read")
                .requestMatchers(path.matcher(
                        HttpMethod.POST, "/api/reports/{id}/publish"))
                    .hasAuthority("report:publish")
                .anyRequest().denyAll()
            ).httpBasic(Customizer.withDefaults());

            // Default CSRF remains enabled; POST tests use with(csrf()).
            return http.build();
        }

        @Bean
        ReportController controller() {
            return new ReportController();
        }
    }

    @RestController
    static class ReportController {

        @GetMapping("/public/ping")
        String ping() {
            return "pong";
        }

        @GetMapping("/api/reports/{id}")
        String read(@PathVariable("id") long id) {
            return "report:" + id;
        }

        @PostMapping("/api/reports/{id}/publish")
        String publish(@PathVariable("id") long id) {
            return "published:" + id;
        }
    }

    @Autowired
    MockMvc mvc;

    @Test
    void anonymousCanCallExplicitPublicRoute() throws Exception {
        mvc.perform(get("/public/ping"))
                .andExpect(status().isOk())
                .andExpect(content().string("pong"));
    }

    @Test
    void anonymousCannotReadReport() throws Exception {
        mvc.perform(get("/api/reports/42"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    @WithMockUser(authorities = "report:read")
    void readerCanRead() throws Exception {
        mvc.perform(get("/api/reports/42"))
                .andExpect(status().isOk())
                .andExpect(content().string("report:42"));
    }

    @Test
    @WithMockUser(authorities = "other")
    void loggedInUserWithoutReadAuthorityIsForbidden() throws Exception {
        mvc.perform(get("/api/reports/42"))
                .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(authorities = "report:publish")
    void publisherCanPublish() throws Exception {
        mvc.perform(post("/api/reports/42/publish").with(csrf()))
                .andExpect(status().isOk())
                .andExpect(content().string("published:42"));
    }

    @Test
    @WithMockUser(authorities = "report:read")
    void readerCannotPublish() throws Exception {
        mvc.perform(post("/api/reports/42/publish").with(csrf()))
                .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(authorities = "report:publish")
    void publisherWithoutReadAuthorityCannotRead() throws Exception {
        mvc.perform(get("/api/reports/42"))
                .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(authorities = "report:read")
    void deeperPathNotMatchedByIdPattern() throws Exception {
        mvc.perform(get("/api/reports/42/export"))
                .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(authorities = "report:read")
    void postToReadOnlyRouteIsDenied() throws Exception {
        mvc.perform(post("/api/reports/42").with(csrf()))
                .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(authorities = "report:read")
    void unrelatedRouteIsDeniedByDefault() throws Exception {
        mvc.perform(get("/admin/settings"))
                .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(authorities = "report:read")
    void queryParameterDoesNotAlterPathPattern() throws Exception {
        mvc.perform(get("/api/reports/42").param("view", "compact"))
                .andExpect(status().isOk())
                .andExpect(content().string("report:42"));
    }

    @Test
    @WithMockUser(authorities = "report:read")
    void getCannotInvokePublishRoute() throws Exception {
        mvc.perform(get("/api/reports/42/publish"))
                .andExpect(status().isForbidden());
    }
}
~~~

**Run** in a Spring Boot 3.5/Security 6.5 Gradle project configured for Java 17+:

~~~bash
./gradlew test --tests "demo.authorization.MatcherMigrationTest"
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat test --tests "demo.authorization.MatcherMigrationTest"
~~~

**Expected outcome:** **12 passing tests** when configuration and versions align. Tests do not print fixed stdout; JUnit/Gradle reports execution status. This is an **expectation derived from sample logic**, not captured output from a real Gradle run. Both permitted endpoints return 200; anonymous calls to protected endpoints get 401 when HTTP Basic is enabled; logged-in users lacking the authority or calling undeclared routes get 403.

**Why must POST include with(csrf())?** Spring Security can return 403 for a missing CSRF token **before checking authorities**. Without a valid token, `readerCannotPublish` could still pass without proving the `report:publish` rule actually ran. Including a CSRF token isolates authorization failures from CSRF failures.

**Limitations:** `@WithMockUser` creates mock Authentication/authorities; tests do not verify mapping from real OAuth2/OIDC tokens, IdPs, or databases. Test authentication converters or user provisioning separately, as well as per-resource permissions if required by business rules. This example uses no custom servlet prefix; add integration tests if your real app sets a context path/servlet path.

## 8. Multiple SecurityFilterChains and Protection Scope

The following two methods illustrate chain selection. They are **snippets inside a `@Configuration`**, requiring `@Order`, `@Bean`, and corresponding Spring Security imports:

~~~java
@Order(1)
@Bean
SecurityFilterChain api(HttpSecurity http) throws Exception {
    PathPatternRequestMatcher.Builder path =
            PathPatternRequestMatcher.withDefaults();

    http.securityMatcher(path.matcher("/api/**"))
        .authorizeHttpRequests(auth -> auth
            .requestMatchers(path.matcher(
                    HttpMethod.GET, "/api/reports/{id}"))
                .hasAuthority("report:read")
            .anyRequest().denyAll()
        )
        .httpBasic(Customizer.withDefaults());
    return http.build();
}

@Order(2)
@Bean
SecurityFilterChain fallback(HttpSecurity http) throws Exception {
    http.authorizeHttpRequests(auth -> auth
        .requestMatchers("/public/**").permitAll()
        .anyRequest().denyAll()
    );
    return http.build();
}
~~~

In this example, the API chain matches only `/api/**` requests. The fallback chain uses the default matcher matching every request not selected by the API chain. Consequently, **`/admin/settings`** still passes through a `denyAll` chain instead of escaping Spring Security altogether.

If only the API chain exists with no other chain, requests outside `/api/**` **may go unprotected**. Check chain selection both before and after migration, especially when replacing `http.antMatcher(...)` with `http.securityMatcher(...)`.

Inside **a single chain**, `requestMatchers` are evaluated **in order**. Never place `.requestMatchers("/api/**").authenticated()` before `.requestMatchers("/api/admin/**").hasRole("ADMIN")`; regular accounts would match the broad rule first.

## 9. Regression Matrix to Run on Both Old and New Versions

| Case | Request | Caller | Expected | Defect Detected |
| --- | --- | --- | --- | --- |
| R1 | GET /api/reports/42 | report:read | Allow | Read route no longer matches |
| R2 | GET /api/reports/42 | Anonymous | Reject | Missing chain or authentication |
| R3 | GET /api/reports/42 | Logged in, no report:read | Reject | Overly broad login-only rule |
| R4 | POST /api/reports/42/publish + CSRF | report:publish | Allow | Faulty POST matcher |
| R5 | POST /api/reports/42/publish + CSRF | report:read | Reject | Read permission allowed to publish |
| R6 | GET /api/reports/42/publish | report:read | Reject | HTTP method not constrained |
| R7 | POST /api/reports/42 + CSRF | report:read | Reject | POST conflated with GET |
| R8 | GET /api/reports/42/export | report:read | Reject if export not granted | Unintended broad `/**` |
| R9 | GET /admin/settings | report:read | Reject | Missing fallback chain |
| R10 | GET /public/ping | Anonymous | Allow | Public rule locked out after migration |
| R11 | GET /api/reports/42?view=compact | report:read | Allow | Query string confused with path |
| R12 | GET /api/reports/42/ | report:read | Per trailing slash policy | Different path parser |
| R13 | GET /portal/mvc/orders/42 | order:read | Per policy and servlet prefix | Context/servlet confusion |
| R14 | GET path with URL-encoded chars | report:read | Per URL normalization policy | Wrong URL decoding |
| R15 | GET /api/admin/erase | Regular user | Reject | Catch-all rule placed before ADMIN |

**Do not misread statuses:** 401 typically reflects unauthenticated access on Basic/Bearer apps; 403 reflects missing permission (or CSRF); 404 may simply mean no controller matched. To confirm matchers accurately, combine HTTP tests with verifying whether the real handler/service executes and data state stays unchanged on denial.

If the app uses a Servlet prefix, reverse proxy, or multiple SecurityFilterChains, integration tests on a real server must also check context path, forwarded headers, path normalization, URL encoding, and matchers built directly by filters. Never rely on a root-context `MockMvc` test to prove all deployment paths are safe.

## 10. Common Migration Errors

| Symptom | Cause | Remediation |
| --- | --- | --- |
| `antMatchers`/`mvcMatchers` fail to compile on 6.x | Legacy DSL methods removed | Migrate to `requestMatchers` with matching HTTP method, URL, and permissions |
| `AntPathRequestMatcher`/`MvcRequestMatcher` missing on 7.x | Implementation classes removed | Migrate to `PathPatternRequestMatcher` or still-supported matchers |
| App fails pattern parsing | Ant pattern has `**` in a position PathPattern rejects | Redesign pattern, test scope, avoid widening `/**` |
| Regular user reaches `/api/admin` | `requestMatchers("/api/**")` comes before ADMIN rule | Fix ordering, test authenticated-but-forbidden |
| Requests outside `/api/**` bypass security | Only a `securityMatcher("/api/**")` chain exists | Add a policy-compliant catch-all chain |
| 403/404 changes after servlet path shift | Context root mistakenly added to pattern, or `/mvc` omitted | Use `basePath` and test real deployment paths |
| Custom matcher fails compiling on 6 | Legacy `javax.servlet.HttpServletRequest` | Migrate to `jakarta.servlet` and check dependencies |
| Unauthorized POST test still passes when rule removed | 403 came from CSRF | Add `with(csrf())` to isolate authorization |
| Regex matcher misfires | Regex confused with Ant or HTTP method omitted | Test explicit `RegexRequestMatcher` thoroughly |
| Login/logout flow changes | Specialized filters create different default matchers | Check setters taking `RequestMatcher`, test full flow |
| New endpoints added without policy updates | `anyRequest` set to overly broad `authenticated` | Maintain route inventory and apply `denyAll` appropriately |

**Note on business permissions:** Matchers distinguish HTTP paths; they do not decide whether a user may view document `id=42` or which tenant they belong to. Where needed, owner/tenant/ACL checks in the service or data-access layer remain essential. Properly migrated matchers do not automatically prevent BOLA/IDOR or fix missing object-level checks.

## 11. Practical Upgrade Workflow

1. **Inventory** all calls to `antMatchers`, `mvcMatchers`, `regexMatchers`, `antMatcher`, `securityMatcher`, `requestMatchers`, custom `RequestMatcher`s, `SecurityFilterChain`s, and filters using custom URLs. Document routes, methods, permissions, and servlets.
2. **Freeze expected table** of allow/deny cases, especially authenticated-but-unauthorized, sensitive routes, out-of-scope URLs, other HTTP methods, and public endpoints.
3. **Upgrade to 5.8 before 6.0** if currently on 5.x, replacing deprecated DSLs and fixing warnings while tooling still supports both APIs. Run tests after each batch of changes.
4. **Upgrade to Spring Security 6.x** with matching Spring Framework/Jakarta, migrate to `SecurityFilterChain`/`authorizeHttpRequests` beans, and update custom matchers to `jakarta.servlet` types.
5. **On Spring Security 6.5**, adopt explicit `PathPatternRequestMatcher` or the default opt-in mechanism, testing patterns and servlet prefixes before moving to 7.
6. **On Spring Security 7**, remove unsupported Ant/MVC matcher classes and verify the rule of absolute URIs starting with `/` while excluding context paths.
7. **Accept** only via allow/deny tests across HTTP methods, routes, servlet paths, chain selection, and object permissions. Never accept solely because the app compiles or starts.
8. **Monitor post-deployment** for 401/403 anomalies, endpoints missing a security chain, and login/logout behavior changes; compare against the approved permission matrix.

For critical systems, matcher changes should be reviewed as **security** changes. Keep valid denial cases in the regression suite, because when a new matcher unintentionally widens a rule, suites testing only successful access easily miss vulnerabilities.

## 12. Practice Exercises

**Exercise A — replacing antMatchers:** Given legacy rule `antMatchers(GET,"/reports/**")`, rewrite it with `requestMatchers` on 5.8 and `PathPatternRequestMatcher` on 6.5. Compare outcomes for `GET /reports/42`, `GET /reports/42/export`, and `POST /reports/42`. Identify which changes are syntactic and which alter scope.

**Exercise B — servlet prefix:** An app runs at `/portal` (context) and `/mvc` (servlet), with controller mapping `/orders/{id}`. Write a matcher using `basePath("/mvc")`, test `/portal/mvc/orders/42` in an environment with matching `contextPath`, and ensure paths outside the servlet are blocked.

**Exercise C — custom matcher:** `GET /reports/42?print=true` requires `report:print`, while `GET /reports/42` only requires `report:read`. Write an `AndRequestMatcher` and place the print rule first; write a test proving a user with only `report:read` cannot use print.

**Exercise D — multiple filter chains:** Create an API chain at `@Order(1)` and a fallback at `@Order(2)`, proving both `/api` and `/admin` are protected; then intentionally remove the fallback in a test fixture to observe why chain selection must be tested.

**Exercise E — comparing 6.5 and 7:** Run matrix R1–R15 on a 6.5 branch using `PathPatternRequestMatcher`, then upgrade to 7. Record differences from parsers, path variables, and servlet paths; change expectations only when business policy intentionally changes.

## 13. Acceptance Checklist

- [ ] No remaining `antMatchers`/`mvcMatchers` in code targeting Spring Security 6+.
- [ ] No remaining `AntPathRequestMatcher`/`MvcRequestMatcher` in code targeting Spring Security 7.
- [ ] Clearly distinguished chain-selecting `securityMatcher` from rule-selecting `requestMatchers`.
- [ ] Catch-all chain or mechanism protects all expected requests.
- [ ] HTTP methods, roles/authorities, and rule order were not lost during API changes.
- [ ] PathPatterns start with `/` and exclude the context path.
- [ ] Servlet prefixes, trailing slashes, wildcards, and URL encoding have been tested.
- [ ] Custom matchers migrated to Jakarta and are version-compatible.
- [ ] Both allowed and denied cases verified.
- [ ] POST tests use a valid CSRF token when measuring authorization.
- [ ] Login/logout filters, dispatcher types, and public endpoints verified.
- [ ] Migration evaluated by **behavior**, not compilation alone.

## 14. References

- Spring Security 5.8 AbstractRequestMatcherRegistry API: https://docs.spring.io/spring-security/site/docs/5.8.x/api/org/springframework/security/config/annotation/web/AbstractRequestMatcherRegistry.html
- Spring Security 6 Migration: https://docs.spring.io/spring-security/reference/6.5/migration/index.html
- Spring Security 6.5 Authorize HttpServletRequests: https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/authorize-http-requests.html
- Spring Security 6.5 AntPathRequestMatcher API: https://docs.spring.io/spring-security/site/docs/6.5.x/api/org/springframework/security/web/util/matcher/AntPathRequestMatcher.html
- Spring Security 6.5 MvcRequestMatcher API: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/servlet/util/matcher/MvcRequestMatcher.html
- Spring Security 6.5 PathPatternRequestMatcher.Builder API: https://docs.spring.io/spring-security/site/docs/6.5.6/api/org/springframework/security/web/servlet/util/matcher/PathPatternRequestMatcher.Builder.html
- Spring Security Prepare for 7, Web Migrations: https://docs.spring.io/spring-security/reference/6.5/migration-7/web.html
- Spring Security 7 Java Configuration: https://docs.spring.io/spring-security/reference/7.0/servlet/configuration/java.html
- Spring Security 7 PathPatternRequestMatcher API: https://docs.spring.io/spring-security/reference/7.0/api/java/org/springframework/security/web/servlet/util/matcher/PathPatternRequestMatcher.html
