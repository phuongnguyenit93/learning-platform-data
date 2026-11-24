# WebAuthn, passkeys, and Spring Security version/dependency requirements

## 1. Problem, scope, and objectives

Users want to sign in to a Spring Boot application using a fingerprint, face recognition, PIN, or security key instead of entering a password every time. Across many devices, this experience is called a **passkey**. The web mechanism behind it is the **Web Authentication API (WebAuthn)**: the browser asks the authenticator to create or use an asymmetric key pair; the server verifies using the registered public key, without receiving the private key and without storing a shared secret for login.

Within the **Spring Security - authentication** module, this lesson focuses on **Spring Security's actual integration capabilities, version requirements, and corresponding dependencies**, rather than just general passkey definitions. After completing this lesson, you should be able to:

1. Distinguish between WebAuthn, passkeys, FIDO2, authenticators, Relying Party (RP), registration, and authentication assertions.
2. Understand why passkeys are bound to an application domain and help reduce phishing risk compared to passwords.
3. Know the exact difference between **Spring Security 6.4–6.5** and **Spring Security 7.x** regarding artifacts.
4. Configure `HttpSecurity.webAuthn(...)` with `rpId`, `allowedOrigins`, and `rpName`; choose the right starter and Java/Spring Boot versions.
5. Execute the **credential registration** flow followed by **sign-in**; understand default HTTP endpoints, CSRF, challenges, sessions, and repositories.
6. Know when in-memory WebAuthn data is only suitable for demos and how to switch to JDBC/custom persistence.
7. Troubleshoot common errors: missing HTTPS/secure context, wrong RP ID, origin mismatch, missing dependencies, or losing challenges/sessions or credentials after restart.
8. Evaluate account-takeover prevention policies when registering/deleting passkeys, recovering accounts, verifying users, and maintaining sessions.

**Technical scope of the runnable example:** a **Servlet/Spring MVC** application with Java 17, Spring Boot 3.5.x, and Spring Security 6.5.x. Reactive/WebFlux APIs, native mobile apps, and building a WebAuthn server from scratch are out of scope and cannot automatically use the same Servlet configuration.

## 2. WebAuthn and passkey are not completely synonymous

**WebAuthn** is a web API + authentication protocol that uses public-key cryptography. A **Passkey** is a type of FIDO/WebAuthn-based experience/credential that can typically be managed on a device or synced across a platform's ecosystem and is discoverable for convenient sign-in.

Key concepts:

| Term | Meaning | Integration impact |
| --- | --- | --- |
| **Relying Party (RP)** | The application service wanting to authenticate the user | Spring Boot is the RP server; it must declare the RP ID and verify the origin |
| **RP ID** | A domain name string defining the scope for credential use, e.g., `app.example.com` or `example.com` | Has no scheme/port; must match the host or a valid registrable-domain suffix |
| **Origin** | Scheme + host + port of the web page calling WebAuthn, e.g., `https://app.example.com` | Must be allowed by the server; do not compare only the hostname |
| **Authenticator** | Platform or security key that holds the private key and signs challenges | The browser calls it via `navigator.credentials`; the server must never obtain the private key |
| **Credential ID** | Identifier of a specific public-key credential | Used to look up the public key record, owner, status, and metadata |
| **Public key** | Component stored on the RP side after registration | Used to verify signatures during subsequent logins |
| **Private key** | Component residing on the authenticator/passkey provider | Never sent to the server in WebAuthn |
| **Challenge** | Fresh random value tied to a specific ceremony | Must be stored and matched, checking expiration/anti-replay |
| **Attestation** | Additional information about the authenticator's provenance/type when policy uses it | Not synonymous with verifying user identity; many apps use `none` |
| **Assertion** | Data sent by the browser when a credential signs an authentication challenge | Server verifies signature, challenge, RP ID, origin, and flags |
| **User presence (UP)** | The device detected user interaction | Not synonymous with user verification |
| **User verification (UV)** | The authenticator performed local verification such as PIN/biometric | Server needs a UV policy appropriate to the risk |

**A passkey is not "logging in with a fingerprint where the server stores your fingerprint."** Fingerprint/face/PIN only unlocks or verifies the user **on the device/provider**; the server receives cryptographic proof, not biometric templates.

**A passkey is not a JWT, OAuth2 access token, or OIDC ID Token.** After WebAuthn succeeds, Spring Security creates an `Authentication` in the application and can store it in the session; if you later need to issue a JWT for an API, that is an additional mechanism and must be designed separately.

## 3. Why does WebAuthn reduce phishing risk?

With passwords, a spoofed site can trick the user into entering the same secret. With WebAuthn, the browser and authenticator scope the credential to the **RP ID**. A credential for `app.example.com` cannot be freely used on `fake-login.attacker.example`. Furthermore, each login requires a signature over a **fresh challenge** from the RP, preventing replay of an old response.

