# Distinguishing User Errors from Account Store or Identity Service Failures

> **Scope:** Spring Security fundamentals, "Security Errors" group. This lesson explains authentication errors caused by credentials/account state versus errors caused by an unavailable database, LDAP, IdP, or dependent service. The hands-on example uses Java 17, Spring Boot 3.3.x, Spring Security 6.x, and Servlet/Spring MVC; the classification principles also apply to other identity mechanisms, with protocol-specific handlers.

## 1. Problem: "Unable to Log In" Does Not Equal "Entered Wrong Password"

When a user fails to log in, the application may have verified that the credentials are invalid; or the system may have been **unable to verify** because the account store or identity provider suffered an outage. These two situations must be distinguished from the error source, even though public messages must both remain concise and safe.

- **Credential error:** username absent after a successful lookup, password does not match the hash, corrupted/expired token, validly rejected grant or credential.
- **Account state error:** locked, disabled, account expired, credentials expired. The system knows the account is currently ineligible to log in; this is neither a connection failure nor necessarily user misbehavior.
- **Account store / identity service error:** database connection lost, exhausted connection pool, query timeout, unreachable LDAP, 5xx from IdP/token endpoint, network error while fetching required JWKS keys. **Insufficient evidence to conclude whether the password was right or wrong.**
- **Configuration/programming error:** no matching `AuthenticationProvider`, misconfigured client/redirect/certificate, user-mapping or schema bug. A system error requiring investigation, not proof of wrong user input.

**Principle:** "account not found" applies only if the lookup **succeeded** and returned empty; "unable to look up account" must be classified as a backend error. Never turn a database timeout into `UsernameNotFoundException` or `BadCredentialsException` just to avoid handling exceptions.

### Why Does Accurate Classification Matter?

If you return "Wrong username or password" while the database is down, users may repeatedly retry, reset passwords, or trip failed-attempt counters and get locked out unfairly. Monitoring may also mistake an outage for credential stuffing. Conversely, revealing "username does not exist" too specifically lets attackers probe accounts (account enumeration). And if the system skips identity verification when the backend fails, it risks **failing open**, which is far worse than login disruption.

## 2. Root-Cause Classification Table

| Verified Situation | Internal Category | What Should Be Concluded? | Action |
| --- | --- | --- | --- |
| Lookup succeeded, username absent | `INVALID_CREDENTIALS` | Identity/credentials rejected | Deny; external message matches wrong password |
| Lookup found user, password hash mismatch | `INVALID_CREDENTIALS` | Invalid credentials | Deny; increment credential-failure metric per policy |
| Account locked / disabled / expired | `ACCOUNT_STATE` | Account ineligible | Deny; recover through a controlled workflow |
| Database connection refused / query timeout | `IDENTITY_DEPENDENCY` | **Cannot verify credentials yet** | Fail closed, alert on outage |
| LDAP server unreachable / bind service timeout | `IDENTITY_DEPENDENCY` | Insufficient evidence on credentials | Track latency/dependency, do not lock users out unfairly |
| IdP returns protocol error `invalid_grant` | `AUTHENTICATION_REJECTED` or flow error by code | Grant rejected; not necessarily wrong password | Analyze grant/flow, return no sensitive details |
| IdP/token endpoint returns `temporarily_unavailable` or 5xx | `IDENTITY_DEPENDENCY` | Identity service failing | Fail closed, monitor, bounded retry if appropriate |
| Expired JWT, wrong signature, wrong issuer/audience | `INVALID_TOKEN` | Invalid token | Usually 401 per Bearer protocol |
| JWKS endpoint timeout when new key is needed | `IDENTITY_DEPENDENCY` | Token not necessarily invalid | Inspect decoder/cache and failing dependency |
| `ProviderNotFoundException` due to provider misconfiguration | `AUTH_CONFIGURATION` | System lacks a supporting provider | Fix configuration, do not blame user |
| Authenticated user missing role/scope | `AUTHORIZATION_DENIED` | Insufficient resource permission | Usually 403, not a login failure |
| Rate-limited due to too many requests | `RATE_LIMITED` | Anti-abuse policy triggered | May return 429, backoff per policy |

HTTP status codes are **response behavior**, not proof of root cause. The same exception can be mapped to different statuses by filters, handlers, or gateways; by default, Spring Security does not guarantee that every database error automatically becomes 503.

