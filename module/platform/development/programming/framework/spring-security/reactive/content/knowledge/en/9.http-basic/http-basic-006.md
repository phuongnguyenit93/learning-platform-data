# HTTPS Requirements and Risks of Credential Exposure via Logs, Proxies, or Tool History

## 1. The core problem when using HTTP Basic

In Spring Security reactive (Spring WebFlux), HTTP Basic authenticates using the username and password that the client sends in the `Authorization` HTTP header. It is a simple protocol supported by many HTTP clients, yet Basic itself **has no credential encryption mechanism**. The part after `Basic` is the Base64 of `username:password`; anyone who can read the header can decode it.

Therefore, using Basic responsibly requires simultaneously controlling:

1. **Transport:** start with HTTPS, verify certificates and hostnames; never send credentials over HTTP.
2. **TLS termination points:** proxies/gateways and the application can see the header after decryption; protect every hop involved.
3. **Logging/observability:** do not record passwords, Basic tokens, `Authorization` headers, or similar secrets in access logs, application logs, traces, and APM.
4. **Operational tooling:** do not put passwords in URLs, shell commands, browser history, API client collections, test files, or CI output.
5. **Credential lifecycle:** enforce least privilege, protect storage, rotate credentials, and handle exposure incidents.

HTTPS solves **transport channel security**, while controlling logs/proxies/tool history addresses **risks after credentials are decrypted or entered into tools**. Enabling HTTPS while still logging raw headers is not secure.

Goal: understand RFC 7617, configure HTTPS directly for Spring Boot WebFlux with PKCS12, practice `curl` with certificate verification, distinguish HTTPS redirects/HSTS/TLS termination, implement logging redaction, and test common leak paths. Examples target **Java 17+, Spring Boot 3.3.5, Spring Security 6.x**, using test accounts that hold no value outside localhost.

## 2. What does a Basic header actually contain?

Sample from RFC 7617:

```http
Authorization: Basic QWxhZGRpbjpvcGVuIHNlc2FtZQ==
```

This is a **public illustrative credential**, not a real password. This Base64 string decodes to:

```text
Aladdin:open sesame
```

Protocol flow:

```text
Client has username/password
         |
         v
Concatenate username + ":" + password
         |
         v
Base64-encode the byte string
         |
         v
Authorization: Basic <Base64-value>
         |
         v
Send HTTP request to server
         |
         v
Server decodes -> looks up user -> verifies password
```

Base64 only changes representation, **requiring no decryption key**. With HTTPS, the HTTP headers are encrypted **over the TLS connection**, rather than the Basic token itself becoming ciphertext. When HTTP Basic is sent over an unencrypted HTTP connection, an observer capturing packets can extract the username and password and replay them in other requests.

Common points of confusion:

- `WWW-Authenticate: Basic ...` is the challenge typically returned by the server with `401 Unauthorized`; the challenge does not encrypt login credentials.
- Clients typically resend `Authorization` on requests requiring authentication within the Basic scope; do not treat it as a one-time-use credential.
- `401` usually means missing valid authentication; `403` means the user is authenticated but lacks sufficient permissions (or hit another blocking policy such as CSRF).
- Username/password on the client side are **cleartext credentials before transmission**; the server typically stores only a password hash in `UserDetails` and uses `PasswordEncoder.matches(...)`. Hashing on the server **does not replace** the requirement for HTTPS in transit.
- Never log a "Basic token" on the excuse that it is Base64-encoded; that token is equivalent to a recoverable copy of the password.

### HTTP vs. HTTPS: fundamental distinction

```text
HTTP:
Client -- plaintext request including Authorization --> Server
         (intermediaries can read/modify)

HTTPS:
Client -- verified TLS session --> Server
         (HTTP data is protected over that connection)
```

HTTPS/TLS provides confidentiality, integrity, and server authentication **when the client properly validates certificates and hostnames**. If a client disables certificate verification, an attacker impersonating the server can decrypt the request at the spoofed endpoint even though the URL looks like HTTPS.

## 3. Which segments are encrypted? Threat model

### 3.1. Spring Boot terminating TLS itself

```text
Browser/curl -- HTTPS/TLS --> Spring Boot WebFlux/Netty
                             (TLS terminates at the application)
```

On this segment, devices merely observing network traffic cannot read HTTP headers if TLS is properly deployed. Once Netty decrypts the request, the application still has access to `Authorization` and other data to process authentication.

### 3.2. TLS termination at a reverse proxy

```text
Client -- TLS 1 --> Reverse proxy -- TLS 2 --> WebFlux
                     |                         |
               TLS decrypted             App decrypts
                     |
               Access log / WAF / tracing
```

This model has TLS on both hops. If the proxy receives HTTPS and forwards **HTTP** to the backend:

```text
Client -- TLS --> Proxy -- internal HTTP --> App
```

then `Authorization` travels in cleartext on the backend hop. You cannot by default call that end-to-end TLS. The system must inspect trust boundaries, packet-capture privileges, network segmentation, sidecars, policies, and compliance rules; for sensitive accounts, encrypting the backend hop or using an equivalently protected channel is usually preferred.

### 3.3. What does HTTPS NOT protect against?

TLS **does not inherently prevent**:
- Reverse proxies, gateways, WAFs, or load balancers reading headers after decryption.
- WebFlux applications, WebFilters, exception handlers, or HTTP libraries logging full headers.
- APM agents/exporters storing `Authorization` in span attributes or error reports.
- IDEs/API clients saving request history, collections, or environment exports.
- Shell history, terminal scrollback, process arguments, CI runners, or script output retaining typed passwords.
- Users putting credentials into query strings/paths/URL userinfo so they appear in logs or browser history.

Key point: the `Authorization` HTTP header **usually does not appear in normal browser URL history**; history exposure happens when you **put passwords in URLs**, command history, network traces/HAR files, or tool request histories.

### 3.4. Risk table by location

| Location | Behavior causing exposure | Mitigation |
| --- | --- | --- |
| Unencrypted HTTP | Basic header can be eavesdropped | HTTPS-first, trusted certificates, and matching hostnames |
| Client `curl -k` | Skips server verification | Use proper CA/certificate, never disable verification |
| TLS-terminating proxy | Logs raw `Authorization` | Allowlist logs, strip sensitive headers at the source |
| Proxy → backend hop | Cleartext HTTP in an unprotected zone | Enable TLS/mTLS or protect the hop per threat model |
| Spring WebFilter | `log.debug("headers={}", headers)` | Never log full requests/headers |
| APM/tracing | Span records contain tokens | Redact/drop attributes before export |
| Terminal/curl | `-u user:password` in command | `--user user` so curl prompts for password |
| Browser/API URL | `user:pass@host` or `?password=...` | Never put credentials in URLs |
| API client/collection | Exporting workspaces containing secrets | Private variables/secret stores and export reviews |
| CI/CD | `set -x`, echoed env, build artifacts | Mask secrets, disable xtrace, restrict access and retention |
| Log aggregator | App logs collected and broadly shared | Block at source, RBAC, rotation, and incident response |

## 4. HTTPS rules to remember

A proper HTTPS deployment has these layers:

1. **Valid and trusted server certificate.** The accessed domain name must appear in the certificate SAN; proper CA chain, validity period, and TLS configuration.
2. **Client verifies the certificate.** Never use trust-all clients, `--insecure`, or disabled hostname verification to hide errors.
3. **Use HTTPS from the very first request.** HTTP redirects arrive too late if the initial HTTP request already carried a Basic header.
4. **Protect every hop.** Identify which proxy terminates TLS, which metadata is trusted, and whether the backend hop is encrypted or equivalently protected.
5. **Protect secrets where used.** `Authorization` can leak after TLS termination if logs/traces are misconfigured.
6. **Add HSTS for browsers** where appropriate; HSTS does not replace HTTPS, certificate validation, or configuration for machine-to-machine API clients.
7. **Configure safe logging and retention.** Do not collect credentials and mask them only on a dashboard; prefer stripping them before logging/exporting.

Do not conflate features: BCrypt password hashing protects **passwords at rest**; HTTPS protects **HTTP in transit**; redaction protects **observability/logs**. One layer does not replace the other two.

## 5. Complete example: Spring Boot WebFlux serving HTTP Basic over TLS

The following demo project uses Spring Boot **3.3.5** with Gradle and Java 17+. Locally, the server listens on HTTPS port **8443** using a PKCS12 keystore. The sample user password and keystore password are read from runtime environment variables. All secrets in the example are **for learning only**; in production use a secret manager and properly managed certificates.

Structure:

```text
basic-https-demo/
├── settings.gradle
├── build.gradle
├── .gitignore
├── local-tls.p12                 # Generated locally, do not commit
├── localhost.crt                 # Public certificate for curl verification
└── src/
    ├── main/
    │   ├── java/dev/example/basichttps/
    │   │   ├── BasicHttpsApplication.java
    │   │   ├── SecurityConfig.java
    │   │   └── DemoController.java
    │   └── resources/application.properties
    └── test/java/dev/example/basichttps/
        └── BasicSecurityTests.java
```

The two TLS files only exist after generating the certificate with `keytool` in section 6. `local-tls.p12` contains the **private key**; do not share it or commit it to Git.

`settings.gradle`:

