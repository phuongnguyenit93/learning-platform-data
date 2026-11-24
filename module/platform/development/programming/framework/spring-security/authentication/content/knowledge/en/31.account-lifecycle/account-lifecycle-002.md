# Password Policies and Input Validation Responses

An account management application cannot secure passwords with just an “uppercase + digit + special character” regex. Across the **account lifecycle**, the same secret appears during registration, password change, account recovery, and sign-in. Each step must combine an **appropriate password policy**, **input validation**, **secure hash storage**, and **HTTP responses that do not leak sensitive information**.

This lesson targets **Java 17+, Spring Boot 3.x, Spring Security 6.x, and Spring MVC/Servlet**. The focus is on choosing length and blocklist policies, handling Unicode, using `PasswordEncoder`, combining `@Valid`/Jakarta Validation with domain checks, building error responses with stable codes, and distinguishing messages for **setting a new password** from messages for **login/recovery** to prevent account enumeration.

## 1. Where Do Password Policies Fit in the Account Lifecycle?

| Step | Primary checks | Safe response |
| --- | --- | --- |
| **Registration** | Valid username/email; strong new password not on blocklist; DB uniqueness; contact verification | Explain *new-password* errors while avoiding confirming whether the email/account exists |
| **Password change** | Authenticated user; verify current password or step-up; new password meets policy; transactional update | Show specific policy feedback to the account owner; never include passwords or hashes in errors |
| **Forgot password** | Random, short-lived, single-use reset token; verify registered channel; policy on the new password | On reset request: “If a matching account exists, we will send instructions” |
| **Sign-in** | Use `PasswordEncoder.matches`; rate limiting; account status; MFA/session policy | Return a **generic** message when username/password is wrong or the account cannot sign in |
| **Account lock/risk review** | Monitor attacks, detect credential compromise, require password change when warranted | Avoid exposing account status on public endpoints |
| **Account deletion** | Verify authorization, revoke sessions/tokens, delete/handle password hashes and related data per policy | Never return secrets or internal details |

**Password policies** primarily validate **new passwords** during creation, change, or reset. During **login**, the system should compare against the stored hash and trigger a migration flow when needed; do not apply a brand-new password policy directly to legacy users and return “your password is 10 characters long” before authentication.

Distinguish three kinds of data:

- **Password** is a user-held secret; never log it, echo it back, or store it in plaintext.
- **Username/email** is an identifier: it usually has separate validation and may require canonicalization to enforce uniqueness.
- **Password hash** is sensitive data that must be protected in the DB; it is not an encrypted password that can be decrypted.

## 2. NIST SP 800-63B-4 Reference Standard

NIST SP 800-63B-4 (published in 2025) updates guidance for **centrally verified passwords**. It serves as a reference baseline; systems must also satisfy industry regulations, contractual obligations, and actual authentication assurance requirements.

| Requirement/Recommendation | Action to take |
| --- | --- |
| Password used as the **sole authentication factor** | Require at least **15 characters** |
| Password used **only within mandatory MFA** | May use a lower threshold, but still **at least 8 characters** |
| Maximum supported length | Should allow **at least 64 characters** so users can set long passphrases |
| Accepted characters | Allow printable characters, **spaces**, and Unicode; support pasting and password managers |
| Composition rules | **Do not** force combinations of uppercase, lowercase, digits, or special characters |
| Blocklist | Check the **entire password** against common, predictable, and previously breached passwords |
| Periodic password rotation | Do not require arbitrary periodic changes without evidence of compromise |
| Online authentication | Must rate-limit failed attempts and defend against brute force and credential stuffing |
| Unicode normalization | Should apply **NFC** consistently before hashing and checking |

**Do not misinterpret the MFA condition:** merely offering *optional* MFA does not mean every login enforces two factors. If a user still has a password-only login path, enforce the 15-character minimum for single-factor access.

### 2.1. Why Not Use Regexes Requiring Special Characters?

A password like `Password1!Password1!` has uppercase, digits, and special characters and looks long, yet is highly predictable. A long secret phrase made only of lowercase letters and spaces can be much harder to guess. Composition rules also push users toward predictable habits like appending `!` at the end. Therefore:

1. Encourage **long, unique passphrases not reused** across services.
2. Check the entire normalized value against a controlled **blocklist**.
3. Allow password managers, autofill, and paste.
4. Rate-limit login attempts on the server.
5. Do not force users to rotate passwords every 30/60/90 days without a security reason.

