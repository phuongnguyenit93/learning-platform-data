# Login Failure Responses and Limiting Account Information Disclosure

## 1. Goal, scope, and real-world scenario

When a user enters wrong login credentials, the server must **deny authentication** while avoiding accidentally leaking information such as "this username exists," "the account is locked," "this email is registered," or "the password is right, just missing another step." This lesson belongs to the **Login and Logout** section of **Spring Security - fundamentals**, focusing on **login failure responses** and how to limit **account enumeration**.

After completing this lesson, you can:

1. Explain why a login failure message can become a channel for disclosing account information.
2. Distinguish responses for **wrong credentials**, **missing credentials**, **insufficient permissions**, **invalid CSRF**, and **rate limits**, without collapsing them all into one arbitrary error.
3. Understand the authentication failure flow through `UsernamePasswordAuthenticationFilter`, `AuthenticationManager`, `AuthenticationFailureHandler`, and Spring Security Servlet's default `/login?error`.
4. Choose public messages suitable for browser forms and JSON APIs; maintain the principle that "message, status, URL, and metadata must not reveal whether a user exists."
5. Recognize **timing side channels**, username-not-found exceptions, differences in redirects, response sizes, email/SMS recovery, MFA, and lockouts.
6. Design defenses against brute-force/password spraying/credential stuffing using multi-signal throttling and security monitoring without causing account-lockout DoS.
7. Run a Java 17 + Spring Boot 3.5.12 application, test identical public responses for nonexistent usernames, wrong passwords, and disabled accounts; test CSRF 403 and successful login.

**Technical scope:** the runnable portion uses **Spring MVC/Servlet**, `HttpSecurity`, and `SecurityFilterChain`, with default `formLogin`. Spring WebFlux uses `SecurityWebFilterChain`/`ServerHttpSecurity` and corresponding reactive components; data-protection principles are the same, though Servlet classes are not used directly in WebFlux.

## 2. Why is a login error a privacy vulnerability?

Suppose a system has an account `alice`. An attacker sends two requests:

```text
POST /login   username=alice    password=wrong
POST /login   username=made-up  password=wrong
```

If the server replies:

```text
alice     → "Wrong password!"
made-up   → "User does not exist!"
```

then the attacker learns that `alice` is a real account **without ever logging in successfully**. A list of valid usernames/emails can be used for password guessing, targeted phishing, credential stuffing, or other privacy exploitation.

Even when the screen shows the exact same text **"Invalid username or password"**, external differences may still exist:

- **HTTP status:** e.g., 401 for an existing user and 404 for a nonexistent user.
- **Redirect/Location:** `/login?bad-password` differs from `/login?unknown-user`.
- **Response body/length/headers:** differing HTML, JSON, `WWW-Authenticate` details, cookies, or headers.
- **Response time:** an existing account must run password hash verification (CPU-intensive), while a nonexistent user finishes very quickly.
- **Email/SMS delivery timing:** password recovery only sends mail for real accounts, or the API replies differently.
- **Rate limiting/lockout:** only real usernames count failed attempts and then return "locked."
- **MFA/SSO flow:** the application only shows the next-step screen when the username is valid, accidentally revealing accounts.
- **Observable side effects:** CAPTCHAs, password policies, support pages, API status codes, or "Account not activated" messages.

**Design objective:** across the same class of *failed login* situations, an outsider **cannot reliably distinguish** whether an account exists solely from responses and observable behavior. This goal requires combining multiple measures; a generic message is only the first step.

### How does account enumeration differ from brute force?

| Attack type | Primary goal | Example |
| --- | --- | --- |
| **Username/account enumeration** | Identify valid account identifiers | Comparing responses for existing vs. nonexistent emails |
| **Brute-force password** | Guess an account's password | Trying many passwords for `alice` |
| **Password spraying** | Try a few common passwords across many accounts | `Password123` across many usernames |
| **Credential stuffing** | Try username/password pairs from other breaches | Feeding leaked credentials into the login form |

Reducing account enumeration does not replace rate limits/MFA. Conversely, curbing brute force at every layer also slows down enumeration.

## 3. What should a message say and not say?

**Appropriate public message:**

> Unable to sign in with the provided credentials. Please check your information or use account recovery.

Where appropriate, a short sentence like **"Invalid username or password."** can be used. The message must be consistent between nonexistent accounts and wrong passwords. For locked/disabled accounts, designs may balance UX and privacy; if the goal is preventing enumeration, do not return specific reasons to unauthenticated clients.

**Messages that should NOT be returned directly to unauthenticated requests:**

```text
"Email alice@example.com is registered, but password is wrong."
"No user found with name alice."
"This account exists, but was locked by an administrator."
"This account is pending activation."
"Username is valid, please enter OTP."   // if this step reveals a valid user
"User not found in table users."
"org.springframework.security.authentication.BadCredentialsException: ..."
```