## 3. How Spring Security Handles Errors

### 3.1 Username/Password Flow in Servlet

```text
HTTP request + credentials
    |
    v
Authentication filter (e.g. BasicAuthenticationFilter)
    |
    v
AuthenticationManager / ProviderManager
    |
    v
DaoAuthenticationProvider
    |
    +--> UserDetailsService.loadUserByUsername(username)
    |      |
    |      +--> Query OK, no record:
    |      |       UsernameNotFoundException
    |      |       (by default may be masked as BadCredentialsException)
    |      |
    |      +--> Query OK, record found:
    |      |       check account status + PasswordEncoder.matches()
    |      |       success / BadCredentialsException / account-status exception
    |      |
    |      +--> Query failed:
    |              AuthenticationServiceException /
    |              InternalAuthenticationServiceException
    |
    v
Authentication failure handling by filter:
    HTTP Basic -> AuthenticationEntryPoint
    Form login -> AuthenticationFailureHandler
    OAuth2/OIDC -> corresponding handler and protocol
```

`DaoAuthenticationProvider` uses `UserDetailsService` to load `UserDetails`, then checks password and account status. For non-existent usernames, `AbstractUserDetailsAuthenticationProvider` enables `hideUserNotFoundExceptions` by default, so `UsernameNotFoundException` is typically replaced with `BadCredentialsException` just like a wrong password. This reduces user enumeration risk; do not disable it just to show exact errors to the frontend.

### 3.2 What Does Each Exception Mean?

| Class / Exception | Interpretation |
| --- | --- |
| `UsernameNotFoundException` | `UserDetailsService` did not find the username after a valid lookup |
| `BadCredentialsException` | Credentials rejected; **does not prove the username exists** |
| `LockedException`, `DisabledException` | Account is locked or disabled |
| `AccountExpiredException`, `CredentialsExpiredException` | Account or credentials have expired |
| `AuthenticationServiceException` | Service error during authentication |
| `InternalAuthenticationServiceException` | Internal authentication service error, suitable for wrapping certain backend failures |
| `ProviderNotFoundException` | No provider supports the authentication token; usually check configuration |
| `AccessDeniedException` | Access denial in authorization or another protection mechanism; **does not mean wrong password** |

`AuthenticationEntryPoint` handles responses requesting authentication, e.g., status 401 and `WWW-Authenticate` in HTTP Basic. `AuthenticationFailureHandler` typically handles form login errors. `AccessDeniedHandler` handles permission denials for authenticated users; it is not the place to fix account-store errors. `ExceptionTranslationFilter` coordinates security exceptions along the filter chain, though exceptions already caught and handled by an authentication filter may follow that filter's own failure handler.

### 3.3 Distinguishing Authentication, Authorization, and Infrastructure Errors

- **401 Unauthorized:** usually requires re-authentication or indicates an invalid token; Basic/Bearer must preserve protocol-appropriate HTTP challenges.
- **403 Forbidden:** authenticated but lacking permissions (or another protection mechanism like CSRF); not automatically a login failure.
- **503 Service Unavailable:** may be chosen by the application when a dependent authentication service is down. Spring Security **does not automatically map** every `AuthenticationServiceException` to 503.
- **429 Too Many Requests:** may be due to rate limiting; does not assert wrong user/password.
- **Other 5xx:** system or configuration error; inspect handlers, logs, and root cause.

For user errors, public messages should be uniform between non-existent username and wrong password. For infrastructure errors, a public error code like `identity_service_unavailable` can be used without revealing database names, LDAP hostnames, user details, stack traces, or account existence.

## 4. Complete Example: A REST API Distinguishing Credential Errors from Identity Store Failures

The sample below has user `alice` and protected endpoint `GET /secure`. The simulated account store has two states: operating normally or experiencing an outage. **Do not create an HTTP endpoint to toggle the outage**, because that operation could break authentication if exposed; tests will control this state inside the JVM.

### 4.1 Maven Configuration

File `pom.xml` for Java 17 and Spring Boot 3.3.5:

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
    <groupId>com.example</groupId>
    <artifactId>identity-error-demo</artifactId>
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

### 4.2 Application Code

Create `src/main/java/com/example/identity/IdentityFailureDemoApplication.java`:

```java
package com.example.identity;

import java.nio.charset.StandardCharsets;
import java.util.Map;
import java.util.Optional;

import jakarta.servlet.DispatcherType;
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.security.authentication.AuthenticationServiceException;
import org.springframework.security.authentication.InternalAuthenticationServiceException;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.core.userdetails.UsernameNotFoundException;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.AuthenticationEntryPoint;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class IdentityFailureDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(IdentityFailureDemoApplication.class, args);
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    DemoAccountStore demoAccountStore(PasswordEncoder encoder) {
        UserDetails alice = User.withUsername("alice")
            .password(encoder.encode("demo123"))
            .roles("USER")
            .build();
        return new DemoAccountStore(Map.of("alice", alice));
    }

    @Bean
    UserDetailsService userDetailsService(DemoAccountStore store) {
        return username -> {
            try {
                return store.find(username)
                    .orElseThrow(() ->
                        new UsernameNotFoundException("Account not found"));
            } catch (StoreUnavailableException cause) {
                // Service failure is distinct from username not found.
                throw new InternalAuthenticationServiceException(
                    "Account store unavailable", cause);
            }
        };
    }

    @Bean
    AuthenticationEntryPoint apiAuthenticationEntryPoint() {
        return (request, response, authError) -> {
            boolean dependencyFailure =
                authError instanceof AuthenticationServiceException;

            response.setStatus(
                dependencyFailure
                    ? HttpServletResponse.SC_SERVICE_UNAVAILABLE
                    : HttpServletResponse.SC_UNAUTHORIZED);
            response.setContentType(MediaType.APPLICATION_JSON_VALUE);
            response.setCharacterEncoding(StandardCharsets.UTF_8.name());

            if (!dependencyFailure) {
                response.setHeader(
                    HttpHeaders.WWW_AUTHENTICATE, "Basic realm=\"demo\"");
            }

            response.getWriter().write(
                dependencyFailure
                    ? "{\"error\":\"identity_service_unavailable\"}"
                    : "{\"error\":\"invalid_credentials\"}");
        };
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            AuthenticationEntryPoint apiAuthenticationEntryPoint)
            throws Exception {

        http.authorizeHttpRequests(authorize -> authorize
                .dispatcherTypeMatchers(DispatcherType.ERROR).permitAll()
                .requestMatchers("/health").permitAll()
                .requestMatchers("/secure").authenticated()
                .anyRequest().denyAll()
            )
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .httpBasic(basic -> basic
                .authenticationEntryPoint(apiAuthenticationEntryPoint))
            .exceptionHandling(errors -> errors
                .authenticationEntryPoint(apiAuthenticationEntryPoint));

        return http.build();
    }

    @RestController
    static class DemoController {
        @GetMapping("/health")
        String health() {
            return "application running";
        }

        @GetMapping("/secure")
        String secure() {
            return "secure ok";
        }
    }

    static final class DemoAccountStore {
        private final Map<String, UserDetails> accounts;
        private volatile boolean available = true;

        DemoAccountStore(Map<String, UserDetails> accounts) {
            this.accounts = accounts;
        }

        Optional<UserDetails> find(String username) {
            if (!available) {
                throw new StoreUnavailableException();
            }
            return Optional.ofNullable(accounts.get(username));
        }

        void setAvailable(boolean available) {
            this.available = available;
        }
    }

    static final class StoreUnavailableException extends RuntimeException {
        StoreUnavailableException() {
            super("Simulated account-store outage");
        }
    }
}
```

**Why does the example classify errors properly?**

1. `store.find(username)` returns `Optional.empty()` when the lookup **completed normally** without finding an account; `UserDetailsService` converts it to `UsernameNotFoundException`. The default provider can mask it as `BadCredentialsException`.
2. When the backend cannot serve requests, `StoreUnavailableException` is wrapped in `InternalAuthenticationServiceException`; it belongs to the `AuthenticationServiceException` family so the service-failure branch can recognize it.
3. Wrong passwords are checked by `DaoAuthenticationProvider` via `PasswordEncoder`, without hand-rolling password comparisons or fake exceptions.
4. `apiAuthenticationEntryPoint` returns **503 only on the service-error branch**, and **401 with a Basic challenge** for other authentication failures. This is a rule of the demo API; form login/OAuth2/Bearer must use their corresponding handlers.
5. `SessionCreationPolicy.STATELESS` keeps HTTP Basic attempts independent. There is no path allowing authentication to pass when the store is down, so the example **fails closed**.
6. The demo uses a weak password for ease of learning; production needs strong password policies, secret management, and a real repository. Never expose `setAvailable` as a public operational API.

