# Composing HTTP Authorization Conditions with AuthorizationManagers.allOf and anyOf

> **Context:** Spring Security **Servlet** 6.x, Java 17+, HTTP authorization using `HttpSecurity.authorizeHttpRequests`. This lesson focuses on `AuthorizationManagers.allOf(...)` (**AND** composition) and `AuthorizationManagers.anyOf(...)` (**OR** composition), how `AuthorizationManager<RequestAuthorizationContext>` works, grant/deny/abstain outcomes, evaluation order, and common design mistakes. Examples run with Spring Boot 3.3.5 and Java 17.

## 1. The Problem: One URL Often Has Multiple Authorization Requirements

For an endpoint protecting reports, business rules are not necessarily just "logged in" or "has one role". For instance:

- `GET /reports/view`: user is **authenticated** **AND** (**has `REPORT_READ`** **OR** **has role `ADMIN`**).
- `GET /reports/export`: user **has role `ADMIN`** **AND** **has authority `REPORT_EXPORT`**.
- `GET /review`: user **has role `ADMIN`** **OR** **has role `AUDITOR`**.

Written as logical expressions:

```text
VIEW   = AUTHENTICATED && (REPORT_READ || ROLE_ADMIN)
EXPORT = ROLE_ADMIN && REPORT_EXPORT
REVIEW = ROLE_ADMIN || ROLE_AUDITOR
```

With Spring Security Servlet, we can compose multiple `AuthorizationManager<RequestAuthorizationContext>` instances to express this policy structurally. `AuthorizationManagers.allOf` corresponds to **every required condition must pass**; `AuthorizationManagers.anyOf` corresponds to **only one branch needs to allow**.

**This is authorization, not authentication.** Prior to this, an authentication filter such as `BasicAuthenticationFilter`, `UsernamePasswordAuthenticationFilter`, or a Bearer token filter must verify credentials and create a trusted `Authentication`. `AuthorizationManager` merely evaluates the identity/permissions/request context **already known to the system** against the policy.

## 2. Map of APIs and Data Types

Commonly used classes:

| API | Role |
| --- | --- |
| `AuthorizationManager<T>` | Decision-maker interface for a protected target of type `T` |
| `AuthorizationManagers.allOf(...)` | Combines multiple managers with **AND** |
| `AuthorizationManagers.anyOf(...)` | Combines multiple managers with **OR** |
| `AuthorityAuthorizationManager<T>` | Checks authorities or roles in `Authentication` |
| `AuthenticatedAuthorizationManager<T>` | Checks authentication levels such as `authenticated()`, `fullyAuthenticated()` |
| `RequestAuthorizationContext` | Servlet HTTP request context, holding `HttpServletRequest` and matcher variables when present |
| `AuthorizationDecision` | Represents grant/deny result for managers using the decision API |
| `AuthorizationFilter` | Applies `AuthorizationManager` to requests reaching the authorization step |
| `ExceptionTranslationFilter` | Routes missing-authentication errors to entry point (e.g., 401/redirect) or insufficient-permission errors to access-denied handling (typically 403) |

Illustrative logical API signatures:

```java
// Interface-explaining code; no need to redeclare in your application.
AuthorizationManager<RequestAuthorizationContext> rule = ...;

AuthorizationManager<RequestAuthorizationContext> mustPassAll =
        AuthorizationManagers.allOf(firstRule, secondRule);

AuthorizationManager<RequestAuthorizationContext> mayPassAny =
        AuthorizationManagers.anyOf(firstRule, secondRule);
```

Variables `firstRule` and `secondRule` in the fragment must have types compatible with `AuthorizationManager<RequestAuthorizationContext>`. `AuthorizationManagers` does not accept precomputed `boolean`s, does not read databases itself, does not issue JWTs, and does not replace `SecurityFilterChain`.

### Type T Matters

`AuthorizationManager<T>` is a generic API. For the `authorizeHttpRequests().requestMatchers(...).access(...)` DSL on Servlet, `T` is typically **`RequestAuthorizationContext`**. Never take an `AuthorizationManager<MethodInvocation>` meant for method security or a type meant for reactive WebFlux and cast it for HTTP Servlet.

Typical imports:

```java
import org.springframework.security.authorization.AuthorizationManager;
import org.springframework.security.authorization.AuthorizationManagers;
import org.springframework.security.authorization.AuthorityAuthorizationManager;
import org.springframework.security.authorization.AuthenticatedAuthorizationManager;
import org.springframework.security.web.access.intercept.RequestAuthorizationContext;
```

In the complete example below, manager variables are explicitly typed with `RequestAuthorizationContext` so the compiler checks the target object type being authorized.

## 3. allOf: Logical AND of Conditions

Visualize `allOf(A,B,C)`:

```text
Request -> A?
             |
       deny -+---> DENY
             |
           grant / no-decision
             |
             v
             B?
             |
       deny -+---> DENY
             |
           grant / no-decision
             |
             v
             C?
             |
       deny -+---> DENY
             |
           grant / no-decision
             |
             v
          GRANT (if no manager vetoed)
```

With typical managers returning explicit true/false decisions, AND works just like the truth table:

| A | B | `allOf(A,B)` |
| --- | --- | --- |
| Allow | Allow | Allow |
| Allow | Deny | Deny |
| Deny | Allow | Deny |
| Deny | Deny | Deny |

For example, allowing report export only when the user both holds `ROLE_ADMIN` and has `REPORT_EXPORT`:

```java
AuthorizationManager<RequestAuthorizationContext> exportRule =
        AuthorizationManagers.allOf(
                AuthorityAuthorizationManager
                        .<RequestAuthorizationContext>hasRole("ADMIN"),
                AuthorityAuthorizationManager
                        .<RequestAuthorizationContext>hasAuthority("REPORT_EXPORT")
        );
```

Here **either condition alone is insufficient**. An admin not yet granted export permission is blocked. A user with `REPORT_EXPORT` but lacking `ROLE_ADMIN` is also blocked.

**Do not confuse `hasRole("ADMIN")` with `hasAuthority("ADMIN")`:** `hasRole("ADMIN")` uses the standard role prefix `ROLE_ADMIN`, whereas `hasAuthority("REPORT_EXPORT")` matches the exact string `REPORT_EXPORT`. With `UserDetails`, define authorities explicitly and consistently with your rules.

### Abstaining Elements (No Decision)

In the `AuthorizationManager` API, some implementations can return **no decision** (`null`) from `check(...)`. With `AuthorizationManagers.allOf` in Spring Security 6, an abstaining manager **is not automatically treated as a veto**. If no manager denies, the composition can **grant**, even if all managers abstained.

Therefore for critical policies, **never write a manager that returns null on unrecognized requests expecting `allOf` to fail closed**. Ensure a condition explicitly returns deny if required data is missing or invalid, or design appropriate matchers/scopes.

Defensive fragment example:

```java
// Java fragment, used inside an application's custom manager.
AuthorizationManager<RequestAuthorizationContext> tenantCheck =
        (authentication, context) -> {
            String tenant = context.getRequest().getHeader("X-Tenant");
            if (tenant == null || tenant.isBlank()) {
                return new AuthorizationDecision(false);
            }
            // Must verify tenant against trusted principal/server data;
            // never merely trust a client-sent header value.
            return new AuthorizationDecision(
                    canAccessTenant(authentication.get(), tenant));
        };
```

`canAccessTenant(...)` is a **business method you must implement and back with trusted data sources**; this fragment **is not standalone runnable**. The goal is to illustrate: when tenant is missing return false, **do not return null and accidentally let `allOf` grant**. In real environments, also handle exceptions, null authentication, valid tenant IDs, and server-side ownership checks.

## 4. anyOf: Logical OR of Conditions

`anyOf(A,B,C)` grants immediately when **at least one** condition grants. With managers always returning explicit decisions:

| A | B | `anyOf(A,B)` |
| --- | --- | --- |
| Allow | Allow | Allow |
| Allow | Deny | Allow |
| Deny | Allow | Allow |
| Deny | Deny | Deny |

For example, `/review` for admins **or** auditors:

```java
AuthorizationManager<RequestAuthorizationContext> reviewRule =
        AuthorizationManagers.anyOf(
                AuthorityAuthorizationManager
                        .<RequestAuthorizationContext>hasRole("ADMIN"),
                AuthorityAuthorizationManager
                        .<RequestAuthorizationContext>hasRole("AUDITOR")
        );
```

Someone with only `ROLE_AUDITOR` is still allowed access. Someone with only `ROLE_USER` is denied.

**With abstaining managers:** `anyOf` typically ignores `null` results and only grants when a branch grants. If no branch grants, the composition **denies**. Therefore never treat `null` as `true`, and never assume AND/OR over managers that can return null behaves identically to ordinary three-valued Boolean expressions.

### Use anyOf or hasAnyAuthority?

When you simply need one of several plain authorities:

```java
// Shorter fragment if only checking a list of authorities:
AuthorityAuthorizationManager<RequestAuthorizationContext> simple =
        AuthorityAuthorizationManager.hasAnyAuthority(
                "ROLE_ADMIN", "ROLE_AUDITOR");
```

`hasAnyAuthority` is usually sufficient and readable. `anyOf` is more beneficial when combining **heterogeneous policies**, e.g., admin role **or** resource owner **or** user granted a special business permission.

`anyOf` does not automatically pick which branch goes first by performance or safety. Evaluation order is determined by how you pass the managers; avoid branches with side effects or order dependencies. Both `allOf` and `anyOf` may short-circuit once decided, so **never use them to run mandatory audit side effects every time**.

## 5. Nesting allOf and anyOf to Express Real Policies

Given the report-viewing endpoint:

```text
VIEW = AUTHENTICATED && (REPORT_READ || ROLE_ADMIN)
```

We can write a nested structure:

```java
AuthorizationManager<RequestAuthorizationContext> canRead =
        AuthorizationManagers.anyOf(
                AuthorityAuthorizationManager
                        .<RequestAuthorizationContext>hasAuthority("REPORT_READ"),
                AuthorityAuthorizationManager
                        .<RequestAuthorizationContext>hasRole("ADMIN")
        );

AuthorizationManager<RequestAuthorizationContext> viewRule =
        AuthorizationManagers.allOf(
                AuthenticatedAuthorizationManager
                        .<RequestAuthorizationContext>authenticated(),
                canRead
        );
```

Logical sequence in this example:

1. The user must have an authentication considered authenticated by the framework.
2. The user has `REPORT_READ` **or** `ROLE_ADMIN`.
3. If any required condition denies, `allOf` denies.
4. If the user only has `ROLE_GUEST`, `authenticated()` is true but `canRead` is false -> overall still deny.
5. If anonymous has no valid role/authority, authorization fails; with HTTP Basic, the client typically gets a 401 challenge instead of 403.

