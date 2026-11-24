# Comparing Spring Boot, Spring Security Versions, and Authorization Features

## Learning Objectives

When upgrading Spring Boot, the version number in `build.gradle` or `pom.xml` is not enough to conclude which authorization features the application is actually running. **Spring Boot manages dependencies**, while **Spring Security provides and enforces authentication/authorization APIs**; the application remains responsible for properly configuring requests, methods, resources, and data. An upgrade may compile successfully yet alter URL matching, dispatch types, method security, custom `AuthorizationManager`s, or role/authority mappings. An "endpoint returns 200" result does not prove that permissions are still enforced properly.

This lesson helps you:

1. Map Spring Boot ↔ Spring Security release lines and the artifact versions **actually resolved** in a build.
2. Categorize authorization features by **request-level, method-level, and object/data-level**, and verify the presence and activation conditions of each feature.
3. Identify notable changes when moving from Security 5.x to 6.x and 6.x to 7.x; distinguish between deprecated APIs, removed APIs, and default behavior changes.
4. Use Gradle/Maven commands, configuration patterns, and identity-and-path matrix tests to verify migrations without inadvertently opening up permissions.
5. Write a project-specific comparison table with pinned versions, evidence, and PASS/FAIL decisions, rather than inferring from release names.

**Convention:** Examples use Java 17+ and the explicitly stated Spring Boot/Spring Security branches. The `x` placeholders in tables denote **version lines**, not fixed patch versions; exact patch versions and managed dependencies must be read from the project's BOM/metadata. Third-party libraries, Spring Cloud, Servlet/Reactive stacks, and how the principal is supplied must also be checked separately.

## 1. Distinguishing Responsibilities Between Boot and Security

**Spring Boot** helps build and bootstrap the application, provides auto-configuration, starters, and dependency management (typically via the `spring-boot-dependencies` BOM). When using Boot's dependency management properly, most `org.springframework.security:*` artifacts pull compatible versions selected by the BOM, unless overridden by the project or another plugin.

**Spring Security** provides `SecurityFilterChain`/`SecurityWebFilterChain`, authentication, `GrantedAuthority`, `AuthorizationManager`, request matchers, method security, OAuth 2.0 resource server/client, CSRF, and many other components. Having a Security dependency **does not mean** every authorization mechanism is enabled:

- Declaring a starter does not automatically create row-level/tenant-level rules for repositories.
- Method authorization with `@PreAuthorize` requires enabling `@EnableMethodSecurity` (or an equivalent configuration); the Security starter **does not automatically enable** method security.
- A request-level `authenticated()` rule only proves the caller is logged in; it does not automatically confirm the caller is allowed to view an invoice/document by ID.
- A role name inside a token does not automatically become a `GrantedAuthority` with the expected value; the JWT converter and prefix are parts of the contract.

To know "what a version supports," ask sequentially: **which artifact was resolved? does that API exist in the version? is the configuration enabled? which bean/filter is executing? what behavior do authorization tests prove?**

## 2. Version Line Matrix to Compare

The following table is a map of **typical release lines**, not every compatible combination or current patch release:

| Spring Boot Line | Bundled/Primary Target Spring Security Line | Authorization-Related Milestones | Comparison Notes |
| --- | --- | --- | --- |
| Boot **2.7.x** | Security **5.7.x** per standard BOM | `WebSecurityConfigurerAdapter` and `authorizeRequests` are the legacy configuration path; the new `SecurityFilterChain` approach is recommended | You can **proactively** upgrade Security separately to **5.8.x** to prepare for 6.0; that is a controlled migration step, not the 2.7 default |
| Boot **3.0.x** | Security **6.0.x** | Java 17+, Spring Framework 6, Jakarta namespace; `SecurityFilterChain`/`authorizeHttpRequests` and `AuthorizationManager` direction | Check filter dispatch rules, method security, and `javax.*` → `jakarta.*` imports |
| Boot **3.3.x** | Security **6.3.x** | 6.x line implementing modern request/method authorization | Consult documentation for Security 6.3/6.x and check exact BOM patch versions |
| Boot **3.5.x** | Security **6.5.x** | Final 6.x line, preparation phase for upgrading to Security 7 | Complete the "Preparing for 7" steps before changing major versions |
| Boot **4.0.x** | Security **7.0.x** | Several deprecated APIs removed; `AuthorizationManager#check` replaced by `authorize`; changes to some matchers | Need to audit custom `AuthorizationManager`s, `HttpSecurity` DSL, matchers, and legacy access APIs |
| Boot **4.1.x** | Security **7.1.x** | Same Security 7 generation with additional changes/features | Do not infer every 4.1 method from 4.0; verify dependency versions and reference docs for 7.1 |