Three important verification layers:

1. **Domain/origin binding:** the browser only allows WebAuthn in a valid context, and the server compares `clientDataJSON.origin`/RP ID.
2. **Proof of key possession:** the server verifies the signature using the public key tied to the registered credential ID.
3. **Freshness:** the challenge must be the one the server issued for the current ceremony, unexpired and unused.

However, "phishing-resistant" does not mean the application is **automatically completely secure**. If an attacker hijacks the user's HTTP session, exploits an XSS vulnerability, tricks the user into adding a passkey to an account via a hijacked registration flow, or compromises a weak recovery method, WebAuthn cannot solve that on its own. Security still depends on the server, session, CSRF, registration permissions, and account operations.

## 4. Version and dependency requirements: the easiest place to get confused

Spring Security started supporting WebAuthn/passkeys in **Spring Security 6.4**. Library packaging changed between the two generations:

| Spring Generation | Where does WebAuthn live? | Dependencies to watch |
| --- | --- | --- |
| **Spring Security before 6.4** | No equivalent built-in WebAuthn DSL | Upgrade or integrate another library supporting that Spring version; do not call `http.webAuthn(...)` |
| **Spring Security 6.4–6.5** (Spring Boot 3.4–3.5) | WebAuthn classes live in `spring-security-web` | In addition to the Security starter, you must include **`com.webauthn4j:webauthn4j-core`** per the corresponding branch's documentation |
| **Spring Security 7.0–7.1** (Spring Boot 4.x) | WebAuthn functionality split into artifact **`spring-security-webauthn`** | Add **`org.springframework.security:spring-security-webauthn`** with the version managed by the Spring Boot/Security BOM |

**Do not copy a `pom.xml` verbatim from 6.5 to 7.x.** Splitting the module in 7.x can cause classpath/runtime errors even though the configuration API looks very similar. Conversely, adding `spring-security-webauthn` to a 6.5 project selects the wrong dependency ecosystem.

### 4.1. Maven for Spring Boot 3.5 / Spring Security 6.5

The Spring Security **6.5.11** documentation states:

```xml
<dependency>
    <groupId>org.springframework.security</groupId>
    <artifactId>spring-security-web</artifactId>
</dependency>
<dependency>
    <groupId>com.webauthn4j</groupId>
    <artifactId>webauthn4j-core</artifactId>
    <version>0.29.7.RELEASE</version>
</dependency>
```

When using `spring-boot-starter-security`, `spring-security-web` is already pulled in by the starter; **no duplicate declaration is needed**. However, `webauthn4j-core` must be on the classpath for the right branch. Use `mvn dependency:tree` to verify instead of guessing versions from another guide.

Gradle Groovy:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'com.webauthn4j:webauthn4j-core:0.29.7.RELEASE'
}
```

**Java requirement:** Spring Boot 3.x requires Java 17 or higher; the example uses Java 17. Spring Security 6.x corresponds to the Jakarta Servlet API—do not use old `javax.servlet.*` imports in Servlet code on Boot 3.x.

### 4.2. Maven/Gradle for Spring Security 7.x

With Spring Security 7.0–7.1 and a compatible BOM:

```xml
<dependency>
    <groupId>org.springframework.security</groupId>
    <artifactId>spring-security-webauthn</artifactId>
</dependency>
```

```groovy
dependencies {
    implementation 'org.springframework.security:spring-security-webauthn'
}
```

Core dependencies such as Spring Security config/web are still required according to your application structure. **Do not put `0.29.7.RELEASE` as the version of the Spring Security 7.x artifact**; that is the WebAuthn4J library version used by Spring Security 6.5 docs, not the `spring-security-webauthn` version.

Check the actual versions with Maven:

```bash
mvn dependency:tree -Dincludes=org.springframework.security
mvn dependency:tree -Dincludes=com.webauthn4j
```

When upgrading major Spring Boot versions, read the version-specific docs instead of relying on the "latest" page because the latest page may describe a changed module structure. You must also check for dependency conflicts, serialization libraries, Spring Framework/Servlet versions, and security advisories.

### 4.3. Note on Spring Boot 3.5.16

The hands-on lab uses a pinned version **Spring Boot 3.5.16** available on Maven Central. Spring announced this as the **final OSS release of 3.5.x** on **2026-06-25**; for new production deployments, you should upgrade to a supported branch such as Boot 4.x following the compatibility roadmap. Using Boot 3.5 in this lesson is solely to illustrate the Spring Security 6.5 API with explicit WebAuthn4J dependencies, **not a recommendation to keep running an end-of-support version**.

## 5. Relying Party ID, allowedOrigins, and secure context

This is the misconfiguration most likely to cause failures even when the project builds successfully.

For a production application:

```text
Public URL:      https://login.example.com
RP ID:           login.example.com
Allowed Origin:  https://login.example.com
```

- **RP ID** is a domain string, without `https://`, port, or path.
- **Origin** consists of scheme, hostname, and port if non-default; no path.
- RP ID must be the effective host or a valid registrable-domain suffix of the host according to WebAuthn rules (for example, in some architectures the RP ID can be `example.com` for controlled subdomains).
- You must not use an arbitrary public suffix like `com` as the RP ID.
- A passkey registered for one RP ID is not automatically usable for an unrelated RP ID.
- If the login domain changes later, you need a migration/credential re-issuance plan or an appropriate architecture, not just changing a single config variable.

