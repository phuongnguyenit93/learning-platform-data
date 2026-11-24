# Distinguishing a Shared AuthenticationManager from Per-SecurityFilterChain AuthenticationManagers

> **Scope:** Spring Security **Servlet** (Spring MVC, Java 17+, Spring Boot 3.5.x / Spring Security 6.5.x). This lesson focuses on how HTTP requests select a `SecurityFilterChain` and how **each chain receives its `AuthenticationManager`**: shared, independent, or inheriting via a parent. You must clearly distinguish **filter-chain selection rules** from **provider selection rules**, verify wiring when configuring multiple URL zones, understand session/context boundaries, and know how to choose the right pattern. A complete runnable example uses Spring Boot 3.5.7 and HTTP Basic to observe the difference; demo password data is for local use only.

## 1. Two Selection Layers: Select the Filter Chain First, Then Authenticate

In a Servlet application, the processing flow is typically as follows:

```text
Client sends HTTP request (path, headers, cookies)
               │
               ▼
    Spring Security's FilterChainProxy
               │
               ├─ iterates SecurityFilterChains in order
               ├─ picks the FIRST CHAIN whose RequestMatcher matches
               └─ runs the selected chain's filter set
                               │
                               ▼
                   Authentication filter
                   (Basic, form login, bearer...)
                               │
                   creates Authentication request
                               │
                               ▼
                  AuthenticationManager
                    (manager used by the filter)
                               │
                     ProviderManager?
                               │
                 ├─ AuthenticationProvider A
                 ├─ AuthenticationProvider B
                 └─ optional parent manager
                               │
                   Successful Authentication
                               │
                      SecurityContext
                               │
                         Authorization
                 (roles, scopes, rules, resource)
```

**Two distinct decisions:**

1. **`FilterChainProxy` selects a `SecurityFilterChain`** based on HTTP request matchers and `@Order`. Only the first matching chain processes the request through its filters; it does not run all chains sequentially.
2. **The chain's authentication filter uses an `AuthenticationManager`**. This manager may be an object shared with another chain, a chain-specific manager, or a manager with a parent to reuse some common mechanism.

For example, two URLs `/api/orders` and `/portal/profile` can enter two different filter chains yet still call **the exact same manager** to verify username/password. Conversely, they can use **two separate managers**, checking two independent account stores. Two chains do not automatically create two isolated sets of users.

## 2. Core Concepts and Easily Confused Names

| Component | Responsibility | Are they the same thing? |
| --- | --- | --- |
| `SecurityFilterChain` | List of security filters applied to requests matching a matcher | Not an `AuthenticationManager` |
| `FilterChainProxy` | Selects the first chain matching the request | Does not iterate `AuthenticationProvider`s |
| `HttpSecurity` | Builder creating the configuration of a `SecurityFilterChain` | Not the built chain itself |
| `AuthenticationManager` | `authenticate(Authentication)` API; returns authenticated result or throws error | An interface; does not define how sessions are saved |
| `ProviderManager` | Common implementation using a list of `AuthenticationProvider`s | Selects providers by token type and processing outcome |
| `AuthenticationProvider` | Authenticates one credential/token type via a specific mechanism | Reusable across managers; check state and policy |
| `SecurityContext` | Holds the current `Authentication` | Not a user list or manager |
| `AuthorizationManager` | Decides access permissions after authentication exists | Does not replace authentication |

The phrase **global/shared `AuthenticationManager`** has two usages that are easy to conflate:

- **Global configured by Spring Security**: a common manager built through global configuration, involving `AuthenticationConfiguration` and beans/providers registered via framework mechanisms.
- **Shared designed by the application**: an `AuthenticationManager` object the application creates and **explicitly passes the same reference** into two or more chains. It may be a Spring bean or a configuration object; “shared” here refers to **the actual object used**, without automatically guaranteeing every place in the application context uses that object.

A `@Bean AuthenticationManager` does not by itself prove every authentication filter uses that bean. When multiple managers exist, **you must verify which chain receives which manager** via code or tests. A chain can also build a **local manager from `AuthenticationManagerBuilder`** and use the global one as a parent depending on configuration; never assume everything omitting `.authenticationManager(...)` uses the exact same instance.

## 3. Configuring Multiple SecurityFilterChains: Matchers and Order

Abbreviated example:

```java
@Bean
@Order(1)
SecurityFilterChain api(HttpSecurity http) throws Exception {
    http.securityMatcher("/api/**")
        .authorizeHttpRequests(auth -> auth.anyRequest().authenticated())
        .httpBasic(Customizer.withDefaults());
    return http.build();
}

@Bean
@Order(2)
SecurityFilterChain portal(HttpSecurity http) throws Exception {
    http.securityMatcher("/portal/**")
        .authorizeHttpRequests(auth -> auth.anyRequest().authenticated())
        .httpBasic(Customizer.withDefaults());
    return http.build();
}
```

