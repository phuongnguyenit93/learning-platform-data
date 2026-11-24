# Session Cookies with Secure, HttpOnly, SameSite, Path, and Lifetime

> **Objective:** Understand what a Spring Security (Servlet) application's session cookie is, what each attribute—**Secure**, **HttpOnly**, **SameSite**, **Path**, **Domain**, **Max-Age/Expires**—protects, and why **browser cookie lifetime differs from server session lifetime**. Know how to configure Spring Boot, inspect **Set-Cookie**, test login/logout, and choose appropriate policies for production.

## 1. Session Cookie and Server-Side Session Are Not the Same Thing

In **session-based authentication**, the server stores session state, including information allowing Spring Security to restore **SecurityContext** after a user logs in. The browser holds a cookie containing the **session ID** (by default **JSESSIONID** in many Servlet containers). When the URL, domain, path, SameSite, and cookie conditions allow, the browser automatically attaches the ID to the **Cookie** header of subsequent requests.

~~~text
1) GET /login --> server creates session (if needed) --> Set-Cookie: JSESSIONID=opaque-id; ...
2) User POST /login with valid credentials + CSRF
3) Spring Security authenticates, manages/rotates session ID per config, and saves SecurityContext
4) GET /api/me
   Cookie: JSESSIONID=opaque-id
             |
             v
   Server/SessionRepository looks up session by ID
             |
             v
   Reads SecurityContext --> authentication/authorization --> response
5) Session expires/revoked: cookie may remain, yet ID no longer points to a valid session
~~~

**A session ID is a secret that can be used for impersonation if stolen.** It must be sufficiently random, unpredictable, and protected in transit and storage. Cookies **must not contain passwords, arbitrary access tokens, client-dictated roles, or the entire user object**. With a standard JSESSIONID, the cookie is a reference to server data; the value itself grants no access if the server has deleted or revoked the session.

Do not confuse:

- **Cookie**: data stored by the browser, which decides when to send it back based on cookie attributes.
- **HTTP session**: server-side state with an ID, last-accessed timestamp, and expiration policy.
- **SecurityContext**: authentication result that Spring Security can save/restore via a session repository.
- **Remember-me**: a separate mechanism that can create a new authentication from a long-lived cookie/token. It is not synonymous with extending JSESSIONID.
- **JWT bearer**: a different token model; rules about JSESSIONID cannot replace JWT signature verification, expiry, and revocation.

This lesson focuses on **Spring Boot 3.x + Spring Security 6.x, Servlet/MVC**. WebFlux/Reactive and systems using **Spring Session** have specialized configuration properties, so Servlet property names should not be assumed to apply to all cases.

## 2. Reading the Set-Cookie Header Properly

Example server response after creating a session:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Set-Cookie: JSESSIONID=opaque-random-session-id; Path=/; Max-Age=1800; Secure; HttpOnly; SameSite=Lax

{"status":"session created"}
~~~

On the next request, the browser sends only **name=value**:

~~~http
GET /api/me HTTP/1.1
Host: app.example.com
Cookie: JSESSIONID=opaque-random-session-id
~~~

**Secure/HttpOnly/SameSite/Path/Max-Age do not appear in the returned Cookie header**; they are server instructions inside **Set-Cookie** that the browser uses when storing and sending the cookie. If a cookie is rejected due to rule violations, the next request will lack the session ID and the application will typically treat the client as not logged in.

| Set-Cookie Attribute | Primary Effect | Limitations to Understand |
| --- | --- | --- |
| **Secure** | Sends cookie only over an encrypted HTTPS connection (some browsers have an exception for localhost) | Does not replace properly configured TLS and certificate verification; does not encrypt the cookie value itself |
| **HttpOnly** | Prevents JavaScript from reading/writing the cookie via **document.cookie** | Malicious JavaScript can still trigger requests using the cookie; does not eliminate XSS/CSRF risks |
| **SameSite=Strict/Lax/None** | Controls whether the cookie is sent on **cross-site** requests | Not an authorization mechanism and does not replace CSRF tokens in all applications |
| **Path=...** | Restricts the request paths for which the browser sends the cookie | Does not establish a strong security boundary between applications on the same host |
| **Domain=...** | Broadens the hosts/subdomains eligible to receive the cookie; omitted usually means host-only | Overly broad Domain widens exposure and cookie injection surface |
| **Max-Age=seconds** | Cookie lifetime on the client, measured relatively | Does not extend or validate an expired session on the server |
| **Expires=HTTP-date** | Absolute expiration date on the client | When both Max-Age and Expires are present, Max-Age takes precedence |
| **No Max-Age/Expires** | Browser-session cookie | "Closing the browser" is not an absolute boundary due to browser session restore |
| **Name** | Distinguishes the cookie; usually JSESSIONID | Reusing the same name across multiple Paths/Domains easily causes confusion |

