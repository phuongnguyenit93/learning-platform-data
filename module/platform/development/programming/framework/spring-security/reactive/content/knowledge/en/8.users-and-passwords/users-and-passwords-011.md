# Password Changes, Session Revocation, and Handling Changed Account State — Spring Security Reactive

## 1. Objectives and Core Problem

In a **Spring WebFlux + Spring Security** application, updating a password in the database is an important event, yet **does not automatically ensure** all browsers, devices, login sessions, and prior access tokens become invalid. Likewise, locking an account or revoking a role does not mean `SecurityContext`s already stored in sessions automatically reload `UserDetails`.

After this lesson, you should be able to:

1. Design a password-change flow that verifies identity, checks the old password, persists the new password via `PasswordEncoder`, and notifies safely.
2. Distinguish **rejecting the old password on new logins** from **revoking already-issued sessions/cookies or tokens**.
3. Handle **the current WebSession**, **all registered sessions**, **JWT access tokens**, **refresh tokens**, and changed account/role state with matching mechanisms.
4. Understand reactive APIs such as `ReactiveUserDetailsService`, `ReactiveSessionRegistry`, `WebSessionStore`, `ReactiveSecurityContextHolder`, and `WebSessionServerLogoutHandler`.
5. Run a Java 17+ WebFlux example verifying that the new password takes effect, locked users can no longer log in, and a new CSRF token is generated after WebSession invalidation.

**Design principle:** credential changes and access changes are related events with different lifecycles. To revoke access effectively on subsequent requests, identify where authentication state is stored and where validity is checked.

## 2. Distinguishing Five Things That May Still Remain Valid

| Component | What Does It Hold? | Does Changing Password or Locking Account Invalidate It Automatically? |
| --- | --- | --- |
| **Password hash in user store** | One-way encoded value compared against passwords at authentication | Updates when saved properly; old password must fail on **the next authentication** |
| **HTTP Basic credentials** | Username/password re-sent by client on every request | If the server checks the updated user store per request, the old password is rejected; not a login session |
| **WebSession and SecurityContext** | Session ID/cookie plus server-stored authentication | **Not necessarily**; old sessions may retain previously authenticated principal and authorities |
| **JWT access token** | Signed claims such as subject, scope, expiration | **Not revoked automatically** merely because password hash changed; resource servers typically verify signature/time/issuer |
| **Refresh token / OAuth2 login at IdP** | Authority to request new access tokens or an identity-provider session | Must use token store / authorization server / IdP revocation; app logout may not log out of the IdP |

**Crucial distinction:** Spring Security reactive uses `Reactor Context` to supply `SecurityContext` along a request's processing chain. That is not a long-lived session store. To persist context **across requests**, a `ServerSecurityContextRepository` such as `WebSessionServerSecurityContextRepository` must save/read it. For pure Bearer JWT APIs, the security context is normally reconstructed from the token on each request without storing an authentication session.

## 3. A Lifecycle Diagram

~~~text
User is logged in on devices A and B
       |                             |
       v                             v
WebSession A + SecurityContext   WebSession B + SecurityContext
       |                             |
       +------------+----------------+
                    |
User submits valid password change
                    |
                    v
Verify current password / recent authentication
                    |
                    v
Hash new password -> persist durably -> increment securityVersion
                    |
            +-------+-----------------------+
            |                               |
            v                               v
Invalidate sessions to revoke        Revoke refresh tokens / JWT issuance points
            |                               |
            v                               v
Next request requires fresh login    Old JWT: depends on TTL & verification check
            |
            v
Check fresh account state at request boundary
            |
      Enabled, locked, roles, tenant, version...
~~~

This is a conceptual architecture. Fetching all sessions, updating passwords, and revoking tokens may span different services; a single database transaction does not automatically cover all of them. When guaranteed revocation is required, maintain **shared revocation state** checked at request time, or a coordination flow recoverable from partial step failures.

## 4. Safe Password Change Flow

### 4.1. Accepting the Right HTTP Method and Subject

A typical endpoint uses `POST /account/password` or `PUT /account/password`. Never use GET to change passwords, lock users, or log out because GET can be triggered unintentionally by browsers, crawlers, caches, or prefetching.

Requests must come from the currently authenticated principal; take the name/id from the Spring Security-provided `Authentication`, **never trust a client-supplied username to pick the target account**. Depending on sensitivity, require **recent re-authentication** or MFA even when the current session is valid.

For cookie/session-based web UIs, require CSRF tokens on state-changing requests. Spring Security WebFlux enables CSRF protection by default; `WebSessionServerCsrfTokenRepository` normally holds tokens in WebSession. A stateless Bearer API has different properties, yet only consider disabling CSRF after evaluating cookies and automatic browser credential sending.

### 4.2. Verifying the Old Password

Load the current user from a trusted data source. Use:

~~~java
boolean oldPasswordMatches =
        passwordEncoder.matches(currentPassword, account.passwordHash());
~~~

This is a **snippet inside a service**; `currentPassword`, `account`, and `passwordEncoder` must be declared. Never compare plaintext against a hash with `String.equals`, and never decrypt a hash to recover the old password. Password hashes must come from an appropriate algorithm via `PasswordEncoder`, such as `PasswordEncoderFactories.createDelegatingPasswordEncoder()`.

However, if password resets via email/recovery tokens lack an old password, use a separate **password reset** workflow: single-use, time-limited tokens bound to the right account with replay protection and post-success token invalidation. Never fake "old password matched" to reuse the same flow.

### 4.3. Validating the New Password

Validate the new password before saving:

- Non-null/non-empty, meets length policy, and differs from the current password; password history may also be checked per policy.
- Favor length, passphrases, breach screening, and password-manager compatibility. Do not rely solely on hard-to-remember composition rules like "uppercase + special character".
- For high-assurance environments, check common/compromised password lists. Spring Security provides `ReactiveCompromisedPasswordChecker` for suitable integrations; handle timeouts and never log plaintext.
- Rate-limit and cap verification attempts for the old password. Never leak extra sensitive information in responses.

**Never store plaintext passwords.** When using `DelegatingPasswordEncoder`, stored hashes may carry an encoder id prefix like `{bcrypt}`; never strip this prefix when saving/reading with the same encoder.

### 4.4. Persisting Changes Consistently

Recommended flow in real systems:

1. Verify the current user and old password; ensure the account is not locked or barred from self-service password changes.
2. Generate the new hash and update the record with concurrency control via transactions or version-based optimistic locking.
3. Increment `securityVersion`/`credentialsChangedAt` **in the same write** so subsequent requests can recognize stale credentials.
4. After commit succeeds, trigger revocation of required sessions, refresh tokens, remembered devices, or tokens per policy.
5. Record an audit event (user id, timestamp, request id, request origin; **never log passwords or tokens**) and notify the account owner.
6. If a remote revocation step fails, mark it for retry and rely on request-time version/denylist checks to eliminate any lingering access window.

Never delete sessions **before confirming the password update committed** if that logs users out while the password stayed unchanged. Yet never claim "logged out of all devices" before revoking the corresponding sessions/tokens.

## 5. Changing Passwords Does Not Automatically Invalidate Authenticated Sessions

### 5.1. WebSession and SecurityContext

With form login or session-based mechanisms, `WebSessionServerSecurityContextRepository` can store authentication inside WebSession. After login, subsequent requests carrying the session cookie can reuse that stored context **without re-checking the password in the database**.

Suppose at 09:00 a user logs in with `ROLE_ADMIN`. At 10:00 another admin removes their `ADMIN` role. If a request at 10:01 simply reads authorities from the stale SecurityContext, the user risks retaining old admin access. The same happens when an account is locked or its password changes.

**Mitigation:** revoke sessions and/or verify fresh account state on subsequent requests. Updating only the database hash is insufficient for contexts authenticated prior to the change.

### 5.2. Invalidating the Current WebSession

Inside a reactive handler with `ServerWebExchange exchange`:

~~~java
return exchange.getSession()
        .flatMap(WebSession::invalidate);
~~~

This is a **snippet inside a `Mono<Void>`-returning method**, requiring `import org.springframework.web.server.WebSession`. It invalidates only **the current request's WebSession**, not every browser session or JWT belonging to the same user.

For logout via Spring Security reactive, you can configure logout handlers:

~~~java
DelegatingServerLogoutHandler handlers =
        new DelegatingServerLogoutHandler(
                new SecurityContextServerLogoutHandler(),
                new WebSessionServerLogoutHandler());

http.logout(logout -> logout.logoutHandler(handlers));
~~~

This is an **additional configuration snippet inside the `SecurityWebFilterChain` bean method**, requiring imports of all three classes from `org.springframework.security.web.server.authentication.logout`. `SecurityContextServerLogoutHandler` clears the context via the repository; `WebSessionServerLogoutHandler` invalidates the current WebSession. Per reactive documentation, logout defaults to **POST /logout** with a CSRF token when CSRF is enabled. Never use GET logout for state-changing actions.

### 5.3. Log Out One Session or All Sessions?

| Product Requirement | What Must Be Done |
| --- | --- |
| "Log out of this device" | Clear SecurityContext and invalidate current WebSession; clear client cookies as appropriate |
| "Log out of all devices" | Find and revoke all sessions for the principal from the appropriate registry/store, including sessions on other nodes |
| "Password change forces everyone to log in again" | Update password + version, then revoke related sessions/tokens; ensure new requests check revocation state |
| "Lock account immediately" | Block new authentications and reject old sessions/tokens via revocation or per-request account-state checks |
| "Only remove a role" | Do not only edit the database; refresh authorities or invalidate context and force re-authentication |

