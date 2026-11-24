# Pre-authentication and Trust Boundaries with Upstream Authenticating Proxies

## 1. What Is Pre-authentication?

In a **Spring Security Servlet** application, *pre-authentication* is the model where **a trusted upstream system has already authenticated the user**, and the downstream application receives that authentication result to construct an `Authentication` and enforce its own authorization rules.

For example: a user accesses `https://reports.example.com`; a reverse proxy or identity-aware gateway checks an OIDC/SAML session, then forwards the request to Spring Boot along with the identity verified by the gateway. The application does not directly verify passwords or execute OAuth2 login at that step, yet it still must map the principal to permitted authorities.

**Most dangerous pitfall:** HTTP headers sent by clients can always be forged. `X-Verified-User: alice` is only valid identity evidence **when a trusted proxy has stripped client-supplied headers, authenticated the user successfully, and generated a fresh header itself**, and the backend accepts requests exclusively from that proxy. If clients can connect directly to the backend and set headers themselves, pre-authentication turns into complete authentication bypass.

Distinguish clearly between:

- **Authentication:** who the caller is; the gateway may perform this initial verification step.
- **Pre-authentication:** the backend accepts an authentication result handed across a trust boundary.
- **Authorization:** what the caller is allowed to do in the application; Spring Security/the backend must still enforce this.
- **Transport trust:** who is allowed to send authentication results to the backend, and over which network path.
- **Identity claims vs. network metadata:** `X-Forwarded-Proto` indicates the scheme, not who has signed in.

Pre-authentication is not "just turning on a filter." It is a security contract **between the browser/client, the authenticating proxy, the internal network, and the resource application**.

## 2. Proper Architecture vs. Vulnerable Architecture

### Desired Flow

```text
                 Untrusted Internet
Browser/Client ------------------------------------+
                                                   |
                              HTTPS                v
                     +-------------------------------+
                     | Identity-aware reverse proxy  |
                     | 1. Verify cookie/token        |
                     | 2. Strip incoming ID headers  |
                     | 3. Set trusted identity header|
                     +-------------------------------+
                                  |
                                  | private network / mTLS
                                  | X-Verified-User: alice
                                  v
                     +-------------------------------+
                     | Spring Boot Servlet           |
                     | RequestHeaderAuthentication   |
                     | Filter -> AuthenticationMgr   |
                     | -> PreAuthenticatedProvider   |
                     | -> app UserDetails/permissions|
                     | -> authorizeHttpRequests      |
                     +-------------------------------+
                                  |
                                  v
                            Controller/API
```

If the proxy rejects the login session, the request **must not be forwarded** to the backend as an authenticated request. If the proxy authenticates successfully yet cannot establish a clear identity, it must **fail closed**: assign no default principal and never reuse a prior client header as identity.

### Attack Flow When the Backend Is Exposed

```http
GET /api/reports HTTP/1.1
Host: internal-app.example.com
X-Verified-User: admin
```

If the backend is exposed and uses `RequestHeaderAuthenticationFilter` to trust `X-Verified-User` directly, an attacker can claim to be `admin`. **HTTPS on this request does nothing to validate the header's authenticity**; TLS only protects the connection to the server the attacker just called.

Questions you must answer before using pre-authentication:

1. Can the backend be called directly outside the proxy?
2. Who is permitted to set `X-Verified-User` or an equivalent header?
3. Does the proxy strip **every variant** of the identity header from clients before attaching the verified value?
4. How does the proxy authenticate (OIDC session, mTLS, verified JWT, SSO…)?
5. Where does the application obtain roles/scopes, and how are permissions scoped per tenant?
6. When the proxy/auth service fails, are requests rejected or let through?

## 3. What Components Does Spring Security Have?

In the request-header-based Servlet pre-authentication model, you will encounter:

