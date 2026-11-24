# Choosing Where to Pass an API Key and Keeping Secrets Out of URLs

## 1. Goal and context

A Spring Boot application exposes `GET /api/report` for partner services. To identify callers, the API requires an **API key**: a secret value issued individually to a client/integration and checked on every request. Anyone holding the key typically gains the ability to call the API within the key's permission scope, so where the key is transmitted directly affects the risk of credential exposure.

Two requests with the same business intent but different ways of carrying the secret:

~~~http
GET /api/report?api_key=lab-demo-secret HTTP/1.1
Host: api.example.org
~~~

~~~http
GET /api/report HTTP/1.1
Host: api.example.org
X-API-Key: lab-demo-secret
~~~

**Design rule:** for API keys dedicated to machine-to-machine communication, prefer an **HTTP header over HTTPS**. Never accept secrets in the URL query, URL path, fragment, or URL userinfo. Avoid accepting multiple credential locations simultaneously, which can cause infrastructure components to interpret the request differently.

After this lesson you can:
- Explain the risks of leaking API keys via URLs, logs, browser history, proxies, and analytics, even when HTTPS is used.
- Choose between the `Authorization` header, `X-API-Key` header, request body, cookie, and query string according to the proper contract.
- Configure Spring Security Servlet to authenticate API keys solely from a header without persisting authentication sessions across requests.
- Thoroughly test cases for valid key, wrong key, missing key, key in URL, duplicate headers, and public endpoints.
- Operate keys with identifiers, least privilege, logging redaction, expiration, rotation, and revocation capabilities.

**Scope:** Spring Security 6.x, Spring Boot 3.x, Java 17+, Servlet/Spring MVC applications. WebFlux uses `SecurityWebFilterChain` and reactive context; the Servlet filter below does not apply verbatim.

## 2. An API key authenticates a client, not all authorization rules

An API key is usually tied to an application or integration service:

~~~text
Client ID: billing-exporter
Key ID: key_prod_7c12         # ID usable for lookup and audit
Secret: [long random value, displayed only when issued]
Environment: production
Scopes: invoices:read
Status: active
Expires: per policy
~~~

**Distinction:** the key ID is an identifier; the secret is the credential to keep confidential. A valid key helps the server identify which **client** was issued the key, but does not by itself authenticate an end user or grant permission to view arbitrary invoices. The API must still check scope, tenant, ownership, rate limits, and permissions on each endpoint.

For highly sensitive endpoints, an API key alone may not suffice. OAuth 2.0 client credentials, short-lived access tokens, mTLS, IP/network controls, and separate authorization policies may be needed. Do not treat rate limiting as a substitute for authorization.

## 3. Comparing HTTP locations for carrying a key

| Location | Example | Assessment | Key considerations |
| --- | --- | --- | --- |
| Dedicated header | `X-API-Key: <secret>` | **Preferred** for self-issued API keys with a clear contract | Needs explicit redaction because logging systems may not mask custom headers |
| `Authorization` header | `Authorization: Bearer <token>` | **Preferred for OAuth2 bearer access tokens** | The Bearer scheme does not mean every API key is an OAuth access token |
| Custom `Authorization` scheme | `Authorization: ApiKey <secret>` | Usable when the API defines its own scheme | Must align with SDKs/proxies; Spring does not authenticate it by default |
| Request body | `{"apiKey":"..."}` in POST | Possible in special protocols, **not default** | GET has no standard request body for keys; bodies can still be logged |
| Cookie | `Cookie: session=...` | Used for different browser session designs | Browsers send cookies automatically; requires `Secure`, `HttpOnly`, `SameSite`, CSRF |
| Query string | `?api_key=<secret>` | **Do not use** | URLs can enter logs, history, analytics, caches, and shared links |
| Path | `/api/keys/<secret>/report` | **Do not use** | The secret remains in the URL, exposed in logs and route telemetry |
| URL userinfo | `https://key:secret@host/path` | **Do not use** | URLs are easily shared, logged, and misparsed |
| Fragment | `https://host/path#secret` | **Do not use** | Fragments are normally not sent to the server in HTTP requests; unsuitable for API auth |