Also never return stack traces, internal class names, SQL, bean identifiers, session IDs, tokens, internal group names, or distinguish `reason=user_not_found` from `reason=password_wrong` in JSON.

### Response matrix when identity is unknown

| Situation in the system | Expected public message | Internal action |
| --- | --- | --- |
| Username does not exist | Generic login error | Track failure, increment appropriate limits |
| Username exists but password is wrong | **Same** generic error | Track failure, increment limits |
| Account disabled/locked by policy | **Same** generic error when preventing enumeration | Log internal reason, support safe recovery |
| Valid user and valid password | Authentication succeeds | Create/update session per login mechanism |
| Request missing CSRF token | 403, not treated as wrong password | Blocked by CSRF filter, prompt to reload valid form if appropriate |
| Request is throttled | 429 or challenge following the same protection principles | Enforce rate limits and write audit log |
| Backend identity store unavailable | Generic 5xx service error, do not pretend "wrong password" | Fail closed, monitor incident |

**Note:** not every HTTP failure has to share the same status code. CSRF is a request-protection error, rate limiting is a traffic condition, and an identity provider outage is a service incident. The security requirement is **not letting user existence drive different responses along the same login path**. Do not accidentally return 429 only for real usernames or 500 with a stack trace for nonexistent usernames.

## 4. Where does Spring Security handle failed form login?

In a Servlet `formLogin` configuration, the typical flow is:

```text
POST /login + username/password + CSRF
       │
       ▼
CsrfFilter
  ├─ missing/invalid token → block 403, do not test password
  └─ valid
       │
       ▼
UsernamePasswordAuthenticationFilter
       │
       └─ AuthenticationManager
             │
             ├─ authentication succeeds
             │     ├─ Authenticated Authentication
             │     ├─ SessionAuthenticationStrategy / SecurityContext
             │     └─ AuthenticationSuccessHandler → target page
             │
             └─ authentication fails
                   ├─ clear SecurityContext from failed attempt
                   ├─ notify RememberMeServices.loginFail (if present)
                   └─ AuthenticationFailureHandler
                         └─ default redirect /login?error
```

**Important:** `AuthenticationFailureHandler` handles *authentication failure* after the authentication filter catches `AuthenticationException`. It does not necessarily run when `CsrfFilter` has already blocked the request, when a route gets an authorization 403, or when a reverse proxy rejects the request before it reaches the application.

### What does Spring Security typically do by default?

With `formLogin(Customizer.withDefaults())` or the equivalent DSL:

- `GET /login` has a default login page generated by Spring Security if you do not configure a custom page.
- `POST /login` receives a form with two parameters `username` and `password` (configurable to other names).
- Invalid authentication invokes `AuthenticationFailureHandler`, usually `SimpleUrlAuthenticationFailureHandler` redirecting to **`/login?error`**.
- The default login page displays a generic error message; do not render the raw framework exception stored in the request/session verbatim.
- Form login normally has CSRF protection; a valid form needs the token in POST.
- A wrong POST normally returns **302 Redirect**, and then the browser GETs `/login?error` to receive HTML. These are **two separate HTTP responses**.

Final distinction: **302 does not mean login succeeded**, because both successful and failed logins can redirect. Inspect the Location/destination and security context per configuration, rather than just checking for 3xx.

### Setting failureUrl and failureHandler

Spring Security provides two levels of customization:

```java
.formLogin(form -> form
    .failureUrl("/login?error")
    .permitAll()
)
```

This is a **fragment** inside `HttpSecurity`. `failureUrl` is used when the browser expects a redirect after failed authentication. That is also the standard form login default; stating it explicitly helps readers see the contract.

If you need a JSON API or structured logging, use a suitable `AuthenticationFailureHandler`. However, **do not map different exceptions to different URLs** such as `?reason=unknown` or `?reason=disabled`. Even if the UI renders a generic message, the URL/headers are still observable to the client.

## 5. UsernameNotFoundException, BadCredentialsException, and leaked information

Spring Security has specific authentication exception types, for example:

- `UsernameNotFoundException`: user store could not find the username.
- `BadCredentialsException`: invalid credentials.
- `DisabledException`: account disabled.
- `LockedException`: account locked.
- `AccountExpiredException` and `CredentialsExpiredException`: account/credential expiration conditions.

These classes are **useful for internal handling**. Do not use the class name or `exception.getMessage()` to produce distinct messages for public clients.

`AbstractUserDetailsAuthenticationProvider` has the `hideUserNotFoundExceptions` setting, whose typical default behavior **hides the distinction between a nonexistent username and a wrong password by throwing `BadCredentialsException`**. Customizing `setHideUserNotFoundExceptions(false)` can expose internal differences; it is even riskier if the failure handler leaks the exception message externally. Even so, hiding exceptions **does not by itself fix timing side channels** or reset-password/MFA flows.

**Do not turn exception types into public payloads.** A JSON endpoint like:

```json
{"error": "INVALID_CREDENTIALS"}
```

is better than:

```json
{"error": "USER_NOT_FOUND", "usernameExists": false}
```