This is a **Spring `@Configuration` snippet**, not yet a runnable project since user sources/managers and endpoints are omitted. Here:

- `@Order(1)` is evaluated before `@Order(2)`. The first chain matches `/api/**`; the second matches `/portal/**`.
- `http.securityMatcher(...)` decides **whether the chain applies to the request**.
- `authorizeHttpRequests().requestMatchers(...)` only decides **permissions inside the selected chain**. It is not a chain-selection tool.
- If a catch-all `anyRequest`/default chain is configured at a higher precedence, it can capture `/api/**` too and shadow later chains.
- If **no chain matches** the request, that request is **not protected by Spring Security** through the declared chains. With multiple path-restricted chains, include a final catch-all chain with an intentional policy.
- Each `HttpSecurity` is configured to build a corresponding chain. The number of chains **does not dictate** the number of managers or providers.

### Illustrative Request Paths

| Request | First matching chain | Authentication manager used |
| --- | --- | --- |
| `GET /api/me` | API chain `@Order(1)` | The manager that the API chain's authentication filter was configured to use |
| `GET /portal/me` | Portal chain `@Order(2)` | The manager that the Portal chain's authentication filter was configured to use |
| `GET /health` | Neither of the two chains above | Protected only if a catch-all or another matching chain exists |

**Note on form login:** if a chain only matches `/portal/**` yet default form login uses `/login` and `POST /login` falls outside the matcher, login endpoints may not be handled by that chain's filters as expected. When separating form-login flows, align login/callback/logout paths and matchers so requests actually enter the right chain.

## 4. Pattern A: Sharing One AuthenticationManager

With the shared pattern, multiple chains reference the same `AuthenticationManager` (typically a `ProviderManager` with shared providers/user store). The two chains can still differ in filters, entry points, session policies, CSRF, and authorization.

```text
                  ┌── API SecurityFilterChain ── BasicAuthenticationFilter ─┐
HTTP request ─────┤                                                        ├─ sharedManager
                  └── Portal SecurityFilterChain ── BasicAuthenticationFilter┘      │
                                                                                   ├─ DaoAuthenticationProvider
                                                                                   └─ shared user store
```

You can declare a shared manager bean and pass **the same bean** into both chains:

```java
@Bean
AuthenticationManager sharedManager(UserDetailsService users,
                                    PasswordEncoder encoder) {
    DaoAuthenticationProvider provider = new DaoAuthenticationProvider(users);
    provider.setPasswordEncoder(encoder);
    return new ProviderManager(provider);
}

@Bean
@Order(1)
SecurityFilterChain api(HttpSecurity http,
                        AuthenticationManager sharedManager) throws Exception {
    http.securityMatcher("/api/**")
        .authenticationManager(sharedManager)
        .httpBasic(Customizer.withDefaults())
        .authorizeHttpRequests(auth -> auth.anyRequest().hasRole("API"));
    return http.build();
}

@Bean
@Order(2)
SecurityFilterChain portal(HttpSecurity http,
                           AuthenticationManager sharedManager) throws Exception {
    http.securityMatcher("/portal/**")
        .authenticationManager(sharedManager)
        .httpBasic(Customizer.withDefaults())
        .authorizeHttpRequests(auth -> auth.anyRequest().hasRole("PORTAL"));
    return http.build();
}
```

This is a **configuration example needing `UserDetailsService`, `PasswordEncoder`, imports, and controllers**, not a standalone runnable class. To avoid bean type ambiguity if the application has multiple `AuthenticationManager`s, use explicit bean names/`@Qualifier`.

**Important consequence:** with one user store containing `api-user` (`ROLE_API`) and `portal-user` (`ROLE_PORTAL`), the shared manager can **authenticate both accounts on both chains**. After authentication, each chain's authorization rules decide whether the user enters. Typical results:

- `api-user` + right password calling `/api/me` → **200**.
- `api-user` + right password calling `/portal/me` → authentication **succeeds**, yet lacking `ROLE_PORTAL` returns **403**.
- Non-existent user or wrong password → authentication fails; with HTTP Basic, typically **401**.

**A 403 in the second case does not mean the manager didn't know the account**. On the contrary, it shows the shared manager **recognized the credentials**, while the chain's policy blocked authorization. Do not take “an API account gets 403 on portal” as proof that credentials were rejected by portal authentication.

### When Is a Shared Manager Suitable?

- Same identity set and same credential-checking policy, e.g., multiple HTTP paths authenticating against one user store.
- Differing only in **authorization** by role, or endpoint/filter layout within the same trust domain.
- Wanting to reuse a centrally governed set of providers, avoiding inconsistent password encoder/user cache configuration across chains.
- Needing unified account lockout, password rotation, and auditing in a single identity store.