**HTTPS:** WebAuthn is allowed in a **secure context**. Plain HTTP on a public domain is insufficient; specifically, `http://localhost:<port>` is permitted by WebAuthn as a local development exception. Thus a local example can use:

```text
Public URL:      http://localhost:8080
RP ID:           localhost
Allowed Origin:  http://localhost:8080
```

Do not confuse `http://127.0.0.1:8080`, `http://localhost:8080`, and `https://localhost:8080`: their origins differ. If RP/origin is configured for localhost but accessed by IP, the browser may reject the request; use the exact hostname. In production behind a reverse proxy, the public host/HTTPS must be consistent with the RP and origin—do not trust arbitrary `Host` header values.

## 6. Two ceremonies: registration and authentication

A passkey **must be registered first** before it can be used for authentication. Logically, WebAuthn consists of two distinct ceremonies.

### 6.1. Registration: an authenticated user adds a new credential

```text
User logged in via a trusted bootstrap method
         |
         | Open /webauthn/register
         v
Browser / Spring Security registration page
         |
         | POST /webauthn/register/options + CSRF
         v
Spring: verifies user, creates challenge/options
         |
         | publicKey.rp / user / challenge / algorithms / policy
         v
Browser: navigator.credentials.create({ publicKey: options })
         |
         | Authenticator creates key pair and performs local user verification
         | Private key stays on the authenticator/passkey provider
         v
Browser sends attestation/credential response
         |
         | POST /webauthn/register + CSRF
         v
Spring: verifies challenge, origin, RP ID, attestation data
         |
         | Stores credential ID, public key, user handle, metadata
         v
Passkey is linked to the current account
```

**Why must the user be logged in before registering?** Because "adding a new sign-in method" to an account is a sensitive operation. If an attacker can add a passkey to someone else's account without a valid session/reauth, the attacker gains persistent access. Registration should be bound to a **stable local user ID**, enforce anti-CSRF checks, and apply re-authentication (step-up) for high-risk scenarios.

Default HTTP endpoints in Spring Security Servlet 6.5/7.x:

| Step | Endpoint | HTTP method | Special requirements |
| --- | --- | --- | --- |
| Display sample passkey management page | `/webauthn/register` | GET | Authenticated user |
| Generate registration options | `/webauthn/register/options` | POST | Authenticated user, CSRF token, challenge stored |
| Save new credential | `/webauthn/register` | POST | Authenticated user, CSRF token, WebAuthn response verified |

The same URL `/webauthn/register` can handle both **GET for the UI page** and **POST for actual registration**; do not assume a single method for all actions.

### 6.2. Authentication: using a registered credential to sign in

```text
Anonymous Browser
     |
     | GET /login
     v
Login page with passkey option
     |
     | POST /webauthn/authenticate/options + CSRF
     v
Spring creates authentication challenge
     |
     | Browser navigator.credentials.get({ publicKey: options })
     v
Authenticator selects a credential matching the RP ID
     | verifies local user (PIN/biometric if policy requires)
     | signs challenge-related data with the private key
     v
POST /login/webauthn + CSRF (assertion)
     |
     v
Spring looks up credential record by credential ID
     | verifies challenge, origin, RP ID hash
     | verifies UP/UV per policy, signature, and metadata
     v
Spring Security Authentication succeeds
     |
     v
SecurityContext + session + authorization
```

Default endpoints:

| Step | Endpoint | HTTP method |
| --- | --- | --- |
| Sample login page | `/login` | GET |
| Generate authentication options | `/webauthn/authenticate/options` | POST |
| Submit assertion to sign in | `/login/webauthn` | POST |

**Fresh challenge every time:** the server generates a random challenge and stores the ceremony state, typically bound to the session. The client calls `navigator.credentials.get(...)`; the server must match the response against the challenge of that specific pending request. An old assertion must never be accepted just because its signature is valid under the user's public key.

**User presence vs user verification:** device interaction (UP) does not guarantee that a PIN/biometric (UV) was required. Apps requiring strong authentication must properly enforce the `userVerification` policy and server-side check results; do not assume "WebAuthn always means biometrics."

### 6.3. Browser WebAuthn flow and binary data

