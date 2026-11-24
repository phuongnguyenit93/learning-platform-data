# HTTP Basic: HTTPS, How Browsers Store Credentials, and Logout Limitations

**Module:** Spring Security – Servlet  
**Group:** HTTP Basic  
**Example:** Java 17, Spring Boot 3.3.5, Spring Security 6.x, Spring MVC, and Tomcat.

## Objectives

After this lesson, you can explain why HTTP Basic **must travel over HTTPS**, how browsers can remember and resend username/password, why there is no reliable cross-browser Basic logout, and how to test a Spring Security Servlet API using HTTP Basic. The lesson clearly distinguishes **HTTP authentication cache**, **password manager**, **session cookie**, and **SecurityContext**. Examples use dummy credentials, not for production.

## 1. How HTTP Basic Works

HTTP Basic uses the `Authorization` request header. For username `student` and password `learn-pass`, the payload is the Base64 encoding of `student:learn-pass`:

```http
GET /api/me HTTP/1.1
Host: localhost:8080
Authorization: Basic c3R1ZGVudDpsZWFybi1wYXNz
```

Base64 can be decoded to recover the exact username/password; **Base64 is encoding, not encryption or hashing**. If the header leaks, an attacker can recover the credentials and replay requests. Never mistakenly explain that the `Basic` keyword or Base64 provides confidentiality.

Common challenge-response flow:

```mermaid
sequenceDiagram
    participant C as Browser or HTTP client
    participant S as Spring Security Servlet
    participant P as AuthenticationProvider
    C->>S: GET /api/me (no Authorization yet)
    S-->>C: 401 + WWW-Authenticate: Basic realm="Learning API"
    Note over C: Browser may show username/password prompt
    C->>S: GET /api/me + Authorization: Basic ...
    S->>P: Verify username/password
    P-->>S: Authentication success or error
    S-->>C: 200 JSON or 401 challenge
```

**Not every client waits for a challenge.** `curl -u` and some HTTP libraries can send the Basic header right on the first request. After authenticating, a browser may also proactively resend the header for URLs within the protection space.

| Component | Meaning | Key point |
| --- | --- | --- |
| `Authorization: Basic <base64>` | Client sends username/password via HTTP Basic | Decodable; every request carries reusable credentials |
| `401 Unauthorized` | Authentication requirement not yet satisfied | Named *Unauthorized*, yet usually an authentication challenge |
| `WWW-Authenticate: Basic realm="Learning API"` | Server advertises Basic scheme and realm | Realm is a protection space label, **not** a session, role, or token |
| `403 Forbidden` | Caller is not permitted to perform the action | May be authorization or CSRF; does not necessarily mean wrong password |
| `200 OK` | Request processed successfully | Does not prove the browser holds a session cookie |

`BasicAuthenticationFilter` in Spring Security reads the Basic header, builds an authentication request, invokes `AuthenticationManager`, and uses the result. `AuthenticationEntryPoint` can issue a `401` challenge when needed. This is a **Servlet filter** flow, not an MVC login `@PostMapping`.

## 2. HTTPS Matters More Than Base64

### 2.1. What Happens Over Plain HTTP

Over `http://`, the `Authorization` header can be read or modified by anyone able to observe or intercept the network path. Since Base64 is decodable, an attacker sees `username:password`; users risk account takeover if passwords are reused. Even if the server uses `BCryptPasswordEncoder` to store hashes, that does not protect the raw password **in transit over the wire**.

**Conclusion:** HTTP Basic should only be used over **HTTPS with proper server certificate validation** when real credentials are involved.

HTTPS/TLS protects confidentiality and integrity from the client to the **TLS termination point**. It does not automatically protect downstream systems, data in logs, heap dumps, secrets in the browser, or credential stuffing.

```text
Browser -- HTTPS/TLS --> Reverse proxy -- backend hop --> Spring Boot
```

If TLS terminates at a proxy, verify whether the proxy→backend hop is adequately protected under your threat model. For sensitive data, consider internal TLS/mTLS, restricted networks, secret redaction in proxies/APM, certificate chain configuration, and server name verification.

### 2.2. Do Not Send Basic Over HTTP and Then Redirect