An easy trap: writing `anyOf(authenticated(), hasRole("ADMIN"))` lets **every logged-in user** pass the first branch, nullifying the admin constraint in the second branch. That is an **overly broad OR** design flaw. When "logged in and has permission" is required, use `allOf` or a sufficiently strict role/authority rule.

### Nested Policy Diagram

```text
                    allOf
                   /     \
        authenticated    anyOf
                         /    \
                  REPORT_READ  ROLE_ADMIN

Outcomes:
- anonymous                       -> DENY
- authenticated, ROLE_GUEST       -> DENY
- authenticated, REPORT_READ      -> GRANT
- authenticated, ROLE_ADMIN       -> GRANT
- authenticated, both             -> GRANT
```

Nesting conditions expresses policy openly instead of hiding it inside a long lambda. However, if rules depend on **resource ownership** or dynamic permissions from a database, a custom `AuthorizationManager` or server-side permission service is still required; do not reduce all business logic to static role checks.

## 6. From AuthorizationManager to HTTP 200, 401, 403

Typical Servlet flow:

```text
HTTP request
    |
    v
FilterChainProxy -> SecurityFilterChain
    |
    v
Authentication filters
(Basic/form/Bearer... depending on chain)
    |
    v
SecurityContextHolder / current Authentication
    |
    v
AuthorizationFilter
    |
    v
AuthorizationManager<RequestAuthorizationContext>
    |
    +--- allOf / anyOf / nested managers
             |
         +---+----+
         |        |
       GRANT     DENY
         |        |
         v        v
   Controller    AccessDeniedException
                  |
                  v
           ExceptionTranslationFilter
                  |
             +----+-----------+
             |                |
         anonymous?       authenticated?
             |                |
             v                v
       Authentication     AccessDeniedHandler
         EntryPoint        typically 403
         typically 401
         or form 302
```

With **HTTP Basic** as in the runnable example in section 9:

| Scenario | Typical Result | Explanation |
| --- | --- | --- |
| No Basic credentials, protected endpoint | **401** + `WWW-Authenticate` | No valid identity yet |
| Wrong username/password | **401** | Authentication fails before authorization |
| Valid credentials yet fails `allOf`/`anyOf` | **403** | Authenticated properly, yet policy denies |
| Valid credentials and composition grants | **200** (if controller returns 200) | Controller is allowed to run |
| `permitAll()` endpoint without Basic credentials | **200** | No login required |

In form-login web apps, denied anonymous requests may lead to a **302 redirect** to the login page. `AuthorizationManagers.allOf/anyOf` **do not generate HTTP status codes themselves**; responses are produced by the filter chain, entry point, and access-denied handling.

### Authentication Differs from Authorization

`Authentication` supplies `principal`, `authorities`, and authenticated status. Providers verify passwords/tokens. The authorization manager **reads** that info; it never lets clients pick roles via URL/headers and attach them to `Authentication`.

`GrantedAuthority` values like `ROLE_ADMIN` or `REPORT_EXPORT` must come from a trusted source: user store, identity provider, or verified claims mapping. Never let a request body send `roles:["ROLE_ADMIN"]` and use it directly in decisions.

## 7. Issues When Composing Multiple Conditions

### 7.1. Overly Broad Accepted Branch

Business-intent error:

```java
// Dangerous if /admin must require ROLE_ADMIN:
AuthorizationManager<RequestAuthorizationContext> tooBroad =
        AuthorizationManagers.anyOf(
                AuthenticatedAuthorizationManager
                        .<RequestAuthorizationContext>authenticated(),
                AuthorityAuthorizationManager
                        .<RequestAuthorizationContext>hasRole("ADMIN")
        );
```

Because `anyOf` is OR, any ordinary logged-in user passes the `authenticated()` branch. If the requirement is "logged in **and** admin", use `allOf` or `hasRole("ADMIN")` directly.

### 7.2. Impossible Branch

```java
// Allows only users holding BOTH roles.
// If business data defines these roles as mutually exclusive,
// this condition will never grant.
AuthorizationManager<RequestAuthorizationContext> impossible =
        AuthorizationManagers.allOf(
                AuthorityAuthorizationManager
                        .<RequestAuthorizationContext>hasRole("GUEST"),
                AuthorityAuthorizationManager
                        .<RequestAuthorizationContext>hasRole("ADMIN")
        );
```

Note: technically a user **can hold multiple roles**; thus "impossible" applies only when the data model makes two roles mutually exclusive. Do not conclude from this example that Spring Security limits each user to one role by default.

### 7.3. Confusing the ROLE_ Prefix

`hasRole("ADMIN")` checks `ROLE_ADMIN` with the default prefix. `hasAuthority("ADMIN")` checks the exact string `ADMIN`. Do not arbitrarily pass `ROLE_` into `hasRole` expecting `hasAuthority` behavior. If the app customizes the role prefix, inspect the actual policy and test authority mapping.

### 7.4. Returning Null When It Should Deny

If a custom manager cannot determine access because a tenant ID is missing, the database returns no data, or the request is invalid, **do not return null by default** expecting AND to deny. With `allOf`, an abstaining condition can be skipped. Depending on the case, return `new AuthorizationDecision(false)` or let exceptions be handled per an explicit error policy.

Fail-closed illustrative code:

```java
AuthorizationManager<RequestAuthorizationContext> featureCheck =
        (authentication, context) -> {
            boolean featureEnabled = false; // Example closed policy
            return new AuthorizationDecision(featureEnabled);
        };
```