**Never use example passwords or usernames from code snippets as production secrets.** Any illustrative string can be guessed by attackers.

### 2.2. Unicode, Characters, and Byte Counts

Java's `String.length()` counts **UTF-16 code units**, not Unicode code points; an emoji often occupies two code units. `codePointCount(0, s.length())` counts code points. `s.getBytes(StandardCharsets.UTF_8).length` counts bytes. For characters with multiple combining marks, the number of code points does not always match user-perceived grapheme clusters either.

In this example, the rule is **15–128 Unicode code points after NFC normalization**. This is a programming convention that must be documented clearly. More importantly, **the exact same normalization** must be applied during registration, change/reset, and login `matches`.

**Do not arbitrarily `trim()`, `strip()`, lowercase, or truncate passwords.** Those transformations can collapse two distinct secrets into one. Usernames, on the other hand, may have separate trimming/case normalization rules if defined by the identity policy.

### 2.3. Upper Bounds and Hashing Algorithms

Recommending support for at least 64 characters does not mean accepting multi-megabyte JSON bodies. Enforce:

- a max length in the password policy (e.g., 128 code points);
- an HTTP request size limit before the server parses the payload;
- an early raw length check before running expensive hashing algorithms;
- a database column sized properly for the **encoded hash** and algorithm metadata.

Some bcrypt implementations process at most **72 input bytes**, so if you allow long Unicode passphrases while using bcrypt, you must understand your library's actual limit and **never silently truncate passwords**. The Java example below uses PBKDF2. For legacy systems using bcrypt, evaluate byte lengths, handling of long passwords, and an explicit migration plan.

## 3. Blocklists and Compromised Passwords

A length of 15 is not enough if a user picks `passwordpassword` or `123456789012345`. A blocklist must check the **complete password value**:

- Common, sequential, repetitive, and easily guessed strings.
- Values known to appear in breach corpuses.
- Application names, organization names, usernames, domains, and obvious predictable variants.

**Avoid regexes that ban a substring.** A passphrase containing the word `spring` in the middle is not automatically weak just because it is a dictionary word.

Spring Security 6.x provides the `CompromisedPasswordChecker` interface and `HaveIBeenPwnedRestApiPasswordChecker`; `CompromisedPasswordDecision#isCompromised()` can be checked when a user **sets a new password**. Example snippet inside a service with an injected `compromisedPasswordChecker`:

~~~java
CompromisedPasswordDecision decision =
        compromisedPasswordChecker.check(proposedPassword);
if (decision.isCompromised()) {
    throw new IllegalArgumentException(
            "Choose a different, uncompromised password");
}
~~~

This is only an **in-method snippet**; do not expose `IllegalArgumentException.getMessage()` directly as an HTTP error. Translate it into an error code such as `COMMON_PASSWORD` and a whitelisted message.

The runnable local example below uses a **three-string mock blocklist** so tests run without Internet access. It is **not** sufficient for a production blocklist. In production, use an appropriate compromised-password source, handle timeouts/outages, apply privacy safeguards, and cache responsibly. Never send plaintext passwords carelessly to external services, and never log passwords when the checker fails.

**Note:** Spring Security can wire `CompromisedPasswordChecker` into some `DaoAuthenticationProvider` login configurations; that **does not automatically add checks** to custom `/register` endpoints you write. New-password checks must still be invoked in registration/change/reset services.

## 4. Storing Passwords with PasswordEncoder

Keep these paths clearly separated:

~~~text
New password submitted
   ├─ Input/DTO validation
   ├─ Domain password policy, breach blocklist
   ├─ Consistent Unicode normalization
   ▼
PasswordEncoder.encode(...)
   ▼
Salted hash + algorithm parameters stored in DB

Sign-in:
password input → same normalization → PasswordEncoder.matches(...)
                                         │
                             against stored hash
                                         ▼
                   UserDetailsService / DaoAuthenticationProvider
                                         │
                   account status, MFA, authorization, session
~~~

`UserDetailsService`/`UserDetails` loads accounts for Spring Security; `DaoAuthenticationProvider` typically uses `PasswordEncoder` to verify passwords. The policy for setting a new password is **separate business logic**: Spring Security does not enforce it just because a `UserDetailsService` exists.

**Never** store plaintext passwords, Base64-encoded strings, fast unsalted hashes like MD5/SHA-256, or `{noop}` in production. Adaptive password hashing such as PBKDF2, bcrypt, scrypt, or Argon2 requires a salt, work factor, and benchmarking on real infrastructure.