```groovy
rootProject.name = 'basic-https-demo'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'dev.example'
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
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Do not add `spring-boot-starter-web` to a pure WebFlux demo, because when both starters are present Spring Boot usually chooses Servlet/MVC.

`.gitignore`:

```gitignore
.gradle/
build/
local-tls.p12
*.key
.env
```

In real applications, also protect other secret files, custom truststores, local configs, and organization artifacts. A public certificate is not a secret, yet do not confuse `localhost.crt` with `local-tls.p12`, which holds the private key.

### 5.1. Startup class

`src/main/java/dev/example/basichttps/BasicHttpsApplication.java`:

```java
package dev.example.basichttps;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class BasicHttpsApplication {
    public static void main(String[] args) {
        SpringApplication.run(BasicHttpsApplication.class, args);
    }
}
```

### 5.2. HTTP Basic, sample user, and authorization

`src/main/java/dev/example/basichttps/SecurityConfig.java`:

```java
package dev.example.basichttps;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.MapReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableWebFluxSecurity
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    MapReactiveUserDetailsService users(
            PasswordEncoder encoder,
            @Value("${demo.user.password}") String demoPassword) {
        UserDetails reader = User.withUsername("reader")
                .password(encoder.encode(demoPassword))
                .roles("READER")
                .build();
        return new MapReactiveUserDetailsService(reader);
    }

    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        return http
                .authorizeExchange(exchanges -> exchanges
                        .pathMatchers("/public").permitAll()
                        .pathMatchers("/me").hasRole("READER")
                        .anyExchange().denyAll())
                .httpBasic(Customizer.withDefaults())
                .formLogin(form -> form.disable())
                .build();
    }
}
```

`MapReactiveUserDetailsService` holds `UserDetails` in memory. `PasswordEncoder` generates a BCrypt hash from the test password at startup; when Basic credentials arrive, Spring Security verifies the raw password against the hash. `SecurityWebFilterChain` specifies that `/public` is publicly accessible, `/me` requires the READER role, and all other URLs are denied.

**Note:** `SecurityWebFilterChain` **does not enable TLS by itself**. TLS is configured at the embedded server layer using `server.ssl.*`. Conversely, enabling TLS does not protect an endpoint if authorization rules are wrong.

### 5.3. WebFlux controller

`src/main/java/dev/example/basichttps/DemoController.java`:

```java
package dev.example.basichttps;

import java.security.Principal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class DemoController {

    @GetMapping("/public")
    public Mono<String> publicPage() {
        return Mono.just("public-ok");
    }

    @GetMapping("/me")
    public Mono<String> currentUser(Principal principal) {
        return Mono.just("user=" + principal.getName());
    }
}
```

The controller returns `Mono<String>`, without `block()` or `subscribe()`. Never return raw passwords, password hashes, `Authorization`, or `UserDetails` directly.

### 5.4. Keystore and runtime secrets configuration

`src/main/resources/application.properties`:

```properties
server.port=8443
server.ssl.enabled=true
server.ssl.key-store=file:./local-tls.p12
server.ssl.key-store-type=PKCS12
server.ssl.key-alias=localhost
server.ssl.key-store-password=${HTTPS_KEYSTORE_PASSWORD}

demo.user.password=${DEMO_PASSWORD}

logging.level.org.springframework.security=INFO
```

Explanation:
- `server.port=8443`: listens directly on HTTPS.
- `server.ssl.key-store=file:./local-tls.p12`: keystore file in the process working directory; run the demo from the project root.
- `server.ssl.key-store-type=PKCS12` and `key-alias=localhost` must match `keytool`.
- Both secrets are injected from the environment. Never write plaintext passwords into source control.
- Setting Spring Security logging to INFO avoids verbose debug output, but **does not guarantee** that logs at proxies, custom filters, or APMs are redacted.
- SSL configuration in Spring Boot **does not automatically open a parallel HTTP 8080 listener**. Only HTTPS port 8443 is open; `http://localhost:8443` is not a valid HTTP connector.

In production, use valid CA certificates/SSL bundles or TLS termination at the gateway; never bundle local private keys into public JARs.

## 6. Generating a local certificate and starting the demo

### 6.1. Generating PKCS12 with `keytool`

Using `keytool` from JDK 17+, in the `basic-https-demo` directory:

```bash
keytool -genkeypair \
  -alias localhost \
  -keyalg RSA -keysize 3072 \
  -validity 30 \
  -storetype PKCS12 \
  -keystore local-tls.p12 \
  -dname "CN=localhost, OU=Learning, O=Demo, L=Local, ST=Local, C=VN" \
  -ext "SAN=dns:localhost,ip:127.0.0.1"
```