| Component | Function | Security note |
| --- | --- | --- |
| `RequestHeaderAuthenticationFilter` | Reads principal (and optionally credentials) from a header set by an upstream system | **Does not verify** the proxy or user itself |
| `AbstractPreAuthenticatedProcessingFilter` | Base class for filters accepting identities already authenticated by another source | Requires an appropriate `AuthenticationManager` |
| `PreAuthenticatedAuthenticationToken` | Carries principal and credentials through the authentication chain | Not a JWT and does not prove the header is trustworthy |
| `PreAuthenticatedAuthenticationProvider` | Uses `AuthenticationUserDetailsService` to load `UserDetails` and authorities | Place only behind a trust boundary |
| `AuthenticationUserDetailsService<PreAuthenticatedAuthenticationToken>` | Looks up/maps the pre-auth token identity to backend-recognized user/roles | Avoid blindly trusting roles from clients |
| `SecurityContext` | Holds the `Authentication` for the request being processed | Must control session/caching if identity can change |
| `SecurityFilterChain` | Registers the filter, URL authorization, and error handling | Rules must still deny missing identities or missing permissions |

`RequestHeaderAuthenticationFilter` is not `BearerTokenAuthenticationFilter`: the latter extracts a bearer token for a Resource Server to verify JWTs or introspect opaque tokens, whereas request-header pre-auth **relies on an upstream system having already authenticated**. Do not use `RequestHeaderAuthenticationFilter` as a way to "decode a JWT from a header"—it does not do that.

Similarly, pre-auth based on client certificates or Java EE container principals has its own filters/adapters; identity taken from a **certificate verified by the TLS stack** differs fundamentally from a plain text header named `X-Client-Cert` sent by an arbitrary client.

## 4. Trust Boundaries of HTTP Headers

An ordinary request header is **caller-supplied data**. Elevating it into an identity assertion requires a **trusted issuer and a locked-down transport channel**.

This architectural invariant can be stated as:

```text
Backend trusts X-Verified-User only when:
  network caller = trusted proxy
  AND proxy executed authentication
  AND proxy stripped/overwrote client-supplied headers
  AND header value was constructed by the proxy from the auth result
  AND backend still enforces user/permission checks per app policy.
```

If any clause fails to hold, trusting the header can become a vulnerability.

**Especially never use `X-Forwarded-For` as user proof.** That header describes a chain of network addresses and is only trustworthy when properly normalized by proxies. `X-Forwarded-Proto: https` is not proof of identity authentication either. `request.getRemoteAddr()` can be altered by forwarded-header processors; if you rely on it to verify the real *peer*, understand the container/proxy config, or better yet enforce it via firewall/network policy and mTLS.

When multiple layers exist—CDN, load balancer, ingress, API gateway—explicitly designate which layer authenticates the user and which is the **source of truth** for the identity header. An outer gateway authenticating properly while an inner gateway accidentally preserves a client header still breaks security.

## 5. Spring Boot 3.3.x, Java 17+, Spring Security Servlet Example

This is a learning example consisting of a read-only API illustrating `RequestHeaderAuthenticationFilter` and `PreAuthenticatedAuthenticationProvider`. For local execution, the backend binds only to loopback `127.0.0.1`. **Do not treat loopback access as proof that headers are authenticated**: another process on the same machine can still set headers directly. In production, place the application behind an authenticating proxy with network controls, never expose the backend port, and use a real identity store and business permissions.

### 5.1. Project Structure

```text
preauth-demo/
├── build.gradle
└── src/
    ├── main/
    │   ├── java/demo/preauth/
    │   │   ├── PreAuthApplication.java
    │   │   ├── SecurityConfig.java
    │   │   └── ReportController.java
    │   └── resources/application.yml
    └── test/java/demo/preauth/PreAuthIntegrationTest.java
```

Create `build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'demo'
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
```

Create `src/main/resources/application.yml`:

```yaml
server:
  address: 127.0.0.1
  port: 8080
```

In this application, the loopback address prevents external network access to the backend on the same host. When running across Kubernetes/separate network namespaces, you must use appropriate network policies/service bindings rather than applying loopback literally.

Create `src/main/java/demo/preauth/PreAuthApplication.java`:

```java
package demo.preauth;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class PreAuthApplication {
    public static void main(String[] args) {
        SpringApplication.run(PreAuthApplication.class, args);
    }
}
```

### 5.2. Configuring Pre-authentication and Permissions

Create `src/main/java/demo/preauth/SecurityConfig.java`:

```java
package demo.preauth;

import jakarta.servlet.http.HttpServletResponse;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UsernameNotFoundException;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.preauth.AbstractPreAuthenticatedProcessingFilter;
import org.springframework.security.web.authentication.preauth.PreAuthenticatedAuthenticationProvider;
import org.springframework.security.web.authentication.preauth.PreAuthenticatedAuthenticationToken;
import org.springframework.security.web.authentication.preauth.RequestHeaderAuthenticationFilter;

@Configuration
public class SecurityConfig {

    @Bean
    AuthenticationManager preAuthManager() {
        PreAuthenticatedAuthenticationProvider provider =
                new PreAuthenticatedAuthenticationProvider();

        provider.setPreAuthenticatedUserDetailsService(token -> {
            String name = String.valueOf(token.getPrincipal());

            // Learning data: replace with application's identity/tenant store.
            UserDetails user = switch (name) {
                case "alice" -> User.withUsername("alice")
                        .password("{noop}unused")
                        .authorities("REPORT_READ")
                        .build();
                case "admin" -> User.withUsername("admin")
                        .password("{noop}unused")
                        .authorities("REPORT_READ", "REPORT_ADMIN")
                        .build();
                default -> throw new UsernameNotFoundException(
                        "Unknown pre-authenticated principal");
            };
            return user;
        });

        return new ProviderManager(provider);
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http, AuthenticationManager preAuthManager)
            throws Exception {

        RequestHeaderAuthenticationFilter preAuthFilter =
                new RequestHeaderAuthenticationFilter();
        preAuthFilter.setPrincipalRequestHeader("X-Verified-User");
        // Missing header => no principal, let authorization deny.
        preAuthFilter.setExceptionIfHeaderMissing(false);
        preAuthFilter.setAuthenticationManager(preAuthManager);
        preAuthFilter.setCheckForPrincipalChanges(true);

        return http
                .sessionManagement(session -> session
                        .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers(HttpMethod.GET, "/api/health")
                                .permitAll()
                        .requestMatchers(HttpMethod.GET, "/api/reports")
                                .hasAuthority("REPORT_READ")
                        .requestMatchers(HttpMethod.GET, "/api/admin")
                                .hasAuthority("REPORT_ADMIN")
                        .anyRequest().denyAll())
                .exceptionHandling(ex -> ex
                        .authenticationEntryPoint((request, response, error) ->
                                response.sendError(
                                        HttpServletResponse.SC_UNAUTHORIZED)))
                .addFilterAt(preAuthFilter,
                        AbstractPreAuthenticatedProcessingFilter.class)
                .build();
    }
}
```

**Explaining each decision:**

1. `RequestHeaderAuthenticationFilter` **only reads** `X-Verified-User`. There is no signature or header-origin check at this layer, so the proxy and network boundary are mandatory prerequisites.
2. `setExceptionIfHeaderMissing(false)` ensures a missing header does not throw immediately during extraction; the request remains unauthenticated and protected rules reject it. With `authenticationEntryPoint` above, routes requiring authentication typically return `401`.
3. `PreAuthenticatedAuthenticationProvider` loads user details by the proxy-authenticated name. The demo allows `alice` to read reports, while `admin` also holds admin permission. **Do not read a client-supplied `X-Role`** to grant `REPORT_ADMIN`.
4. `SessionCreationPolicy.STATELESS` demonstrates re-authenticating on every request, avoiding keeping one authenticated user cached in an HTTP session when the proxy identity changes. If a production app uses sessions, carefully design logout synchronization, principal changes, and session fixation handling.
5. The filter is created **inside `SecurityFilterChain`**, not declared as a separate `@Bean Filter`. This prevents Spring Boot from accidentally auto-registering the filter a second time outside the security chain.
6. `.addFilterAt(..., AbstractPreAuthenticatedProcessingFilter.class)` places the filter at the pre-auth position in the security chain. In projects with multiple `SecurityFilterChain` beans, ensure the right chain applies and avoid registering the same filter multiple times.
7. `anyRequest().denyAll()` ensures only explicitly designed URLs are open. This is not a template for every application, rather the demo's minimal policy.
8. `password("{noop}unused")` merely satisfies the demo `UserDetails` structure; **this password is never used for login**, since there is no username/password authentication in this flow.

Key point: this application is secure only when **incoming headers are genuinely created by a trusted proxy**. `SecurityConfig` alone cannot prove that, so never expose port 8080 to the Internet.

### 5.3. Controller Checking Principal and Authorities

Create `src/main/java/demo/preauth/ReportController.java`:

```java
package demo.preauth;

import java.util.List;
import java.util.Map;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ReportController {

    @GetMapping("/api/health")
    public Map<String, String> health() {
        return Map.of("status", "ok");
    }

    @GetMapping("/api/reports")
    public Map<String, Object> reports(Authentication authentication) {
        List<String> authorities = authentication.getAuthorities().stream()
                .map(GrantedAuthority::getAuthority)
                .sorted()
                .toList();
        return Map.of(
                "principal", authentication.getName(),
                "authorities", authorities);
    }

    @GetMapping("/api/admin")
    public Map<String, Boolean> admin() {
        return Map.of("allowed", true);
    }
}
```

The controller does not return raw headers, cookies, or access tokens. It uses the `Authentication` placed into the security context by Spring Security. In production, avoid exposing all authorities to callers; this `/api/reports` endpoint is solely for demo purposes.

## 6. Running the Application and Interpreting Results Correctly

Run using the project's Gradle wrapper:

```bash
./gradlew bootRun
```

On Windows PowerShell use `.\gradlew.bat bootRun`.

Call the unauthenticated endpoint:

```bash
curl -i http://127.0.0.1:8080/api/health
```

A successful response returns HTTP 200 and JSON equivalent to:

```json
{"status":"ok"}
```

Call reports **without the pre-auth header**:

```bash
curl -i http://127.0.0.1:8080/api/reports
```

Expect `401 Unauthorized` in the demo configuration.

Call reports with a **simulated header**:

```bash
curl -i http://127.0.0.1:8080/api/reports \
    -H "X-Verified-User: alice"
```

In the local demo, you will see HTTP 200 with JSON equivalent to:

```json
{
  "principal": "alice",
  "authorities": ["REPORT_READ"]
}
```

**Essential warning:** the very fact that `curl` on the same machine can spoof the header and still be authenticated proves **the pre-auth filter does not verify identity**. Only proxy configuration and blocking direct connections turn the header into a trusted identity assertion. Never allow that direct call path in production.

Test missing permission:

```bash
curl -i http://127.0.0.1:8080/api/admin \
    -H "X-Verified-User: alice"
```

Expect HTTP `403 Forbidden` because `alice` was recognized but lacks `REPORT_ADMIN`. Conversely, `X-Verified-User: admin` in the demo passes this rule, underscoring that **any client allowed to attach headers directly to the backend can impersonate `admin`**.

## 7. Testing with Java 17+ and MockMvc

Create `src/test/java/demo/preauth/PreAuthIntegrationTest.java`:

```java
package demo.preauth;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class PreAuthIntegrationTest {

    @Autowired
    MockMvc mvc;

    @Test
    void noIdentityHeaderMeansUnauthenticated() throws Exception {
        mvc.perform(get("/api/reports"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void trustedIdentityIsMappedToApplicationPermission()
            throws Exception {
        mvc.perform(get("/api/reports")
                        .header("X-Verified-User", "alice"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.principal").value("alice"))
                .andExpect(jsonPath("$.authorities[0]")
                        .value("REPORT_READ"));
    }

    @Test
    void knownUserWithoutAdminPermissionIsForbidden()
            throws Exception {
        mvc.perform(get("/api/admin")
                        .header("X-Verified-User", "alice")
                        .header("X-Verified-Role", "ADMIN"))
                .andExpect(status().isForbidden());
    }

    @Test
    void unknownPrincipalIsNotAutomaticallyTrusted()
            throws Exception {
        mvc.perform(get("/api/reports")
                        .header("X-Verified-User", "mallory"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void adminPermissionComesFromApplicationUserDetails()
            throws Exception {
        mvc.perform(get("/api/admin")
                        .header("X-Verified-User", "admin"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.allowed").value(true));
    }
}
```

Run:

```bash
./gradlew test
```

These tests confirm **header-to-principal conversion** and application permission mapping; they **do not prove the proxy actually authenticated the user**. MockMvc intentionally lets you simulate headers to test the filter. End-to-end testing through ingress/proxy is required: an Internet request self-setting `X-Verified-User: admin` without valid credentials must still be blocked.

## 8. Reverse Proxy Example: Authenticating Before Setting the Header

A system might use Nginx `auth_request` to query an internal authentication service. The snippet below shows **only `location` blocks inside an HTTPS `server` block already configured with certificates and trusted proxy settings**, not a complete Nginx config file.

