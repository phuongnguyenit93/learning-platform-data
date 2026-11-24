# Removing Deprecated APIs After Regression Tests Confirm Behavior

> **Context:** Upgrading **Spring Security Servlet** applications on Java 17+, Spring Boot 3.x / Spring Security 6.x. The goal is not merely eliminating `deprecated` warnings: you must **preserve approved security behavior** when replacing configuration APIs, method security, request matchers, or `SecurityContext` management. The mandatory order is **specify behavior → green regression tests on old code → swap APIs in small steps → re-run and analyze diffs → only then delete legacy paths**. Version examples in this lesson illustrate a specific framework line and do not claim to be the latest release at reading time.

## 1. Why can “zero deprecation warnings” still leave an app less secure?

A change that looks purely syntactic:

```java
// Legacy syntax, historical Spring Security illustration
http.authorizeRequests()
    .antMatchers("/admin/**").hasRole("ADMIN");
```

migrated to:

```java
// Lambda syntax in Spring Security 6.x
http.authorizeHttpRequests(auth -> auth
    .requestMatchers("/admin/**").hasRole("ADMIN")
    .anyRequest().authenticated());
```

can alter **semantics** or expose preexisting misconfigurations:

- Which URLs, servlet paths/context paths, or HTTP methods does the first matcher rule cover?
- Are requests outside `/admin/**` still `authenticated()`, or accidentally permitted without a trailing rule?
- Do authority values still match `ROLE_ADMIN`, or did authority mapping shift after the upgrade?
- Are login/logout/error pages still accessible anonymously?
- Does CSRF still protect POST/PUT/PATCH/DELETE?
- Do sessions after form login continue working, with session cookie flags and redirects intact?
- Do JSON/API endpoints still return 401, 403, or 302 per the legacy contract?
- Are method-security annotations still enforced via proxies, even when services are called from other threads?
- Did filter ordering, exception translation, or `SecurityContext` persistence change?

**A clean build does not prove authentication/authorization policies remained unchanged.** You need tests measuring external behavior and side effects, not merely asserting that config classes use the new method names.

## 2. Four categories of change to distinguish

| Category | Meaning | How to handle |
| --- | --- | --- |
| **Deprecated API** | Still present, yet framework authors recommend replacing it | Read the exact-version migration guide; build a regression baseline first |
| **Removed API** | Absent from target dependencies; legacy code fails to compile | Upgrade in compatible stages or migrate APIs intentionally without disabling tests |
| **Behavioral change** | New API compiles, yet matchers/filters/sessions/exceptions differ semantically | Write characterization tests and compare real behavior |
| **Deliberate security policy change** | Intentionally tightening rules, CSRF, sessions, or roles | Isolate as a separate change, update requirements/acceptance tests, and get approval |

**Never mix** “refactoring away deprecations” with “changing security policy.” For instance, switching `/health` from `permitAll` to requiring authentication is a behavioral change; it may be right under new requirements, yet must never be slipped into a legacy-API-removal commit disguised as an equivalent migration.

## 3. Golden rule: test before replacing APIs

For each legacy API, document a **behavioral contract** covering:

1. **Input:** HTTP method/path/host, principal, authorities, cookies, CSRF, origin, session, dispatch type.
2. **Output:** status 200/302/401/403, error body, `Location`, `Set-Cookie`, security headers.
3. **Side effects:** session rotation, invalidation, repository calls, audit events, data writes, request cache.
4. **Boundaries:** anonymous, wrong role, valid role, expired token, same/cross tenant, disabled account.
5. **Environment:** real Servlet filter chain, context paths, HTTPS proxies, browsers where cookies/`SameSite` matter.
6. **Decision:** preserve behavior or change intentionally? Who approves the change?

Run tests on the **working legacy version** to capture a reviewed baseline. When swapping APIs, the exact same tests must pass without weakening assertions. If existing tests are failing, record the exact cause before fixing anything; never treat a red build as a trustworthy regression baseline.

### 3.1. Weak tests vs valuable tests

Weak test:

```java
// This test only checks a bean; it does not prove access control:
assertThat(securityFilterChain).isNotNull();
```

Valuable test:

```java
mvc.perform(get("/admin/report")
        .with(httpBasic("alice", "alice-pass")))
    .andExpect(status().isForbidden());
```

The second test proves a user lacking `ROLE_ADMIN` is genuinely denied through the Spring Security HTTP filter chain. Tests must also cover **allowed** admin access and **anonymous** callers; negative-only or positive-only tests are insufficient.

**Never “make tests green” by deleting negative cases, changing `403` to `anyStatus`, mocking out `SecurityFilterChain`, or disabling CSRF.** If expected outcomes must change due to a new policy, record that decision separately.

## 4. Inventory legacy APIs before writing the migration

### 4.1. Identify actual framework versions

With the Gradle Wrapper:

```bash
./gradlew --version
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight \
  --dependency spring-security-web \
  --configuration runtimeClasspath
./gradlew dependencyInsight \
  --dependency spring-security-config \
  --configuration compileClasspath
```

Use `.\gradlew.bat` accordingly on Windows PowerShell. Read versions from **dependency resolution**, rather than guessing solely from `build.gradle` when other BOMs/plugins are active.

Record:

- Java version, Spring Boot version, Spring Security artifacts, and resolved versions.
- Servlet stack (`jakarta.servlet` on Boot 3) vs reactive WebFlux. This lesson **covers Servlet only**.
- How many `SecurityFilterChain` beans, `@Order` values, and `securityMatcher`s exist?
- Authentication mechanisms: form, HTTP Basic, OAuth2 login, OIDC, resource server, LDAP, remember-me, custom providers?
- Which custom `Filter`/`AuthenticationProvider`/`AuthenticationSuccessHandler`/`SecurityContextRepository` classes rely on legacy APIs?
- Which annotations/configs enable method security?
- Are reverse proxies/Ingress, multi-node session stores, Redis/JDBC, CORS, `SameSite`, and custom CSRF involved?

