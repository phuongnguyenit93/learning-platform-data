# hasRole, hasAuthority, and the ROLE_ Prefix in HTTP Authorization

> **Topic:** Spring Security – reactive  
> **Context:** HTTP Authorization with Spring WebFlux  
> **Focus:** Understanding how `hasRole` and `hasAuthority` compare `GrantedAuthority`, when Spring Security adds `ROLE_`, how to build a properly ordered `SecurityWebFilterChain`, and how to test with `WebTestClient` using real user accounts.

## 1. Why Can the Same User Pass hasRole Yet Fail hasAuthority?

Consider two endpoint rules in Spring Security WebFlux:

```java
.pathMatchers("/api/admin").hasRole("ADMIN")
.pathMatchers("/api/raw-admin").hasAuthority("ADMIN")
```

They are **not equivalent** when the user's authority list contains `ROLE_ADMIN` but not `ADMIN`.

- `hasRole("ADMIN")` by default convention looks for an authority named **`ROLE_ADMIN`**.
- `hasAuthority("ADMIN")` requires the exact authority **`ADMIN`**, **without adding** `ROLE_`.
- `hasAuthority("ROLE_ADMIN")` requires the exact authority **`ROLE_ADMIN`**, so under the default prefix convention it matches the same condition as `hasRole("ADMIN")`.
- `hasRole("ROLE_ADMIN")` is an incorrect call per the standard role API: the role argument is already prefixed; do not add the prefix twice.
- A user who **succeeded at authentication** but lacks the required authority can still receive **403 Forbidden**. Missing credentials on a protected endpoint usually receive **401 Unauthorized**.

The core takeaway is: **a role is a naming convention on an authority string, not a completely separate type of `GrantedAuthority`**. When predicting outcomes, inspect the exact two strings: the **granted** authority and the **required** authority.

### Learning Objectives

After this lesson, you can:

1. Explain the relationship between `Authentication`, `GrantedAuthority`, roles, and fine-grained permissions.
2. Predict the outcome of `hasRole`, `hasAnyRole`, `hasAuthority`, and `hasAnyAuthority` for given granted strings.
3. Correctly use `User.withUsername(...).roles(...)` and `.authorities(...)`, avoiding duplicate `ROLE_` prefixes or overwriting authority sets.
4. Write HTTP authorization using `ServerHttpSecurity.authorizeExchange(...)` and `SecurityWebFilterChain`, distinct from Servlet `HttpSecurity`.
5. Understand the impact of matcher order, prefixes, case sensitivity, and authority mapping from JWT/identity providers.
6. Write a Java 17+ WebFlux application and test authorized/unauthorized cases with real HTTP Basic credentials.
7. Distinguish HTTP authorization from reactive method security, avoiding configuration mismatches between the two layers.

## 2. Distinguishing Authentication, GrantedAuthority, Role, and Permission

In Spring Security, caller information typically resides in an `Authentication` object:

```java
// Illustrative signature: this snippet is not a standalone Java file.
Authentication authentication = ...;
String username = authentication.getName();
Collection<? extends GrantedAuthority> granted =
    authentication.getAuthorities();
```

- `Authentication`: represents the principal's authentication state; holds a name, credentials (possibly erased), authorities, and an authentication flag.
- `GrantedAuthority`: interface describing a permission granted to the principal. For example, `SimpleGrantedAuthority("ROLE_ADMIN")` has `getAuthority()` returning the string `ROLE_ADMIN`.
- **Role:** usually a group/functional-level authority **named using the `ROLE_` convention**, such as `ROLE_ADMIN` or `ROLE_READER`.
- **Specific permission/authority:** also represented as a `GrantedAuthority`, such as `report:read`, `order:approve`, or `SCOPE_reports.read`.
- **Principal:** the user or entity being authenticated. A JWT client, Basic auth user, session login, or service identity can all be converted into an `Authentication`; the framework does not guess roles from the account name.

Example authority list:

```text
Authentication name: alice
Authorities:
  ROLE_READER
  report:read
  SCOPE_reports.read
```

From that list:

| HTTP Condition | Authority to Match | Result |
| --- | --- | --- |
| `hasRole("READER")` | `ROLE_READER` | True |
| `hasRole("ADMIN")` | `ROLE_ADMIN` | False |
| `hasAuthority("ROLE_READER")` | `ROLE_READER` | True |
| `hasAuthority("READER")` | `READER` | False |
| `hasAuthority("report:read")` | `report:read` | True |
| `hasAuthority("SCOPE_reports.read")` | `SCOPE_reports.read` | True |
| `hasAuthority("reports.read")` | `reports.read` | False |
| `hasAnyRole("ADMIN", "READER")` | `ROLE_ADMIN` **or** `ROLE_READER` | True |

**Authority name matching is string matching** in this standard setup. `ADMIN` differs from `ROLE_ADMIN`, `report:read` differs from `REPORT:READ`, and `SCOPE_reports.read` differs from `reports.read`. There is no automatic conversion across every naming convention.

### 2.1. "Logged In" Does Not Mean "Authorized"

In HTTP Basic, form login, or JWT, the authentication manager may determine that the user is valid. Afterwards, **authorization** evaluates the endpoint policy. User `reader` with `ROLE_READER` but without `ROLE_ADMIN` will log in successfully yet still receive 403 on an admin endpoint.

```text
Request
  |
  v
Authentication (Basic / session / JWT)
  |
  +-- No valid credentials ------------------> 401 / challenge or login flow
  |
  +-- Authentication succeeds
          |
          v
   AuthorizationWebFilter
          |
          +-- hasRole / hasAuthority matches -> handler/controller
          |
          +-- Insufficient permissions ---------> AccessDeniedException
                                                    |
                                                    v
                                             usually 403 Forbidden
```

This is a simplified diagram. Spring Security has many different filters, handlers, and entry points; the exact response depends on the authentication mechanism, CSRF configuration, and principal state. **Do not use 403 to conclude a wrong password** or **use 401 to conclude a missing role**.

## 3. What Does hasRole("ADMIN") Actually Check?

In the default Spring Security WebFlux configuration, `hasRole("ADMIN")` is a convenience equivalent to requiring the authority `ROLE_ADMIN`.

```java
// Snippet inside authorizeExchange(...):
.pathMatchers("/admin").hasRole("ADMIN")
```

The system checks whether `Authentication.getAuthorities()` contains `ROLE_ADMIN`. There is no need—and you should not—write `.hasRole("ROLE_ADMIN")`. In the standard role manager API, an argument already containing `ROLE_` may be rejected with `IllegalArgumentException` to prevent prefix mistakes.

You can write the equivalent condition as an authority **in a configuration using the default prefix**:

```java
.pathMatchers("/admin").hasAuthority("ROLE_ADMIN")
```

However, **do not claim every `hasRole` configuration variant across every layer is fixed this way**. There are ways to change the prefix convention in expression/method security systems; furthermore, HTTP rules, method rules, and JWT converters may use different configuration mechanisms. Section 12 clarifies this boundary.

