# Version Requirements and Support Scope for One-Time Token Login

**One-Time Token Login (OTT Login)** is a sign-in mechanism using a **single-use token** natively supported by Spring Security starting in **Spring Security 6.4**. The user enters an identifier such as a username/email, the system generates a short-lived token and sends it over a dedicated channel (typically an email containing a *magic link*). Whoever holds the valid, unexpired token submits it back to sign in; after successful consumption, **that exact token cannot be reused**.

This lesson focuses on two integration questions: **(1) Which Java/Spring Boot/Spring Security versions qualify to use the built-in API? (2) What does the framework already provide, and what must the application implement itself?** This is especially important because the name OTT is easily confused with OTP/TOTP, two-factor authentication, or Bearer tokens, whereas their feature scopes differ.

The examples use **Java 17+**, **Spring Boot 3.5.x**, **Spring Security 6.5.x patched for the corresponding vulnerability**, and a **Servlet/MVC** application. The Java packages/methods below are verified against the Spring Security 6.4/6.5 API; WebFlux applications are also supported but have a **different reactive API**.

## 1. What One-Time Token Is and What It Is Not

| Mechanism | How It Works | Is It the OTT Login Feature? |
| --- | --- | --- |
| **Spring Security OTT** | The server generates a single-use token bound to a user, with an expiration, delivers it over a separate channel, and consumes it to establish a login session | **Yes** |
| **Magic link** | A way to deliver a token as a link; the user opens the link and completes sign-in | Usually an **OTT delivery method**, not the name of a new token type |
| **TOTP** | A code from an authenticator based on a pre-shared secret and time, e.g. RFC 6238 | **No**; requires a separate TOTP mechanism |
| **HOTP** | A code generated from a shared secret and counter, e.g. RFC 4226 | **No**; requires a separate HOTP mechanism |
| **App-built SMS/email OTP** | May be a custom-designed code, not necessarily using the Spring OTT service | Not by default; must be decided and integrated |
| **OAuth2 Bearer access token/JWT** | A token used to call APIs, which can be reused multiple times while valid | **Not** OTT Login |
| **Password reset token** | Proves permission to change a password, with a different purpose from login | **No** by default |
| **MFA/2FA** | Requires an additional independent authentication factor beyond the primary factor | **Not automatically**; OTT is a login method by default, not automatically a second factor |

**OTT does not require the user to configure a TOTP secret beforehand** or install an authenticator app; it depends on the token delivery channel and how the application verifies the recipient. If an email account is compromised, someone else can receive the magic link. Therefore, "passwordless" **does not mean** "immune to phishing/account takeover".

OTT can be a **passwordless login** method, but on its own it only proves possession of the token at consumption time; anti-fraud controls, initial email verification, device trust, or MFA must be designed additionally by the system.

## 2. Minimum Versions and Compatibility Matrix

### 2.1. Spring Security Is the Version That Determines the API

| Spring Security Version | Built-In One-Time Token Login | Meaning |
| --- | --- | --- |
| **6.3.x and older** | **No built-in OTT DSL as described here** | Cannot copy `http.oneTimeTokenLogin(...)` and expect it to compile; must upgrade or build another solution |
| **6.4.x** | **Yes**, this is the branch that introduced OTT into the framework | Servlet and reactive have separate APIs; check patches/security advisories for the exact version |
| **6.5.x** | **Yes** | Continues OTT support; adds ability to customize request generation via `GenerateOneTimeTokenRequestResolver`; prefer patches that fix related security bugs |
| **7.0.x and subsequent 7.x branches** | **Yes** | The OTT API still exists; foundational Spring Framework/Boot changes and extension points must be checked against the Javadoc of the version in use |

**Official introduction point:** `OneTimeToken`, `OneTimeTokenService`, `OneTimeTokenAuthenticationProvider`, `OneTimeTokenLoginConfigurer`, and the corresponding reactive APIs carry `Since: 6.4` in Javadoc. Do not mistake an outdated article for checking the project's actual dependencies.

### 2.2. Which Version Does Spring Boot Manage?

In a Spring Boot project, dependency management/BOM usually determines the specific Spring Security version; do not infer the Security version merely from an annotation or import.

| Spring Boot Line | Spring Security at the Start of the Corresponding Line | OTT Usage Recommendation |
| --- | --- | --- |
| **3.3.x** | Typically **6.3.x** | **Does not yet have** the 6.4 OTT DSL by default; using it requires a compatible upgrade plan, not just adding a line of Java |
| **3.4.x** | Typically **6.4.x** | Supports OTT from the framework, but must check **patches** for Security and dependencies |
| **3.5.x** | Typically **6.5.x** | Supports OTT with more convenient configuration APIs; requires a patched version if using JDBC OTT |
| **4.x** | Corresponding Spring Security **7.x** line | Has OTT, but must check migration guides and exact-version APIs; do not mechanically copy 6.x config |

These are **relationships of the release lines at launch**, not a promise that every Boot patch brings a fixed Security patch. Practical governance requires **printing the resolved dependency tree**.

