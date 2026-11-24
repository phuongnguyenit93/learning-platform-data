# Observing a Full Authentication Pass from Input to Result Authentication

> **Context:** Spring Security — authentication, **Authentication Engine** group. The goal of this lesson is to trace **one concrete request** from credentials to the final `Authentication`, identifying which component verified the proof, where the result is placed, and what happens when credentials are wrong. The main example uses Spring Boot 3.3.x / Spring Security 6.3.x (Servlet) and Java 17+. The code is designed to run in a standalone demo project.

## 1. What Do You Need to Observe?

After this lesson, you will:

1. Trace the path **HTTP request → SecurityFilterChain → authentication filter → AuthenticationManager → AuthenticationProvider → result Authentication → SecurityContext → authorization**.
2. Distinguish an **unauthenticated input `Authentication`** from a **verified result `Authentication` produced by a provider**.
3. Know what to observe at each checkpoint: token type, `isAuthenticated` flag, principal, authorities, error type, context state, and HTTP status code; know what must never be logged.
4. Run a Spring Boot application with a **safe tracing provider** and test HTTP 200, 401, and 403 outcomes.
5. Understand why a request may not pass through a provider, why a succeeding provider does not mean an endpoint allows access, and why `AuthenticationManager` is not the component storing `SecurityContext`.
6. Apply the same observation method to form login, JWT bearer, remember-me, or multi-`SecurityFilterChain` configurations without guessing token types wrongly.

**Guiding question:** “In this request, **what proof** did Spring Security receive, **who verified the proof**, and **which `Authentication` result** did the application actually use?”

## 2. Separating Input Data from Trusted Results

`Authentication` is an interface serving **two roles**:

- **Authentication input:** carries principal/credentials submitted by the client or extracted from the request by a filter. Usually unauthenticated, `isAuthenticated() == false`.
- **Authentication result:** created by a trusted mechanism after verifying proof; carries the verified principal, authorities, and authenticated flag. The result may be placed by the filter into `SecurityContextHolder` for downstream code to use.

Two objects can share the same Java class, such as `UsernamePasswordAuthenticationToken`, yet differ in **origin, semantics, and state**. Never treat the input request as a trusted result merely because the Java class is identical.

| Data/attribute | Input before verification | Result after verification |
| --- | --- | --- |
| `Authentication` type | Usually `UsernamePasswordAuthenticationToken` from HTTP Basic/form login filter | May still be `UsernamePasswordAuthenticationToken` |
| `principal` | Usually username string extracted from credentials | Usually `UserDetails` returned by a trusted source |
| `credentials` | Password or token requiring verification | May already be erased, depending on provider/manager |
| `isAuthenticated()` | Usually `false` | `true` when the provider returns a trusted success result |
| `authorities` | Self-declared client roles must not be trusted | Mapped from the verified account or token |
| API access permission | Not yet decided | Still must pass authorization and resource/tenant checks |

**Distinguish four milestones:** receiving data ≠ verifying proof ≠ placing the result into `SecurityContext` ≠ granting operation access. Seeing `isAuthenticated() == true` does not by itself confirm your code verified passwords/JWTs properly; you must know **who produced the `true` state**.

## 3. A Concrete HTTP Basic Flow: From Request to Controller

We use a simple Servlet API:

- `GET /api/me`: caller must be authenticated.
- `GET /api/reports`: caller must have authority `reports.read`.
- Two demo accounts: `linh` has `reports.read` and `khach` lacks that authority.
- HTTP Basic is enabled; requests carry `Authorization: Basic ...` over HTTPS in real systems.

~~~mermaid
sequenceDiagram
    participant C as HTTP Client
    participant F as Spring Security FilterChain
    participant B as BasicAuthenticationFilter
    participant M as ProviderManager
    participant P as DaoAuthenticationProvider
    participant U as UserDetailsService + PasswordEncoder
    participant S as SecurityContextHolder
    participant A as Authorization + Controller
    C->>F: GET /api/me, Authorization: Basic ...
    F->>B: Pass request through HTTP Basic filter
    B->>B: Create unauthenticated Authentication
    B->>M: authenticate(request)
    M->>P: supports(type), authenticate(request)
    P->>U: Look up UserDetails + verify password
    alt Password valid, account allowed to log in
        U-->>P: Verification succeeded
        P-->>M: Authenticated Authentication + authorities
        M->>M: Erase credentials from result if supported
        M-->>B: Result Authentication
        B->>S: Put Authentication into SecurityContext
        B->>A: Allow request to continue
        A->>A: Check endpoint permissions
        A-->>C: 200 or 403 if missing permissions
    else Invalid credentials
        U-->>P: Mismatch
        P-->>M: AuthenticationException
        M-->>B: AuthenticationException
        B-->>C: HTTP 401 via AuthenticationEntryPoint
    end