### 4.2. Search for legacy markers within bounded scope

Example searches inside **your project's source**, not inside dependency/vendor folders:

```bash
rg -n 'WebSecurityConfigurerAdapter|authorizeRequests|antMatchers|mvcMatchers|regexMatchers' src
rg -n 'EnableGlobalMethodSecurity|GlobalMethodSecurityConfiguration|access\(' src
rg -n 'SecurityContextPersistenceFilter|SecurityContextHolderFilter|SessionCreationPolicy' src
rg -n 'csrf\(\)|headers\(\)|httpBasic\(\)|formLogin\(\)|logout\(\)' src
```

`rg` requires ripgrep installed; escaping varies by shell. **Matches are only candidates**, not an exhaustive list of deprecated symbols: some may be comments, strings, test code, or another library's APIs. In large projects, inspect submodules and deliberate generated/config files too.

Enable Java compiler deprecation warnings:

```groovy
tasks.withType(JavaCompile).configureEach {
    options.compilerArgs.add('-Xlint:deprecation')
}
```

In Gradle, track Java compilation warnings separately from Gradle plugin deprecations; a Gradle DSL warning is **not** a deprecated Spring Security Java API. If you plan to turn warnings into build failures later, introduce that as a separate gate **after** the baseline is approved rather than enabling `-Werror` too early and blocking comparisons.

### 4.3. Build a migration inventory table

| Component | Current API/behavior | Target API | Risk | Protective test |
| --- | --- | --- | --- | --- |
| HTTP configuration | `WebSecurityConfigurerAdapter` | `SecurityFilterChain` bean | Lost auth manager/filter chain | Basic/form login + negative auth |
| Authorization DSL | `authorizeRequests` | `authorizeHttpRequests` | Rule order, semantics, exception mapping | 200/302/401/403 matrix |
| URL matchers | `antMatchers`/`mvcMatchers` | `requestMatchers` or explicit `RequestMatcher` | Different path/context/servlet/method handling | Wildcards, URL encoding, methods |
| Method security | `@EnableGlobalMethodSecurity` | `@EnableMethodSecurity` | Annotation inactive or policy shifted | Proxy-backed service tests |
| `SecurityContext` handling | Manual authentication setting | Context repository / proper flow | Lost session after redirect | Login + follow-up request |
| HTTP DSL config | Legacy no-arg chained methods | Version-matched Lambda DSL | Defaults/settings dropped | CSRF, headers, logout |
| Error dispatch | Custom filtering | Current dispatcher/error policy | Errors turn into redirect loops | 500/ERROR dispatch tests |

Read Javadocs and migration guides for **source version → target version**; never stitch advice from multiple major versions into an assumed syntax.

## 5. Common replacements in Spring Security Servlet

### 5.1. WebSecurityConfigurerAdapter → explicit configuration beans

Older Spring Security projects subclassed `WebSecurityConfigurerAdapter`. This API is not the standard configuration path in Spring Security 6; replace it with `SecurityFilterChain` beans plus needed authentication/user/password beans.

Legacy example, **does not compile on Boot 3 / Security 6**:

```java
// Historical example from an older framework line; does NOT run with Spring Security 6.
public class LegacySecurity extends WebSecurityConfigurerAdapter {
    @Override
    protected void configure(HttpSecurity http) throws Exception {
        http.authorizeRequests()
            .antMatchers("/public").permitAll()
            .anyRequest().authenticated()
            .and().httpBasic();
    }
}
```

Modern bean-based configuration:

```java
@Bean
SecurityFilterChain securityFilterChain(HttpSecurity http)
        throws Exception {
    return http
            .authorizeHttpRequests(auth -> auth
                    .requestMatchers("/public").permitAll()
                    .anyRequest().authenticated())
            .httpBasic(Customizer.withDefaults())
            .build();
}
```

**Do not treat the two blocks as equivalent merely because URLs look alike.** Verify matcher ordering, multiple chains, exception responses, CSRF, and authentication providers—especially if the old config overrode `configure(AuthenticationManagerBuilder)`/`configure(WebSecurity)`. Switching to bean composition can change dependency injection and configuration precedence.

### 5.2. authorizeRequests/antMatchers → authorizeHttpRequests/requestMatchers

Before example (historical):

```java
// Old API pattern for comparison; do not use as a new compile example:
http.authorizeRequests()
    .antMatchers("/public/**").permitAll()
    .antMatchers("/admin/**").hasRole("ADMIN")
    .anyRequest().authenticated();
```

After example:

```java
http.authorizeHttpRequests(auth -> auth
        .requestMatchers("/public/**").permitAll()
        .requestMatchers("/admin/**").hasRole("ADMIN")
        .anyRequest().authenticated());
```

**Verify behavior instead of only renaming:**

- Does the matcher handle `/admin`, `/admin/`, and `/admin/report` as intended?
- Do context path and servlet path affect it?
- Are HTTP methods still restricted if method-specific matchers were used previously?
- How does `HttpFirewall` treat encoded slashes, percent encoding, semicolons, and path traversal?
- Is **specific-to-general** rule order preserved?
- Was a trailing `anyRequest().authenticated()` accidentally dropped?
- On MVC over Servlet, choose the right matcher mechanism: `requestMatchers(String...)` is a convenience API whose actual matcher depends on config and version. When preserving specific semantics, use an explicit `RequestMatcher` and test in a real Servlet environment.

Never copy legacy Ant pattern strings verbatim and assume every edge case matches. Whenever path matching underpins business access control, write a **path/method test table** before changing it.

### 5.3. Lambda DSL for csrf, httpBasic, formLogin, logout

Legacy no-arg chained styles often linger in codebases upgraded across multiple releases:

```java
// Old-style pattern; some no-arg methods/entry points are deprecated:
http.csrf().disable();
http.httpBasic();
http.formLogin();
```

When migrating to the Lambda DSL, keep intent explicit:

```java
http.httpBasic(Customizer.withDefaults());
http.formLogin(Customizer.withDefaults());

// Only when a specific CSRF policy applies:
http.csrf(csrf -> csrf
        .ignoringRequestMatchers("/webhook/verified"));
```

**Never copy `csrf(csrf -> csrf.disable())` just to mimic legacy code without auditing the security model.** Both old and new snippets compile, yet security expectations may differ. With session/cookie authentication, CSRF normally stays enabled; exceptions for webhooks or bearer tokens must be evaluated against the trust model and endpoint.

Explicit logout example:

```java
http.logout(logout -> logout
        .logoutUrl("/logout")
        .logoutSuccessUrl("/login?logout")
        .permitAll());
```

With default CSRF enabled, logout usually requires **POST** and a CSRF token; never switch to GET logout just to dodge a 403 in tests. Logout tests must prove the session loses access and cookies/remember-me are cleared, not only that a redirect occurred.

### 5.4. @EnableGlobalMethodSecurity → @EnableMethodSecurity

In older releases:

```java
// Historical configuration, not the modern approach:
@EnableGlobalMethodSecurity(prePostEnabled = true)
```

In Spring Security 6:

```java
@Configuration
@EnableMethodSecurity
public class MethodSecurityConfiguration {
}
```

Still, **do not stop at swapping the annotation**. Verify:

- `@PreAuthorize` blocks unauthorized callers before the method body executes.
- `@PostAuthorize` rejects return values after the method finishes, meaning side effects may already have executed; never rely on post-authorization alone to protect mutating operations.
- Rules referencing `#parameter` still resolve parameter names properly—check whether `@P` or compiler flag `-parameters` is needed.
- Service beans are invoked **through the Spring proxy**, rather than `new Service()` or `this.securedMethod()` self-invocation bypassing the interceptor.
- `@Secured`, JSR-250 annotations, or custom permission evaluators are explicitly enabled if required, rather than assuming one flag enables every annotation family.
- `ROLE_` prefixes and OAuth/JWT authority mappings preserve prior semantics.

Expression example:

```java
@PreAuthorize("hasRole('ADMIN') or (isAuthenticated() and #owner == authentication.name)")
public String readOwner(@P("owner") String owner) {
    return "profile:" + owner;
}
```

Here `@P` comes from `org.springframework.security.core.parameters.P`. Test that user `alice` reading owner `bob` is denied rather than testing only that `admin` succeeds.

### 5.5. SecurityContextHolderFilter and explicit context saving

An older custom filter may set:

```java
SecurityContextHolder.getContext()
        .setAuthentication(authentication);
```

Under Spring Security 6's `SecurityContextHolderFilter` and configured explicit saving, **setting `ThreadLocal` alone does not keep the next request authenticated**. If a custom flow requires session persistence, build a fresh context and save it through the matching `SecurityContextRepository` after verifying real credentials:

```java
// Architectural snippet: use only after verification by a trusted authentication provider.
SecurityContext context = SecurityContextHolder.createEmptyContext();
context.setAuthentication(authentication);
SecurityContextHolder.setContext(context);
securityContextRepository.saveContext(context, request, response);
```

This snippet needs the variables and imports of a custom authentication flow; **it is not a standalone program**. Never use it to trust a raw username from the request. If using standard `formLogin()`, HTTP Basic, or OAuth2/OIDC login, let the framework manage context persistence through its built-in flow.

**Decisive regression test:** log in over an HTTP socket with a cookie jar, then issue a second request: `GET /me` must stay authenticated if the contract is session-based. Unit tests inspecting `SecurityContextHolder.getContext()` on the same thread are insufficient.

### 5.6. Do not equate “new” with “safer” if controls were relaxed

Some edits make tests pass by stripping protections:

```java
// Do not use as a migration shortcut:
http.csrf(csrf -> csrf.disable());
http.authorizeHttpRequests(auth -> auth.anyRequest().permitAll());
```

Such settings require strong architectural security justification and are never default replacements for legacy APIs. A valid migration preserves—or **deliberately tightens**—approved security policy rather than deleting negative tests to avoid failures.

## 6. Building a regression suite around the security contract

### 6.1. Required test layers

| Test layer | Tooling | Purpose |
| --- | --- | --- |
| Unit policy | JUnit + Mockito | Test business rules and permission logic; does not verify security proxies/filters |
| Method security | `@SpringBootTest`, `@WithMockUser` | Test `@PreAuthorize`/`@PostAuthorize` through Spring-managed proxies |
| Web MVC security | `MockMvc` + `spring-security-test` | Test request matchers, entry points, CSRF, authorization, and error mapping |
| Real Servlet HTTP | `@SpringBootTest(RANDOM_PORT)` + Java `HttpClient` | Test cookies, redirects, session persistence, and form login over real sockets |
| Reverse proxy/TLS | Staging Nginx/Ingress + HTTP client | Test external host/scheme/prefix, forwarded headers, and `Secure` cookies |
| Browser E2E | Playwright/Selenium | Test `SameSite`/cookie acceptance, cross-origin, navigation, and IdP callbacks |

Not every pull request has to run the entire cross-browser suite, yet for changes touching sessions, cookies, or proxies, **MockMvc alone is insufficient**. If legacy behavior depends on servlet paths, send real Servlet requests with matching path/dispatcher types.

### 6.2. Minimum HTTP behavior matrix