A **Java 17+** application is the appropriate foundation for Spring Boot 3.x/Spring Security 6.x. With Java 8 or 11, the Boot 3/Security 6 stack cannot be used in standard configuration. Having Java 17 source code in the project **is not enough** if the build is pulling Spring Security 6.3 or if Spring Security modules have mixed versions.

### 2.3. Checking the Actual Version in the Project

For a Gradle Spring Boot project:

~~~bash
./gradlew dependencyInsight \
  --dependency spring-security-config \
  --configuration runtimeClasspath

./gradlew dependencyInsight \
  --dependency spring-security-web \
  --configuration runtimeClasspath

./gradlew dependencyInsight \
  --dependency spring-security-core \
  --configuration runtimeClasspath

./gradlew --version
~~~

On Windows PowerShell/CMD, use `gradlew.bat` instead of `./gradlew`. For Maven:

~~~bash
mvn dependency:tree -Dincludes=org.springframework.security
mvn --version
~~~

You must check the **resolved version**, not just `build.gradle`/`pom.xml`: dependency overrides, platforms, or the Spring Boot plugin can affect the result. The dependency tree must be consistent; do not select `spring-security-web:6.5` while keeping `spring-security-config:6.3` and expect the DSL to work.

**Signs of meeting the requirements:** the project compiles `http.oneTimeTokenLogin(...)` and the classes in `org.springframework.security.authentication.ott.*`; the dependency tree shows Spring Security **>=6.4** and a safe patch version for the chosen storage. If the IDE reports `Cannot resolve method 'oneTimeTokenLogin'`, check the **Spring Security config module and JDK** before writing a manual filter.

### 2.4. Security Patch Requirement When Using JDBC OTT

An official advisory dated **2026-04-21**, **CVE-2026-22751**, describes a **TOCTOU** race condition in `JdbcOneTimeTokenService`: multiple concurrent requests using the same token could all complete login, violating the single-use expectation.

| Spring Security Line | Affected Versions per Advisory | Published Fixed Version |
| --- | --- | --- |
| 6.4.x | 6.4.0 – 6.4.15 | **6.4.16** (*Enterprise Support Only*) |
| 6.5.x | 6.5.0 – 6.5.9 | **6.5.10** |
| 7.0.x | 7.0.0 – 7.0.4 | **7.0.5** |

The advisory explicitly states that **`InMemoryOneTimeTokenService` by default is not affected by this vulnerability**, whereas applications that **explicitly configure `JdbcOneTimeTokenService`** on an affected version are at risk. Do not infer that merely switching to in-memory storage is sufficient for multi-node production; that is a separate architectural decision.

**Recommendation for new systems:** prefer a maintained branch and current security patch, at minimum ensuring you do not use a JDBC OTT version in the affected list. Do not rely on the label `Spring Boot 3.5` to assume Spring Security is already on `6.5.10+`; verify the resolved dependency lock/BOM. You do not need and should not write your own non-atomic token deletion workaround when an official patch is available.

## 3. Support Scope: Servlet and Reactive Have Different APIs

| Layer | **Servlet / Spring MVC** | **Reactive / Spring WebFlux** |
| --- | --- | --- |
| Security configuration | `HttpSecurity` | `ServerHttpSecurity` |
| Filter chain bean | `SecurityFilterChain` | `SecurityWebFilterChain` |
| DSL | `http.oneTimeTokenLogin(...)` | `http.oneTimeTokenLogin(...)` on `ServerHttpSecurity` |
| Token generation/consumption service | `OneTimeTokenService` | `ReactiveOneTimeTokenService` |
| In-memory default | `InMemoryOneTimeTokenService` | `InMemoryReactiveOneTimeTokenService` |
| Token delivery handler | `OneTimeTokenGenerationSuccessHandler` | `ServerOneTimeTokenGenerationSuccessHandler` |
| Request handler objects | `HttpServletRequest`, `HttpServletResponse` | `ServerWebExchange` and Reactor `Mono<Void>` |
| Token generation filter | `GenerateOneTimeTokenFilter` | `GenerateOneTimeTokenWebFilter` |
| Token receiving filter | `OneTimeTokenAuthenticationFilter` | Corresponding OTT filter in WebFlux |
| Login style | Web/browser session + Servlet Security OTT endpoints | WebFlux login/session + reactive OTT filters |

Both stacks have One-Time Token Login documentation starting in the 6.4 branch, but **you cannot port a Servlet handler implementation to WebFlux** because the signatures differ. In particular, `OneTimeTokenService#generate` returns `OneTimeToken` synchronously, whereas `ReactiveOneTimeTokenService#generate` returns `Mono<OneTimeToken>`. Choose the web or webflux starter matching the real environment, and do not mix the two filter chains.

**Do not interpret "Spring Security supports OTT" to mean the framework automatically sends emails/SMS or integrates every IdP.** This is an **in-application authentication login mechanism**, not a federated OAuth2/OIDC or WebAuthn protocol enabled for free.