**Attributes work together.** Configuring only HttpOnly without Secure on an HTTPS endpoint can leak the cookie over an unintended plain HTTP request. Configuring only Secure while leaving the cookie readable by JavaScript can amplify XSS impact. Configuring only SameSite without protecting state-changing actions with CSRF tokens can miss flows that satisfy cookie-sending rules.

## 3. Secure: Mandatory Protection for Session IDs Over HTTPS

### 3.1. Browser Behavior

A cookie with **Secure** is sent over HTTPS connections. When an application attempts to use that cookie over plain HTTP, the browser withholds it (some browsers apply an exception for **localhost**; never rely on that exception in production).

~~~http
Set-Cookie: JSESSIONID=abc123; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

If logged in via **https://app.example.com**, requests to **http://app.example.com** are not permitted to carry the Secure cookie under standard browser behavior. However, **Secure does not encrypt the cookie**; TLS encrypts the transport channel, while the cookie value remains visible at the server, the reverse proxy terminating TLS, developer tools, and anywhere headers are inadvertently logged.

Proper deployment requires:

1. Serving **HTTPS** with a valid server certificate; never skip certificate validation.
2. Starting the login flow and setting the cookie over HTTPS, avoiding initial HTTP requests carrying credentials.
3. Explicitly configuring **server.servlet.session.cookie.secure=true**.
4. Ensuring reverse proxy → backend hops are protected per your threat model; avoid logging **Cookie** and **Set-Cookie**.
5. Configuring HTTPS redirects/HSTS for websites by design; do not treat redirects as a substitute for transmitting secrets exclusively over TLS.

### 3.2. Reverse Proxies and Load Balancers

A common deployment:

~~~text
Browser --HTTPS--> Load balancer / ingress --internal HTTP--> Spring Boot
             TLS terminate
~~~

Spring Boot in the backend may see requests as HTTP because TLS terminated at the ingress. If relying solely on **request.isSecure()** or automatic detection, the app may emit cookies missing Secure. Setting **server.servlet.session.cookie.secure=true** enforces this attribute explicitly.

If Spring Boot needs to know the real scheme/host to generate redirects or URLs, configure **Forwarded/X-Forwarded-Proto** via trusted proxies and **server.forward-headers-strategy** per your architecture. Never blindly trust forwarded headers sent by arbitrary Internet clients, as scheme/host can be spoofed. Inspect **Set-Cookie** headers at the real public edge, not only from the backend container.

## 4. HttpOnly: Reducing Cookie Theft via JavaScript

~~~http
Set-Cookie: JSESSIONID=abc123; Secure; HttpOnly; Path=/; SameSite=Lax
~~~

With **HttpOnly**, JavaScript running on the page cannot read the cookie via **document.cookie**. This makes stealing the session ID via XSS vulnerabilities harder.

However, HttpOnly **does not make the cookie "invisible" everywhere**:

- The browser still attaches the cookie automatically on **fetch/XHR** calls if the request meets cookie rules and credentials/CORS modes.
- XSS can still trigger authenticated requests, read same-origin responses, or act on the user's behalf.
- Session IDs can still leak via logs, reverse proxies, compromised machines, privileged browser extensions, or physical access depending on the situation.
- HttpOnly does not stop CSRF: a malicious page can trigger certain requests that cause the browser to attach cookies automatically if SameSite and browser policies allow.

**Rule:** mark session cookies HttpOnly; simultaneously apply output encoding, CSP, XSS defenses, CSRF protection, CORS restrictions, and proper authorization. If the frontend needs a CSRF token, issue the token via a dedicated mechanism rather than forcing the frontend to read **JSESSIONID**.

## 5. SameSite: How Strict, Lax, and None Differ

**SameSite** helps the browser decide whether to attach a cookie when a request originates from a **different site**. In modern browsers, "site" is based on **scheme + registrable domain**, distinct from **origin** which includes scheme, host, and port. Therefore **https://app.example.com** and **https://api.example.com** are usually **same-site** yet **cross-origin**; CORS may still be required for JavaScript API calls.