An anti-pattern is letting the app accept an `http://` request carrying `Authorization` and return `301/302` to `https://`. By the time the browser receives the redirect, the header has already crossed an **unencrypted** link; secrets may already be exposed.

Clients must initiate connections **directly over `https://`** and verify the certificate. Servers/edges can redirect ordinary HTTP requests to HTTPS, but a redirect cannot restore confidentiality to credentials already sent earlier. HSTS can instruct browsers to prefer HTTPS **after a valid policy is recorded or preloaded**, yet it cannot undo a prior HTTP credential transmission.

### 2.3. What HTTPS Does Not Protect

- Application or reverse proxy writing `Authorization`, raw HTTP headers, or passwords to access logs.
- Tracing/APM systems recording credentials in span attributes, exception messages, or body captures.
- TLS termination at the edge with an unprotected backend hop.
- Clients disabling certificate verification with `curl -k`/`--insecure` or browsers bypassing certificate warnings.
- Credentials appearing in shell history, command-line process listings, deploy scripts, URL query strings, or repositories.
- Passwords reused across services or guessed via brute force.

Your design must combine **HTTPS + server-side password hashing + log/trace controls + rate limiting**; one layer does not replace the others.

## 3. How Browsers Store HTTP Basic Credentials

### 3.1. Browser-Managed Basic Prompt

When a page returns `401` and `WWW-Authenticate: Basic ...`, a browser may display a **native login dialog**. The user enters username/password; the browser resends the request with the Basic header. When visiting related URLs, the browser may **automatically resend stored credentials** without prompting the user again.

Credential retention behavior depends on the browser, session, realm, origin, access method, and settings. **Closing a tab does not guarantee forgetting credentials**. Some browsers retain them until the browser session/application closes, while others behave differently; never promise a specific duration or condition across all browsers.

Similarly, seeing the browser show the prompt again upon `401` is not proof that the old cache was completely cleared. The browser may reuse remembered credentials, re-prompt, or pick another credential; applications must not rely on the prompt as a security session boundary.

### 3.2. Protection Space and `realm`

Example header:

```http
WWW-Authenticate: Basic realm="Learning API"
```

`realm` helps the client identify the authentication scope. The scope of HTTP Basic credential reuse also relates to **scheme/host/port and path scope** according to protocol rules and client implementations. Browsers may resend credentials to URLs within the same protection space.

Do not treat creating two paths `/api/a` and `/api/b` as a way to force browsers to ask for a password twice; nor should you treat realm as an access permission. **Authorization is still checked per endpoint by the server**. Changing the realm may trigger another prompt, yet it is not a standardized password revocation or guaranteed logout mechanism.

### 3.3. Four Different Kinds of State Storage

| Location/mechanism | What is stored | Who controls it | How it relates to logout |
| --- | --- | --- | --- |
| Browser HTTP auth cache | HTTP Basic credentials used | Browser/HTTP stack | No standard Basic web logout API for the server to force forgetting |
| Password manager | User-saved passwords, possibly synced | User/password manager | Deleting a saved entry does not necessarily clear the active auth cache |
| Cookie such as `JSESSIONID` | Session identifier | Held by browser, session managed by server | Server can invalidate session and send cookie expiry |
| Spring Security `SecurityContext` | `Authentication` for the request, possibly via repository/session | Spring Security per configuration | Clearing context/session does not force the browser to clear Basic credentials |

**Very common confusion:** A browser can keep auto-sending `Authorization` **even without `JSESSIONID`**, because HTTP Basic requires no session cookie. Conversely, a password manager offering to save a password is a separate feature and does not mean every browser using HTTP Basic persists credentials forever.

Do not try to read or clear the browser's auth cache using page JavaScript: browsers provide no universal web API guaranteeing that operation. Never design logout around “closing the tab”, `window.location`, clearing localStorage, or deleting cookies when the authentication mechanism is Basic.

## 4. Logout Limitations: Why Deleting a Session Can Still Let Users Back In

### 4.1. HTTP Basic Re-Authenticates Per Request

A client holding a Basic username/password can resend it on **every request**:

```text
Request 1: Authorization: Basic ... -> server authenticates -> 200
Request 2: Authorization: Basic ... -> server authenticates -> 200
Request 3: Authorization: Basic ... -> server authenticates -> 200
```