**Proper usage:** place the running BOM in the first column, open the "Managed Dependency Coordinates" table for **that exact Boot version** to obtain `spring-security-config`, `spring-security-web`, `spring-security-core`, and `spring-security-test`; then cross-check against the Gradle/Maven graph. For example, numbers like `3.3.x → 6.3.x` and `4.0.x → 7.0.x` describe release lines and do not guarantee that a project with overrides or Spring Cloud resolves those exact versions.

These Boot/Security pairings are recommendations, not arbitrary mix-and-match options: upgrading only `spring-security-web` to a new major while leaving `spring-security-config` on an older major can cause `NoSuchMethodError`, `ClassNotFoundException`, or untested semantics. You must compare **all present Security artifacts** and integration libraries rather than only comparing starter versions.

### Why not use a "latest version" list as the source of truth?

"Latest" changes daily and may be a new patch, preview, or snapshot. A project also has a Java baseline, Spring Framework, Servlet container, Spring Cloud, and foundational libraries. The right upgrade target is a **stable release supported for that specific project**, backed by its dependency tree, release notes, migration guide, and tests. Do not replace production dependencies with the latest version via a homepage search and assume compatibility.

## 3. Checking Actual Versions in Gradle and Maven

### 3.1. Gradle: distinguishing declared versions from resolved versions

Example for a **Spring Boot 3.3.x** application; other project plugins/repositories can be added as needed, as this is an **illustrative build configuration snippet**:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.0'
    id 'io.spring.dependency-management' version '1.1.5'
}

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
```

`3.3.0` here only illustrates a reproducible build, **not the latest or production-recommended version**. The Security starter and `spring-security-test` omit explicit versions so they use Boot's dependency management. If the project uses Gradle native platforms/BOMs instead of the dependency management plugin, check where `spring-boot-dependencies` and other constraints are imported; do not assume the BOM is active just because you see the Spring Boot plugin.

On Linux/macOS:

```bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-security-web --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-security-config --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-security-core --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-security-test --configuration testRuntimeClasspath
```

On Windows PowerShell/CMD, change `./gradlew` to `.\gradlew.bat`. The `dependencyInsight` command shows the final resolved version, dependency paths, and selection reasons such as constraints/forces/conflicts (output format depends on Gradle). Repeat for `spring-security-oauth2-resource-server`, `spring-security-oauth2-jose`, and `spring-security-messaging` if the project uses those modules.

**Reading the results properly:** if the build shows `requested: 6.2.x` but `selected: 6.3.y`, find the actual management source and confirm it is intentional. If `spring-security-web` = 6.x while `spring-security-config` = 7.x, treat this as a **major-version mismatch risk**, and do not use a green build as proof of safety. In a multi-module Gradle project, run the check on the **actual executable/classpath module**; the root project or a library module's graph may differ from runtime.

### 3.2. Maven: parent/BOM and effective model

Example dependencies without explicit versions:

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-security</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.security</groupId>
        <artifactId>spring-security-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
```

Comparison commands:

```bash
mvn help:effective-pom
mvn dependency:tree -Dincludes=org.springframework.security
```

Inspect parent/BOM, `dependencyManagement`, properties such as `spring-security.version` (if used/overridden), profiles, and dependencies with explicitly declared versions. Do not confuse the `spring-boot-maven-plugin` version with the entire dependency graph; they can be configured independently.

### 3.3. Recording an evidence-backed "version manifest"

Example inventory table (values represent a **template to fill in**, not command output):

