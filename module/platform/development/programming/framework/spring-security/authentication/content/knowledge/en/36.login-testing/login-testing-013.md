# Testing through containers, proxies, and browsers for real-world cookie and TLS behavior

## 1. Goal and starting scenario

A Spring Security application uses form login. `MockMvc` validates the username/password properly and returns a redirect on success. However, in production behind Nginx/a load balancer, users may get sent back to the login page because the browser **does not retain or send JSESSIONID**, the cookie lacks `Secure`/`SameSite`, the proxy passes the wrong scheme/port, or sessions are not shared across pods.

This is why you must test through **containers, proxies, TLS handshakes, and a real browser**, instead of running Java unit tests alone.

After this lesson, you can:
- Distinguish Java/Spring authentication from user-agent cookie/session behavior.
- Inspect `Set-Cookie`, `Secure`, `HttpOnly`, `SameSite`, `Path`, `Domain`, session expiration, session fixation, and logout.
- Verify public HTTPS URLs, certificate SANs, trust chains, and redirects; without using `curl -k` or `ignoreHTTPSErrors:true` to “pass” tests.
- Deploy a lab with Spring Boot **3.3.12**, Java **17+**, Docker Compose, Nginx TLS termination, and Chromium/Playwright.
- Test a real cross-site POST from `127.0.0.1` to `localhost`, distinguishing SameSite cookies from CSRF tokens.
- Verify that `Forwarded`/`X-Forwarded-*` cannot be spoofed by an attacker and the backend does not expose a direct HTTP port.
- Use JDK `HttpClient` to measure TLS and cookie flags without confusing it with browser policies.
- Build a test matrix covering nodes, session stores, CI, certificate rotation, and browser compatibility.

**Scope:** Spring Security Servlet/Spring MVC. For WebFlux, use a reactive `SecurityWebFilterChain` and do not copy `HttpSecurity` verbatim. Hosts and passwords in this lesson are **lab-only data**.

## 2. Why test layers must be separated

| Layer | Good at checking | Insufficient to prove |
| --- | --- | --- |
| JUnit unit tests | PasswordEncoder, UserDetails, login and account-lock logic | TLS, browser cookie acceptance |
| MockMvc | Spring Security filters, CSRF, login/logout status, simulated redirect logic | Handshake, certificate hostname, SameSite cookie sending |
| Curl/JDK HttpClient | HTTPS handshake/CA when not bypassed, status, Location, Set-Cookie | Browser navigation/iframe/site-for-cookies |
| Docker Compose/Testcontainers | App, proxy, network, container ports, and forwarding | Whether the browser stores/sends cookies |
| Playwright | Browser cookie jar, HTTPS page load, network Cookie header, SameSite, E2E login/logout | Other browsers/OSes and multi-node production |
| Multi-node staging | LB, sticky routing, shared sessions, restart/revocation, cert rotation | Does not replace authorization/code review |

**Measurement principle:** You must observe a post-login request **sent by the browser with Cookie attached** and the backend resolving the right principal. Merely seeing HTTP 200 on the login request, or seeing the server emit `Set-Cookie`, is not enough.

## 3. Cookie attributes to inspect

Example response:

~~~http
HTTP/1.1 200 OK
Set-Cookie: JSESSIONID=<random-id>; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

**`Secure`:** the browser restricts the cookie to HTTPS, with a `localhost` exception in some browsers. Do not use HTTP localhost tests to conclude that a Secure cookie can never leak over public HTTP.

**`HttpOnly`:** JavaScript cannot read the session ID via `document.cookie`, yet the browser still automatically sends the cookie according to policy. HttpOnly does **not** replace CSRF defense.

**`SameSite=Lax`:** restricts most cross-site unsafe requests such as POST; the cookie may still be sent on top-level safe navigation. `Strict` is tighter; `None` requires `Secure` and also depends on third-party cookie restrictions. `SameSite` does not eliminate all CSRF.

**`Path`:** determines which URL paths receive the cookie. `Path=/` covers the application at root.

**`Domain`:** if omitted, the cookie is **host-only**; if set to `Domain=example.org`, it may be sent to multiple subdomains, including lower-trust subdomains. With the browser API `context.cookies()`, the domain field is normalized; you need to inspect **raw Set-Cookie** to confirm the header has no `Domain` attribute.

**`Expires`/`Max-Age`:** browser-side cookie persistence differs from server-side session TTL. A cookie still existing does not mean the server session is still valid.

**`JSESSIONID`:** is a bearer secret; do not log cookie values or publish Playwright storage state/traces containing real cookies in public artifacts.

### 3.1. Same-origin vs same-site

~~~text
https://localhost:8443  vs  https://localhost:9443
=> Different origin due to port, yet usually SAME site.

https://localhost:8443  vs  https://127.0.0.1:9443
=> Different host and different site (suitable for a cross-site lab).

https://app.example.org  vs  https://blog.example.org
=> Different origin yet usually same site by registrable domain.
~~~

To test that `SameSite=Lax` omits the cookie on a cross-site POST, **do not** merely change the port on the same `localhost`. You must use a genuinely different site such as a loopback IP address in the lab. Behavior also depends on scheme, request method, top-level navigation, iframes, and browser version.

### 3.2. Three pieces of cookie evidence

1. **Raw response `Set-Cookie`:** what attributes does the backend/proxy emit?
2. **Browser cookie jar:** does the browser accept/store it with the expected flags?
3. **Subsequent browser network request:** does the browser actually send the cookie for the target URL and context?

`curl` seeing `Set-Cookie` is not enough to prove the browser stored it. `document.cookie` not showing `JSESSIONID` can be **correct** due to HttpOnly. Combine all three pieces of evidence and verify the server-side principal/session.

## 4. Real TLS and reverse proxies