Never confuse **application** logout with **Identity Provider** logout when using OAuth2/OIDC login.

## 6. Revoking All Reactive Sessions via Session Registry

Spring Security offers **Reactive Concurrent Sessions Control** and `ReactiveSessionRegistry` (Spring Security 6.3+). When enabled in a supported manner, sessions from mechanisms such as form login, OAuth2 login, and HTTP Basic can be registered via success handlers. `InMemoryReactiveSessionRegistry` is a simple single-process implementation.

Example registry configuration **for a session-based app** (do not apply to Section 9's stateless Basic example):

~~~java
@Bean
ReactiveSessionRegistry reactiveSessionRegistry() {
    return new InMemoryReactiveSessionRegistry();
}

@Bean
SecurityWebFilterChain webSecurity(ServerHttpSecurity http) {
    return http
            .authorizeExchange(ex -> ex.anyExchange().authenticated())
            .formLogin(Customizer.withDefaults())
            .sessionManagement(sessions -> sessions
                    .concurrentSessions(concurrency -> concurrency
                            .maximumSessions(SessionLimit.of(2))))
            .build();
}
~~~

This snippet lives inside a `@Configuration` class with proper imports and is **not a complete project**. `SessionLimit.of(2)` illustrates a two-session cap. If an app only wants to **track and revoke** without capping session count, use an unlimited limit setting per your library version's API; never assume merely declaring the registry bean registers every session by itself.

Once the registry actually tracks user sessions, Spring Security's docs illustrate revoking them:

~~~java
final class SessionRevocationService {
    private final ReactiveSessionRegistry registry;
    private final WebSessionStore store;

    SessionRevocationService(
            ReactiveSessionRegistry registry, WebSessionStore store) {
        this.registry = registry;
        this.store = store;
    }

    Mono<Void> revokeRegisteredSessions(String username) {
        return registry.getAllSessions(username)
                .flatMap(session -> session.invalidate()
                        .then(store.removeSession(session.getSessionId()))
                        .then(registry.removeSessionInformation(session.getSessionId()))
                        .then())
                .then();
    }
}
~~~

This is an **example class requiring package/imports and bean wiring**, not a standalone buildable module. Imports:

~~~java
import org.springframework.security.core.session.ReactiveSessionRegistry;
import org.springframework.web.server.session.WebSessionStore;
import reactor.core.publisher.Mono;
~~~

Explanation:

1. `getAllSessions(username)` retrieves sessions the registry **currently tracks** for the principal; ensure the principal key matches how sessions were registered.
2. `session.invalidate()` marks the session invalidated in the registry.
3. `store.removeSession(session.getSessionId())` removes the actual session from the backing store.
4. `registry.removeSessionInformation(...)` cleans up the registry entry; with certain Spring Session-backed implementations, verify exact behavior before use.
5. `then()` ensures the publisher completes only after all reactive operations finish; merely **creating a Mono without subscribing/returning** performs no action.

**Limitation:** In-memory registries and `WebSessionStore` only cover the current instance. In clustered/multi-instance deployments, use a shared session store and synchronized registry or an appropriate Spring Session-backed registry. If any session was not registered, the registry cannot revoke an unknown session. Test across multiple nodes.

Official docs warn that concurrent-session control has no automatic visibility into sessions at an OAuth2 Identity Provider; application logout may require separate revocation calls to the IdP.

## 7. JWT, Refresh Tokens, and Stateless Authentication

### 7.1. Why Does Changing a Password Not Automatically Invalidate JWTs?

JWT access tokens carry signed claims and an expiration timestamp. A Spring Security reactive resource server typically validates signature, `exp`, `nbf`, and issuer per configuration. **It does not by default query the latest password hash on every JWT decode.** Thus already-issued JWTs **can remain valid until expiration** unless an additional revocation mechanism is implemented.

Three common approaches:

1. **Short access-token TTL + revocable refresh tokens:** cap how long old tokens survive; on password change/account lock, revoke the account's refresh tokens.
2. **Denylist by `jti` or token identifier:** each request checks a set of revoked tokens with TTLs up to token expiration; requires a shared store and an error-handling policy when the store fails.
3. **Per-user version/epoch:** embed `securityVersion` or `credentialsChangedAt` in claims when issuing tokens; the resource server checks the token's version against current records or an invalidatable cache. When the version advances, old tokens are rejected.

Some systems choose **opaque tokens + introspection**, letting the auth server decide validity centrally at the cost of network/cache overhead. If near-instant revocation is needed, you cannot rely solely on long-lived signed JWTs validated offline.

### 7.2. Watch Out for Races and Caching

When incrementing `securityVersion` and updating the password in the same transaction, newly issued tokens must carry the new version. If token issuers or resource servers cache account state, bound cache staleness or publish invalidation events. When a request is already mid-flight during an account lock, do not assume an in-progress request past its auth check gets aborted; evaluate sensitive business operations and re-check authorization close to critical commits when needed.

Never keep an unbounded permanent blacklist for all tokens; store `jti` with matching TTLs and protect the lookup store. Define an explicit fail-closed/fail-open strategy when the state store is unreachable, calibrated to API risk.

### 7.3. Refresh Tokens and IdPs

After a password change:

- Revoke refresh tokens in the server store or call the OAuth2 provider's revocation endpoint.
- With refresh token rotation, block reuse of old tokens and detect replay.
- With OIDC/OAuth2 login, logging out of the app's WebSession does not automatically end the IdP session; consider RP-initiated logout or back-channel logout if supported.
- If the IdP owns passwords, password changes must happen at the IdP—never write a change into your app database and assume all SSO sessions were revoked.

## 8. Changed Account State: Enabled, Locked, Roles, and Tenants

### 8.1. Blocking New Authentications

`ReactiveUserDetailsService` loads `UserDetails` for the authentication manager to evaluate the current user. Typical flags on `UserDetails` include:

- `isEnabled()`: whether the account is allowed to operate.
- `isAccountNonLocked()`: whether the account is unlocked.
- `isAccountNonExpired()`: whether the account has not expired.
- `isCredentialsNonExpired()`: whether credentials have not expired.

If the data store updates these flags and the manager reloads fresh user data, **new logins** are rejected under the updated state. Never treat that as proof that old sessions were invalidated.

### 8.2. Blocking Stale Permissions on Subsequent Requests

Suppose at 10:00 a user loses their admin role while their session still holds `ROLE_ADMIN`. Three solutions exist:

1. **Revoke sessions when roles/locks change** and force re-login.
2. **Custom authorization** checking current permissions from a trusted reactive source on sensitive endpoints.
3. **Security version** stored in context/tokens and compared against the current account version on each protected request; on mismatch, reject and require re-authentication.

Request-boundary checks must sit in the right security chain and work with Reactor Context. Never rely on Servlet-style `ThreadLocal` to read authentication. For tenant or ownership changes, service/data-layer checks are also essential; URL authorization alone cannot protect every business object.

### 8.3. Do Not Track Users Solely by Name

Usernames can change or be reused; in real systems, use an **immutable user ID** to tie together sessions, tokens, and audit records. When `ReactiveSessionRegistry.getAllSessions(...)` uses a username, make sure the registry's principal key matches how sessions were registered. Otherwise, reporting "no sessions found" may just be a key mismatch.

### 8.4. State Transitions and Recommended Actions

| Event | New Authentications | Old Sessions/Tokens | Recommended Action |
| --- | --- | --- | --- |
| Password changed | Old password must fail | May still be valid | Revoke per policy, check version |
| Account disabled/locked | Rejected if service reads fresh state | May still be valid | Revoke immediately, add per-request account-state check |
| `ADMIN` role removed | Auth may still succeed with reduced roles | Old context/tokens may retain role | Refresh authorities or revoke; check authoritative permissions |
| User deleted | No new logins possible | Old sessions/tokens may linger | Revoke all credentials and clean up properly |
| Email password reset | Old password replaced if reset succeeds | Depends on policy | Revoke refresh tokens/sessions, audit and notify |
| MFA factor changed | Password not necessarily changed | High-assurance sessions may linger | Reassess authentication assurance, revoke sensitive sessions |

## 9. Runnable Example: Changing Passwords and Locking Accounts with WebFlux

This example uses **HTTP Basic for API requests** so you can see clearly that password changes/disabling take effect on the next authentication. We **do not store SecurityContext in sessions** for HTTP Basic; a separate `WebSession` is still used for CSRF and invalidated after changing the password. Therefore, it **is not a demo of revoking all cookie-based login sessions**; Section 6 covers that capability.

### 9.1. Project Setup

Create a Maven project with Java **17+**, group `com.example`, artifact `account-state-demo`, and dependencies **Spring Reactive Web** and **Spring Security** on [Spring Initializr](https://start.spring.io/). Complete minimal `pom.xml` (Spring Boot 4.1.2):

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
    <artifactId>account-state-demo</artifactId>
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

Do not add `spring-boot-starter-web`/MVC and do not override Spring Security or Reactor versions manually; Boot's BOM manages compatible libraries.

### 9.2. Complete Java Code

Create `src/main/java/com/example/accountstate/AccountStateDemoApplication.java`:

~~~java
package com.example.accountstate;

import java.security.Principal;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpMethod;
import org.springframework.http.ResponseEntity;
import org.springframework.security.authentication.ReactiveAuthenticationManager;
import org.springframework.security.authentication.UserDetailsRepositoryReactiveAuthenticationManager;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.ReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.context.NoOpServerSecurityContextRepository;
import org.springframework.security.web.server.csrf.CsrfToken;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ServerWebExchange;
import org.springframework.web.server.WebSession;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

@SpringBootApplication
@EnableWebFluxSecurity
public class AccountStateDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(AccountStateDemoApplication.class, args);
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    Accounts accounts(PasswordEncoder encoder) {
        return new Accounts(encoder);
    }

    @Bean
    ReactiveUserDetailsService users(Accounts accounts) {
        return username -> Mono.defer(
                () -> Mono.justOrEmpty(accounts.find(username)));
    }

    @Bean
    ReactiveAuthenticationManager authenticationManager(
            ReactiveUserDetailsService users, PasswordEncoder encoder) {
        UserDetailsRepositoryReactiveAuthenticationManager manager =
                new UserDetailsRepositoryReactiveAuthenticationManager(users);
        manager.setPasswordEncoder(encoder);
        return manager;
    }

    @Bean
    SecurityWebFilterChain security(
            ServerHttpSecurity http, ReactiveAuthenticationManager manager) {
        return http
                .authenticationManager(manager)
                .securityContextRepository(
                        NoOpServerSecurityContextRepository.getInstance())
                .authorizeExchange(ex -> ex
                        .pathMatchers(HttpMethod.GET, "/csrf").permitAll()
                        .pathMatchers(HttpMethod.POST, "/account/password")
                            .authenticated()
                        .pathMatchers(HttpMethod.POST, "/admin/lock/**")
                            .hasRole("ADMIN")
                        .anyExchange().authenticated())
                .httpBasic(Customizer.withDefaults())
                .formLogin(form -> form.disable())
                .build();
    }

    record ChangePassword(String oldPassword, String newPassword) { }

    record State(String hash, boolean disabled, String role, long version) { }

    static final class Accounts {
        private final PasswordEncoder encoder;
        private final Map<String, State> data = new ConcurrentHashMap<>();

        Accounts(PasswordEncoder encoder) {
            this.encoder = encoder;
            data.put("learner", new State(
                    encoder.encode("learnerOld123!"), false, "USER", 0));
            data.put("admin", new State(
                    encoder.encode("adminSecret123!"), false, "ADMIN", 0));
        }

        synchronized UserDetails find(String username) {
            State state = data.get(username);
            if (state == null) {
                return null;
            }
            return User.withUsername(username)
                    .password(state.hash())
                    .roles(state.role())
                    .disabled(state.disabled())
                    .build();
        }

        synchronized boolean change(String username, ChangePassword input) {
            State old = data.get(username);
            if (old == null || old.disabled() || input == null
                    || input.oldPassword() == null
                    || input.newPassword() == null
                    || input.newPassword().length() < 12
                    || !encoder.matches(input.oldPassword(), old.hash())
                    || encoder.matches(input.newPassword(), old.hash())) {
                return false;
            }
            data.put(username, new State(
                    encoder.encode(input.newPassword()),
                    false, old.role(), old.version() + 1));
            return true;
        }

        synchronized boolean lock(String username) {
            State old = data.get(username);
            if (old == null) {
                return false;
            }
            data.put(username, new State(
                    old.hash(), true, old.role(), old.version() + 1));
            return true;
        }
    }

    @RestController
    static final class Api {
        private final Accounts accounts;

        Api(Accounts accounts) {
            this.accounts = accounts;
        }

        @GetMapping("/csrf")
        Mono<Map<String, String>> csrf(ServerWebExchange exchange) {
            Mono<CsrfToken> token =
                    exchange.getAttribute(CsrfToken.class.getName());
            return token.map(value -> Map.of(
                    "headerName", value.getHeaderName(),
                    "token", value.getToken()));
        }

        @GetMapping("/me")
        Mono<String> me(Principal principal) {
            return Mono.just("ME:" + principal.getName());
        }

        @PostMapping("/account/password")
        Mono<ResponseEntity<String>> changePassword(
                Principal principal,
                @RequestBody ChangePassword input,
                ServerWebExchange exchange) {
            return Mono.fromCallable(
                    () -> accounts.change(principal.getName(), input))
                .subscribeOn(Schedulers.boundedElastic())
                .flatMap(changed -> changed
                    ? exchange.getSession()
                        .flatMap(WebSession::invalidate)
                        .thenReturn(ResponseEntity.ok("PASSWORD_CHANGED"))
                    : Mono.just(ResponseEntity.badRequest()
                        .body("PASSWORD_NOT_CHANGED")));
        }

        @PostMapping("/admin/lock/{username}")
        Mono<ResponseEntity<String>> lock(@PathVariable String username) {
            return Mono.fromSupplier(() -> accounts.lock(username))
                    .map(ok -> ok
                        ? ResponseEntity.ok("ACCOUNT_LOCKED")
                        : ResponseEntity.notFound().<String>build());
        }
    }
}
~~~

**Meaning of the code:**

- `Accounts` stores password hashes via `DelegatingPasswordEncoder`, keeps a `disabled` flag, and increments `version` when password/state changes. Data lives only in RAM; restarting the app restores demo accounts, so it is **not a production repository**.
- `ReactiveUserDetailsService` returns fresh `UserDetails` whenever the manager needs to authenticate. Once `disabled` flips, subsequent Basic authentications are rejected.
- `UserDetailsRepositoryReactiveAuthenticationManager` uses the same `PasswordEncoder` to verify passwords. Never compare passwords manually in controllers.
- `NoOpServerSecurityContextRepository` avoids saving Basic authentication across requests. This exemplifies an API re-checking credentials per request; `WebSession` may still be used separately for CSRF.
- `POST /account/password` takes the username from the authenticated `Principal`, never trusting a username in the payload. After a successful update, it invalidates the current WebSession—which is unrelated to revoking all devices or JWTs.
- `POST /admin/lock/{username}` is callable only with `ROLE_ADMIN`. Locked/disabled state takes effect on subsequent requests using that account in the demo.
- `Schedulers.boundedElastic()` runs the `PasswordEncoder.matches/encode` portion of the password change, keeping that CPU cost off the event loop. In production, use a reactive repository, concurrency/transaction mechanisms, and an appropriately tuned scheduler.
- Sample passwords sit in source for easy testing; **never deploy them in real environments**. Never log JSON requests containing passwords.

**Limitation to understand:** because Basic is used, username/password credentials are still re-sent when clients make requests. WebSession invalidation in the example mainly affects the session used for CSRF; to demonstrate authenticated login cookies persisting across requests and revoking multiple sessions, use the session model in Sections 5–6.

### 9.3. Running the Application

In the directory containing `pom.xml`:

~~~bash
./mvnw spring-boot:run
~~~

On Windows use `.\mvnw.cmd spring-boot:run`; without a Maven wrapper, use `mvn spring-boot:run`. The app listens on `http://localhost:8080` unless the default port was changed.

Try a non-state-changing GET:

~~~bash
curl -i -u 'learner:learnerOld123!' http://localhost:8080/me
curl -i -u 'learner:wrong' http://localhost:8080/me
~~~

Expected results: first request HTTP **200**, body `ME:learner`; second request HTTP **401**. On PowerShell, you can use `curl.exe` to avoid the `Invoke-WebRequest` alias.

### 9.4. Changing Passwords While Preserving CSRF Protection

Spring Security reactive enables CSRF by default. Never disable CSRF just to make `POST` convenient. First fetch the token and session cookie:

~~~bash
curl -i -c cookies.txt http://localhost:8080/csrf
~~~

The response body contains JSON with `headerName` and `token`; normally the header to send is `X-CSRF-TOKEN`. Save **the actual token value from the response** and use the newly created cookie file. Because the token is stored in WebSession, the next request must send **the matching cookie** paired with that token; sending a token without its paired cookie will fail verification.

Next (replace `TOKEN_FROM_CSRF_RESPONSE` with the received token):

~~~bash
curl -i -b cookies.txt \
  -u 'learner:learnerOld123!' \
  -H 'Content-Type: application/json' \
  -H 'X-CSRF-TOKEN: TOKEN_FROM_CSRF_RESPONSE' \
  -d '{"oldPassword":"learnerOld123!","newPassword":"learnerNew123!"}' \
  http://localhost:8080/account/password
~~~

In Windows terminals that do not support backslash line continuations, put the entire command on **one line** and quote JSON appropriately for your shell. Expected result is **HTTP 200** with body `PASSWORD_CHANGED`. In this response, the current WebSession has been invalidated; the old CSRF token/cookie is no longer valid for subsequent POST requests.

Verify old password and new password:

~~~bash
curl -i -u 'learner:learnerOld123!' http://localhost:8080/me
curl -i -u 'learner:learnerNew123!' http://localhost:8080/me
~~~

Expected results: old password **401**, new password **200** with body `ME:learner`. This happens because Basic performs **fresh authentication on every request**, not as proof that all login sessions were revoked.

### 9.5. Locking an Account and Observing

Call `GET /csrf` again to obtain a fresh token/cookie after the old session was invalidated; to reuse the same command line, save into `cookies.txt` and swap the token placeholder. With Basic admin user holding `ROLE_ADMIN`:

~~~bash
curl -i -b cookies.txt \
  -u 'admin:adminSecret123!' \
  -H 'X-CSRF-TOKEN: TOKEN_FROM_NEW_CSRF_RESPONSE' \
  -X POST http://localhost:8080/admin/lock/learner
~~~

Expected result **HTTP 200** with body `ACCOUNT_LOCKED`. Now:

~~~bash
curl -i -u 'learner:learnerNew123!' http://localhost:8080/me
~~~

Expected result **401** because the account is disabled. Do not lock the admin account in the demo unless intentionally testing how the system cuts off admin access. Since state lives only in RAM, restarting restores the initial credentials.

### 9.6. Why Is This Example Still Not Production-Ready?

The example lacks a database, durable auditing, rate limiting, MFA, a full password policy, distributed sessions, reset tokens, refresh tokens, event-driven revocation, and secret key management. It lets you observe **the mechanism for checking fresh UserDetails**. When moving to real deployment, add transactions/optimistic locking, concurrency caps, data-store error handling, and parallel tests for password changes and logins.

## 10. Production Deployment Designs by Authentication Model

### 10.1. WebFlux + Form Login + WebSession Cookie

- Use an appropriate `ServerSecurityContextRepository` (typically `WebSessionServerSecurityContextRepository`) to persist authentication across requests.
- When a user logs out themselves, clear SecurityContext and invalidate the current WebSession via logout handlers.
- When a password changes, an account is locked, or permissions change, **find all registered sessions and revoke them**; on sensitive endpoints, also check the current account version/roles.
- With multiple instances, use a shared session store and a Spring Session-compatible registry; never rely on a single-node map.
- Keep CSRF for state-changing requests; set `Secure`/`HttpOnly`/`SameSite` on cookies as appropriate.
- After logout or password change, old session cookies no longer grant access; prompt users to log in again.

### 10.2. HTTP Basic APIs

- Each request sends username/password; the manager must read current user state.
- Old passwords are rejected on the next authentication; disabled accounts are rejected as well.
- There is no "Basic login JWT/session" to revoke if the app does not persist SecurityContext in a session.
- If Basic is used in browsers, watch for CSRF risk because browsers automatically resend cached credentials.
- Prefer suitable token mechanisms for modern systems rather than sending passwords on every request unnecessarily.

### 10.3. Bearer JWT APIs

- Resource servers verify signature, issuer, validity window, and configured claims.
- Password/account updates do not rewrite JWTs already stored on clients.
- Use short TTLs + refresh revocation, or check token version/denylist per request; near-instant revocation requires a shared state store or introspection.
- If roles/scopes inside a token become stale, re-evaluate permissions or revoke the token; never trust stale claims indefinitely.
- Audit both auth servers and resource servers, since changing a password in one service is insufficient if other services still trust old tokens.

### 10.4. OAuth2/OIDC and External Session Management

- Logging out at the relying party may only clear the app session; the IdP may still hold an SSO session.
- Use logout/revocation features supported by the identity provider, with proper callback and request validation.
- If passwords are managed by the IdP, password change/reset flows must happen at the IdP.
- Verify effects on refresh tokens, device sessions, browser sessions, and sibling apps sharing the IdP.

## 11. Common Real-World Pitfalls

| Symptom | Possible Cause | How to Check |
| --- | --- | --- |
| Old password still logs in | Hash not committed, stale user cache, wrong data store, login manager not reading fresh state | Check transactions, source of truth, caches, and authentication manager |
| Password changed yet an already open tab keeps access | SecurityContext cached in WebSession | Inspect session repository and invalidation logic |
| Deleting cookies still leaves Bearer tokens working | JWT is independent of cookies | Check token TTL, `jti`, version/introspection |
| Locked user still has `ROLE_ADMIN` | Stale session/token retains authorities | Revoke context/tokens or check current permissions per request |
| POST password change returns 403 | Missing CSRF token/cookie or user lacks required role | Inspect `CsrfWebFilter`, challenge, and authorization rules |
| "Revoke all sessions" affects only one node | Per-instance in-memory registry/store | Use a distributed store and synchronized principal index |
| Logged out of app yet automatically re-logged in | IdP SSO session still active | Inspect RP/IdP logout and refresh tokens |
| New password works yet UI reports "revocation failed" | Password committed, a remote revoke step failed | Audit, idempotent retries, and per-request version checks |
| 401 instead of 403 after locking an account | Basic authentication fails before authorization | Distinguish authentication failure from role denial |

### 11.1. Cache Warning

A service might cache `UserDetails` or authorization decisions. When password/role/disabled state changes, handle invalidation properly. Long cache TTLs can preserve wrong permissions for minutes; if sensitive access requires stronger consistency, check fresh records or versions on incoming requests.

### 11.2. Race Conditions

If request A authenticates with the old password **at the same time** request B changes the password, A may pass authentication before the update completes. You cannot assume every in-flight request gets aborted; define clear guarantees such as "every new request after commit must check the new version", and for sensitive operations re-verify authorization close to the business commit point.

### 11.3. Never Swallow Revocation Errors

Avoid this pattern:

~~~java
return updatePassword()
        .then(revokeAllSessions())
        .onErrorResume(error -> Mono.empty());
~~~

This snippet uses hypothetical methods. It hides real failures, letting the API report success even though revocation did not happen. Separate password commit state from revocation state, audit and retry with bounds; when strong guarantees are required, pair with request-side version checks.

## 12. Test Plan

Do not test only one successful login. Minimum test suite:

1. **Valid password change:** old password verified, new hash saved, old password fails, new password succeeds.
2. **Invalid password change:** wrong old password or invalid new password; neither hash nor `securityVersion` updates.
3. **CSRF:** POST password change missing a valid token/cookie is blocked under session/cookie authentication.
4. **Current session revocation:** after logout/password change per policy, old session cookies no longer grant access.
5. **Other device revocation:** log in on devices A/B, change password on A; if policy mandates all-session revocation, B must be forced to re-authenticate.
6. **Account disabled/locked:** new logins fail; previously issued sessions/tokens are also blocked within the documented window.
7. **Role changed:** `ROLE_ADMIN` removed, privileged requests are denied even if old sessions/tokens still exist.
8. **JWT/refresh:** old access tokens obey TTL/version/denylist, and revoked refresh tokens cannot mint new access tokens.
9. **Multi-node:** revocations on node A become visible to node B within allowed propagation lag.
10. **Mid-flight failures:** password update succeeds while a backend revocation times out; retries and auditing preserve access control.
11. **Races:** concurrent password changes or lock + login; outcomes remain consistent via versions/transactions.
12. **Sensitive data:** passwords/tokens never appear in server logs, metric labels, tracing tags, URL queries, or client error messages.

With WebFlux, use `WebTestClient`, Spring Security test support, and `StepVerifier` for publishers. When testing "log out all devices", use separate cookie jars for distinct clients rather than sharing one cookie across two windows.

## 13. Self-Check Questions

**Question 1.** The password changed in the database, yet an old WebSession cookie still accesses protected routes. Did the password update fail?

**Answer:** Not necessarily. Login sessions may rely on a stored SecurityContext without re-checking the password on each request. You must revoke sessions or check security versions/current account state.

**Question 2.** How do HTTP Basic and JWT differ after a password change?

**Answer:** Basic typically verifies username/password on every request, so the old password is rejected as soon as the user store updates. JWTs can be validated offline without reading the password hash; TTL/revocation/versioning is needed to limit how long old tokens stay valid.

**Question 3.** Does `WebSessionServerLogoutHandler` delete all of a user's sessions?

**Answer:** No. It invalidates only the WebSession processing that logout; covering all sessions requires an appropriate registry/store and verifying coverage scope.

**Question 4.** Why is removing a role in the database alone insufficient?

**Answer:** Existing SecurityContexts or JWTs can retain old authorities. You must refresh or revoke them, or look up current permissions on protected requests.

**Question 5.** Why does a POST password change need CSRF protection when using cookies?

**Answer:** Browsers automatically attach cookies to target sites; attackers can exploit that behavior. CSRF tokens require state-changing requests to carry proof an external page cannot easily obtain.

**Question 6.** If the session registry reports zero sessions, can we be sure the user is logged out everywhere?

**Answer:** No. Some sessions might never have been registered, the registry might not be shared across nodes, or the principal lookup key might mismatch. Ensure the registry/store truly covers all sessions and use request-side revocation checks when strong guarantees are required.

## 14. Official Documentation Sources

- [Spring Security — Reactive Concurrent Sessions Control](https://docs.spring.io/spring-security/reference/reactive/authentication/concurrent-sessions-control.html)
- [Spring Security — Reactive Logout](https://docs.spring.io/spring-security/reference/reactive/authentication/logout.html)
- [Spring Security — CSRF for WebFlux](https://docs.spring.io/spring-security/reference/reactive/exploits/csrf.html)
- [Spring Security — Reactive HTTP Basic Authentication](https://docs.spring.io/spring-security/reference/reactive/authentication/basic.html)
- [Spring Security — Password Storage](https://docs.spring.io/spring-security/reference/features/authentication/password-storage.html)
- [Spring Security API — ReactiveSessionRegistry](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/core/session/ReactiveSessionRegistry.html)
- [Spring Security API — WebSessionServerLogoutHandler](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/authentication/logout/WebSessionServerLogoutHandler.html)
- [Spring Security API — WebSessionServerSecurityContextRepository](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/context/WebSessionServerSecurityContextRepository.html)
- [Spring Security API — UserDetailsRepositoryReactiveAuthenticationManager](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authentication/UserDetailsRepositoryReactiveAuthenticationManager.html)
- [Spring Security — Reactive OAuth2 Resource Server JWT](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/jwt.html)
- [Spring Session — WebSession Integration](https://docs.spring.io/spring-session/reference/web-session.html)