Spring Security can hold `Authentication` in the request's `SecurityContext`. If a session exists, a logout handler can invalidate the session and clear the context. Yet when the next request still carries a valid `Authorization: Basic ...`, **`BasicAuthenticationFilter` can re-authenticate immediately**, making the user appear never logged out.

This is not a bug in `HttpSession.invalidate()`; HTTP Basic **does not define a standard logout operation** that forces a browser to forget username/password. In browser app design, this is a major UX and security limitation.

### 4.2. “Tricks” That Do Not Guarantee Logout

| Attempt | Why it is unreliable as logout |
| --- | --- |
| Returning `401` on Logout click | May show a challenge/prompt, but does not guarantee the browser forgets credentials |
| Sending a wrong Basic header to “overwrite” the password | Browser-dependent; may just fail the request or trigger a prompt |
| Changing `realm` | May create a different protection space, old credentials are not guaranteed deleted |
| Deleting the `JSESSIONID` cookie | HTTP Basic does not need a session cookie to send credentials |
| Clearing localStorage/sessionStorage | Does not control the browser's HTTP authentication cache |
| `Clear-Site-Data: "cache", "cookies", "storage"` | Affects some supported site data; **not guaranteed** to wipe the HTTP Basic auth cache |
| Closing tab/refreshing page/JavaScript redirect | No guarantee on when the browser forgets Basic credentials |

Never build a Logout button claiming “fully logged out” while the server still accepts the old password from the same browser and the browser keeps resending the Basic header.

### 4.3. How to Truly Revoke Access?

There are two distinct goals:

- **Block every client using the old password:** disable the account, change/revoke the password on the backend, or update authorization policies. If every request re-checks the current credential store, a client resending the old password receives `401`/an appropriate error.
- **End only one session/device:** HTTP Basic has no session identifier independent of the password. Use form login + an invalidatable session, or tokens/OIDC with properly designed lifecycle and revocation/rotation.

Changing a password **does not automatically remove the password saved in the browser**; the browser may keep sending the expired password and get rejected. If the system also has authentication caches, tokens, sessions, or SSO mechanisms, evaluate revocation across **all** of those paths instead of assuming changing the password alone suffices immediately.

### 4.4. When Should HTTP Basic Be Used?

HTTP Basic is simple and common for internal scripts and CLIs **over TLS**, where each request supplies credentials itself and per-device logout UX is not needed. For browser apps needing a Logout button, timeouts, remember-me, SSO, or multiple independent sessions, **form login/sessions or OAuth2/OIDC/tokens** are usually a better fit.

Whether using sessions or tokens, logout must have a concrete definition: one session, all devices, refresh token, access token, or the identity provider session. No mechanism makes every kind of token vanish with a single redirect.

## 5. Configuring HTTP Basic in Spring Security Servlet

Components:

```mermaid
flowchart TD
    A["GET /api/me"] --> B["FilterChainProxy selects SecurityFilterChain"]
    B --> C["BasicAuthenticationFilter checks Authorization"]
    C --> D{"Credentials present and valid?"}
    D -- "Yes" --> E["AuthenticationManager → Provider"]
    E --> F["SecurityContext for request"]
    F --> G["Authorization then controller"]
    D -- "No" --> H["AuthenticationEntryPoint"]
    H --> I["401 + WWW-Authenticate: Basic ..."]
```

`FilterChainProxy` selects the first security chain matching the request. `BasicAuthenticationFilter` operates **inside the selected chain**, so if multiple chains have different `securityMatcher` rules, ensure `/api/**` enters a chain with `httpBasic`.

HTTP Basic is an authentication mechanism that **can work without a server session**, yet `httpBasic()` alone **does not prove** the entire application has no `HttpSession`: controllers, MVC, CSRF, or other libraries may still create sessions for their own purposes.

When you want each API request to supply its own header, a common configuration is:

```java
http.sessionManagement(session -> session
        .sessionCreationPolicy(SessionCreationPolicy.STATELESS));
```

`STATELESS` directs Spring Security not to use `HttpSession` to store/restore `SecurityContext` across subsequent requests; it **does not** make browsers forget headers, **does not** disable password managers, and **does not** replace TLS.