## 4. Framework-Provided Components vs. What Must Be Implemented

### 4.1. What Is Built In When Enabling the DSL

Spring Security Servlet provides:

1. **Token generation request filter**: processes `POST /ott/generate` by default.
2. **One-time token object/service**: creates a token bound to a username and expiration; `OneTimeTokenService#generate(...)` and `#consume(...)`.
3. **Token consumption filter**: processes login requests to `POST /login/ott` by default. It is not an auto-login GET magic link; a submit page can pre-fill the token for the user to submit.
4. **Authentication provider**: uses the consumed token and loads the corresponding account via `UserDetailsService`.
5. **Default login/submit page** depending on the DSL and UI configuration; can be combined with `formLogin()` or replaced with the application's UI.
6. **Standard SecurityContext/session** after successful authentication; the user does not need to keep the OTT to send on every API request like an OAuth2 access token.

**Purpose of the token:** provide a single-use proof of control to initiate authentication. After consuming the token, subsequent requests use the application's configured authentication/session storage mechanism, **not reusing the OTT**.

### 4.2. What Is Not Automatically Provided

| Item | Why It Must Be Self-Implemented |
| --- | --- |
| **Token delivery via email/SMS** | The framework does not know which account owns which mailbox/phone number, nor does it know the delivery infrastructure |
| **Recipient verification** | A username/email declared by the requester does not prove ownership; must look up the verified address in the user store |
| **Email template and magic link** | Must construct a trusted base URL, content, and UX |
| **Rate limiting / abuse prevention** | Prevent bulk email sending, account scanning, and spam |
| **Anti-user-enumeration** | Return uniform responses even when the identifier does not exist |
| **Durable multi-node storage** | Default in-memory storage is not shared across instances and is lost on restart |
| **Account policies** | Locked/disabled state, email/tenant verification, privilege restrictions |
| **Monitoring and audit** | Track failed requests/consumptions, without logging tokens |
| **MFA, strong phishing resistance, device binding** | Standalone OTT does not add those properties automatically |

Important: a **token delivery handler** is usually a mandatory integration piece. The Servlet `OneTimeTokenGenerationSuccessHandler` interface has the method:

~~~java
void handle(
    HttpServletRequest request,
    HttpServletResponse response,
    OneTimeToken oneTimeToken
) throws IOException, ServletException;
~~~

This is **a method signature inside an interface**, not a standalone Java class. `OneTimeToken` has `getTokenValue()`, `getUsername()`, and `getExpiresAt()`. When sending email, only use the **previously verified email address** corresponding to `getUsername()`, and never send to an arbitrary unconfirmed address supplied by the caller.

## 5. OTT Application Flow by Proper Responsibility

~~~text
User enters identifier on the login page
          │ sends POST /ott/generate + CSRF token
          ▼
GenerateOneTimeTokenFilter (Servlet)
          │
          ▼
OneTimeTokenService.generate(GenerateOneTimeTokenRequest)
          │ creates token: username + random token + expiresAt
          ▼
OneTimeTokenGenerationSuccessHandler (application-owned)
          │ looks up trusted mailbox; sends Magic Link over external channel
          ▼
User opens link GET /login/ott?token=...
          │ submit page pre-fills token; GET does not authenticate yet
          ▼
POST /login/ott (token + CSRF token)
          │
          ▼
OneTimeTokenAuthenticationFilter
          │
          ▼
OneTimeTokenAuthenticationProvider
          │ calls OneTimeTokenService.consume(...)
          ├── token missing / already used / expired → reject
          │
          └── valid token + valid user
                   │ loads UserDetails/authorities
                   ▼
           Authenticated SecurityContext
                   │
                   ▼
           Redirect to protected page/login session
~~~

Here, the default paths and GET/POST handling are specifics of **Servlet OTT Login**; do not use it like a Bearer API `Authorization: Bearer ...`. When changing URLs via the DSL, update the form, CSRF, magic link, and redirect path under the same contract.

### Why Not Return the Token in the Response to the Requester?

If a user simply enters `victim@example.test` and the server returns the token immediately in the HTTP response, an attacker could also enter that email and obtain the token to sign in as the victim. Therefore, the token must go to an **out-of-band channel** controlled by the account owner (or an equivalently designed verification channel). In production, do not log the token and do not display the token on the confirmation page.

### Why Does CSRF Still Matter?

The OTT generation and consumption endpoints use HTTP POST; when CSRF is enabled, POST requests from a browser typically must carry a valid CSRF token. Spring Security's default forms support CSRF as configured; if you write your own frontend, you must send the CSRF token properly. **Do not disable CSRF for the whole application just because POST /ott/generate returns 403 when testing with curl.** Distinguish 403 due to missing CSRF from rate-limiting errors and expired-token errors.

## 6. Minimal Java 17+ Example with Spring Boot 3.5 / Patched Spring Security 6.5