~~~

### Explaining Each Checkpoint

**Checkpoint 0 — Actual HTTP request.** Browser, curl, or an app sends the request. The Basic header is a transmitted credential; Base64 in Basic **is not encryption**, so use HTTPS in real deployments. When tracing, log only “header present or not”, scheme, and request ID; never print the raw header or password.

**Checkpoint 1 — Selecting the filter chain.** `FilterChainProxy` evaluates `SecurityFilterChain`s and picks the matching chain. Multi-chain configs must inspect `securityMatcher`, chain order, and URL; non-matching chains will not run their filters. This is **filter order**, distinct from **authentication provider order**.

**Checkpoint 2 — Extracting credentials and creating the input token.** `BasicAuthenticationFilter` receives the Basic header and creates a `UsernamePasswordAuthenticationToken` request with untrusted username/password. At this point, seeing `principal="linh"` only proves the client **claimed** that username.

**Checkpoint 3 — Passing to the manager.** The filter calls `AuthenticationManager.authenticate(input)`. `ProviderManager` walks its `AuthenticationProvider` list in order, calling `supports(input.getClass())` and then `authenticate` on matching providers. Some providers may return `null`/throw errors; the final outcome depends on iteration and exception policies. Do not assume the manager checks passwords itself.

**Checkpoint 4 — Provider verifies proof.** `DaoAuthenticationProvider` loads `UserDetails` from `UserDetailsService`, uses `PasswordEncoder` to compare the supplied password against the stored hash, and checks account status per Spring Security mechanics. Only the provider has grounds to return a successful result.

**Checkpoint 5 — Creating the result Authentication.** On successful verification, the provider returns an `Authentication` with trusted principal and authorities. With the default username/password flow this is typically an authenticated `UsernamePasswordAuthenticationToken` whose principal is `UserDetails`. `ProviderManager` by default invokes `eraseCredentials()` on the result if it supports `CredentialsContainer`, so the password may no longer be readable in controllers.

**Checkpoint 6 — Putting the result into context.** The filter/mechanism calling the manager receives the result and sets `SecurityContextHolder` for the request context. **`ProviderManager` does not put the result into `SecurityContextHolder` itself.** Persistence across requests depends on `SecurityContextRepository`, sessions, and stateless/stateful policies; never infer it from a `true` flag.

**Checkpoint 7 — Checking permissions.** `AuthorizationFilter` and/or method security decide whether the resource may be invoked. A successful `Authentication` lacking `reports.read` can still get **403**. When a request lacks valid credentials, endpoints protected with HTTP Basic typically return **401**.

**Checkpoint 8 — Request completion.** Context is managed/cleared per the filter's lifecycle. Do not rely on a thread-local `SecurityContextHolder` from another thread or after the request has finished to infer the principal of the completed request.

## 4. Practice: Spring Boot App with Tracing at the Provider Boundary

This example uses **the standard `DaoAuthenticationProvider` to genuinely verify passwords**, then wraps it with an `AuthenticationProvider` that logs only **non-sensitive** observable attributes. The wrapper **does not authenticate itself**, does not alter results, and does not grant permissions; it helps distinguish inputs, outputs, and failures when `ProviderManager` invokes the provider.

Project structure:

~~~text
authentication-trace-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/example/authtrace/
    │   ├── AuthenticationTraceApplication.java
    │   ├── SecurityConfiguration.java
    │   └── IdentityController.java
    └── test/java/example/authtrace/
        └── AuthenticationTraceTest.java
~~~

Hardcoded accounts and passwords here are **solely for local study**. Never use sample accounts, source-embedded passwords, or HTTP Basic without TLS in real environments.

### 4.1. Gradle and Java 17

`settings.gradle`:

~~~groovy
rootProject.name = 'authentication-trace-demo'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'example'
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
~~~

Spring Boot manages compatible Spring Framework and Spring Security versions through dependency management. There is no need to declare a different Spring Security Core version on dependencies, avoiding library mismatches.

### 4.2. Application Entry Point

`src/main/java/example/authtrace/AuthenticationTraceApplication.java`:

~~~java
package example.authtrace;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class AuthenticationTraceApplication {
    public static void main(String[] args) {
        SpringApplication.run(AuthenticationTraceApplication.class, args);
    }
}
~~~

### 4.3. Real Provider Configuration and Safe Tracing

`src/main/java/example/authtrace/SecurityConfiguration.java`:

~~~java
package example.authtrace;

import java.util.List;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.AuthenticationProvider;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.authentication.dao.DaoAuthenticationProvider;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.AuthenticationException;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfiguration {

    private static final Logger log =
            LoggerFactory.getLogger(SecurityConfiguration.class);

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        UserDetails linh = User.withUsername("linh")
                .password(encoder.encode("demoPass!"))
                .authorities("reports.read")
                .build();

        UserDetails khach = User.withUsername("khach")
                .password(encoder.encode("demoPass!"))
                .authorities("profile.read")
                .build();

        return new InMemoryUserDetailsManager(linh, khach);
    }

    @Bean
    AuthenticationManager authenticationManager(
            UserDetailsService users, PasswordEncoder encoder) {

        // Standard provider: looks up UserDetails, verifies hash and account status.
        DaoAuthenticationProvider delegate =
                new DaoAuthenticationProvider(encoder);
        delegate.setUserDetailsService(users);

        AuthenticationProvider observingProvider =
                new AuthenticationProvider() {

            @Override
            public boolean supports(Class<?> tokenType) {
                boolean supported = delegate.supports(tokenType);
                log.info("auth.provider.supports type={} supported={}",
                        tokenType.getSimpleName(), supported);
                return supported;
            }

            @Override
            public Authentication authenticate(Authentication input)
                    throws AuthenticationException {

                // Never log principal, password, headers, or the full token.
                log.info("auth.provider.input type={} authenticated={}",
                        input.getClass().getSimpleName(),
                        input.isAuthenticated());

                try {
                    Authentication output = delegate.authenticate(input);

                    // A provider may return null to abstain from deciding.
                    if (output == null) {
                        log.info("auth.provider.abstain");
                        return null;
                    }

                    log.info("auth.provider.success type={} authenticated={} authorities={}",
                            output.getClass().getSimpleName(),
                            output.isAuthenticated(),
                            output.getAuthorities().size());
                    return output;
                }
                catch (AuthenticationException failure) {
                    log.info("auth.provider.failure exception={}",
                            failure.getClass().getSimpleName());
                    throw failure;
                }
            }
        };

        // List contains only one traced provider, avoiding unintended
        // fallback to another identity provider.
        return new ProviderManager(List.of(observingProvider));
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http, AuthenticationManager authenticationManager)
            throws Exception {

        http.authenticationManager(authenticationManager)
            .sessionManagement(session -> session
                    .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(requests -> requests
                    .requestMatchers(HttpMethod.GET, "/api/me")
                        .authenticated()
                    .requestMatchers(HttpMethod.GET, "/api/reports")
                        .hasAuthority("reports.read")
                    .anyRequest().denyAll())
            .httpBasic(Customizer.withDefaults());

        return http.build();
    }
}
~~~

**Role of each part:**

- `InMemoryUserDetailsManager` holds demo accounts. Spring Security uses `BCryptPasswordEncoder` to verify the submitted password, never comparing plaintext passwords directly.
- `DaoAuthenticationProvider` handles actual authentication; the `observingProvider` decorator only logs **token type, status, authority count, and exception type**. It preserves the delegate's `Authentication` and exceptions unchanged.
- `ProviderManager` is explicitly configured with the single wrapped provider. Thanks to `http.authenticationManager(authenticationManager)`, the filter chain uses the exact manager constructed in this application.
- `httpBasic(...)` enables `BasicAuthenticationFilter` to handle Basic credentials.
- `SessionCreationPolicy.STATELESS` ensures the demo does not rely on `HttpSession` to remember a previous login. For each HTTP request carrying a Basic header, authentication executes anew. Do not extrapolate this pattern to apps using form login or OIDC sessions.
- All other endpoints are blocked by `denyAll()`. The demo only has GET operations; if adding mutating APIs, evaluate CSRF and client/session architecture rather than copying the config mechanically.

**Key point about wrappers:** A decorator must never turn an invalid request into a success. It always calls `delegate.authenticate(input)`, returning the exact result or rethrowing the exact `AuthenticationException`. Using a custom provider solely to “log” and then return an `authenticated(...)` token without checking credentials defeats security.

### 4.4. Controller Reading the Result Authentication

`src/main/java/example/authtrace/IdentityController.java`:

~~~java
package example.authtrace;

import java.util.Map;