`X-API-Key` is a conventional header name, **not a single mandatory standard**. A system may define another name, but it must be consistent across client, gateway, backend, and OpenAPI. Header names are case-insensitive; **the secret value must match exactly**.

### 3.1. When to use `Authorization: Bearer`?

RFC 6750 specifies sending an **OAuth 2.0 bearer access token** in the `Authorization` header. Tokens can be JWTs or opaque; the resource server must validate them according to the proper issuer, expiry, audience, scope, and trust contract. Do not take a custom API key string, pass it into Spring Security's JWT Resource Server, and assume it will be accepted automatically.

If a product documents `Authorization: ApiKey <secret>`, that is the product's custom contract. A corresponding parser/authentication and redaction must be implemented.

### 3.2. OpenAPI example declaring a header key

~~~yaml
openapi: 3.0.3
info:
  title: Reporting API
  version: 1.0.0
components:
  securitySchemes:
    ReportingKey:
      type: apiKey
      in: header
      name: X-API-Key
security:
  - ReportingKey: []
paths: {}
~~~

OpenAPI configuration tells clients how to pass credentials. **It does not create an authentication filter automatically** and does not store keys for the server. For standard bearer tokens, define the security scheme appropriately with `type: http`, `scheme: bearer` or OAuth flows, without mixing the two styles.

## 4. Why doesn't HTTPS save a secret placed in a URL?

HTTPS protects the request **in transit up to the TLS termination point**; the proxy/gateway/server receiving the request still needs to read the request URI. When a client uses:

~~~text
https://api.example.org/api/report?api_key=lab-demo-secret&month=11
~~~

the query value can end up in:

1. **Web server access logs:** Nginx/Apache commonly log the request URI; some log formats include the query string.
2. **CDN/API gateway/load balancer:** access logs, WAF events, and debug traces can record the URL.
3. **Application/APM:** framework request logging, exception logs, trace attributes such as `url.full` or request URL.
4. **Browsers:** history, bookmarks, shared links, screenshots, devtools, or automatic crash reporters.
5. **Caches and analytics:** URLs may serve as cache keys or be sent to analytics/monitoring.
6. **Referer:** depending on `Referrer-Policy` and navigation behavior, part of the URL can appear at another recipient. Do not put secrets in URLs and rely on referrer policies for protection.

Even if the application does not actively log it, **an intermediary can still record the URL**. Do not try to fix this by URL-encoding, Base64-encoding, renaming the query param, or stripping the key after a redirect: the credential is still in the URL before arriving.

These patterns are all unsuitable:

~~~text
/api/report?api_key=secret
/api/report?token=secret
/api/report?access_token=secret
/api/credentials/secret/report
https://secret@api.example.org/api/report
~~~

RFC 6750 describes passing OAuth bearer tokens via query parameters for historical compatibility, but warns about how easily they get logged and **discourages its use**. An API key is not by default an OAuth token, yet the URL leakage risk is similar.

### 4.1. What is allowed in a URL?

URLs should contain routing and business parameters:

~~~text
GET https://api.example.org/api/report?month=11&format=csv
GET https://api.example.org/api/customers/42
~~~

Do not put passwords, API keys, bearer access tokens, refresh tokens, HMAC secrets, or reusable authentication data into query/path. If a URL contains sensitive personal data, evaluate it separately under privacy/logging policies.

## 5. Headers are better than URLs, yet still need leak prevention

Recommended request:

~~~http
GET /api/report?month=11 HTTP/1.1
Host: api.example.org
Accept: text/plain
X-API-Key: <demo-key-value>
~~~

The key is sent in a header and connections must use HTTPS in real environments. However, the system can still leak headers if full requests are logged, verbose curl is enabled, HTTP client debugging is turned on, or headers are forwarded to another host.

Apply simultaneously:
- **Proper TLS on every trusted hop**: client → gateway, gateway → backend if traffic crosses networks requiring protection; verify certificates and hostnames.
- **Mask sensitive headers**: `X-API-Key`, `Authorization`, `Cookie` in proxies, application logging, collectors, tracing, error reporting, and support tooling.
- **Prevent unintended forwarding**: avoid sending keys to other upstreams via HTTP redirects or misconfigured proxies.
- **Keep keys out of public clients**: keys inside a SPA JavaScript bundle or mobile app can be extracted; headers cannot keep a secret distributed to every user confidential.
- **Do not treat keys as absolute authority**: enforce client/tenant/scope and object-level authorization in the API.