### 3.1. hasAnyRole Is OR, Not AND

```java
.pathMatchers("/api/manage").hasAnyRole("ADMIN", "EDITOR")
```

By default, this requires **at least one** of `ROLE_ADMIN` or `ROLE_EDITOR`. It **does not require both**. Do not write two rules for the same path expecting them to automatically form an AND; if you need compound conditions, design a `ReactiveAuthorizationManager` or perform deeper checks in the business layer.

### 3.2. Roles Have No Default Hierarchy

`ROLE_ADMIN` **does not automatically** imply `ROLE_READER` just because the word "ADMIN" sounds higher-level. If you want `admin` to also access reader endpoints, you can:

- Grant **both** authorities to `admin`;
- Use `hasAnyRole("ADMIN", "READER")` on the appropriate endpoints;
- Design a **role hierarchy** supported by Spring Security and configured properly at the authorization layer;
- Use independent business permissions like `report:read` to avoid over-coupling to role names.

Do not assume a role hierarchy if none is configured. When a user gets 403 despite being called "admin" in the database, inspect the actual `GrantedAuthority` list after authentication.

## 4. What Does hasAuthority("...") Actually Check?

`hasAuthority` requires the **exact authority name**, without automatically adding `ROLE_` or `SCOPE_`.

```java
.pathMatchers("/api/report").hasAuthority("report:read")
.pathMatchers("/api/scoped").hasAuthority("SCOPE_reports.read")
.pathMatchers("/api/raw-admin").hasAuthority("ADMIN")
```

These three rules require three **different** strings:

```text
report:read
SCOPE_reports.read
ADMIN
```

Therefore:

- `ROLE_ADMIN` does not pass `hasAuthority("ADMIN")`.
- `ADMIN` does not pass `hasAuthority("ROLE_ADMIN")`.
- `SCOPE_reports.read` does not pass `hasAuthority("report:read")`.
- `report:read` does not pass `hasAuthority("SCOPE_reports.read")`.

If a user has multiple authorities, each rule only checks whether **its required authority is present in the granted set**.

### 4.1. hasAnyAuthority Is Exact-Name OR

```java
.pathMatchers("/api/view")
.hasAnyAuthority("report:read", "report:admin")
```

The condition passes if at least one of `report:read` or `report:admin` is present, not because `report:admin` automatically implies `report:read`. A system might establish a convention that every admin must hold both permissions, but that is a **granting policy**, not the default comparison behavior of `hasAuthority`.

### 4.2. Should You Use Role or Authority?

| Use Case | Usually Clearer Expression | Notes |
| --- | --- | --- |
| Admin page for the `ADMIN` group | `hasRole("ADMIN")` | `ROLE_ADMIN` convention |
| Reports for the `READER` group | `hasRole("READER")` | `ROLE_READER` convention |
| Permission to read reports regardless of group | `hasAuthority("report:read")` | Specific permission |
| Default OAuth2/JWT scope | `hasAuthority("SCOPE_reports.read")` | Depends on scope mapping mechanism |
| Partner directly issuing string `ADMIN` | `hasAuthority("ADMIN")` | Do not assume it became `ROLE_ADMIN` |
| User allowed if ADMIN or EDITOR | `hasAnyRole("ADMIN", "EDITOR")` | OR |
| Endpoint requiring one of two scopes | `hasAnyAuthority("SCOPE_a", "SCOPE_b")` | OR |

There is no rule that every fine-grained permission must use the `resource:action` format: that is a design convention. In large APIs, prefer standardizing naming conventions to avoid an undocumented mix of `ROLE_`/`SCOPE_`/`ADMIN`.

## 5. User.roles(...) and User.authorities(...): Origin of the Prefix

When building `UserDetails` with `org.springframework.security.core.userdetails.User`:

```java
UserDetails admin = User.withUsername("admin")
    .password(passwordHash)
    .roles("ADMIN")
    .build();
```

The `.roles("ADMIN")` method creates the authority **`ROLE_ADMIN`**. In terms of authority name, it is equivalent to:

```java
UserDetails admin = User.withUsername("admin")
    .password(passwordHash)
    .authorities("ROLE_ADMIN")
    .build();
```

Conversely:

```java
UserDetails raw = User.withUsername("raw")
    .password(passwordHash)
    .authorities("ADMIN")
    .build();
```

User `raw` has an authority named **`ADMIN`**, without `ROLE_ADMIN`.

### 5.1. Common Mistakes in Builder Calls

| Builder Call | Resulting Authority | Remarks |
| --- | --- | --- |
| `.roles("ADMIN")` | `ROLE_ADMIN` | Correct, follows role convention |
| `.roles("USER", "ADMIN")` | `ROLE_USER`, `ROLE_ADMIN` | Correct |
| `.authorities("ROLE_ADMIN")` | `ROLE_ADMIN` | Correct, sets authority directly |
| `.authorities("ADMIN")` | `ADMIN` | Valid syntax, **not** the same as `ROLE_ADMIN` |
| `.authorities("report:read")` | `report:read` | Correct, specific permission |
| `.roles("ROLE_ADMIN")` | Does not produce expected result | **Wrong:** `roles` already adds the prefix; standard API rejects prefixed roles |
| Calling `.roles(...)` then `.authorities(...)` | Does not guarantee accumulation | May **overwrite** the authority list in the builder |

If a user needs **both roles and permissions**, specify **a single final authority set**, for example:

```java
UserDetails reader = User.withUsername("reader")
    .password(passwordHash)
    .authorities("ROLE_READER", "report:read")
    .build();
```

This avoids assuming that chaining `.roles("READER").authorities("report:read")` appends the permission to the initial role list. With real providers (DB/LDAP/JWT/OIDC) that do not use `User.UserBuilder`, mapping is usually done by a dedicated `Authentication` converter.

### 5.2. A Plain Java 17 Helper to Visualize Authority Strings

The class below **does not run Spring Security and does not replace real authorization checks**; it merely simulates authority name lookup so you can verify the difference between `ROLE_ADMIN` and `ADMIN` yourself.

Create `RolePrefixDemo.java`:

```java
import java.util.Set;

public final class RolePrefixDemo {

    public static void main(String[] args) {
        Set<String> granted = Set.of("ROLE_ADMIN", "report:read");

        System.out.println("hasRole(ADMIN)="
            + granted.contains("ROLE_" + "ADMIN"));
        System.out.println("hasAuthority(ADMIN)="
            + granted.contains("ADMIN"));
        System.out.println("hasAuthority(ROLE_ADMIN)="
            + granted.contains("ROLE_ADMIN"));
        System.out.println("hasAuthority(report:read)="
            + granted.contains("report:read"));
        System.out.println("hasRole(READER)="
            + granted.contains("ROLE_" + "READER"));
    }
}
```

Run with Java 17+:

```bash
javac RolePrefixDemo.java
java RolePrefixDemo
```

**Exact stdout:**