### 5.1. CSRF Warning When Browsers Auto-Send Credentials

**Never conclude CSRF is harmless simply because an API uses Basic or is called stateless.** Browsers can automatically send stored Basic credentials with certain requests. For state-changing endpoints, evaluate CSRF based on whether credentials are sent automatically, browser behavior, and actual clients.

Spring Security's `CsrfFilter` protects unsafe requests when CSRF is enabled. `GET` should not cause state changes. Do not equate CORS with CSRF: CORS mainly restricts how cross-origin JavaScript reads/uses responses, not proof that every cross-site state-changing request is harmless.

The demo below **uses GET only** and retains default CSRF protection; if adding `POST/PUT/DELETE`, evaluate and test an appropriate CSRF policy. Never turn `.csrf(csrf -> csrf.disable())` into blanket advice for every Basic-authenticated API.

## 6. Runnable Spring Boot Project

The example exposes public `/public/ping`, Basic-protected `/api/me`, and `ADMIN`-restricted `/api/admin`. Demo account `student`/`learn-pass` has `ROLE_USER` with a one-way BCrypt-encoded password in the in-memory user store; responses return only the username, never passwords or hashes.

### 6.1. Directory Tree

```text
http-basic-demo/
├── pom.xml
└── src/
    ├── main/java/demo/basic/
    │   ├── BasicApplication.java
    │   ├── SecurityConfig.java
    │   └── ApiController.java
    └── test/java/demo/basic/
        └── BasicApplicationTests.java
```

Requires JDK 17+, Maven 3.6.3+, and dependency repository access on first build.

### 6.2. `pom.xml`

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
    <groupId>demo</groupId>
    <artifactId>http-basic-demo</artifactId>
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

`spring-boot-starter-web` uses Spring MVC/Servlet (embedded Tomcat by default), unlike WebFlux. The Spring Boot BOM manages versions of Spring Security and related dependencies.

### 6.3. `src/main/java/demo/basic/BasicApplication.java`

```java
package demo.basic;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class BasicApplication {
    public static void main(String[] args) {
        SpringApplication.run(BasicApplication.class, args);
    }
}
```

### 6.4. `src/main/java/demo/basic/SecurityConfig.java`

```java
package demo.basic;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        http.authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/public/ping").permitAll()
                .requestMatchers(HttpMethod.GET, "/api/admin")
                    .hasRole("ADMIN")
                .anyRequest().authenticated());

        http.httpBasic(basic -> basic.realmName("Learning API"));

        http.sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS));

        // GET-only demo; do not disable CSRF by default.
        return http.build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        UserDetails student = User.withUsername("student")
                .password(encoder.encode("learn-pass"))
                .roles("USER")
                .build();
        return new InMemoryUserDetailsManager(student);
    }
}
```

`httpBasic(...)` installs Basic authentication on the security chain and sets the realm. `hasRole("ADMIN")` requires the `ROLE_ADMIN` authority; account `student` only holds `ROLE_USER`, so it cannot access `/api/admin`. Because a `UserDetailsService` bean is present, the app does not need Boot's default generated user.

This is a demo setup **without form login and without a logout endpoint**: it avoids giving the false impression that `/logout` clears HTTP Basic credentials in the browser. In real systems, store users in a database/identity provider, use password hashing, and apply brute-force throttling.

### 6.5. `src/main/java/demo/basic/ApiController.java`

```java
package demo.basic;

import org.springframework.http.MediaType;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ApiController {
    @GetMapping(value = "/public/ping",
                produces = MediaType.TEXT_PLAIN_VALUE)
    public String ping() {
        return "pong";
    }

    @GetMapping("/api/me")
    public MeResponse me(Authentication authentication) {
        return new MeResponse(authentication.getName());
    }

    @GetMapping("/api/admin")
    public String admin() {
        return "admin-only";
    }

    public record MeResponse(String username) {}
}
```

Only returns `MeResponse` containing the username—**never returning** the raw `Authentication`, `Authorization` header, or encoded password hash.

## 7. Running the Project and Checking Status Codes

On localhost you can run HTTP to observe the mechanics in a learning environment **without real credentials**:

```bash
mvn clean test
mvn spring-boot:run
```