A web frontend with end users should use a BFF holding secrets server-side, or OAuth2/OIDC for user-delegated access; never bundle a shared API key into a public SPA.

## 6. Complete Spring Boot 3.3.x + Spring Security Servlet example

The example uses **Java 17+**, Spring Boot 3.3.12, a demo API key passed via `X-API-Key`, and two endpoints:
- `GET /health`: public.
- `GET /api/report`: requires the `API_READ` authority, granted only after verifying the correct API key **in the header**.

The goal is to test *where credentials are extracted*, not to build a production key issuance system. The code below supports one dummy key for a single service account; production requires a key ID/hash store, expiry, revocation, tenancy, and rotation.

### 6.1. Project structure

~~~text
api-key-header-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/
    │   ├── java/demo/apikey/
    │   │   ├── ApiKeyApplication.java
    │   │   ├── ApiKeyFilter.java
    │   │   └── SecurityConfig.java
    │   └── resources/application.yml
    └── test/java/demo/apikey/ApiKeySecurityTest.java
~~~

`settings.gradle`:

~~~groovy
rootProject.name = 'api-key-header-demo'
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
app:
  api-key: ${LAB_API_KEY}
~~~

`LAB_API_KEY` is provided from the environment. Never commit real secrets into repositories, YAML files, or container images.

### 6.2. Application and endpoints

`src/main/java/demo/apikey/ApiKeyApplication.java`:

~~~java
package demo.apikey;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@RestController
public class ApiKeyApplication {
    public static void main(String[] args) {
        SpringApplication.run(ApiKeyApplication.class, args);
    }

    @GetMapping(value = "/health", produces = MediaType.TEXT_PLAIN_VALUE)
    public String health() {
        return "OK";
    }

    @GetMapping(value = "/api/report", produces = MediaType.TEXT_PLAIN_VALUE)
    public String report() {
        return "report: READY";
    }
}
~~~

### 6.3. Filter accepting credentials only from the header

`src/main/java/demo/apikey/ApiKeyFilter.java`:

~~~java
package demo.apikey;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.Collections;
import java.util.List;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.web.filter.OncePerRequestFilter;

public final class ApiKeyFilter extends OncePerRequestFilter {
    private static final String HEADER = "X-API-Key";
    private final byte[] expectedDigest;

    public ApiKeyFilter(String configuredKey) {
        if (configuredKey == null || configuredKey.isBlank()) {
            throw new IllegalArgumentException("API key must be configured");
        }
        this.expectedDigest = sha256(configuredKey);
    }

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain) throws ServletException, IOException {

        if (!request.getServletPath().startsWith("/api/")) {
            chain.doFilter(request, response);
            return;
        }

        var keys = Collections.list(request.getHeaders(HEADER));

        if (keys.isEmpty()) {
            // Do not read the key from request.getParameter("api_key").
            chain.doFilter(request, response);
            return;
        }

        if (keys.size() != 1 || keys.get(0).isBlank()
                || keys.get(0).length() > 512) {
            response.sendError(HttpServletResponse.SC_UNAUTHORIZED);
            return;
        }

        if (!MessageDigest.isEqual(
                expectedDigest, sha256(keys.get(0)))) {
            response.sendError(HttpServletResponse.SC_UNAUTHORIZED);
            return;
        }

        var auth = new UsernamePasswordAuthenticationToken(
                "reporting-client",
                null,
                List.of(new SimpleGrantedAuthority("API_READ")));

        SecurityContext context = SecurityContextHolder.createEmptyContext();
        context.setAuthentication(auth);
        SecurityContextHolder.setContext(context);

        try {
            chain.doFilter(request, response);
        } finally {
            SecurityContextHolder.clearContext();
        }
    }

    private static byte[] sha256(String value) {
        try {
            return MessageDigest.getInstance("SHA-256")
                    .digest(value.getBytes(StandardCharsets.UTF_8));
        } catch (NoSuchAlgorithmException impossibleOnJava17) {
            throw new IllegalStateException(impossibleOnJava17);
        }
    }
}
~~~