The Servlet example below demonstrates a complete **OTT-only** configuration that generates a magic link and sends it to a test mailbox. It uses a **localhost SMTP sink** so learners can observe the email in a lab environment; it will not work end-to-end without a configured mail server or if using non-existent emails/recipients.

Prerequisites:

- JDK **17+**.
- Spring Boot **3.5.x** with Spring Security **6.5.10+** resolved when using JDBC OTT; the example uses **in-memory**.
- A project with the Spring Boot plugin/BOM and Gradle wrapper.
- An SMTP test server listening at `127.0.0.1:1025`, lab mailbox `student@example.test`.
- Browser access via `http://localhost:8080` in local environments only; production requires HTTPS and appropriate public DNS.

### 6.1. Dependencies

Snippet in `build.gradle` (Groovy DSL, placed inside an existing Spring Boot project):

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-mail'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

`spring-boot-starter-mail` provides `JavaMailSender`; if you wire the filter/handler without configuring SMTP, the app may fail with a bean error or fail when sending mail. The OAuth2 Resource Server starter is not required for this OTT lesson, because OTT is **not** JWT Bearer authentication.

### 6.2. Application Configuration

`src/main/resources/application.properties`:

~~~properties
server.port=8080
spring.mail.host=127.0.0.1
spring.mail.port=1025
app.ott.public-base-url=http://localhost:8080
~~~

These values are for local use only. Production must obtain `public-base-url` from trusted configuration, use HTTPS and a canonical hostname, and **must not build login links from client-controlled Host/X-Forwarded-Host headers**.

### 6.3. Application and Security Configuration

File `src/main/java/example/ott/OttDemoApplication.java`:

~~~java
package example.ott;

import java.util.Map;
import java.util.UUID;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.mail.SimpleMailMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.security.authentication.ott.OneTimeToken;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.ott.OneTimeTokenGenerationSuccessHandler;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.util.UriComponentsBuilder;

@SpringBootApplication
public class OttDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(OttDemoApplication.class, args);
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            OneTimeTokenGenerationSuccessHandler mailHandler)
            throws Exception {

        http.authorizeHttpRequests(auth -> auth
                .requestMatchers("/ott/sent").permitAll()
                .anyRequest().authenticated());

        http.oneTimeTokenLogin(ott -> ott
                .tokenGenerationSuccessHandler(mailHandler));

        // Do not enable formLogin in this OTT-only example.
        // Keep default CSRF protection for POST forms.
        return http.build();
    }

    @Bean
    UserDetailsService userDetailsService() {
        // Single lab user only. Random password avoids fixed credentials
        // if someone later enables formLogin.
        String unknownPassword = UUID.randomUUID().toString();
        UserDetails student = User.withUsername("student")
                .password("{bcrypt}" + new BCryptPasswordEncoder()
                        .encode(unknownPassword))
                .roles("USER")
                .build();
        return new InMemoryUserDetailsManager(student);
    }

    @Bean
    OneTimeTokenGenerationSuccessHandler mailHandler(
            JavaMailSender sender,
            @Value("${app.ott.public-base-url}") String publicBaseUrl) {

        // Demo: map account -> verified mailbox.
        // Production: retrieve mapping from the user database.
        Map<String, String> registeredEmails =
                Map.of("student", "student@example.test");

        return (request, response, token) -> {
            String recipient = registeredEmails.get(token.getUsername());

            if (recipient != null) {
                String magicLink = UriComponentsBuilder
                        .fromUriString(publicBaseUrl)
                        .path("/login/ott")
                        .queryParam("token", token.getTokenValue())
                        .build()
                        .encode()
                        .toUriString();

                SimpleMailMessage email = new SimpleMailMessage();
                email.setFrom("no-reply@example.test");
                email.setTo(recipient);
                email.setSubject("Your one-time login link");
                email.setText("Open this single-use link before expiry: "
                        + magicLink);
                sender.send(email);
            }

            // Do not reveal whether the username exists.
            response.sendRedirect(request.getContextPath() + "/ott/sent");
        };
    }
}

@RestController
class DemoPages {
    @GetMapping("/ott/sent")
    String sent() {
        return "If the account exists, check your inbox.";
    }

    @GetMapping("/private")
    String privatePage() {
        return "Signed in.";
    }
}
~~~

**Why is the code structured this way?**

1. `HttpSecurity.oneTimeTokenLogin(...)` is the built-in DSL since 6.4, instead of writing custom authentication filter/password reset logic.
2. The `OneTimeTokenGenerationSuccessHandler` bean matches the Servlet method signature; the handler sends the token over SMTP rather than returning it in the HTTP body. It does not use the host name from the request, avoiding creating magic links pointing to an attacker-supplied host.
3. `UserDetailsService` provides the user/roles after the token is validated. The lab account `student` is mapped to a test email, while unmapped users are not sent a token. Production requires a real user database, locking policies, and email-verified checks.
4. `formLogin` is not enabled so the example stays **OTT-only**. If you want **both password + OTT**, you can add `formLogin(Customizer.withDefaults())` after ensuring accounts have separate credential/password policies and testing both flows.
5. `anyRequest().authenticated()` protects `/private`; `/ott/sent` is permitted to display the generic message.
6. CSRF is not disabled; the browser must use forms/CSRF properly. There is no need to turn the magic link into an auto-authenticating GET endpoint; GET `/login/ott?token=...` leads to the submit page, while login is processed via POST.
7. Token data is kept in-memory by default, so the demo app is suitable only for **a single instance** and loses unused tokens on restart.