```nginx
# Every /api/ request must first be authorized by the auth service.
location /api/ {
    auth_request /_verify_identity;
    auth_request_set $verified_user $upstream_http_x_verified_user;

    # Overwrite any client-sent header with the auth subrequest result.
    proxy_set_header X-Verified-User $verified_user;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-Proto $scheme;

    proxy_pass http://127.0.0.1:8080;
}

# Internal Nginx call; Internet clients cannot call this location directly.
location = /_verify_identity {
    internal;
    proxy_pass http://127.0.0.1:8081/verify;
    proxy_pass_request_body off;
    proxy_set_header Content-Length "";
    proxy_set_header Authorization $http_authorization;
}
```

For this model to work safely:

1. The auth service at `127.0.0.1:8081/verify` genuinely validates the session or bearer token, **not** merely echoing a client-sent identity header.
2. On success, the auth service returns `2xx` and a header **it generates itself**: `X-Verified-User: <verified principal>`. On unauthenticated requests, it returns `401` or `403`, never asserting a user.
3. Nginx `auth_request` forwards the request to the application only when the subrequest succeeds. `auth_request_set` captures identity from the auth service response; `proxy_set_header` replaces any header value received from the client. Without a valid username, the backend must grant no access.
4. Port 8080 **must not be exposed directly to the Internet**; e.g. use loopback on the same host. Across multiple containers/hosts, use an internal network restricting connection sources, firewall/network policy, or mTLS.
5. Check **duplicate headers/aliases** and how the proxy normalizes header names. Never accept two conflicting values and "just pick the first one."
6. The deployed Nginx build must support `auth_request`; other proxy auth mechanisms (ingress external auth, Envoy ext_authz, API gateways) follow a similar contract.

Fail-closed policy on errors: an unreachable/timed-out auth service or invalid response must fail the request; **never fall back** to "proxy lets requests through when the auth server errors." After auth succeeds, the proxy must govern user, tenant, and role headers against an approved whitelist.

## 9. Safely Interpreting Identity in the Backend

A useful identity assertion might contain:

```text
X-Verified-User: user-42
X-Verified-Tenant: tenant-acme
```

However, **two headers still do not replace business-level checks**:

- If the verified token/session belongs to tenant `A`, the proxy must not allow the client to pick `X-Verified-Tenant: B`.
- The backend must look up the principal and verify whether the user is still active, which tenant and roles they belong to, and which resources they may access.
- Privileges like `REPORT_ADMIN` are best pulled from a backend-controlled authority store or an assertion that is **signed/delivered over a strongly authenticated channel** with verified audience.
- Stable IDs (issuer-namespaced `sub`/subject) are usually better than mutable display names or emails.
- With multiple identity providers, tie user identity to **issuer + subject**; identical `"alice"` strings from two issuers are not automatically the same person.

Depending on compliance requirements, you can choose **full gateway delegation** (backend trusts verified user and role assertions) or **partial delegation** (gateway authenticates, backend decides permissions). In either case, the backend must know **which assertion source is authorized to grant which permissions**.

Examples of fields to retain in internal audit logs: correlation ID, normalized principal ID, verified issuer/tenant ID, route, authorization outcome, proxy ID, error code. Never log cookies, bearer tokens, private claims, or full authentication headers.

## 10. Common Attacks and Implementation Pitfalls