Over public HTTPS, the client needs to verify:
- Certificate chain up to a trusted CA, with the leaf cert having a SAN matching the hostname/IP.
- Valid cert dates, matching SNI/hostname, and trust store alignment.
- Handshake using policy-compliant TLS version/ciphers (typically TLSv1.2/TLSv1.3).
- No downgrade to HTTP during login, logout, or redirects.
- Session cookie has `Secure` and the browser only uses it over the corresponding protected connection.
- The reverse proxy may convert TLS→internal HTTP only when the network/application has a clear trust boundary.
- Do not accept client-supplied `Forwarded: proto=https;host=attacker.invalid` as source of truth.

**Avoid anti-patterns:** `curl -k`, `ignoreHTTPSErrors:true`, Java trust-all `SSLContext`/`HostnameVerifier`, skipping certificate checks in CI. They may be used temporarily to isolate failures in a private diagnostic environment, **not as passing TLS tests**.

Spring may see `request.isSecure()==true` from forwarded headers even when the client did not actually verify the certificate. Therefore you must test **from the browser/HTTP client side**, not merely assert request metadata inside the JVM.

## 5. End-to-end lab architecture

~~~text
Browser / Playwright
   |
   +--> https://localhost:8443
   |          |
   |          v
   |       Nginx TLS:443
   |          | X-Forwarded-Proto=https
   |          | X-Forwarded-Host=localhost:8443
   |          | X-Forwarded-Port=8443
   |          v
   |       Spring Boot app:8080 (Docker private network)
   |
   +--> https://127.0.0.1:9443
              |
              v
           Nginx static attack.html:4444
              |
              +-- HTML form POST -> https://localhost:8443/profile/name
~~~

Both the target site and attack site belong to the lab. `app` **does not publish port 8080 to the host**; only Nginx publishes 8443/9443 to loopback `127.0.0.1`. Testers never send real credentials to addresses outside their control.

Structure:

~~~text
cookie-tls-login-lab/
├── settings.gradle
├── build.gradle
├── Dockerfile
├── compose.yaml
├── nginx.conf
├── certs/                     # generated; do not commit
├── attacker/attack.html
├── src/main/
│   ├── java/demo/cookie/
│   │   ├── CookieApplication.java
│   │   ├── SecurityConfig.java
│   │   └── SessionController.java
│   └── resources/application.yml
├── HttpsCookieProbe.java
├── package.json
├── playwright.config.js
└── e2e/session.spec.js
~~~

`.gitignore`:

~~~gitignore
certs/
build/
.gradle/
node_modules/
playwright-report/
test-results/
*.trace.zip
~~~

Do not commit leaf private keys, CA private keys, browser storage state, or logs containing verbatim Cookie/Set-Cookie values.

## 6. Spring Boot 3.3.12 + Java 17: build and session configuration

`settings.gradle`:

~~~groovy
rootProject.name = 'cookie-tls-login-lab'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.12'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'demo'
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
~~~

`src/main/resources/application.yml`:

~~~yaml
server:
  port: 8080
  forward-headers-strategy: framework
  tomcat:
    redirect-context-root: false
  servlet:
    session:
      cookie:
        secure: true
        http-only: true
        same-site: lax

spring:
  application:
    name: cookie-tls-login-lab
~~~

- `secure: true` requires the issued session cookie to carry Secure, even when the proxy calls the app over internal HTTP.
- `http-only: true` prevents JS from reading the session cookie.
- `same-site: lax` is an explicit value, avoiding reliance on browser defaults.
- `forward-headers-strategy: framework` enables Spring's `ForwardedHeaderFilter`. **Use only when the proxy is controlled, strips and overwrites forwarded headers, and the backend is not public**.
- `redirect-context-root: false` helps Tomcat behind a TLS-terminating proxy apply the forwarded scheme at the right time when generating redirects.

**Do not treat `server.forward-headers-strategy=framework` itself as “secure”**: the app can trust spoofed headers if ingress passes them through without sanitization.

### 6.1. Entrypoint

`src/main/java/demo/cookie/CookieApplication.java`:

~~~java
package demo.cookie;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CookieApplication {
    public static void main(String[] args) {
        SpringApplication.run(CookieApplication.class, args);
    }
}
~~~

### 6.2. Spring Security: form login, CSRF, and logout

`src/main/java/demo/cookie/SecurityConfig.java`:

~~~java
package demo.cookie;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
                User.withUsername("student")
                        .password(encoder.encode("lab-password-123456"))
                        .roles("USER")
                        .build());
    }

    @Bean
    SecurityFilterChain security(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/health").permitAll()
                        .anyRequest().authenticated())
                .formLogin(login ->
                        login.defaultSuccessUrl("/whoami", true))
                .logout(Customizer.withDefaults())
                .csrf(Customizer.withDefaults())
                .build();
    }
}
~~~

Spring Security renders `GET /login` and handles `POST /login`; it redirects on success to `/whoami`. With CSRF enabled, the login form includes a hidden token; `POST /logout` also requires a token, while `GET /logout` is typically a confirmation page. Before login, a session may be created to hold the CSRF token; after login, the session ID rotates by default (session fixation protection). `InMemoryUserDetailsManager` is for the lab only; production uses an appropriate user store, account status checks, MFA, and rate limiting.

### 6.3. Controller to inspect public scheme/host/port and test CSRF

`src/main/java/demo/cookie/SessionController.java`:

~~~java
package demo.cookie;

import java.security.Principal;
import java.util.Map;
import java.util.concurrent.atomic.AtomicReference;

import jakarta.servlet.http.HttpServletRequest;

import org.springframework.http.MediaType;
import org.springframework.security.web.csrf.CsrfToken;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.util.HtmlUtils;

@RestController
public class SessionController {

    // Lab only: single shared variable; production must store per account ID.
    private final AtomicReference<String> displayName =
            new AtomicReference<>("Initial");

    @GetMapping(value = "/health", produces = MediaType.TEXT_PLAIN_VALUE)
    public String health() {
        return "OK";
    }

    @GetMapping("/whoami")
    public Map<String, Object> whoami(
            Principal principal, HttpServletRequest request) {
        return Map.of(
                "user", principal.getName(),
                "scheme", request.getScheme(),
                "secure", request.isSecure(),
                "host", request.getServerName(),
                "port", request.getServerPort());
    }