Omit `-storepass ...` so `keytool` **prompts for the password interactively**. This avoids placing the value in command history/process arguments. Pick a dedicated test password for the local keystore. The certificate includes a SAN for localhost so clients can verify the hostname. A **self-signed** certificate is not trusted by public CAs by default, which is appropriate in a controlled test environment.

Export the public certificate to pass to curl:

```bash
keytool -exportcert \
  -rfc \
  -alias localhost \
  -storetype PKCS12 \
  -keystore local-tls.p12 \
  -file localhost.crt
```

`localhost.crt` is the public certificate; `local-tls.p12` holds the private key. Never send `local-tls.p12` in email/chat or commit it. On Windows PowerShell, `\` is not Bash's line-continuation syntax: put each `keytool` command on a single line or use PowerShell's line continuation.

### 6.2. Entering passwords without typing them in cleartext on the command line

With Bash:

```bash
read -r -s -p "Keystore password: " HTTPS_KEYSTORE_PASSWORD
printf '\n'
export HTTPS_KEYSTORE_PASSWORD

read -r -s -p "Demo reader password: " DEMO_PASSWORD
printf '\n'
export DEMO_PASSWORD

gradle bootRun
```

`read -s` suppresses echoing characters to the terminal and the values do not appear in the `gradle` command. However, secrets still reside in the process's **environment and memory**; this is only a local demo solution, not a secret vault.

On Windows PowerShell 5.1+ you can use:

```powershell
$secureStore = Read-Host "Keystore password" -AsSecureString
$secureDemo = Read-Host "Demo reader password" -AsSecureString

$env:HTTPS_KEYSTORE_PASSWORD =
    [System.Net.NetworkCredential]::new("local", $secureStore).Password
$env:DEMO_PASSWORD =
    [System.Net.NetworkCredential]::new("local", $secureDemo).Password

gradle bootRun
```

Creating `$env:...` turns secrets into strings in the environment, so restrict process read permissions and do not enable debug dumps. After finishing the demo, close the terminal or clear the corresponding environment variables. If the project includes Gradle Wrapper, use `./gradlew bootRun` (Bash) or `gradlew.bat bootRun` (PowerShell/Windows).

### 6.3. Testing HTTPS without disabling certificate verification

With the certificate exported to `localhost.crt`:

```bash
# Public endpoint: still runs over HTTPS and verifies the certificate.
curl --cacert localhost.crt -i https://localhost:8443/public

# Private endpoint without credentials.
curl --cacert localhost.crt -i https://localhost:8443/me

# Provide username only; curl prompts interactively for the password.
curl --cacert localhost.crt -i --user reader https://localhost:8443/me
```

`curl --user reader` (without `:password`) prompts for the password interactively per curl's docs. Enter the password used for `DEMO_PASSWORD`. On PowerShell, if `curl` is an alias for `Invoke-WebRequest`, use `curl.exe` to call the actual curl tool.

Expected results:

| Test | Expected result |
| --- | --- |
| `GET https://localhost:8443/public` | 200, body `public-ok` |
| `GET https://localhost:8443/me` without Basic | 401, typically with `WWW-Authenticate` |
| `GET /me` with reader/correct password | 200, body `user=reader` |
| `GET /me` with reader/wrong password | 401 |
| `https://localhost:8443` when client does not trust self-signed cert | Client rejects certificate validation |
| `http://localhost:8443` on TLS-only port | Fails to process normal HTTP request; handshake/protocol error |

Exact headers may vary by version, while the main statuses/bodies follow the table. These are **expected results from the code**, not a report of executing the program.

**Never use `curl -k`, `--insecure`, trust-all HTTP clients, or disabled hostname validation** to make a connection look successful. Those defeat TLS testing and can accept spoofed servers.

### 6.4. Observing HSTS over HTTPS

```bash
curl --cacert localhost.crt -i https://localhost:8443/public
```

In a typical Spring Security WebFlux configuration, the `Strict-Transport-Security` header is added to responses over HTTPS. Inspect actual responses rather than assuming every configuration behaves identically. HSTS requires a browser that has **trusted and cached** the HTTPS-only policy for the host for the specified duration; it does not encrypt requests, protect all non-browser HTTP clients, or rescue credentials previously sent over HTTP before the browser learned the policy.

## 7. HTTP redirects and HSTS do not replace HTTPS-first

Spring Security reactive supports:

```java
// Optional inside ServerHttpSecurity configuration:
http.redirectToHttps(Customizer.withDefaults());
```

This is an **API illustration snippet**, not a complete program. `redirectToHttps` only affects HTTP requests that **reach the security filters**. For instance, a direct TLS port 8443 has no HTTP listener; adding redirect to the chain **does not create** an 8080 or 80 listener. Behind a reverse proxy, the ingress/gateway typically redirects HTTP to HTTPS and forwards trusted scheme metadata to the backend.