This is a simple fragment illustrating an explicit false result, not a full feature-flag system. If a remote policy service is required, distinguish **policy denial** from **service outage** in audit/monitoring.

### 7.5. Side Effects and Invocation Order

A manager may never be called if:

- `allOf`: an earlier manager already denied.
- `anyOf`: an earlier manager already granted.

Therefore never attach mandatory actions like "always write audit log" solely inside the last manager. Auditing should be handled by a mechanism guaranteeing coverage across allow/deny outcomes by design, rather than hoping every manager branch executes.

### 7.6. Authorization Is Not Object Ownership Checking

`hasRole("USER")` + `REPORT_READ` may suffice for shared group documents, yet does not itself know whether the user may view a **specific report ID**. For "owner or admin" rules, custom managers must rely on **trusted `Authentication`** and **server-side resource ownership**; the client only supplies the report ID, never the conclusion "I am the owner".

The HTTP API layer can use `RequestAuthorizationContext.getRequest()` or `getVariables()` (when the request matcher populates variables) to extract request info; the authorization service must look up true permissions. Avoid using client-sent `X-Role` or `X-Admin: true` as proof.

## 8. Writing Readable and Testable Policies

You do not always need both `allOf` and `anyOf`. Pick the simplest expressive form:

- Single authority: `hasAuthority("REPORT_READ")`.
- Single role: `hasRole("ADMIN")`.
- Any of multiple authorities: `hasAnyAuthority("REPORT_READ", "REPORT_EXPORT")`.
- **AND between two constraint types:** `allOf(hasRole("ADMIN"), hasAuthority("REPORT_EXPORT"))`.
- **OR between two heterogeneous policies:** `anyOf(hasRole("ADMIN"), customOwnerRule)`.
- **Multi-level nesting:** `allOf(authenticated(), anyOf(hasAuthority("REPORT_READ"), hasRole("ADMIN")))`.

Extracting managers into variables with business-meaningful names prevents reviewers from misreading:

```java
AuthorizationManager<RequestAuthorizationContext> reportReadAccess = ...;
AuthorizationManager<RequestAuthorizationContext> exportAccess = ...;
AuthorizationManager<RequestAuthorizationContext> reviewAccess = ...;
```

This is a **naming-illustration fragment**, not runnable source; ellipses must be replaced with real managers. The complete example immediately below uses no placeholders.

### Note When Multiple SecurityFilterChains Exist

`SecurityFilterChain` is chosen by `securityMatcher`, and **only the first matching chain** applies to the request. `requestMatchers` inside `authorizeHttpRequests` selects rules for URLs/methods within the chosen chain.

If you place an API chain after a web fallback chain matching all URLs, the API's `allOf`/`anyOf` rules may **never be invoked**. Before debugging AND/OR logic, verify the request entered the right chain.

## 9. Runnable Project: Java 17 + Spring Boot 3.3.5 + HTTP Basic

We build a simple Spring MVC Servlet app comprising:

| Method/URL | Policy | Response When Permitted |
| --- | --- | --- |
| `GET /public` | `permitAll()` | `public:ok` |
| `GET /reports/view` | `authenticated() AND (REPORT_READ OR ROLE_ADMIN)` | `report:view:<username>` |
| `GET /reports/export` | `ROLE_ADMIN AND REPORT_EXPORT` | `report:export:<username>` |
| `GET /review` | `ROLE_ADMIN OR ROLE_AUDITOR` | `review:<username>` |

We use HTTP Basic with `SessionCreationPolicy.STATELESS` for easy `curl` testing. Using Basic is **only for the example**: the `AuthorizationManager` logic works identically with form login and Bearer tokens given the right authentication mechanism. Production must always use HTTPS and credential protection per system requirements.

Demo accounts (all using password `demo123` **locally only**):

| Username | Authorities | Meaning |
| --- | --- | --- |
| `reader` | `ROLE_USER`, `REPORT_READ` | May view reports, not export/review |
| `auditor` | `ROLE_AUDITOR` | May review, does not automatically have `REPORT_READ` |
| `admin` | `ROLE_ADMIN`, `REPORT_EXPORT` | May view/export/review |
| `adminNoExport` | `ROLE_ADMIN` | May view/review, **not** export |
| `guest` | `ROLE_GUEST` | Logged in yet fails protected rules |

### 9.1. Project Structure

```text
authorization-composition/
├── pom.xml
└── src/main/java/example/authorization/
    ├── AuthorizationApplication.java
    ├── SecurityConfig.java
    └── ReportController.java
```

### 9.2. pom.xml

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>
    <groupId>example</groupId>
    <artifactId>authorization-composition</artifactId>
    <version>1.0.0</version>
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
            <artifactId>spring-boot-starter-security</artifactId>
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

### 9.3. AuthorizationApplication.java

```java
package example.authorization;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class AuthorizationApplication {
    public static void main(String[] args) {
        SpringApplication.run(AuthorizationApplication.class, args);
    }
}
```

### 9.4. SecurityConfig.java: Combining AND/OR