In another terminal (Windows PowerShell may require `curl.exe`):

```bash
# GET public
curl -s http://localhost:8080/public/ping

# No Basic credentials provided
curl -s -o /dev/null -w '%{http_code}\n' \
  http://localhost:8080/api/me

# Valid dummy credentials
curl -s -u student:learn-pass \
  http://localhost:8080/api/me

# Wrong password
curl -s -o /dev/null -w '%{http_code}\n' \
  -u student:wrong http://localhost:8080/api/me

# Right password but missing ROLE_ADMIN
curl -s -o /dev/null -w '%{http_code}\n' \
  -u student:learn-pass http://localhost:8080/api/admin
```

Output from **five separate commands**:

```text
pong
401
{"username":"student"}
401
403
```

The `pong` and JSON bodies typically have no trailing newline; `-w` adds a newline when printing the HTTP status. If you need to inspect the challenge, use:

```bash
curl -i http://localhost:8080/api/me
```

Key parts of the response:

```http
HTTP/1.1 401
WWW-Authenticate: Basic realm="Learning API"
```

Other headers may vary. `Authorization` is the client's **request** header; `WWW-Authenticate` is the server's **response** header. Never pass real passwords in `curl -u user:password` commands that may be saved in shell history/process logs; only use the demo's dummy credentials.

### 7.1. Proving Base64 Reversibility with Java 17

Standalone file `BasicHeaderDemo.java`:

```java
import java.nio.charset.StandardCharsets;
import java.util.Base64;

public class BasicHeaderDemo {
    public static void main(String[] args) {
        String credentials = "student:learn-pass";
        String value = Base64.getEncoder().encodeToString(
                credentials.getBytes(StandardCharsets.UTF_8));

        String decoded = new String(Base64.getDecoder().decode(value),
                StandardCharsets.UTF_8);
        System.out.println(value);
        System.out.println(decoded);
    }
}
```

Run:

```bash
javac BasicHeaderDemo.java
java BasicHeaderDemo
```

Exact stdout:

```text
c3R1ZGVudDpsZWFybi1wYXNz
student:learn-pass
```

This is an encoding demonstration with **dummy data**; never print `Authorization` headers or Base64 credentials in production logs.

## 8. Setting Up Self-Signed HTTPS for Localhost

In development, you can use self-signed TLS to study Basic exchanges over HTTPS. **This is not a production certificate setup**. Real applications need a trusted certificate chain, private key management, and properly configured reverse proxies/edges.

### 8.1. Creating a PKCS#12 Keystore

Ensure `src/main/resources` exists, then run JDK `keytool`:

```bash
keytool -genkeypair \
  -alias localhost \
  -keyalg RSA -keysize 3072 \
  -validity 365 -storetype PKCS12 \
  -keystore src/main/resources/dev-keystore.p12 \
  -storepass changeit -keypass changeit \
  -dname "CN=localhost, OU=Dev, O=Demo, L=HCM, ST=HCM, C=VN" \
  -ext "SAN=dns:localhost,ip:127.0.0.1"
```

The `\` backslashes denote line continuations in POSIX shells; in Windows PowerShell use a single line or PowerShell's syntax. The password `changeit` is **for demo only**. Never commit keystores, private keys, or passwords to real repositories.

Add `src/main/resources/application.properties`:

```properties
server.port=8443
server.ssl.enabled=true
server.ssl.key-store=classpath:dev-keystore.p12
server.ssl.key-store-type=PKCS12
server.ssl.key-store-password=${TLS_KEYSTORE_PASSWORD}
server.ssl.key-alias=localhost
```

Supply the password via an environment variable at runtime:

```bash
export TLS_KEYSTORE_PASSWORD=changeit
mvn spring-boot:run
```

In PowerShell, set `$env:TLS_KEYSTORE_PASSWORD = "changeit"` before running Maven.

### 8.2. Using `curl --cacert` Instead of Skipping TLS Validation

Export the public certificate to PEM:

```bash
keytool -exportcert \
  -alias localhost -storetype PKCS12 \
  -keystore src/main/resources/dev-keystore.p12 \
  -storepass changeit -rfc -file local-cert.pem