However, policy decisions must consider status, headers, size, timing, and rate limiting together. Two identical JSON responses are not enough to guarantee there is no side channel.

### Do not store "last failure reason" to render raw to strangers

Some failure handlers can store `AuthenticationException` in the session/request for the login page to read. Control how the view uses that value: do not expose raw `SPRING_SECURITY_LAST_EXCEPTION.message` to users if it contains account state or internal details. In custom UIs, rely solely on the `error` flag to show a generic error; internal details can go to server-side audit logs as needed.

## 6. HTTP status codes: 302, 401, 403, 429, and 5xx

Do not have a single helper turn every error into "401" or "403"; HTTP status codes have distinct meanings.

| Common code | Valid situation | What to avoid |
| --- | --- | --- |
| **302/303** | Browser form login redirects to `/login?error` on failure | Redirecting to distinct URLs depending on whether username exists |
| **401 Unauthorized** | API authentication fails or requires credentials, depending on mechanism/entry point | Mixing 401 and 403 merely based on account existence |
| **403 Forbidden** | User is authenticated but lacks permission; or CSRF is rejected | Calling every 403 a wrong password |
| **429 Too Many Requests** | Throttling/rate limiting | Returning 429 only for real usernames and leaking accounts |
| **500/503** | Identity store failure or infrastructure incident | Returning stack traces or masking outages as "user does not exist" |

**HTTP Basic:** the authentication entry point can return `401` with `WWW-Authenticate`. **Browser form login:** the default failure handler typically returns a 302 redirect instead of 401 on POST `/login`. Both models can be right if the contract is clearly defined. A custom password-login JSON API you build may choose `401` with generic JSON; do not expect Spring form login to return JSON automatically.

When a user is already logged in and hits `/admin` without the role, 403 is usually **authorization**; that is not a "failed login" for incrementing a login failure counter. When a CSRF token is wrong, 403 is usually **CSRF validation**, and should not be recorded as a wrong password either.

### Separating internal reasons from external responses

An architecture can map:

```text
INTERNAL_REASON                     PUBLIC_RESPONSE
unknown_username                  ┐
password_mismatch                 ├── /login?error
account_disabled                  │   generic message
account_locked                    ┘
                                   (same reasonable status/location/UX)

CSRF_INVALID                       → 403 Forbidden (without checking password)
TOO_MANY_REQUESTS                  → 429 or uniform challenge
IDENTITY_STORE_UNAVAILABLE         → 503 generic service error
```

Only authorized operators view internal reasons via protected audit logs. Never send the reason via public cookies, URL query parameters, response headers, or hidden HTML elements hoping the UI will not display it.

## 7. Timing side channel: when identical answers still reveal the user

Suppose the database lacks a user and the service returns immediately after `findByUsername`. If the user exists, the server must run a CPU-intensive password hash check (such as BCrypt). After enough samples, an attacker can analyze response times statistically and infer real usernames.

```text
User absent ────────> DB lookup → generic error (fast)
User exists, bad pw ─> DB lookup → BCrypt verify → generic error (slower)
```

This is a *timing discrepancy* — identical response bodies yet different processing paths.

Mitigations:

1. Use an appropriate `PasswordEncoder` with significant password-verification cost, and never store plaintext or fast unsalted hashes like SHA-256 for passwords.
2. Consider performing **an equivalent-cost password hash check** when the username does not exist (for example, against a precomputed dummy hash), inside a securely designed authentication mechanism.
3. Avoid heavily divergent response branches, URLs, caches, and database work for existing vs. nonexistent accounts.
4. Apply appropriate throttling/monitoring to reduce an attacker's ability to gather large response samples.
5. Test latency statistically in production-equivalent environments; **do not claim constant-time just because you use BCrypt or hide exceptions**.

Spring Security handles some nonexistent-username cases internally depending on provider and version. **Do not assume the framework guarantees completely identical latency**: databases, caches, password encoders, account status, MFA, network, and custom code can still introduce differences.

**"Random sleep" is not recommended as a standalone solution.** Random delays do not fix divergent execution paths and can exhaust resources under attack. A combined solution includes proper password hashing, balanced authentication paths, traffic limits, and observability.

## 8. Lockout and rate limiting: stopping password guessing without creating new leaks

### Types of limits

- By **target account/identifier**: curbs brute force focused on one username, yet can enable *account lockout DoS* if anyone can lock another person's account.
- By **IP/subnet/ASN**: curbs bulk traffic, yet may penalize many users behind shared NAT/VPN; attackers can distribute IPs.
- By **device/session/challenge**: adds defensive signals, though self-reported cookies/device IDs are not completely trustworthy.
- By **global rate**, behavior/risk score: detects password spraying and credential stuffing across many usernames.
- **Backoff/challenge/MFA:** requires verification steps or acceptable delays based on risk assessment.

No single threshold fits every system. Choose policies based on normal load, account sensitivity, distributed bot risk, UX requirements, and user support.