```java
package example.authorization;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.authorization.AuthorizationManager;
import org.springframework.security.authorization.AuthorizationManagers;
import org.springframework.security.authorization.AuthorityAuthorizationManager;
import org.springframework.security.authorization.AuthenticatedAuthorizationManager;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.access.intercept.RequestAuthorizationContext;
import org.springframework.security.web.savedrequest.NullRequestCache;

@Configuration
@EnableWebSecurity
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        UserDetails reader = User.withUsername("reader")
                .password(encoder.encode("demo123"))
                .authorities("ROLE_USER", "REPORT_READ")
                .build();

        UserDetails auditor = User.withUsername("auditor")
                .password(encoder.encode("demo123"))
                .authorities("ROLE_AUDITOR")
                .build();

        UserDetails admin = User.withUsername("admin")
                .password(encoder.encode("demo123"))
                .authorities("ROLE_ADMIN", "REPORT_EXPORT")
                .build();

        UserDetails adminNoExport = User.withUsername("adminNoExport")
                .password(encoder.encode("demo123"))
                .authorities("ROLE_ADMIN")
                .build();

        UserDetails guest = User.withUsername("guest")
                .password(encoder.encode("demo123"))
                .authorities("ROLE_GUEST")
                .build();

        return new InMemoryUserDetailsManager(
                reader, auditor, admin, adminNoExport, guest);
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {

        // /reports/view = authenticated AND
        //                 (REPORT_READ OR ROLE_ADMIN)
        AuthorizationManager<RequestAuthorizationContext> readOrAdmin =
                AuthorizationManagers.anyOf(
                        AuthorityAuthorizationManager
                                .<RequestAuthorizationContext>hasAuthority(
                                        "REPORT_READ"),
                        AuthorityAuthorizationManager
                                .<RequestAuthorizationContext>hasRole("ADMIN")
                );

        AuthorizationManager<RequestAuthorizationContext> viewRule =
                AuthorizationManagers.allOf(
                        AuthenticatedAuthorizationManager
                                .<RequestAuthorizationContext>authenticated(),
                        readOrAdmin
                );

        // /reports/export = ROLE_ADMIN AND REPORT_EXPORT
        AuthorizationManager<RequestAuthorizationContext> exportRule =
                AuthorizationManagers.allOf(
                        AuthorityAuthorizationManager
                                .<RequestAuthorizationContext>hasRole("ADMIN"),
                        AuthorityAuthorizationManager
                                .<RequestAuthorizationContext>hasAuthority(
                                        "REPORT_EXPORT")
                );

        // /review = ROLE_ADMIN OR ROLE_AUDITOR
        AuthorizationManager<RequestAuthorizationContext> reviewRule =
                AuthorizationManagers.anyOf(
                        AuthorityAuthorizationManager
                                .<RequestAuthorizationContext>hasRole("ADMIN"),
                        AuthorityAuthorizationManager
                                .<RequestAuthorizationContext>hasRole("AUDITOR")
                );

        http.authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/public").permitAll()
                .requestMatchers(HttpMethod.GET, "/reports/view")
                    .access(viewRule)
                .requestMatchers(HttpMethod.GET, "/reports/export")
                    .access(exportRule)
                .requestMatchers(HttpMethod.GET, "/review")
                    .access(reviewRule)
                .anyRequest().denyAll()
        );

        // Enable Basic to focus on testing authorization with curl.
        http.httpBasic(Customizer.withDefaults());

        // Do not use HTTP sessions for identity across demo API requests.
        http.sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS));
        http.requestCache(cache -> cache
                .requestCache(new NullRequestCache()));

        // Do not enable form login for API demo; default CSRF is retained.
        http.formLogin(form -> form.disable());
        return http.build();
    }
}
```

Analyzing the composition:

1. **`readOrAdmin`** is `anyOf`: someone with `REPORT_READ` **or** `ROLE_ADMIN` passes this step.
2. **`viewRule`** is `allOf`: must have valid authentication **and** pass `readOrAdmin`.
3. **`exportRule`** is `allOf`: an admin without `REPORT_EXPORT` is still denied.
4. **`reviewRule`** is `anyOf`: an auditor can review despite lacking `REPORT_READ`.
5. `.access(viewRule)` binds `AuthorizationManager<RequestAuthorizationContext>` to the corresponding HTTP Servlet rule.
6. `anyRequest().denyAll()` ensures URLs or methods without rules are not unintentionally opened.
7. `httpBasic()` + `STATELESS` authenticates each request independently. Role/authority mechanics do not depend on HTTP Basic, though the example avoids needing HTML login/session for testing.
8. CSRF **is not disabled**: the demo endpoints are GET-only. If adding POST/PUT/PATCH/DELETE, design CSRF per client/threat model rather than disabling protection globally just for testing.
9. `hasRole` uses the default role prefix; user data is explicitly declared with `.authorities("ROLE_ADMIN", ...)`, avoiding mixing up `.roles()` and `.authorities()`.
10. The demo hardcodes passwords strictly for local study. Production uses a user store/IdP, password hashing, and HTTPS; never keep real passwords in source or shell history.

### 9.5. ReportController.java

```java
package example.authorization;

import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ReportController {

    @GetMapping("/public")
    public String publicPage() {
        return "public:ok";
    }

    @GetMapping("/reports/view")
    public String view(Authentication auth) {
        return "report:view:" + auth.getName();
    }

    @GetMapping("/reports/export")
    public String export(Authentication auth) {
        return "report:export:" + auth.getName();
    }

    @GetMapping("/review")
    public String review(Authentication auth) {
        return "review:" + auth.getName();
    }
}
```

These controller methods do not decide permissions themselves. `AuthorizationFilter` applies `AuthorizationManagers.allOf/anyOf` **before the request reaches the controller**. The controller only sees permitted requests and the corresponding `Authentication`.