Why isn't redirecting enough? If a client already sent:

```http
GET /private HTTP/1.1
Host: example.test
Authorization: Basic QWxhZGRpbjpvcGVuIHNlc2FtZQ==
```

over plaintext HTTP, the header can be intercepted **before** the server responds with a 301/302/307/308 redirect. Therefore:
- Clients must start with `https://` before sending Basic.
- Configure SDKs and documentation to use HTTPS endpoints; never send Basic to an HTTP URL "waiting for a redirect".
- HSTS reduces mistakes for browsers that learned the policy or are on a preload list, but does not replace the client HTTPS-first requirement.
- If an HTTP port exists, it should only serve redirects without requiring/accepting credentials for sensitive operations.
- Verify how clients handle cross-host redirects; never assume `Authorization` is always preserved or always stripped across all tools.

Do not enable HSTS `includeSubDomains` or preload unless all subdomains fully support HTTPS; an overly broad policy can break legitimate services.

## 8. Reverse proxies, Forwarded headers, and trust boundaries

### 8.1. TLS termination

A gateway terminating HTTPS and forwarding to WebFlux can read `Authorization` in memory and log requests. Verify simultaneously:
- Client → proxy TLS, with certificates verified by the client.
- Proxy → WebFlux: is it TLS, mTLS, or HTTP? If HTTP, which network can observe it and who has access?
- Log formats of ingress, gateway, WAF, service mesh, and load balancer.
- How APM/tracing is configured to capture headers/HTTP bodies.
- Whether the proxy forwards `Authorization` only to the intended backend scope; whether any filter/route forwards it unintentionally.
- Redirect policies, host allowlists, and proxy-generated request IDs.

### 8.2. `X-Forwarded-Proto` and `Forwarded`

When a proxy terminates TLS, the backend may see an HTTP connection. Headers like `Forwarded` or `X-Forwarded-Proto` convey the client-facing scheme so the app builds accurate redirects/URLs. Spring Boot provides an option:

```properties
# Apply only when a trusted proxy controls all incoming headers.
server.forward-headers-strategy=framework
```

Enable this only in architectures that guarantee **the proxy strips client-supplied headers and regenerates metadata itself**. If external internet clients can spoof `X-Forwarded-Proto: https` and the app trusts it unconditionally, HTTPS redirect logic or security diagnostics can break. Setting this property does not encrypt the proxy → backend hop and does not protect `Authorization` in logs.

If you encounter redirect loops, wrong-scheme absolute URLs, or unexpected HSTS behind a proxy, check TLS termination order, trusted proxy headers, and port mappings; never "fix" it by disabling TLS checks.

## 9. Never leak Basic credentials in application logs and APM

In WebFlux, headers can be logged by a `WebFilter`, exception handler, logging middleware, tracing agent, HTTP client logging, or DEBUG/TRACE settings.

**Wrong** example (anti-pattern illustration only; never put this in an app):

```java
// Wrong: logging all headers can include Authorization.
log.debug("headers: {}", exchange.getRequest().getHeaders());
```

`exchange` is a `ServerWebExchange`, and `log` is an assumed class logger. Never log raw `Authentication`, `Authorization`, `HttpHeaders`, raw requests, stack traces containing raw headers, or request dumps.

### Good practice: allowlist-based logging

Only record purposeful data evaluated as safe. Standalone code example inside a `WebFilter` with a declared logger:

```java
// Illustrative fragment; inside a class with WebFilter and Logger.
log.info("http request method={} routeTag={}",
        exchange.getRequest().getMethod(),
        "basic-demo");
```

`routeTag` is a server-defined constant, not a client-supplied query/path. You may also log response status, a normalized request ID, and elapsed time when operationally needed. Do not assume paths are safe if the app allows sensitive IDs or secrets inside URL paths.

### Fields to exclude from logs/traces

- `Authorization` and `Proxy-Authorization`, including case variations.
- `Cookie`/`Set-Cookie` carrying session or access tokens.
- Custom API key headers, bearer/refresh tokens, client secrets.
- Bodies/queries containing passwords, OTPs, recovery codes, or sensitive secret data.
- Headers/tracing tags that could carry the above after Base64/URL encoding.

The OWASP Logging Cheat Sheet recommends omitting, masking, or protecting authentication credentials, tokens, and sensitive personal data. **Redact where logs/traces are generated**, before export; masking in a dashboard after data has already reached a log collector can be too late.

### Controlling log storage

- Grant log/trace read access by role; separate production and development.
- Restrict retention, exports, backups, support-bundle sharing, and audit who accesses logs.
- Configure proxy/access logging independently from Spring Security logging.
- Log only `LOGIN_FAILURE`, `LOGIN_SUCCESS`, generic error codes, timestamps, route/trace IDs, and policy-minimized identifiers; never log passwords or Basic tokens.
- If usernames must be protected from enumeration, do not return responses to clients that distinguish wrong username from wrong password.