```text
hasRole(ADMIN)=true
hasAuthority(ADMIN)=false
hasAuthority(ROLE_ADMIN)=true
hasAuthority(report:read)=true
hasRole(READER)=false
```

This proves a name-matching operation, **not that any `UserDetails` passed authentication**. In a real application, Spring Security also checks authentication status, request matching, security chains, role hierarchy (if any), and authorization managers.

## 6. Reactive HTTP Authorization: ServerHttpSecurity, Not HttpSecurity

In Spring WebFlux, HTTP security configuration uses:

```java
SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
    return http
        .authorizeExchange(exchanges -> exchanges
            .pathMatchers("/api/public").permitAll()
            .pathMatchers("/api/admin").hasRole("ADMIN")
            .pathMatchers("/api/report").hasAuthority("report:read")
            .anyExchange().denyAll()
        )
        .build();
}
```

This is an **illustrative excerpt**, omitting `@Configuration`, authentication mechanisms, and imports; a complete runnable example is in Section 9.

**Key differences:**

| Reactive WebFlux | Servlet |
| --- | --- |
| `ServerHttpSecurity` | `HttpSecurity` |
| `SecurityWebFilterChain` | `SecurityFilterChain` |
| `authorizeExchange(...)` | `authorizeHttpRequests(...)` |
| `pathMatchers(...)` | `requestMatchers(...)` |
| `AuthorizationWebFilter` | Servlet filter chain |
| `ReactiveSecurityContextHolder` | Usually thread-bound `SecurityContextHolder` |

Do not copy `HttpSecurity.authorizeHttpRequests(...)` snippets from Servlet documentation into a WebFlux project expecting them to behave as reactive code. Also, do not conclude that `@EnableWebFluxSecurity` alone creates roles/authorities; authorities come from authentication providers or converters.

### 6.1. Matcher Order Changes the Outcome

Rules are declared in order. When multiple matchers could match a request, Spring Security selects the condition according to the security DSL's matching/ordering rules. Example:

```java
// Illustrates MISCONFIGURATION: broad rule shadows sensitive rule.
.authorizeExchange(exchanges -> exchanges
    .pathMatchers("/api/**").authenticated()
    .pathMatchers("/api/admin/**").hasRole("ADMIN")
    .anyExchange().denyAll()
)
```

Here, `/api/admin/users` matches the broad `/api/**` rule first and only requires authentication. The admin condition declared afterwards may never get a chance to apply.

Better configuration:

```java
.authorizeExchange(exchanges -> exchanges
    .pathMatchers("/api/admin/**").hasRole("ADMIN")
    .pathMatchers("/api/**").authenticated()
    .anyExchange().denyAll()
)
```

**Tip:** narrow/sensitive rules first, broad rules later, `anyExchange` last. Do not treat multiple rules matching the same URL as automatically combining with AND. When adding endpoints and multiple `SecurityWebFilterChain`s, check **chain selection order** as well, not only rule order within a single chain.

### 6.2. Authorization by HTTP Method

Authorities can be applied to a specific method and path:

```java
// Illustrative DSL snippet, not part of the GET-only project below.
.pathMatchers(HttpMethod.GET, "/api/reports/**")
    .hasAuthority("report:read")
.pathMatchers(HttpMethod.POST, "/api/reports/**")
    .hasAuthority("report:write")
```

Requires importing `org.springframework.http.HttpMethod`. A user with `report:read` **does not automatically have** `report:write`. For POST requests using browser cookies/sessions, CSRF must be considered separately; a 403 on POST may be caused by CSRF rather than missing authority.

## 7. Distinguishing 401, 403, and ROLE_ Misconfiguration

Several scenarios when using HTTP Basic in WebFlux:

| Request | Authentication | Actual Authority | Rule | Typical HTTP Status |
| --- | --- | --- | --- | --- |
| No credentials | Unauthenticated | None | `hasRole("ADMIN")` | **401** + `WWW-Authenticate` |
| Wrong password | Authentication failed | None | `hasRole("ADMIN")` | **401** |
| Right password | Authentication succeeded | `ROLE_ADMIN` | `hasRole("ADMIN")` | **200** if controller OK |
| Right password | Authentication succeeded | `ADMIN` | `hasRole("ADMIN")` | **403** |
| Right password | Authentication succeeded | `ADMIN` | `hasAuthority("ADMIN")` | **200** if controller OK |
| Right password | Authentication succeeded | `ROLE_ADMIN` | `hasAuthority("ADMIN")` | **403** |
| Right password | Authentication succeeded | `ROLE_ADMIN` | `hasAuthority("ROLE_ADMIN")` | **200** if controller OK |
| Right password | Authentication succeeded | `report:read` | `hasAuthority("report:read")` | **200** if controller OK |

Note: You cannot tell from HTTP **403** alone that a prefix mismatch is definitely the cause. CSRF, object-level permissions, a different chain, `denyAll`, or application policies can also return 403. Inspect authorities and policies in a controlled manner without logging credentials or raw tokens.

### 7.1. Do Not Confuse ROLE_ with SCOPE_

In a Spring Security OAuth2 resource server with JWT and the default scope converter, the `scope`/`scp` claim is typically mapped to a `GrantedAuthority` prefixed with **`SCOPE_`**. For example, scope `reports.read` can become:

```text
SCOPE_reports.read
```

In that case, you should write:

```java
.pathMatchers("/api/jwt-reports")
    .hasAuthority("SCOPE_reports.read")
```

Do not blindly replace it with `hasRole("reports.read")`: that requires `ROLE_reports.read`, which is a different name. JWT setups do not have to use the default converter; if your organization maps custom `roles`/`groups` claims, inspect `Authentication.getAuthorities()` after conversion rather than guessing from the token's JSON claims.

### 7.2. Do Not Confuse a Database "admin role" with ROLE_ADMIN

A database might store `role_name='ADMIN'`. Storing it that way **does not automatically make Spring Security see `GrantedAuthority("ROLE_ADMIN")`**. The `UserDetailsService`/`ReactiveUserDetailsService` conversion layer must choose a policy:

- Prepend `ROLE_` when mapping roles from the DB, then use `hasRole("ADMIN")`.
- Keep `ADMIN` as an authority as-is, then use `hasAuthority("ADMIN")`.
- Use a consistent converter across HTTP security, method security, and token policies.

Never prepend `ROLE_` again to a string that already has `ROLE_`, producing `ROLE_ROLE_ADMIN`. Never strip prefixes indiscriminately across all authorities, as that can break scopes/permissions.

## 8. Key Truth Table: Predict Before Running Tests

Suppose there are five users:

```text
admin   -> ROLE_ADMIN
raw     -> ADMIN
editor  -> ROLE_EDITOR
reader  -> ROLE_READER, report:read
scoped  -> SCOPE_reports.read
```

The table below uses `✔` for allowed access and `✘` for denied permission **after authentication has succeeded**:

| User | hasRole("ADMIN") | hasAuthority("ADMIN") | hasAuthority("ROLE_ADMIN") | hasAnyRole("ADMIN","EDITOR") | hasAuthority("report:read") |
| --- | --- | --- | --- | --- | --- |
| admin | ✔ | ✘ | ✔ | ✔ | ✘ |
| raw | ✘ | ✔ | ✘ | ✘ | ✘ |
| editor | ✘ | ✘ | ✘ | ✔ | ✘ |
| reader | ✘ | ✘ | ✘ | ✘ | ✔ |
| scoped | ✘ | ✘ | ✘ | ✘ | ✘ |

A role is recognized by its **prefix**, not because the username happens to be `admin`. User `raw` has the exact string `ADMIN` yet still fails `hasRole("ADMIN")`. User `scoped` has the right scope yet still fails `hasAuthority("report:read")` unless granted that exact permission name.

## 9. Runnable Java 17+ Project: Spring Boot WebFlux + role/authority

The project below uses **Spring Boot 3.5.16** and Java 17; this Boot version exists on Maven Central, though it is the **end-of-OSS-support release for the 3.5 line**, so it serves as an illustrative baseline, **not a recommendation for choosing a new production version in 2026**. When deploying a new system, choose a supported branch (e.g., Boot 4.x) and follow its migration guide.

This example uses HTTP Basic for reproducible HTTP authorization testing. Usernames/passwords are hardcoded **for this lesson only**, with passwords stored in `MapReactiveUserDetailsService` as BCrypt hashes (generated at startup). All endpoints are **GET**; there is no need to disable CSRF. Spring Security remains responsible for authentication, while each path rule determines the required authority.

### 9.1. Directory Structure

```text
role-authority-webflux/
├── pom.xml
└── src/
    ├── main/java/demo/roles/
    │   ├── Application.java
    │   ├── SecurityConfiguration.java
    │   └── ApiController.java
    └── test/java/demo/roles/
        └── RoleAuthorityWebFluxTests.java
```

### 9.2. `pom.xml`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>

    <groupId>demo</groupId>
    <artifactId>role-authority-webflux</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
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
        <dependency>
            <groupId>org.springframework.security</groupId>
            <artifactId>spring-security-test</artifactId>
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

The Spring Boot parent manages compatible versions of Spring Security, Reactor, and related libraries. Do not add `spring-boot-starter-web` just to get Basic auth, because that starter pulls in Servlet MVC and can cause the application to run on a different web stack than intended.

### 9.3. `src/main/java/demo/roles/Application.java`

```java
package demo.roles;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class Application {
    public static void main(String[] args) {
        SpringApplication.run(Application.class, args);
    }
}
```

### 9.4. `src/main/java/demo/roles/SecurityConfiguration.java`

```java
package demo.roles;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authentication.ReactiveAuthenticationManager;
import org.springframework.security.authentication.UserDetailsRepositoryReactiveAuthenticationManager;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.MapReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableWebFluxSecurity
public class SecurityConfiguration {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    MapReactiveUserDetailsService users(PasswordEncoder encoder) {
        // Shared demo password for easy testing, DO NOT use in real accounts.
        String password = "demo123";

        UserDetails admin = User.withUsername("admin")
            .password(encoder.encode(password))
            .roles("ADMIN") // granted authority: ROLE_ADMIN
            .build();

        UserDetails raw = User.withUsername("raw")
            .password(encoder.encode(password))
            .authorities("ADMIN") // NO ROLE_ prefix
            .build();

        UserDetails editor = User.withUsername("editor")
            .password(encoder.encode(password))
            .roles("EDITOR") // ROLE_EDITOR
            .build();

        UserDetails reader = User.withUsername("reader")
            .password(encoder.encode(password))
            .authorities("ROLE_READER", "report:read")
            .build();

        UserDetails scoped = User.withUsername("scoped")
            .password(encoder.encode(password))
            .authorities("SCOPE_reports.read")
            .build();

        UserDetails multi = User.withUsername("multi")
            .password(encoder.encode(password))
            .authorities(
                "ROLE_ADMIN", "report:read", "SCOPE_reports.read")
            .build();

        return new MapReactiveUserDetailsService(
            admin, raw, editor, reader, scoped, multi);
    }

    @Bean
    ReactiveAuthenticationManager authenticationManager(
            MapReactiveUserDetailsService users, PasswordEncoder encoder) {

        UserDetailsRepositoryReactiveAuthenticationManager manager =
            new UserDetailsRepositoryReactiveAuthenticationManager(users);
        manager.setPasswordEncoder(encoder);
        return manager;
    }

    @Bean
    SecurityWebFilterChain securityWebFilterChain(
            ServerHttpSecurity http, ReactiveAuthenticationManager manager) {

        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers("/api/public").permitAll()
                .pathMatchers("/api/admin").hasRole("ADMIN")
                .pathMatchers("/api/raw-admin").hasAuthority("ADMIN")
                .pathMatchers("/api/admin-exact")
                    .hasAuthority("ROLE_ADMIN")
                .pathMatchers("/api/reader").hasRole("READER")
                .pathMatchers("/api/report").hasAuthority("report:read")
                .pathMatchers("/api/scoped")
                    .hasAuthority("SCOPE_reports.read")
                .pathMatchers("/api/editors")
                    .hasAnyRole("ADMIN", "EDITOR")
                .pathMatchers("/api/me").authenticated()
                .anyExchange().denyAll()
            )
            .httpBasic(basic -> basic.authenticationManager(manager))
            .formLogin(form -> form.disable())
            .build();
    }
}
```

**Why this project helps prevent misunderstandings:**

- User `admin` is created with `.roles("ADMIN")`, so it has `ROLE_ADMIN`.
- User `raw` is created with `.authorities("ADMIN")`, so it **does not have** `ROLE_ADMIN`.
- User `editor` has `ROLE_EDITOR`, sufficient for `hasAnyRole("ADMIN","EDITOR")` but insufficient for `hasRole("ADMIN")`.
- User `reader` has **both** `ROLE_READER` and `report:read`. It does not have `ROLE_ADMIN`.
- User `scoped` has `SCOPE_reports.read`, which does not automatically become `report:read`.
- User `multi` is explicitly granted three authorities; this is the clearest way when you want role + permission + scope together in an example.
- `anyExchange().denyAll()` acts as **default deny** for unmatched requests, preventing newly added endpoints from being accidentally exposed.
- `httpBasic(...)` allows testing with real credentials; `formLogin(...disable())` prevents login page redirects from interfering with 401/403 results.
- Uses BCrypt to hash passwords in the demo user store, but **never hardcode production passwords**. With real HTTP Basic outside localhost, TLS/HTTPS and brute-force protections are required.

### 9.5. `src/main/java/demo/roles/ApiController.java`