### 4.3 Running HTTP Tests Manually

Requires Java 17+ and Maven. From the directory containing `pom.xml`:

```bash
mvn test
mvn spring-boot:run
```

Use another terminal window:

```bash
curl -i http://localhost:8080/health
curl -i http://localhost:8080/secure
curl -i -u alice:wrong http://localhost:8080/secure
curl -i -u nobody:wrong http://localhost:8080/secure
curl -i -u alice:demo123 http://localhost:8080/secure
```

| Request | HTTP | Expected Body |
| --- | --- | --- |
| `GET /health` | 200 | `application running` |
| `GET /secure` without credentials | 401 | `{"error":"invalid_credentials"}` and `WWW-Authenticate: Basic ...` |
| `alice:wrong` | 401 | `{"error":"invalid_credentials"}` |
| `nobody:wrong` | 401 | **Same body** as wrong password |
| `alice:demo123` | 200 | `secure ok` |

Store outage state cannot be toggled via curl in this example; the next test section does this inside the JVM.

### 4.4 Integration Tests: Credential Failure vs. Dependency Failure

Create `src/test/java/com/example/identity/IdentityFailureDemoApplicationTest.java`:

```java
package com.example.identity;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class IdentityFailureDemoApplicationTest {

    @Autowired MockMvc mvc;
    @Autowired IdentityFailureDemoApplication.DemoAccountStore store;

    @AfterEach
    void resetStore() {
        store.setAvailable(true);
    }

    @Test
    void wrongPasswordAndUnknownUserLookTheSame() throws Exception {
        mvc.perform(get("/secure").with(httpBasic("alice", "wrong")))
            .andExpect(status().isUnauthorized())
            .andExpect(jsonPath("$.error").value("invalid_credentials"));

        mvc.perform(get("/secure").with(httpBasic("nobody", "wrong")))
            .andExpect(status().isUnauthorized())
            .andExpect(jsonPath("$.error").value("invalid_credentials"));
    }

    @Test
    void validCredentialWorks() throws Exception {
        mvc.perform(get("/secure").with(httpBasic("alice", "demo123")))
            .andExpect(status().isOk())
            .andExpect(content().string("secure ok"));
    }

    @Test
    void storeOutageIsNotBadCredentials() throws Exception {
        store.setAvailable(false);

        mvc.perform(get("/secure").with(httpBasic("alice", "demo123")))
            .andExpect(status().isServiceUnavailable())
            .andExpect(jsonPath("$.error")
                .value("identity_service_unavailable"));

        mvc.perform(get("/secure").with(httpBasic("nobody", "wrong")))
            .andExpect(status().isServiceUnavailable())
            .andExpect(jsonPath("$.error")
                .value("identity_service_unavailable"));
    }

    @Test
    void missingCredentialGetsBasicChallenge() throws Exception {
        mvc.perform(get("/secure"))
            .andExpect(status().isUnauthorized())
            .andExpect(header().string(
                "WWW-Authenticate", "Basic realm=\"demo\""));
    }
}
```

Four tests confirm: non-existent username and wrong password yield the **same public response**; valid credentials succeed; store outage is always classified as a **service error for both existing and non-existent users**; anonymous requests receive the right Basic challenge. During an outage, the `/secure` controller must never run successfully.

Re-run `mvn test`. The tests require `spring-boot-starter-test` and `spring-security-test` as declared in `pom.xml`. These are tests for the demo, not proof that every OAuth2/LDAP project will share the exact same HTTP mapping.

## 5. Connecting to a Real Account Store: Exception Mapping at the Repository Boundary

Replace `DemoAccountStore` with a JPA/JDBC/LDAP adapter, ensuring that "query returned no result" and "unable to execute query" are returned differently. Example **fragment**, requiring your project's repository and mapper:

```java
@Override
public UserDetails loadUserByUsername(String username) {
    try {
        var account = accountRepository.findByUsername(username)
            .orElseThrow(() ->
                new UsernameNotFoundException("Account not found"));

        return accountMapper.toUserDetails(account);
    } catch (DataAccessResourceFailureException cause) {
        throw new InternalAuthenticationServiceException(
            "Account database is unavailable", cause);
    }
}
```

