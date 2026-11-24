# Choosing Between Evicting Old Sessions and Rejecting New Logins When Exceeding Session Limits in Spring Security Reactive

## 1. Learning Objectives

A user logs into the same account from a laptop, a phone, and another browser. If the system allows only **one concurrent login session**, what happens when a second device successfully logs in with the right password?

With **Spring Security for Spring WebFlux**, you have two standard strategies:

1. **Allow the new login and evict an old session** — by default, invalidating the least recently used (LRU) session.
2. **Preserve the old session and reject the new login** — using a handler that prevents creating a new session once the limit is reached.

This lesson explains the reactive components, how to choose a policy for business needs, runnable configuration with Java 17+, hands-on testing with two browser profiles, registry/store management, and critical pitfalls around logout, session timeouts, multiple instances, OAuth2, and JWTs.

**Key reminder:** concurrent session control is a policy on **sessions tracked/registered by the system**; it does not mean limiting TCP connections, concurrent requests, or valid unexpired JWTs.

## 2. What Is a "Concurrent Session" Really?

In a cookie-based form-login app, a session normally corresponds to a server-side `WebSession` and a session ID sent by the browser via cookie. `SecurityContext` can be persisted across requests via `ServerSecurityContextRepository`, typically `WebSessionServerSecurityContextRepository`.

When concurrent sessions control is enabled, Spring Security reactive uses `ReactiveSessionRegistry` to track registered sessions per principal. Each session record can contain the session ID, last-access time, and invalidated status.

A user with two tabs sharing the **same session cookie** in the same browser profile normally uses only **one session**, not two. Two browser profiles, or an isolated incognito window alongside a regular browser, have separate cookie jars and can therefore create two distinct sessions.

| Concept | Example | Limited by `maximumSessions`? |
| --- | --- | --- |
| Second browser tab using the same session cookie | Two tabs in one profile | Usually still **one session** |
| Two independent profiles, each with its own `WebSession` | Profile A and B | **Two sessions** if both are registered |
| Two concurrent HTTP requests using the same cookie | Parallel page and API loads | **One session**, not two |
| HTTP Basic requests authenticating per credentials | Client sends `Authorization` on every request | Can be tracked by concurrent sessions control's success handler, yet semantics differ from form-login sessions |
| Self-contained JWT held by client | Multiple valid access tokens | **Not automatically** stored in `WebSession` registry |
| SSO session at an Identity Provider (IdP) | OAuth2 login to external provider | App registry **does not automatically** revoke IdP sessions |

Spring Security allows **unlimited sessions** by default until you configure a limit. Concurrent session control in the reactive stack has been supported since Spring Security 6.3; the API snippets in this lesson follow the Spring Security 6.5/7.1 line—do not copy Servlet API names.

## 3. Comparing the Two Policies

Suppose `SessionLimit.of(1)` is set, user `learner` is already logged into **Browser A**, and B is about to log in with valid credentials.

### 3.1. Policy 1 — Evict the least recently used session

~~~text
T0: Browser A logs in successfully -> session A is registered
T1: Browser B submits login form with valid credentials
T2: Spring Security checks registered session count: 1 / limit 1
T3: Exceeds limit if granting another session to B
T4: Default handler invalidates the LRU session (typically A)
T5: B logs in successfully; session B is now the active session
T6: A sends a new /private request -> no longer authorized via old session
~~~

The default handler class is `InvalidateLeastUsedServerMaximumSessionsExceededHandler`. It invalidates **only as many old sessions as needed** to satisfy the limit; it does not always destroy every session. For example, with limit 2, creating one extra session exceeds by one, so the handler typically revokes one LRU session.

**Pros:** users who lost a device or forgot to log out can still log in on a new device. This UX suits general-purpose systems, yet note the risk if an attacker already has credentials: a new login can kick the legitimate user out of their old session.

**Cons:** Browser A may abruptly be prompted to log in again; unsaved transaction flows may be interrupted. Provide a "Your session was replaced by another login" notice and draft-saving mechanisms where appropriate.

### 3.2. Policy 2 — Prevent new login

~~~text
T0: Browser A logs in successfully -> session A is registered
T1: Browser B submits login form with valid credentials
T2: Spring Security checks registered session count: 1 / limit 1
T3: Handler refuses to create a new authenticated session
T4: Browser B follows the authentication failure path
T5: A continues accessing /private with session A
T6: B can log in only after A logs out, expires, or the slot is freed
~~~