**Risk:** every chain using a shared manager can send credentials from the shared set to that authentication mechanism. If you genuinely must isolate realms, tenants, or credential types, role-based authorization alone may not meet authentication-isolation requirements. Be especially careful with a shared manager having multiple providers whose `supports(...)` match the same token type: one provider failing does not necessarily block the next provider, depending on error type/rules of `ProviderManager`.

## 5. Pattern B: Separate Manager per SecurityFilterChain

With this pattern, each chain invokes **its own manager**. You can use two independent `ProviderManager`s with distinct providers and user stores, or managers with different structures when the API uses bearer tokens while the portal uses form login.

```text
HTTP GET /api/me
   → API chain
   → BasicAuthenticationFilter
   → apiManager
   → API provider / API users

HTTP GET /portal/me
   → Portal chain
   → BasicAuthenticationFilter
   → portalManager
   → Portal provider / Portal users
```

Attach a dedicated manager via `http.authenticationManager(managerForThisChain)`. The official API allows overriding the shared manager with a local manager on `HttpSecurity`.

### What Changes in Behavior?

If `apiManager` only has `api-user` and `portalManager` only has `portal-user`:

| Credentials sent to endpoint | Result with separate managers | Explanation |
| --- | --- | --- |
| `api-user` right password → `/api/me` | **200** | API manager knows the account |
| `portal-user` right password → `/portal/me` | **200** | Portal manager knows the account |
| `api-user` right password → `/portal/me` | **401** with HTTP Basic | Portal manager does not authenticate API accounts |
| `portal-user` right password → `/api/me` | **401** with HTTP Basic | API manager does not authenticate Portal accounts |
| No Authorization header → either endpoint | **401** with HTTP Basic | Filter requests credentials |
| Manager returns authenticated user lacking chain's required role | **403** | Authentication succeeds, authorization denies |

The table assumes **HTTP Basic + no prior login session + no other parent/fallback**. The same username string could exist in both stores with different passwords and roles; outcomes depend on the actual configuration.

**Important:** separate managers **do not automatically create an absolute security sandbox across filter chains**. If chains share a `SecurityContextRepository`/HTTP session, a request may pick up a saved `Authentication` from the session **without re-invoking the manager as on fresh credentials**. This matters especially when one chain uses form login/sessions and another chain also accepts session cookies. Design proper context/session boundaries, stateless policies, and authorization; also test sending a cookie after logging into the other chain.

### When Are Separate Managers Needed?

- Two application areas use **two independent identity sources** and require an account from realm A never to be accepted by realm B.
- Machine-to-machine channels vs. browsers, with different credentials/providers/verification policies.
- API using a JWT Resource Server while portal uses DB/form login; the two systems have distinct trust anchors and lifecycles.
- Needing separate auditing, failure policies, or account-source governance per channel, after verifying how context/sessions are shared.

Do not create separate managers merely because there are multiple URLs. If all chains authenticate the same set of users and only require different authorization, a single shared manager is usually simpler.

## 6. Complete Example: Two Chains, Two Truly Independent Managers

Build a minimal Spring Boot app with two endpoints:

- `GET /api/me` accepts **api-user / api-pass** via HTTP Basic.
- `GET /portal/me` accepts **portal-user / portal-pass** via HTTP Basic.
- Each chain has its own `ProviderManager`, its own `DaoAuthenticationProvider`, and its own `InMemoryUserDetailsManager`.
- A third catch-all **denies all paths outside the demo scope**, avoiding accidentally leaving URL areas unprotected.
- Only GET is used, keeping Spring Security's default CSRF protection; HTTP Basic in the example uses **STATELESS** sessions to clearly test manager boundaries.
- Demo passwords are encoded with BCrypt at startup; never use these hardcoded values in real environments.

### 6.1. Directory Structure

```text
manager-scope-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/dev/example/managers/ManagerScopeApplication.java
    └── test/java/dev/example/managers/ManagerScopeApplicationTests.java
```

`settings.gradle`:

```groovy
rootProject.name = 'manager-scope-demo'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.7'
    id 'io.spring.dependency-management' version '1.1.7'
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
```

Spring Boot manages compatible Spring Security dependency versions, so no separate Spring Security version is declared for the starter. In real deployments, use patched versions approved by the project.

### 6.2. Application Java File

Create `src/main/java/dev/example/managers/ManagerScopeApplication.java`:

```java
package dev.example.managers;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.core.annotation.Order;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.authentication.dao.DaoAuthenticationProvider;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class ManagerScopeApplication {

    public static void main(String[] args) {
        SpringApplication.run(ManagerScopeApplication.class, args);
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    // Only accepts requests starting with /api/
    @Bean
    @Order(1)
    SecurityFilterChain apiChain(
            HttpSecurity http, PasswordEncoder encoder) throws Exception {

        AuthenticationManager apiManager = newManager(
                "api-user", "api-pass", "API", encoder);

        http.securityMatcher("/api/**")
                .authenticationManager(apiManager)
                .authorizeHttpRequests(auth -> auth
                        .anyRequest().hasRole("API"))
                .httpBasic(Customizer.withDefaults())
                .sessionManagement(session -> session
                        .sessionCreationPolicy(SessionCreationPolicy.STATELESS));

        return http.build();
    }

    // Only accepts requests starting with /portal/
    @Bean
    @Order(2)
    SecurityFilterChain portalChain(
            HttpSecurity http, PasswordEncoder encoder) throws Exception {

        AuthenticationManager portalManager = newManager(
                "portal-user", "portal-pass", "PORTAL", encoder);

        http.securityMatcher("/portal/**")
                .authenticationManager(portalManager)
                .authorizeHttpRequests(auth -> auth
                        .anyRequest().hasRole("PORTAL"))
                .httpBasic(Customizer.withDefaults())
                .sessionManagement(session -> session
                        .sessionCreationPolicy(SessionCreationPolicy.STATELESS));

        return http.build();
    }

    // Denies all other paths, preventing protection gaps.
    @Bean
    @Order(3)
    SecurityFilterChain denyOtherPaths(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(auth -> auth
                .anyRequest().denyAll());
        return http.build();
    }

    private AuthenticationManager newManager(
            String username, String rawPassword,
            String role, PasswordEncoder encoder) {

        UserDetails account = User.withUsername(username)
                .password(encoder.encode(rawPassword))
                .roles(role)
                .build();

        UserDetailsService users = new InMemoryUserDetailsManager(account);

        DaoAuthenticationProvider dao = new DaoAuthenticationProvider(users);
        dao.setPasswordEncoder(encoder);

        // Each call returns a fresh ProviderManager,
        // with no parent and no shared user store.
        return new ProviderManager(dao);
    }

    @RestController
    static class WhoAmIController {
        @GetMapping({"/api/me", "/portal/me"})
        String me(Authentication authentication) {
            return authentication.getName();
        }
    }
}
```

**Points to observe in the code:**

1. Both `apiChain` and `portalChain` receive `HttpSecurity` builders yet invoke `newManager(...)` **twice separately**. Each call creates a `ProviderManager` with only that realm's account; no provider is shared between the two managers.
2. `http.authenticationManager(apiManager)` binds the API chain to the exact manager; `http.authenticationManager(portalManager)` does the same for the Portal chain. Reading this configuration is far more reliable than guessing from `@Bean` names.
3. `securityMatcher("/api/**")` and `securityMatcher("/portal/**")` select the **chain**; `hasRole("API")` and `hasRole("PORTAL")` decide **authorization** after authentication.
4. `newManager` is intentionally a **private method**, not a Spring bean. This clarifies its local scope and prevents multiple `AuthenticationManager` beans from causing ambiguity during type-based injection.
5. `DaoAuthenticationProvider` handles `UsernamePasswordAuthenticationToken` created by the HTTP Basic filter, using `PasswordEncoder.matches(...)` to compare the password against the BCrypt hash in `UserDetails`.
6. `STATELESS` ensures each HTTP Basic request is authenticated via current credentials rather than relying on a previously saved login session. It does not mean the app is automatically immune to CSRF across all client types; assess whether cookies or Authorization headers are sent automatically by browsers.
7. `denyOtherPaths` is the final catch-all chain with a default matcher for remaining requests, applying deny-all. It adds no extra accounts and provides no alternate login path.

### 6.3. Running and Observing HTTP

In the directory containing `build.gradle`, with Gradle compatible with Spring Boot 3.5 and JDK 17+, run:

```bash
gradle bootRun
```

If a Gradle Wrapper exists, use `./gradlew bootRun` on macOS/Linux or `gradlew.bat bootRun` on Windows. In another terminal, on Windows use `curl.exe` (avoiding the PowerShell `curl` alias):

```bash
curl.exe -i -u api-user:api-pass http://localhost:8080/api/me
curl.exe -i -u portal-user:portal-pass http://localhost:8080/portal/me
curl.exe -i -u api-user:api-pass http://localhost:8080/portal/me
curl.exe -i -u portal-user:portal-pass http://localhost:8080/api/me
curl.exe -i http://localhost:8080/api/me
```

On macOS/Linux replace `curl.exe` with `curl`. Never put real passwords into shell history; these are demo credentials.

Core HTTP results, omitting variable headers:

| Request | HTTP status | Main body on success |
| --- | --- | --- |
| API credentials → `/api/me` | **200** | `api-user` |
| Portal credentials → `/portal/me` | **200** | `portal-user` |
| API credentials → `/portal/me` | **401** | No user info returned |
| Portal credentials → `/api/me` | **401** | No user info returned |
| No credentials → `/api/me` | **401** | HTTP Basic challenge |