**Explanation:**
1. The filter only calls `getHeaders("X-API-Key")`; it does not call `getParameter("api_key")` or parse query/path/body to locate a key.
2. Missing header → the request remains unauthenticated; `/api/report` will be rejected by the authorization layer.
3. Invalid/duplicate header → rejects with 401, preventing proxies and backends from interpreting multiple headers differently.
4. For a matching key, the filter creates an `Authentication` for the simulated service account `reporting-client` with authority `API_READ`. Key info is not used to fabricate an end-user identity.
5. The demo hashes the key and compares bytes via `MessageDigest.isEqual` to avoid unsafe prefix comparisons. This is not a complete solution for storage, timing, or brute force; keys must be randomly generated and lifecycle-managed.
6. The context is cleared after the request. This is Servlet code using `SecurityContextHolder`, not WebFlux's Reactor Context.
7. The filter **has no `@Component`** because the configuration below adds it once to the Spring Security chain; this avoids accidentally registering it via Spring Boot as a second servlet filter.

### 6.4. SecurityFilterChain

`src/main/java/demo/apikey/SecurityConfig.java`:

~~~java
package demo.apikey;

import jakarta.servlet.http.HttpServletResponse;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.logout.LogoutFilter;

@Configuration
public class SecurityConfig {
    @Bean
    SecurityFilterChain security(
            HttpSecurity http,
            @Value("${app.api-key}") String configuredKey) throws Exception {
        return http
                .csrf(AbstractHttpConfigurer::disable)
                .sessionManagement(session -> session
                        .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
                .requestCache(cache -> cache.disable())
                .formLogin(AbstractHttpConfigurer::disable)
                .httpBasic(AbstractHttpConfigurer::disable)
                .exceptionHandling(exceptions -> exceptions
                        .authenticationEntryPoint((request, response, error) ->
                                response.sendError(
                                        HttpServletResponse.SC_UNAUTHORIZED)))
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/health").permitAll()
                        .requestMatchers("/api/**").hasAuthority("API_READ")
                        .anyRequest().denyAll())
                .addFilterAfter(new ApiKeyFilter(configuredKey),
                        LogoutFilter.class)
                .build();
    }
}
~~~

The custom authentication filter is placed after `LogoutFilter` and before authorization. `STATELESS` avoids using a session for the SecurityContext; every request must send the key. `formLogin` and `httpBasic` are disabled so the demo has a single login mechanism.

**CSRF is disabled only in a machine-to-machine model that does not use browser session cookies as credentials**. If integrating browser cookies or sessions, CSRF must be analyzed and configured accordingly; do not copy this snippet blindly into every application. Real systems normally add key ID lookups, status and scope checks, and tenant binding; a valid key is not automatically enough permission.

Spring Security does not understand `X-API-Key` just by adding the starter. A filter/AuthenticationProvider or gateway must enforce authentication per the contract.

## 7. Running and observing

Set a **dummy** key for the local demo:

~~~bash
# Linux/macOS
export LAB_API_KEY='lab-demo-only-1234567890'
./gradlew bootRun
~~~

On Windows PowerShell:

~~~powershell
$env:LAB_API_KEY = 'lab-demo-only-1234567890'
.\gradlew.bat bootRun
~~~

Use the created project's Gradle Wrapper; if no wrapper exists, install a compatible Gradle version and run `gradle bootRun`. In production, never put real secrets in shell history, process arguments, transcripts, screenshots, or uncontrolled config files; use a secret manager/secret injection.

From another terminal, call:

~~~bash
# Public, no header required:
curl -i http://localhost:8080/health

# Valid API key, in header:
curl -i -H 'X-API-Key: lab-demo-only-1234567890' \
  http://localhost:8080/api/report

# Missing header:
curl -i http://localhost:8080/api/report

# Wrong header:
curl -i -H 'X-API-Key: wrong-demo-key' \
  http://localhost:8080/api/report

# To prove the API does not read the URL key. Only use a dummy value on localhost:
curl -i 'http://localhost:8080/api/report?api_key=lab-demo-only-1234567890'
~~~

Expected results:

| Request | HTTP status | Body/meaning |
| --- | --- | --- |
| `GET /health` | 200 | `OK` |
| `GET /api/report` with valid header | 200 | `report: READY` |
| `GET /api/report` missing header | 401 | Unauthenticated |
| `GET /api/report` with wrong header | 401 | Unauthenticated |
| `GET /api/report?api_key=...`, no header | 401 | **URL has no authentication effect** |