The matching reactive class is `PreventLoginServerMaximumSessionsExceededHandler`. It raises `SessionAuthenticationException` once the limit is reached and prevents successful authentication of the new session. When using **default form login**, the failed attempt typically redirects to the login page with an error state (e.g., `/login?error`); **do not** assume a fixed 401 status across every mechanism.

**Pros:** protects continuity on the active device; suits sensitive admin environments, provisioned terminals, or session/license policies prioritizing the existing logged-in session.

**Cons:** if a cookie is lost, the browser closes before session expiration, or the registry misses cleanup events, the user may be **unable to log back in** despite knowing the right password. The system needs sensible timeouts and a reliable way for users/support staff to revoke old sessions.

### 3.3. Decision table

| Criterion | Evict LRU session (default) | Reject new login |
| --- | --- | --- |
| New device logs in with valid credentials | Allowed after clearing old session | Rejected once limit is reached |
| Old device | Invalidated if selected | Continues working |
| User forgets to log out | Easy self-recovery | May be temporarily locked out |
| Device-switching UX | Convenient | Must log out/revoke old session |
| Risk of user being kicked out by another login | Yes | No under this policy |
| Account-takeover risk | Still needs MFA, alerts, and credential controls | Still needs MFA; attacker could log in first and claim the "slot" |
| User support requirements | Notice that session was replaced | Session management screen/timeouts/secure revocation |
| Suitable scenarios | Consumer web apps, mobile staff switching devices | Dedicated terminals, systems prioritizing active sessions |

**Neither policy replaces MFA, anomalous-login detection, device risk scoring, or token management.** "Reject new login" does not stop an attacker from logging in when no session exists yet.

## 4. Participating Reactive Classes

A configuration via `ServerHttpSecurity.sessionManagement(...)` wires together these components:

| Component | Responsibility |
| --- | --- |
| `SecurityWebFilterChain` | Security filter chain for WebFlux requests |
| `ServerHttpSecurity.SessionManagementSpec.ConcurrentSessionsSpec` | DSL configuring session limits and exceeded handlers |
| `SessionLimit` | Determines maximum sessions from `Authentication` |
| `ReactiveSessionRegistry` | Queries and stores known sessions for a principal |
| `InMemoryReactiveSessionRegistry` | In-RAM registry implementation, suitable for demos/single nodes |
| `ConcurrentSessionControlServerAuthenticationSuccessHandler` | Checks the limit upon successful authentication |
| `RegisterSessionServerAuthenticationSuccessHandler` | Registers the session after successful authentication |
| `InvalidateLeastUsedServerMaximumSessionsExceededHandler` | Defaults to invalidating the LRU session when over limit |
| `PreventLoginServerMaximumSessionsExceededHandler` | Refuses creating a new session if limit is reached |
| `ServerMaximumSessionsExceededHandler` | Interface for swapping handling strategies |
| `WebSessionStore` | Backing data store for actual `WebSession`s |

Simplified flow:

~~~text
POST /login (browser B)
      |
      v
ServerFormLoginAuthenticationConverter
      |
      v
ReactiveAuthenticationManager: valid credentials?
      |
      +-- NO --> authentication failure handler
      |
      +-- YES --> ConcurrentSessionControlServerAuthenticationSuccessHandler
                         |
                         v
                  ReactiveSessionRegistry
                  getAllSessions(principal)
                         |
             +-----------+------------+
             |                        |
       below limit                at limit
             |                        |
             v                        v
      Register session     ServerMaximumSessionsExceededHandler
             |                        |
             |                +-------+-------+
             |                |               |
             |              EVICT           PREVENT
             |                |               |
             v                v               v
       login succeeds   evict old session  reject new login
       + save context   then admit B       via failure path
~~~

This is a learning model. Internal execution order, context saving, and specific handlers depend on the login mechanism and version. Never use the diagram as proof that every custom authentication filter registers sessions.

### A critical detail: the success handler

Spring Security automatically wires concurrent-session control success handlers for supported mechanisms such as **form login**, **OAuth2 login**, and **HTTP Basic**, **provided** you do not replace the success handler in a way that drops them.

For example, configuring:

~~~java
.formLogin(login -> login
        .authenticationSuccessHandler(
                new RedirectServerAuthenticationSuccessHandler("/")))