Setting `logging.level.org.springframework.security=INFO` only reduces verbose framework logging; it does not stop custom code, proxies, or other observability tools from recording headers.

## 10. Risks from CLI, browsers, and tool history

### 10.1. Arguments and shell history

Illustrative command **never to use with real secrets**:

```bash
# Anti-pattern: dummy password appears directly on the command line.
curl --user reader:example-password https://service.example.test/private
```

The password can end up in shell history, process arguments temporarily, terminal transcripts/screenshots, CI output, and support dumps. Some curl versions attempt to mask arguments in the process list, yet a window of exposure remains; do not treat that as a security guarantee.

Better approach for interactive work:

```bash
curl --cacert localhost.crt --user reader https://localhost:8443/me
```

When only a username is given, curl prompts for the password on the terminal, keeping it off the command line. Even so, the terminal/tool remains exposed if the host is compromised. Never enable `--verbose`, `--trace`, or `--trace-ascii` with real credentials since they can print request/header data to output.

### 10.2. URL userinfo and query parameters

Never send passwords in URLs:

```text
https://reader:example-password@service.example.test/me
https://service.example.test/login?user=reader&password=example-password
```

These are **dummy password** strings to help recognize the anti-pattern. URLs can appear in browser history, bookmarks, gateway access logs, `Referer` headers in certain contexts, analytics, or API client request histories. Never use query strings as a credential transport.

### 10.3. Postman/Insomnia/IDE

API clients can retain passwords in request configs, collections/workspaces, environment exports, cloud sync, histories, and debug panes. Use private/secret variables, separate local/test/production, and never export or share collections containing real passwords. For `.http` files in IDEs, never commit `Authorization` headers or real Basic tokens to Git.

### 10.4. CI/CD, secrets, and environment

- Never echo secrets or use `set -x` when scripts touch passwords/API keys.
- Never pass passwords as command-line arguments, Gradle `-D...password=...`, URLs, or strings printed to the console.
- If secrets are loaded from environment variables, restrict process/CI job read permissions and exclude them from test artifacts.
- Environment variables are not a vault: processes and privileged users can read them, so use a secret manager/secret mount for production.
- Protect command histories, trace outputs, log retention, and screenshot sharing permissions.

Cleaning shell history alone is not enough if Postman, CI, APM, or proxies already recorded the request headers. Inventory **every place where secrets can be captured or copied**.

## 11. Testing with WebTestClient: separating authentication from TLS

You can test Spring Security WebFlux using `WebTestClient`. However, HTTP/Mock tests **only verify authentication/authorization behavior**, not that production runs HTTPS or has valid certificates. TLS verification must use `curl --cacert` or a certificate-validating TLS client as in section 6.

`src/test/java/dev/example/basichttps/BasicSecurityTests.java`:

```java
package dev.example.basichttps;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT,
        properties = {
                "server.ssl.enabled=false",
                "server.ssl.key-store-password=unused-test-value",
                "demo.user.password=test-only-reader-password"
        }
)
@AutoConfigureWebTestClient
class BasicSecurityTests {

    @Autowired
    WebTestClient client;

    @Test
    void publicRouteIsAccessible() {
        client.get().uri("/public")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("public-ok");
    }

    @Test
    void privateRouteRequiresLogin() {
        client.get().uri("/me")
                .exchange()
                .expectStatus().isUnauthorized();
    }

    @Test
    void validBasicCredentialsWork() {
        client.get().uri("/me")
                .headers(h ->
                        h.setBasicAuth("reader", "test-only-reader-password"))
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("user=reader");
    }

    @Test
    void wrongPasswordIsRejected() {
        client.get().uri("/me")
                .headers(h -> h.setBasicAuth("reader", "wrong-password"))
                .exchange()
                .expectStatus().isUnauthorized();
    }

    @Test
    void unknownRouteIsDenied() {
        client.get().uri("/unknown")
                .headers(h ->
                        h.setBasicAuth("reader", "test-only-reader-password"))
                .exchange()
                .expectStatus().isForbidden();
    }
}
```

Run:

```bash
gradle test
```

**Expected:** five tests pass if the code and dependencies match the sample. This is the expected outcome from security logic, **not a claim that Gradle was executed**. The password strings in tests are dummy values only, not production credentials.

Specifically, `server.ssl.enabled=false` is **a setting solely for testing authentication on a random HTTP port**, not a deployment configuration. When testing TLS, run the main app with SSL enabled and use an HTTPS client. Never treat a 200 status from an HTTP test as proof that real-world credentials are encrypted.

## 12. End-to-end protection verification checklist