```java
package demo.roles;

import java.util.stream.Collectors;

import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class ApiController {

    @GetMapping("/api/public")
    public Mono<String> publicRoute() {
        return Mono.just("public OK");
    }

    @GetMapping("/api/admin")
    public Mono<String> adminRoute() {
        return Mono.just("admin OK");
    }

    @GetMapping("/api/raw-admin")
    public Mono<String> rawAdminRoute() {
        return Mono.just("raw authority OK");
    }

    @GetMapping("/api/admin-exact")
    public Mono<String> adminExactRoute() {
        return Mono.just("role authority OK");
    }

    @GetMapping("/api/reader")
    public Mono<String> readerRoute() {
        return Mono.just("reader OK");
    }

    @GetMapping("/api/report")
    public Mono<String> reportRoute() {
        return Mono.just("report OK");
    }

    @GetMapping("/api/scoped")
    public Mono<String> scopedRoute() {
        return Mono.just("scope OK");
    }

    @GetMapping("/api/editors")
    public Mono<String> editorsRoute() {
        return Mono.just("editors OK");
    }

    @GetMapping("/api/me")
    public Mono<String> authorities() {
        return ReactiveSecurityContextHolder.getContext()
            .map(SecurityContext::getAuthentication)
            .map(authentication -> "authorities="
                + authentication.getAuthorities().stream()
                    .map(GrantedAuthority::getAuthority)
                    .sorted()
                    .collect(Collectors.joining(",")));
    }
}
```

The `/api/me` endpoint lets you **observe in the demo** the actual `GrantedAuthority` set placed into the reactive security context by Spring Security. Do not expose all authorities in production if that reveals sensitive internal authorization details; it is better to read from controlled server logs/metrics or expose only permissions needed for UX.

In this code, the `Authentication` import is not directly referenced in the body (and can be removed), though it does not prevent compilation. If your IDE warns about an unused import, delete it for clean code style.

## 10. WebTestClient Test Suite: Real Authentication, Real Permission Checks

This is where the prefix rules are proven. `@WithMockUser` or `mockUser()` can be useful for testing **authorization policies** but do not prove the password encoder and Basic converter work. The test suite below uses **real `Authorization: Basic`** via `setBasicAuth`, testing both the authentication mechanism and the granted authorities.

### 10.1. `src/test/java/demo/roles/RoleAuthorityWebFluxTests.java`

```java
package demo.roles;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.http.HttpHeaders;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.springSecurity;

@SpringBootTest
class RoleAuthorityWebFluxTests {

    @Autowired
    ApplicationContext context;

    private WebTestClient client;

    @BeforeEach
    void setup() {
        client = WebTestClient
            .bindToApplicationContext(context)
            .apply(springSecurity())
            .configureClient()
            .build();
    }

    private WebTestClient.ResponseSpec getAs(String path, String username) {
        return client.get().uri(path)
            .headers(headers -> headers.setBasicAuth(username, "demo123"))
            .exchange();
    }

    @Test
    void publicEndpointAllowsAnonymous() {
        client.get().uri("/api/public")
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("public OK");
    }

    @Test
    void protectedEndpointWithoutCredentialsNeedsAuthentication() {
        client.get().uri("/api/admin")
            .exchange()
            .expectStatus().isUnauthorized()
            .expectHeader().exists(HttpHeaders.WWW_AUTHENTICATE);
    }

    @Test
    void invalidPasswordIsAuthenticationFailure() {
        client.get().uri("/api/admin")
            .headers(h -> h.setBasicAuth("admin", "wrong"))
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void rolesAdminPassesHasRoleAdmin() {
        getAs("/api/admin", "admin")
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("admin OK");
    }

    @Test
    void rawAuthorityAdminDoesNotPassHasRoleAdmin() {
        getAs("/api/admin", "raw")
            .expectStatus().isForbidden();
    }

    @Test
    void rawAuthorityAdminPassesHasAuthorityAdmin() {
        getAs("/api/raw-admin", "raw")
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("raw authority OK");
    }

    @Test
    void roleAdminDoesNotPassHasAuthorityAdmin() {
        getAs("/api/raw-admin", "admin")
            .expectStatus().isForbidden();
    }

    @Test
    void roleAdminPassesExactRoleAuthority() {
        getAs("/api/admin-exact", "admin")
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("role authority OK");
    }

    @Test
    void rawAdminDoesNotPassExactRoleAuthority() {
        getAs("/api/admin-exact", "raw")
            .expectStatus().isForbidden();
    }

    @Test
    void readerRolePassesHasRoleReader() {
        getAs("/api/reader", "reader")
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("reader OK");
    }

    @Test
    void readerPermissionPassesHasAuthorityReportRead() {
        getAs("/api/report", "reader")
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("report OK");
    }

    @Test
    void adminWithoutReportPermissionIsForbidden() {
        getAs("/api/report", "admin")
            .expectStatus().isForbidden();
    }

    @Test
    void jwtStyleScopeAuthorityIsExact() {
        getAs("/api/scoped", "scoped")
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("scope OK");
    }

    @Test
    void jwtStyleScopeIsNotPlainReportPermission() {
        getAs("/api/report", "scoped")
            .expectStatus().isForbidden();
    }

    @Test
    void editorPassesHasAnyRoleAdminOrEditor() {
        getAs("/api/editors", "editor")
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("editors OK");
    }

    @Test
    void adminAlsoPassesHasAnyRoleAdminOrEditor() {
        getAs("/api/editors", "admin")
            .expectStatus().isOk();
    }

    @Test
    void rawAdminDoesNotPassHasAnyRoleAdminOrEditor() {
        getAs("/api/editors", "raw")
            .expectStatus().isForbidden();
    }

    @Test
    void multipleExplicitAuthoritiesPermitAllMatchingRoutes() {
        getAs("/api/admin", "multi")
            .expectStatus().isOk();
        getAs("/api/report", "multi")
            .expectStatus().isOk();
        getAs("/api/scoped", "multi")
            .expectStatus().isOk();
    }

    @Test
    void exactAuthoritiesAreVisibleInReactiveSecurityContext() {
        getAs("/api/me", "raw")
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("authorities=ADMIN");

        getAs("/api/me", "admin")
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("authorities=ROLE_ADMIN");
    }

    @Test
    void unspecifiedRouteUsesDefaultDeny() {
        getAs("/api/unlisted", "admin")
            .expectStatus().isForbidden();
    }
}
```

There are **20 `@Test` methods** (several execute multiple HTTP requests). A shared `WebTestClient` creates a new request in each test; `setBasicAuth` sends a properly formatted Basic header. The test suite verifies `hasRole`, `hasAnyRole`, `hasAuthority`, raw roles without prefixes, scopes not automatically renamed, 401 when unauthenticated, 403 when lacking permissions, and default deny.

**A note on "authenticated" tests:** To test only authorization without relying on BCrypt, you can use `client.mutateWith(mockUser("someone").authorities(...))`. However, when the goal is verifying `UserDetails` mapping + Basic flow, real-credential tests as above are more valuable. Do not mix results from mocks into claims that Basic authentication was verified.

### 10.2. Summary of Results