| Information | Verification Source |
| --- | --- |
| Spring Boot plugin/parent and BOM | Build script, effective POM, dependency constraints |
| Security core/config/web/test individual versions | `dependencyInsight` or `dependency:tree` |
| Spring Framework and Java runtime/toolchain | Dependency graph, `java -version`, build image |
| Servlet or WebFlux | Starters and security filter chain type |
| Custom `AuthorizationManager` or legacy access APIs | Search project source for types/imports/methods |
| Method security annotations in use | Search `@EnableMethodSecurity`, `@PreAuthorize`, `@Secured`, `@RolesAllowed` |
| Integration test matrix results | CI run and PASS/FAIL status per endpoint/role |

Save the manifest along with CI results **before and after the upgrade** to distinguish compatibility bugs from intentional policy changes.

## 4. Authorization Features to Compare by Layer

Do not ask generally "does Security 6 have authorization?"; break it down by layer:

| Layer | Typical API/Config | What Does It Decide? | Things to Verify After Upgrade |
| --- | --- | --- | --- |
| Request Servlet | `HttpSecurity`, `SecurityFilterChain`, `authorizeHttpRequests`, `requestMatchers` | Whether the current URL/method/dispatcher passes the filter | Matcher order, public paths, 401/403, ERROR/FORWARD, multiple chains |
| Request Reactive | `ServerHttpSecurity`, `SecurityWebFilterChain`, `authorizeExchange` | Whether an exchange in WebFlux may proceed | `pathMatchers`, web filter order, `WebTestClient`, reactive context |
| Method | `@EnableMethodSecurity`, `@PreAuthorize`/`@PostAuthorize`, `@Secured`/`@RolesAllowed` (if enabled) | Who may invoke a method or receive its return value | Whether annotations are active, parameter expressions, proxies/self-invocation |
| Programmatic | `AuthorizationManager`, custom authorization bean | Decisions from code/policy sources | API signature, fail-closed, abstain/deny states, exceptions |
| Object/data | `hasPermission`, service policies, repository predicates/ACL | Whether access is allowed for a specific record | IDOR, tenant isolation, COUNT, search/pagination, redaction |
| JWT/OAuth2 | Resource server, JWT converter, authorities mapping | Which claims/scopes become `GrantedAuthority` | `SCOPE_*`, `ROLE_*`, issuer/audience validation, claim mapping |
| Test | `spring-security-test`, `MockMvc`/`WebTestClient` | Whether tests run with real security or mocks/bypasses | Presence of filter chain, method interceptor, accurate principal/claims |

**A feature existing in the library ≠ enabled ≠ handling business data correctly.** For example, `hasRole("ADMIN")` checks an authority with the `ROLE_` prefix by default; `hasAuthority("ADMIN")` compares the exact name `ADMIN`. These two expressions are not equivalent, especially after modifying a JWT converter or role hierarchy. You must inspect `Authentication.getAuthorities()` at runtime/in tests using safe data.

## 5. Migrating from Spring Security 5.x to 6.x

### 5.1. Low-surprise migration path

1. On Boot 2.7, use Security 5.7 per the BOM; consider upgrading Security separately to **5.8.x** following the official migration guide to replace deprecated APIs before upgrading to Boot 3.0/Security 6.0.
2. Clean up `WebSecurityConfigurerAdapter`, legacy `authorizeRequests`/`antMatchers`, old method security configurations, imports/namespaces, and dependent libraries.
3. Upgrade Java to **17+**, Spring Framework 6, `jakarta.*` standards, and Boot 3/Security 6 according to the corresponding BOM.
4. Run request/method/object permission tests, paying attention to servlet dispatcher types and filter/custom security components.
5. Only after behavior is equivalent should you incrementally upgrade through the Boot 3.x lines supported by the project and inspect changes in each release.

**Configuration design change:** Security 5.x commonly had code extending `WebSecurityConfigurerAdapter`; Security 6.x uses `SecurityFilterChain` beans. You cannot mechanically rename classes/DSL methods while ignoring rule precedence.

Historical pattern **meaningful only for legacy branches**, **do not use as source code for Security 6/7**:

```java
// Sketch of legacy Spring Security 5.x configuration.
@EnableGlobalMethodSecurity(prePostEnabled = true)
class LegacySecurity extends WebSecurityConfigurerAdapter {
    @Override
    protected void configure(HttpSecurity http) throws Exception {
        http.authorizeRequests()
            .antMatchers("/public/**").permitAll()
            .antMatchers("/admin/**").hasRole("ADMIN")
            .anyRequest().authenticated();
    }
}
```

Corresponding pattern using Security 6.x beans (assuming Servlet MVC, Java 17+, with required imports):

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableMethodSecurity
public class SecurityConfig {

    @Bean
    SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public/**").permitAll()
                .requestMatchers(HttpMethod.GET, "/api/reports/**")
                    .hasAuthority("report:read")
                .requestMatchers("/admin/**").hasRole("ADMIN")
                .anyRequest().denyAll())
            .httpBasic(Customizer.withDefaults())
            .build();
    }
}
```

In the new pattern, `anyRequest().denyAll()` intentionally **denies by default**; the legacy pattern uses `anyRequest().authenticated()`. **The two configurations are not equivalent for all URLs** — during a real product migration, explicitly document which routes remain protected by `authenticated` and which must be closed; do not silently change logic to match an example. Switching from `hasRole` to `hasAuthority` must be accompanied by verifying actual authority values, not guessing.

`httpBasic` here is only an authentication mechanism so the example can focus on authorization. If production uses JWT/OAuth2, configure the corresponding resource server and test the converter; do not infer Basic Auth from the example.

### 5.2. Migrating method security

Previously there was `@EnableGlobalMethodSecurity(prePostEnabled = true)`; the new system uses `@EnableMethodSecurity`, which enables pre/post annotations by default. If previously only `securedEnabled = true` was enabled **without pre/post**, migration may require:

```java
// Example when preserving the option to use only @Secured:
@EnableMethodSecurity(
        securedEnabled = true,
        prePostEnabled = false)
class MethodSecurityConfiguration {}
```

If the project uses `@RolesAllowed` or `@PermitAll` via JSR-250, enable the appropriate setting, e.g., `@EnableMethodSecurity(jsr250Enabled = true)`. **Do not assume `@EnableMethodSecurity` automatically enables every legacy annotation type.** Review existing annotations and verify they actually block invocations.

When an expression like `@PreAuthorize("hasAuthority('report:read') and #id > 0")` relies on parameter names, ensure Spring receives the names in bytecode (typically via `-parameters`), or annotate parameters with `@P` as appropriate. Changing compiler flags can prevent the expression from resolving parameters even though the code still compiles. Additionally, proxy-based method security can be bypassed by internal `this.method()` calls; test actual execution paths.

### 5.3. Dispatcher-based authorization

Per the Boot 3.0/Security 6.0 migration guide, Servlet authorization includes changes related to **dispatcher types**. `REQUEST`, `ERROR`, and `FORWARD` dispatches should not be assumed to behave identically before/after migration; for instance, rendering an error page may turn into 403 if the configuration does not allow `ERROR` through. When handling this, apply the right rule for needed dispatcher types and **do not accidentally open up normal data requests**. Test both the original request and error/forward paths, using the application's security contract as the source of truth.

## 6. Migrating from Spring Security 6.x to 7.x

The Spring-recommended path: update to the Boot **3.5.x**/Security **6.5.x** branch, complete the steps preparing for 7 per the migration guide, and only then upgrade to Boot **4.x**/Security **7.x**. A major upgrade can also change Spring Framework and the Jackson ecosystem, modules, matchers, and build infrastructure; you need an upgrade branch with full build/test coverage.

Items **documented in Spring Security 7.0** that are particularly relevant to authorization code:

| Migration Point | Security 6.x Line | Security 7.x Line | Action |
| --- | --- | --- | --- |
| Custom AuthorizationManager | The `check(...)` API existed in 6.x alongside the newer `authorize(...)` direction | `AuthorizationManager#check` **has been removed**, use `authorize(...)` | Search `.check(` in custom auth/policy integrations, update to the new API, and thoroughly test PERMIT/DENY/null |
| Legacy request DSL | `authorizeRequests` remained in some older branches as deprecated | `authorizeRequests` **has been removed** | Use `authorizeHttpRequests` and verify matcher/rule priority |
| HttpSecurity chaining | Some legacy `.and()` forms were still supported/deprecated in 6.x | Legacy `HttpSecurity` DSL `and()` **has been removed** | Migrate to lambda DSL with the proper overloads |
| Servlet request matcher | Older code might use `AntPathRequestMatcher`/`MvcRequestMatcher` | Legacy matchers **have been removed**, moving toward `PathPatternRequestMatcher` | Check imports/custom matchers; test path variables/trailing slashes/encoding |
| Legacy access decision | `AccessDecisionManager`, voters, and legacy configs might still exist | Legacy APIs moved to the `spring-security-access` module | Prefer migrating to `AuthorizationManager`; if keeping legacy, understand the support module and migration plan |
| Method security | `@EnableMethodSecurity`, `@PreAuthorize` available | Modern mechanism continues to be supported | Verify default enabled annotations, parameters, proxies, exceptions |
| Scope/role authorization | `hasAuthority`/`hasRole` | Still requires accurate authorities mapping | Do not assume mappings are preserved when switching converters/dependencies |

Do not interpret "Security 7 adds new features" as "every project must immediately adopt those features." For example, Security 7 adds `AllAuthoritiesAuthorizationManager` and utilities for checking "requires all authorities"; it **differs** from `hasAnyAuthority`. If writing a condition that requires all scopes, verify true AND semantics rather than OR across every version.

**Find removed APIs before upgrading:** search all application code and integration packages for `WebSecurityConfigurerAdapter`, `authorizeRequests`, `antMatchers`, `AntPathRequestMatcher`, `MvcRequestMatcher`, `AccessDecisionManager`, `AccessDecisionVoter`, `AuthorizationManager#check`/`.check(`, and `.and()`. Not every search hit is a security call; check types/imports before modifying. If a third-party library uses a removed API, upgrade to a compatible library version or isolate/migrate appropriately — do not simply add a dependency hoping the error disappears.

## 7. Understanding `hasRole`, `hasAuthority`, and JWT Scopes

This is a very common source of "suddenly getting 403 after upgrading" or "inadvertently granting broader access."

- `hasAuthority("report:read")`: compares against the **exact** authority string attached to the Authentication.
- `hasRole("EDITOR")`: in a standard configuration, matches against the authority `ROLE_EDITOR` (the default role prefix can be customized).
- OAuth2 resource server scopes are typically mapped by the default converter to authorities in the form `SCOPE_reports.read`; however, a custom converter may behave differently. Do not read `scope` data from a token and manually prepend `ROLE_` if the policy does not define it that way.
- `hasAnyRole` and `hasAnyAuthority` check **one of many**; do not substitute them for a condition requiring **multiple** permissions simultaneously.

A **standalone Java 17+ program** simulating how role prefixes and authority strings are distinguished. It does not replace Spring's evaluator; its purpose is to reinforce the difference in data values.

Create `AuthorizationNamesDemo.java`:

```java
import java.util.Set;

public class AuthorizationNamesDemo {
    static boolean hasRole(Set<String> granted, String role) {
        return granted.contains("ROLE_" + role);
    }

    static boolean hasAuthority(Set<String> granted, String name) {
        return granted.contains(name);
    }

    public static void main(String[] args) {
        Set<String> granted = Set.of(
                "ROLE_EDITOR", "SCOPE_reports.read");

        System.out.println("hasRole(EDITOR): "
                + hasRole(granted, "EDITOR"));
        System.out.println("hasAuthority(EDITOR): "
                + hasAuthority(granted, "EDITOR"));
        System.out.println("hasAuthority(SCOPE_reports.read): "
                + hasAuthority(granted, "SCOPE_reports.read"));
        System.out.println("hasRole(REPORTS): "
                + hasRole(granted, "REPORTS"));
    }
}
```

Commands:

```bash
javac AuthorizationNamesDemo.java
java AuthorizationNamesDemo
```

Exact stdout:

```text
hasRole(EDITOR): true
hasAuthority(EDITOR): false
hasAuthority(SCOPE_reports.read): true
hasRole(REPORTS): false
```

In a real Spring application, inspect the authenticated principal's `GrantedAuthority` set in a **test environment**, and test both `ROLE_EDITOR`/`SCOPE_reports.read` whenever a custom JWT converter changes. Just because a `roles` field in a token contains `EDITOR` does not mean `hasRole("EDITOR")` will definitely work: you must verify the converter and system conventions.

## 8. Servlet, WebFlux, and Request Matchers Cannot Be Equated

The two stacks have different APIs and tests:

| Component | Spring MVC/Servlet | Spring WebFlux/Reactive |
| --- | --- | --- |
| HTTP security | `HttpSecurity`, `SecurityFilterChain` | `ServerHttpSecurity`, `SecurityWebFilterChain` |
| Request rules | `authorizeHttpRequests(...)` | `authorizeExchange(...)` |
| URL matching | `requestMatchers(...)` or current version's matcher | `pathMatchers(...)`/appropriate `ServerWebExchangeMatcher` |
| Request nature | `HttpServletRequest` and dispatcher/filter chain | `ServerWebExchange` and Reactor context/web filters |
| HTTP authorization testing | `MockMvc` + `spring-security-test` | `WebTestClient` + reactive security test support |
| Context | Servlet/thread/request-related context | Reactive `Context`, propagated along the pipeline |

Do not copy a `SecurityFilterChain` into WebFlux expecting it to work; nor use `@WebMvcTest` to prove reactive security. When dependencies include both the web starter and the webflux starter, determine the **actual application type** running.

Comparing matchers during a major upgrade:

1. Are there multiple `SecurityFilterChain`s with `@Order` or `securityMatcher`? Both the selected chain and rules must be right.
2. Do paths like `/admin`, `/admin/`, `/admin/42`, encoding/URL normalization, or paths with special delimiters match as before?
3. `requestMatchers(HttpMethod.GET, ...)` differs from an all-methods matcher; a public read route does not automatically allow POST writes.
4. If there is a reverse proxy, context-path, servlet-path, or forwarded headers, test the exact path the application actually receives.
5. After switching to `PathPatternRequestMatcher` per Spring Security 7, do not assume every Ant/MVC matcher's syntax and behavior stays identical; write tests covering positive and negative boundaries.

Any new `permitAll()` configuration must be reviewed because it can expose sensitive endpoints; avoid "fixing tests to green" with `anyRequest().permitAll()` or disabling security filters.

## 9. Controlled Migration Process

### Step 1 — Lock down baseline and scope

Record the **actually running** Boot/Security versions and Java/Spring Framework; identify whether the app is Servlet/Reactive, the authentication mechanism (session, Basic, JWT, opaque token, mTLS), method security, and data-level policies. Build a table of endpoint → HTTP method → principal type → authority/tenant/owner → expected status and side effects. Include both public and sensitive endpoints as controls.

### Step 2 — Build a version diff

Compare the before/after BOM tables; record which artifacts change major/minor versions. Read release notes for **the exact branches traversed**, not just the target version's page. Follow staged migration guides: 2.7→3.0/5.8→6.0 and 3.5→4.0/6.5→7.0 where applicable. Check compatibility of supporting libraries for OAuth, JWT, SAML, OpenAPI, Spring Cloud, session, and actuator.

### Step 3 — Migrate APIs while preserving permission semantics

Fix deprecated/removed code, but **preserve the prior authorization contract** unless the business requires a change. Each rule should be marked as equivalent or an approved change: `authenticated` differs from `permitAll`, `hasRole` differs from `hasAuthority`, `hasAny...` differs from `hasAll...`, and request-only checks differ from object checks.

Commonly confused before/after scenario:

```text
Before: GET /api/reports/42
        USER alice, authority report:read, owner=bob  -> 403

After:  requestMatchers("/api/reports/**").hasAuthority("report:read")
        -> passes request-level, but if the object check in the service
           is dropped, alice can read bob's report.

Equivalent requirement:
        request-level has authority + service/repository checks owner/tenant,
        or an equivalent AuthorizationManager/policy runs before returning data.
```

**Data boundaries** do not heal themselves after changing filter APIs. If repositories enforce multi-tenant policies or row-level ACLs, test data queries, pagination `totalElements`, field redaction, and side effects per principal.

### Step 4 — Configure version-appropriate tests

Choose `spring-security-test` from the same line managed by the BOM; ensure `MockMvc`/`WebTestClient` enables the security chain. A unit test instantiating a service with a mock principal will not detect matcher changes; conversely, a request-only test does not verify that `@PreAuthorize` protects the service when called via another path.

Example **sketch of a Spring Boot 3.x + Security 6.x integration test** (requires application context, `/api/reports/**` controller, security config, JUnit/Spring Test dependencies, and corresponding imports):

```java
@SpringBootTest
@AutoConfigureMockMvc
class ReportAuthorizationIT {
    @Autowired MockMvc mvc;

    @Test
    void anonymousCannotReadReport() throws Exception {
        mvc.perform(get("/api/reports/42"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    @WithMockUser(authorities = "report:read")
    void readerCanReachPermittedEndpoint() throws Exception {
        mvc.perform(get("/api/reports/42"))
                .andExpect(status().isOk());
    }

    @Test
    @WithMockUser(roles = "USER")
    void missingAuthorityIsForbidden() throws Exception {
        mvc.perform(get("/api/reports/42"))
                .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(roles = "ADMIN")
    void unknownRouteIsDeniedByDefault() throws Exception {
        mvc.perform(get("/api/not-configured"))
                .andExpect(status().isForbidden());
    }
}
```

Expecting 401 for anonymous users depends on the authentication entry point (Basic in this example), just as the real endpoint returns 200 only when both `report:read` **and** the resource policy allow it. If the application enforces owner/tenant checks, the fixture must let the reader own 42 or adjust expectations accordingly; do not mock away policies just to force 200. With a custom JSON error handler, the response body may differ. The snippet above is an **illustration inside an app with full beans/config**, not a standalone Java program. There is no body/DB fixture here, so separate data-level integration tests must be added for a real system.

### Step 5 — Before/after matrix testing

| Principal/Scenario | Request | Illustrative Expectation | What Needs to Be Proved |
| --- | --- | --- | --- |
| Anonymous | GET public | 200 | Only public routes are granted access |
| Anonymous | GET protected | 401 or configured entry point | No data/side effects |
| Authenticated without sufficient authority | GET protected | 403 | Not mistaking `authenticated` for sufficient permission |
| Has authority but wrong owner | GET /documents/{id} | 403/404 per policy | Object-level policy is not bypassed |
| Has authority and right owner | GET /documents/{id} | 200 | Legitimate permissions are served |
| ADMIN of tenant A | GET tenant B document | 403/404 | No cross-tenant permission leak |
| Authenticated missing CSRF token in session-based browser | POST/DELETE requiring CSRF | 403 (if CSRF is enforced) | CSRF was not accidentally removed during migration |
| FORWARD/ERROR path | Internal dispatch path | Per specified policy | No data leaks or error loops |
| Valid JWT signature but missing scope | GET scope-protected | 403 | Authorities + scope converter works properly |
| PDP/custom auth error | GET protected | Fails safely, 403/503 per policy | Does not fall back to PERMIT |

Results must be compared **both before and after** the upgrade. If a status changes, clearly classify it as a bug fix, an intentional policy change, or a regression. Do not use an HTTP 403 response alone as proof that all method security is working; tests should include at least one path directly hitting the service via a Spring bean and verifying data/side effects.

### Step 6 — Verify live execution and record new baseline

In CI, run tests verifying request/method/object permissions under a production-like configuration, `dependencyInsight`/`dependency:tree`, compile + package, and deployment environment tests; verify response headers, 401/403 statuses, decision auditing, and path coverage. If changing the Servlet container, Jakarta, JWT decoder, path matcher, or filter order, run tests against a real HTTP layer before concluding completion. Save the results alongside the version manifest so future upgrades can compare against them.

## 10. Common Mistakes When Comparing Versions

| Mistake | Why It Is Dangerous | Remediation |
| --- | --- | --- |
| Looking at the Boot plugin version to guess all Security versions | Dependencies can be overridden/transitive/constrained | Read the dependency graph **per artifact** of the runnable module |
| Putting `spring-security-web` 7.x into Boot 3.x while keeping 6.x config | Can mismatch APIs, Framework, and modules | Use a supported version line; test the full stack |
| Copying `WebSecurityConfigurerAdapter`/`antMatchers` to Boot 3/4 | APIs are replaced/removed | Migrate to current `SecurityFilterChain`/matchers |
| Switching `authorizeRequests` to `authorizeHttpRequests` while altering semantics | Public/private endpoints change | Compare every matcher, HTTP method, and fallback |
| Failing to enable `@EnableMethodSecurity` | `@PreAuthorize` is not enforced | Enable the right annotation + test via Spring bean/proxy |
| Confusing `hasRole("ADMIN")` with `hasAuthority("ADMIN")` | `ROLE_` prefix differs | Verify actual `GrantedAuthority` values |
| Checking only compilation without checking 401/403 | API compiles while matchers/dispatches differ | Matrix-based HTTP integration tests |
| Protecting only URLs, skipping owner/tenant checks | IDOR and cross-tenant access despite endpoint role | Test object/data-level queries and services |
| Keeping `AuthorizationManager#check` after upgrading to 7.x | API is removed | Migrate to `authorize`, test custom managers |
| Copying Servlet DSL to WebFlux | Wrong filter/matcher/context types | Use `SecurityWebFilterChain`/`authorizeExchange` and reactive tests |
| Using mocks that bypass security filters | False green tests | Run the security filter chain, test method proxies and real policies |
| Disabling CSRF or using `permitAll` upon hitting a 403 in tests | Unintentionally opens permissions | Investigate differences by request/token/policy |

## 11. Lesson Completion Checklist

A conclusion that "Spring Boot X supports authorization feature Y with Spring Security Z" is well-founded only when you can answer:

- **Version:** know the Boot/BOM version and resolved versions of `spring-security-core`, `config`, `web`, `test`, and related modules; no unintended major mismatches.
- **Capability:** the API exists in that Security line and is not on the removed list; if deprecated, a replacement path exists.
- **Activation:** `SecurityFilterChain`/`SecurityWebFilterChain` beans, method security, JWT converters, and policy services are enabled at the right application layers.
- **Semantic:** matchers, dispatches, role/authority prefixes, URL/method rules, object/tenant policies, and fail-closed behavior match the contract.
- **Evidence:** tests distinguish public/anonymous/no-role/valid-role/cross-tenant cases, with data-level checks and `dependencyInsight`/`dependency:tree` records.
- **Migration:** checked migration guides for each major, Java/Jakarta, custom managers/matchers, integration libraries, and post-change endpoint behavior.

**Key takeaway:** compatibility tables only give a starting point. Actual authorization results depend on **resolved dependencies + enabled configuration + policy semantics + application behavior tests**.

## Official Documentation for Version-Based Lookup

1. [Spring Boot — Managed Dependency Coordinates (currently published version)](https://docs.spring.io/spring-boot/appendix/dependency-versions/coordinates.html). Change the documentation URL to a **specific Boot line** to read the exact version, e.g., [3.5](https://docs.spring.io/spring-boot/3.5/appendix/dependency-versions/coordinates.html) and [4.0](https://docs.spring.io/spring-boot/4.0/appendix/dependency-versions/coordinates.html).
2. [Spring Boot 3.0 Migration Guide](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-3.0-Migration-Guide): Java 17, Jakarta, Spring Security 6, authorization dispatcher.
3. [Spring Security 6.0 Migration Guide](https://github.com/spring-projects/spring-security/wiki/Spring-Security-6.0-Migration-Guide): preparing via Security 5.8.
4. [Spring Boot 4.0 Migration Guide](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-4.0-Migration-Guide): preparing from 3.5 and ecosystem changes.
5. [Spring Security — Migrating to 7.0](https://docs.spring.io/spring-security/reference/migration/index.html) and [Spring Security 7.0 — What's New](https://docs.spring.io/spring-security/reference/7.0/whats-new.html): authorization APIs/matchers changes and removal of old APIs.
6. [Spring Security — Authorize HttpServletRequests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html) and [Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html): request rules, `AuthorizationManager`, `@EnableMethodSecurity`, role/authority expressions.