`DataAccessResourceFailureException` is in `org.springframework.dao`; this is only one connection-error type. With real database/LDAP clients, identify the exact exceptions thrown, including timeouts, transactions, and pool exhaustion; never catch all `RuntimeException` and treat them as invalid credentials.

**Anti-example 1 — masking database failure as non-existent username:**

```java
// WRONG: a failed query also turns into "user does not exist".
try {
    return repository.findByUsername(username)
        .orElseThrow(() -> new UsernameNotFoundException("Not found"));
} catch (RuntimeException cause) {
    throw new UsernameNotFoundException("Not found");
}
```

**Anti-example 2 — failing open with a fake user:** some apps handle exceptions by granting temporary permissions. This is a critical vulnerability; if identity cannot be verified, never issue an authenticated session/token and never grant default permissions. Never fall back to `ROLE_ADMIN` or a user cache without evaluating freshness of lock/revocation state.

## 6. Differences with LDAP, OAuth2/OIDC, and JWT

### LDAP / Active Directory

An LDAP bind rejected due to credentials differs from a connection timeout or unreachable LDAP server. LDAP error codes can cover multiple causes; consult the protocol/driver and application reality before classifying. Never take a network error and report "wrong password". For LDAP accounts with special states (locked/disabled), consider protecting that info from enumeration via public messages.

### OAuth2 / OpenID Connect (OIDC)

- `invalid_grant` is not necessarily a wrong password; an authorization code may be expired or reused, a refresh token revoked, or flow parameters invalid.
- `temporarily_unavailable`, `server_error`, token endpoint timeouts, or HTTP 5xx usually point to service errors, though cause/configuration still needs checking.
- Wrong redirect URI, client secret, TLS trust, or clock skew can break login even while the IdP is healthy: classify as configuration error.
- Error handlers for `oauth2Login`/form login differ from HTTP Basic's `AuthenticationEntryPoint`. Do not copy the 401/503 mapping from the example across every protocol.

### JWT Resource Server / JWKS

Expired JWTs, invalid signatures, or wrong issuer/audience are usually **invalid tokens** and typically return 401 Bearer per protocol. If fetching a new key is needed and the JWKS endpoint times out, the error may be **verification service unavailable**; you cannot conclude the token is invalid from a timeout alone. However, the decoder may use an existing JWK cache, so a brief IdP outage does not mean every JWT request will fail. Inspect `JwtDecoder`, cache, `jwk-set-uri` configuration, and actual traces.

When customizing Bearer handling, keep `WWW-Authenticate` and error semantics per RFC 6750; never replace them with a Basic challenge or JSON body that prevents clients from recognizing `invalid_token` / `insufficient_scope`.

## 7. Observability and Alerting: Measuring Infrastructure Errors Separately from User Errors

Have clear internal fields (logs/metrics/tracing), without exposing all of them to clients:

| Field | Example | Meaning |
| --- | --- | --- |
| `category` | `INVALID_CREDENTIALS`, `ACCOUNT_STATE`, `IDENTITY_DEPENDENCY`, `AUTH_CONFIGURATION` | Error classification |
| `dependency` | `account-db`, `ldap`, `oidc-token-endpoint`, `jwks` | Pinpoints failing dependency |
| `operation` | `loadUserByUsername`, `tokenExchange`, `jwtDecode` | Pinpoints operation |
| `exceptionClass / rootCause` | `InternalAuthenticationServiceException`, timeout | Aids investigation |
| `traceId/correlationId` | Request ID | Correlates across services |
| `duration / timeoutCount` | Latency, timeout errors | Alerts on slow dependencies |
| `responseStatus` | 401, 403, 503 | Verifies public mapping |

**Never log passwords, raw Authorization headers, raw tokens, session cookies, OAuth2 authorization codes, private keys, or unnecessary personal data.** If user correlation is needed, use internal identifiers or secure hashes per data-protection policy, controlling log access and retention.

Spring Security's `DefaultAuthenticationEventPublisher` publishes events for several exceptions, including `BadCredentialsException` and `AuthenticationServiceException`. Event mapping may need additions when exceptions are subclasses. Never use **total authentication failures** to infer an outage: rising credential failures can stem from users or attacks, whereas timeouts and connection errors must have separate metrics.