### Beware of account enumeration via lockout

Dangerous example:

```text
username="alice"      → HTTP 429 "Account locked"
username="made-up"    → HTTP 302 "/login?error"
```

If only real usernames lead to a distinct 429, the rate-limit logic **becomes a new enumeration channel**. Design lock buckets, response times, and public responses to minimize divergence; never let unauthenticated clients read an account's lockout state.

**Account lockout DoS:** if hard-locking a user after 3 wrong tries can be triggered by anyone, an attacker can lock out masses of users. Consider soft rate limits, progressive challenges, safe unlock flows, and multi-signal policies. Sending notifications to the account owner's **verified channel** can help, but never use public HTTP responses to confirm a username.

### HTTP 429 and Retry-After

A rate-limited API can return `429 Too Many Requests`, sometimes with `Retry-After`. Ensure public status codes and wait times do not systematically differ between real and nonexistent accounts in equivalent situations. `Retry-After` must never contain identifiers or sensitive internal state. Spring Security **does not provide a full anti-bot solution automatically** just because you enabled `formLogin`.

## 9. Password reset, registration, and MFA can also disclose accounts

If form login is safe yet `/forgot-password` replies "This email is not registered," an attacker can still enumerate accounts through the other flow.

### Password recovery

**Responses should follow a single conditional promise:**

> If that address matches an account in our system, we will send recovery instructions per our security policy.

Avoid returning:

```text
"Email does not exist" / "Email sent"   // differs by existence
```

Recovery workflows must use random, short-lived, single-use tokens, never log tokens, enforce rate limits, and verify account security attributes. For nonexistent accounts, avoid response-time discrepancies caused by running the email workflow on only one branch; async jobs can help, though timing and observable side effects must still be checked.

### Account registration

"Email already in use" can disclose identity. Many apps balance UX and anti-enumeration depending on the product; for high-privacy systems, giving a single generic message and sending instructions via a verified email channel is worth considering.

### MFA and multi-step login

Username-first or initial-step flows can open an enumeration channel if only real users see the next step. Never display masked phone numbers, recovery emails, MFA types, memberships, or roles to someone who has not passed appropriate authentication. Once a trusted factor is verified, richer UX can be shown based on risk assessment; separate **caller trust level** from merely typing a valid username.

### OAuth2/OIDC

If the application delegates login to an Identity Provider, part of failure responses, account state, and recovery lives at the **IdP**, not Spring form login. Align disclosure policies across RP/client, IdP, and APIs. Never print full OAuth2 exceptions, `state`, authorization codes, or tokens onto error pages.

## 10. Runnable Java 17 example: form login failure with uniform response

The sample application uses **Java 17+**, **Spring Boot 3.5.12**, **Spring Security 6.x**, **Gradle 8.4+**, Spring MVC, and `BCryptPasswordEncoder`.

Scenario:

- `alice`: valid, active account, role `USER`, demo password `DemoPass123!`.
- `disabled`: real account but `disabled(true)`; shares the same demo password to test that public messages do not leak account state.
- `ghost`: username absent from `InMemoryUserDetailsManager`.
- `GET /public`: public endpoint.
- `GET /account`: endpoint requiring login.
- `POST /login`: Spring Security handles form credentials and CSRF, with no custom login controller.
- **All three** cases—*wrong password / nonexistent username / disabled*—go to `/login?error`.
- `GET /login?error`: default login page shows a generic notice; no internal exception is exposed publicly.

This project demonstrates **form login response consistency**. It does not include production-grade rate limiters, IdPs, email recovery, or timing mitigations; those real-world architectures were analyzed above.

### 10.1. File structure

```text
login-failure-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/com/example/loginfailure/
    │   ├── LoginFailureApplication.java
    │   ├── SecurityConfiguration.java
    │   └── AccountController.java
    └── test/java/com/example/loginfailure/
        └── LoginFailureSecurityTests.java
```

**`settings.gradle`**

```groovy
rootProject.name = 'login-failure-demo'
```

**`build.gradle`**

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.12'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '1.0.0'

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

Spring Boot 3.5 uses Java 17+ and supports compatible Gradle 8.x (8.4 or higher per 3.5 documentation); if using Gradle 9 or Boot 4, re-check that version's compatibility requirements. Bare `javac`/`java` commands without the Spring classpath will not compile the application; use Gradle as instructed in section 10.5.

### 10.2. Main

**`src/main/java/com/example/loginfailure/LoginFailureApplication.java`**

```java
package com.example.loginfailure;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class LoginFailureApplication {
    public static void main(String[] args) {
        SpringApplication.run(LoginFailureApplication.class, args);
    }
}
```

### 10.3. SecurityConfiguration: failure URL as a shared contract

**`src/main/java/com/example/loginfailure/SecurityConfiguration.java`**