### 9.6. Running the Application

In the directory containing `pom.xml`, JDK 17+ and Maven are required:

```bash
mvn spring-boot:run
```

By default Spring Boot listens at `http://localhost:8080`. The `curl` commands below are **for local use only**; real environments require HTTPS so HTTP Basic credentials are not exposed.

## 10. HTTP Test Cases for AND/OR

### 10.1. Anonymous Accessing Public Endpoint

```bash
curl -s http://localhost:8080/public
```

Expected body:

```text
public:ok
```

Because of `permitAll()`, the public endpoint requires no authorities.

### 10.2. Anonymous Accessing Protected Endpoint

```bash
curl -s -o /dev/null -w '%{http_code}\n' \
  http://localhost:8080/reports/view
```

Expected result:

```text
401
```

An anonymous call without Basic credentials is denied by policy and challenged by the Basic authentication entry point. This is missing authentication, not an authenticated user missing `REPORT_READ`.

### 10.3. Reader Views Report via REPORT_READ

```bash
curl -s --user reader:demo123 \
  http://localhost:8080/reports/view
```

Expected body:

```text
report:view:reader
```

`authenticated()` grants, `hasAuthority("REPORT_READ")` grants -> `anyOf` grants -> `allOf` grants.

### 10.4. Admin Views Report Despite Lacking REPORT_READ

```bash
curl -s --user admin:demo123 \
  http://localhost:8080/reports/view
```

Expected body:

```text
report:view:admin
```

Admin was not granted `REPORT_READ` yet holds `ROLE_ADMIN`; the second OR branch in `anyOf` grants, so the overall rule grants.

### 10.5. Auditor with Only ROLE_AUDITOR Cannot View Reports

```bash
curl -s -o /dev/null -w '%{http_code}\n' \
  --user auditor:demo123 http://localhost:8080/reports/view
```

Expected:

```text
403
```

`auditor` authenticated, yet lacks **both** `REPORT_READ` and `ROLE_ADMIN`. The OR composition denies, leading the AND composition to deny. This is an authorization failure, not a password error.

### 10.6. Auditor Reviews via OR Branch

```bash
curl -s --user auditor:demo123 \
  http://localhost:8080/review
```

Expected body:

```text
review:auditor
```

`anyOf(ROLE_ADMIN,ROLE_AUDITOR)` succeeds via the auditor branch.

### 10.7. Reader Lacks Role to Review

```bash
curl -s -o /dev/null -w '%{http_code}\n' \
  --user reader:demo123 http://localhost:8080/review
```

Expected:

```text
403
```

`reader` has `REPORT_READ` yet belongs to neither admin nor auditor; report-reading permission does not automatically turn into review permission.

### 10.8. Admin Must Meet Both Conditions to Export

```bash
curl -s --user admin:demo123 \
  http://localhost:8080/reports/export
```

Body:

```text
report:export:admin
```

Both `ROLE_ADMIN` and `REPORT_EXPORT` succeed so `allOf` grants.

### 10.9. Admin Missing REPORT_EXPORT Is Denied

```bash
curl -s -o /dev/null -w '%{http_code}\n' \
  --user adminNoExport:demo123 \
  http://localhost:8080/reports/export
```

Expected:

```text
403
```

This case proves `allOf` does not mean "only need role ADMIN". One missing condition causes the whole policy to deny.

### 10.10. Logged-In Guest Is Still Blocked

```bash
curl -s -o /dev/null -w '%{http_code}\n' \
  --user guest:demo123 http://localhost:8080/reports/view
```

Expected:

```text
403
```

`guest` authenticated, yet holds neither condition to view reports. If mistakenly written as `anyOf(authenticated(), ...)`, guest would gain access — a serious security regression.

### Results Comparison Table

| User and Endpoint | `authenticated` | Matching Role/Authority | Expected Result |
| --- | --- | --- | --- |
| anonymous `GET /public` | No | Not needed | 200 |
| anonymous `GET /reports/view` | No | No | 401 |
| reader `GET /reports/view` | Yes | `REPORT_READ` | 200 |
| admin `GET /reports/view` | Yes | `ROLE_ADMIN` | 200 |
| auditor `GET /reports/view` | Yes | Insufficient | 403 |
| auditor `GET /review` | Yes | `ROLE_AUDITOR` | 200 |
| reader `GET /review` | Yes | Insufficient | 403 |
| admin `GET /reports/export` | Yes | Both role and permission | 200 |
| adminNoExport `GET /reports/export` | Yes | Missing export permission | 403 |
| guest `GET /reports/view` | Yes | Insufficient | 403 |

**Testing note:** these are **expected results from the sample config**, not an execution transcript on the learner's machine. Test end-to-end when integrating other authentication providers, proxies, filter chains, or method security.

## 11. Testing with Spring Security Test and MockMvc

The `curl` commands are integration smoke tests. For long-term code development, write **automated tests** checking AND/OR branches and role/permission boundaries.

Add test dependencies to `pom.xml` if you want to extend the project:

```xml
<!-- Add to dependencies when writing tests -->
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
</dependency>
<dependency>
    <groupId>org.springframework.security</groupId>
    <artifactId>spring-security-test</artifactId>
    <scope>test</scope>
</dependency>
```

Example **JUnit 5/MockMvc fragment** once those dependencies are added:

```java
package example.authorization;

import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class AuthorizationRulesTest {

    @Autowired
    MockMvc mvc;

    @Test
    void readerCanViewButCannotExport() throws Exception {
        mvc.perform(get("/reports/view")
                .with(user("reader").authorities(
                        new org.springframework.security.core.authority
                                .SimpleGrantedAuthority("REPORT_READ"))))
                .andExpect(status().isOk());

        mvc.perform(get("/reports/export")
                .with(user("reader").authorities(
                        new org.springframework.security.core.authority
                                .SimpleGrantedAuthority("REPORT_READ"))))
                .andExpect(status().isForbidden());
    }

    @Test
    void adminWithoutExportAuthorityCannotExport() throws Exception {
        mvc.perform(get("/reports/export")
                .with(user("adminNoExport").roles("ADMIN")))
                .andExpect(status().isForbidden());
    }

    @Test
    void auditorCanReview() throws Exception {
        mvc.perform(get("/review").with(user("auditor").roles("AUDITOR")))
                .andExpect(status().isOk());
    }
}
```

These tests illustrate **how to inject an `Authentication` into MockMvc's security context**; they **do not test HTTP Basic passwords** or the real user store. To test end-to-end authentication, test with HTTP Basic credentials via `spring-security-test`'s `httpBasic(...)` or a real client; to focus on authorization, `user(...)` cleanly isolates grant/deny conditions.

In test code, if a username does not exist in `UserDetailsService` yet MockMvc uses `user(...)`, authorization rules still evaluate against the mocked `Authentication`; that is a **trait of the test setup**, not a real user logged in through the provider.

## 12. Combining Custom AuthorizationManagers When Static Roles Are Not Enough

Some business rules must check **ownership** or **resource state**:

```text
CAN_EDIT = authenticated() AND
           (ROLE_ADMIN OR (IS_OWNER AND DOCUMENT_NOT_ARCHIVED))
```

Here `IS_OWNER` and `DOCUMENT_NOT_ARCHIVED` must be determined from server data, usually by a service/repository, not from a client-supplied flag.

One possible design:

```java
// Fragment: ownershipRule and documentStateRule must be
// AuthorizationManager<RequestAuthorizationContext> instances implemented by the app.
AuthorizationManager<RequestAuthorizationContext> ownerCanEdit =
        AuthorizationManagers.allOf(
                ownershipRule,
                documentStateRule
        );

AuthorizationManager<RequestAuthorizationContext> editRule =
        AuthorizationManagers.allOf(
                AuthenticatedAuthorizationManager
                        .<RequestAuthorizationContext>authenticated(),
                AuthorizationManagers.anyOf(
                        AuthorityAuthorizationManager
                                .<RequestAuthorizationContext>hasRole("ADMIN"),
                        ownerCanEdit
                )
        );
```

**Non-standalone fragment** because `ownershipRule` and `documentStateRule` are business-specific. Nesting `allOf` and `anyOf` does not replace server-side resource ownership checks. If the path contains `/documents/{id}`, a custom manager can read the ID from the request and query a trusted repository to learn owner/archived status; never trust `X-Owner: true`.

### Avoiding TOCTOU Between Permission Check and Action Execution

Resource ownership/state can change between the authorization filter check and the controller's database update. For sensitive writes, beyond HTTP authorization, the service/domain layer may need to re-check inside a transaction, use optimistic locking, or apply conditional updates ensuring consistency. **An allow decision before the controller does not eliminate all race conditions.**

## 13. Security, Performance, and Maintainability

### Fail Closed and Exceptions

For mandatory rules, return an explicit deny when data is insufficient. If the authorization service fails, distinguish **infrastructure failures** from policy denials, and never accidentally return `grant` to "keep the system running". If a custom manager throws an exception, the response may be a server error or handled by filter/exception handling depending on design; do not assume every exception becomes 403.

### Short-Circuit Evaluation

`allOf` typically stops on deny; `anyOf` typically stops on grant. This avoids running unnecessary branches, yet also means **manager ordering affects how much work runs**. Do not rely on all branches executing to perform auditing, billing, or business-state updates. An `AuthorizationManager` should **read data and decide**, without causing side effects.

### Optimizing Permission Checks

If multiple branches call a repository or remote policy service, consider request-scoped caching, avoid N+1 calls, and load only fields needed for checking. Never cache permissions across changes to account status/roles/tenant membership without an invalidation policy.

### Safe Logging

Log the rule ID, safely sanitized resource ID, grant/deny outcome, and correlation ID. Never log raw passwords, access tokens, session cookies, or full `Authentication` objects containing credentials. Denial/allow auditing should cover short-circuited branches as well.

### Testing and Code Review

Ensure sufficient tests for:

- **Positive:** each OR branch allows the users it should allow.
- **Negative:** missing any condition in AND must be denied.
- **Anonymous:** unauthenticated callers must not accidentally be granted by `anyOf(authenticated(),...)`.
- **Role prefix:** `ROLE_ADMIN` differs from `ADMIN`, `hasRole` differs from `hasAuthority`.
- **Abstain/null:** a custom manager returning null can let `allOf` allow unexpectedly.
- **Method/URL:** HTTP methods other than GET must not open automatically without rules.
- **Ownership:** never trust client-claimed data; check the specific target resource.
- **Multiple chains:** requests must enter the intended `SecurityFilterChain`.

## 14. Quick Debugging Table