| Test | Expected | Scope |
| --- | --- | --- |
| HTTPS with valid certificate | Client verifies and connects | TLS, hostname/CA |
| HTTPS with untrusted certificate | Client rejects | Server identity verification |
| HTTP to TLS-only port | Fails to process normal Basic request | No accidental HTTP connector |
| `GET /me` without credentials | 401 | HTTP Basic |
| `GET /me` with valid credentials | 200, returns only needed identity | Authentication |
| `GET /me` with wrong credentials | 401 | Authentication failure |
| Spring app logs | Contains no password or Authorization | Log redaction |
| Proxy/gateway/WAF logs | Captures no raw secrets | Gateway configuration |
| APM/tracing spans | No Basic token in attributes | Observability |
| CLI history/process arguments | No raw password | Client tooling |
| HSTS on HTTPS response | Matches configured policy | Browser HTTPS preference |
| Proxy → backend | TLS or network protected per policy | Trust boundaries |
| Forwarded headers | Trusts only proxy-controlled values | Redirects, scheme recognition |

**Test logging with disposable dummy values:** create dedicated test credentials, send requests through the paths under test, confirm the app/proxy/APM do not record tokens, then revoke the test credentials. Never put production passwords into tests to "check if they leak".

If responses include HSTS, verify scope and emission conditions over real HTTPS. Never enable `includeSubDomains` or preload for domains without full HTTPS coverage. HSTS only affects supporting browsers that received/trusted the policy; it does not protect machine-to-machine tools.

### HTTP Basic and CSRF

Some browsers can resend cached Basic credentials within an authentication scope, so **do not disable CSRF by default just because Basic or an API is used**. Spring Security has default CSRF protection suitable for state-changing methods; evaluate the client/browser model and CSRF risks before adjusting it. CSRF and CORS do not encrypt the `Authorization` header and do not replace TLS.

## 13. Responding when a Basic credential has leaked

If an `Authorization` header, Base64 Basic token, or raw password appears in logs, traces, CI artifacts, Git, issues, or history:

1. **Stop recurrence:** fix/disable whatever captures sensitive headers, and temporarily restrict the offending routes or tools.
2. **Revoke/rotate credentials:** Basic carries replayable passwords; treat exposed credentials as untrusted and handle related sessions/tokens per design.
3. **Inventory copies:** app logs, proxies, log shippers, APM, backups, CI history, terminals, API clients, support tickets, screenshots, Git history.
4. **Assess impact:** exposure window, credential privileges, who had log access, and signs of unauthorized use.
5. **Handle logs/artifacts per procedure:** redact/delete authorized copies, preserve required evidence per incident response policy, and never indiscriminately wipe audit trails.
6. **Re-test with fresh dummy credentials:** verify the collection points are fixed before returning to production.
7. **Improve processes:** HTTPS-first, no-secrets-in-URL/CLI, redaction, log RBAC, secret managers, and team training.

Deleting a password from the latest commit **does not revoke** copies in Git history, forks, caches, or artifacts. Rotating the secret and locking down all new storage locations is the primary action.

## 14. Common mistakes

| Mistake | Consequence | How to fix? |
| --- | --- | --- |
| Thinking Basic's Base64 is encrypted | Anyone seeing the header decodes the password | HTTPS + never log headers |
| TLS only at the gateway | Hop to app may still be plaintext HTTP | Protect each hop per threat model |
| Using `curl -k` for self-signed certs | Skips server identity verification | `--cacert` or valid CA |
| Sending Basic over HTTP relying on redirect | Header may already leak before 3xx | Call HTTPS from the start |
| Enabling `redirectToHttps` without an HTTP listener | Nothing listens on HTTP to redirect | Configure listener/gateway separately |
| Configuring SSL and assuming port 8080 HTTP exists | Misunderstanding that Spring Boot only opens the HTTPS port | Verify ports and topology |
| Logging `getHeaders()` at DEBUG | Leaks Authorization into app logs | Selectively pick safe fields before logging |
| Masking passwords only on the APM dashboard | Raw header already exported to collector | Drop/redact at source |
| Typing `curl -u user:password` | Password in history/process list | Pass username only, enter password at prompt |
| Putting passwords in URLs/queries | Leaks via history, access logs, analytics | Never put secrets in URLs |
| Trusting any `X-Forwarded-Proto` | Clients can spoof HTTPS scheme | Trust only proxy-controlled headers |
| Testing 200 auth and concluding TLS works | Authorization differs from transport security | Test certificates and TLS separately |
| Trusting HSTS to protect every client's first request | HSTS depends on browsers and prior policy caching | HTTPS-first, certificate validation |
| Disabling CSRF because Basic is used | Browsers can auto-send credentials | Evaluate CSRF per client/threat model |
| Only deleting secrets from current code | Git/history/log backups may still hold them | Rotate secrets and manage copies |