```java
package com.example.loginfailure;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration(proxyBeanMethods = false)
public class SecurityConfiguration {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public").permitAll()
                .requestMatchers("/account").authenticated()
                .anyRequest().denyAll()
            )
            .formLogin(form -> form
                .defaultSuccessUrl("/account", true)
                .failureUrl("/login?error")
                .permitAll()
            )
            .logout(logout -> logout.permitAll())
            .build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        UserDetails alice = User.withUsername("alice")
            .password(encoder.encode("DemoPass123!"))
            .roles("USER")
            .build();

        UserDetails disabled = User.withUsername("disabled")
            .password(encoder.encode("DemoPass123!"))
            .roles("USER")
            .disabled(true)
            .build();

        return new InMemoryUserDetailsManager(alice, disabled);
    }
}
```

**Explanation of each decision:**

1. `formLogin` enables the standard login page/filter; omitting a `POST /login` controller avoids duplicate handlers.
2. `failureUrl("/login?error")` sends all form-login `AuthenticationException` types to the same public path. It never appends exception details or usernames to the URL.
3. `defaultSuccessUrl("/account", true)` is only for the demo so success redirects have a fixed target easy to test. Do not use the success path to infer errors; a failed login must never reach `/account`.
4. `permitAll()` on form login grants access to endpoints serving the login/failure page, not permission to read `/account`.
5. `anyRequest().denyAll()` blocks unclassified endpoints. If you add actuator, static assets, or other APIs, update the public/protected lists accordingly instead of using `/**.permitAll()`.
6. `BCryptPasswordEncoder` hashes demo passwords when creating the user store. Unlike `{noop}`, passwords are not stored in plaintext inside `UserDetails`, yet the exercise source code still contains sample passwords; **never deploy demo accounts to production**.
7. `.disabled(true)` provides a real account that cannot sign in; tests verify the public response does not disclose account state.
8. **Do not disable CSRF**: Spring Security Test's form login helper sends a valid CSRF token; POSTs without a token must be blocked at the CSRF filter before authentication.
9. Note when moving to production: protect password resets, multi-factor authentication, account lockouts, HTTPS, session cookies, and rate limits; the configuration above is a teaching model, not a complete defense suite.

### 10.4. Controller: never let handlers leak user existence

**`src/main/java/com/example/loginfailure/AccountController.java`**

```java
package com.example.loginfailure;

import java.security.Principal;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class AccountController {

    @GetMapping("/public")
    public String publicPage() {
        return "public";
    }

    @GetMapping("/account")
    public String account(Principal principal) {
        return "welcome " + principal.getName();
    }
}
```

`/account` only uses `Principal` after security authentication succeeds, returning `welcome alice` for the demo account. This endpoint has no `/users/exists` or `/users/{username}/status` routes for unauthenticated callers because those can create enumeration channels.

### 10.5. Running the application and testing with a browser

The machine needs **JDK 17+** and compatible **Gradle 8.4+**. In `login-failure-demo`:

```bash
gradle test
gradle bootRun
```

If a compatible Gradle Wrapper is present, use `./gradlew test` / `./gradlew bootRun` (Linux/macOS) or `gradlew.bat test` / `gradlew.bat bootRun` (Windows).

Sequence:

1. Open `http://localhost:8080/public`. Result **200**, body `public`.
2. Open `http://localhost:8080/account` while not logged in. The browser is typically redirected to `/login`.
3. Enter `alice` with any wrong password. POST /login has a CSRF token, so the response is **302 Location: /login?error**; the browser shows the login page with a generic error message.
4. Enter `ghost` with any password. The client still sees the **exact same error URL** and generic login page; there is no "username does not exist" message.
5. Enter `disabled` with `DemoPass123!`. The disabled account cannot log in, and the client is still sent to **`/login?error`**.
6. Enter `alice` / `DemoPass123!`. Successful login redirects to `/account`; the body after GET is `welcome alice`.
7. In DevTools Network, compare HTTP method/status/Location/body/headers across the three failure types. Identical UI alone **does not prove all timing differences are eliminated**; production measurements may still be needed.

### 10.6. Why not use a simple `curl -d username/password`?

The application keeps default CSRF enabled; a POST /login lacking a valid CSRF token typically receives **403** and never enters password verification. That example is invalid for proving an account was rejected due to its password:

```bash
curl -i -X POST http://localhost:8080/login \
  -d 'username=alice&password=wrong'
```

The command above may return 403 due to missing CSRF. To test form login properly with curl, you must extract the cookie/CSRF token from GET /login, maintain a cookie jar, and send the token properly, or use `MockMvc` as shown next. **Never disable CSRF just to make login test requests look convenient.**

In real applications, enforce HTTPS when sending credentials; HTTP localhost in this example is only for local learning.

### 10.7. MockMvc tests: identical failure responses, right reasons

**`src/test/java/com/example/loginfailure/LoginFailureSecurityTests.java`**