The browser WebAuthn API uses `ArrayBuffer`/`Uint8Array`, whereas Spring's JSON API typically represents byte arrays in **base64url**. Conversion is needed in both directions.

This is a **JS snippet illustrating the WebAuthn API**, not a complete web page:

```javascript
// publicKey is the options obtained from /webauthn/authenticate/options.
// This helper converts base64url-encoded binary fields to ArrayBuffer.
// Production integrations must also convert allowCredentials[].id if present.
function fromBase64url(text) {
  const base64 = text.replace(/-/g, "+").replace(/_/g, "/");
  const padded = base64.padEnd(Math.ceil(base64.length / 4) * 4, "=");
  return Uint8Array.from(atob(padded), char => char.charCodeAt(0)).buffer;
}

async function usePasskey(publicKey) {
  const options = {
    ...publicKey,
    challenge: fromBase64url(publicKey.challenge),
    allowCredentials: (publicKey.allowCredentials ?? []).map(item => ({
      ...item,
      id: fromBase64url(item.id)
    }))
  };
  return navigator.credentials.get({ publicKey: options });
}
```

During registration, `navigator.credentials.create({publicKey: ...})` is used, decoding `challenge`, `user.id`, and `excludeCredentials[].id`. After the browser API returns a credential, the client must **re-encode** the binary values in `rawId`/`response.*` according to the request schema expected by Spring Security. You can inspect the default registration/login pages instead of writing serialization from scratch based on just a few illustrative lines.

Never grab `credential.id` and treat it as proof of login: **the ID is only for looking up the public key; the assertion signature is what must be verified**.

## 7. Example with Spring Boot 3.5.16 + Spring Security 6.5 + WebAuthn4J

This example is a minimal **Java 17+, Servlet/MVC** project. It uses the **default login and registration pages generated by Spring Security**, avoiding the need to write custom client-side JavaScript/WebAuthn serializers before understanding the server flow.

Conditions for real interaction: a WebAuthn-capable browser, a machine with an authenticator/passkey provider or security key, the browser accessing `http://localhost:8080` exactly, and user consent to create a passkey. This demo uses in-memory credential persistence: restarting the app will lose registrations.

Structure:

```text
webauthn-passkey-demo/
├── pom.xml
└── src/
    ├── main/
    │   └── java/demo/passkey/PasskeyApplication.java
    └── test/
        └── java/demo/passkey/PasskeyApplicationTests.java
```

### 7.1. Create `pom.xml`

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
        <version>3.5.16</version>
        <relativePath/>
    </parent>
    <groupId>demo</groupId>
    <artifactId>webauthn-passkey-demo</artifactId>
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
        <!-- WebAuthn crypto integration required for Spring Security 6.5 -->
        <dependency>
            <groupId>com.webauthn4j</groupId>
            <artifactId>webauthn4j-core</artifactId>
            <version>0.29.7.RELEASE</version>
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

Both `spring-security-web` and `spring-security-config` are brought into the project by `spring-boot-starter-security`; you do not need to specify versions for those modules separately. **Do not add 7.x `spring-security-webauthn` to this `pom.xml`.**

### 7.2. Create the complete Java file

Create `src/main/java/demo/passkey/PasskeyApplication.java`:

```java
package demo.passkey;

import java.security.Principal;
import java.util.Map;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.ResponseEntity;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
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
@RestController
public class PasskeyApplication {

    public static void main(String[] args) {
        SpringApplication.run(PasskeyApplication.class, args);
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder passwords) {
        UserDetails learner = User.withUsername("learner")
            .password(passwords.encode("local-demo-password"))
            .roles("USER")
            .build();
        return new InMemoryUserDetailsManager(learner);
    }

    @Bean
    SecurityFilterChain webSecurity(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/public", "/error").permitAll()
                .requestMatchers("/private/**").authenticated()
                .anyRequest().authenticated())
            // Use password login to bootstrap the account in the demo;
            // do not disable recovery mechanisms by default in production.
            .formLogin(Customizer.withDefaults())
            .webAuthn(webAuthn -> webAuthn
                .rpId("localhost")
                .rpName("Local Passkeys Demo")
                .allowedOrigins("http://localhost:8080"))
            .build();
    }

    @GetMapping("/")
    Map<String, String> index() {
        return Map.of(
            "login", "/login",
            "registerPasskey", "/webauthn/register");
    }

    @GetMapping("/public")
    ResponseEntity<String> publicPage() {
        return ResponseEntity.ok("public");
    }

    @GetMapping("/private/me")
    Map<String, String> currentUser(Principal principal) {
        return Map.of("name", principal.getName());
    }
}
```

**Intentional choices:**