In this table, the **401** on both “wrong-realm” rows occurs because **the selected chain's manager does not recognize that account**, even though the credentials are valid for the other chain's manager. This is the hallmark behavior differing from the shared-manager version.

### 6.4. Automated Test for Manager Boundaries

Create `src/test/java/dev/example/managers/ManagerScopeApplicationTests.java`:

```java
package dev.example.managers;

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
        .MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class ManagerScopeApplicationTests {

    @Autowired
    MockMvc mvc;

    @Test
    void eachPathUsesOnlyItsOwnManager() throws Exception {
        mvc.perform(get("/api/me")
                        .with(httpBasic("api-user", "api-pass")))
                .andExpect(status().isOk())
                .andExpect(content().string("api-user"));

        mvc.perform(get("/portal/me")
                        .with(httpBasic("portal-user", "portal-pass")))
                .andExpect(status().isOk())
                .andExpect(content().string("portal-user"));

        mvc.perform(get("/portal/me")
                        .with(httpBasic("api-user", "api-pass")))
                .andExpect(status().isUnauthorized());

        mvc.perform(get("/api/me")
                        .with(httpBasic("portal-user", "portal-pass")))
                .andExpect(status().isUnauthorized());

        mvc.perform(get("/api/me"))
                .andExpect(status().isUnauthorized());
    }
}
```

Run:

```bash
gradle test
```

The test sends real requests via `MockMvc` through the configured **Spring Security filter chain**. It is more valuable than testing solely with mock `Authentication` via `@WithMockUser`, because `@WithMockUser` can bypass the password provider and does not prove the chain's actual manager is correct.