import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class IdentityController {

    @GetMapping("/api/me")
    public Map<String, Object> me(Authentication authentication) {
        return Map.of(
                "name", authentication.getName(),
                "authenticationType",
                        authentication.getClass().getSimpleName(),
                "principalType",
                        authentication.getPrincipal().getClass().getSimpleName(),
                "authenticated", authentication.isAuthenticated(),
                "credentialsPresent",
                        authentication.getCredentials() != null,
                "authorities", authentication.getAuthorities().stream()
                        .map(GrantedAuthority::getAuthority)
                        .sorted()
                        .toList());
    }

    @GetMapping("/api/reports")
    public String reports() {
        return "REPORT_OK";
    }
}
~~~

`Authentication authentication` in the controller is **the result placed into the request context by Spring Security**, after the preceding authentication steps. With successful HTTP Basic in the demo, it is typically `UsernamePasswordAuthenticationToken`, principal is `UserDetails` (`User`), `authenticated=true`, and authorities come from the account store.

`credentialsPresent=false` is expected because `ProviderManager` by default erases credentials after success if the token supports it. **This does not mean the input credentials were empty**: the password was present in the request before the provider verified it.

The example controller intentionally returns several **learning metadata fields**. In real applications, do not expose token classes, full authorities, or other operational info to every client by default. Return only the fields the API genuinely needs.

## 5. Testing from HTTP Input to Result and Permission Decisions

Use `MockMvc` with real Spring Security filters to test multiple branches without opening an HTTP port. Demo data is declared in `SecurityConfiguration`.

`src/test/java/example/authtrace/AuthenticationTraceTest.java`:

~~~java
package example.authtrace;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class AuthenticationTraceTest {

    @Autowired
    MockMvc mvc;

    @Test
    void missingCredentialIsUnauthorized() throws Exception {
        mvc.perform(get("/api/me"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void wrongPasswordIsUnauthorized() throws Exception {
        mvc.perform(get("/api/me")
                        .with(httpBasic("linh", "not-the-password")))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void correctPasswordProducesVerifiedAuthentication() throws Exception {
        mvc.perform(get("/api/me")
                        .with(httpBasic("linh", "demoPass!")))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.name").value("linh"))
                .andExpect(jsonPath("$.authenticated").value(true))
                .andExpect(jsonPath("$.authenticationType")
                        .value("UsernamePasswordAuthenticationToken"))
                .andExpect(jsonPath("$.principalType").value("User"))
                .andExpect(jsonPath("$.credentialsPresent").value(false))
                .andExpect(jsonPath("$.authorities[0]")
                        .value("reports.read"));
    }

    @Test
    void verifiedUserWithoutAuthorityIsForbidden() throws Exception {
        mvc.perform(get("/api/reports")
                        .with(httpBasic("khach", "demoPass!")))
                .andExpect(status().isForbidden());
    }

    @Test
    void verifiedUserWithAuthorityMayReadReport() throws Exception {
        mvc.perform(get("/api/reports")
                        .with(httpBasic("linh", "demoPass!")))
                .andExpect(status().isOk())
                .andExpect(content().string("REPORT_OK"));
    }
}
~~~

**Why is this a valuable authentication test?** `httpBasic(...)` attaches Basic credentials to the HTTP test request. Spring Security's filter, declared manager, provider, and password encoder all participate. Thus the test does not merely plant a fake principal in `SecurityContext` bypassing the credential stage.

Conversely, `@WithMockUser` and `SecurityMockMvcRequestPostProcessors.user(...)` are suited for isolated **authorization** tests, yet do not prove passwords were checked. You can use both test kinds, provided their goals are kept distinct.

### 5.1. Running with Gradle

In the project directory, with JDK 17+ and compatible Gradle or Gradle Wrapper:

~~~bash
gradle test
gradle bootRun
~~~

If a wrapper is present, use `./gradlew test` and `./gradlew bootRun`. On Windows PowerShell use `.\gradlew.bat test` and `.\gradlew.bat bootRun`. There is no need to run `javac` manually for each Spring Boot class because Gradle manages the classpath and dependency versions.

In another terminal, try these requests:

~~~bash
curl -i http://localhost:8080/api/me
curl -i -u "linh:not-the-password" http://localhost:8080/api/me
curl -i -u "linh:demoPass!" http://localhost:8080/api/me
curl -i -u "khach:demoPass!" http://localhost:8080/api/reports
curl -i -u "linh:demoPass!" http://localhost:8080/api/reports
~~~

Passwords in the commands above are **public demo credentials for localhost**. In real systems, never place real secrets in command lines, terminal history, logs, chat, or documentation; use tools with secure secret input/storage and TLS.

### 5.2. What Appears Over HTTP?

| Request | Might provider be called? | Authentication outcome | Expected HTTP |
| --- | --- | --- | --- |
| `GET /api/me`, no Basic header | Usually not, due to missing Basic credential input | No valid authenticated user for the endpoint | **401 Unauthorized** |
| `GET /api/me`, Linh + wrong password | Yes; provider checks and throws `BadCredentialsException` | No successful authentication result created | **401 Unauthorized** |
| `GET /api/me`, Linh + right password | Yes; provider authenticates successfully | `Authentication` with name `linh`, `authenticated=true`, authority `reports.read` | **200 OK** |
| `GET /api/reports`, Khach + right password | Yes; provider authenticates successfully | Authenticated, yet only has `profile.read` | **403 Forbidden** |
| `GET /api/reports`, Linh + right password | Yes; provider authenticates successfully | Has `reports.read` | **200 OK**, body `REPORT_OK` |

For Linh's valid request to `/api/me`, the JSON body has **the following values**; field order is determined by the JSON serializer and need not match the presentation order:

~~~json
{
  "name": "linh",
  "authenticationType": "UsernamePasswordAuthenticationToken",
  "principalType": "User",
  "authenticated": true,
  "credentialsPresent": false,
  "authorities": ["reports.read"]
}
~~~

This is output from **the result `Authentication`** in the controller. The initial input from the Basic filter may have contained the password yet was untrusted; the credential contents were verified by the provider before the system placed the result into context.

### 5.3. What Does Safe Tracing at the Provider Look Like?

Because the decorator uses `Logger.info`, you can see lines with the following meaning (omitting timestamp/thread/logger prefix as they vary by environment):

~~~text
auth.provider.supports type=UsernamePasswordAuthenticationToken supported=true
auth.provider.input type=UsernamePasswordAuthenticationToken authenticated=false
auth.provider.success type=UsernamePasswordAuthenticationToken authenticated=true authorities=1
~~~

In the wrong-password case, the final line is replaced by:

~~~text
auth.provider.failure exception=BadCredentialsException
~~~

**Precision note:** These are **representative lines** extracted from one request pass, not a complete startup log and not promising a fixed log count when multiple requests or other components invoke the manager. For a request lacking a Basic header, there may be **no provider trace**, because the authentication filter never sent credentials for verification.

Trace logs **must not print** passwords, Base64 Basic strings, Bearer tokens, `Authentication.toString()`, raw principals, or full JWT claims. Those values may contain personal data, credentials, or sensitive details.

## 6. Inspecting Three Forms of Authentication at Different Moments

To understand an authentication pass, know **which milestone you are standing at**:

| Milestone | Who holds the object? | Type/State | Meaning |
| --- | --- | --- | --- |
| Client sends HTTP | `HttpServletRequest` holding headers | Not yet a verified `Authentication` | Proof supplied by caller, untrusted |
| Filter creates input token | `BasicAuthenticationFilter` | Unauthenticated `UsernamePasswordAuthenticationToken`, `isAuthenticated=false` | Authentication request needing provider check |
| Provider receives input | `DaoAuthenticationProvider` | Same request type, accessing UserDetails/encoder | Proof is currently being verified |
| Provider returns success | Provider → Manager | Result token `isAuthenticated=true`, trusted principal and authorities | Authentication result prior to credential-management step |
| Manager returns success | `ProviderManager` → Filter | Final `Authentication`; credentials may already be erased | Ready for use in security context |
| Filter sets context | `SecurityContextHolder` | Holds the authenticated result | Downstream filters/controllers can use it |
| Authorization | `AuthorizationFilter` / method security | Evaluates policies based on Authentication | Decides whether operation is allowed |
| Controller | `Authentication` injection or `@CurrentSecurityContext` | Inspects principal, authorities, token type, status | Observes the result accepted by the system |

**Common question:** “Does `isAuthenticated=true` mean the password was verified right where the flag is read?” No. It only reflects the object's state at the read site. You must ensure a trusted filter/manager/provider path actually verified credentials. Never build an `authenticated(...)` token from client input and treat the `true` flag as proof.

### 6.1. Simulating the Manager Boundary Separately

This is an **integrated snippet** using the `AuthenticationManager` configured in the example, not a standalone file:

~~~java
Authentication input =
        UsernamePasswordAuthenticationToken.unauthenticated(
                "linh", passwordFromTrustedTestFixture);

Authentication result = authenticationManager.authenticate(input);

System.out.println(input.isAuthenticated());  // false
System.out.println(result.isAuthenticated());  // true
~~~

Variable `passwordFromTrustedTestFixture` is a test credential controlled by the fixture; this snippet illustrates the API, **not instructing you to create an endpoint taking client passwords and stuffing results into the context yourself**. The `true` result only occurs if the provider verifies successfully; on a wrong password, `authenticate(...)` throws an exception and never reaches the line printing `true`.

**Separating the manager from filters:** when calling the manager directly in a Java service/test, the manager **does not put the result into `SecurityContextHolder` automatically**. In web applications, filters or outer components must manage context/sessions properly. This distinction helps diagnose “`authenticate()` succeeded yet the controller still sees no user”.

## 7. When the Process Fails: Distinguishing Causes and Origin Points

A 401 response does not by itself tell you which checkpoint failed. Trace **request ID → filter chain → whether input credentials existed → whether provider ran → exception class → entry point**.

### 7.1. Missing Credentials

For `/api/me` requiring authenticated access, without a Basic header `BasicAuthenticationFilter` may not call the manager. Anonymous support may create an `AnonymousAuthenticationToken` to represent a guest in the context; this token does not mean a user has logged in. Authorization denies, and `ExceptionTranslationFilter` invokes the authentication entry point, yielding 401 for HTTP Basic.

**Having no provider log** in this case is expected, not proof that the provider is broken or the filter chain did not run.

### 7.2. Credentials Present Yet Wrong

The Basic filter creates the input token, the manager passes it to the provider, `PasswordEncoder` fails to match the password, and the provider throws `BadCredentialsException` (the specific message may be hidden to avoid revealing user existence). With Basic configuration, the failure is turned into 401 via the authentication entry point. No successful `Authentication` reaches the controller.

If the system has multiple providers, `ProviderManager` may try another provider after certain standard `AuthenticationException`s; do not assume “first provider rejects means stop immediately”. Conversely, `AccountStatusException` and `InternalAuthenticationServiceException` stop early. Hence, when debugging multi-provider systems, know the real **list and ordering**.

### 7.3. Authentication Succeeded Yet Lacking Permissions

A `khach` request with the right password yields `provider.success` and puts an authenticated principal in context. However, the authority in the result is `profile.read`, while `/api/reports` requires `reports.read`. The authorization layer denies with 403.

**401 and 403 are outcomes at the HTTP layer**, which can vary with form login/entry point configurations or custom handlers. `AuthenticationManager` itself returns a Java object or throws `AuthenticationException`; it does not write HTTP responses.

### 7.4. Provider System Error or Unsupported Token

`InternalAuthenticationServiceException` can reflect a user-source outage; `ProviderNotFoundException` can occur when no provider handles the `Authentication` type. Log the exception type and provider selection trace; never print passwords or full stack traces into client responses.

Such errors cannot be fixed by flipping `isAuthenticated` to `true`. Fix the root cause: manager/provider wiring, user source, keys/JWK, policies, network, or identity data.

## 8. Observing a Pass via Logs Without Leaking Secrets

**Logging goal:** know *which milestone ran*, *which mechanism processed the request*, *what outcome occurred*, and *which request it belonged to*. No need to retain credentials.

### 8.1. Fields to Log vs. Never Log

| Log (selectively) | Never log |
| --- | --- |
| Request/correlation ID, HTTP method, and route template (without sensitive queries) | Raw `Authorization`, Basic Base64, bearer token |
| Authentication class, provider class, filter name in dev environments | Plaintext passwords or password hashes |
| Before/after `isAuthenticated` at appropriate points | `Authentication.toString()` or entire principal/UserDetails out of habit |
| `supports` status, success/failure/abstain | Full JWTs, session cookies, `refresh_token`, client secrets |
| Exception class and low-sensitivity internal error codes | Sensitive stack traces/claims returned to clients |
| Authority count or policy code needed for auditing | Full user profiles/PII if unnecessary |

Logging `Authentication` can accidentally expose `details`, credential data, or identifying info. The example chose to log fewer fields than needed for full product debugging to preserve privacy. You can include a pseudonymous subject ID in audit logs governed by proper retention and access controls, avoiding printing emails, tokens, or passwords.

### 8.2. When to Use Framework DEBUG?

In local environments, you can temporarily enable:

~~~properties
logging.level.org.springframework.security=DEBUG
~~~

This setting helps observe chains and security decisions at a high level. When deeper inspection is needed, enable trace only in narrow scopes and test environments with dummy data; never treat package-wide TRACE as a default production configuration. Log content varies by framework version and actual filter chains. When finished diagnosing, restore log levels per operational policy.

### 8.3. Testing with Request IDs

A practical approach: the client or gateway sends a sanitized `X-Correlation-Id`; a safe logging filter puts the same ID into MDC; the provider logs an outcome category; access logs record the HTTP status. From there you can correlate:

~~~text
request-id=R-17  route=/api/me  basic-present=true
request-id=R-17  provider=DaoAuthenticationProvider  outcome=SUCCESS
request-id=R-17  auth-type=UsernamePasswordAuthenticationToken
request-id=R-17  authorization=ALLOWED  http-status=200
~~~

The lines above are a **descriptive format for designing observability**, **not default output** of the Section 4 application: the demo code only logs inside the provider, whereas request IDs and authorization outcomes require a separate observability layer. Never accept arbitrary request headers as system IDs without length and character limits; prevent log injection.

## 9. Three Other Flow Types and How to Observe Properly

### 9.1. Form Login: Creating a Session, Not Just Returning a Result

With `UsernamePasswordAuthenticationFilter`, the input is typically a `UsernamePasswordAuthenticationToken` received from form login. On success, Spring Security filters/mechanisms handle the security context, success/failure handlers, and sessions per configuration. Browsers usually receive a session cookie or a redirect, rather than a JSON controller returning `Authentication` like the Basic demo.

With stateful sessions, a subsequent request may **not call the provider again** because `SecurityContext` is loaded from the session/repository. Having no provider trace on the second request **does not mean the user never logged in**. Observe safe session IDs, security context lifecycles, and logout/session-revocation policies.

### 9.2. Bearer JWT: Verifying Tokens, Not Comparing Passwords

`BearerTokenAuthenticationFilter` extracts the bearer token and passes a matching request type to the authentication manager. For JWTs, `JwtAuthenticationProvider` uses a decoder/validator to check signature, issuer, expiration, and other conditions such as audience when configured. The resulting `Authentication` is typically `JwtAuthenticationToken` with principal `Jwt`; authorities can be mapped from scopes via framework rules or a custom converter.

Never print raw JWTs or take claims from an unverified JWT to populate the result `Authentication`. `JwtAuthenticationToken.isAuthenticated=true` must be the **result** after verification, not client-submitted data.

### 9.3. OIDC Login and Identity Providers

With OIDC, the browser goes through a redirect/authorization-code flow; the app verifies the IdP response and tokens via the corresponding mechanism and builds an appropriate authentication principal, typically `OidcUser`. Completely different tokens/managers/providers appear compared to username/password.

When debugging, ask: “Is this the redirect step? callback? token exchange? local session creation? or a post-login API request?” A request might simply be restoring a session rather than re-running OIDC authentication from scratch. Never apply the same `Authentication.getPrincipal() instanceof UserDetails` assumption across all mechanisms.

## 10. Diagnostic Questions in the Right Order

When an endpoint has an authentication issue, answer in order:

1. **Which endpoint/filter chain did the request actually reach?** Are there proxies, path rewrites, or multiple `SecurityFilterChain`s?
2. **Which mechanism did the client use to send credentials?** Basic, Bearer, cookie, or form? Are headers/formats right? Never paste real tokens when asking for debugging help.
3. **Which filter created the `Authentication` request?** What is the input class, and what is `isAuthenticated` before the manager?
4. **Which manager did the filter invoke?** Is it a `ProviderManager`, how many providers does it have, and is there a parent manager?
5. **Which provider `supports` the request type?** Was it actually called? Did it return `null`, a result, or throw an exception?
6. **How was the proof verified?** `PasswordEncoder`, token signature + issuer/audience, introspection, session, mTLS?
7. **What did the result look like before/after the manager?** Principal class, authenticated flag, authority count, credentials still present or erased?
8. **Who set and persisted `SecurityContext`?** Stateless, session, or custom repository? Do subsequent requests reuse the context?
9. **Did authorization allow the operation?** Missing authority or missing permission on a specific tenant/resource?
10. **Which component produced the HTTP response?** `AuthenticationEntryPoint`, access denied handler, failure handler, or controller?

When you only see HTTP 401/403, trace backward through the actual milestones before concluding. When you only see `isAuthenticated=true`, check **the source of the result**, **which context is active**, and **what permissions are checked**.

## 11. Anti-Patterns and How to Avoid Them

| Anti-pattern | Why it is wrong | Replacement |
| --- | --- | --- |
| Printing `Authorization`/passwords to “inspect input requests” | Leaks reusable credentials | Log only presence and scheme; test with dummy credentials |
| Building an `authenticated(...)` token from client JSON to “make tests pass” | Bypasses proof verification, creating spoofing flaws | Call a manager/provider that checks credentials, or use test helpers **only** in authorization tests |
| Reading only `isAuthenticated()` and concluding the password was right | Flag belongs to the object; depends on creator and anonymous/remember-me | Trace filter → manager → provider → result |
| Inspecting controllers when the filter already rejected the request | The controller never ran | Trace at filters/providers and exception handlers |
| Concluding Security isn't working because there are no provider logs | Request may lack credentials, use a session, or miss the filter | Verify chain, credentials, and session context |
| Calling manager directly and assuming the result is in `SecurityContextHolder` | The manager does not save context itself | Let filters manage it or set repository/context via designed mechanisms |
| Equating 401 with 403 | Authentication and authorization are two separate decisions | Distinguish missing/wrong credentials from missing permissions |
| Always casting principal to `UserDetails` | JWT/OIDC/anonymous have different principal types | Check token type and mechanism contract |
| Leaving DEBUG/TRACE on permanently in production | Leak risks and high log costs | Log selectively, emit only needed info, turn off debug when done |
| Using `@WithMockUser` and assuming passwords were tested | Bypasses real filters/providers | Add HTTP Basic/Bearer tests through the real authentication path |
| Putting all business logic into authentication providers | Mixes identity verification with resource policies | Providers authenticate; authorization/services enforce specific permissions |

## 12. Self-Check Exercises

**Scenario 1.** Request has a Basic header yet a wrong password. Provider log appears, controller is not called. Why?

**Answer:** The filter built the input `Authentication`; the provider checked it and threw `AuthenticationException`; the filter/entry point handled the error before the request reached the controller. No valid authentication result existed.

**Scenario 2.** Request for `khach` has the right password and provider logs success, yet `GET /api/reports` returns 403. Is there a contradiction?

**Answer:** No. Successful authentication established the subject and authorities; the authorization step still had to check `reports.read`. `khach` only has `profile.read`.

**Scenario 3.** After form login, the second request has no provider log yet still has a principal. Is that definitely a bug?

**Answer:** No. A valid session/repository can restore the `SecurityContext` authenticated on the prior request. Inspect the session model and validity/revocation policy rather than inferring solely from provider call counts.

**Scenario 4.** Inside `/api/me`, `getCredentials() == null`. Does that mean the client sent no password?

**Answer:** No. `ProviderManager` by default erases credentials from the result `Authentication` if supported; the password was verified beforehand.

**Scenario 5.** A developer writes the entire `Authentication.toString()` to logs to investigate a 401. Is that safe?

**Answer:** Not guaranteed. Different classes can hold different details/claims/PII. Log minimally: type, state, error code, and safe request ID; never log raw credentials/tokens.

**Scenario 6.** A test calls `manager.authenticate(...)` successfully yet sees no user in `SecurityContextHolder`. Why?

**Answer:** `AuthenticationManager` returns the result; **the caller/filter** is responsible for putting it into context. A direct manager test does not automatically run filter chain steps.

**Scenario 7.** An API uses JWT, yet observation code casts the principal to `UserDetails` and hits `ClassCastException`. How to fix?

**Answer:** Rely on the JWT mechanism's actual `Authentication` type, such as `JwtAuthenticationToken` and `Jwt` with Resource Server. Design an adapter mapping to a unified business principal if needed; never cast based on username/password assumptions.

**Scenario 8.** HTTP 401 occurs and the provider is never called. What are the first three hypotheses to check?

**Answer:** Missing credentials or wrong scheme, the request went through a different filter chain, or the request uses a mechanism (session, bearer, form) that does not invoke the instrumented provider. Verify the request and chain before changing provider code.

## 13. Things to Remember

An authentication pass has **untrusted input**, **trusted verification**, **result `Authentication`**, **request-context storage**, and **authorization decisions**. The real lesson lies in connecting these steps with controlled traces:

~~~text
Credentials on HTTP request
  -> authentication filter creates Authentication request (unauthenticated)
  -> AuthenticationManager / ProviderManager
  -> AuthenticationProvider + proof verification source
  -> Authentication result (authenticated or exception)
  -> filter sets SecurityContext for successful request
  -> authorization applies authorities and resource policies
  -> controller or HTTP 401/403
~~~

**When seeing a result `Authentication`, ask**: Who verified the credentials? Which token class? Where did the principal come from? Where did the authorities come from? Who put the result into context? What permissions does the endpoint still check? That is how to observe an authentication pass in a way that can be explained and verified.

### Official Documentation

- Spring Security — Authentication Architecture: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/architecture.html
- Spring Security — HTTP Basic Authentication: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/basic.html
- Spring Security — DaoAuthenticationProvider: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/dao-authentication-provider.html
- Spring Security — SecurityContextHolder and SecurityContext: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/architecture.html#servlet-authentication-securitycontextholder
- Spring Security — Request Authorization: https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/authorize-http-requests.html
- Spring Security — JWT Resource Server: https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/resource-server/jwt.html