~~~

can **accidentally disable concurrent-session registration/control for form login** because it replaces the entire default success handler. When adding post-login logic (auditing/redirects), use the API that appends to the handler list instead of overwriting it; reactive docs provide `authenticationSuccessHandler(Consumer<List<ServerAuthenticationSuccessHandler>>)` for this purpose. Re-test concurrent-session behavior after customizing success handlers.

## 5. Complete Demo: Switching Policies with One Property

The example below runs a Java 17+ Spring Boot WebFlux app; `demo.session-policy` selects `evict` or `prevent`. It has one user `learner`, one public HTML route, and one route restricted to logged-in users.

**No need to write a login form yourself.** `formLogin(Customizer.withDefaults())` generates `GET /login` and handles `POST /login`; Spring Security keeps default CSRF protection enabled.

### 5.1. Create the project

Use Spring Initializr with Maven, Java 17+, Spring Boot **4.1.2** (or a compatible supported Boot patch release), and dependencies **Spring Reactive Web** and **Spring Security**.

Complete minimal `pom.xml`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>4.1.2</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>reactive-session-policy</artifactId>
    <version>0.0.1-SNAPSHOT</version>

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
~~~

Do not add `spring-boot-starter-web` because that is Spring MVC/Servlet. Do not manually pin mismatched versions of Spring Security, Reactor, and Netty; let the Spring Boot BOM manage them.

### 5.2. Complete Java code

Create `src/main/java/com/example/sessionpolicy/ReactiveSessionPolicyApplication.java`:

~~~java
package com.example.sessionpolicy;

import java.security.Principal;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.core.env.Environment;
import org.springframework.http.MediaType;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.session.InMemoryReactiveSessionRegistry;
import org.springframework.security.core.session.ReactiveSessionRegistry;
import org.springframework.security.core.userdetails.MapReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.authentication.PreventLoginServerMaximumSessionsExceededHandler;
import org.springframework.security.web.server.authentication.SessionLimit;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@SpringBootApplication
@EnableWebFluxSecurity
public class ReactiveSessionPolicyApplication {

    public static void main(String[] args) {
        SpringApplication.run(ReactiveSessionPolicyApplication.class, args);
    }

    @Bean
    MapReactiveUserDetailsService users() {
        UserDetails learner = User.withUsername("learner")
                .password("{noop}learn123")
                .roles("USER")
                .build();
        return new MapReactiveUserDetailsService(learner);
    }

    @Bean
    ReactiveSessionRegistry reactiveSessionRegistry() {
        return new InMemoryReactiveSessionRegistry();
    }

    @Bean
    SecurityWebFilterChain security(ServerHttpSecurity http, Environment env) {
        String mode = env.getProperty("demo.session-policy", "evict")
                .trim().toLowerCase(java.util.Locale.ROOT);

        if (!mode.equals("evict") && !mode.equals("prevent")) {
            throw new IllegalArgumentException(
                    "demo.session-policy must be evict or prevent");
        }

        return http
                .authorizeExchange(exchanges -> exchanges
                        .pathMatchers("/", "/public").permitAll()
                        .anyExchange().authenticated())
                .httpBasic(basic -> basic.disable())
                .formLogin(Customizer.withDefaults())
                .sessionManagement(sessions -> sessions
                        .concurrentSessions(concurrency -> {
                            concurrency.maximumSessions(SessionLimit.of(1));
                            if (mode.equals("prevent")) {
                                concurrency.maximumSessionsExceededHandler(
                                        new PreventLoginServerMaximumSessionsExceededHandler());
                            }
                            // "evict" uses Spring Security's default handler
                        }))
                .build();
    }

    @RestController
    static class Pages {

        @GetMapping(value = "/", produces = MediaType.TEXT_HTML_VALUE)
        Mono<String> index() {
            return Mono.just("""
                    <!doctype html>
                    <html lang="en">
                      <head><meta charset="UTF-8">
                        <title>Concurrent Session Demo</title></head>
                      <body>
                        <h1>Public Page</h1>
                        <a href="/private">Login-required page</a>
                      </body>
                    </html>
                    """);
        }

        @GetMapping("/public")
        Mono<String> publicPage() {
            return Mono.just("PUBLIC_OK");
        }