    @GetMapping("/profile/name")
    public Map<String, String> readProfile() {
        return Map.of("displayName", displayName.get());
    }

    @GetMapping(value = "/settings",
            produces = MediaType.TEXT_HTML_VALUE)
    public String settings(HttpServletRequest request) {
        CsrfToken token = (CsrfToken) request.getAttribute(
                CsrfToken.class.getName());
        if (token == null) {
            throw new IllegalStateException("CSRF token unavailable");
        }

        return """
                <!doctype html>
                <html lang="en">
                <head><meta charset="UTF-8"></head>
                <body>
                <form method="post" action="/profile/name">
                  <input type="hidden" name="%s" value="%s">
                  <label for="displayName">Display name</label>
                  <input id="displayName" name="value">
                  <button type="submit">Save</button>
                </form>
                </body></html>
                """.formatted(
                        HtmlUtils.htmlEscape(token.getParameterName()),
                        HtmlUtils.htmlEscape(token.getToken()));
    }

    @PostMapping("/profile/name")
    public Map<String, String> updateProfile(
            @RequestParam String value) {
        if (value.isBlank() || value.length() > 80) {
            throw new IllegalArgumentException("Invalid display name");
        }

        displayName.set(value);
        return Map.of("displayName", displayName.get());
    }
}
~~~

- `/whoami` returns the principal, `request.getScheme()`, `isSecure()`, and host/port **as seen by Spring** after trusted forwarding. To prove real TLS, tests must verify the certificate from the client.
- `/settings` contains a POST form with `CsrfFilter`'s CSRF token; it uses `HtmlUtils.htmlEscape` when rendering.
- `GET /profile/name` lets you observe state; POST requires an authenticated session and CSRF token. If a POST without a token causes side effects, the security configuration has a bug.
- Production should use a template engine (Thymeleaf/JSP) with CSRF support rather than building forms via raw strings, and enforce per-user/tenant authorization. A global `AtomicReference` is not suitable for production.

## 7. Container image and networking

`Dockerfile`:

~~~dockerfile
FROM gradle:8.10.2-jdk17 AS build
WORKDIR /workspace
COPY settings.gradle build.gradle ./
COPY src ./src
RUN gradle --no-daemon bootJar