If you need to confirm the application protects other paths, add a test calling `GET /unknown` and assert the request **does not succeed** due to the `denyAll` catch-all (the exact status is influenced by the fallback chain's entry point and exception-handling config).

## 7. Switching the Example to a Shared Manager: Predictable Changes

In the application above, replace the two `newManager(...)` calls with **one shared bean** holding **both users**. Representative configuration:

```java
@Bean
AuthenticationManager sharedManager(PasswordEncoder encoder) {
    UserDetails apiUser = User.withUsername("api-user")
            .password(encoder.encode("api-pass"))
            .roles("API")
            .build();

    UserDetails portalUser = User.withUsername("portal-user")
            .password(encoder.encode("portal-pass"))
            .roles("PORTAL")
            .build();

    UserDetailsService users =
            new InMemoryUserDetailsManager(apiUser, portalUser);

    DaoAuthenticationProvider dao = new DaoAuthenticationProvider(users);
    dao.setPasswordEncoder(encoder);
    return new ProviderManager(dao);
}
```

This is a **snippet to place inside the existing `@Configuration` class**; to complete the shared variant, update **the signatures of both filter chain beans to inject that `sharedManager` bean**, and use the same `.authenticationManager(sharedManager)` line on both chains. Remove the old `newManager(...)` calls. Example of the wiring inside one bean:

```java
@Bean
@Order(1)
SecurityFilterChain apiChain(HttpSecurity http,
                             AuthenticationManager sharedManager)
        throws Exception {
    http.securityMatcher("/api/**")
            .authenticationManager(sharedManager)
            .authorizeHttpRequests(auth -> auth
                    .anyRequest().hasRole("API"))
            .httpBasic(Customizer.withDefaults())
            .sessionManagement(session -> session
                    .sessionCreationPolicy(SessionCreationPolicy.STATELESS));
    return http.build();
}
```

Apply the same idea to the Portal chain with `hasRole("PORTAL")`. **This is a configuration variant, not meant to be pasted alongside two identically named `apiChain` beans.** When there is one manager bean intended to be shared, use clear naming/`@Qualifier` in larger codebases so you do not rely on injection guesswork.

After switching:

- `api-user` to `/api/me` remains **200**.
- `portal-user` to `/portal/me` remains **200**.
- `api-user` to `/portal/me`: the shared manager **authenticates successfully**, yet lacking `ROLE_PORTAL` typically yields **403**.
- `portal-user` to `/api/me`: the shared manager authenticates successfully, yet lacking `ROLE_API` typically yields **403**.

What shifts 401 into 403 is **the manager's scope changing**, not changing URL matchers or forcing changes to `hasRole`. Both chains still run separately and retain their respective authorization rules.

**Never rely mechanically on 401/403 statuses** across all applications: form login may redirect 302 when unauthenticated; custom entry points/access denied handlers may alter statuses. Conclude based on the actual filters, managers, providers, and configured rules.

## 8. Pattern C: Separate Managers with a Shared Parent

Sharing and isolation are not strictly binary. `ProviderManager` supports a **parent `AuthenticationManager`**, allowing multiple child managers to have local providers while sharing common authentication methods.

```text
                  apiChain                            portalChain
                      │                                    │
                      ▼                                    ▼
              ProviderManager A                    ProviderManager B
              [API-only provider]                  [Portal-only provider]
                      │ parent                            │ parent
                      └──────────────┬─────────────────────┘
                                     ▼
                         Shared parent manager
                           [Common provider]
```

**Semantics to understand:** the child tries the providers it manages. If not yet authenticated and no stopping error was hit, it can consult the parent. Thus the parent is **a real additional authentication path**, not merely “borrowing code” or metadata.

Illustrative snippet building parent/child managers:

```java
AuthenticationManager common = new ProviderManager(commonProvider);

ProviderManager apiManager =
        new ProviderManager(List.of(apiProvider), common);

ProviderManager portalManager =
        new ProviderManager(List.of(portalProvider), common);
```

This is **Java pseudoconfiguration**, assuming `commonProvider`, `apiProvider`, and `portalProvider` are already declared as valid `AuthenticationProvider`s; not a standalone runnable program. This structure is useful when a shared authentication mechanism is permitted on both channels, such as a well-defined service credential type.

**Risk:** if a child manager rejects credentials belonging to its own realm yet the parent accepts them, you can break isolation policies. `BadCredentialsException` from one provider does not always make `ProviderManager` stop immediately; understand ordering/fallback/exception types. Account status errors like `LockedException` or `DisabledException` normally stop the flow. Parent design must clearly define namespaces, trusted issuers, token types, and rules blocking weak fallbacks.

Never add a parent just so “every account can log in somewhere”. If the requirement is strict isolation between two identity realms, two `ProviderManager`s without a shared parent are usually easier to verify.

## 9. Distinguishing Shared Manager, Local Manager, and Local Provider Registration

### 9.1. Explicit Shared Object

```java
http.authenticationManager(sharedManager);
```

The chain uses the manager object specified at that configuration point. If two chains receive **the exact same reference**, it is a shared manager in the operational sense.

### 9.2. Explicit Local Object

```java
http.authenticationManager(new ProviderManager(apiProvider));
```

The chain uses its own manager. Ensure `apiProvider` is initialized with the right credential store, encoder, and exception policy. This snippet requires an `apiProvider` variable; it is not standalone code.

### 9.3. Adding a Provider via HttpSecurity

```java
http.authenticationProvider(apiProvider);
```

This **registers a provider into `HttpSecurity`'s configuration**, not directly equivalent to “all chains share one manager object”. Depending on how the framework builds `AuthenticationManagerBuilder` and the parent, a local manager may combine custom providers with the ability to call the global manager. Inspect each chain's actual configuration; never declare that `authenticationProvider(...)` guarantees complete isolation.

### 9.4. Not Attaching a Manager Explicitly

```java
http.securityMatcher("/api/**")
    .httpBasic(Customizer.withDefaults());
```

When `authenticationManager(...)` is not called, Spring Security decides/wires the manager through its configuration mechanism. It may use global configuration, provider/service beans, or a manager built for `HttpSecurity`. **Do not infer solely from the number of chains whether a shared manager exists.** When a testable, auditable isolation contract is required, prefer attaching managers explicitly.

### 9.5. Exposing an AuthenticationManager Bean to Services/Controllers

An `@Bean AuthenticationManager` can be injected into a service for programmatic authentication; injecting a manager in a service does not mean filters across all chains call that exact bean. Hence **the exposed manager**, **the manager used by authentication filters**, and **whether a manager has a parent** are three separate facts to verify.

When multiple beans of the same type exist, use `@Qualifier` or proper bean names; avoid ambiguous type-based field injection that triggers `NoUniqueBeanDefinitionException` or causes Spring to pick an unintended bean.

## 10. SecurityContext and Sessions: Why Separate Managers Are Not Enough

`AuthenticationManager` is typically called **when credentials must be verified**. After a successful login, Spring Security can store `Authentication` in `SecurityContext` and via `SecurityContextRepository`/HTTP session. Subsequent requests carrying a session cookie can be recognized from the saved context **without re-running every provider**.

Suppose:

1. A browser logs in via form on `/portal/**` and stores a session cookie.
2. The browser calls `/api/**` sending the same cookie, without sending an API Basic header.
3. Depending on the API chain's session/context repository configuration and authorization rules, the saved portal identity may still be visible; you cannot conclude “a separate API manager means the API will always return 401” without testing sessions.

Achieving real isolation requires designing **all of**:

- URL matchers, filter chain order, and authentication mechanisms.
- Managers/providers/credential stores/trust realms.
- `SecurityContextRepository`, session policy, cookie scope, login/logout, remember-me.
- CORS/CSRF for browsers and automatic cookie/Authorization submission.
- Authorization rules, especially roles, scopes, issuers, tenants, and resource-level permissions.

In the demo, `SessionCreationPolicy.STATELESS` combined with HTTP Basic cleanly isolates requests carrying individual credentials. In systems with form login, also test logging into one chain and using **that same cookie** to access another chain. Never use a global/static `SecurityContextHolder` to solve session sharing.

## 11. Different Mechanisms Between API and Web App

A real-world application might use:

| Zone | Chain | Authentication mechanism | Typical manager/provider |
| --- | --- | --- | --- |
| `/api/**` | API chain | `oauth2ResourceServer().jwt(...)` | Manager/provider validating JWTs per issuer/JWKS |
| `/portal/**` | Portal chain | `formLogin(...)` | Username/password manager/provider backed by DB |
| `/internal/**` | Internal chain | HTTP Basic/mTLS/custom as required | Dedicated manager/provider for service identities |
| Other paths | Catch-all | Deny-all or controlled policy | Does not necessarily need a login manager |

This is an **illustrative architecture table**. With OAuth2 Resource Server, authentication filters/providers may be built and wired internally by the DSL, and multi-issuer architectures can use `AuthenticationManagerResolver<HttpServletRequest>` to pick a manager per request. A **Resolver** is a technique for selecting a manager **inside one authentication mechanism**; it does not replace `FilterChainProxy` rules selecting chains by matcher.

There is no rule that “every API must have a new manager” or “JWT and form login must share one manager”. Design according to trust boundaries, credential types, session strategies, and governance needs.

## 12. How to Identify Which Manager Is Used When Debugging

Effective investigation order:

1. **Verify request path and method**, including context path/proxy rewrites.
2. **List all `SecurityFilterChain`s by `@Order`**, along with `securityMatcher` and catch-all chains. Identify the first matching chain.
3. **Identify authentication filters** present in the chain: Basic, form login, bearer token, custom filters… If only authorization filters exist without a credential-ingesting mechanism, unauthenticated requests will not become authenticated.
4. **Find where the chain's manager is configured**: `http.authenticationManager(...)`, providers in `HttpSecurity`, global authentication config, or a resolver. Never inspect bean names alone.
5. **For `ProviderManager`, check provider list, order, `supports(tokenClass)`, null/exceptions, and parent**.
6. **Check state**: is the request sending fresh credentials or already carrying a `SecurityContext` restored from session? Are remember-me or other token filters active?
7. **Interpret status/entry point**: 401 Basic challenge, 302 form-login redirect, and 403 access denied are outcomes of configured mechanisms; do not diagnose solely from status.
8. **Check trust domain and authorization**: a user accepted by the manager yet lacking a role differs from a user not authenticated by the manager.
9. **Check auditing**: log token type, chain/matcher, outcome, and error code; never write passwords, Authorization headers, raw tokens, or password hashes.

You can enable Spring Security DEBUG logging in a controlled development environment to see the list of security filters and which chain protects a request. Do not leave sensitive debug logging enabled long-term in production. If code uses multiple managers, write `MockMvc` or real integration tests for each `(path × credential × session state)` combination, because looking solely at `ProviderManager` constructors does not confirm request routing.

## 13. Required Test Matrix with Multiple Chains

| Case | What must be proven |
| --- | --- |
| `/api/**` matches API chain | API filters/manager actually process the request |
| `/portal/**` matches Portal chain | Not shadowed by an earlier catch-all |
| Path outside matchers | Catch-all protects properly; no endpoints accidentally left open |
| Right API-realm credentials on API | 200 when authorized |
| Right Portal-realm credentials on Portal | 200 when authorized |
| API credentials on Portal with **separate managers** | Authentication fails per policy, typically 401 with Basic |
| API credentials on Portal with **shared manager** | Authentication may succeed, yet role check usually returns 403 |
| Wrong password, locked account | Not accepted via fallback/other provider |
| Request without credentials | Entry point/challenge or redirect matches mechanism |
| Session from Portal then calling API | Context is not unintentionally reused |
| Logout, expiration, remember-me | No access remains after state changes per policy |
| One chain uses JWT, one uses Basic/form | No confusion across token types, issuers, managers, or sessions |
| Shared provider in parent | Verify fallback path and account state |
| Manager bean injected into service | Do not assume filters also use that bean |

Test **both positive and negative cases**, because a system may work normally for valid users while harboring serious flaws when credentials from another realm are mistakenly accepted.

## 14. Common Mistakes and Fixes

1. **“Two `SecurityFilterChain`s = two independent managers.”** False. Chain count and manager count have no mandatory 1-to-1 relationship. Inspect the actual object bound to each chain.
2. **“Having one `@Bean AuthenticationManager` means all chains use it.”** Cannot be concluded. The bean might be for services; filter chains may use another manager or be configured locally.
3. **“`requestMatchers` selects the chain.”** Each chain's `securityMatcher` is the chain-level filter. `requestMatchers` inside `authorizeHttpRequests` is an internal rule after the chain is chosen.
4. **Putting a catch-all `@Order(1)` ahead of the API chain.** It shadows subsequent chains. Put specific matchers at higher precedence and catch-all last.
5. **Omitting a catch-all and thinking all paths are protected.** Requests matching no chain fall outside Spring Security filter chain protection.
6. **Keeping form login at `/login` while matching only `/portal/**`.** Login endpoints may miss the chain. Align login/logout/callback endpoints consistently with matchers.
7. **Confusing 403 with the manager rejecting credentials.** 403 can mean authentication succeeded yet authorization lacked permissions; compare with Basic's 401 on authentication failure.
8. **Separate managers yet sharing sessions/context across chains without testing.** Isolating user stores does not isolate sessions. Evaluate policies with cookie-bearing requests too.
9. **Declaring multiple `AuthenticationManager` beans and injecting without `@Qualifier`.** Can cause ambiguity errors or pick the wrong bean during refactoring.
10. **Assuming `http.authenticationProvider(provider)` is always completely isolated from the global parent.** Understand how the builder constructs the manager and parent rather than guessing isolation.
11. **Letting a shared parent authenticate credentials rejected by a child across boundaries.** Establish explicit namespaces, token types, account states, and fallback policies.
12. **Disabling CSRF and sessions arbitrarily to “make the API work”.** With browsers auto-sending cookies/Basic auth, CSRF protection may still be needed. Configure per credential mechanism and client traits.
13. **Testing only with `@WithMockUser`.** Mock security context tests bypass authentication filters/managers; add tests sending real credentials to endpoints.
14. **Calling a manager programmatically and assuming all HTTP chains use that manager.** A manager injected into a controller can differ from the manager used by Basic/form/bearer filters.
15. **Putting every credential type into one provider regardless of token type.** Blurs boundaries and invites unwanted fallbacks. Use appropriate providers/managers/resolvers.

## 15. Exercises and Completion Criteria

**Exercise 1 — Draw the two selection layers:** trace step by step how matchers pick the chain and the manager picks providers for `GET /api/me` carrying Basic credentials. Explain why changing `@Order` does not change `AuthenticationProvider` ordering.

**Exercise 2 — Observe 401 and 403:** run the separate-manager demo and capture HTTP statuses for the 5 requests in Section 6. Switch to the shared manager per Section 7 and compare the two cross-realm requests; explain via authentication/authorization rather than copying status codes.

**Exercise 3 — Form login:** design an additional `/portal/**` chain using form login and sessions. Define GET/POST login paths, logout, CSRF tokens, cookies, and cross-session tests with the API chain. Do not merely swap `.httpBasic(...)` for `.formLogin(...)` and ignore endpoint paths.

**Exercise 4 — Parent:** given an OTP/machine-identity provider intentionally shared across chains, draw an appropriate child–parent structure; specify which credentials must never fall back to the parent.

**Exercise 5 — Debug:** suppose `/api/me` returns 302 to a login form when 401 Basic was expected. Write an inspection sequence covering selected chain, `@Order`, enabled filters, entry point, manager, and session before editing code.

**Exercise 6 — Real tests:** add integration tests for `/outside`, wrong passwords, disabled accounts, and an existing session from another chain. Explain why tests using only `@WithMockUser` do not prove manager boundaries.

**Lesson completion** means being able to answer: “Which request enters which chain?”, “Which filter calls which manager?”, “Which providers does that manager hold, and does it have a parent?”, “What happens when credentials are right yet permissions are missing?”, and “Can a session keep a request from calling the manager again?”. Distinguishing **authentication manager** independence from **security context** independence is the foremost requirement when designing multiple chains.

## 16. Official Reference Documentation

- [Spring Security 6.5 — Java Configuration, Multiple HttpSecurity Instances](https://docs.spring.io/spring-security/reference/6.5/servlet/configuration/java.html): `securityMatcher`, `@Order`, first matching chain, and risk of unprotected paths.
- [Spring Security 6.5 — Username/Password Authentication](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/index.html): global manager, `@Bean AuthenticationManager`, `http.authenticationManager(...)` attaching local managers.
- [Spring Security 6.5 — Servlet Authentication Architecture](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/architecture.html): `AuthenticationManager`, `ProviderManager`, parent, and `SecurityContext`.
- [Spring Security 6.5 — Servlet Architecture](https://docs.spring.io/spring-security/reference/6.5/servlet/architecture.html): `FilterChainProxy`, security filters, configuring/reading filter chains.
- [Spring Security 6.5 — DaoAuthenticationProvider](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/dao-authentication-provider.html): username/password, `UserDetailsService`, and `PasswordEncoder`.
- [Spring Boot 3.5.7 — Release](https://spring.io/blog/2025/10/23/spring-boot-3-5-7-available-now/): specific Spring Boot version used in the Gradle example.

References focus on Spring Security 6.5/Boot 3.5 because that is the API line of the examples. If your project uses Spring Security 7, WebFlux, or custom authentication filters, verify the API/configuration of your exact version and stack before applying patterns mechanically.