        @GetMapping("/private")
        Mono<String> privatePage(Principal principal) {
            return Mono.just("PRIVATE_OK:" + principal.getName());
        }
    }
}
~~~

**Explanation:**

- The `MapReactiveUserDetailsService` bean provides the test user `learner`. `{noop}` passwords are only for local learning; production requires a strong `PasswordEncoder`, HTTPS, and a real identity store.
- `ReactiveSessionRegistry` is used by Spring Security to store session information per user. `InMemoryReactiveSessionRegistry` fits a single-instance demo, not a full cluster solution.
- `SessionLimit.of(1)` caps **registered sessions** at one per user.
- In `evict` mode, no custom handler needs to be instantiated: the DSL defaults to `InvalidateLeastUsedServerMaximumSessionsExceededHandler`.
- In `prevent` mode, `maximumSessionsExceededHandler(new PreventLoginServerMaximumSessionsExceededHandler())` changes what happens when the limit is hit.
- HTTP Basic is disabled in the example so **only form login and cookie sessions** exist, keeping the two-browser-profile test clear. If Basic were enabled, each request could trigger authentication success with different semantics, which should not be used to simulate two form-login sessions.
- Default login is used without a custom success handler to avoid accidentally dropping the session-management success handlers.
- CSRF is not disabled; default form login includes a valid CSRF token. Never use GET to perform login/logout.
- `Principal` in `privatePage` reads the security-verified user, not a browser-declared name.

**Class-name version note:** the reactive Java API has the exact class `PreventLoginServerMaximumSessionsExceededHandler` in `org.springframework.security.web.server.authentication`. Some documentation snippets show the shorter name `PreventLoginMaximumSessionsExceededHandler`, which **does not match the Javadoc class in this package**. In your IDE, verify imports against the Javadoc for your exact version.

### 5.3. Running EVICT mode (default)

In the directory containing `pom.xml`:

~~~bash
./mvnw spring-boot:run
~~~

On Windows use `.\mvnw.cmd spring-boot:run`. If no Maven Wrapper is present, use `mvn spring-boot:run` with a compatible Maven installation.

Manual scenario:

1. Open **Browser A**, e.g., a normal Chrome profile. Visit `http://localhost:8080/private`; redirected to `/login`.
2. Enter `learner` / `learn123`. Browser A is taken to the requested resource and sees `PRIVATE_OK:learner`.
3. Open **Browser B** in an independent Chrome profile or incognito window **not sharing cookies** with A. Visit `/private` and log in with the **same account**.
4. In the default `evict` mode, B is logged in. Return to A and **refresh `/private`**. Session A has been selected for invalidation and is normally redirected to login.
5. Refresh B: session B continues accessing `/private` normally.

To inspect the initial redirect response without following redirects:

~~~bash
curl -i http://localhost:8080/private
~~~

Without an authenticated cookie, it normally returns HTTP **302** with `Location` pointing to `/login`. Do not pass `curl -L` when wanting to inspect the 302 response instead of the login page's 200 HTML.

**Do not use two tabs in the same browser profile** to test because they normally share the same session cookie and thus still count as one session. Do not hardcode expectations on session IDs or cleanup timing; verify behavior on the **next request** of the old session.

### 5.4. Running PREVENT mode (reject new logins)

Stop the application and restart with the property:

~~~bash
./mvnw spring-boot:run -Dspring-boot.run.arguments=--demo.session-policy=prevent
~~~

If running a built JAR, the syntax is easier to check and independent of Maven shell quoting rules:

~~~bash
java -jar target/reactive-session-policy-0.0.1-SNAPSHOT.jar --demo.session-policy=prevent
~~~

When using `java -jar`, build first with `./mvnw clean package`. For a mode change to take effect, you must **restart the application**; the property does not retroactively alter the policy of existing runtime sessions.

Repeat the test with A and B as two separate browser profiles:

1. A logs in successfully and visits `/private`.
2. B opens `/login` and enters valid `learner` / `learn123`.
3. Because A already occupies 1/1 slot, **B is refused a new authenticated session**. With default form login, B normally goes to `/login?error`; do not claim the response is HTTP 401 for form login.
4. A refreshes `/private` and still sees `PRIVATE_OK:learner`.
5. A logs out via Spring Security's logout button/form, or waits for session timeout/valid session revocation. B can try logging in again once the slot is freed.