| Risk / Symptom | Cause | Mitigation |
| --- | --- | --- |
| Stranger sends `X-Verified-User: admin` and gains access | Exposed backend or proxy retains client header | Block direct backend access; proxy strips/overwrites all identity headers |
| Auth service times out yet request gets through | Fail-open gateway | Fail closed, monitor 5xx, and block without a valid identity assertion |
| Logged-out user still accesses API | Gateway session/cookie still valid or backend reuses stale SecurityContext | Align session revocation, request-level authentication, and timeouts |
| User A receives User B's permissions | Cache/security context retains identity across requests, faulty principal mapping | Use stateless or check principal changes; scope caches by user/tenant |
| User header present yet app returns 401 | Header not received, principal unknown, wrong header name | Check proxy upstream headers, user-details lookup, and entry point |
| Principal present yet app returns 403 | Missing resource authority | Check `GrantedAuthority`, object/tenant rights; do not loosen roles automatically |
| Proxy forwards client-supplied `X-Verified-Role: ADMIN` | Failing to separate authentication proof from arbitrary metadata | Load roles from backend store or verified assertions |
| App trusts `X-Forwarded-For` as true source IP | Spoofed header or multiple proxy hops | Trust IP at network boundary/real proxy, not arbitrary headers |
| Two headers with different casing | Inconsistent normalization and duplicate handling | Normalize at the edge; emit a single assertion |
| Identity header contains commas/odd characters | Multi-value string or injection | Enforce encoding, length, format validation, and reject ambiguities |
| App runs behind ingress yet backend service is public | Misconfigured LoadBalancer/Ingress/firewall policy | Verify external network exposure, not just architecture diagrams |
| Gateway trusts token with wrong audience/issuer | Upstream validation violates contract | Validate signature, issuer, audience, expiry, and token type in auth service |

An especially dangerous mistake is accepting the same header on requests from both the Internet and an internal proxy, then attempting to tell them apart using an `X-Forwarded-For` check. Attackers can forge that header too. Valid rules must rely on **a controlled channel and a trusted identity-assertion issuer**, not easily spoofed hints.

## 11. Relationship to Sessions, CSRF, and CORS

**Sessions:** a pre-auth system may create a Spring Security session under some configurations. If the authenticated header switches from User A to User B while the old session retains `Authentication`, the app can assign the wrong identity. The demo chooses `SessionCreationPolicy.STATELESS` to authenticate per request. In truly session-based apps, inspect principal changes, session invalidation, and logout synchronization with the gateway.

**CSRF:** if the frontend relies on session cookies automatically sent by the browser to the gateway, state-changing requests remain exposed to CSRF risks. CORS only restricts JavaScript from reading cross-origin responses; it **does not replace CSRF protection**. Never disable CSRF globally merely because the proxy logs users in. The demo only uses GET and does not disable CSRF.

**CORS:** an `OPTIONS` preflight request may carry no cookies/session or skip the same authorization flow as real requests. Order CORS policies and gateway auth properly for real endpoints; never invent identity from external headers just to "make OPTIONS pass."

**HTTPS:** the authenticating proxy must use TLS toward clients; the proxy → backend hop also needs protection, such as mTLS/re-encryption when crossing trust zones. Identity headers sent over HTTP on open networks can be observed, altered, or replayed.

**Caching:** proxies/CDNs must never cache one user's private response and serve it to another user. Design `Vary`/`Cache-Control` around user/credential boundaries whenever endpoints return personal data.

## 12. Comparison with Other Authentication Solutions

| Integration type | Who authenticates identity? | When to consider |
| --- | --- | --- |
| Pre-auth + trusted header | Upstream identity proxy/gateway | Backend sits inside a trusted network and must integrate with existing SSO/proxy |
| `oauth2Login()` | Spring Security app participates in OAuth2/OIDC authorization code flow | Web app wants to manage OIDC login/sessions itself |
| `oauth2ResourceServer().jwt()` | Backend verifies JWT access tokens from client/proxy itself | API needs independence without trusting plain text headers |
| Opaque token introspection | Backend queries the authorization server to verify tokens | Provider issues opaque tokens or online token status is required |
| Servlet container mTLS/X.509 pre-auth | TLS stack verified certificate and supplies peer identity | Internal networks/server-to-server with trusted client certificates |

If the backend cannot lock down direct access, it is safer to **verify a bearer token or signed identity assertion** inside the backend itself—checking issuer/audience/expiration/revocation—rather than trusting `X-Verified-User`. When propagating user identity across multiple trust zones, mTLS or scoped short-lived signed assertions are generally far sturdier than unsigned plain headers.

**Never copy a browser's bearer access token into `X-Verified-User` and treat it as a valid principal**: tokens must be validated against a security contract. If the gateway validated it, verify the trust criteria so the backend can rely on that decision; if not, use a Resource Server.

## 13. Testing Across the Proxy Boundary

Unit/MockMvc tests only prove code maps identity to authorities. Pre-auth security requires **negative tests from the Internet side**, such as:

1. Unauthenticated; send `X-Verified-User: admin` to a protected request. The gateway must return `401/403`, and the backend must not serve content.
2. Signed in as `alice`; attempt to attach `X-Verified-User: admin` or `X-Verified-Role: REPORT_ADMIN`. The backend must still recognize `alice` with only the permissions from the trusted source.
3. Send the identity header twice, with different casing or aliases. The proxy must strip/normalize and reject ambiguous cases per policy.
4. Call the backend port directly from an external host. The connection must be rejected at the network boundary, not merely hit a Spring Security error.
5. Auth service down/timeout/5xx. The proxy must not fail open.
6. User locked, logged out, or stripped of roles right before the next request. The backend must not keep granting access from a stale session/cache.
7. Swap the assertion's issuer/tenant in a multi-domain setup. A matching identity name must not cross into another tenant.
8. State-changing requests still enforce CSRF/idempotency/authorization; preflight requests are never accidentally treated as logins.
9. Spoofed `Host` or `Forwarded`/`X-Forwarded-*` headers from the Internet do not alter authority or canonical URLs unexpectedly.
10. Correlate logs cleanly across proxy/auth service/backend via correlation IDs without exposing credentials.

A test using `curl` through a **public HTTPS proxy** can look like:

```bash
curl -i https://reports.example.com/api/admin \
  -H "X-Verified-User: admin" \
  -H "X-Verified-Role: REPORT_ADMIN"
```

If the request has **no valid authentication credentials**, the result **must be a rejection**; you cannot predict exact 401 vs. 403 without knowing the gateway configuration. The example endpoint does not exist at the illustrative hostname, so replace it with the real system's public host in your test scenario.

## 14. Distinguishing "Authenticated" from "Authorized"

An identity proxy may verify user `"alice"` accurately, yet that **does not automatically allow** the user to read every resource. Spring Security still requires:

```java
.requestMatchers(HttpMethod.GET, "/api/reports")
.hasAuthority("REPORT_READ")
```

In multi-tenant applications, `REPORT_READ` may only permit reading reports belonging to **the user's tenant**. Check ownership at the service/database layer; a generic authority does not verify the user can read an arbitrary object ID.

Avoid interpreting roles from free-form text headers like:

```text
X-Verified-User: alice
X-Verified-Roles: ADMIN,SUPERUSER
```

If identity-provider roles are truly required, the proxy must validate and normalize roles along with scope/issuer/audience, and the backend must restrict recognized roles. In practice, many products pass only an **immutable subject ID** and let the backend look up permissions from business data, especially when roles change frequently.

## 15. Pre-Deployment Checklist

- The proxy or identity gateway genuinely enforces authentication for every request to protected areas.
- All identity headers arriving from the Internet are **stripped/overwritten**, including duplicate headers and name variants.
- The backend cannot be reached directly outside the proxy (firewall, internal load balancer, Kubernetes NetworkPolicy, mTLS…).
- The proxy → app channel provides integrity/confidentiality commensurate with identity data.
- A clear contract defines which ID `X-Verified-User` holds, its format/length, and how issuer/tenant are distinguished.
- `RequestHeaderAuthenticationFilter` is placed only inside the intended filter chain, without unintended Servlet filter registration.
- `PreAuthenticatedAuthenticationProvider` maps valid users from the trusted source; unknown users are rejected.
- `Authentication` is constructed properly per request; logouts and principal changes do not reuse stale identities.
- Authorization is enforced separately per endpoint and object/tenant; client-sent roles are never trusted.
- CSRF/CORS/session/HSTS/caching remain configured independently; protections are not disabled just to work behind a proxy.
- Tests cover spoofed headers, direct access, auth-service downtime, stale sessions, duplicate identities, and role escalation.
- Logs/metrics/audits never record cookies, bearer tokens, or raw identity assertions containing sensitive details.

## Remember

Spring Security pre-authentication **does not re-authenticate the user** from an HTTP header; it accepts **an authentication result already proven by an upstream system**. `RequestHeaderAuthenticationFilter` reads the principal, `PreAuthenticatedAuthenticationProvider` turns that principal into an `Authentication` with authorities, and `SecurityFilterChain` governs access. This design is safe only when **the proxy is the sole trusted identity source, Internet requests cannot forge headers, and the backend cannot be called bypassing the proxy**. Whenever that boundary cannot be guaranteed, have the backend verify tokens/assertions itself or use a strong alternative authentication channel.