The file contains one public class `OttDemoApplication`, in the same package as `DemoPages`. The remaining classes come from Spring Boot/Framework/Security 6.5 and the mail starter. There is no custom controller handling POST `/ott/generate` or `/login/ott` because the filters created by the DSL handle them.

### 6.4. Running and Testing

In a project with the Gradle wrapper:

~~~bash
./gradlew bootRun
~~~

On Windows:

~~~powershell
.\gradlew.bat bootRun
~~~

Browser testing steps while the SMTP sink is running:

1. Open `http://localhost:8080/login` to use the default login page or the OTT request page of the current Security configuration.
2. Enter username `student` in the **One-Time Token** form and submit it; Spring Security generates a token and the handler sends an email to the test mailbox.
3. Open the magic link received from the test SMTP server. The `/login/ott` page displays the token/submit form.
4. Submit the form; after the valid token is consumed, visiting `/private` will display:

~~~text
Signed in.
~~~

5. Sign out or use another browser session and retry the **same old token**; the result must be rejected. Trying an expired token must also be rejected. If you are already signed in within the current session, visiting `/private` can still succeed because **the session is still valid**, not because the token was reusable.

**Do not use a curl POST command without a CSRF token to conclude that OTT does not work.** In the default configuration, a request without a valid CSRF token may receive 403 before reaching OTT generation/consumption logic. Do not print real tokens to consoles, logs, or public screenshots.

### 6.5. A Unit Test Verifying Single-Use and Expiry

With the `spring-boot-starter-test`/JUnit Jupiter dependency, you can test the **in-memory service** independently of email, UI, and HTTP. File `src/test/java/example/ott/OneTimeTokenServiceTest.java`:

~~~java
package example.ott;

import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneOffset;

import org.junit.jupiter.api.Test;
import org.springframework.security.authentication.ott.GenerateOneTimeTokenRequest;
import org.springframework.security.authentication.ott.InMemoryOneTimeTokenService;
import org.springframework.security.authentication.ott.OneTimeToken;
import org.springframework.security.authentication.ott.OneTimeTokenAuthenticationToken;

import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;

class OneTimeTokenServiceTest {

    @Test
    void tokenCanBeConsumedOnlyOnce() {
        InMemoryOneTimeTokenService service =
                new InMemoryOneTimeTokenService();

        OneTimeToken token = service.generate(
                new GenerateOneTimeTokenRequest(
                        "student", Duration.ofMinutes(5)));

        assertNotNull(service.consume(
                new OneTimeTokenAuthenticationToken(
                        token.getTokenValue())));

        assertNull(service.consume(
                new OneTimeTokenAuthenticationToken(
                        token.getTokenValue())));
    }

    @Test
    void expiredTokenCannotBeConsumed() {
        InMemoryOneTimeTokenService service =
                new InMemoryOneTimeTokenService();

        Clock start = Clock.fixed(
                Instant.parse("2026-11-06T00:00:00Z"),
                ZoneOffset.UTC);
        service.setClock(start);

        OneTimeToken token = service.generate(
                new GenerateOneTimeTokenRequest(
                        "student", Duration.ofMinutes(1)));

        service.setClock(
                Clock.offset(start, Duration.ofMinutes(2)));

        assertNull(service.consume(
                new OneTimeTokenAuthenticationToken(
                        token.getTokenValue())));
    }
}
~~~

Run the test:

~~~bash
./gradlew test --tests example.ott.OneTimeTokenServiceTest
~~~

The test uses `setClock`, so it does not depend on CI wall-clock time. If the assumptions hold, both tests pass and Gradle reports a successful build; detailed output varies by plugin version. This **only tests `InMemoryOneTimeTokenService`**; it does **not** prove that `JdbcOneTimeTokenService` prevents race conditions under 2+ concurrent requests, nor does it test SMTP mail delivery or browser CSRF. For JDBC, you must add multi-threaded/multi-instance integration tests and use a patched framework version.

## 7. Token Storage Scope and Deployment Environments

### 7.1. When to Use the Default InMemoryOneTimeTokenService?

**Suitable for:**

- Workshops and local demos.
- Single-instance applications that accept losing unused tokens on restart.
- Unit tests verifying single-use/expiry mechanics.

**Limitations:**

- Stored in the current instance's RAM, not shared across nodes; a generate request hitting node A and a verify request hitting node B can fail.
- If the application restarts, unused tokens can be lost.
- Does not provide high availability/durability the way a database does.
- Because tokens are tied to service state, do not treat them like a **stateless JWT** whose signature any node can verify independently.