| Symptom | Possible Cause | How to Locate the Bug |
| --- | --- | --- |
| User with `ADMIN` role gets 403 on export | `allOf` also requires `REPORT_EXPORT` | Inspect exact `Authentication` authorities and both branches |
| Every logged-in user can view admin endpoint | Used `anyOf(authenticated(), hasRole("ADMIN"))` | Switch structure to `allOf` or an appropriate role rule |
| Auditor gets 403 on review | `ROLE_AUDITOR` absent from authorities or wrong prefix | Compare `hasRole("AUDITOR")` against actual `ROLE_AUDITOR` |
| Anonymous gets 401 instead of 403 | HTTP Basic entry point triggered by missing auth | Normal behavior for anonymous callers |
| User logs in successfully yet gets 403 | Authentication succeeded, authorization denied | Do not edit password encoder; inspect policy |
| `allOf` grants when custom manager abstains | Manager returned null instead of false | Return explicit deny when data is missing or fix policy structure |
| One manager branch never runs | Earlier branch already denied in AND or granted in OR | Do not rely on that branch for side effects/audits |
| API returns 302 login instead of 401 | Web chain/form entry point handled API request | Inspect `securityMatcher`, `@Order`, entry point |
| `access(...)` fails to compile due to generics | Manager type does not match `RequestAuthorizationContext` | Check `AuthorizationManager<RequestAuthorizationContext>` generic type |
| Specific resource rule is bypassed | Only checked role, not real ownership | Add server-side custom manager/service |
| GET blocked with 403 for unclear reason | `anyRequest().denyAll()`, URL/method mismatch, or missing authority | Inspect rule order, path, HTTP method |
| Role changed yet permissions stay stale | Cache/session context holds old authorities | Design proper refresh/re-auth/invalidation |

Step-by-step verification process:

1. Verify **the request entered the right filter chain**.
2. Verify **`Authentication` was created from valid credentials**, not client-supplied authorities.
3. Verify actual authorities and `ROLE_` prefixes.
4. Verify `allOf` vs. `anyOf` matches **AND/OR** requirements.
5. For custom managers, verify **null/abstain** cases and exceptions.
6. Verify rules match the right URL/method; `requestMatchers` are evaluated in declaration order.
7. Test HTTP statuses 200/401/403 and controller response bodies.
8. Re-test after changing roles, resource owners, or resource state.

In development, you can add:

```properties
logging.level.org.springframework.security=DEBUG
```

Never enable raw credential logging in production or write sensitive permissions/PII into uncontrolled logs.

## 15. Self-Check

1. **Is `allOf` AND or OR?** AND: no manager may veto; with explicit Boolean managers, all must grant.
2. **Is `anyOf` AND or OR?** OR: only one manager needs to grant.
3. **Does `anyOf(authenticated(), hasRole("ADMIN"))` protect an admin endpoint?** No: any ordinary logged-in user satisfies the first branch.
4. **Can an admin with the role but without `REPORT_EXPORT` export when using `allOf`?** No.
5. **Can an auditor without `REPORT_READ` but with `ROLE_AUDITOR` review?** Yes, under the example's `anyOf(ADMIN,AUDITOR)`.
6. **What HTTP status does an authenticated user lacking permission get with Basic?** Typically 403.
7. **What does an anonymous caller hitting a protected endpoint get with Basic?** Typically 401 + challenge.
8. **Are `hasRole("ADMIN")` and `hasAuthority("ADMIN")` the same?** No, the default role prefix differs.
9. **If a custom manager's `check(...)` returns null, is `allOf` guaranteed to deny?** No, that is a fail-open trap to avoid.
10. **Should you run side effects inside every manager?** No, because combinators can short-circuit evaluation.
11. **Is `RequestAuthorizationContext` for HTTP Servlet or method security?** HTTP Servlet; method security uses a different context type.
12. **Where should resource ownership be checked?** Against trusted server data, in a custom manager and especially in the service/domain layer for sensitive actions.

## 16. Production Adoption Checklist

- [ ] Write business rules as clear AND/OR expressions before coding.
- [ ] Use `AuthorizationManagers.allOf` for conditions that are **all mandatory**.
- [ ] Use `AuthorizationManagers.anyOf` for **valid alternative** branches.
- [ ] Avoid overly broad OR branches like `authenticated()` when a role/permission is actually required.
- [ ] Declare managers with the exact `AuthorizationManager<RequestAuthorizationContext>` type for Servlet HTTP.
- [ ] Use `hasRole`, `hasAuthority`, and role prefixes consistently with trusted authority sources.
- [ ] For custom managers, explicitly define grant/deny/null behavior and handle infrastructure errors safely.
- [ ] Do not use combinators for side effects that must always run; test short-circuiting.
- [ ] Verify security chains, method/path matchers, and `denyAll()` fallbacks.
- [ ] Check resource ownership and tenant boundaries server-side when static roles are not enough.
- [ ] Test positive and negative user/role/authority combinations, especially cases missing one branch of an AND.
- [ ] Test anonymous vs. authenticated to distinguish 401/403.
- [ ] Configure HTTPS, session/token lifecycle, and auditing per architecture; authorization rules do not replace those layers.

**Conclusion:** `AuthorizationManagers.allOf` and `AuthorizationManagers.anyOf` let you express **structured, testable HTTP authorization policies** in Spring Security Servlet. Use `allOf` when **every requirement must hold**; use `anyOf` when **one of several valid branches suffices**. Stay alert for **overly broad ORs**, wrong `ROLE_` prefixes, custom managers **abstaining/returning null**, and assuming every branch always runs. When access depends on resources/tenants, manager composition must pair with trusted server-side data checks.