Example using Spring Security 6.5 APIs:

~~~java
PasswordEncoder encoder =
        Pbkdf2PasswordEncoder.defaultsForSpringSecurity_v5_8();

String hash = encoder.encode("Long and private passphrase 2026");

System.out.println(encoder.matches(
        "Long and private passphrase 2026", hash));
System.out.println(encoder.matches("Wrong password", hash));
~~~

This is an **in-method snippet** importing `PasswordEncoder` and `Pbkdf2PasswordEncoder`; stdout of the last two lines is:

~~~text
true
false
~~~

Hashes are salted, so the `hash` string varies each time. Never compare `encoder.encode(input).equals(storedHash)`, because `encode` generates a random salt.

### 4.1. DelegatingPasswordEncoder and Migration

`PasswordEncoderFactories.createDelegatingPasswordEncoder()` creates an encoder that stores hashes in `{id}encodedPassword` format. By default it may **encode using bcrypt** while supporting verification across multiple algorithms; therefore check the 72-byte ceiling if your application allows long passphrases. To encode new hashes with PBKDF2 while still verifying legacy bcrypt hashes, configure:

~~~java
Map<String, PasswordEncoder> implementations = new HashMap<>();
implementations.put("pbkdf2@SpringSecurity_v5_8",
        Pbkdf2PasswordEncoder.defaultsForSpringSecurity_v5_8());
implementations.put("bcrypt", new BCryptPasswordEncoder());

PasswordEncoder encoder = new DelegatingPasswordEncoder(
        "pbkdf2@SpringSecurity_v5_8", implementations);
~~~

This is a snippet: add imports from `java.util.*` and `org.springframework.security.crypto.password.*`, and place it in an appropriate bean/configuration class. New hashes carry the `{pbkdf2@SpringSecurity_v5_8}` prefix. Legacy hashes missing an `{id}` prefix must be migrated in a controlled manner; never configure `NoOpPasswordEncoder` as a fallback just to silence errors. Hashing cost must also be tuned and monitored before deployment.

## 5. Validation Responses: When Is Detailed Feedback Allowed?

| Scenario | Typical HTTP | Appropriate response |
| --- | --- | --- |
| Malformed JSON syntax | 400 | `MALFORMED_JSON`, do not return parser stack trace |
| Missing or malformed username/password field | 400 | `INPUT_INVALID` + controlled field/code/message |
| **New password** too short | 400 or 422 per contract | `PASSWORD_POLICY_REJECTED` + `TOO_SHORT` |
| **New password** on blocklist | 400 or 422 | `COMMON_PASSWORD` + prompt to choose a different secret |
| Registering an existing username/email | Depends on anti-enumeration policy | Generic response; do not confirm whether the account exists |
| Login with wrong password/username | 401 | “Invalid login credentials.” |
| Insufficient permissions after auth | 403 | “You do not have permission to perform this action.” |
| Invalid CSRF when app uses cookies | 403 | Message asking to refresh the form/request |
| Rate limited | 429 | Ask to retry later, without leaking account state |
| Breach checker unreachable | Per outage policy, possibly 503 | Do not silently treat the password as safe |

**Detailed feedback is allowed about the password a user is choosing** during account setup: for example, “Use at least 15 characters.” However, **never** display “this user exists but is locked” or “right username, wrong password” on public login endpoints.

Example response using **Problem Details (RFC 9457)**:

~~~json
{
  "type": "about:blank",
  "title": "Invalid input data",
  "status": 400,
  "detail": "Please check the highlighted fields.",
  "code": "PASSWORD_POLICY_REJECTED",
  "errors": [
    {
      "field": "password",
      "code": "TOO_SHORT",
      "message": "Please use at least 15 characters."
    }
  ]
}
~~~

**Never return** `rejectedValue`, plaintext passwords, stored hashes, exception stack traces, raw SQL constraints, or the full request body. Validation frameworks typically expose `FieldError.getRejectedValue()`: if you serialize the raw `BindingResult` or log `MethodArgumentNotValidException`/request DTOs, the password can leak into HTTP responses or logs.

### 5.1. Validation Layers in Spring MVC