- `.webAuthn(...)` uses Spring Security 6.5's built-in DSL instead of writing a custom filter to verify signatures manually.
- `rpId("localhost")` and `allowedOrigins("http://localhost:8080")` are appropriate for loopback dev. If deploying at `https://login.example.com`, both values must be updated together to match the public domain.
- `.formLogin(...)` provides a bootstrap path: log in with the demo username/password, then visit `/webauthn/register` to add a passkey. After logging out, log back in using the passkey.
- `UserDetailsService` uses an in-memory username/password for **demo** purposes, with the password hashed using BCrypt. Never use hardcoded passwords in a real application.
- The default credential repository is also **in-memory**. It is separate from `InMemoryUserDetailsManager`: one stores accounts/login passwords, while the other stores public-key credentials. Neither is suitable as a production user store.
- Spring Security handles the protocol, challenges, and creating the `Authentication`. The `/private/me` controller simply reads the authenticated `Principal`.
- CSRF is not disabled; the POSTs that create challenges/credentials still require a CSRF token because they mutate state or bind the ceremony to the session.

**Do not call this example "passwordless-only"**: users still bootstrap with a demo password. A product that wants to be completely passwordless must design dedicated onboarding, invitation, account recovery, and risk-management flows.

### 7.3. Run the application and test in the browser

Run:

```bash
mvn spring-boot:run
```

Open **exactly**:

```text
http://localhost:8080/
```

Steps:

1. Open `/private/me` while logged out: Spring redirects to `/login`.
2. Sign in with `learner` / `local-demo-password` on your **local machine** to bootstrap.
3. Open `http://localhost:8080/webauthn/register`.
4. Use Spring Security's registration UI to create a passkey. Your browser/OS may prompt for a PIN/biometric or to select a security key.
5. Confirm the UI reports successful registration.
6. Log out via Spring Security's UI (using the POST/CSRF mechanism or standard logout page), returning to `/login`.
7. Choose sign in with passkey and select the newly created credential.
8. Verify `/private/me` returns the username `learner` if authentication succeeded.

Sample JSON on success:

```json
{"name":"learner"}
```

This is an example response for the fixed test user, not data that the WebAuthn API always returns directly. If `mvn spring-boot:run` runs but the browser rejects `navigator.credentials.create`, check the secure context/RP ID/origin and device before changing dependencies.

**Important:** a credential on the device may persist even after an app restart, while the server's in-memory public key record is wiped. As a result, the browser still "sees the passkey" but the server cannot match it for login. That is why a **persistent WebAuthn credential store** is needed in production.

## 8. Testing with MockMvc and limitations of unit tests

You can test controllers, authorization, and login fallback with `MockMvc` without invoking a biometric device or browser WebAuthn. However, **you cannot conclude that WebAuthn crypto/challenges work just because `@WithMockUser` passes**.

Create `src/test/java/demo/passkey/PasskeyApplicationTests.java`:

```java
package demo.passkey;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class PasskeyApplicationTests {

    @Autowired
    MockMvc mvc;

    @Test
    void publicEndpointDoesNotRequireLogin() throws Exception {
        mvc.perform(get("/public"))
            .andExpect(status().isOk())
            .andExpect(content().string("public"));
    }

    @Test
    void anonymousUserIsRedirectedToLogin() throws Exception {
        mvc.perform(get("/private/me"))
            .andExpect(status().is3xxRedirection());
    }

    @Test
    void authenticatedPrincipalCanReadPrivateEndpoint()
            throws Exception {
        mvc.perform(get("/private/me").with(user("learner")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.name").value("learner"));
    }
}
```

Run:

```bash
mvn test
```

Expect **3 tests passing** if the project and dependencies are correct. These tests prove that the basic `SecurityFilterChain` runs, protected pages require authentication, and the controller receives the principal. The test using `user("learner")` **injects a test authentication**, bypassing any authenticator.

**To test WebAuthn end-to-end**, you need a real browser or a browser automation framework supporting virtual authenticators/FIDO2 (the corresponding DevTools APIs) or test devices; you must execute both registration and assertion ceremonies for real, and verify 401 on wrong challenge/credential, multiple browsers/sessions, lost credentials after restart, wrong RP ID, and revocation mechanisms. Never attribute to `MockMvc` guarantees it has not verified.

## 9. Persistence: repositories and schemas you must not overlook

Spring Security 6.5 documentation describes two data storage abstractions:

- `PublicKeyCredentialUserEntityRepository`: links the WebAuthn user entity / user handle to the user managed by the RP.
- `UserCredentialRepository`: stores credential records, public key/credential ID, and metadata needed to verify assertions.

The default is **in-memory**. In a single-node demo, you can register and sign in within the same process lifecycle; **restarting loses data**, and multiple nodes without a shared credential store will behave erratically.

### 9.1. Using JDBC from Spring Security 6.5

Spring provides:

- `JdbcPublicKeyCredentialUserEntityRepository`.
- `JdbcUserCredentialRepository`.

Bean snippet **to place inside a `@Configuration` class**, not a standalone program:

```java
@Bean
JdbcPublicKeyCredentialUserEntityRepository webauthnUserEntities(
        JdbcOperations jdbc) {
    return new JdbcPublicKeyCredentialUserEntityRepository(jdbc);
}

@Bean
JdbcUserCredentialRepository webauthnCredentials(
        JdbcOperations jdbc) {
    return new JdbcUserCredentialRepository(jdbc);
}
```

When using the code above, add `spring-boot-starter-jdbc`, configure a `DataSource`, and initialize **the exact schema required by that Spring Security version** instead of guessing column names. For example, the `JdbcUserCredentialRepository` API notes the schema resource:

```text
classpath:org/springframework/security/user-credentials-schema.sql
```

Verify the schema resources in your **chosen JAR version**; the user entity repository also has its own schema. Run controlled Flyway/Liquibase migrations, apply unique constraints on credential ID/user handle, and restrict DB access. Never give the database custom table names and expect the built-in JDBC repositories to query them.

If account data lives in PostgreSQL/MySQL or a custom identity platform, you can implement both repository interfaces yourself, provided you preserve the find/save/delete credential contracts and transactional consistency.

### 9.2. Challenges/options also hold state

In addition to credential tables, registration options must be preserved between requesting options and submitting the credential. Spring Security has `PublicKeyCredentialCreationOptionsRepository`; the default implementation keeps options in **HttpSession**. When needed, customize the repository via `webAuthn(...).creationOptionsRepository(...)` or an appropriate bean.

In a multi-instance environment, if each node keeps its own session without sticky routing or a shared session store, the registration/challenge step can be lost when the next request hits another node. You must evaluate session stores, cookies, TTLs, and anti-replay—do not just move credentials to JDBC and assume all steps are now stateless.

### 9.3. Designing the credential lifecycle

An account can own multiple passkeys (phone, laptop, hardware security key), and each passkey has:

- Credential ID, public key, owner user handle, and associated RP ID.
- User-defined name such as "My Laptop", type/hints, and registration/last-used timestamps.
- Revoked/deleted status, authenticator metadata, and sign counter if available.
- Signals such as backup eligibility/backup state if required by policy/audit.

You do not need and **must not** store users' biometric templates or private keys. If a user deletes a passkey in the OS while the server record remains, the credential may no longer work; you need a management UI and application-side removal flow. Conversely, deleting the server record does not necessarily remove a synced credential on the device, but it will cause the server to reject assertions from that credential.

## 10. Production deployment requirements to verify

### 10.1. HTTPS and proxy configuration

- Public origins must use HTTPS with a valid certificate, except for the localhost development exception.
- Declare RP ID and `allowedOrigins` using the **domain the browser actually accesses**, not internal hostnames/container ports.
- If using an ingress/load balancer, ensure the browser sees the correct HTTPS/origin; do not blindly trust `X-Forwarded-Host`/`X-Forwarded-Proto` from external clients.
- Configure forwarded headers only from trusted proxies; verify redirect URLs, `Secure`/`SameSite` cookies, and routing of registration/authentication endpoints.
- Never add `*` to the origin allowlist to fix CORS or origin mismatch errors. **CORS does not replace WebAuthn origin verification.**

### 10.2. CSRF, state, and session

- Options requests are POSTs because they create challenges/state to match in the next step. Spring Security documentation requires a CSRF token for both options requests and credential submissions.
- Do not disable CSRF globally just to make a sample work; retrieve the token from the form/meta/cookie per your security configuration and send the proper header.
- Preserve session/challenge state between the options request and response submission. Cookies on the wrong domain, expired sessions, or multiple nodes not sharing state will cause "invalid/missing challenge" errors.
- Prevent replay and handle challenge expiration; when a ceremony fails, avoid reusing an old challenge as if it were a valid credential.
- After successful authentication, Spring Security builds the context and handles session fixation/logout according to the configured filter chain. Passkeys do not replace session management.

### 10.3. Credential enrollment, recovery, and account takeover

- Registration typically requires an **authenticated** user; for high-value accounts, consider requiring re-authentication/step-up when adding a new passkey, deleting the last passkey, or changing recovery options.
- Explicitly verify the user handle/owner; never accept an arbitrary `username` from the request while ignoring the current user context.
- Provide a safe recovery flow when all devices are lost; if recovery relies on weak email verification, an attacker can bypass passkey security.
- Limit credentials per account, prevent abuse, and audit every add/remove/failed login; alert users about credential changes.
- If your organization requires hardware authenticators or attestation, evaluate a dedicated policy. `attestation: none` supports privacy and broad compatibility but **does not prove a device belongs to a specific vendor/model**.
- Test `preferred`/`required` user verification policies according to risk level. Do not treat every WebAuthn request as guaranteed biometric verification.
- Check disabled/deleted user status in the local account store before granting access, even when the credential has a valid signature.