In production **HTTPS must be used**. The `http://localhost:8080` URL is only for local testing with a demo key. Never use `curl -v` or dump requests containing real keys because terminals/logs may display sensitive headers.

## 8. Automated testing with MockMvc

`src/test/java/demo/apikey/ApiKeySecurityTest.java`:

~~~java
package demo.apikey;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest(properties = "app.api-key=lab-demo-only-1234567890")
@AutoConfigureMockMvc
class ApiKeySecurityTest {
    @Autowired
    MockMvc mvc;

    @Test
    void acceptsHeaderCredential() throws Exception {
        mvc.perform(get("/api/report")
                        .header("X-API-Key", "lab-demo-only-1234567890"))
                .andExpect(status().isOk())
                .andExpect(content().string("report: READY"));
    }

    @Test
    void rejectsMissingHeader() throws Exception {
        mvc.perform(get("/api/report"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void rejectsWrongKey() throws Exception {
        mvc.perform(get("/api/report")
                        .header("X-API-Key", "wrong-demo"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void urlParameterIsNotAuthentication() throws Exception {
        mvc.perform(get("/api/report")
                        .queryParam("api_key", "lab-demo-only-1234567890"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void rejectsDuplicateHeader() throws Exception {
        mvc.perform(get("/api/report")
                        .header("X-API-Key",
                                "lab-demo-only-1234567890",
                                "lab-demo-only-1234567890"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void healthIsPublic() throws Exception {
        mvc.perform(get("/health"))
                .andExpect(status().isOk())
                .andExpect(content().string("OK"));
    }
}
~~~

Run:

~~~bash
./gradlew test
# Windows: gradlew.bat test
~~~

Expect **6 passing tests**. Do not assert exact Gradle stdout text because log output varies by version/console/cache. The tests use a dummy key and `MockMvc` to exercise the Servlet security filter chain; no real network API is needed. Conclusions about **proxy/TLS/redaction** must still be verified in an integration environment with the corresponding gateway.

**Extension:** test a key with `READ` permission but lacking `WRITE`, wrong tenant, revoked key, multiple concurrent keys, expiry, rate limits, and redirects/header forwarding. Do not just test "valid key returns HTTP 200" and conclude the entire system is secure.

## 9. Java 17+ client sending header, keeping URL clean

File `ApiKeyClient.java` runs standalone with JDK 17 while the demo backend is running:

~~~java
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;

public class ApiKeyClient {
    public static void main(String[] args) throws Exception {
        String key = System.getenv("LAB_API_KEY");
        if (key == null || key.isBlank()) {
            throw new IllegalStateException("LAB_API_KEY is required");
        }

        HttpClient http = HttpClient.newHttpClient();
        HttpRequest request = HttpRequest.newBuilder()
                .uri(URI.create("http://localhost:8080/api/report?month=11"))
                .header("X-API-Key", key)
                .GET()
                .build();

        HttpResponse<String> response = http.send(
                request, HttpResponse.BodyHandlers.ofString());

        System.out.println("HTTP " + response.statusCode());
        System.out.println(response.body());
    }
}
~~~

Run:

~~~bash
javac ApiKeyClient.java
java ApiKeyClient
~~~

When the demo key is valid and the backend is running, stdout:

~~~text
HTTP 200
report: READY
~~~

In Java 17, `HttpClient` does not support `try-with-resources` as an `AutoCloseable`; the example above intentionally creates a normal client so it compiles cleanly. For production, replace `http://localhost` with HTTPS, add timeouts, handle redirects carefully, and never forward the key to unintended hosts.

## 10. Logs, proxies, and observability: multi-hop protection

Typical flow:

~~~text
Client service
    |
    | HTTPS, X-API-Key
    v
CDN / WAF / API Gateway / TLS Terminator
    |
    | Controlled header forwarding
    | Internal TLS if a trust boundary exists
    v
Spring Security Filter
    |
    | API_READ + business authorization
    v
Report API
~~~

Several practical controls:
1. **Edge access log:** do not log the full `X-API-Key` or `Authorization`; use field allowlists and redaction before emitting logs.
2. **App logging:** do not print `request.getHeader("X-API-Key")`, full request dumps, stack traces containing secrets, or error responses exposing key values.
3. **Distributed tracing:** inspect request URL, query, and header fields in SDKs/collectors/exporters; never store raw credentials in traces/spans.
4. **CI and test reports:** use dummy keys; never print secrets via `curl -v`, test snapshots, debug logs, chats, screenshots, or support tickets.
5. **Gateway → backend:** determine where authentication runs. If the gateway adds an "authenticated client" header, the backend may trust it only when direct access is blocked and externally supplied headers of that name are stripped.
6. **Redirects:** never automatically send keys to another host and never place keys in a `Location` response header.
7. **Consistent contract:** the gateway and app must agree to accept **headers only**; do not let the gateway accept query params while the backend dropped them.
8. **Caching:** avoid caching private responses with wrong authorization or using URLs containing credentials as cache keys. For sensitive APIs, configure `Cache-Control` appropriately.

**HTTPS is mandatory but insufficient:** even headers can appear in APM or request dumps if misconfigured. Therefore, "keeping keys out of URLs" and "preventing header logging" are two complementary requirements.

## 11. API key lifecycle: generate, store, scope, revoke

A key should have:
- A separate **Key ID** for lookup/audit, not a secret.
- A **strong random secret** generated with a CSPRNG; e.g., ~256 bits of random data, delivered over a secure provisioning channel.
- A **stored verification record**: never store plaintext keys in logs/databases. For sufficiently strong random secrets, store a digest (e.g., SHA-256) with the key ID and compare securely; human-chosen passwords require a password KDF rather than being treated like random API keys.
- **Owner/tenant/environments**: know which application owns the key and where it is valid; never use test keys in production.
- **Permissions/scope**: least privilege, e.g., `reports:read`, with dedicated quotas/rate limits.
- **Expiry/disable/revoke**: revoke immediately upon leak or client retirement; track last-used time without logging secrets.
- **Rotation**: allow a brief overlap window where both old and new keys are valid, update the client, then revoke the old key.
- **Client-side storage**: controlled secret manager/environment variables; avoid Git, frontend bundles, mobile APKs, shell history, and public plaintext configs.

When supporting multiple keys, do not hardcode a single shared key like the demo. Build a KeyRepository/AuthenticationProvider that looks up the key ID, compares digests, checks status, expiry, scope, and tenant, and builds a principal containing the **client ID** without the raw credential. The database requires uniqueness and safe revocation. Return 401 for wrong/missing keys; 403 for authenticated clients denied by policy.

## 12. Migrating legacy APIs that accept `?api_key=...`

There is no need to support query parameters forever because the risk persists. A controlled migration path:

1. **Inventory** clients/SDKs/API docs passing keys via query/path; identify owners and environments.
2. **Add the canonical header** in clients/gateways per the contract; test authentication, logging, and permissions.
3. **Announce the migration** and a clear cutoff. Do not log verbatim URLs containing keys while measuring legacy usage.
4. **Stop authenticating from URLs**: accept headers only. If legacy clients still send query params, return a generic error and direct them to update configuration via documentation channels.
5. **Audit secrets that may have leaked** into access logs/analytics/caches under security and retention procedures; rotate/revoke keys as needed.
6. **Verify after cutover** at ingress, backend, and tests. Never "temporarily fall back" to query params when the header is invalid, as that breaks the policy.

The filter example above demonstrates this exact principle: requests with `?api_key=...` **but without `X-API-Key`** are not authenticated. Only use dummy keys to simulate URLs containing secrets; never intentionally place real keys into URLs for testing.

## 13. Common mistakes

| Misconception | Why it is wrong | Mitigation |
| --- | --- | --- |
| "HTTPS makes keys in URLs safe" | URLs are still visible at TLS termination and can enter logs | Move credentials to headers, redact logs |
| "Renaming `api_key` to `token` fixes it" | Query params are still part of the URL | Stop using query credentials |
| "Headers are always secret" | Headers can be logged by proxies/APM/debug logs | Redact `X-API-Key`/`Authorization` at every layer |
| "`X-API-Key` is a mandatory standard" | It is an API-chosen header name | Standardize in docs/SDK/OpenAPI |
| "Every API key is an OAuth bearer access token" | Issuer, grant, token validation, and contract may differ | Use the appropriate validator for each mechanism |
| "A valid key grants the client all permissions" | Authentication and authorization are different | Check scopes, tenant, and record ownership |
| "Use CORS to block clients without a key" | CORS only governs certain browser behaviors | Authenticate and authorize on the server |
| "SPAs can hide keys because JavaScript is minified" | Bundles and requests can still be inspected | BFF or user-based OAuth2/OIDC |
| "Sending keys in the path is safer than query" | Both are part of the URL | Never send keys in path/query |
| "Keys in POST bodies never leak" | Bodies can be captured/traced, and don't work consistently for GET | Header per contract, protect logging |
| "Machine-to-machine APIs must always disable CSRF" | If browser cookies/sessions are used, CSRF risk remains | Evaluate transport and threat model |
| "One shared key for all customers is simpler" | No per-client permissions, auditing, or revocation | Independent keys per client/tenant |
| "Testing only a valid key is enough" | Misses URL fallback, duplicate headers, and 403s | Test positive, negative, proxy, and permission cases |

## 14. Self-check questions

**1.** A request has `https://api.example.org/report?api_key=K`. Does HTTPS prevent server access logs from storing K?  
**No.** The server/gateway still sees the decrypted URL at TLS termination, and logging may record it.

**2.** Keys are sent in `X-API-Key`. Can "log all request headers" be enabled in production?  
**No.** Headers also require redaction. Never put verbatim credentials into logs or traces.

**3.** A browser SPA embeds a static key in JavaScript but sends it in an HTTPS header. Is the key protected?  
**No.** Users can inspect network requests/code. The credential distribution model must be changed.

**4.** Request `/api/report?api_key=K` has no header. What does the Spring Security example return?  
**401**, because the filter does not read query params and the endpoint requires `API_READ`.

**5.** Does using `Authorization: Bearer <token>` mean a custom API key is being used?  
**Not necessarily.** Bearer is typically an OAuth access token with its own verification rules; follow the contract.

**6.** A key authenticates client A, and the request accesses a tenant B resource. Is it allowed if the key is valid?  
**Only if policy actually permits it.** Key authentication does not eliminate tenant and object-level permission checks.

### Implementation checklist

- [ ] Accept API keys only in the canonical header per contract.
- [ ] Use HTTPS and verify certificates properly on all hops requiring protection.
- [ ] Never place secrets in path/query/fragment/userinfo, even in real test links.
- [ ] Redact `X-API-Key`, `Authorization`, and sensitive URLs/queries in proxies, apps, APMs, and client logs.
- [ ] Never embed static secret keys in SPAs/mobile apps or commit them to repos.
- [ ] API keys have ID, owner, tenant, scope, expiry, revocation, rotation, and rate limits.
- [ ] The API checks authorization per endpoint/resource.
- [ ] Test missing/wrong/valid/duplicate headers, query keys, and paths through the gateway.
- [ ] Never disable CSRF if browser cookies are still used as credentials without a risk analysis.
- [ ] Never store real keys in support tickets, stdout, CI artifacts, or screenshots.

## 15. References

- [OWASP REST Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/REST_Security_Cheat_Sheet.html): HTTPS, API Keys, keeping sensitive data out of URLs, and API controls.
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750): passing Bearer access tokens via `Authorization`, warnings on query parameter usage.
- [Spring Security — Servlet Architecture](https://docs.spring.io/spring-security/reference/6.5/servlet/architecture.html): SecurityFilterChain ordering, custom authentication filters.
- [Spring Security — Session Management](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/session-management.html): session policies and stateless authentication.
- [OpenAPI 3.0.3 — Security Scheme Object](https://spec.openapis.org/oas/v3.0.3#security-scheme-object): describing API keys in headers.
- [Spring Boot 3.3 Reference](https://docs.spring.io/spring-boot/3.3/reference/): application configuration and testing.

**Key takeaway:** keep secrets out of URLs, place API keys in a standardized HTTP header over HTTPS, never fall back to query params, and protect headers from logs. Accepting a valid API key is only the client authentication step; authorization and key lifecycle management remain mandatory.