| SameSite | Main Behavior | When to Use | Risks / Limitations |
| --- | --- | --- | --- |
| **Strict** | Never sends cookie on requests originating from another site, including top-level navigation | Sensitive areas with little need for external inbound links | Users clicking a link from another site may appear logged out on the initial request |
| **Lax** | Sends cookie on same-site requests; typically sends on **top-level cross-site navigation with safe methods** such as GET | Typical session-login websites | Does not prevent all CSRF; GET must never mutate state |
| **None** | Allows sending in cross-site contexts, subject to browser policies | Integrations needing third-party/cross-site cookies after full review | **Requires Secure** in modern browsers; third-party cookies may be blocked |
| **Omitted** | Browser applies its own default, many treating it close to Lax | Not recommended to rely on defaults | Some browsers have temporary exceptions, especially for newly issued cookies |

With **SameSite=None**, configure **Secure=true**. Browsers restricting third-party cookies may block the cookie despite SameSite=None; do not assume this attribute guarantees every cross-site iframe/SPA will work.

**SameSite=Lax does not replace CSRF tokens.** Cookies can still be sent on top-level GET navigations from other sites; applications must never perform data writes via GET. Additionally, same-site requests from another subdomain can still carry the cookie under same-site rules. When using session cookies for login, maintain CSRF protection for unsafe methods such as POST/PUT/PATCH/DELETE per Spring Security policy.

### 5.1. Example: Same Site, Different Origin

Frontend at **https://app.example.com** calling backend **https://api.example.com**:

- The two URLs may be **same-site**, so **SameSite=Lax** does not block requests by itself.
- They are **cross-origin**, so JavaScript fetch must comply with **CORS**, **credentials** policy, and server response headers.
- If the cookie is **host-only** for **api.example.com**, the browser sends the cookie to the API host when eligible; the frontend neither needs nor should read the session ID.
- If frontend and API live on **two different registrable domains**, they are cross-site: SameSite=None + Secure may be needed, though it also depends on third-party cookie policies and authentication design.

Frontend example:

~~~javascript
const response = await fetch("https://api.example.com/api/me", {
  credentials: "include",
});
const profile = await response.json();
~~~

For cross-origin requests with credentials, the API must respond with **Access-Control-Allow-Origin** specifying an allowed explicit origin and **Access-Control-Allow-Credentials: true** per policy; never combine a wildcard origin with credentials. CORS does not replace authentication or CSRF and must not be used to let arbitrary origins access the API.

### 5.2. With OAuth2/OIDC Login Callbacks

Some external login flows use a top-level redirect back to a callback. **SameSite=Strict** can prevent the session cookie from being sent on the return step, causing lost state/session; **Lax** can suit top-level GET callbacks. If a flow requires cross-site POST/iframe, **None** plus additional controls may be needed. Choosing SameSite must be tested on target browsers with the real OAuth2/OIDC flow, not inferred from an internal GET request.

## 6. Path and Domain: Scoping Cookies, Not Authorization

### 6.1. Path

~~~http
Set-Cookie: JSESSIONID=...; Path=/app; Secure; HttpOnly; SameSite=Lax
~~~

A cookie with **Path=/app** is typically sent to **/app** and matching subpaths like **/app/profile**, not to **/other**. **Path=/** lets the browser send the cookie across all paths on the scoped host.

Practical rules:

- Use **Path=/** when the application needs the session across login/logout, APIs, and pages on the same host.
- For an app mounted under **/portal**, consider **Path=/portal** if all related endpoints stay within that prefix.
- Do not arbitrarily set **Path=/api** if the login form is at **/login** and callbacks sit outside **/api**; the browser will not send the cookie where needed.
- When deleting a cookie, use the **same name, Path, and Domain** matching the original cookie; a mismatched Path can create a duplicate cookie or fail to delete the old one.

**Path is not a security isolation mechanism between two apps on the same origin.** Scripts on the same origin and related paths can interact in ways that do not form a solid trust boundary. Never rely on Path to protect secrets from an untrusted app sharing the same host.

### 6.2. Domain: Host-Only Is Usually Better

If **Domain is omitted**, the cookie is normally **host-only**: the browser sends it only to the exact issuing host. Setting **Domain=example.com** lets the cookie be sent to the apex domain and matching subdomains. Widening Domain increases the hosts receiving the cookie and the attack surface from subdomains; omit Domain unless genuinely required.

~~~http
# Host-only: issued by server app.example.com, no Domain
Set-Cookie: JSESSIONID=...; Secure; HttpOnly; Path=/; SameSite=Lax

# Domain cookie: broader scope, requires risk assessment
Set-Cookie: JSESSIONID=...; Domain=example.com; Secure; HttpOnly; Path=/; SameSite=Lax
~~~