Operationally, "the app returns HTTP 200 for `/health`" does not prove the database/IdP is ready. Liveness, readiness, and dependency health must be defined per architecture; avoid letting health checks overload the identity store.

## 8. Safe Handling Policy When the Identity Store Is Unavailable

1. **Fail closed:** when unable to verify, do not create an authenticated session, issue tokens, or use fake users.
2. **Preserve error semantics:** distinguish service failures from invalid credentials in internal handling; never do `catch (Exception) -> BadCredentialsException`.
3. **Fit-for-purpose messages:** wrong credentials can ask the user to re-check input; an outage should report temporary service unavailability and instruct to try later, not tell users to change passwords.
4. **Do not increment failed-login counters on backend timeouts:** otherwise an outage triggers mass lockouts. Keep independent anti-abuse rate limits in place.
5. **Bounded retries:** clear timeouts, retry/backoff/jitter, and circuit breakers matching each request's nature; avoid "retry storms" or repeating one-time authorization-code exchanges/operations.
6. **Do not leak account existence:** responses for non-existent username and wrong password should look identical; consider timing as well.
7. **Do not leak infrastructure info:** exclude DB hostnames, stack traces, role names, and user statuses from public responses.
8. **Do not infer errors from HTTP status alone:** inspect the original exception, failure point, and upstream responses before choosing a fix.

## 9. Login Incident Diagnostic Checklist

When receiving a "login failed" report, check in order:

1. **Where did the request go?** Identify the security filter chain, authentication filter, `AuthenticationProvider`, user store/IdP/JWKS, and whether an error occurred at a proxy/gateway.
2. **Did the lookup complete?** Succeeding with no record differs from query timeout/connection refused; never guess from a response body saying "bad credentials".
3. **If an account was found, what to check?** Password hash, locked/disabled/expired state, token expiry, issuer/audience, and matching authentication type.
4. **Protocol or dependency error?** OAuth2 error code, LDAP code, token endpoint HTTP status, DNS/TLS/JWKS errors; check client configuration.
5. **Is the response mapping accurate?** 401 with appropriate challenge, 403 only when appropriate, 503 if a service-error policy applies; never return 200 on failure.
6. **What security risks appear?** Account enumeration, credential logging, unfair user lockouts, creating an authenticated context while the user store is down, or falling back to default permissions?
7. **Regression tests:** unknown user, wrong password, valid login, locked user, DB down with existing and non-existing users, insufficient permissions after login, invalid token, IdP timeout, and protocol headers.

A good test suite verifies more than status codes. It must prove that **infrastructure errors never turn into credential failures**, unauthenticated users cannot access resources, and responses leak no sensitive information.

## 10. Key Takeaways

- **No user found after a successful lookup** and **unable to look up a user due to backend failure** are two distinct outcomes.
- `BadCredentialsException` does not prove a username exists: Spring Security defaults to masking `UsernameNotFoundException` to curb account enumeration.
- Use `AuthenticationServiceException`/`InternalAuthenticationServiceException` or an equivalent internal classification for dependency errors. Returning 503 is an **application policy that must be configured and tested**, not the default across all versions/mechanisms.
- Distinguish **authentication 401**, **authorization 403**, **dependency 5xx**, and **rate limiting 429** by root cause. Never use `AccessDeniedHandler` to work around user-lookup failures.
- For LDAP, OAuth2/OIDC, and JWT, preserve protocol semantics, do not ignore JWKS caching, and do not confuse `invalid_grant` with wrong passwords in every scenario.
- When identity cannot be verified, the system **fails closed** and records the incident for safe recovery.

## Official Documentation

- Spring Security — Servlet Authentication Architecture: https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html
- Spring Security — UserDetailsService: https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/user-details-service.html
- Spring Security — DaoAuthenticationProvider: https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/dao-authentication-provider.html
- AbstractUserDetailsAuthenticationProvider / `hideUserNotFoundExceptions`: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authentication/dao/AbstractUserDetailsAuthenticationProvider.html
- Spring Security — Authentication Events: https://docs.spring.io/spring-security/reference/servlet/authentication/events.html
- Spring Security — OAuth2 Resource Server JWT: https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html
- AuthenticationEntryPoint Java API: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/AuthenticationEntryPoint.html