| Actor and request | Expected behavior | Migration invariant to preserve |
| --- | --- | --- |
| Anonymous `GET /public` | 200 | Public routes stay public |
| Anonymous `GET /private` with Basic | 401 + Basic challenge | Entry point / API contract |
| Normal Basic user `GET /private` | 200 | Authentication provider wired properly |
| Normal user `GET /admin/report` | 403 | Role check not bypassed |
| Admin `GET /admin/report` | 200 | Role mapping intact |
| Wrong password `GET /private` | 401 | Invalid credentials never treated as permitted anonymous |
| Normal user `POST /settings` without CSRF | 403 in session-based web config | CSRF not disabled |
| Normal user `POST /settings` with CSRF | 200/redirect per API contract | Form/CSRF repository working |
| Anonymous `POST /settings` | 401/302 per entry point and policy | Cannot act merely by having CSRF |
| `GET /error` or ERROR dispatch | Policy-aligned error handling | No login redirect loops |
| Form/session login: POST then GET | User stays authenticated | `SecurityContext`/cookie persistence |
| Logout then GET private | Prompts for login | Session invalidation/cleanup |
| Same user requests another tenant's resource | 403 or 404 per security policy | Object-level authorization |
| OAuth2 callback failure / state mismatch | Fails safely | State/code validation preserved |
| Valid CORS preflight | Responds per allowlist | Never open `*` loosely with credentials |

Status codes above vary by `AuthenticationEntryPoint`: **form login typically redirects 302** for anonymous users, whereas HTTP Basic typically returns 401. Confirm the existing mechanism and real contract before changing expected statuses; never “standardize” everything to 403.

### 6.3. Test both allowed and denied outcomes

Solid coverage includes at least:

- **Positive test**: user with matching role/authority succeeds.
- **Negative test**: authenticated user lacking permission is denied.
- **Anonymous test**: unauthenticated caller cannot read protected data.
- **Cross-user/object test**: User A cannot access User B's object even when URL/ID is guessable.
- **CSRF test**: unsafe method without a token is rejected.
- **Session test**: valid session after login; revoked access after logout or expiry.
- **Error/redirect test**: error pages do not loop; entry points fit browser vs API clients.
- **Path boundary test**: trailing slashes, servlet contexts, similar prefixes, HTTP methods, and URL encoding do not accidentally alter rules.

Assert the **exact denial cause** when needed, not just the status code: 403 can come from CSRF, method security, URL authorization, or business validation. Separate positive/negative tests per layer isolate root causes cleanly.

## 7. Runnable demo: modern config and regression suite on Spring Boot 3.4

This section builds a small Servlet project on **Spring Boot 3.4.2 + Java 17** to verify behavior before and after replacing an equivalent legacy config. Use the Gradle Wrapper if generated via Spring Initializr. Do not compile historical APIs on the new version; they serve only for comparison.

### 7.1. Project structure

```text
security-upgrade-regression/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/com/example/upgrade/
    │   ├── UpgradeApplication.java
    │   ├── SecurityConfig.java
    │   ├── AdminTaskService.java
    │   └── DemoController.java
    └── test/java/com/example/upgrade/
        ├── SecurityHttpRegressionTest.java
        └── MethodSecurityRegressionTest.java
```

### 7.2. Gradle

File `settings.gradle`:

```groovy
rootProject.name = 'security-upgrade-regression'
```

File `build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.4.2'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
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

tasks.withType(JavaCompile).configureEach {
    options.compilerArgs.add('-parameters')
    options.compilerArgs.add('-Xlint:deprecation')
}

tasks.named('test') {
    useJUnitPlatform()
}
```

`-parameters` supports parameter-name discovery for parameter-bound SpEL expressions. `-Xlint:deprecation` only surfaces compiler warnings; it never proves runtime behavior is correct. The demo project uses Spring Security 6.x syntax with zero removed classes imported.

### 7.3. Application

File `src/main/java/com/example/upgrade/UpgradeApplication.java`:

```java
package com.example.upgrade;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class UpgradeApplication {
    public static void main(String[] args) {
        SpringApplication.run(UpgradeApplication.class, args);
    }
}
```

### 7.4. SecurityConfig

File `src/main/java/com/example/upgrade/SecurityConfig.java`:

```java
package com.example.upgrade;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.PasswordEncoder;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableMethodSecurity
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        UserDetails alice = User.withUsername("alice")
                .password(encoder.encode("alice-pass"))
                .roles("USER")
                .build();

        UserDetails admin = User.withUsername("admin")
                .password(encoder.encode("admin-pass"))
                .roles("ADMIN")
                .build();

        return new InMemoryUserDetailsManager(alice, admin);
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {

        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/public", "/error")
                            .permitAll()
                        .requestMatchers("/admin/**")
                            .hasRole("ADMIN")
                        .anyRequest().authenticated())
                .httpBasic(Customizer.withDefaults())
                .build();
    }
}
```

**Demo policy:**

- `/public` is anonymously accessible.
- `/admin/**` allows `ROLE_ADMIN` only.
- Remaining URLs require authentication.
- HTTP Basic is this example's entry point; unauthorized callers receive 401 rather than a 302 form-login redirect.
- CSRF stays enabled by default: POST without a CSRF token is blocked. For stateless bearer-token APIs, design CSRF policy separately; **do not apply this Basic template blindly to every architecture**.
- `@EnableMethodSecurity` activates the `@PreAuthorize` interceptor.
- Sample users/passwords are for local testing only; never deploy these credentials to production.

### 7.5. Method security service and countable side effect

File `src/main/java/com/example/upgrade/AdminTaskService.java`:

```java
package com.example.upgrade;

import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.core.parameters.P;
import org.springframework.stereotype.Service;

@Service
public class AdminTaskService {

    private final AtomicInteger invoked = new AtomicInteger();

    @PreAuthorize("hasRole('ADMIN')")
    public String performAdminTask() {
        invoked.incrementAndGet();
        return "admin-ok";
    }

    @PreAuthorize("""
            hasRole('ADMIN') or
            (isAuthenticated() and #owner == authentication.name)
            """)
    public String readOwnerPage(@P("owner") String owner) {
        return "owner:" + owner;
    }

    public int invocationCount() {
        return invoked.get();
    }
}
```