- `@Valid @RequestBody RegisterRequest` + Jakarta Validation: validates the DTO (required fields, username pattern). Failures typically raise `MethodArgumentNotValidException`.
- `PasswordPolicy` in the service layer: checks Unicode code-point length, blocklist, and max size; throws a business exception without secret values.
- Database: enforces uniqueness via a UNIQUE constraint and transaction, preventing two concurrent requests from registering the same username.
- If a controller places constraints **directly on method parameters** (Spring MVC 6.1+), `HandlerMethodValidationException` may be thrown; a production API should map both validation exception types.
- Unparseable JSON triggers `HttpMessageNotReadableException`: handle with a generic 400 response, never exposing raw parser errors to the client.

For Unicode passwords, `@Size(min=15)` uses Java string length semantics and is **not always** equivalent to 15 Unicode code points. Therefore, the example uses `@NotNull` on the DTO password field, while the service counts code points after NFC normalization.

## 6. Example: Spring Boot 3.5 / Spring Security 6.5 / Java 17+

The example creates **one public JSON registration endpoint** that validates password policy, hashes with PBKDF2, and returns structured error codes. The app stores accounts in a `ConcurrentHashMap` for demonstration and returns the same `202 Accepted` whether the username already exists or not. **It has no login, email confirmation, production database, rate limiting, or session revocation**; do not copy it as-is into production.

### 6.1. Dependencies

In a Spring Boot 3.5.x Gradle project with the plugin/BOM and Java 17+:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-validation'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

### 6.2. Complete Source File

File `src/main/java/example/account/PasswordPolicyApplication.java`:

~~~java
package example.account;

import java.text.Normalizer;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;

import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.http.ProblemDetail;
import org.springframework.http.ResponseEntity;
import org.springframework.http.converter.HttpMessageNotReadableException;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.crypto.password.Pbkdf2PasswordEncoder;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.stereotype.Component;
import org.springframework.stereotype.Service;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@SpringBootApplication
public class PasswordPolicyApplication {
    public static void main(String[] args) {
        SpringApplication.run(PasswordPolicyApplication.class, args);
    }
}

@Configuration(proxyBeanMethods = false)
class AccountSecurityConfig {
    @Bean
    PasswordEncoder passwordEncoder() {
        return Pbkdf2PasswordEncoder.defaultsForSpringSecurity_v5_8();
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        http.authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.POST, "/api/accounts/register")
                    .permitAll()
                .anyRequest().denyAll());

        // Exempt CSRF only for the lab's stateless public JSON endpoint.
        // Do not disable CSRF for remaining form/session endpoints.
        http.csrf(csrf -> csrf.ignoringRequestMatchers(
                "/api/accounts/register"));

        return http.build();
    }
}

record RegisterRequest(
        @NotBlank
        @Pattern(regexp = "[A-Za-z0-9._-]{3,40}")
        String username,
        @NotNull String password) {
}

record FieldIssue(String field, String code, String message) {
}

class PasswordRejectedException extends RuntimeException {
    private final List<FieldIssue> issues;

    PasswordRejectedException(List<FieldIssue> issues) {
        super("Password policy rejected");
        this.issues = List.copyOf(issues); // Contains no raw password.
    }

    List<FieldIssue> issues() {
        return issues;
    }
}

@Component
class PasswordPolicy {
    private static final Set<String> DEMO_BLOCKLIST = Set.of(
            "passwordpassword",
            "123456789012345",
            "qwertyqwertyqwerty"
    );

    String normalizeAndValidate(String raw) {
        if (raw == null) {
            throw new PasswordRejectedException(List.of(
                    new FieldIssue("password", "REQUIRED",
                            "Password must not be blank.")));
        }

        // Reject oversized input before normalizing/hashing.
        if (raw.length() > 1024) {
            throw new PasswordRejectedException(List.of(
                    new FieldIssue("password", "TOO_LONG",
                            "Password exceeds maximum allowed length.")));
        }

        String value = Normalizer.normalize(raw, Normalizer.Form.NFC);
        int codePoints = value.codePointCount(0, value.length());
        List<FieldIssue> issues = new ArrayList<>();

        if (codePoints < 15) {
            issues.add(new FieldIssue("password", "TOO_SHORT",
                    "Please use at least 15 characters."));
        }
        if (codePoints > 128) {
            issues.add(new FieldIssue("password", "TOO_LONG",
                    "Password must be at most 128 characters."));
        }
        if (value.isBlank()
                || value.codePoints().anyMatch(Character::isISOControl)) {
            issues.add(new FieldIssue("password", "UNSUITABLE",
                    "Please choose a passphrase with valid content."));
        }

        // Lowercase only for blocklist lookup; do not alter secret before hashing.
        if (DEMO_BLOCKLIST.contains(value.toLowerCase(Locale.ROOT))) {
            issues.add(new FieldIssue("password", "COMMON_PASSWORD",
                    "Password is too predictable. Please choose another."));
        }

        if (!issues.isEmpty()) {
            throw new PasswordRejectedException(issues);
        }
        return value;
    }
}