```

Test HTTPS to hostname `localhost` matching the SAN:

```bash
curl --cacert local-cert.pem \
  -u student:learn-pass https://localhost:8443/api/me
```

Expected body:

```json
{"username":"student"}
```

`--cacert` uses the test certificate as the trust anchor for this request **without disabling server verification**. Avoid `curl -k`/`--insecure` because they disable certificate verification and fail to verify that passwords are sent to the right server. Browsers may warn on self-signed certificates; never instruct users to bypass warnings in real environments.

## 9. Testing the Servlet Filter Chain with MockMvc

File `src/test/java/demo/basic/BasicApplicationTests.java`:

```java
package demo.basic;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.containsString;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class BasicApplicationTests {
    @Autowired
    MockMvc mvc;

    @Test
    void publicEndpointDoesNotNeedCredentials() throws Exception {
        mvc.perform(get("/public/ping"))
                .andExpect(status().isOk())
                .andExpect(content().string("pong"));
    }

    @Test
    void privateEndpointIssuesBasicChallenge() throws Exception {
        mvc.perform(get("/api/me")
                .accept(MediaType.APPLICATION_JSON))
                .andExpect(status().isUnauthorized())
                .andExpect(header().string("WWW-Authenticate",
                        containsString("Basic realm=\"Learning API\"")));
    }

    @Test
    void validCredentialsAreAccepted() throws Exception {
        mvc.perform(get("/api/me")
                .with(httpBasic("student", "learn-pass")))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.username").value("student"))
                .andExpect(jsonPath("$.password").doesNotExist());
    }

    @Test
    void incorrectPasswordIsRejected() throws Exception {
        mvc.perform(get("/api/me")
                .with(httpBasic("student", "wrong")))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void nextIndependentRequestWithoutHeaderIsUnauthenticated()
            throws Exception {
        mvc.perform(get("/api/me")
                .with(httpBasic("student", "learn-pass")))
                .andExpect(status().isOk());

        mvc.perform(get("/api/me"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void authenticatedUserWithoutAdminRoleIsForbidden()
            throws Exception {
        mvc.perform(get("/api/admin")
                .with(httpBasic("student", "learn-pass")))
                .andExpect(status().isForbidden());
    }

    @Test
    void adminEndpointWithoutCredentialsChallenges() throws Exception {
        mvc.perform(get("/api/admin")
                .accept(MediaType.APPLICATION_JSON))
                .andExpect(status().isUnauthorized())
                .andExpect(header().string("WWW-Authenticate",
                        containsString("Basic")));
    }
}
```

`mvn test` is expected to run **seven tests** and pass with the source/config above. `httpBasic(...)` in tests is a `spring-security-test` helper, not real browser interaction.

**Evidence boundaries:** MockMvc does not test TLS handshakes, certificate validation, HSTS, or browser HTTP Basic caching. The two-independent-request test proves only that **without the header, the subsequent MockMvc request does not succeed on its own** in this configuration; you cannot infer that a real browser forgets the password after closing a tab. Use real browser/client tests and deployed environments for those requirements.

## 10. Common Failure Scenarios

### Mistake A: Thinking Base64 Is Secure Encryption

An `Authorization` header can be decoded trivially. **Fix:** HTTPS with certificate validation, no secret logging, store password hashes on the server.

### Mistake B: App Has `STATELESS` Yet Browser Still “Logs In Automatically”

The browser may be resending Basic credentials itself. `STATELESS` governs Spring Security's `SecurityContext` storage, not clearing the client's credential cache. Inspect network requests using demo data and distinguish `Authorization` from cookies.

### Mistake C: Logout Clears Session Yet Refresh Still Lets the User In

The browser still sends valid passwords via the Basic header. Clearing the session removes only session state; it does not force the client to forget Basic credentials. If per-device revocation is needed, switch to dedicated sessions/tokens with an explicit lifecycle.

### Mistake D: Changing the Realm and Thinking Users Were Logged Out

A new realm may alter prompt/cache mapping, yet does not invalidate old passwords on the server. Never use it as a security boundary.

### Mistake E: HTTPS at Proxy Yet Logs Still Contain Passwords

TLS decrypts at the edge. If access logs or APM record the Authorization header, secrets are stored in infrastructure. Apply masking/redaction and restrict access and retention.

### Mistake F: Confusing `401` and `403`

Missing Basic credentials -> may return `401` with a challenge. Authenticated without `ROLE_ADMIN` -> `403`. On unsafe requests, `403` can also come from CSRF. Test status, headers, and policies together.

### Mistake G: Disabling CSRF Simply Because Only HTTP Basic Is Used

That is a wrong conclusion for many browser apps. If browsers auto-send HTTP Basic credentials, malicious requests can exploit ambient authentication. Evaluate CSRF based on HTTP methods, client types, and actual auth policies.

### Mistake H: Ignoring TLS Certificate Errors

`curl -k` may make requests succeed while skipping server verification. Use a valid trust store/certificate; local dev with self-signed certs can use `--cacert`.

## 11. Deployment Checklist

1. Clients send credentials only to **HTTPS URLs** with TLS validation and proper hostnames.
2. Never rely on HTTP→HTTPS redirects to protect passwords already sent earlier.
3. Reverse proxy/backend hops, certificate chains, and forwarded headers are configured from trusted sources.
4. `Authorization`, cookies, and secrets are never written to logs/APM/traces.
5. Passwords are stored server-side with secure hashing; rate limiting and anomaly alerts are in place.
6. `httpBasic` is enabled on the **right SecurityFilterChain**; `securityMatcher` and `@Order` do not bypass protected routes.
7. If independent requests are desired, use `STATELESS` and test actual behavior, never treating it as logout.
8. Distinguish authentication `401` from authorization `403`.
9. Apply an appropriate CSRF policy, especially when browsers can auto-send Basic credentials on state-changing requests.
10. Never expose passwords, hashes, or Basic headers via REST DTOs or logs.
11. If UX requires Logout, session expiry, or per-device revocation, consider **form login/sessions** or revocable tokens.
12. Use MockMvc tests for the security chain, HTTPS clients with certificate validation, and real browser tests for credential caching.
13. Never promise that closing a tab, clearing cookies, `401`, or changing the realm makes a browser forget Basic passwords.
14. Explicitly define what logout means: revoking one device, all devices, a session, a refresh token, or all account access.

## 12. Self-Practice Questions

**1.** Why is Base64 not secure enough?  
**Answer:** It is a reversible encoding; passwords in Basic headers can be recovered. HTTPS is required to protect data in transit.

**2.** Does `WWW-Authenticate: Basic realm="Docs"` create a session?  
**Answer:** No. The realm advertises the protection space and helps clients scope credentials; it does not issue a session ID.

**3.** Without cookies, refreshing `/api/me` in a browser still succeeds. Why?  
**Answer:** The browser may automatically resend the remembered `Authorization: Basic ...`, and the server re-authenticates the request.

**4.** Does deleting `JSESSIONID` delete Basic credentials?  
**Answer:** No. HTTP Basic credentials live in a client-managed header; session cookies and the HTTP auth cache are separate mechanisms.

**5.** Does returning `401` from a Logout endpoint force all browsers to forget the password?  
**Answer:** No. It may trigger a prompt, yet there is no guaranteed standard logout for HTTP Basic.

**6.** GET `/api/me` with the right password returns `200`, while GET `/api/admin` returns `403`. Where is the bug?  
**Answer:** Not necessarily a bug. The user is authenticated but lacks the `ROLE_ADMIN` authority.

**7.** Why is `STATELESS` insufficient to prove CSRF is harmless?  
**Answer:** Browsers may automatically send ambient Basic credentials; you must evaluate cross-site state-changing risks and CSRF policy.

**8.** What is a better way to support per-device logout?  
**Answer:** Use a session or token mechanism decoupled from the password with explicit expiry/invalidation/revocation, rather than relying on the browser's HTTP Basic cache.

## Conclusion

**HTTP Basic merely represents `username:password` in Base64, so proper HTTPS is always required.** Browsers can remember and resend credentials independently of cookies/sessions; Spring Security's `httpBasic` and `SessionCreationPolicy.STATELESS` provide no way to wipe that browser memory. **There is no reliable, universal HTTP Basic logout.** Choose Basic for simple clients over TLS when this limitation is acceptable; use sessions or tokens with designed revocation when the application truly needs logout.