A leading dot in **Domain=.example.com** no longer carries special meaning under modern cookie rules. Expanding Domain does not make servers across subdomains trust one another; authorization must still happen in the application.

### 6.3. The `__Host-` Cookie Prefix

In browsers supporting cookie prefixes, a name starting with **__Host-** must have **Secure**, **Path=/**, **no Domain**, and be set from a secure context. This is a stronger way to constrain cookie scope when the application can meet those constraints.

~~~http
Set-Cookie: __Host-JSESSIONID=...; Secure; HttpOnly; Path=/; SameSite=Lax
~~~

Do not rename JSESSIONID to **__Host-JSESSIONID** if the app runs under a Path other than / or needs a Domain cookie; browsers will reject cookies violating prefix rules. When renaming the cookie, also update logout/clear-cookie settings, monitoring, and tests. The prefix only adds a browser constraint; it does not replace server-side session verification.

## 7. Two Clocks: Client Cookie Lifetime and Server Session Timeout

This is the easiest part to confuse when configuring "lifetime."

### 7.1. Cookie Max-Age / Expires

~~~http
Set-Cookie: JSESSIONID=...; Path=/; Max-Age=1800; Secure; HttpOnly; SameSite=Lax
~~~

**Max-Age=1800** means the browser can keep the cookie for up to about **1,800 seconds (30 minutes)** from receiving the header. This is a client-side duration and **does not** guarantee the session remains valid on the server for 30 minutes. If the server sends a new Set-Cookie later, the cookie's expiration time can update per the new header; do not assume every request automatically refreshes Max-Age.

**Expires** specifies an absolute date-time; **Max-Age** takes priority if both are present. **Max-Age=0** instructs the browser to delete the cookie. Without Max-Age/Expires, it is a browser-session cookie; browsers may restore sessions after restart, so never treat closing the window as a guaranteed logout.

### 7.2. Server Session Timeout (Idle Timeout)

For Servlets:

~~~properties
server.servlet.session.timeout=15m
~~~

This is the duration **a session can go unaccessed before expiring**, depending on the session repository/container. A valid request to the session usually updates the last-accessed time; the session expires after a period of inactivity. This is **not an absolute lifetime** measured from initial login.

Example configuration:

~~~properties
server.servlet.session.cookie.max-age=30m
server.servlet.session.timeout=15m
~~~

Suppose:

- **10:00**: the server creates session S and issues a cookie with a 30-minute Max-Age.
- **10:10**: the user sends no requests for 10 minutes; the session can still be valid.
- **10:16**: if no request occurred since 10:00, the server may have expired S after 15 minutes of inactivity. The browser may still hold the cookie until 10:30, yet **the server rejects the old ID**.
- **10:31**: the cookie reaches Max-Age even if there was activity on the server; the browser stops sending the old cookie unless re-issued/renewed by design.

**Interaction between the two clocks:** repeated access can extend the **server idle timeout**, yet does not guarantee automatically extending **cookie Max-Age**. Setting identical values does not make the two mechanisms behave identically. If you need sliding sessions, absolute session limits, or "remember me," design them explicitly and test with real browsers.

### 7.3. Logout, Session Fixation, and Permission Changes

Proper logout requires:

1. **Invalidating** the server-side session or revoking the authentication binding in the session store.
2. **Clearing SecurityContext** and preventing reuse of the old session.
3. Sending cookie-deletion instructions if appropriate, with **name/Path/Domain** matching the original cookie; verify in browsers.
4. Ensuring the logout endpoint is properly CSRF-protected when using session cookies.

A cookie may still remain after invalidating the server session due to container/cookie-clearing differences. **That is not proof of logout failure if the old ID is already invalid**, though clearing the cookie reduces UX confusion. Deleting the cookie in the browser without invalidating the server session leaves any previously copied ID still usable.

Spring Security has default **session fixation** protection for login via standard filters, usually rotating the **session ID** on modern Servlet containers. Do not let an attacker fix an ID before login and keep using it afterward. With a controller that authenticates manually via AuthenticationManager, handle the session authentication strategy and save SecurityContext properly instead of assuming filter protections run automatically.

When an account is locked, a role is revoked, or a user changes their password, an active session does not vanish automatically in every design. You need a policy to **invalidate sessions / refresh authorities / manage the session registry** to meet security requirements.

## 8. Configuring Spring Boot 3.x / Spring Security 6.x (Servlet)

### 8.1. Direct Configuration Example

Start with a **Java 17+, Spring Boot 3.x, Spring Web, Spring Security** project from Spring Initializr. File **src/main/resources/application.properties**:

~~~properties
# HTTPS for localhost practice environment
server.port=8443
server.ssl.enabled=true
server.ssl.key-store=file:./localhost-demo.p12
server.ssl.key-store-type=PKCS12
server.ssl.key-store-password=${TLS_KEYSTORE_PASSWORD}
server.ssl.key-alias=localhost-demo

# Servlet session cookie attributes
server.servlet.session.cookie.name=JSESSIONID
server.servlet.session.cookie.secure=true
server.servlet.session.cookie.http-only=true
server.servlet.session.cookie.same-site=lax
server.servlet.session.cookie.path=/

# Distinguish client lifetime from server idle timeout
server.servlet.session.cookie.max-age=30m
server.servlet.session.timeout=15m

# Only for local demo account
demo.user.password=${DEMO_USER_PASSWORD}
~~~

These properties belong to the **server.servlet.session** namespace. Do not confuse them with WebFlux's **server.reactive.session**. **server.servlet.session.cookie.same-site** is supported by Spring Boot on common auto-configured Servlet containers such as Tomcat, Jetty, and Undertow; in real applications, still verify Set-Cookie at the public edge.

**A 30-minute Cookie Max-Age and 15-minute server idle timeout were chosen intentionally to prove they differ.** When building for production, choose values according to your risk model: sensitive apps may require short inactivity timeouts, absolute lifetimes, and re-authentication for critical operations. Avoid setting excessively long cookie lifetimes without reason.

If you want the cookie to live only for the browser session, **omit cookie.max-age** (do not set it to 0, because 0 means expire immediately). Server timeout still operates independently.

### 8.2. Minimal Java to Create and Use a Session

File **src/main/java/com/example/sessioncookie/SessionCookieApplication.java**:

~~~java
package com.example.sessioncookie;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SessionCookieApplication {
    public static void main(String[] args) {
        SpringApplication.run(SessionCookieApplication.class, args);
    }
}
~~~

File **src/main/java/com/example/sessioncookie/SecurityConfig.java**:

~~~java
package com.example.sessioncookie;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(
            PasswordEncoder encoder,
            @Value("${demo.user.password}") String rawPassword) {
        return new InMemoryUserDetailsManager(
                User.withUsername("alice")
                        .password(encoder.encode(rawPassword))
                        .roles("USER")
                        .build());
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/public/**", "/error")
                        .permitAll()
                        .anyRequest().authenticated())
                .formLogin(form -> form.permitAll())
                .logout(logout -> logout
                        .logoutSuccessUrl("/public/bye")
                        .permitAll())
                .build();
    }
}
~~~

**formLogin** uses a session after logging in. Under standard Spring Security configuration, **POST /login** requires a valid CSRF token; do not disable CSRF to run the demo. Passwords are hashed with BCrypt in the server-side user store. The class never returns passwords or session IDs from endpoints.

File **src/main/java/com/example/sessioncookie/SessionController.java**:

~~~java
package com.example.sessioncookie;

import jakarta.servlet.http.HttpServletRequest;
import java.util.Map;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class SessionController {

    @GetMapping("/public/session")
    public Map<String, String> prepareSession(
            HttpServletRequest request) {
        request.getSession(true);
        return Map.of("status", "session created");
    }

    @GetMapping("/api/me")
    public Map<String, String> currentUser(
            Authentication authentication) {
        return Map.of("username", authentication.getName());
    }

    @GetMapping("/public/bye")
    public Map<String, String> afterLogout() {
        return Map.of("status", "logged out");
    }
}
~~~

**GET /public/session** proactively creates a session to make observing Set-Cookie headers easy. In real applications, there is no need to create a session for every unauthenticated visitor; create one only when necessary to avoid wasting resources and generating unnecessary session IDs.

### 8.3. Localhost HTTPS with a Practice Certificate

In the project root, use **keytool** bundled with the JDK to generate a PKCS#12 file:

~~~bash
keytool -genkeypair -alias localhost-demo -keyalg RSA -keysize 2048 -validity 7 -storetype PKCS12 -keystore localhost-demo.p12 -storepass local-only-pass -keypass local-only-pass -dname "CN=localhost" -ext "SAN=dns:localhost"
keytool -exportcert -rfc -alias localhost-demo -keystore localhost-demo.p12 -storepass local-only-pass -file localhost-demo.crt
~~~

This is a self-signed certificate **for localhost only**. In production environments, use trusted certificates, manage private keys securely, and never commit **.p12** files, passwords, or secrets. The file name, alias, and password must match the configuration.

On Linux/macOS:

~~~bash
export TLS_KEYSTORE_PASSWORD=local-only-pass
export DEMO_USER_PASSWORD=demo-pass
./mvnw spring-boot:run
~~~

On Windows PowerShell:

~~~powershell
$env:TLS_KEYSTORE_PASSWORD = "local-only-pass"
$env:DEMO_USER_PASSWORD = "demo-pass"
.\mvnw.cmd spring-boot:run
~~~

After Spring Boot starts, verify the certificate using the local CA/certificate file instead of disabling TLS verification.

~~~bash
curl --cacert localhost-demo.crt -i -c cookies.txt https://localhost:8443/public/session
~~~

The response will contain a **Set-Cookie** header similar to:

~~~http
Set-Cookie: JSESSIONID=<random-value>; Path=/; Max-Age=1800; Expires=<date-time>; Secure; HttpOnly; SameSite=Lax
~~~

**This is an illustrative format**; ordering, representation, and Expires may vary depending on the container and Spring Boot patch version; session ID values and expiration dates are dynamic. What must be verified is **the presence and meaning of the attributes**, not hardcoding the entire header string.

After saving the cookie to **cookies.txt**, try calling a route requiring login:

~~~bash
curl --cacert localhost-demo.crt -i -b cookies.txt https://localhost:8443/api/me
~~~

Because you are not logged in yet, the form-login app usually returns **302** to **/login**. A browser can use the default form at **https://localhost:8443/login**; to test in a browser, trust the localhost certificate via an appropriate development workflow. **Never** use `curl -k` or disable SSL validation for real paths.