@Component
class DemoAccountStore {
    private final Map<String, String> storedHashes =
            new ConcurrentHashMap<>();

    void insertIfAbsent(String username, String encodedHash) {
        storedHashes.putIfAbsent(username, encodedHash);
    }
}

@Service
class RegistrationService {
    private final PasswordPolicy policy;
    private final PasswordEncoder encoder;
    private final DemoAccountStore store;

    RegistrationService(PasswordPolicy policy,
                        PasswordEncoder encoder,
                        DemoAccountStore store) {
        this.policy = policy;
        this.encoder = encoder;
        this.store = store;
    }

    void register(RegisterRequest request) {
        String normalized = policy.normalizeAndValidate(
                request.password());
        String encoded = encoder.encode(normalized);
        store.insertIfAbsent(request.username(), encoded);
    }
}

@RestController
class RegistrationController {
    private final RegistrationService service;

    RegistrationController(RegistrationService service) {
        this.service = service;
    }

    @PostMapping("/api/accounts/register")
    ResponseEntity<Map<String, String>> register(
            @Valid @RequestBody RegisterRequest request) {
        service.register(request);
        // Do not reveal whether the username already exists.
        return ResponseEntity.accepted().body(Map.of(
                "status", "RECEIVED",
                "message", "Request has been received."));
    }
}

@RestControllerAdvice
class SafeRegistrationErrors {

    @ExceptionHandler(PasswordRejectedException.class)
    ResponseEntity<ProblemDetail> rejected(PasswordRejectedException e) {
        return ResponseEntity.badRequest().body(problem(
                "PASSWORD_POLICY_REJECTED", e.issues()));
    }

    @ExceptionHandler(MethodArgumentNotValidException.class)
    ResponseEntity<ProblemDetail> badRequest(
            MethodArgumentNotValidException e) {
        Map<String, FieldIssue> unique = new LinkedHashMap<>();
        e.getBindingResult().getFieldErrors().forEach(error -> {
            String field = error.getField();
            unique.putIfAbsent(field, new FieldIssue(
                    field, "INVALID_FIELD",
                    "password".equals(field)
                            ? "Password is required."
                            : "Username is invalid."));
        });
        // DO NOT use error.getRejectedValue() or e.getMessage().
        return ResponseEntity.badRequest().body(problem(
                "INPUT_INVALID", List.copyOf(unique.values())));
    }

    @ExceptionHandler(HttpMessageNotReadableException.class)
    ResponseEntity<ProblemDetail> malformed(
            HttpMessageNotReadableException ignored) {
        return ResponseEntity.badRequest().body(problem(
                "MALFORMED_JSON", List.of()));
    }

    private ProblemDetail problem(String code, List<FieldIssue> errors) {
        ProblemDetail value =
                ProblemDetail.forStatus(HttpStatus.BAD_REQUEST);
        value.setTitle("Invalid input data");
        value.setDetail("Please check the highlighted fields.");
        value.setProperty("code", code);
        value.setProperty("errors", errors);
        return value;
    }
}
~~~

**Code analysis:**

1. `RegisterRequest` validates `username` with Bean Validation and requires `password` to be non-null. The regex constraint applies to **username**, without violating the rule against password composition rules.
2. `PasswordPolicy.normalizeAndValidate` applies NFC normalization and checks code-point count, min/max bounds, control characters, and the mock blocklist. The same function must be used when creating, changing, or resetting passwords; login must also normalize with the same rule **before** `PasswordEncoder.matches`.
3. `PasswordRejectedException` carries only `FieldIssue` items, never the user-entered password.
4. `Pbkdf2PasswordEncoder` hashes the password after validation; `DemoAccountStore` only keeps hashes in RAM for testing and is not a real repository. Production needs DB migrations, unique constraints, and account verification.
5. `RegistrationController` returns the same `202` for new and existing usernames; it does not claim the account was activated or an email was sent. Production needs contact verification and anti-enumeration timing controls.
6. `SafeRegistrationErrors` returns only whitelisted fields, codes, and messages. Never call `getRejectedValue()` or send Bean Validation objects or stack traces over the network.
7. `SecurityFilterChain` permits public POST registration and denies all other routes. CSRF is exempted only for the **lab's stateless/public** endpoint; cookie/session browser apps must enforce CSRF according to their architecture.
8. There is no `UserDetailsService` or login controller in this demo because the focus is **policy + registration feedback**; production must wire the account store into an authentication provider and manage the full lifecycle.