**Proper logout flow:** default Spring Security form login handles `POST /logout` with CSRF; use the logout UI or a form with a valid token. Do not assume `GET /logout` always logs out when CSRF is enabled. If browser A merely closes its tab, the server does not necessarily know the session should end.

### 5.5. Results to observe

| Step | EVICT Mode | PREVENT Mode |
| --- | --- | --- |
| A logs in first | Succeeds | Succeeds |
| B logs in with same account after A | Succeeds; LRU session is invalidated | Fails because slot is full |
| B visits `/private` after login | `PRIVATE_OK:learner` | No authenticated session; redirected to login |
| A refreshes `/private` | Prompted to log in again | `PRIVATE_OK:learner` |
| A logs out actively, B retries login | B already has a session, no re-login needed | B can log in once registry frees A's session |
| A **different** user logs in | Gets separate slot if policy is per user | Gets separate slot if policy is per user |

Exact status codes, cookies, redirect URLs, and bodies may differ with custom handlers and versions. The exercise focuses on **who continues holding a valid session after the second login**.

## 6. Choosing Per-Account Limits with SessionLimit

`maximumSessions` accepts `SessionLimit`, a functional interface taking `Authentication` and returning `Mono<Integer>`. You can vary the limit by role or account tier. Example **snippet replacing `SessionLimit.of(1)`** in the security method above:

~~~java
SessionLimit limit = authentication -> {
    boolean unlimited = authentication.getAuthorities().stream()
            .anyMatch(a -> "ROLE_UNLIMITED_SESSIONS".equals(a.getAuthority()));
    if (unlimited) {
        return Mono.empty(); // unlimited
    }

    boolean admin = authentication.getAuthorities().stream()
            .anyMatch(a -> "ROLE_ADMIN".equals(a.getAuthority()));
    return Mono.just(admin ? 2 : 1);
};

// Inside concurrentSessions(...):
concurrency.maximumSessions(limit);
~~~

This is a **configuration snippet**, not a standalone Java class. Import `org.springframework.security.web.server.authentication.SessionLimit` and `reactor.core.publisher.Mono`. Meaning:

- `Mono.just(1)`: one session.
- `Mono.just(2)`: two sessions.
- `Mono.empty()`: unlimited for that selected user.
- `SessionLimit.UNLIMITED` is a built-in constant if all users have no limit.

**Do not confuse this with `Mono.empty()` from `AuthenticationManager`.** Here, empty is the contract of **`SessionLimit`**, meaning unlimited—**not** an authentication failure or session-save error.

When roles change after login, the session-count policy was evaluated on the `Authentication` supplied during authentication. If session counts must tighten immediately when a role is revoked, actively revoke/re-verify sessions rather than changing a database role and expecting the registry to clean up on its own.

## 7. Registry, Session Store, and Consistency

### 7.1. Registry and backing session store are two separate concerns

`ReactiveSessionRegistry` answers "which sessions are registered for this user?"; `WebSessionStore` answers "where is the concrete `WebSession` data stored?". To revoke a session reliably, both sides must coordinate.

If you only delete the registry record, the session cookie may still point to a `WebSession` holding `SecurityContext`. If you only delete `WebSession` while the registry retains the record, **PREVENT** mode may keep thinking the user is at capacity and block new logins.

An in-memory registry implementation applies to **one JVM/process**. Across multiple pods/nodes, a user can log in on node A and node B, with each node seeing its own session count. Enforcing a system-wide limit requires a shared session/registry solution, synchronized lifecycles, and contention control across concurrent logins.

### 7.2. Manual session revocation for lost devices

Reactive docs provide a pattern using `ReactiveSessionRegistry` and `WebSessionStore`. Example **service class added to an app already configured with a session registry/store**, not a standalone runnable file:

~~~java
import org.springframework.security.core.session.ReactiveSessionRegistry;
import org.springframework.web.server.session.WebSessionStore;
import reactor.core.publisher.Mono;

final class SessionRevocationService {
    private final ReactiveSessionRegistry registry;
    private final WebSessionStore store;

    SessionRevocationService(
            ReactiveSessionRegistry registry, WebSessionStore store) {
        this.registry = registry;
        this.store = store;
    }

    Mono<Void> revokeKnownSessions(String principal) {
        return registry.getAllSessions(principal)
                .concatMap(session -> session.invalidate()
                        .then(store.removeSession(session.getSessionId())))
                .then();
    }
}
~~~