`invocationCount()` here is a test counter, not a production metric. `@PreAuthorize` must block the method body before the counter increments when the caller lacks the role. Direct method tests through the Spring proxy prove enforcement ordering instead of relying solely on an HTTP 403 that could come from another filter.

### 7.6. Controller

File `src/main/java/com/example/upgrade/DemoController.java`:

```java
package com.example.upgrade;

import java.util.Map;

import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {

    private final AdminTaskService adminTaskService;

    public DemoController(AdminTaskService adminTaskService) {
        this.adminTaskService = adminTaskService;
    }

    @GetMapping("/public")
    public Map<String, String> publicPage() {
        return Map.of("message", "public");
    }

    @GetMapping("/me")
    public Map<String, String> me(Authentication authentication) {
        return Map.of("user", authentication.getName());
    }

    @GetMapping("/admin/task")
    public Map<String, String> adminTask() {
        return Map.of("result",
                adminTaskService.performAdminTask());
    }

    @GetMapping("/owners/{owner}")
    public Map<String, String> ownerPage(@PathVariable String owner) {
        return Map.of("result",
                adminTaskService.readOwnerPage(owner));
    }

    @PostMapping("/settings")
    public Map<String, Boolean> updateSettings() {
        return Map.of("accepted", true);
    }
}
```

`/settings` intentionally writes nothing to a DB; the test goal is proving CSRF blocks a POST without a token. `anyRequest().authenticated()` lets authenticated users reach the controller, while `AdminTaskService` guards ownership per parameter. When upgrading frameworks, both URL and method layers must preserve behavior.

## 8. HTTP regression tests with MockMvc

File `src/test/java/com/example/upgrade/SecurityHttpRegressionTest.java`:

```java
package com.example.upgrade;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class SecurityHttpRegressionTest {

    @Autowired
    MockMvc mvc;

    @Test
    void publicUrlRemainsPublic() throws Exception {
        mvc.perform(get("/public"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.message").value("public"));
    }

    @Test
    void privateUrlRejectsAnonymous() throws Exception {
        mvc.perform(get("/me"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void privateUrlRejectsBadPassword() throws Exception {
        mvc.perform(get("/me")
                        .with(httpBasic("alice", "wrong-pass")))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void authenticatedUserReadsOwnIdentity() throws Exception {
        mvc.perform(get("/me")
                        .with(httpBasic("alice", "alice-pass")))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.user").value("alice"));
    }

    @Test
    void userCannotCallAdminUrl() throws Exception {
        mvc.perform(get("/admin/task")
                        .with(httpBasic("alice", "alice-pass")))
                .andExpect(status().isForbidden());
    }

    @Test
    void adminCanCallAdminUrl() throws Exception {
        mvc.perform(get("/admin/task")
                        .with(httpBasic("admin", "admin-pass")))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.result").value("admin-ok"));
    }

    @Test
    void ownerParameterCannotBeForged() throws Exception {
        mvc.perform(get("/owners/admin")
                        .with(httpBasic("alice", "alice-pass")))
                .andExpect(status().isForbidden());
    }

    @Test
    void ownerCanReadOwnPage() throws Exception {
        mvc.perform(get("/owners/alice")
                        .with(httpBasic("alice", "alice-pass")))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.result").value("owner:alice"));
    }

    @Test
    void unsafeRequestWithoutCsrfIsRejected() throws Exception {
        mvc.perform(post("/settings")
                        .with(httpBasic("alice", "alice-pass")))
                .andExpect(status().isForbidden());
    }

    @Test
    void unsafeRequestWithCsrfCanPass() throws Exception {
        mvc.perform(post("/settings")
                        .with(httpBasic("alice", "alice-pass"))
                        .with(csrf()))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.accepted").value(true));
    }
}
```

**Key takeaway:** `MockMvc` traverses the filter chain when Spring Security is wired into the test context as shown. `httpBasic(...)` supplies Basic credentials so tests do not assume session logins. `spring-security-test`'s `csrf()` supplies a valid CSRF token for filter testing, though **it does not prove real browser token transport works** in production.

Expected result: **10 passing tests** with the demo code and config. The 401/403 codes match **HTTP Basic**; under `formLogin()`, anonymous requests would receive a 302 login redirect instead of 401.

## 9. Method security regression tests: verifying proxies and side effects

File `src/test/java/com/example/upgrade/MethodSecurityRegressionTest.java`:

```java
package com.example.upgrade;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.test.context.support.WithMockUser;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

@SpringBootTest
class MethodSecurityRegressionTest {

    @Autowired
    AdminTaskService adminTaskService;

    @Test
    @WithMockUser(username = "alice", roles = "USER")
    void nonAdminMethodCallIsDeniedBeforeBody() {
        int before = adminTaskService.invocationCount();

        assertThatThrownBy(adminTaskService::performAdminTask)
                .isInstanceOf(AccessDeniedException.class);

        assertThat(adminTaskService.invocationCount())
                .isEqualTo(before);
    }

    @Test
    @WithMockUser(username = "admin", roles = "ADMIN")
    void adminMethodCallWorks() {
        assertThat(adminTaskService.performAdminTask())
                .isEqualTo("admin-ok");
    }

    @Test
    @WithMockUser(username = "alice", roles = "USER")
    void userCanReadOwnOwnerParameter() {
        assertThat(adminTaskService.readOwnerPage("alice"))
                .isEqualTo("owner:alice");
    }

    @Test
    @WithMockUser(username = "alice", roles = "USER")
    void userCannotReadOtherOwnerParameter() {
        assertThatThrownBy(
                () -> adminTaskService.readOwnerPage("admin"))
                .isInstanceOf(AccessDeniedException.class);
    }
}
```