### 6.3. Running the Sample

In a Spring Boot 3.5/JDK 17 project with the Gradle wrapper:

~~~bash
./gradlew bootRun
~~~

On Windows use `gradlew.bat bootRun`. Create a lab-only test file `register-test.json`:

~~~json
{
  "username": "student-01",
  "password": "Long and private passphrase 2026"
}
~~~

Send the request to localhost (demo only; production uses HTTPS and never stores plaintext secrets on disk):

~~~bash
curl -i \
  -H "Content-Type: application/json" \
  --data-binary @register-test.json \
  http://localhost:8080/api/accounts/register
~~~

When the project runs properly, the expected result is **HTTP 202** with body:

~~~json
{
  "status": "RECEIVED",
  "message": "Request has been received."
}
~~~

Changing the password in the test file to `short` must reject the request with **HTTP 400**, `code=PASSWORD_POLICY_REJECTED`, and an error `password: TOO_SHORT`. For malformed JSON, the error code is `MALFORMED_JSON`. Never use real passwords or tokens in demo files or access logs.

### 6.4. Policy Unit Tests

File `src/test/java/example/account/PasswordPolicyTest.java`:

~~~java
package example.account;

import java.text.Normalizer;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.*;

class PasswordPolicyTest {
    private final PasswordPolicy policy = new PasswordPolicy();

    @Test
    void rejectsShortPassword() {
        PasswordRejectedException e = assertThrows(
                PasswordRejectedException.class,
                () -> policy.normalizeAndValidate("short"));
        assertEquals("TOO_SHORT", e.issues().get(0).code());
    }

    @Test
    void rejectsCommonPassword() {
        PasswordRejectedException e = assertThrows(
                PasswordRejectedException.class,
                () -> policy.normalizeAndValidate(
                        "passwordpassword"));
        assertTrue(e.issues().stream().anyMatch(
                issue -> "COMMON_PASSWORD".equals(issue.code())));
    }

    @Test
    void acceptsLongPassphraseWithoutSpecialCharacters() {
        String value = "A long and unique passphrase";
        assertEquals(value, policy.normalizeAndValidate(value));
    }

    @Test
    void appliesNfcNormalization() {
        String decomposed = "Cafe\u0301 a very long secret phrase";
        String expected = Normalizer.normalize(
                decomposed, Normalizer.Form.NFC);
        assertEquals(expected, policy.normalizeAndValidate(decomposed));
    }
}
~~~

`\u0301` is the combining acute accent in Java source; the test ensures input strings are normalized to NFC. Tests use JUnit Jupiter from starter-test and do not start a Spring context.

### 6.5. HTTP Tests Verifying Safe Responses

File `src/test/java/example/account/RegistrationHttpTest.java`:

~~~java
package example.account;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest
@AutoConfigureMockMvc
class RegistrationHttpTest {

    @Autowired
    MockMvc mvc;