After logging in successfully in the browser, calling **/api/me** returns JSON:

~~~json
{"username":"alice"}
~~~

At that point, DevTools → Application/Storage → Cookies shows the stored cookie, its Secure/HttpOnly/SameSite/Path attributes, lifetime, and host. Never copy session ID values into public tickets/logs. In the Network tab, inspect the login/Set-Cookie response, Cookie requests, and redirects/CSRF.

### 8.4. Do Not Copy Servlet Configuration to WebFlux or Spring Session Without Checking

For **Spring Boot reactive**, there are separate properties such as **server.reactive.session.cookie.same-site** and WebSession timeouts. For **Spring Session** (Redis/JDBC), the repository and cookie serializer may have dedicated settings and distributed-store TTLs. Spring Boot may apply certain session properties to auto-configured Spring Session Servlet, but customized projects must inspect the exact implementation emitting Set-Cookie and storing TTLs.

Real-world observation at the load balancer, container, and browser is the final source of verification. Never assume setting a property guarantees a proxy will not overwrite headers.

## 9. Testing Cookie Attributes and Session Lifecycle

### 9.1. HTTP Header-Level Testing with an Embedded Container

**MockMvc** simulates the Servlet API and is great for testing Spring Security flows, yet it does not replace seeing **the real Set-Cookie from an embedded container**. When checking Secure/HttpOnly/SameSite/Path/Max-Age, have at least one test running a real server or testing against a deployed URL.