**Explanation:**

- `getAllSessions(principal)` retrieves sessions known to the registry; use the exact same principal key format the registry stores. In real systems prefer stable user IDs, handling username changes.
- `session.invalidate()` marks the registry record invalid.
- `store.removeSession(id)` deletes the session from the actual backing store.
- `concatMap` serializes cleanup steps, appropriate when avoiding excessive concurrent operations.
- `then()` completes when the publisher finishes; never create a `Mono` without returning/subscribing to it.
- This mechanism covers **registered sessions**; it cannot destroy sessions unknown to the registry or JWTs outside `WebSession`.

Ensure the caller is authorized (users managing their own sessions or verified admins), log safe audit events, enforce CSRF on state-changing endpoints, and define error/retry policies. Never expose session IDs in logs or frontends.

### 7.3. Cleaning up sessions on expiration

PREVENT mode requires session slots to be freed **on time**:

- Logout must clear context/session/registry per configured mechanics.
- Session timeouts must be reflected in both the backing store and the registry.
- Eviction must clean up sessions across all nodes.
- Manually destroyed sessions must not linger as occupied "slots".

Test abrupt browser closes, network drops, session expirations, and server restarts. In production, provide a "Logged-in devices" screen or a "Log out other devices" flow protected by re-authentication/MFA per risk.

## 8. Do Not Equate WebSession with OAuth2 IdP, Basic, or JWT

### 8.1. Form login

The section 5 demo uses form login, session cookies, and Spring Security defaults, making outcomes straightforward to observe. Form-login success handlers integrate with concurrent session control unless overridden.

### 8.2. OAuth2/OIDC login

Reactive concurrent session control can record the **application session after OAuth2 login succeeds**, yet does not automatically know session counts inside the IdP/SSO. If device A loses its app session, it may still hold an active IdP login session and re-authenticate very quickly. When limits must apply at the identity provider too or global logout is needed, use the IdP's session/logout/revocation APIs with error handling and permission checks.

### 8.3. HTTP Basic

Reactive docs list HTTP Basic among mechanisms managed by the success handler. However, Basic requests typically send credentials **on every call**, so "logged in on two devices" has different semantics from browser form login. If using HTTP Basic in a purely stateless API, do not assume `maximumSessions(1)` automatically caps clients or request counts; choose matching authentication and session-tracking models.

### 8.4. Stateless JWT/Bearer tokens

JWTs are self-contained with claims and can be verified offline by resource servers; `ReactiveSessionRegistry` has no knowledge of issued JWTs. Thus `maximumSessions` on `WebSession` **does not automatically limit** valid JWTs or refresh tokens.

If business logic demands "one active device/token", consider token families/device IDs, refresh-token rotation, revoked-token stores, `jti` denylists, security versions, or introspection. Every resource server must enforce that state per policy; verifying only signature and `exp` lets old tokens keep working until expiration.

### 8.5. Multi-instance / cluster

When scaling from one node to multiple nodes, `InMemoryReactiveSessionRegistry` sees only that node's memory. A distributed `WebSession` store **does not by itself prove** the registry is shared and LRU selection is consistent. Your design must synchronize the session index and lifecycle, handle concurrent logins (races), and prevent two nodes from both seeing "one slot free" and issuing sessions.

## 9. Choosing a Policy for Business Scenarios

### 9.1. Staff apps with frequent device switching

**Prefer EVICT** when UX demands users quickly log into a new machine after forgetting to log out. Add "another login occurred" notifications, device risk checks, email/push alerts, MFA, and auditing.

### 9.2. POS/terminals or continuously authorized devices

**Prefer PREVENT** if losing the current session disrupts operations or an operational shift must bind to an approved terminal. However, an admin-authorized revocation flow is mandatory; if a device is lost, the system must never lock out the user permanently just because the registry holds an old slot.

### 9.3. High-risk financial or administrative systems

Do not rely on a single enum alone. Consider allowing new-device logins only after MFA/step-up, revoking old sessions with confirmation and alerts, locking accounts on anomalies, bounding `WebSession` lifetime, checking account state, and monitoring. If users legitimately need two devices, a limit of 1 may be the wrong policy from the start.

### 9.4. Limits by role, tenant, or subscription

You can write `SessionLimit` to return 1, 2, or unlimited based on authorities, yet if limits depend on subscription/tenant data in a database, the policy needs a reactive data source and safe concurrency handling. Never call blocking JDBC directly inside a lambda running on the reactive authentication success path.