| User / credentials | Endpoint | Rule | Expected |
| --- | --- | --- | --- |
| No credentials | `/api/public` | `permitAll` | **200** |
| No credentials | `/api/admin` | `hasRole("ADMIN")` | **401** |
| `admin:wrong` | `/api/admin` | Basic authentication | **401** |
| `admin:demo123` | `/api/admin` | `hasRole("ADMIN")` | **200** |
| `raw:demo123` | `/api/admin` | `hasRole("ADMIN")` | **403** |
| `raw:demo123` | `/api/raw-admin` | `hasAuthority("ADMIN")` | **200** |
| `admin:demo123` | `/api/raw-admin` | `hasAuthority("ADMIN")` | **403** |
| `admin:demo123` | `/api/admin-exact` | `hasAuthority("ROLE_ADMIN")` | **200** |
| `raw:demo123` | `/api/admin-exact` | `hasAuthority("ROLE_ADMIN")` | **403** |
| `reader:demo123` | `/api/reader` | `hasRole("READER")` | **200** |
| `reader:demo123` | `/api/report` | `hasAuthority("report:read")` | **200** |
| `admin:demo123` | `/api/report` | `hasAuthority("report:read")` | **403** |
| `scoped:demo123` | `/api/scoped` | `hasAuthority("SCOPE_reports.read")` | **200** |
| `scoped:demo123` | `/api/report` | `hasAuthority("report:read")` | **403** |
| `editor:demo123` | `/api/editors` | `hasAnyRole("ADMIN", "EDITOR")` | **200** |
| `raw:demo123` | `/api/editors` | `hasAnyRole("ADMIN", "EDITOR")` | **403** |
| `multi:demo123` | `/api/admin`, `/api/report`, `/api/scoped` | Three corresponding authorities | **200** |
| `admin:demo123` | `/api/unlisted` | `denyAll` | **403** |

Do not hardcode 401/403 error bodies unless you have customized the handlers. WebFlux/Boot can change the body/headers depending on content negotiation. In this lesson, the core assertions are **status, exact authority names, and success response bodies**.

## 11. Running Maven and Observing with curl

### 11.1. Running Tests

In the project directory containing `pom.xml`:

```bash
java -version
mvn -version
mvn clean test
```

Surefire is expected to report **20 tests, 0 failures, 0 errors** and Maven finishes with `BUILD SUCCESS` on a Java 17+ environment with compatible dependencies installed. This is the **expected result from the example code**; it cannot be treated as an actual local run result before executing it. If errors occur, read `target/surefire-reports` and verify the JDK/Maven versions and Java sources in the `demo.roles` package.

Start the app:

```bash
mvn spring-boot:run
```

In another terminal:

```bash
# Public, no credentials needed.
curl -i http://localhost:8080/api/public

# Missing credentials => 401 + challenge.
curl -i http://localhost:8080/api/admin

# Same hasRole("ADMIN") endpoint:
curl -i -u admin:demo123 http://localhost:8080/api/admin
curl -i -u raw:demo123 http://localhost:8080/api/admin

# Comparing hasAuthority("ADMIN") and hasAuthority("ROLE_ADMIN"):
curl -i -u raw:demo123 http://localhost:8080/api/raw-admin
curl -i -u admin:demo123 http://localhost:8080/api/raw-admin
curl -i -u admin:demo123 http://localhost:8080/api/admin-exact

# Specific permission differs from role:
curl -i -u reader:demo123 http://localhost:8080/api/report
curl -i -u admin:demo123 http://localhost:8080/api/report

# JWT-style scope is still an authority string:
curl -i -u scoped:demo123 http://localhost:8080/api/scoped

# hasAnyRole is OR:
curl -i -u editor:demo123 http://localhost:8080/api/editors
curl -i -u raw:demo123 http://localhost:8080/api/editors

# Inspect demo user authorities (do not expose this endpoint in production):
curl -i -u raw:demo123 http://localhost:8080/api/me
curl -i -u admin:demo123 http://localhost:8080/api/me
```

On PowerShell, you can use `curl.exe` instead of the `curl` alias. With real credentials, avoid putting passwords directly in command-line history/process lists; use client secret handling and always call APIs over HTTPS. All passwords in the block above are **dummy learning data**.

### 11.2. Sample Responses

`GET /api/admin` with user `admin`:

```http
HTTP/1.1 200 OK
Content-Type: text/plain;charset=UTF-8

admin OK
```

Same endpoint with user `raw`:

```http
HTTP/1.1 403 Forbidden
```

`GET /api/raw-admin` with user `raw`:

```http
HTTP/1.1 200 OK
Content-Type: text/plain;charset=UTF-8

raw authority OK
```

`GET /api/admin` without credentials:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Basic realm="Realm"
```

Realm/header values vary across versions and customizations; these are only sample responses. In tests, check that the **header exists** rather than hardcoding `realm="Realm"` unless your project explicitly configures a fixed realm.

## 12. Can the Role Prefix Be Customized?

**There are mechanisms to customize the role prefix**, but you must clearly distinguish where they apply:

1. **Method security** expressions (such as `@PreAuthorize("hasRole('ADMIN')")`) can use a configured default role prefix via the method security mechanism, including `GrantedAuthorityDefaults` in the appropriate Spring Security configuration.
2. Standard `AuthorityReactiveAuthorizationManager.hasRole("ADMIN")` is documented to create an authority requirement with the **`ROLE_` prefix**. Typical `ServerHttpSecurity.authorizeExchange(...).hasRole(...)` configurations use that exact mechanism.
3. **Do not assume** that simply adding a `GrantedAuthorityDefaults("APP_")` bean will simultaneously change every WebFlux HTTP `hasRole`, every method expression, every user builder, and every JWT authority converter to `APP_`.
4. To make an HTTP rule check a custom string `APP_ADMIN`, the clearest, most transparent, and easiest-to-test approach is **`hasAuthority("APP_ADMIN")`** and mapping the identity provider to that exact authority.
5. To keep the system consistent, standardize mappers and policies, then test each layer: HTTP, method, and token conversion.

Example using a custom prefix via **explicit authority**:

```java
// Illustrative example, DO NOT modify the Section 9 project:
.pathMatchers("/api/custom-admin")
    .hasAuthority("APP_ADMIN")