```java
package com.example.loginfailure;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestBuilders.formLogin;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.redirectedUrl;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class LoginFailureSecurityTests {

    @Autowired
    MockMvc mvc;

    private MvcResult failedLogin(String username, String password)
            throws Exception {
        return mvc.perform(formLogin().user(username).password(password))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("/login?error"))
            .andReturn();
    }

    @Test
    void anonymousCanSeeLoginPage() throws Exception {
        mvc.perform(get("/login"))
            .andExpect(status().isOk());
    }

    @Test
    void protectedPageRedirectsAnonymousToLogin() throws Exception {
        mvc.perform(get("/account"))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("http://localhost/login"));
    }

    @Test
    void wrongPasswordAndUnknownUsernameHaveSamePublicResponse()
            throws Exception {
        MvcResult wrongPassword = failedLogin("alice", "incorrect");
        MvcResult unknownUsername = failedLogin("ghost", "incorrect");

        assertEquals(
            wrongPassword.getResponse().getStatus(),
            unknownUsername.getResponse().getStatus()
        );
        assertEquals(
            wrongPassword.getResponse().getHeader("Location"),
            unknownUsername.getResponse().getHeader("Location")
        );
    }

    @Test
    void disabledAccountGetsSameFailureRedirect() throws Exception {
        MvcResult disabled = failedLogin("disabled", "DemoPass123!");
        MvcResult wrong = failedLogin("alice", "incorrect");

        assertEquals(
            wrong.getResponse().getHeader("Location"),
            disabled.getResponse().getHeader("Location")
        );
    }

    @Test
    void failedLoginPageCanBeRenderedWithoutInternalReason()
            throws Exception {
        mvc.perform(get("/login").param("error", ""))
            .andExpect(status().isOk());
    }

    @Test
    void missingCsrfIsNotAUsernameOrPasswordFailure()
            throws Exception {
        mvc.perform(post("/login")
                .param("username", "alice")
                .param("password", "DemoPass123!"))
            .andExpect(status().isForbidden());
    }

    @Test
    void validCredentialsCreateUsableAuthenticatedSession()
            throws Exception {
        MvcResult success = mvc.perform(
                formLogin().user("alice").password("DemoPass123!")
            )
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("/account"))
            .andReturn();

        MockHttpSession session =
            (MockHttpSession) success.getRequest().getSession(false);
        assertNotNull(session);

        mvc.perform(get("/account").session(session))
            .andExpect(status().isOk())
            .andExpect(content().string("welcome alice"));
    }
}
```

**What the tests demonstrate:**

- `formLogin()` from `spring-security-test` submits POST login with a **valid CSRF token**; thus the test exercises the authentication failure branch rather than getting blocked with 403 before trying the password.
- `wrongPasswordAndUnknownUsernameHaveSamePublicResponse` compares status and `Location`; `disabledAccountGetsSameFailureRedirect` additionally compares the disabled account.
- `missingCsrfIsNotAUsernameOrPasswordFailure` proves a CSRF failure yields 403 and must not be recorded as a wrong password.
- `validCredentialsCreateUsableAuthenticatedSession` proves success creates an authenticated session usable for the next `/account` request.
- Tests **do not prove constant-time behavior** because `MockMvc` is not a production statistical latency environment. Nor does this suite replace rate-limiter security tests, XSS/cookie tests, or recovery/MFA tests.

### 10.8. A test adjustment if entry point/redirect differs

In Spring Security Servlet, unauthenticated `GET /account` usually returns a redirect to the login page (potentially a full URL like `http://localhost/login` in `MockHttpServletResponse`). With custom entry points, hosts, proxies, or context paths, the `Location` value may differ; when testing another app, check redirect matchers intentionally instead of hardcoding the wrong URL. For instance, `redirectedUrl("http://localhost/login")` relies on default redirect behavior in MockMvc; with a different version or redirect strategy, keep the test meaning "directs to the login page" rather than changing production policy just to make a test pass.

## 11. When JSON is needed instead of a redirect: custom AuthenticationFailureHandler

Browser form apps rightly use redirects. Yet a JSON login API may need a **401 + consistent JSON** response instead of a 302 to HTML:

```json
{"error":"invalid_credentials"}
```

An **optional fragment**, separate from the runnable demo in section 10:

```java
.formLogin(form -> form
    .failureHandler((request, response, exception) -> {
        response.setStatus(401);
        response.setContentType("application/json;charset=UTF-8");
        response.setHeader("Cache-Control", "no-store");
        response.getWriter().write(
            "{\"error\":\"invalid_credentials\"}"
        );
    })
)
```

This **is not a complete REST/JWT login API** and must not be pasted over the sample `SecurityConfiguration.java` without updating tests. The fragment merely shows how to standardize a **public failure response**. Never include `exception.getMessage()`, `exception.getClass().getSimpleName()`, or `request.getParameter("username")` in the returned JSON.

For APIs, choose login/OAuth2/OIDC mechanisms suited to the actual architecture, consistent response Content-Type, CSRF policies if browsers auto-send credentials, rate limits, `no-store`, and client UX handling. If a JSON login endpoint needs different behavior from browser forms, clearly define separate `SecurityFilterChain`s, matchers, and entry points rather than using one ad-hoc handler for all requests.