**Why these tests matter:** `@WithMockUser` supplies a mock authentication in the Spring test context while the service is invoked **through its Spring-managed proxy**; method-security annotations are genuinely exercised. Calling `new AdminTaskService()` or Mockito `@InjectMocks` **lacks the security interceptor**, creating false positives even when protection is missing.

When migrating from `@EnableGlobalMethodSecurity` to `@EnableMethodSecurity`, run these tests on both the existing and upgraded versions (adapting test sources to compatible test dependencies). The HTTP suite above catches URL bugs, while direct service tests isolate interceptor/proxy bugs.

## 10. Running and capturing a trustworthy baseline

In the demo repository with the Gradle Wrapper:

```bash
# Linux/macOS
./gradlew clean test
./gradlew compileJava

# Windows PowerShell
.\gradlew.bat clean test
.\gradlew.bat compileJava
```

All **14 tests** across the two classes are expected to pass when config, Java, and dependencies are right. This is the **expected outcome of the example**, not a claim this lesson was executed in the learner's environment. If your local framework/dependency versions differ, run the commands to verify compilation and adjust APIs accordingly.

Capture evidence:

- Source commit SHA before changes, plus Java/Gradle/Boot/Security dependency versions.
- Test report `build/test-results/test`, pass/fail counts, and environment (OS, JDK, DB, session store).
- Specific HTTP contracts verified: 200, 401, 403, CSRF, principal, and methods.
- List of deprecated symbols from `-Xlint:deprecation` and their source paths.
- Untested areas (SSO/proxy/TLS/browser cookies) with assigned owners for follow-up.

**Never treat environment-flaky test runs as proof a migration passed.** Flaky tests must be triaged, fixed, or quarantined deliberately rather than letting “occasionally green” serve as a release gate.

## 11. Additional tests for apps using form login/sessions

The HTTP Basic example tests authorization cleanly, yet **does not cover** form login. A project upgrading real form login needs session-aware regression tests:

1. Anonymous `GET /account` receives `302 Location: /login`.
2. `GET /login` returns valid login HTML without redirecting to itself.
3. `GET /login` creates or reuses a session, and the form contains a CSRF token matching the flow.
4. `POST /login` with valid username/password and CSRF using the **same cookie jar** succeeds.
5. Client accepts the new `Set-Cookie` after login (session ID may rotate).
6. `GET /account` with that cookie jar returns 200 and the expected principal.
7. `GET /account` from a fresh/cookieless client still prompts for login.
8. `POST /logout` with a valid CSRF token invalidates the local session per policy; the next request prompts for login.
9. Failed logins never create an authenticated session; error messages leak no sensitive details.
10. Error/login/static asset URLs cause no redirect loops when anonymous.

This catches regressions after changing `SecurityContext` persistence, session config, filter chains, or success handlers that MockMvc with `with(user("alice"))` misses.

When using `@SpringBootTest(webEnvironment = RANDOM_PORT)` and Java `HttpClient` with a `CookieManager`, configure the right redirect policy when diagnosing `302` responses. With OAuth2/OIDC, also test `state`, redirect URIs, browser `SameSite` cookies, and ID token validation across trust boundaries. Never mock an identity provider by skipping token signature/issuer checks and calling it sufficient.

## 12. Subtle behavior shifts when migrating APIs

### 12.1. RequestMatcher ordering

In `authorizeHttpRequests`, order typically picks the first matching rule. Wrong example:

```java
http.authorizeHttpRequests(auth -> auth
        .requestMatchers("/**").permitAll()
        .requestMatchers("/admin/**").hasRole("ADMIN"));
```

The broad public rule swallows the admin rule. Testing `GET /admin/report` as a regular user must fail, catching misordered refactors immediately. Put specific rules first and a meaningful trailing rule:

```java
http.authorizeHttpRequests(auth -> auth
        .requestMatchers("/admin/**").hasRole("ADMIN")
        .requestMatchers("/public/**").permitAll()
        .anyRequest().authenticated());
```

### 12.2. Anonymous authentication and hasRole

`AnonymousAuthenticationToken` can have `isAuthenticated()==true` at the token level, yet Spring Security's `isAuthenticated()` expression uses trust-resolver semantics. Never write a custom guard `authentication != null && authentication.isAuthenticated()` that treats anonymous as logged in. After migration, test both anonymous **and** authenticated-without-role callers.

`hasRole("ADMIN")` uses the `ROLE_ADMIN` convention in standard configurations, whereas `hasAuthority("ADMIN")` matches literal `ADMIN`. If authority mapping changes during an upgrade, test with real roles from the authentication provider rather than only mock admins.

### 12.3. CORS and preflight

An `OPTIONS` preflight can be rejected if CORS filters/rules sit in the wrong order or chain. Configure CORS only when the app genuinely serves cross-origin browsers; never pair `allowedOrigins("*")` with credentials as a workaround.

Regression tests should check:

- Allowed origin → preflight returns exact allowed methods/headers/credentials.
- Disallowed origin → not opened.
- Cross-origin requests carry cookies or bearer credentials per the designed scheme.
- CSRF still enforces on unsafe requests backed by cookies/sessions.

### 12.4. Error pages and authentication entry points

When a controller exception triggers `/error` / `ERROR` dispatch, rule evaluation can differ after migration. If blocked, clients may receive a login redirect instead of 500 or enter a loop. Test real app errors, error handling, and `AuthenticationEntryPoint`. You may need to permit `DispatcherType.ERROR` or a custom error path, without blindly opening all dispatcher types.

### 12.5. RequestCache, saved requests, and redirects

Form login can save the pre-login URL and redirect back to it afterward. Changing chains or matchers can make `RequestCache`, success URLs, or custom success handlers emit the wrong host or path. Regression tests should assert exact `Location` values per contract rather than only `302`; with TLS termination, test through the proxy with external host/scheme.

### 12.6. CSRF is not authorization