```

The user needs `GrantedAuthority("APP_ADMIN")`, not `ROLE_ADMIN`. This approach causes fewer surprises than trying to alter the entire default role prefix without knowing its scope of impact.

### 12.1. Reactive Method Security Is Not HTTP Security

Example method-level rule:

```java
@PreAuthorize("hasRole('ADMIN')")
public Mono<String> approveReport(String reportId) {
    return service.approve(reportId);
}
```

**This is an illustrative snippet and does not compile standalone**, as it lacks service definitions and imports; for real use, `@EnableReactiveMethodSecurity` must be enabled in an appropriate configuration. An HTTP rule may require `hasAuthority("report:read")` before the controller runs, while the underlying method requires role `ADMIN`. The final effective permission is the intersection of the security gates actually applied.

Do not rely on HTTP path matchers as the sole defense for multi-tenant data, user-owned objects, or services invoked outside HTTP. **Business-layer authorization** must also verify resource ownership, tenant boundaries, and the action being performed.

## 13. Authorities from JWT, OIDC, LDAP, and Databases

In production applications, `GrantedAuthority` instances are usually not created from `MapReactiveUserDetailsService` as in this lesson. Sources may include:

- Database: role, permission, role–permission, and user–role tables.
- LDAP/Active Directory: groups mapped to authorities.
- OAuth2 resource server JWT: scopes and `roles`/`groups` claims converted into authorities by a converter.
- OIDC: identity provider attributes, token claims, and application-controlled mapping policies.

**General rule:** Spring Security inspects **`Authentication.getAuthorities()`**. A claim such as:

```json
{"sub":"123","roles":["ADMIN"],"scope":"reports.read"}
```

**does not guarantee** that at authorization time there will be `ROLE_ADMIN`, `ADMIN`, `SCOPE_reports.read`, or all three. You must check the configured converter mechanism. Default converters follow conventions, but never assume an arbitrary JSON claim is turned into the exact `GrantedAuthority` format you expect.

### 13.1. Mapping Roles from a Database

Suppose the DB returns `"ADMIN"` and the HTTP rule requires `hasRole("ADMIN")`. The mapping layer must grant the authority `ROLE_ADMIN`:

```java
// Illustrative snippet inside a mapper:
String roleFromDatabase = "ADMIN";
GrantedAuthority granted =
    new SimpleGrantedAuthority("ROLE_" + roleFromDatabase);