## 15. Review questions

**Question 1.** Does `Authorization: Basic ...` encrypt the password?  
**Answer:** No. It is Base64 encoding, which can be decoded directly.

**Question 2.** Does HTTPS protect Basic credentials from application logs or a TLS-terminating proxy?  
**Answer:** No. Headers are in cleartext after TLS termination and can be captured by loggers/agents.

**Question 3.** Why does `curl --user reader` leak less in shell history than `curl --user reader:password`?  
**Answer:** It prompts interactively for the password and omits the secret from the command; you still must protect the tool and endpoint.

**Question 4.** Should you use `--insecure` to test a self-signed certificate?  
**Answer:** No, if you want to genuinely test TLS. Use `--cacert` with the trusted demo certificate.

**Question 5.** If a proxy terminates TLS and uses HTTP to the backend, is the request encrypted end-to-end?  
**Answer:** No. The proxy → backend hop is plaintext HTTP and must be secured per policy.

**Question 6.** Does an HTTP redirect rescue a Basic request sent earlier over HTTP?  
**Answer:** No; credentials may already have traversed HTTP on the first request.

**Question 7.** Does `server.ssl.enabled=true` automatically create an HTTP port 8080 for redirects?  
**Answer:** No; the example listens only on HTTPS 8443.

**Question 8.** Does the HSTS header replace certificate validation?  
**Answer:** No. HSTS helps browsers prefer HTTPS after learning an eligible policy; it does not verify server identity itself.

**Question 9.** Besides `Authorization`, what other data should be filtered out of logs?  
**Answer:** `Proxy-Authorization`, session cookies, API keys, bearer/refresh tokens, raw passwords, OTPs, and secrets in bodies/queries.

**Question 10.** Why isn't lowering Spring Security logging to INFO enough on its own?  
**Answer:** Custom filters, proxies, ingress, APM, CI, and client histories each have their own logging systems.

**Question 11.** With BCrypt password hashes in `UserDetails`, is TLS still needed?  
**Answer:** Yes, because the client sends raw Basic credentials before Spring Security checks the hash.

**Question 12.** What should be done first if a Basic credential is discovered in a CI artifact?  
**Answer:** Stop recurrence, revoke/rotate the credential, locate copies, and follow incident response procedures.

### Exercises

1. Generate a localhost certificate with `keytool`, start the demo on 8443, and use `curl --cacert` to test `/public` and `/me`. Record only non-sensitive statuses/bodies.
2. Test with a different certificate: explain why certificate verification fails. Do not use `-k` to bypass the error.
3. Log in with Basic via curl providing only the username; verify the test command history contains no password.
4. Create a *dummy* canary password string and inspect logging/tracing in a test environment; confirm the header is never recorded.
5. Draw the client → proxy → app diagram, marking TLS segments and where redaction is needed.
6. Verify browser/HSTS and proxy-forwarded schemes in a trusted test environment; explain why client-supplied `X-Forwarded-Proto` must not be trusted.
7. Add tests for wrong passwords and unauthenticated requests, while still testing TLS independently.
8. Design a response checklist if a token appears in Git history or CI logs: rotation, scope, log copies, and evidence.

## 16. Authoritative documentation

- [RFC 7617 — The 'Basic' HTTP Authentication Scheme](https://www.rfc-editor.org/rfc/rfc7617): Base64 credentials and secure channel requirements.
- [Spring Security — HTTP in WebFlux](https://docs.spring.io/spring-security/reference/reactive/exploits/http.html): HTTPS redirect, HSTS, and proxies.
- [Spring Security — WebFlux Security](https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html): HTTP Basic, `ServerHttpSecurity`, and WebFilters.
- [Spring Boot 3.3 — SSL](https://docs.spring.io/spring-boot/3.3/reference/features/ssl.html): keystore and server TLS configuration.
- [Spring Boot 3.3 — Application Properties](https://docs.spring.io/spring-boot/3.3/appendix/application-properties/): `server.ssl.*`, logging, and proxy properties.
- [OWASP — Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html): data that must not be logged.
- [OWASP — Transport Layer Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Transport_Layer_Security_Cheat_Sheet.html): HTTPS/TLS deployment requirements.
- [curl man page](https://curl.se/docs/manpage.html): `--user`, `--cacert`, and tracing flags.

**Remember:** HTTP Basic only **Base64-encodes** username/password. To protect it, you must **use HTTPS/TLS with verified certificates from the very first request**, control **every hop through proxies**, **never log Authorization or tokens**, and **never place passwords in URLs/command lines/history**. Redaction, TLS, secret management, and log access controls together provide real protection.