Add **spring-boot-starter-test** to the project (if not already present). File **src/test/java/com/example/sessioncookie/SessionCookieHeaderTest.java**:

~~~java
package com.example.sessioncookie;

import java.util.List;
import java.util.Locale;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.http.HttpHeaders;
import org.springframework.http.ResponseEntity;

import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT,
    properties = {
        "server.ssl.enabled=false",
        "demo.user.password=test-only"
    }
)
class SessionCookieHeaderTest {

    @LocalServerPort
    int port;

    @Autowired
    TestRestTemplate client;

    @Test
    void sessionCookieContainsSecurityAttributes() {
        ResponseEntity<String> response = client.getForEntity(
                "http://localhost:" + port + "/public/session",
                String.class);

        assertTrue(response.getStatusCode().is2xxSuccessful());
        List<String> headers =
                response.getHeaders().get(HttpHeaders.SET_COOKIE);
        assertNotNull(headers);

        String rawCookie = headers.stream()
                .filter(h -> h.startsWith("JSESSIONID="))
                .findFirst()
                .orElseThrow();

        String lower = rawCookie.toLowerCase(Locale.ROOT);
        assertTrue(lower.contains("path=/"));
        assertTrue(lower.contains("secure"));
        assertTrue(lower.contains("httponly"));
        assertTrue(lower.contains("samesite=lax"));
        assertTrue(lower.contains("max-age=1800"));
    }
}
~~~