## 10. Common Errors and Pitfalls

### "Configured `maximumSessions(1)` yet I can still log in across multiple tabs"

Two tabs may share the **same `WebSession` cookie**. Test with two independent browser profiles, checking the `SESSION` cookie and registry instead of counting tabs.

### "Configured prevent mode, user closed the browser and can no longer log in"

Closing the browser **does not guarantee** sending a logout request. Server-side sessions may survive until timeout. Configure sensible timeouts, CSRF-protected logout, and old-session revocation flows.

### "Customized form success handler and session limits stopped working"

A replacing handler can drop `ConcurrentSessionControlServerAuthenticationSuccessHandler` and `RegisterSessionServerAuthenticationSuccessHandler` from the flow. Use the list-appending handler API or integrate the mechanics explicitly; always re-test with two browsers after customizing.

### "Used `PreventLoginMaximumSessionsExceededHandler` and the IDE says not found"

In the reactive Javadoc, the class name is `PreventLoginServerMaximumSessionsExceededHandler`. Do not use the similar name from narrative docs or Servlet APIs. Import from `org.springframework.security.web.server.authentication`.

### "Used `maxSessionsPreventsLogin(true)` on WebFlux"

That is familiar syntax from older **Servlet** APIs/docs. In the verified reactive DSL, configure via `maximumSessions(SessionLimit.of(...))` and `maximumSessionsExceededHandler(...)`. Never mix `HttpSecurity` with `ServerHttpSecurity`.

### "Evicting an old session revokes JWTs, refresh tokens, and IdP SSO too"

No. Those systems maintain separate authentication state. An app's `WebSession`/registry does not automatically revoke bearer tokens or identity-provider sessions.

### "`InMemoryReactiveSessionRegistry` works fine across three pods"

There is no cluster-wide guarantee when each pod holds its own registry. Design a shared registry, shared session store, and cross-node race protection.

### "The second form login was rejected, so shouldn't it return 401?"

With form login, the failure handler may redirect to `/login?error`; HTTP 401 is more common for Basic/Bearer APIs. Verify **no new session was granted**, rather than hardcoding one status code across all authentication mechanisms.

### "Choosing LRU means the oldest opened session is evicted"

Not necessarily. **Least recently used** is the **least recently accessed** session, not necessarily the earliest created. When A stays active frequently while B opened earlier yet sat idle, LRU selection depends on last-access timestamps and their update mechanics.

### "Re-logging in on the same `WebSession` always increases the session count"

Do not assume so. The registry tracks session IDs and success handlers. Upon re-login/cookie rotation, registration/invalidation depends on the session lifecycle; test against your real implementation rather than treating form-submission counts as session counts.

## 11. Required Test Matrix

| Scenario | How to test | Expected result |
| --- | --- | --- |
| A logs in first | Browser A logs in | Valid session A exists |
| EVICT when B logs in | Independent B logs in, A refreshes | B succeeds, A is prompted to log in again |
| PREVENT when B logs in | Independent B logs in, A refreshes | B gets no auth session; A stays valid |
| Different user logs in | Use another account | Independent limit per principal |
| Two tabs sharing cookie | Two tabs in same profile | Not counted as two separate sessions |
| A logs out then B logs in under PREVENT | Form POST logout with CSRF | Slot is freed; B can log in |
| A disconnects/closes browser | No logout sent, wait past timeout | Session is released per configured lifecycle |
| Admin revokes A | Service invalidates session + removes store | A can no longer access with old cookie |
| Concurrent logins | B and C log in nearly simultaneously | Does not exceed policy per system's published guarantee |
| Multiple nodes | A logs in on node 1, B on node 2 | Cluster-wide registry/store enforces same policy |
| Custom success handler | Add audit or redirect | Concurrent control remains active |
| OAuth2 SSO | App session expires while IdP session stays alive | App limits and IdP sessions handled properly |
| JWT access token | Token remains unexpired after `WebSession` revocation | Token blocked only if dedicated revocation/version exists |

For automated testing, use `WebTestClient` with Spring Security test support to log in via form/CSRF and manage two separate cookie jars, or use browser tests (Playwright/Selenium) for redirect flows. Never assert only 302/200: check which browser actually holds a principal on the next request.