**HTTP Basic differs from POST form login:** APIs using `httpBasic()` usually signal authentication failure via `AuthenticationEntryPoint`/`WWW-Authenticate`, not `formLogin.failureHandler(...)`. For bearer access tokens, `BearerTokenAuthenticationEntryPoint` and OAuth2 Resource Server have their own token error rules. Test the exact mechanism rather than assuming all login errors flow through the same handler.

## 12. Organizing audit logs without leaking secrets

Public messages must be minimal, yet operations still need enough facts to detect attacks and support users:

- **Event type:** `authentication_failure`, `authentication_success`, `csrf_rejection`, `rate_limit_triggered`.
- **Timestamp, request ID, bounded source metadata:** helps correlate events without logging request bodies.
- **Sufficient internal context:** reason categories can be allowed in **protected** audit logs; manage retention and log access permissions.
- **Anti-bot signals:** failure rates, multiple usernames on the same network signal, device distribution, and IP reputation where lawful and privacy-compliant.

**Never log:** passwords, OTPs, access/refresh tokens, session cookies, raw Authorization headers, full form bodies, recovery tokens, or stack traces containing secrets. Do not treat an unkeyed hash of an email as "completely anonymous," because email/username spaces are guessable and hashes can be dictionary-reversed; if event correlation is needed while limiting PII, use keyed pseudonymization with managed keys and clear retention.

Do not pass an **audit failure reason** from the server down to response headers/clients for "debugging convenience." Operators can query by request ID with proper authorization.

### Do not distinguish accounts via public monitoring endpoints

An unauthenticated metrics dashboard/API returning "failed_password_for_existing_users" or reset-mail queue sizes per username can recreate enumeration, even if form login is safe. Protect metrics/tracing, minimize detail in public responses, and audit supporting channels like helpdesks/chatbots.

## 13. Login response testing checklist

During a review or authorized pentest, construct these request groups:

| Group | Request | What to compare |
| --- | --- | --- |
| A | Existing user, wrong password | status, Location, body, headers, cookies, timing |
| B | Nonexistent user, any password | compare against A |
| C | Disabled/locked user, right or wrong password | compare against A/B per disclosure policy |
| D | Missing CSRF token | classified 403; must not trigger password attempt |
| E | Valid user/password | success, session, fixation protection |
| F | Many attempts, multiple IPs/devices/usernames | rate limit/challenge must not leak existence |
| G | Forgot password/registration/activation | messages and side effects must not leak accounts |
| H | MFA/SSO/IdP error | do not disclose account state when caller lacks trust |

**Testing guidelines:**

1. Only test in authorized environments/accounts, avoiding locking out real users.
2. Compare responses across the **entire HTTP lifecycle**: POST and redirect GET; not just the DOM.
3. Test responses with/without cookies, step-by-step login, disabled accounts, different roles, localization, and custom error handlers.
4. Measure timing methodically with enough samples under uniform conditions without generating harmful traffic; filter out reasonable network/cache noise.
5. Check reset/signup/MFA and post-rate-limiting behavior, because other branches can reintroduce enumeration channels.
6. Verify safe logging and the presence of credential-guessing limits at gateways/backends.
7. Clearly record *what was tested* and *what was not*: a status/location unit test does not prove the whole system is immune to enumeration.

## 14. Common mistakes and fixes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Returning "Account does not exist" | Leaks account existence | Generic message |
| Returning "Wrong password" only for real usernames | Easy to enumerate | Standardize response |
| Same UI text, different status/Location | Alternative observable channel | Compare HTTP status/headers/redirects too |
| Putting `exception.getMessage()` on login page | Leaks internals/account state | Use generic error flag, log audit reason on server |
| Disabling `hideUserNotFoundExceptions` and exposing exception | Distinguishes unknown user vs. bad password | Keep indistinguishable behavior; review provider |
| Nonexistent user returns much faster | Timing oracle | Balance auth path, test timing, throttle |
| Only real accounts get 429/lockout banner | Creates new enumeration | Design throttling/UX without leaking existence |
| Hard-locking accounts after very few failures | Attackers cause account-lockout DoS | Adaptive limits/challenges + safe recovery |
| Counting 403 CSRF in wrong-password metrics | Misattributes cause, causes false lockouts | Separate CsrfFilter from auth failure |
| Treating 403 insufficient role as login failure | Wrong event/UX | Separate authorization from authentication |
| Disabling CSRF to simplify curl POST login | Increases CSRF risk | Use `formLogin()` test helper/cookie+token |
| Not testing disabled/unknown accounts | Misses leaky branches | Test the failure-case matrix |
| Logging passwords/tokens/sessions | Secret leaks via monitoring | Redact, enforce retention, least privilege |
| Reset page replies "email already registered" | Leaks via another flow | Generic reply, send details via verified channel |
| Switching form redirect to JSON while keeping old tests | Client/API contract mismatch | Separate policy, update tests to match mechanism |
| Thinking a generic message alone stops enumeration | Ignores timing/rate-limit/MFA/IdP | Test all observable behavior |