HTTP `403` can stem from missing CSRF, missing authority, or business policy. To keep tests unambiguous:

- Positive POST with CSRF + authorized user.
- Negative POST without CSRF + authorized user.
- Negative POST with CSRF + unauthorized user.
- Anonymous POST with/without CSRF per entry point.

Only the full combination isolates causes. If migration changes the CSRF repository, token request handler, or cookie strategy, test compatibility in a real browser or SPA.

### 12.7. @PostAuthorize and side effects

Changing method-security infrastructure must never silently alter evaluation timing without tests. `@PreAuthorize` checks before the body; `@PostAuthorize` checks after the method returns a value. Never rely solely on `@PostAuthorize` to guard transfers, payments, deletions, or email sends—side effects may already have executed. Denial tests must assert side effects **did not occur** when policy requires blocking upfront.

## 13. Gated migration workflow

### Gate A — Standardize requirements and baseline

1. Lock down organization-supported target framework and dependency versions.
2. Document current behavior and security invariants.
3. Inventory deprecated APIs, legacy classes, filters, providers, matchers, and custom auth flows.
4. Write/stabilize regression tests for allow, deny, anonymous, CSRF, sessions, and method security.
5. Run tests on old code, archive reports, and confirm expected results.
6. If tests are already red, fix or document explicit exceptions before migrating; never proceed with a “blind baseline.”

**Gate A exit criterion:** a test suite validating an approved contract, with an owner and reproducible runs.

### Gate B — Narrow replacement by API group

1. Change **one small group**: e.g., `WebSecurityConfigurerAdapter` → `SecurityFilterChain`, without altering method security and sessions simultaneously.
2. Compile and run unit + web + method tests; compare statuses, authorities, `Location`, and session behavior.
3. If regressions differ from baseline, determine **whether it is a bug or an intentional change**; never tweak assertions just to go green.
4. Commit only when one API swap passes tests and has a small reviewable diff.
5. Move to the next group: URL matchers, method security, DSL, context persistence, logout.
6. Keep revertible commits/tags at each stage.

**Gate B exit criterion:** target code no longer depends on legacy APIs in the chosen scope, runtime behavior passes the same test suite, and no prior protection was dropped.

### Gate C — Clean up legacy APIs and final verification

1. Re-scan source and test code for deprecated symbols; confirm no duplicate filter chains or stale config beans remain.
2. Do not delete custom filters/adapters immediately if tests do not yet cover those paths or integration tests have not run.
3. Run the full suite on pinned target dependencies: unit, integration, method, HTTP, and sessions.
4. Use staging/proxies/browsers whenever changes affect cookies, HTTPS, redirects, or IdPs.
5. Review security invariants and diffs: deny paths still deny, CSRF stays active, cookie policies were not weakened.
6. Only at the very end delete dead code, temporary bridges, old imports, and obsolete migration comments.
7. Obtain reviewer sign-off and record change logs if policy requires.

**Gate C exit criterion:** codebase is free of obsolete APIs within the upgrade scope, tests are reliably green, and no protections were opened unintentionally.

### Gate D — Canary release and rollback

1. Deploy to production-like canary/staging (HTTPS proxy, cookie flags, session store, IdP).
2. Verify login success/failure, 401/403, CSRF, logout, error routes, and real method permissions.
3. Monitor 401/403 rates, login failures, redirect loops, session churn, and unauthorized attempts without logging secrets.
4. If a behavioral regression appears: **roll back in a controlled way** to the prior artifact; never disable a security rule hastily in production.
5. Document root cause and add a regression test so it cannot return.
6. Expand rollout only once canary and smoke tests meet defined thresholds.

**Never** treat green `gradle test` alone as sufficient for release if API changes affect proxies, sessions, or SSO not simulated by the test suite.

## 14. PR review checklist for removing deprecated APIs

### 14.1. Code review

- [ ] Every old API is listed with a clearly sourced, version-matched replacement.
- [ ] No `WebSecurityConfigurerAdapter` or unnecessary legacy overrides remain on the target branch.
- [ ] `SecurityFilterChain` beans and `@Order`/`securityMatcher` match real URLs.
- [ ] `authorizeHttpRequests` preserves rule order; trailing rules do not widen access.
- [ ] `requestMatchers` are tested with servlet/context paths, HTTP methods, and special paths.
- [ ] `@EnableMethodSecurity` and security proxies guard invoked services.
- [ ] No fabricated authenticated tokens for request usernames or skipped provider checks.
- [ ] `SecurityContext` is saved per policy if custom authentication exists.
- [ ] CSRF and logout behavior did not shift unintentionally.
- [ ] CORS, security headers, session cookies, reverse proxies, and error dispatches keep full config.
- [ ] Two overlapping authentication configs do not compete in the context.
- [ ] Legacy configs with `csrf.disable()`/`permitAll()` were not copied into new APIs just for a green build.

### 14.2. Test review

- [ ] Baseline tests passed on the old version before swapping APIs.
- [ ] Unit, method-security, MockMvc, and HTTP integration tests ran cleanly.
- [ ] HTTP 200/302/401/403 have positive, negative, and anonymous assertions.
- [ ] Missing CSRF is rejected; valid CSRF + right permissions succeed.
- [ ] Server-side owner/tenant/resource authorization remains enforced.
- [ ] Post-login sessions and logout work properly in stateful apps.
- [ ] Tests verify side effects do not happen when `@PreAuthorize` denies access.
- [ ] Method-security tests invoke through proxies, never `new Service()`.
- [ ] Proxy/HTTPS changes are tested at the real proxy/browser layer.
- [ ] No tests were deleted, ignored, or altered to mask unapproved regressions.

### 14.3. Operations review