FROM eclipse-temurin:17-jre
WORKDIR /app
COPY --from=build /workspace/build/libs/*.jar /app/app.jar
EXPOSE 8080
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
~~~

`EXPOSE 8080` is image metadata and does not publish a host port. Production needs non-root execution, pinned image digests, vulnerability scanning, resource limits, secrets management, and monitoring.

`compose.yaml`:

~~~yaml
services:
  app:
    build: .
    expose:
      - "8080"
    networks:
      - private

  gateway:
    image: nginx:1.27-alpine
    depends_on:
      - app
    ports:
      - "127.0.0.1:8443:443"
      - "127.0.0.1:9443:4444"
    volumes:
      - "./nginx.conf:/etc/nginx/conf.d/default.conf:ro"
      - "./certs:/etc/nginx/certs:ro"
      - "./attacker:/usr/share/nginx/html/attacker:ro"
    networks:
      - private

networks:
  private:
    driver: bridge
~~~

`app` has no `ports` declaration, so Compose publishes no direct HTTP port. Other containers on the same Docker network can still reach `app`; production must isolate networks and restrict proxy trust. Both public ports bind only to the host loopback. `depends_on` does not mean health-ready; CI must poll `/health` after startup.

## 8. Nginx TLS termination and protecting Forwarded headers

`nginx.conf`:

~~~nginx
server {
    listen 443 ssl;
    server_name localhost;

    ssl_certificate     /etc/nginx/certs/localhost.pem;
    ssl_certificate_key /etc/nginx/certs/localhost-key.pem;
    ssl_protocols TLSv1.2 TLSv1.3;

    if ($host != "localhost") { return 421; }

    location / {
        proxy_pass http://app:8080;
        proxy_http_version 1.1;

        proxy_set_header Host "localhost:8443";
        proxy_set_header X-Forwarded-Proto "https";
        proxy_set_header X-Forwarded-Host "localhost:8443";
        proxy_set_header X-Forwarded-Port "8443";
        proxy_set_header X-Forwarded-For $remote_addr;
        proxy_set_header Forwarded "";
        proxy_set_header X-Forwarded-Prefix "";
        proxy_set_header Connection "";
        proxy_redirect off;
    }
}

server {
    listen 4444 ssl;
    server_name 127.0.0.1;

    ssl_certificate     /etc/nginx/certs/localhost.pem;
    ssl_certificate_key /etc/nginx/certs/localhost-key.pem;
    ssl_protocols TLSv1.2 TLSv1.3;

    location / {
        root /usr/share/nginx/html/attacker;
        try_files $uri =404;
    }
}
~~~

**Key point:** The public port is `8443`, while Nginx listens internally on `443`. Forwarding must preserve public `https://localhost:8443`, **not** generate redirects to `http://app:8080` or the wrong port `443`. Nginx uses fixed values in the lab, overwriting `X-Forwarded-Proto`/Host/Port and clearing any client-supplied `Forwarded` header. Avoid trusting `$http_host` directly without an allowlist. In production with multiple virtual hosts, implement explicit canonical host routing and trust boundaries.

If edge Nginx terminates TLS to internal HTTP, protect the upstream leg with appropriate network policy/mTLS/segmentation. **A `Secure` cookie does not mean the internal upstream hop is automatically encrypted**.

## 9. Cross-site page simulating a form POST

`attacker/attack.html`:

~~~html
<!doctype html>
<html lang="en">
<head><meta charset="UTF-8"><title>Local CSRF demonstration</title></head>
<body>
  <form method="post"
        action="https://localhost:8443/profile/name">
    <input type="hidden" name="value" value="FORGED">
    <button id="attack" type="submit">Send test POST</button>
  </form>
</body>
</html>
~~~

The test must open `https://127.0.0.1:9443/attack.html`. The form's target is `https://localhost:8443/profile/name` — **a different site**. A `SameSite=Lax` cookie is not attached by the browser on a typical cross-site top-level POST; and `CsrfFilter` still rejects it because the POST lacks a CSRF token. Both defense layers must be tested separately; never treat SameSite as a reason to disable CSRF.

This is a safe PoC sent only to the lab's own app; do not test against services outside your ownership.

## 10. Issuing local certificates and verifying HTTPS

### 10.1. mkcert

Install `mkcert` per your OS instructions; on Linux/macOS:

~~~bash
mkdir -p certs
mkcert -install
mkcert -cert-file certs/localhost.pem \
       -key-file certs/localhost-key.pem \
       localhost 127.0.0.1 ::1
~~~

- `localhost.pem` is the leaf cert containing SANs for the lab hostnames/IPs.
- `localhost-key.pem` holds the **private leaf key**; do not commit or share it.
- `$(mkcert -CAROOT)/rootCA.pem` is the public CA certificate.
- `$(mkcert -CAROOT)/rootCA-key.pem` is the **private CA key**; never put it in the repo, containers, or CI artifacts.

`mkcert -install` may add the CA to the OS trust store, yet Playwright-managed browsers and the JDK/Node may use different trust stores. Tests **must** verify real HTTPS in the actual client rather than inferring trust from having run `mkcert -install`.

### 10.2. Running Compose and using curl with CA verification

~~~bash
docker compose up --build -d

curl --cacert "$(mkcert -CAROOT)/rootCA.pem" \
     -i https://localhost:8443/health

curl --cacert "$(mkcert -CAROOT)/rootCA.pem" \
     -i https://127.0.0.1:9443/attack.html
~~~

`GET /health` is expected to return 200/`OK` once the app is ready. If it returns 502 right after startup, use bounded readiness polling and inspect Docker logs instead of turning off TLS. `curl -k` simply disables certificate validation and does not belong in verification tests.

You can inspect the TLS chain:

~~~bash
openssl s_client -connect localhost:8443 \
  -servername localhost \
  -CAfile "$(mkcert -CAROOT)/rootCA.pem" \
  -verify_return_error </dev/null
~~~

When the cert/CA match, chain verification succeeds and the TLS protocol belongs to the allowed set. Hostname SANs should additionally be verified via curl/browser because `openssl s_client` on some versions does not enforce hostname verification by default unless configured.

### 10.3. Verifying redirects and header spoofing

~~~bash
curl --cacert "$(mkcert -CAROOT)/rootCA.pem" \
  -i https://localhost:8443/whoami

curl --cacert "$(mkcert -CAROOT)/rootCA.pem" -i \
  -H 'Forwarded: proto=http;host=evil.invalid' \
  -H 'X-Forwarded-Proto: http' \
  -H 'X-Forwarded-Host: evil.invalid' \
  https://localhost:8443/whoami
~~~

When unauthenticated, Spring redirects to login. The `Location` header may be relative or absolute depending on the redirect strategy. If absolute, it must use the **public HTTPS origin** with the right port. There must be no `evil.invalid` or `http://app:8080`. Production requires testing multiple hosts/virtual hosts and proxy chains, not just these three headers.

## 11. Java 17 HttpClient checking TLS/Set-Cookie (without logging IDs)

JDK `HttpClient` makes a real HTTPS connection and reads raw `Set-Cookie`, yet does **not** simulate full browser SameSite/navigation behavior.

File `HttpsCookieProbe.java`:

~~~java
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.util.List;
import java.util.Locale;

public final class HttpsCookieProbe {

    static boolean has(String cookie, String flag) {
        for (String part : cookie.split(";")) {
            if (part.trim().equalsIgnoreCase(flag)) {
                return true;
            }
        }
        return false;
    }

    public static void main(String[] args) throws Exception {
        HttpClient client = HttpClient.newBuilder()
                .connectTimeout(Duration.ofSeconds(5))
                .followRedirects(HttpClient.Redirect.NEVER)
                .build();

        HttpRequest request = HttpRequest.newBuilder(
                URI.create("https://localhost:8443/login"))
                .timeout(Duration.ofSeconds(10))
                .GET()
                .build();

        HttpResponse<Void> response = client.send(
                request, HttpResponse.BodyHandlers.discarding());

        List<String> headers =
                response.headers().allValues("set-cookie");

        String session = headers.stream()
                .filter(s -> s.startsWith("JSESSIONID="))
                .findFirst()
                .orElseThrow(() ->
                        new IllegalStateException("Missing JSESSIONID"));

        System.out.println("HTTP: " + response.statusCode());
        System.out.println("TLS: "
                + response.sslSession().isPresent());
        System.out.println("Cookie: true");
        System.out.println("Secure: " + has(session, "Secure"));
        System.out.println("HttpOnly: " + has(session, "HttpOnly"));
        System.out.println("SameSite=Lax: "
                + has(session, "SameSite=Lax"));
        System.out.println("Host-only: "
                + !session.toLowerCase(Locale.ROOT)
                        .contains("; domain="));
    }
}
~~~

Run:

~~~bash
javac HttpsCookieProbe.java

# The JVM may not automatically trust the OS local CA; create a dedicated truststore
# with the PUBLIC root certificate (not rootCA-key.pem).
keytool -importcert -noprompt \
  -alias lab-ca \
  -file "$(mkcert -CAROOT)/rootCA.pem" \
  -keystore certs/java-truststore.p12 \
  -storetype PKCS12 -storepass changeit

java -Djavax.net.ssl.trustStore=certs/java-truststore.p12 \
     -Djavax.net.ssl.trustStorePassword=changeit \
     HttpsCookieProbe
~~~

Expected output **if the lab is configured and the certificate is trusted by the JVM**:

~~~text
HTTP: 200
TLS: true
Cookie: true
Secure: true
HttpOnly: true
SameSite=Lax: true
Host-only: true
~~~

`changeit` is only a truststore password holding the public CA for the lab, not a production credential. Do not modify the JDK default cacerts or create a trust-all verifier to run tests. `HttpClient` in Java 17 is not `AutoCloseable` for use with try-with-resources. **Do not print the session ID** even though raw Set-Cookie is present in the response.

The JDK probe result proves TLS and the cookie attributes seen by an HTTP client, **not** that a browser accepts/sends the cookie according to SameSite.

## 12. Playwright Chromium: cookie jar, session, CSRF, and cross-site

### 12.1. Setup

`package.json`:

~~~json
{
  "private": true,
  "type": "module",
  "scripts": { "test:e2e": "playwright test" },
  "devDependencies": { "@playwright/test": "^1.56.1" }
}
~~~

~~~bash
npm install
npx playwright install chromium
~~~

`playwright.config.js`:

~~~javascript
import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  workers: 1,
  use: {
    baseURL: "https://localhost:8443",
    ignoreHTTPSErrors: false,
    trace: "retain-on-failure"
  },
  projects: [
    { name: "chromium", use: { browserName: "chromium" } }
  ]
});
~~~

**Important:** Playwright-managed Chromium must trust `mkcert`'s public CA. Otherwise, configure the browser trust store properly on the runner/OS. **Do not change `ignoreHTTPSErrors` to true**, because doing so loses proof of TLS hostname/chain verification. `trace` may contain request metadata/cookies; use only lab user/password credentials and restrict access.

### 12.2. Full Browser E2E

`e2e/session.spec.js`:

~~~javascript
import { test, expect } from "@playwright/test";

const BASE = "https://localhost:8443";
const ATTACK = "https://127.0.0.1:9443";

async function login(page) {
  const response = await page.goto(BASE + "/login");
  expect(response?.status()).toBe(200);
  await page.locator('input[name="username"]').fill("student");
  await page.locator('input[name="password"]').fill(
    "lab-password-123456");
  await page.locator('button[type="submit"]').click();
  await expect(page).toHaveURL(BASE + "/whoami");
}

test("HTTPS cookie flags, public scheme, session rotation", async ({
  page, context
}) => {
  await page.goto(BASE + "/login");
  const before = (await context.cookies(BASE))
    .find(c => c.name === "JSESSIONID");
  expect(before).toBeDefined();

  await page.locator('input[name="username"]').fill("student");
  await page.locator('input[name="password"]').fill(
    "lab-password-123456");
  await page.locator('button[type="submit"]').click();
  await expect(page).toHaveURL(BASE + "/whoami");

  const after = (await context.cookies(BASE))
    .find(c => c.name === "JSESSIONID");
  expect(after).toBeDefined();
  expect(after.secure).toBe(true);
  expect(after.httpOnly).toBe(true);
  expect(after.sameSite).toBe("Lax");
  expect(after.path).toBe("/");
  expect(after.value).not.toBe(before.value);

  const whoami = await page.evaluate(async () => {
    const r = await fetch("/whoami");
    return r.json();
  });
  expect(whoami.user).toBe("student");
  expect(whoami.scheme).toBe("https");
  expect(whoami.secure).toBe(true);
  expect(whoami.host).toBe("localhost");
  expect(whoami.port).toBe(8443);

  const readable = await page.evaluate(() => document.cookie);
  expect(readable).not.toContain("JSESSIONID=");

  const reqPromise = page.waitForRequest(r =>
    r.url() === BASE + "/whoami" && r.method() === "GET"
  );
  await page.reload();
  const request = await reqPromise;
  const headers = await request.allHeaders();
  expect(headers.cookie ?? "").toContain("JSESSIONID=");
});

test("POST missing CSRF cannot mutate; valid form can", async ({ page }) => {
  await login(page);
  await page.goto(BASE + "/settings");

  const before = await page.evaluate(async () => {
    const r = await fetch("/profile/name");
    return r.json();
  });

  const status = await page.evaluate(async () => {
    const r = await fetch("/profile/name", {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: new URLSearchParams({ value: "FORGED" })
    });
    return r.status;
  });
  expect(status).toBe(403);

  const unchanged = await page.evaluate(async () => {
    const r = await fetch("/profile/name");
    return r.json();
  });
  expect(unchanged.displayName).toBe(before.displayName);

  await page.locator("#displayName").fill("Approved");
  await page.locator('button[type="submit"]').click();
  await expect(page.locator("body"))
    .toContainText('"displayName":"Approved"');
});

test("cross-site POST has no Lax session cookie", async ({
  page, context
}) => {
  await login(page);

  const foreign = await context.newPage();
  const html = await foreign.goto(ATTACK + "/attack.html");
  expect(html?.status()).toBe(200);

  const requestPromise = foreign.waitForRequest(r =>
    r.url() === BASE + "/profile/name" && r.method() === "POST"
  );
  const responsePromise = foreign.waitForResponse(r =>
    r.url() === BASE + "/profile/name" &&
    r.request().method() === "POST"
  );

  await foreign.locator("#attack").click();
  const forgedRequest = await requestPromise;
  const headers = await forgedRequest.allHeaders();
  expect(headers.cookie ?? "").not.toContain("JSESSIONID=");

  const forgedResponse = await responsePromise;
  expect(forgedResponse.status()).toBe(403);
});

test("logout POST with CSRF invalidates session", async ({ page }) => {
  await login(page);
  await page.goto(BASE + "/logout");
  await page.locator('form[action="/logout"] button').click();

  await expect(page).toHaveURL(/\/login\?logout/);
  await page.goto(BASE + "/whoami");
  await expect(page).toHaveURL(/\/login/);
});
~~~

**Four verified tests:**
1. A real browser stores the session cookie with the expected flags; the session ID rotates after login, JS cannot read the HttpOnly cookie, yet same-origin network requests **do send** JSESSIONID; the backend sees the public scheme/host/port via trusted forwarding.
2. An unsafe POST **with a browser session** but without a CSRF token returns 403 and does not mutate state; a form rendering the proper token succeeds in updating it.
3. A cross-site top-level POST from a loopback IP to the localhost hostname **does not send** the `SameSite=Lax` cookie, and the server's CSRF filter rejects the request.
4. GET logout is only a confirmation page, and POST logout with a token invalidates the session; protected GET requests after logout redirect back to login.

If you want to measure SameSite, **do not use** Playwright's `context.request.post()` or Java's `CookieManager` because HTTP clients do not fully simulate browser site-for-cookies behavior. Use `page`/`BrowserContext` and observe actual network requests via `request.allHeaders()`.

### 12.3. Running browser tests

~~~bash
npm run test:e2e

# Observe the browser visually while investigating:
npx playwright test --headed --project=chromium
~~~

**Expected: 4 passing tests**, provided app/proxy/cert/trust/browser match the lab. This is expected behavior, **not a certified run result**. If Playwright fails due to TLS, fix CA/SAN/trust; if due to cookies/CSRF, inspect DevTools network/the Spring Security chain instead of disabling protections. You should add Firefox/WebKit and mobile browsers matching your product's scope.

## 13. Additional testing with MockMvc: right layer, not an E2E replacement

A Spring Boot test with `MockMvc` checks `CsrfFilter` logic:

~~~java
// Test snippet inside @SpringBootTest + @AutoConfigureMockMvc,
// with static imports MockMvcRequestBuilders.*, csrf(), status().
mvc.perform(post("/login")
        .param("username", "student")
        .param("password", "lab-password-123456"))
    .andExpect(status().isForbidden());

mvc.perform(post("/login")
        .with(csrf())
        .param("username", "student")
        .param("password", "lab-password-123456"))
    .andExpect(status().is3xxRedirection());
~~~

This **does not** open TCP/TLS, has no cert SAN, does not pass through Nginx, and does not prove the browser received the cookie or `SameSite`. Use MockMvc for filters/Providers; use Docker/proxy/curl to measure networking and Playwright to measure browsers.

## 14. Reverse proxy and forwarded header issues

A request has three different schemes/hosts:
1. **Browser public URL:** `https://localhost:8443`.
2. **Nginx upstream URL:** `http://app:8080`, only inside the private network.
3. **Spring logical request:** after trusted forwarding, it should be `https` + `localhost` + port `8443`.

If Spring generates a redirect to `http://app:8080/login`, the bug is usually in `X-Forwarded-Proto`/Host/Port or Boot's forwarding strategy. If client-supplied headers produce `Location: https://evil.invalid`, that is a host header poisoning/open redirect risk. **Fix at ingress**: validate host allowlist, overwrite/strip Forwarded headers, and do not expose the backend publicly. Never trust arbitrary client-forwarded hops.

**When there are multiple proxies:** you must clearly define which proxies are trusted, which headers get overwritten, and the network trust tiers. With TLS termination in one container and internal HTTP upstream, evaluate mTLS/segmentation if the internal hop crosses another boundary. A `Secure` cookie does not automatically encrypt internal hops.

## 15. Troubleshooting by observed symptom

| Symptom | Possible cause | How to check |
| --- | --- | --- |
| Login succeeds yet redirects back to login | Browser rejects cookie, session store fails to restore | Set-Cookie, browser jar, subsequent request Cookie |
| Cookie missing Secure | Boot session cookie config/proxy scheme | application.yml, forwarded proto |
| Cookie exists yet is not sent | Path/Domain/SameSite/scheme/third-party policy | Browser DevTools cookie reason |
| JS cannot see JSESSIONID | **Correct** if HttpOnly | Network headers, cookie jar |
| `Location` points to internal host/container | Incorrect forwarded headers | public curl, Nginx config |
| Spoofed `Forwarded` header alters redirect | Proxy trusts client | Strip/overwrite, host allowlist |
| Browser HTTPS only works when ignoring errors | Cert trust/SAN/scheme mismatch | Fix certificate chain/trust |
| Curl passes yet Java hits PKIX error | JVM truststore lacks CA | Import public CA into dedicated truststore |
| POST profile returns 403 despite cookie | Missing/wrong CSRF token | Hidden field/header token and rotation |
| POST logout returns 403 | CSRF token missing after login | GET logout form, refresh right token |
| Cross-site cookie “still travels” when only changing port | Two origins yet same site | Change to a genuinely different host/site |
| App A logs in, app B loses session | No shared sessions | Redis/JDBC Spring Session or sticky LB |
| MockMvc passes yet browser rejects | Test bypasses cookie/TLS policies | Playwright E2E and browser matrix |
| Health 200 yet login fails | Health does not create a session | Test real login/cookie/CSRF/redirect |
| One browser passes, another fails | Differing cookie privacy/CA trust | Firefox/WebKit/Safari matrix |

Do not diagnose issues by printing all request headers: `Cookie`, `Authorization`, passwords, and CSRF tokens must be redacted. Log request ID, route, status, categorized errors, and upstream timing without bearer credentials.

### 15.1. Distinguishing cookie errors from session errors

- **Set-Cookie present, absent from browser jar:** likely rejected by the browser due to attributes/trust/privacy.
- **In browser jar, request omits Cookie:** scope/Path/SameSite/scheme/third-party rules.
- **Request has Cookie, server has no principal:** session expired/revoked, unshared store, wrong session ID, or proxy routing.
- **Request has Cookie/principal yet POST returns 403:** more likely CSRF/authorization, not necessarily a broken cookie.
- **Login returns 200 and sets cookie yet `/whoami` returns 302:** does not prove a persistent session; you must check the next request in the same context.

## 16. Testing load balancers and multi-node sessions

A single app instance in the lab uses in-memory sessions. Production with multiple app pods leads to:

~~~text
POST /login -> LB -> app-A holds session S
GET /profile -> LB -> app-B cannot find S
=> even though the browser sends the cookie, app-B treats it as not logged in
~~~

Solutions: sticky sessions (limited when a pod dies) or a **shared session repository** using Spring Session Redis/JDBC under a managed architecture.

Additional tests needed:
1. Log in on node A; route the next request to B, and verify the principal remains intact.
2. Scaling/rolling restarts, pod drains, and reconnects; sessions must not be lost outside policy.
3. Logging out on B invalidates the session so A no longer accepts it either.
4. Session TTL/idle timeout/absolute timeout work properly across the shared store, including clock skew.
5. Post-login session fixation rotation works across nodes, and the old ID cannot be reused.
6. Cookie Domain/Path/SameSite/Secure stay consistent across every ingress/instance.
7. Account-disabled/logout-all-sessions events propagate per SLA; still-valid tokens must have a revocation strategy.
8. DB/Redis outages do not turn authentication into **fail open**.

Do not claim single-node Compose tests production failover. Multi-node/session persistence requires staging and real or production-like datastores.

## 17. SameSite, CSRF, CORS, and SSO are distinct layers

- **SameSite:** controls when browsers send cookies by site; explicit Lax does not replace CSRF on same-site subdomains or GETs with side effects.
- **CSRF:** the server verifies tokens for unsafe methods with browser-auto-sent credentials; Spring Security protects POST login/logout by default.
- **CORS:** governs cross-origin JS reading responses and preflight; an HTML form can send a POST even if JS cannot read the response.
- **HttpOnly:** JS cannot read the cookie, yet the browser still sends it; does not prevent CSRF.
- **Secure:** cookie travels over secure transport; does not guarantee TLS from proxy to backend.
- **XSS:** scripts running on the same origin can submit valid CSRF tokens; requires CSP, output encoding, and code review.
- **OAuth2/OIDC/SAML:** callbacks/redirects use state, nonce, issuer/audience/signature checks, and their own CSRF/correlation; SameSite on session/callback cookies must be tested per browser/protocol rather than loosely relaxing to `None` or blindly disabling CSRF site-wide.
- **Bearer-only APIs:** if an API only accepts client-attached Authorization headers with no auto-sent cookies/Basic auth, the CSRF threat model differs. JWT in a cookie **still** carries CSRF risk.

Real-world cases also involve partitioned cookies, third-party cookie blocking, the Storage Access API, and mobile webviews. Do not assume one Chromium test represents every browser.

## 18. CI workflow and test reports

A reasonable CI pipeline:
1. JUnit/MockMvc tests, static analysis, and dependency checks.
2. Generate local test certs/CA and ensure the public CA is trusted by browsers/the JDK.
3. Build Docker images and start Nginx/app on the private network.
4. Poll `GET /health` using curl with `--cacert` and a bounded timeout; never use `-k`.
5. Run Playwright Chromium/Firefox/WebKit according to browser support.
6. Assert TLS trust, Secure/HttpOnly/SameSite, browser cookie sending, CSRF/POST, logout, and redirects.
7. Collect redacted logs/traces with limited retention; never upload CA private keys or real session cookies/passwords.
8. Clean up containers, volumes, test certs/private keys, and browser contexts, even when the job fails.
9. For multi-replica production, add session failover/sticky/Redis JDBC tests.

Shell skeleton:

~~~bash
set -eu
docker compose up --build -d

# Real CI needs readiness polling/timeouts and finally/trap cleanup.
curl --cacert "$(mkcert -CAROOT)/rootCA.pem" \
  --fail https://localhost:8443/health

npm run test:e2e
docker compose down --volumes
~~~

**Do not treat this as a complete CI script**: if a test fails, `set -e` stops before cleanup, so real pipelines use `trap/finally`. Startup time is non-deterministic, so a single curl may run before the app is healthy.

In QA reports, distinguish: **code written**, **compiled**, **Docker ran**, **TLS verify passed**, **browser tests actually passed**, **multi-node/staging tested**. Never claim a command ran without logs.

## 19. Pre-release test matrix

| ID | Behavior | Expected |
| --- | --- | --- |
| TLS-01 | Valid cert, SAN, CA chain | Browser/curl HTTPS without bypass |
| TLS-02 | Untrusted/wrong-host cert | Handshake/hostname verification fails |
| PROXY-01 | Trusted forwarding | Backend sees scheme=https, host=localhost, port=8443 |
| PROXY-02 | Header injection | No redirect to evil.invalid |
| PROXY-03 | Private backend | No unintended public direct HTTP port |
| COOKIE-01 | Session Set-Cookie | Secure; HttpOnly; SameSite=Lax; Path=/, no Domain |
| COOKIE-02 | Browser accepted cookie | `context.cookies()` has session with expected flags |
| COOKIE-03 | Same-origin HTTPS next request | Browser sends Cookie and is authenticated |
| COOKIE-04 | HttpOnly | `document.cookie` does not expose session ID |
| COOKIE-05 | Cross-site POST | SameSite Lax cookie does not accompany form POST |
| LOGIN-01 | Correct password | Right principal, session persists on subsequent request |
| LOGIN-02 | Wrong password | No authenticated session |
| LOGIN-03 | Session fixation | Session ID changes after login |
| CSRF-01 | POST missing token | 403, no side effect |
| CSRF-02 | POST with token | Succeeds when authenticated |
| LOGOUT-01 | GET logout | No side effect |
| LOGOUT-02 | POST logout + token | Session invalid, protected GET redirects to login |
| HA-01 | App node failover | Session shared/routed properly per policy |
| HA-02 | Multi-node logout | Old session is no longer accepted |
| OBS-01 | Logs/test artifacts | No leaked credentials/sessions/CA private keys |
| UA-01 | Chrome/Firefox/Safari | Browser support matrix verified |

## 20. Common mistakes

1. “MockMvc `.secure(true)` = real TLS.” **False**: there is no handshake.
2. “`curl -k` is an acceptable HTTPS test.” **False**: it disables cert validation.
3. “Server emitting Set-Cookie means the browser stored it.” **False**: the browser may reject it.
4. “A Secure cookie cannot be sent over HTTP localhost.” **Not always true** due to the localhost exception.
5. “HttpOnly prevents CSRF.” **False**: the browser still sends it automatically.
6. “Changing the port changes the site.” **False**: port changes the origin, not necessarily the site.
7. “CORS blocks reading the response, so form POSTs don't reach the server.” **False**.
8. “Public HTTPS on the proxy means the backend automatically knows the request is secure.” **Not guaranteed**.
9. “Setting Secure means proxy→backend also uses TLS.” **False**.
10. “Trusting client X-Forwarded-Proto is safe.” **False**: host/proto spoofing.
11. “Exposing backend 8080 publicly for debugging is harmless.” **Dangerous**: bypasses proxy/TLS.
12. “A broad JSESSIONID Domain is always more convenient.” **Risks subdomain takeover/cookie tossing**.
13. “Cookie not visible in document.cookie means user is not logged in.” **False** with HttpOnly.
14. “Java CookieManager behaves like Chrome SameSite.” **False**.
15. “HTTP 200 after login is enough.” **False**: you need the subsequent request.
16. “Logout succeeding on one pod revokes it across all pods.” **Not guaranteed**.
17. “We should disable CSRF when browser tests return 403.” **False**.
18. “Health 200 is enough.” **False**: health does not check cookies/login.
19. “One Chromium test represents all browsers.” **False**.
20. “Session test traces are non-sensitive.” **False**: traces/storage state may contain secrets.
21. “Use the local CA for production.” **False**: lab-only; production needs CA lifecycle management.
22. “`forward-headers-strategy=framework` guarantees trust.” **False**: ingress must overwrite/strip.
23. “Testing same localhost on different ports proves SameSite.” **False**: same site.
24. “JWT in a cookie has no CSRF.” **False**: the browser automatically sends cookies.
25. “No shared session store is needed because Kubernetes syncs memory automatically.” **False**.

## 21. Self-check questions

**1.** GET `/login` returns `Set-Cookie`, yet the browser does not retain it. What should you inspect?  
**Answer:** browser DevTools cookie rejection reason, Domain/Path/SameSite/Secure/trust, not just server logs.

**2.** The backend sees request scheme as HTTP behind HTTPS Nginx. Why?  
Check X-Forwarded-Proto/Host/Port, Boot forwarding strategy, and ingress trust; measure TLS at the browser **and** logical scheme in the app.

**3.** Why can't Java HttpClient confirm Chrome will omit a SameSite=Lax cookie on a cross-site POST?  
Because it lacks a browser site-for-cookies/navigation/privacy model.

**4.** Does testing `localhost:8443` and `localhost:9443` prove cross-site isolation?  
**No**; different origins by port, usually the same site.

**5.** `HttpOnly` leaves `document.cookie` empty. Could the user still be authenticated?  
**Yes**. The browser still attaches the cookie to HTTP requests; inspect network headers/principal.

**6.** A profile POST has the cookie and returns 403. Should you disable CSRF?  
**No**. Check the token/CSRF repository and flow, because blocking it may be expected.

**7.** Playwright runs when `ignoreHTTPSErrors=true`; can this be used to prove TLS is secure?  
**No**. You must fix CA trust/host SANs and run real validation.

**8.** A user logged into app A loses their session when the load balancer switches to B; how do you fix it?  
Use a shared session repository or appropriate sticky sessions, and test failover/logout/TTL without failing open.

### Operational checklist

- [ ] Browser public HTTPS has valid SAN/trust chain without bypassing validation.
- [ ] Backend is private, proxy overwrites trusted forwarding headers, and does not redirect to internal hosts.
- [ ] Session cookie has properly scoped Secure, HttpOnly, SameSite, Path, and Domain.
- [ ] Real browser receives/sends cookie and resolves the right principal on subsequent requests.
- [ ] Session ID rotates on login and invalidates on logout.
- [ ] POST login/logout/profile verify CSRF; GET logout does not perform logout.
- [ ] SameSite tested from a **genuinely different site**, not just a different port.
- [ ] All logs/traces redact Cookie/Set-Cookie/passwords/session tokens.
- [ ] Tests use a separate JVM/browser truststore when using a local CA.
- [ ] CI cleans up on failure and tests browser compatibility and session HA matching production.

## 22. References

- [Spring Boot 3.3 — Servlet Web Applications](https://docs.spring.io/spring-boot/3.3/reference/web/servlet.html): session cookie/SameSite properties.
- [Spring Boot 3.3 — Running Behind a Front-end Proxy Server](https://docs.spring.io/spring-boot/3.3/how-to/webserver.html): forward headers strategy and redirects.
- [Spring Security 6.5 — CSRF](https://docs.spring.io/spring-security/reference/6.5/servlet/exploits/csrf.html): CSRF token, login/logout, SPA token lifecycle.
- [Spring Security 6.5 — Session Management](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/session-management.html): session fixation and server sessions.
- [Spring Security 6.5 — Handling Logout](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/logout.html): GET confirmation, POST logout, invalidation.
- [Playwright — BrowserContext](https://playwright.dev/docs/api/class-browsercontext): cookie jar and request observation.
- [Playwright — Test options](https://playwright.dev/docs/test-use-options): TLS error handling.
- [MDN — Set-Cookie](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Set-Cookie): Secure/HttpOnly/SameSite/domain/localhost rules.
- [OWASP — Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html): cookie and session security.
- [OWASP WSTG — Exposed Session Variables](https://wstg.owasp.org/stable/4-Web_Application_Security_Testing/06-Session_Management_Testing/04-Testing_for_Exposed_Session_Variables/): session transport/headers.
- [mkcert — Local CA for development](https://github.com/FiloSottile/mkcert): SAN, trusted local certificates.
- [Docker Compose file reference](https://docs.docker.com/compose/compose-file/): network/port/service declarations.

**Conclusion:** Logging in properly in Java does not prove session security through a reverse proxy and browser. Testing must cover **TLS with CA/hostname verification**, **proper container networking/proxy forwarding**, **real browser cookie jar and network behavior**, along with CSRF/logout/session fixation. `MockMvc`, `curl`, JDK `HttpClient`, and Playwright are **complementary** measurements and do not replace one another.