## 15. Self-check questions

**1.** Why is "This email does not exist" a dangerous response on failed login?

**Answer:** because an unauthenticated party can determine whether the email is in the system, aiding phishing, password spraying, or targeted attacks.

**2.** What does Spring Security's default form login typically do when credentials are wrong?

**Answer:** `AuthenticationFailureHandler` is called and usually redirects to `/login?error`; the login page displays a generic message without returning raw internal exceptions.

**3.** Does HTTP 302 on `POST /login` prove authentication succeeded?

**Answer:** no. Both successful and failed logins can redirect; check `Location` and the security context.

**4.** Should you return 404 when username does not exist, and 401 when password is wrong?

**Answer:** no, if both are the same authentication attempt; differing statuses create account enumeration even if bodies match.

**5.** Why does POST /login without a CSRF token returning 403 not mean the password is wrong?

**Answer:** `CsrfFilter` can block the request before `UsernamePasswordAuthenticationFilter`, so credentials were never checked.

**6.** Does `hideUserNotFoundExceptions` solve all account enumeration?

**Answer:** no. It reduces exception-type differences, yet timing, body, recovery, lockouts, and MFA can still leak.

**7.** If only real accounts hit a 429 rate limit, what can happen?

**Answer:** the status and rate-limit threshold can reveal existence; limit design must avoid creating such public differences.

**8.** Why can permanently locking an account after a few failures backfire?

**Answer:** an attacker can intentionally block legitimate users from signing in; anti-guessing policies must account for denial-of-service.

**9.** Should a downed identity store error be masked as "wrong password"?

**Answer:** no. Fail closed and return a generic service error; what matters is not leaking stack traces/secrets and not tying status to account existence.

**10.** Why does testing identical Location for unknown username and wrong password not prove protection against timing enumeration?

**Answer:** it checks only one part of the HTTP response. Two branches can still have different latencies, especially when one runs BCrypt and the other does not.

**11.** Does browser login failure always return 401?

**Answer:** no. Form login can return a 302 redirect to an error page, while APIs/HTTP Basic typically use 401. Consider the specific authentication mechanism.

**12.** Is displaying `SPRING_SECURITY_LAST_EXCEPTION.message` on a custom login page safe?

**Answer:** not recommended, because the exception can contain account state or internal details. Render a generic message and keep the reason in backend audit logs.

**13.** If a user forgets their password, should you announce "email sent" only when the email exists?

**Answer:** for use cases requiring anti-enumeration, no. Use a generic conditional message, verify the email, and issue tokens server-side per policy.

**14.** After a user logs in successfully, hits an endpoint without enough roles, and gets 403, should the wrong-password counter increment?

**Answer:** no. That is an authorization failure, not an invalid-credentials attempt.

## 16. Conclusion

- Login failure responses are part of **identity security**, not merely UX.
- Keep **one generic public message** for unknown usernames, wrong passwords, and account states that must be hidden, and avoid leaking via HTTP status, Location, body, headers, or cookies.
- In Spring Security Servlet, **`AuthenticationFailureHandler`** handles form authentication failures; by default it usually **redirects to `/login?error`**. `CsrfFilter` blocks requests missing tokens before the password-check stage.
- `AbstractUserDetailsAuthenticationProvider` typically **hides `UsernameNotFoundException`** behind a generic credentials error, yet does not solve all timing side channels.
- Combine anti-enumeration with **secure password hashing, thoughtful throttling, non-leaking recovery/MFA, secure audit logs, and tests**.
- Do not accidentally introduce new leaks through **lockouts, 429, password reset, disabled accounts, JWT/IdP**, or exposed exception messages.
- The Java/MockMvc example proves part of the form-login contract; production assessment requires testing HTTPS, timing, bot controls, and all related identity flows.

### References

- Spring Security — Form Login: https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/form.html
- Spring Security — FormLoginConfigurer and failureUrl/failureHandler API: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/config/annotation/web/configurers/FormLoginConfigurer.html
- Spring Security — AbstractUserDetailsAuthenticationProvider: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/dao/AbstractUserDetailsAuthenticationProvider.html
- Spring Security — Testing Form-Based Authentication: https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/form-login.html
- Spring Security — Testing CSRF: https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/csrf.html
- Spring Security — Security HTTP error handling: https://docs.spring.io/spring-security/reference/servlet/architecture.html
- Spring Boot 3.5 — System Requirements: https://docs.spring.io/spring-boot/3.5/system-requirements.html
- OWASP Authentication Cheat Sheet — Authentication Responses and Error Messages: https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html
- OWASP Forgot Password Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html
- OWASP Credential Stuffing Prevention Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Credential_Stuffing_Prevention_Cheat_Sheet.html