The test intentionally disables TLS **only in the embedded test server** for easy access with TestRestTemplate, while still verifying that configuration forces the server to **emit** a header containing Secure. This test **does not prove the browser sends the cookie over HTTPS**; additional E2E tests with valid certificates are required. In production, never run an HTTP server with Secure cookies because browsers will not send the session reliably.

**If the test fails**, inspect the actual Set-Cookie and version/container before changing assertions; Spring Session, a reverse proxy, or a custom cookie serializer may be managing the header.

### 9.2. Testing Login and SecurityContext with MockMvc

Add the **spring-security-test** dependency in test scope. File **src/test/java/com/example/sessioncookie/SessionFlowTest.java**:

~~~java
package com.example.sessioncookie;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestBuilders.formLogin;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest(properties = {
    "demo.user.password=test-only",
    "server.ssl.enabled=false"
})
@AutoConfigureMockMvc
class SessionFlowTest {

    @Autowired
    MockMvc mvc;

    @Test
    void loginCreatesUsableAuthenticatedSession() throws Exception {
        MvcResult login = mvc.perform(formLogin()
                        .user("alice")
                        .password("test-only"))
                .andExpect(status().is3xxRedirection())
                .andReturn();

        MockHttpSession session = (MockHttpSession)
                login.getRequest().getSession(false);
        assertNotNull(session);

        mvc.perform(get("/api/me").session(session))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.username").value("alice"));
    }

    @Test
    void unauthenticatedRequestRedirectsToLogin() throws Exception {
        mvc.perform(get("/api/me"))
                .andExpect(status().is3xxRedirection());
    }
}
~~~

This test proves that logging in with a real password via **UsernamePasswordAuthenticationFilter / AuthenticationManager** creates a session usable in subsequent requests. It **does not measure 15/30 minutes by waiting** and does not inspect container-issued cookies. When testing server expiration, use a controllable session repository/test clock or deliberate time testing; avoid 15-minute wait tests that make CI slow and flaky.

### 9.3. Matrix of Scenarios to Verify

| Scenario | Browser/HTTP Observation | Server Observation |
| --- | --- | --- |
| Cookie with Secure + HTTPS | Cookie stored, HTTPS requests send it within scope | Session is found |
| Plain HTTP access | Browser does not send Secure cookie | Request is not recognized via cookie |
| HttpOnly cookie | **document.cookie** cannot read session ID | Valid requests can still carry the cookie |
| SameSite=Strict when linked from another site | Cookie may be absent on initial navigation request | User may be treated as not logged in at that step |
| SameSite=Lax with top-level cross-site GET | Cookie may be sent | GET must never mutate data |
| SameSite=None + Secure | Cross-site may carry cookie if browser policy allows | Server must still authenticate and protect against CSRF |
| Path=/app, request to /other | Cookie not sent outside Path | No session received from that cookie |
| Host-only cookie | Not sent to sibling hosts | Avoids widening subdomain scope |
| Cookie present, server session hit idle timeout | Browser still holds cookie | Session lookup fails, re-login required |
| Cookie hit Max-Age, server session still exists | Browser stops sending cookie | Even if server retains record, client cannot access via old cookie |
| Successful login | Session ID rotated per fixation policy | SecurityContext is saved |
| Logout | May receive cookie-clearing instruction | Old session must be invalidated |
| Copied cookie | Replay possible without extra defenses | Requires HTTPS, session invalidation, anomaly detection |
| Reverse proxy TLS termination | Public Set-Cookie still has Secure | Do not trust forwarded headers from arbitrary clients |

**Never log full Cookie/Set-Cookie headers in production tests.** When evidence is needed, record only attributes (Secure/HttpOnly/SameSite/Path/Max-Age), status, and timestamp. Session IDs are credentials and must be masked.

## 10. Common Mistakes and How to Fix Them

### 10.1. "HTTPS is already enabled, so Secure isn't needed"

A current HTTPS connection does not guarantee every future cookie transmission starts over HTTPS, especially with redirects, proxy misconfigurations, or secondary HTTP endpoints. **Fix:** enforce **Secure=true**, enforce HTTPS, and verify at the public edge.

### 10.2. "HttpOnly prevents XSS/CSRF"

HttpOnly only restricts how JavaScript reads cookies. XSS can still use the browser to act on the user's behalf; CSRF relies on cookies sent automatically under matching conditions. **Fix:** prevent XSS, use CSRF tokens for session auth, enforce authorization, restrict CORS, and apply appropriate SameSite.

### 10.3. "SameSite=Lax means all cross-site requests are blocked"