    @Test
    void shortPasswordReturnsSafeFieldError() throws Exception {
        mvc.perform(post("/api/accounts/register")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {"username":"student-01","password":"short"}
                    """))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("PASSWORD_POLICY_REJECTED"))
                .andExpect(jsonPath("$.errors[0].field")
                        .value("password"))
                .andExpect(jsonPath("$.errors[0].code")
                        .value("TOO_SHORT"));
    }

    @Test
    void missingPasswordReturnsInputInvalid() throws Exception {
        mvc.perform(post("/api/accounts/register")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {"username":"student-01"}
                    """))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code").value("INPUT_INVALID"));
    }

    @Test
    void validRequestReturnsGenericAcknowledgement()
            throws Exception {
        mvc.perform(post("/api/accounts/register")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {
                      "username":"student-02",
                      "password":"A long and unique passphrase"
                    }
                    """))
                .andExpect(status().isAccepted())
                .andExpect(jsonPath("$.status").value("RECEIVED"));
    }
}
~~~

Run:

~~~bash
./gradlew test \
  --tests example.account.PasswordPolicyTest \
  --tests example.account.RegistrationHttpTest
~~~

Expected result: **4 unit tests + 3 HTTP tests all pass** in a project with proper dependencies. Gradle output varies by version/build. These tests **do not replace** integration tests covering the DB, account uniqueness, reset tokens, CSRF in session-based apps, and a real blocklist service.

## 7. Password Change and Recovery: Same Policy, Different Access Rules

### 7.1. Password Change (Authenticated Session)

Safe workflow:

1. Identify the account from the verified `Authentication.getName()`/principal, **never from an arbitrary client-supplied user ID**.
2. Require recent authentication, the current password, or appropriate step-up auth to defend against session hijacking.
3. Use `PasswordEncoder.matches(normalizedCurrent, currentStoredHash)`; never log the current password.
4. Apply the **new-password policy** + compromised blocklist to `newPassword`. You can check for reuse using `matches(normalizedNew, currentHash)`—do not compare two hashes directly since salts differ.
5. Encode the new password; update the DB by account ID inside a transaction with a version check to prevent races.
6. Send a security notification via a verified channel; apply policies to revoke existing sessions/refresh tokens.
7. Audit the event type and request ID without logging passwords or hashes.

### 7.2. Forgot Password (Public Request + One-Time Reset Link)

Step one accepts an email/username and **always returns a generic response**. The server sends instructions only to the verified address of an eligible account. The token must be strongly random, securely stored, short-lived, and **atomically consumed once**. The password-reset step invokes the same `PasswordPolicy`, encodes, and updates; never turn a reset token into an unbounded login session.

A common mistake is emailing a “temporary new password” or the “old password.” Always send a **reset link** containing an unpredictable token and never log it. After a reset, notify the user of the change and handle open sessions according to your threat model.

### 7.3. Sign-In: Do Not Return Policy Hints Before Authentication

`DaoAuthenticationProvider` and `UserDetailsService` authenticate accounts using `PasswordEncoder.matches`. When login fails, return a generic message for **non-existent username, wrong password, or disallowed account status** to prevent user enumeration. Enforce rate limits and monitor for credential stuffing and exploitable timing differences.

If a legacy hash or compromised password is detected after a successful login, transition the user into a **secure upgrade flow** rather than turning the login endpoint into an oracle revealing specific weaknesses of the current password to unauthenticated callers.

## 8. Error Codes and UX

| Code | Scope | Suggested message |
| --- | --- | --- |
| `INPUT_INVALID` | DTO | “Please check the information you entered.” |
| `MALFORMED_JSON` | Request | “The request data is not properly formatted.” |
| `PASSWORD_POLICY_REJECTED` | New password | “The password does not meet requirements.” |
| `TOO_SHORT` | New password | “Please use at least 15 characters.” |
| `TOO_LONG` | New password | “The password exceeds the maximum length.” |
| `COMMON_PASSWORD` | New password | “This password is too predictable.” |
| `UNSUITABLE` | New password | “Please choose a valid secret phrase.” |
| `INVALID_CREDENTIALS` | Login | “Invalid login credentials.” |
| `RATE_LIMITED` | Login/reset/register | “Too many attempts. Please try again later.” |

The frontend should display requirements upfront, support password managers, pasting, a show/hide toggle, and accessible per-field feedback. The backend remains the final authority; never rely on client-side JavaScript validation to protect the API.

**Never send** passwords, tokens, `rejectedValue`, or stored hashes to analytics or error tracking. For public registration endpoints, prevent username/email enumeration across HTTP status, body, and **timing**, not just by hiding a single message.

## 9. Security Test Matrix

| ID | Condition | Expected outcome |
| --- | --- | --- |
| T01 | Password with 14 Unicode code points | `TOO_SHORT` |
| T02 | Password with 15+ code points, no special characters | Accepted if not on blocklist |
| T03 | Password with 64 code points containing spaces/Unicode | Not rejected merely for length or spaces |
| T04 | Password with 129 code points in demo | `TOO_LONG` |
| T05 | Emoji and NFC/NFD Unicode | Counted and normalized consistently |
| T06 | Common breached password, even if long | `COMMON_PASSWORD` |
| T07 | Passphrase containing a common word inside | Not blocked merely for a substring |
| T08 | Huge raw input | Bounded before hashing; system protected from DoS |
| T09 | Malformed username | 400 `INPUT_INVALID` |
| T10 | Missing `password` | 400, error leaks no raw input |
| T11 | Malformed JSON | 400 `MALFORMED_JSON` |
| T12 | New vs existing username | Public response does not leak account existence |
| T13 | Two concurrent duplicate registrations | DB unique constraint blocks duplicate |
| T14 | Encoding the same password twice | Hashes differ due to salt, `matches` succeeds for both |
| T15 | Login with wrong username vs wrong password | Generic response, no account disclosure |
| T16 | Repeated login attempts | Throttling/rate limiting and sanitized logging |
| T17 | Unauthenticated / non-step-up password change | Blocked |
| T18 | Submitting another user's `userId` to change password | Blocked (IDOR defense) |
| T19 | Used/expired reset token | Rejected, concurrent consume succeeds at most once |
| T20 | Blocklist checker outage | Behaves per security policy, does not silently allow through |
| T21 | Invalid CSRF on cookie-session endpoint | Blocked |
| T22 | Client-side JS bypassed | Backend still validates everything |
| T23 | Validation exception logged | Never contains raw password |
| T24 | Legacy password needing migration | Not silently truncated/bypassed; has clear migration path |

### Common Mistakes

- **“`@Size(min=15)` is enough”**: can diverge from code-point policy and does not check compromised lists.
- **“Use Base64/MD5/SHA-256 for speed”**: not safe adaptive password hashing.
- **“Encode and compare hash strings”**: use `matches` because random salts produce different outputs.
- **“Use bcrypt and allow very long passwords without checking the byte limit”**: can cause unexpected truncation/collisions.
- **“Only `@Valid` on the controller”**: misses domain policy, DB uniqueness, and business rules.
- **“Return the full `BindingResult`”**: can leak `rejectedValue` = password.
- **“Return 'user is locked'”**: can leak account existence.
- **“No login attempt rate limiting”**: enables brute force and credential stuffing.
- **“Disable CSRF everywhere to make POST work”**: dangerous when the app authenticates with cookies/sessions.
- **“Password reset sends a reusable token”**: creates an account takeover vulnerability.
- **“Change password without handling existing sessions”**: can let an attacker keep access.

## 10. Implementation Checklist

- [ ] Length policy aligned with MFA/single-factor model; max length supports at least 64 characters.
- [ ] No composition regexes; supports Unicode, spaces, paste, and consistent normalization.
- [ ] Full-password blocklist checking plus an explicit checker outage policy.
- [ ] Adaptive + salted password hashing, benchmarked work factor, byte-limit check, and migration plan.
- [ ] Registration/change/reset share the new-password policy; login uses `matches`.
- [ ] Layered DTO validation and domain validation; DB enforces uniqueness and transactions.
- [ ] Responses use safe fields/codes/messages with no raw secrets, `rejectedValue`, hashes, or stack traces.
- [ ] Login/forgot-password return generic messages and prevent user enumeration across timing and status.
- [ ] Rate limiting, request size limits, CSRF/session hardening, HTTPS, and sanitized audit logs.
- [ ] Password change verifies owner/current credential or step-up and prevents IDOR.
- [ ] Reset tokens are random, time-limited, single-use, and revoke appropriate sessions.
- [ ] Tests cover length/Unicode/breach checks, HTTP errors, concurrency, privacy, and recovery.

## 11. References

- [NIST SP 800-63B-4 — Passwords](https://pages.nist.gov/800-63-4/sp800-63b.html#passwords)
- [NIST FAQ — Password requirements](https://pages.nist.gov/800-63-4-Implementation-Resources/faqs/)
- [OWASP Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html)
- [OWASP Password Storage Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html)
- [OWASP Forgot Password Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html)
- [Spring Security 6.5 — Password Storage & Compromised Password Checking](https://docs.spring.io/spring-security/reference/6.5/features/authentication/password-storage.html)
- [Spring Security 6.5 — Cryptography / Pbkdf2PasswordEncoder](https://docs.spring.io/spring-security/reference/6.5/features/integrations/cryptography.html)
- [Spring Boot — Validation](https://docs.spring.io/spring-boot/reference/io/validation.html)
- [Spring Framework — MVC Validation](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-validation.html)
- [Spring Framework — Error Responses and ProblemDetail](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-rest-exceptions.html)
- [RFC 9457 — Problem Details for HTTP APIs](https://www.rfc-editor.org/rfc/rfc9457)