### 10.4. Synced passkeys, privacy, and signCount

Some passkeys can be synced across devices. This improves usability but also affects policy choices (backup state, attestation, device-bound requirements). The server must evaluate metadata and credential records per design and standards, rather than automatically treating synced credentials as "insecure" or hardware keys as "always secure."

`signCount` can help detect signs of cloning on certain authenticators, but with synced credentials the counter does not always increment under the old model. Evaluate anomalies alongside backup flags, policies, and risk signals; do not hardcode a rule like "counter equals 0 means guaranteed fraud."

### 10.5. Post-login access control

WebAuthn verifies **who is accessing**, not automatically granting `ROLE_ADMIN` or allowing the user to view all data. Spring Security `Authentication` receives the principal/authorities tied to the local account; authorization still needs to check endpoints, tenants, and object ownership.

If an API needs an access token, use OAuth2/OIDC protocols or a dedicated, explicitly designed token issuer; a successful WebAuthn login in a web session does not automatically turn into a bearer access token for microservices.

## 11. Practical troubleshooting matrix

| Symptom | Common cause | How to check/fix |
| --- | --- | --- |
| `http.webAuthn(...)` does not compile | Spring Security too old (pre-6.4), wrong major version, or missing config module | Check dependency tree, BOM, and version-specific docs |
| WebAuthn-related `ClassNotFoundException`/`NoClassDefFoundError` | 6.5 missing WebAuthn4J or 7.x missing `spring-security-webauthn` | Match the exact artifact for your Spring Security branch |
| Browser reports `SecurityError`/invalid RP ID | RP ID is invalid for the current hostname | Use the exact host, RP ID without scheme/port, no unrelated domain |
| Browser reports invalid secure context | Accessing over HTTP on a public domain | Enable HTTPS; dev can use `http://localhost:8080` |
| Browser reports `NotAllowedError` | User cancelled, timeout, authenticator policy, no matching credential, or other browser conditions | Check UI, authenticator, timeout, RP ID, and browser logs |
| User has a passkey but server rejects it after restart | Default WebAuthn credential store is in-memory | Use JDBC/custom repository and schema migrations |
| Registration gets 403 | Missing/invalid CSRF token; authenticated user policy | Send CSRF token and verify session/authorization |
| Options request succeeds, submit reports invalid challenge | Session/options mismatch, cookie not sent back, multi-node state not shared, or challenge timeout | Check HttpSession, creation options repository, cookies, and routing |
| Authentication returns 401 even though credential exists | Invalid signature/credential ID/challenge/origin/RP hash/user policy | Debug with sensitive data redacted; never disable validation |
| Credential belonging to another user gets attached to current account | Enrollment flow takes user ID from unverified input | Bind registration to the user principal from `SecurityContext` |
| Passkey login succeeds but admin page returns 403 | Valid authentication but missing authority | Check user store and policies, do not alter cryptographic verification |
| Works on localhost in dev but fails in staging | Wrong HTTPS public origin, proxy headers, RP ID, or cookies | Compare browser URL with `allowedOrigins`/`rpId` |
| Able to log in again after account is locked | Local account state not checked in login path | Load status/authorities from canonical source and check before granting session |
| MockMvc tests pass but WebAuthn does not work | MockMvc injected principal without executing browser/authenticator ceremony | Write browser integration tests with a virtual authenticator or real device |

**Logical debugging order:** Spring version/dependencies → app startup and filter chain → browser secure context → `rpId`/`allowedOrigins` → registration bootstrap/CSRF → options challenge/session → credential store → assertion validation → local user mapping/authorization.

Do not log raw assertions, full `clientDataJSON`, user biometrics (not received by the server anyway), session cookies, or unnecessary credential payloads. Log correlation IDs, error types, and non-sensitive metadata to aid investigation.

## 12. Integration and operational testing checklist

A complete WebAuthn test suite needs both **happy paths** and **failure paths**:

1. **Registration:** logged-in user can register; anonymous is rejected; missing CSRF is blocked; invalid challenge/origin is rejected.
2. **Authentication:** registered passkey can log back in; unknown credential ID or invalid signature returns 401; old challenge is rejected.
3. **Domain binding:** credential registered for the expected RP ID does not work on another domain; wrong origin is blocked.
4. **State:** session/challenge is preserved across the two requests, including when running multiple nodes.
5. **Persistence:** restart/redeploy does not lose credentials; deleting a credential causes subsequent logins to fail.
6. **Local account:** disabled/revoked accounts cannot gain access; role/tenant policies remain enforced.
7. **Recovery:** losing one or all passkeys has a secure recovery process; users are notified when passkeys are added/removed.
8. **Browser/device:** test across supported browsers, OSes, platform authenticators, synced passkeys, and hardware keys on your official support list.
9. **Security:** verify HTTPS, CSRF, cookies, session fixation/logout, XSS, CSP, origin, auditing, and rate limiting.
10. **Compatibility:** test fresh Maven/Gradle builds and deployments with the exact Spring Boot/Security versions, not just on a machine with cached JARs.