Lax has an exception for top-level navigations using safe methods; different subdomains on the same site are also not cross-site. **Fix:** understand site vs. origin, never use GET to mutate state, and keep CSRF tokens for state-changing requests.

### 10.4. "Cookie Max-Age=30m means the user stays logged in for 30m"

False if the server timeout is 15m or the account/session is locked or revoked earlier. **Fix:** clearly define idle timeout, cookie lifetime, absolute lifetime, and re-authentication; test both client and server sides.

### 10.5. "Setting Path=/api makes /login safer"

If login/logout sit outside /api, the cookie may not be sent to endpoints needing the session. Path is not a security sandbox. **Fix:** choose a Path covering the exact URLs of a session and test callback/login/logout flows.

### 10.6. "Domain=.example.com is always great for sharing logins"

A wide Domain sends cookies to multiple subdomains, enlarging the secret exposure surface. **Fix:** prefer host-only; when multi-host SSO is needed, design proper IdP/SSO rather than broadcasting the same JSESSIONID across every subdomain.

### 10.7. "Logout only needs deleting the cookie in the browser"

The server session may still exist and be reused if the ID was stolen earlier. **Fix:** server invalidates the session and clears SecurityContext, then clears the cookie with matching name/Path/Domain.

### 10.8. "Enabled Secure=true, tested on http://localhost, and login failed"

Browsers may withhold Secure cookies over HTTP; localhost exceptions are inconsistent across browsers and tools. **Fix:** use HTTPS localhost with a trusted certificate or dedicated header tests, never bring HTTP dev config into production.

### 10.9. "MockMvc tests are enough to prove production Set-Cookie"

MockMvc does not run the full embedded container/proxy/browser stack. **Fix:** test properties/HTTP headers on a real container, add E2E tests on an HTTPS domain behind ingress, and inspect the browser cookie store.

## 11. Pre-Production Checklist

- [ ] Website and every endpoint receiving cookies/credentials use **HTTPS**; TLS certificates are verified.
- [ ] Session cookie has **Secure**, **HttpOnly**, and **SameSite** per real requirements.
- [ ] Cookie has the right **Path** for login/logout/API/callbacks; do not pick Path out of habit.
- [ ] Prefer **host-only** (omit Domain) unless genuinely sharing across subdomains.
- [ ] Use **__Host-** only when the app satisfies Secure + Path=/ + no Domain; test browsers and logout.
- [ ] **Cookie Max-Age/Expires** and **server session timeout** are chosen, documented, and tested separately.
- [ ] Have policies for **absolute session lifetime**, session fixation, post-logout invalidation, and revocation if security requires.
- [ ] Proper **CSRF** protection when browsers send cookies automatically; do not rely solely on SameSite.
- [ ] Never put session IDs, Cookie/Set-Cookie, or passwords in logs, metrics, exceptions, or URLs.
- [ ] Configure reverse proxies, trusted forwarded headers, and internal TLS to match the deployment model.
- [ ] Test against real servers and real browsers on staging/production domains, inspecting **Set-Cookie** and **Cookie** requests.
- [ ] Cross-origin frontends configure CORS/credentials properly; never allow wildcard origins with credentialed requests.
- [ ] Distinguish session cookies from remember-me, refresh tokens, and other long-lived tokens.
- [ ] If using Spring Session, verify datastore TTLs and the cookie serializer; do not guess from Servlet container defaults.

## 12. References

- [Spring Boot 3.5 — Common Application Properties](https://docs.spring.io/spring-boot/3.5/appendix/application-properties/): **server.servlet.session.cookie.*** and **server.servlet.session.timeout** properties.
- [Spring Boot 3.5 — Servlet Web Applications / SameSite Cookies](https://docs.spring.io/spring-boot/3.5/reference/web/servlet.html): configuring SameSite on Servlet containers and Spring Session.
- [Spring Security 6.5 — Authentication Persistence and Session Management](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/session-management.html): SecurityContext, session fixation, and session management.
- [Spring Security 6.5 — CSRF](https://docs.spring.io/spring-security/reference/6.5/servlet/exploits/csrf.html): protecting state-changing requests using cookie-based authentication.
- [Spring Security 6.5 — Handling Logout](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/logout.html): invalidation, clearing authentication, and cookie/logout handling.
- [MDN — Set-Cookie](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Set-Cookie): Secure, HttpOnly, Domain, Path, SameSite, Max-Age, Expires, cookie prefixes.
- [MDN — Secure cookie configuration](https://developer.mozilla.org/en-US/docs/Web/Security/Practical_implementation_guides/Cookies): principles for minimizing cookie exposure and scope.