```

This snippet is not a standalone Java file. If the DB already stores `"ROLE_ADMIN"`, check the prefix before transforming, or better yet, standardize the schema from the start. Never unconditionally prepend `ROLE_`, as it easily creates `ROLE_ROLE_ADMIN`.

### 13.2. Keeping JWT Scope and Custom Role Mapping Separate

A converter for scopes might produce `SCOPE_reports.read`. A separate mapper for roles might produce `ROLE_ADMIN`. These two authority forms serve different purposes:

```text
ROLE_ADMIN             -> Role assigned to a user/group
report:read            -> Application permission
SCOPE_reports.read     -> OAuth2 access token scope
```

Both are `GrantedAuthority` instances once granted by a mapper, but **they do not imply each other**. In real applications, design who issues scopes, who has permission to assign roles, token audience, tenant boundaries, and expiry/revocation. Never trust roles sent arbitrarily by a client via headers.

## 14. Common Errors and Troubleshooting

| Symptom | Possible Cause | How to Check / Fix |
| --- | --- | --- |
| User has `ADMIN`, `hasRole("ADMIN")` returns 403 | Missing `ROLE_` | Map `ROLE_ADMIN` or use `hasAuthority("ADMIN")` if appropriate |
| User has `ROLE_ADMIN`, `hasAuthority("ADMIN")` returns 403 | `hasAuthority` matches exact string | Use `hasAuthority("ROLE_ADMIN")` or `hasRole("ADMIN")` |
| Writing `hasRole("ROLE_ADMIN")` fails at startup | Role argument already contains prefix | Use `hasRole("ADMIN")` |
| Writing `.roles("ROLE_ADMIN")` fails | User builder adds prefix automatically | Use `.roles("ADMIN")` |
| Calling `.roles("ADMIN").authorities("report:read")` drops `ROLE_ADMIN` | Builder typically replaces the authority list | Use a single `.authorities("ROLE_ADMIN","report:read")` |
| Role `ADMIN` does not automatically grant `report:read` | Roles do not imply permissions by default | Grant additional authorities or define mapping/hierarchy |
| Scope `reports.read` fails `hasRole("reports.read")` | `ROLE_` differs from `SCOPE_` | Use `hasAuthority("SCOPE_reports.read")` if converter maps it that way |
| Different uppercase/lowercase on authorities | String matching is case-sensitive | Standardize authority naming at the source |
| Admin rule is ignored | Broad rule declared before narrow rule | Place sensitive paths before `/api/**` |
| API uses JWT, but Basic tests pass and you assume JWT has the role | Two different authentication converters | Test the real JWT mechanism and token authority mapping |
| DB role has double prefix `ROLE_ROLE_ADMIN` | Mapper prepends prefix without checking data | Normalize role names, avoid double prefixing |
| Missing credentials returns 401 | Unauthenticated | Check entry point and authentication mechanism |
| Authenticated but lacking permission returns 403 | Authorization denied | Inspect actual authorities and matchers |
| POST returns 403 despite having `ROLE_ADMIN` | Could be CSRF, method matcher, or another rule | Check CSRF token, security chain, HTTP method |
| `hasAnyRole` passes with only 1 role | Logical OR, not AND | Use a custom policy if both are required |
| `@PreAuthorize` method and HTTP rule give different results | Prefix/mapping or policy differs across the two layers | Test and align configuration at each layer |
| WebFlux project uses `SecurityFilterChain` | Mixed Servlet configuration | Use `SecurityWebFilterChain`, `ServerHttpSecurity` |
| Undeclared endpoint returns 403 instead of 404 | `anyExchange().denyAll()` blocks before controller | This may be the intended default-deny behavior |
| Logging authorities by printing the entire `Authentication` | Leaks credentials or sensitive security info | Only log allowed state and authority names, never secrets |

### 14.1. Practical Debugging Workflow

1. Confirm **which security chain** matches the request. If there are multiple chains, inspect their matchers/order.
2. Confirm whether authentication actually **succeeded**. HTTP 401 is usually not a role naming mistake.
3. Inspect `Authentication.getAuthorities()` in tests or controlled logs; do not rely on usernames or unmapped DB roles.
4. Write down the **exact string** the rule expects: `hasRole("ADMIN")` → `ROLE_ADMIN` in the default setup; `hasAuthority("ADMIN")` → `ADMIN`.
5. Check `pathMatchers` order, GET/POST methods, and default deny.
6. If using JWT/OIDC, inspect what authorities the converter produces from claims, avoiding leaking raw tokens during debugging.
7. If the request goes through method security or service-level authorization, inspect that layer's rules as well.
8. If the request is POST/PUT/DELETE, check CSRF before concluding 403 is due to a missing authority.

## 15. Practice Exercises and Answers

**Question 1.** A user has only `GrantedAuthority("ROLE_ADMIN")`. What do the two rules `hasRole("ADMIN")` and `hasAuthority("ADMIN")` evaluate to?  
**Answer:** The first rule passes, the second fails. To match with `hasAuthority`, require `hasAuthority("ROLE_ADMIN")`.

**Question 2.** A user has only `GrantedAuthority("ADMIN")`. Does `hasRole("ADMIN")` pass?  
**Answer:** Not in WebFlux HTTP with the default prefix, because `hasRole` requires `ROLE_ADMIN`. `hasAuthority("ADMIN")` is the matching rule.

**Question 3.** Does `.roles("ADMIN")` create the authority `ADMIN`?  
**Answer:** It creates `ROLE_ADMIN`, not `ADMIN`.

**Question 4.** Does `.roles("ROLE_ADMIN")` create `ROLE_ROLE_ADMIN`?  
**Answer:** The standard User builder API rejects role inputs that already contain `ROLE_` rather than allowing that usage. Use `.roles("ADMIN")`.

**Question 5.** Does role `ROLE_ADMIN` automatically grant `report:read`?  
**Answer:** No. You must grant the extra permission, use mapping/hierarchy, or write a policy suitable for admins.

**Question 6.** Does `hasAnyRole("ADMIN", "EDITOR")` require both roles or just one?  
**Answer:** Only at least one. This is an OR.

**Question 7.** Which authority does the default scope mapper typically turn JWT scope `reports.read` into?  
**Answer:** In a resource server using the default scope converter, it is typically `SCOPE_reports.read`, not `ROLE_reports.read`.

**Question 8.** Why can a user log in with the right password and still receive 403?  
**Answer:** Authentication succeeded, but authorization did not find the authority required by the endpoint, or another rule (CSRF, default deny, object-level permission) denied it.

**Question 9.** Should you configure `GrantedAuthorityDefaults` and assume `hasRole` at every layer immediately switches prefix?  
**Answer:** No. Prefix configuration mechanisms have their own scope; you must verify each API, especially WebFlux HTTP rules vs. reactive method security. `hasAuthority("APP_ADMIN")` is an explicit way to require a custom name.

**Question 10.** A user has `ROLE_READER` and `report:read`; does `.pathMatchers("/api/report").hasAuthority("report:read")` permit access?  
**Answer:** Yes, provided the user is validly authenticated and no other security gate denies it.

**Question 11.** What bug occurs if `/api/**` requiring `authenticated()` appears before `/api/admin/**` requiring `hasRole("ADMIN")`?  
**Answer:** The broad rule may match first and only require login, preventing the admin rule from being applied as intended. Put narrow matchers first.

**Question 12.** When an identity provider sends claim `roles:["ADMIN"]`, can you conclude Spring Security granted `ROLE_ADMIN`?  
**Answer:** No. You must know exactly which `GrantedAuthority` the converter maps the claim into.

### Additional Hands-On Exercises

1. Modify `reader` in the demo to have only `ROLE_READER`, removing `report:read`. Re-run `readerPermissionPassesHasAuthorityReportRead` and explain why it gets 403.
2. Try changing `/api/admin-exact` from `hasAuthority("ROLE_ADMIN")` to `hasAuthority("ADMIN")`. Predict how results change for `admin` and `raw`.
3. Add `/api/ops` with `hasAnyAuthority("report:read","SCOPE_reports.read")`; test with `reader`/`scoped`.
4. Add a `POST /api/report` method requiring `report:write`; keep CSRF if using browser-based credentials and build a test sending a valid CSRF token.
5. Try declaring `pathMatchers("/api/**").permitAll()` before `/api/admin` and write a test that catches the sensitive rule being shadowed by the broad rule.
6. If the application uses method security, add service-layer tests to verify prefixes work properly at both HTTP and method layers, not just HTTP.

## 16. Implementation Checklist

- [ ] Define a clear role naming convention (`ROLE_` or a custom convention).
- [ ] Distinguish group-level roles from fine-grained permissions; do not use group names as a substitute for resource permissions without a policy.
- [ ] `hasRole("ADMIN")` uses an **unprefixed** name in default WebFlux HTTP rules.
- [ ] `hasAuthority("ROLE_ADMIN")` checks the **full string**, without adding a prefix.
- [ ] `User.roles(...)` automatically creates `ROLE_`; `User.authorities(...)` uses the exact strings passed in.
- [ ] Do not ambiguously chain `.roles(...)` and `.authorities(...)`.
- [ ] Mappers from JWT/DB/LDAP/OIDC create the right authorities and avoid double prefixes.
- [ ] Distinguish `SCOPE_` from `ROLE_`, checking the actual converter.
- [ ] Sensitive rules are declared before broad rules, with `anyExchange().denyAll()` last.
- [ ] Tests exist for HTTP 401 without credentials, 403 with insufficient permissions, and 200 with the right role/authority.
- [ ] Tests exist for each security chain, method security, and object/tenant authorization if used.
- [ ] Do not assume `ROLE_ADMIN` automatically grants `ROLE_READER` or all permissions.
- [ ] Do not log raw passwords/tokens; maintain HTTPS and password hashing.
- [ ] For WebFlux APIs, use `SecurityWebFilterChain` and `ServerHttpSecurity`.

## 17. Summary and References

**Quick Reference Rules:**

```text
hasRole("ADMIN")                   -> requires "ROLE_ADMIN"
hasAuthority("ADMIN")              -> requires "ADMIN"
hasAuthority("ROLE_ADMIN")         -> requires "ROLE_ADMIN"
hasAnyRole("ADMIN", "EDITOR")       -> requires one of "ROLE_ADMIN", "ROLE_EDITOR"
hasAnyAuthority("A", "B")           -> requires one of "A", "B"
User.roles("ADMIN")                -> grants "ROLE_ADMIN"
User.authorities("ADMIN")          -> grants "ADMIN"
User.authorities("report:read")    -> grants "report:read"
```

All of these checks belong to **HTTP authorization** when declared via `ServerHttpSecurity.authorizeExchange`. `ROLE_` is not an arbitrary transformation applied to every permission string; actual values come from `Authentication.getAuthorities()`, and callers must authenticate successfully before checking roles/authorities on protected resources.

**Official Documentation:**

- Spring Security 6.5 – `ServerHttpSecurity`, `authorizeExchange`: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/config/web/server/ServerHttpSecurity.html
- Spring Security 6.5 – `ServerHttpSecurity.AuthorizeExchangeSpec.Access`: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/config/web/server/ServerHttpSecurity.AuthorizeExchangeSpec.Access.html
- Spring Security 6.5 – `AuthorityReactiveAuthorizationManager`: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authorization/AuthorityReactiveAuthorizationManager.html
- Spring Security 6.5 – `User.UserBuilder` (`roles`/`authorities`): https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/core/userdetails/User.UserBuilder.html
- Spring Security 6.5 – Reactive Web Security: https://docs.spring.io/spring-security/reference/6.5/reactive/configuration/webflux.html
- Spring Security 6.5 – Reactive Authorization: https://docs.spring.io/spring-security/reference/6.5/reactive/authorization/authorize-http-requests.html
- Spring Security 6.5 – Reactive Method Security: https://docs.spring.io/spring-security/reference/6.5/reactive/authorization/method.html
- Spring Security 6.5 – Reactive testing with WebTestClient: https://docs.spring.io/spring-security/reference/6.5/reactive/test/web/setup.html
- Spring Boot 3.5.16 release notice (end of OSS support for 3.5.x): https://spring.io/blog/2026/06/25/spring-boot-3-5-16-available-now/