Browser test automation typically uses a **virtual authenticator** to generate real credentials/signatures in tests; you should still perform at least one manual test pass on representative devices since OS/UI passkey providers vary by platform.

## 13. Common misconceptions to avoid

**"Passkeys mean the server receives the user's fingerprint."** False. Biometrics or PINs are checked on the device/provider; the server verifies a public-key assertion.

**"Spring Boot starter-security alone is enough for all Spring versions."** False. 6.5 requires `webauthn4j-core` per the docs; 7.x requires `spring-security-webauthn` separately.

**"Just adding `.webAuthn(...)` makes it production-ready."** False. You need HTTPS, RP ID/origin, credential persistence, enrollment policies, session/CSRF, account recovery, and monitoring.

**"Passkeys cannot be phished so CSRF or XSS protection isn't needed."** False. Phishing-resistant authentication does not remove the need to protect sessions, registration endpoints, accounts, and the application.

**"The user has a passkey on their phone so the backend will always know about it."** False. The server needs persistent credential records and public keys; a device holding a private key does not mean the server retains metadata after restart.

**"Turning off `formLogin` automatically gives you passwordless onboarding."** False. You must design how to create trusted users, register the first passkey, and recover when devices are lost.

**"MockMvc `user(...)` tests WebAuthn."** False. It only mocks Spring Authentication; it does not call `navigator.credentials` and does not verify signatures.

**"RP ID is a full URL."** False. RP ID is a domain, while origin includes scheme/host/port; the server must protect both.

## 14. Self-check questions

1. **What does WebAuthn store on the server?** Credential ID, public key, user handle, and necessary metadata/policy—not private keys or fingerprints.
2. **Why must `navigator.credentials.create` be called before `navigator.credentials.get` for a new account?** Because the RP must register the credential to have a public key to verify assertions later.
3. **What is the difference between `rpId` and `allowedOrigins`?** RP ID defines the credential's domain scope; `allowedOrigins` are the web origins (scheme/host/port) that the RP accepts.
4. **What exception to the HTTPS requirement exists for dev?** `localhost` over HTTP is treated as a secure context exception for WebAuthn.
5. **Which dependency must Spring Security 6.5 add?** `com.webauthn4j:webauthn4j-core` per the version-specific docs; `spring-security-web` is usually included via the starter.
6. **Which dependency must Spring Security 7.1 add?** `org.springframework.security:spring-security-webauthn` with a compatible BOM.
7. **Why are registration options requested via POST and protected by CSRF?** Because the server generates/stores a challenge/state bound to the session; without protection, credential enrollment could be abused.
8. **Why does browser login fail after a restart even though the device still has the passkey?** Spring's default in-memory credential store was wiped; a persistent repository is required.
9. **Does passkey login automatically grant admin privileges?** No. Spring authorization still relies on authorities and resource policies.
10. **What happens if a user loses their only passkey?** A pre-designed recovery process is needed, not defaulting back to weak methods vulnerable to account takeover.
11. **Does passkey sign-in always require biometrics?** No. The authenticator may use a PIN or another local method, and UV policies may vary.
12. **Is testing only with `@WithMockUser` enough?** No. Browser/authenticator integration tests are needed to verify challenges, signatures, and RP binding.

## 15. Official references and further reading

- **Spring Security 6.5 – Passkeys:** https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passkeys.html
- **Spring Security 7.1 – Passkeys:** https://docs.spring.io/spring-security/reference/servlet/authentication/passkeys.html
- **Spring Security 6.5 – Getting Spring Security and BOM:** https://docs.spring.io/spring-security/reference/6.5/getting-spring-security.html
- **Spring Security 6.5 – What's New, JDBC Persistence:** https://docs.spring.io/spring-security/reference/6.5/whats-new.html
- **Spring Security 7.1 – Modules:** https://docs.spring.io/spring-security/reference/modules.html
- **Spring Security 6.5 – WebAuthnConfigurer API:** https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/config/annotation/web/configurers/WebAuthnConfigurer.html
- **WebAuthn Level 3 specification:** https://www.w3.org/TR/webauthn-3/
- **Spring Boot 3.5.16 release notice:** https://spring.io/blog/2026/06/25/spring-boot-3-5-16-available-now/
- **Spring Boot 3.4 Security/Passkeys example:** https://spring.io/blog/2024/11/24/bootiful-34-security/