Spring Security uses `InMemoryOneTimeTokenService` by default for Servlet when no other `OneTimeTokenService` is configured. Reactive also has `InMemoryReactiveOneTimeTokenService` but does not share the synchronous Java interface/methods.

### 7.2. JDBC and Clustered Deployment

`JdbcOneTimeTokenService` stores tokens in a database via `JdbcOperations` and a table following Spring Security's schema. This is better suited for multiple replicas **if** all instances share the data store and consumption is atomic on a patched version.

Do not just add a JDBC bean and consider it done. You need to:

- Create the schema according to the documentation of the **exact Spring Security version**.
- Use a version patched for **CVE-2026-22751** if on the listed branches.
- Test 2–N **concurrent** requests with the same token: at most one request is authenticated; the rest fail.
- Verify TTL, cleanup, transaction/isolation, clock sync across nodes, database availability, and retry handling.
- Protect token data in the database, backups, and logs according to policy; a token is a **short-lived credential**, not harmless data.

**Concurrency bugs are not caught by sequential tests** such as "1st consume succeeds, 2nd consume fails". That test only proves single-use when requests arrive one after another. In TOCTOU, two parallel requests can both see the token before deletion. Therefore, you need a race test with a barrier/multiple workers verifying **exactly one successful authentication**.

## 8. Customizing Expiration and API Differences Between 6.4 and 6.5

In Spring Security documentation defaults, an OTT request has a **lifetime of about 5 minutes**. This is the value of the token-generation mechanism, not the post-login session lifetime. The actual lifetime should be verified via `GenerateOneTimeTokenRequest#getExpiresIn()` and the chosen service's policy.

Starting in 6.5, Spring Security added the `GenerateOneTimeTokenRequestResolver` extension point in the DSL, letting applications customize the request before generation; the default Servlet class is `DefaultGenerateOneTimeTokenRequestResolver`.

*Additional configuration snippet* example, applicable **when the version has the corresponding resolver API**:

~~~java
import java.time.Duration;
import org.springframework.context.annotation.Bean;
import org.springframework.security.web.authentication.ott.DefaultGenerateOneTimeTokenRequestResolver;
import org.springframework.security.web.authentication.ott.GenerateOneTimeTokenRequestResolver;

// Place inside a @Configuration class.
@Bean
GenerateOneTimeTokenRequestResolver generateOneTimeTokenRequestResolver() {
    DefaultGenerateOneTimeTokenRequestResolver resolver =
            new DefaultGenerateOneTimeTokenRequestResolver();
    resolver.setExpiresIn(Duration.ofMinutes(10));
    return resolver;
}
~~~

This is a **configuration member snippet**, not a standalone Java file with imports outside an existing class. Use it only on versions with the verified API; do not apply it blindly to 6.4. If using a custom service/provider, test the actual expiration at both generation and consumption steps.

Changing TTL from 5 to 10 minutes **increases the exposure window if a token leaks**. Choose TTL based on email/SMS delivery path, real latency, user interaction capability, and sensitivity level. Do not change OTP/JWT expirations assuming OTT uses the same policy.

### API Changes: Method Names Must Follow Javadoc

Different documentation versions/pages show different DSL sample names when customizing endpoints. For Servlet `OneTimeTokenLoginConfigurer` in the 6.4/6.5 branch, the Javadoc-verified methods are:

~~~java
http.oneTimeTokenLogin(ott -> ott
        .tokenGeneratingUrl("/ott/request")
        .loginProcessingUrl("/login/ott")
        .tokenGenerationSuccessHandler(mailHandler));
~~~

This is a **configuration snippet inside a `SecurityFilterChain` method that already has `http` and `mailHandler` variables**, not a standalone class. When changing default URLs, the request UI and magic link must match. Do not copy method names from WebFlux examples in another branch and assume they will compile.

### Servlet and WebFlux Do Not Share Handlers

**Servlet:**

~~~java
OneTimeTokenGenerationSuccessHandler handler =
        (request, response, oneTimeToken) -> {
            response.sendRedirect(request.getContextPath() + "/ott/sent");
        };
~~~

This example illustrates the method signature and **does not yet provide delivery**, so it must not be used alone as a production handler.

**Reactive/WebFlux:** the corresponding interface `ServerOneTimeTokenGenerationSuccessHandler` takes `ServerWebExchange` and `OneTimeToken`, returning `Mono<Void>`. The service is `ReactiveOneTimeTokenService`. If using Spring WebFlux, write a handler that does not block the event loop, such as integrating mail delivery via a suitable reactive client/service; do not call blocking SMTP send directly on the event loop.

## 9. Security Boundaries and Production Operating Conditions

### 9.1. Token Generation Must Be Paired with Identity Binding

If the endpoint accepts a username/email entered by an unauthenticated caller:

- Only send to a **verified address**, retrieved from internal user data; do not use `request.getParameter("email")` as the destination without checking.
- Do not reveal whether an account exists through response status, message, noticeable timing differences, or redirect names.
- Enforce rate limiting by IP/account/device, cooldowns, and email-bombing protection.
- Limit the number of active tokens, define a policy to invalidate old tokens on reissue, and cap requests and failed attempts.
- Check locked/disabled/tenant/login-policy status at **token consumption** time, not only at generation request time.

Recent version documentation notes that `OneTimeTokenAuthenticationProvider` **does not automatically treat every account status flag as a rejection condition**, such as locked/disabled/expired; `AccountStatusUserDetailsChecker` can be added via `setUserDetailsChecker(...)` in supported versions. Do not rely on an untested assumption: have a test for "disabled account + valid OTT → still rejected" on the version you operate.

### 9.2. Keeping the Magic Link Secret

A magic link usually carries the token in the query string `/login/ott?token=...`. This is convenient but risks being copied via history, screenshots, analytics, reverse proxy logs, referrer, or browser extensions.

Measures to consider:

- HTTPS for the token-receiving page; disallow HTTP channels in production.
- Do not embed third-party analytics/assets on pages containing the token; configure an appropriate `Referrer-Policy: no-referrer`.
- Do not store raw tokens in access logs, APM, or error reports; redact the `token` query parameter.
- Limit TTL; consume tokens via POST, do not auto-login on GET.
- Plan for email readers that automatically scan magic links: a simple GET to view the page should not invalidate the token.
- Do not put the token into an email forwarded to others as if it were a harmless verification code.

### 9.3. Do Not Treat OTT as MFA Without Explicit Design

A single OTT login via email is one factor dependent on **control of the email account**. For MFA, you need an additional independent authentication policy and binding between steps to the same user/session under a concrete threat model. Calling `/ott/generate` after password entry **does not automatically create secure MFA** without first-step verification, session fixation protection, and step-by-step authentication state control.

### 9.4. Login Session and Logout

OTT is used to **initiate Authentication**, not as an access token used on every request. A consumed token **cannot be reused**, but the session created after the previous login can continue until logout or expiration. Therefore:

- Reusing an old OTT must fail even while a browser still holds a session.
- Logout should clear the appropriate session and browser/session tokens, without implicitly preventing a new email token from being generated later.
- Do not equate OTT expiration with session expiration; they are two different lifetimes.
- If an account is locked after login, a separate policy is needed to revoke active sessions and application privileges.

## 10. Test Matrix for Version Requirements and Support Scope

| ID | Check | Expected Result |
| --- | --- | --- |
| V01 | Spring Security 6.3 project calls `oneTimeTokenLogin` | No built-in DSL; verify dependencies instead of guessing |
| V02 | Boot 3.4 + Spring Security 6.4.x resolved | Has Servlet/Reactive DSL and OTT core APIs |
| V03 | Boot 3.5 + Spring Security 6.5.x resolved | Has OTT DSL and resolver customization per corresponding API |
| V04 | Security core/config/web modules have mismatched versions | Unreliable build; must align versions |
| V05 | Reactive app uses Servlet `SecurityFilterChain` and handler | Wrong stack; must use `SecurityWebFilterChain` and reactive API |
| V06 | OTT-only Servlet app without a real mail handler integrated | No delivery path for users to complete login |
| V07 | GET magic link after token creation | Shows submit page; not auto-consumed just by opening GET |
| V08 | First POST token submit | Succeeds if token is unexpired and matches user and policy |
| V09 | Resubmitting the same token after consumption | Fails |
| V10 | Submitting token after `expiresAt` | Fails |
| V11 | Two parallel requests with the same token, using JDBC store | **At most one** authentication succeeds; requires CVE-patched version |
| V12 | Running multiple instances with unshared in-memory store | Token missing on other nodes; fails default HA |
| V13 | Non-existent user requests a token | Response does not leak user existence; no token sent to arbitrary address |
| V14 | Disabled/locked user has a valid token | Rejected per configured and tested account policy |
| V15 | Form POST without CSRF token, CSRF enabled | Blocked by CSRF; do not disable system-wide |
| V16 | Token leaked via logs/referrer/screenshot | Detection/mitigation process; tokens never appear in telemetry |
| V17 | No OTP authenticator installed yet TOTP is desired | OTT does not automatically provide TOTP/HOTP |
| V18 | Sending OTT in Authorization Bearer on every API request | Not the default OTT Login model |
| V19 | SMTP fails, mailbox unreachable | Do not create login session just because token was generated; handle delivery failure and retry safely |
| V20 | Spring Security JDBC 6.5.9, concurrency test | In the affected version list; must upgrade before production |

### Reading Test Results Correctly

- A passing test of `InMemoryOneTimeTokenService` does not prove correctness of database transactions.
- A request to `/ott/generate` returning a redirect does not prove the email was delivered to the right user.
- A GET magic link returning HTTP 200 does not prove Authentication succeeded; POST submit and SecurityContext/session verification are required.
- An already-logged-in user viewing `/private` when trying an old token does not prove the token is reusable. Test the token in an **unauthenticated** session or test the service directly.
- Using `curl` without CSRF can return 403 even when OTT code is correct; browser tests must obtain the CSRF token properly.