- [ ] Dependency lock/BOM/Java version are documented.
- [ ] No old compiler warnings remain in upgrade scope; out-of-scope warnings have owners.
- [ ] Audit logs omit passwords, `Authorization` headers, session cookies, and access/refresh tokens.
- [ ] Artifact rollback path and cross-release session/token compatibility plan exist.
- [ ] Canary/smoke tests pass on production-like configuration.
- [ ] Security reviewer and system owner confirmed no permission boundaries regressed.

## 15. Common errors and proper fixes

| Symptom | Likely cause | Proper fix |
| --- | --- | --- |
| Compile fails on `WebSecurityConfigurerAdapter` | Old API removed in Security 6 | Migrate to beans, rewire auth, run regressions |
| `antMatchers` missing on new API | Old DSL/matcher method replaced | Use `requestMatchers`/explicit `RequestMatcher`; test path semantics |
| Anonymous reaches `/admin` | Matcher changed or broad `permitAll` placed first | Compare rule order; add negative admin test |
| Controller tests pass yet service is unguarded | Missing `@EnableMethodSecurity` or self-invocation bypasses proxy | Test Spring-managed service directly |
| `@PreAuthorize` fails to read `#owner` | Missing parameter metadata; SpEL mapping differs | Use `@P`/`-parameters` and test owner mismatch |
| `POST /settings` returns 403 after migration | Missing/invalid CSRF, missing role, or wrong chain | Separate CSRF tests from authorization tests |
| API GET returns 302 instead of 401 | Entry point shifted from Basic/API to form login | Restore entry point matching API contract |
| Form login succeeds, next request is anonymous | Stateless session, dropped cookie, or context unsaved | Test with real HTTP + `CookieManager` and context repository |
| `JSESSIONID` drops behind HTTPS proxy | Bad `Secure`/`SameSite`/`Domain`/`Path` or forwarded scheme | Inspect browser Network/Storage and proxy |
| Redirects to `http://app:8080` | App unaware of external scheme/host | Trusted forwarded headers + proxy integration test |
| Error page loops login redirects | `/error` or `ERROR` dispatch blocked | Set appropriate error policy and inspect root exception |
| Filter executes twice | Both bean auto-registered and added to Security chain | Control filter registration intentionally |
| `hasRole("ADMIN")` fails despite `ADMIN` authority | Missing `ROLE_` prefix match | Align actual authority mapping and policy |
| Unit tests pass yet IDOR hits production | Client-controlled ID not tested for owner/tenant | Add object/tenant negative tests |
| OAuth2 callback fails after upgrade | Cookie/state/redirect URI/scheme/host mismatch | IdP/proxy/browser tests without disabling state checks |
| Old code deleted, rollback fails | No compatibility/test sign-off | Small commits, artifact versioning, and canary gates |

## 16. Self-check questions

**1.** Why shouldn't you immediately delete a `deprecated` API and adjust tests to match the new response?  
**Answer:** Because you must prove whether security behavior/policy stayed intact or changed deliberately. Updating expected responses just to turn tests green can hide an authorization regression.

**2.** Why is `@SpringBootTest` with an injected service bean more informative than `new Service()` when testing `@PreAuthorize`?  
**Answer:** Annotations are enforced by Spring's method-security proxy/interceptor. Calling a manually constructed instance bypasses the proxy and skips protection.

**3.** Is replacing `antMatchers("/admin/**")` with `requestMatchers("/admin/**")` enough on its own?  
**Answer:** No. You must test wildcards, servlet/context paths, rule order, HTTP methods, encoding, and responses for users with and without the role.

**4.** `POST /login` succeeds, yet `GET /me` is anonymous—will unit tests catch every cause?  
**Answer:** Not necessarily. Real HTTP session/cookie tests, `SecurityContextRepository`/explicit save, proxies, and multi-node stores may be needed.

**5.** Why doesn't `-Xlint:deprecation` replace a regression suite?  
**Answer:** Warnings only flag discouraged APIs; they do not verify HTTP statuses, authorization, CSRF, or session behavior.

**6.** When migrating Spring Security from legacy DSL to Lambda DSL, should you disable CSRF to stop 403s?  
**Answer:** No. Inspect tokens/sessions and policy; disabling CSRF changes a security boundary and requires separate review.

**7.** Why test authenticated users lacking the role in addition to anonymous callers?  
**Answer:** Testing only anonymous and admin can miss authorization bypasses by low-privileged authenticated users.

**8.** Is `@PostAuthorize` alone enough to protect a mutating POST operation?  
**Answer:** No. The method body can execute side effects before the post-check runs. Use pre-checks/business policies and verify no side effects occur when denied.

**9.** When is it safe to delete legacy adapters and bridge classes?  
**Answer:** Once the new branch has a test baseline, passing regressions, behavior review approval, zero remaining consumers, and planned rollback/compatibility.

**10.** Does a passing MockMvc suite prove `SameSite` cookies work in production?  
**Answer:** No. `SameSite`/`Secure`/third-party cookies and TLS termination require real browser/proxy tests.

## 17. Conclusion

**Removing deprecated APIs is the final step of proving behavioral equivalence, never the starting goal.** In Spring Security Servlet, upgrades typically touch `SecurityFilterChain`, `authorizeHttpRequests`, `requestMatchers`, Lambda DSL, `@EnableMethodSecurity`, and `SecurityContext` persistence. Each change can affect **request matching, authentication, authorization, CSRF, sessions, login/logout, error handling, proxies, and browsers**.

A reliable workflow is:

1. **Lock versions and measure legacy behavior with regression tests.**
2. **Replace one API group at a time without mixing bug fixes or policy shifts.**
3. **Re-run both positive and negative tests and analyze every difference.**
4. **Verify sessions/HTTPS/proxies/browsers on real layers where risk exists.**
5. **Only after every gate passes, delete legacy code and release with a rollback plan.**

The finish line is not merely code “free of deprecation warnings,” but **a modern configuration whose security behavior has been tested and proven intact**.