## 12. Implementation Checklist

1. Clearly define a "session" as a **principal-registered `WebSession`**, not a tab, connection, or JWT.
2. Explicitly choose **EVICT** or **PREVENT** from product and UX requirements.
3. Configure proper `SessionLimit`: a positive integer, or `UNLIMITED` where permitted.
4. Configure `ReactiveSessionRegistry` and verify the login success handler registers sessions.
5. If PREVENT: provide timeouts, logout, cleanup, and an old-session revocation tool.
6. If EVICT: provide session-replaced notifications, new-login audits, and MFA/risk controls.
7. Keep both registry and `WebSessionStore` synchronized in clusters; handle concurrent logins across nodes.
8. Keep CSRF protection for form login/logout; cookies use HTTPS and `Secure`/`HttpOnly`/`SameSite` per threat model.
9. Never rely on `WebSession` limits to control JWTs/refresh tokens/IdP sessions.
10. Test independent A/B, logout, session timeout, password change, role change, cluster, and infrastructure failures.
11. Never log session IDs, passwords, cookies, access/refresh tokens, or sensitive user data.
12. Verify version-accurate APIs: reactive `ServerHttpSecurity`, never Servlet `HttpSecurity`.

## 13. Self-Assessment Questions

**Question 1.** Limit is 1, A is logged in. B logs in with the right password. How does the default reactive policy respond?

**Answer:** B can log in, and the least recently used session is invalidated to maintain the limit; typically A is revoked when only A existed beforehand.

**Question 2.** How do you keep session A and reject B?

**Answer:** Configure `maximumSessions(SessionLimit.of(1))` with `maximumSessionsExceededHandler(new PreventLoginServerMaximumSessionsExceededHandler())` inside `ServerHttpSecurity.sessionManagement(...).concurrentSessions(...)`.

**Question 3.** Why is B redirected to the login page under PREVENT instead of HTTP 401?

**Answer:** This is a form-login flow. The handler preventing new sessions raises an authentication/session error, and the form failure handler can redirect to login error. HTTP responses depend on the authentication mechanism.

**Question 4.** How many sessions do two tabs in the same browser count as?

**Answer:** Usually one if they share the same session cookie/`WebSession`, even with two visible windows.

**Question 5.** Why can using `InMemoryReactiveSessionRegistry` alone fail when deploying 4 pods?

**Answer:** Each node keeps its own registry, unaware of all sessions in the system; a properly distributed registry/store and concurrency control are needed.

**Question 6.** A user logs out properly yet the registry still thinks the slot is occupied. What should be checked?

**Answer:** Session invalidation, `WebSessionStore`, registry record cleanup, timeout events, and principal mapping. Deleting the cookie client-side alone is insufficient.

**Question 7.** Why does "at most one `WebSession`" not mean "at most one JWT"?

**Answer:** JWTs can be issued and verified independently of `WebSession`/`ReactiveSessionRegistry`. A dedicated token issuance/revocation policy is needed to limit tokens or devices.

## 14. Official Documentation

- [Spring Security — Reactive Concurrent Sessions Control](https://docs.spring.io/spring-security/reference/reactive/authentication/concurrent-sessions-control.html)
- [Spring Security — ServerHttpSecurity.SessionManagementSpec.ConcurrentSessionsSpec](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/config/web/server/ServerHttpSecurity.SessionManagementSpec.ConcurrentSessionsSpec.html)
- [Spring Security — SessionLimit API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/authentication/SessionLimit.html)
- [Spring Security — ReactiveSessionRegistry API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/core/session/ReactiveSessionRegistry.html)
- [Spring Security — PreventLoginServerMaximumSessionsExceededHandler API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/authentication/PreventLoginServerMaximumSessionsExceededHandler.html)
- [Spring Security — InvalidateLeastUsedServerMaximumSessionsExceededHandler API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/authentication/InvalidateLeastUsedServerMaximumSessionsExceededHandler.html)
- [Spring Security — Authentication and Logout in WebFlux](https://docs.spring.io/spring-security/reference/reactive/authentication/logout.html)
- [Spring Security — CSRF for WebFlux](https://docs.spring.io/spring-security/reference/reactive/exploits/csrf.html)
- [Spring Security — Reactive Security Configuration](https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html)
- [Spring Session — WebSession Integration](https://docs.spring.io/spring-session/reference/web-session.html)