## 11. Common Mistakes When Upgrading OTT

| Symptom | Common Cause | Resolution |
| --- | --- | --- |
| `Cannot resolve method oneTimeTokenLogin` | Spring Security prior to 6.4 or missing config module | Check dependency tree, upgrade to matching Boot/Security |
| IDE sees class but runtime build fails | Mismatched Spring Security module versions | Let BOM manage artifact alignment |
| No email is sent | Missing handler, wrong SMTP config, or unmapped user email | Check `OneTimeTokenGenerationSuccessHandler` and SMTP sink |
| OTP authenticator does not generate compatible codes | Confusing OTT with TOTP/HOTP | Use a standards-compliant OTP solution |
| Right link but token rejected | Expired, already used, different node, lost state on restart, wrong URL | Check expiresAt, storage, and endpoints |
| Calling endpoint from SPA gets 403 | Missing CSRF token or wrong URL/form | Integrate standard CSRF properly; do not disable blindly |
| One JDBC token logs in twice under race | Using a version affected by CVE-2026-22751 | Upgrade to patched version, test concurrency |
| Local test passes but cluster fails | Per-instance in-memory store | Choose shared storage and verify atomic consume |
| Link points to unfamiliar domain | Building magic link from arbitrary Host header | Use environment-fixed public base URL |
| Disabled account still has a session | Account status not checked or old sessions not revoked | Add checker/policy and integration tests |
| Token appears in access log | Query param logged verbatim | Redact token, adjust logging and Referrer-Policy |
| Form login still works unexpectedly | Mixing `formLogin` and OTT | Decide clearly between passwordless-only or alongside password |

## 12. How to Make Implementation Decisions

**Use built-in OTT when:** a web application needs passwordless login via a verified mailbox/phone number; running Spring Security **>=6.4**; and having a secure token delivery layer, user storage, CSRF, and appropriate login sessions.

**Do not deploy OTT immediately when:** still on Java 8/11 + Boot 2.x/Security 5.x and unable to upgrade; lacking a reliable token delivery channel; the requirement is TOTP/MFA without an integration design; or a multi-node system needs safe single-use storage without upgrading to a patched JDBC version.

**Choosing Servlet vs. Reactive:** base this on the running web architecture. MVC uses `HttpSecurity` + `OneTimeTokenService`; WebFlux uses `ServerHttpSecurity` + `ReactiveOneTimeTokenService`. User behavior is similar, but code and threading policies differ.

**Choosing a store:** in-memory for learning/single node; JDBC/synchronized storage in a cluster must use a patched version and test concurrent consumption. Never use a database just for "production" while ignoring the right security patch version.

### Final Checklist

- [ ] Verified Java >=17, Spring Security >=6.4, and Boot/Security modules on compatible lines.
- [ ] If JDBC OTT: verified the patch fixing CVE-2026-22751.
- [ ] Selected the right Servlet or Reactive stack without mixing DSLs/handlers.
- [ ] Understand how OTT differs from TOTP/HOTP, JWT Bearer, password-reset, and MFA.
- [ ] Have a `OneTimeTokenGenerationSuccessHandler` / `ServerOneTimeTokenGenerationSuccessHandler` performing real token delivery.
- [ ] User mailbox/phone is verified; anti-enumeration and rate limiting are implemented.
- [ ] Have HTTPS, CSRF, token-leak prevention in URLs/logs, and reasonable TTL.
- [ ] Storage matches node count, with sequential and concurrent tests for single-use and expiry.
- [ ] User status checks, session revocation when needed, and post-login authorization tests are in place.
- [ ] Tested SMTP failures, expired/used tokens, node restarts, race conditions, and non-existent users.

## 13. Official References

- [Spring Security 6.5 — Servlet One-Time Token Login](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/onetimetoken.html)
- [Spring Security 6.5 — Reactive One-Time Token Login](https://docs.spring.io/spring-security/reference/6.5/reactive/authentication/onetimetoken.html)
- [Spring Security 6.4 — OneTimeTokenLoginConfigurer API](https://docs.spring.io/spring-security/site/docs/6.4.x/api/org/springframework/security/config/annotation/web/configurers/ott/OneTimeTokenLoginConfigurer.html)
- [Spring Security — OneTimeTokenService API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/ott/OneTimeTokenService.html)
- [Spring Security 6.5 — What's New](https://docs.spring.io/spring-security/reference/6.5/whats-new.html)
- [Spring Boot 3.4 Release Notes: Spring Security 6.4](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-3.4-Release-Notes)
- [Spring Boot 3.5 Release Notes: Spring Security 6.5](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-3.5-Release-Notes)
- [CVE-2026-22751 — Spring Security JdbcOneTimeTokenService one-time-token reuse](https://spring.io/security/cve-2026-22751)
