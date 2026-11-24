# RequestHeaderAuthenticationFilter and Preventing Identity Header Spoofing in Spring Security Servlet

## 1. Context and Goals

An enterprise system may place a Java application behind a **reverse proxy, API gateway, SSO agent, or identity-aware proxy**. The upstream layer authenticates the user via OIDC, SAML, Kerberos, mTLS, or another mechanism, then passes verified identity details to the backend application. Spring Security Servlet supports this pattern under **pre-authentication** (authentication occurred before the request reached the application).

**RequestHeaderAuthenticationFilter** is a filter that extracts identity from an HTTP request header and passes that identity into Spring Security's **AuthenticationManager** workflow. It is useful when **a trusted component has genuinely authenticated the user** and merely forwards a verified identity to the backend.

However, ordinary HTTP headers **can be set by any HTTP client**. If the application treats **X-Verified-User: alice** as login proof while an attacker can send that header directly, the attacker can **impersonate alice**. This is the central challenge of this guide: designing the **trust boundary** before using RequestHeaderAuthenticationFilter.

After this lesson, you should be able to distinguish:

1. The filter **reads headers**; it does not verify user passwords, OIDC/JWT signatures, or mTLS itself.
2. The gateway **authenticates and issues the identity assertion**; the backend trusts assertions only from a protected transport path, component, and configuration.
3. **Authentication** (who is alice?) differs from **authorization** (is alice allowed to read this data?).
4. When to use pre-authentication vs. when a Resource Server should validate Bearer tokens directly.
5. How to configure Spring Security Servlet, test the backend, and specifically test **traffic through the real proxy** to prevent header spoofing.

## 2. What Is RequestHeaderAuthenticationFilter?

The class **org.springframework.security.web.authentication.preauth.RequestHeaderAuthenticationFilter** belongs to the **pre-authenticated requests** family. It inherits behavior from **AbstractPreAuthenticatedProcessingFilter**, extracts the principal from the request, and asks **AuthenticationManager** to process that identity.

High-level flow:

~~~text
Client / Browser
    |
    | SSO cookie or token, depending on architecture
    v
[Trusted Gateway / SSO Proxy]
    | 1. Authenticate request
    | 2. Strip all client-supplied identity headers
    | 3. Attach verified identity header
    v
[Spring Security Servlet Backend]
    | RequestHeaderAuthenticationFilter reads X-Verified-User
    v
AuthenticationManager
    |
    +-- PreAuthenticatedAuthenticationProvider
          |
          +-- Load UserDetails / authorities from trusted source
    |
    v
SecurityContext: Authenticated Authentication
    |
    v
AuthorizationFilter checks endpoint permissions
    |
    v
Controller -> Service -> data
~~~

**Pre-authentication does not mean "skipping authentication."** It means the **identity verification** step was performed at a trusted boundary outside Spring Security. Backend Spring Security remains responsible for establishing Authentication, mapping permissions, and enforcing access control.

Common components:

| Component | Responsibility |
| --- | --- |
| **RequestHeaderAuthenticationFilter** | Reads the identity header value from HttpServletRequest |
| **PreAuthenticatedAuthenticationToken** | Represents principal/credentials before and after AuthenticationManager processing |
| **PreAuthenticatedAuthenticationProvider** | Uses the backend's user-details service to construct an authenticated Authentication |
| **UserDetailsByNameServiceWrapper** | Maps a pre-authenticated principal to UserDetails by username |
| **UserDetailsService** | Loads users and authorities from a backend-managed source |
| **SecurityContextHolder** | Provides the current Authentication to security filters and controllers |
| **AuthorizationFilter** | Checks authorities/roles/policies before allowing endpoint handling |

Note: loading UserDetails **does not prove the header is genuine**. If the header source was spoofed, finding a valid username in the database merely gives the attacker the impersonated account's authorities.

## 3. Threat Model: Where Does a Header Come From?

### 3.1. Vulnerability Example

Suppose the backend exposes a protected endpoint **GET /api/documents**, and the filter trusts the header **X-Verified-User**. A client can craft the request itself:

~~~http
GET /api/documents HTTP/1.1
Host: backend.example.internal
X-Verified-User: alice
~~~

If the backend accepts this request directly **without a trusted authentication layer guaranteeing the header was created by the gateway**, the header is merely **caller-declared data**, not proof the caller is alice.

Risks commonly arise when:

- The backend accidentally has a public port or secondary ingress bypassing the SSO proxy.
- The gateway fails to **strip headers with the same name** from client requests and simply forwards them as-is.
- Multiple proxies sit in sequence, where one sanitizes while another adds/overwrites inconsistently.
- Header name variants, underscores/hyphens, casing differences, or **duplicate headers** are interpreted differently by the proxy and Servlet container.
- Admin endpoints or internal routes share an ingress without equivalent protection.
- A web app trusts a client-sent **X-Forwarded-User** or **X-Auth-User** value simply because its name sounds like it "came from a proxy."

**Warning sign:** open DevTools, curl, or Postman and add the identity header yourself; if you can call the backend directly and receive someone else's permissions, the design has lost its trust boundary. This is not a "hard-to-guess header name problem": header names are not secrets and never replace authentication.

### 3.2. Safer Architecture

~~~text
INTERNET / UNTRUSTED NETWORK
             |
             v
 [Public Gateway / SSO Proxy]
    - Authenticate user / service
    - Reject unauthenticated requests
    - Strip client-entered identity headers
    - Set a single canonical identity
             |
             | Only an allowed internal network path
             | TLS/mTLS or appropriate hop protection
             v
       [Java Backend]
    - Not directly reachable from outside
    - Accepts identity assertions only from trusted gateway
    - Loads authorities from trusted source
    - Enforces permissions per endpoint/resource
~~~

**Invariant requirement:** every request capable of reaching the filter must pass through the same trusted authentication and sanitization policy. Even a single backdoor path to the backend bypassing the gateway invalidates everything relying on the identity header.

To achieve this, apply defense-in-depth controls:

1. **Network boundary:** the backend listens only on a private network or is allowed by firewall/security group/network policy exclusively from the gateway; block direct public exposure, debug ports, and unintended health/admin ports.
2. **Authenticated transport:** protect the gateway → backend hop with TLS, preferring mTLS or service identity on supporting infrastructure; never assume a private IP alone suffices.
3. **Header sanitization:** the gateway must remove all identity headers/variants from client requests and then **re-attach** the canonical header after authentication.
4. **Fail closed:** on missing, failed, or unclear authentication status, the gateway must not forward a trusted principal to the backend. The backend must also reject protected endpoints when Authentication is absent.
5. **Independent authorization:** the backend uses the authenticated principal strictly as input, still checking roles/scopes and object-level permissions.
6. **Safe observability:** log request ID, trusted gateway source, and security decisions; never log tokens/cookies/secrets or excessive personal data.

## 4. Header Name, Principal Value, and Default Behavior

**RequestHeaderAuthenticationFilter** has this core configuration:

~~~java
RequestHeaderAuthenticationFilter filter =
        new RequestHeaderAuthenticationFilter();

filter.setPrincipalRequestHeader("X-Verified-User");
filter.setExceptionIfHeaderMissing(false);
filter.setAuthenticationManager(authenticationManager);
~~~

Explanation:

- **setPrincipalRequestHeader(...)** selects the exact header holding the identity read by the filter. If unconfigured, this implementation defaults to **SM_USER**, originating from traditional pre-authentication systems.
- **setExceptionIfHeaderMissing(false)** lets requests lacking the header pass through the filter without throwing an exception solely for the missing header. **This does not mean allowing access:** the endpoint must still require authentication/authorities and return 401/403 appropriately.
- **setAuthenticationManager(...)** connects the filter to an AuthenticationManager with a provider handling **PreAuthenticatedAuthenticationToken**.
- The filter can optionally read a credentials header, but **you should never transmit actual user passwords in an HTTP header for "pre-auth."** The goal is consuming a verified identity from a trusted boundary, not offloading password checks to the backend by stuffing credentials into headers.
- A custom header name is not a secret key. Renaming X-Verified-User to a long/random string **does not stop spoofing** if attackers can reach the backend or trick the gateway into forwarding headers.

**Distinguishing username from permissions:** the header **X-Verified-User: alice** does not mean alice has the ADMIN role. When an internal user data source exists, the backend should load authorities from a trusted store and enforce consistent policies. If the gateway also sends roles/groups, there must be a strict provenance and integrity contract; never trust **X-Verified-Roles** from external requests.

**Characters and normalization:** the gateway must define a stable representation for the principal (e.g., durable subject ID), avoiding mutable usernames or collisions across tenants. Define how blank, duplicate, or invalid values and tenant mappings are handled; never just call **getHeader(...)** and blindly assume it represents a unique user.

## 5. How Does Spring Security Process Pre-authentication?

On the backend, the filter extracts the principal from the request. From there, a suitable provider can verify the principal's **validity against backend policy**, such as looking up a registered, enabled UserDetails and loading the corresponding authorities.

This **differs** from password authentication:

| Aspect | Username/password at backend | Header-based pre-authentication |
| --- | --- | --- |
| Initial evidence | Username + secret verified by authentication flow | Assertion generated by trusted gateway |
| Component checking secret/SSO | Backend or IdP in integrated flow | Gateway/SSO proxy external to backend |
| Value seen by backend | Username/password or token verified directly by backend | Unsigned principal header |
| Typical provider | DaoAuthenticationProvider or matching mechanism | PreAuthenticatedAuthenticationProvider |
| Specific risks | Brute force, secret handling, credential stuffing | **Header spoofing**, direct backend bypass, stale principal |
| Authorization | Still required | **Still required** |

In the pre-authentication model, AuthenticationManager must not accept "just any name" and grant elevated roles. A provider backed by **UserDetailsService** should only grant permissions based on data the backend trusts. When an application supports multiple organizations/tenants, the gateway-issued principal should be strong enough to prevent collisions across organizations.

### 5.1. What If the Header Is Missing?

With **exceptionIfHeaderMissing(false)**, the filter creates no new Authentication; endpoints requiring authentication must reject per rules. With **exceptionIfHeaderMissing(true)**, the filter throws an exception for the missing header. The two modes differ in **how errors are signaled**, not in authentication obligations. Production goals are clear responses, failing closed, and avoiding system information leaks.

### 5.2. What If the Session and Header Change?

An application may use sessions/SecurityContext across requests. In that case, analyze the risk of **identity A in the session while the current request's header carries identity B**. AbstractPreAuthenticatedProcessingFilter supports checking principal changes via configuration, yet re-authentication/invalidation policies must be explicitly designed and tested; never assume a new header automatically replaces an old Authentication in every scenario.

For pre-auth APIs behind a gateway, if the backend does not need HttpSession, a **stateless** model reduces the risk of reusing stale SecurityContexts. Even so, remember: if **the gateway authenticates browsers via cookies**, the outer boundary may still be exposed to **CSRF**, even when the backend stores no session. Backend statelessness **does not automatically make browser requests immune to CSRF**.

## 6. Java 17 Example: RequestHeaderAuthenticationFilter in Spring Security Servlet

The example uses **Spring Boot 3.4.5, Spring Security 6, Java 17, Spring MVC**. Endpoint **GET /api/documents** requires role READER. The filter reads only **X-Verified-User**, loading authorities for two users: **alice** (READER) and **bob** (VIEWER).

**Safety limits of the demo:** the Java code below **assumes** a trusted gateway already authenticates users, strips spoofed headers, and is the sole path to the backend. Running standalone on localhost **does not prove a gateway exists**; if the backend port is exposed to the Internet, outsiders can set X-Verified-User themselves. This example illustrates the Spring Security filter/provider and **must not be copied verbatim to expose a public API**.

Project structure:

~~~text
header-preauth-demo/
├── pom.xml
└── src/
    ├── main/java/demo/preauth/HeaderPreauthApplication.java
    └── test/java/demo/preauth/HeaderPreauthApplicationTests.java
~~~

**pom.xml**:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.4.5</version>
        <relativePath/>
    </parent>
    <groupId>demo</groupId>
    <artifactId>header-preauth-demo</artifactId>
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
~~~

**src/main/java/demo/preauth/HeaderPreauthApplication.java**:

~~~java
package demo.preauth;

import java.util.List;
import java.util.Map;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.http.ResponseEntity;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.core.userdetails.UserDetailsByNameServiceWrapper;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.UsernamePasswordAuthenticationFilter;
import org.springframework.security.web.authentication.preauth.PreAuthenticatedAuthenticationProvider;
import org.springframework.security.web.authentication.preauth.PreAuthenticatedAuthenticationToken;
import org.springframework.security.web.authentication.preauth.RequestHeaderAuthenticationFilter;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class HeaderPreauthApplication {
    public static void main(String[] args) {
        SpringApplication.run(HeaderPreauthApplication.class, args);
    }
}

@Configuration
class SecurityConfiguration {

    @Bean
    UserDetailsService userDetailsService() {
        // Simulates internal directory. Password is NOT used
        // to verify pre-authentication via a trusted gateway.
        return new InMemoryUserDetailsManager(
                User.withUsername("alice")
                    .password("{noop}unused")
                    .roles("READER").build(),
                User.withUsername("bob")
                    .password("{noop}unused")
                    .roles("VIEWER").build());
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http,
                                           UserDetailsService users)
            throws Exception {
        // Only backends trusting a gateway that already verified identity
        // may use this model in production.
        UserDetailsByNameServiceWrapper<PreAuthenticatedAuthenticationToken>
                lookup = new UserDetailsByNameServiceWrapper<>();
        lookup.setUserDetailsService(users);

        PreAuthenticatedAuthenticationProvider provider =
                new PreAuthenticatedAuthenticationProvider();
        provider.setPreAuthenticatedUserDetailsService(lookup);
        AuthenticationManager manager = new ProviderManager(provider);

        RequestHeaderAuthenticationFilter preAuth =
                new RequestHeaderAuthenticationFilter();
        preAuth.setPrincipalRequestHeader("X-Verified-User");
        preAuth.setExceptionIfHeaderMissing(false);
        preAuth.setAuthenticationManager(manager);

        // Instantiate filter directly inside chain, DO NOT declare a
        // separate @Bean RequestHeaderAuthenticationFilter:
        // prevents Spring Boot from auto-registering it as a Servlet Filter
        // running a second time outside SecurityFilterChain.
        return http
                .sessionManagement(session ->
                        session.sessionCreationPolicy(
                                SessionCreationPolicy.STATELESS))
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers(
                                HttpMethod.GET, "/api/documents")
                            .hasRole("READER")
                        .anyRequest().denyAll())
                .exceptionHandling(ex -> ex.authenticationEntryPoint(
                        (request, response, exception) ->
                                response.sendError(
                                        HttpServletResponse.SC_UNAUTHORIZED)))
                .addFilterBefore(preAuth,
                        UsernamePasswordAuthenticationFilter.class)
                // Keep default CSRF. Demo only has GET.
                .build();
    }
}

@RestController
class DocumentController {
    @GetMapping("/api/documents")
    ResponseEntity<Map<String, Object>> list(Authentication authentication) {
        return ResponseEntity.ok(Map.of(
                "user", authentication.getName(),
                "documents", List.of("DOC-001")));
    }
}
~~~

**Reading the code step by step:**

1. **UserDetailsService** loads users and roles; this is the backend-managed authority source.
2. **UserDetailsByNameServiceWrapper** lets the provider look up UserDetails using the principal supplied by the pre-auth filter.
3. **PreAuthenticatedAuthenticationProvider** processes the PreAuthenticatedAuthenticationToken created by the filter; it does not check SSO cookies or client passwords itself.
4. **RequestHeaderAuthenticationFilter** reads **X-Verified-User**, delegates to AuthenticationManager, and places Authentication into SecurityContext per filter behavior.
5. **addFilterBefore(...)** inserts the filter into the Spring Security chain before UsernamePasswordAuthenticationFilter. This **does not make the header trustworthy**: only the gateway/network controls do that.
6. **hasRole("READER")** requires authority **ROLE_READER**. alice has ROLE_READER and passes; bob only has ROLE_VIEWER and is denied.
7. **anyRequest().denyAll()** provides a safe fallback for other routes. **SessionCreationPolicy.STATELESS** prevents storing Authentication in the backend's HttpSession.
8. We **do not disable CSRF mechanically**. Since the demo only uses GET, CSRF does not block requests. If later the gateway uses cookies to authenticate browsers and the API has POST/PUT/DELETE, proper CSRF protection must be evaluated and maintained even when the backend is stateless.

**Why doesn't the example declare the filter as a @Bean?** With Spring Boot, a Servlet Filter bean may be automatically registered into the Servlet container; if also added via **http.addFilterBefore(...)**, the filter risks running twice at two layers. Instantiating the filter inside the SecurityFilterChain configuration as shown keeps the processing scope explicit. If a system must declare a separate filter bean, proactively control Servlet registration instead of ignoring this risk.

### 6.1. Running the Demo

From the project directory:

~~~bash
mvn test
mvn spring-boot:run
~~~

The commands below **only demonstrate how the backend processes the header**, not confirmation that a trusted gateway exists:

~~~bash
# Missing identity -> blocked.
curl -i http://localhost:8080/api/documents

# Header matches alice, internal user has ROLE_READER -> 200.
curl -i http://localhost:8080/api/documents \
  -H "X-Verified-User: alice"

# Header matches bob but lacks ROLE_READER -> 403.
curl -i http://localhost:8080/api/documents \
  -H "X-Verified-User: bob"
~~~

On a valid response, the controller body looks like:

~~~json
{"documents":["DOC-001"],"user":"alice"}
~~~

JSON property ordering is not a fixed contract. The example intentionally configures AuthenticationEntryPoint to return **401** on unauthenticated requests. **Crucially:** if a direct curl attaches header alice and receives **200**, that result proves the filter trusts the header value; it **does not prove the client was SSO-authenticated**. In production, direct requests to the backend must be **blocked at the infrastructure layer**, and requests through the gateway must be authenticated and header-sanitized before forwarding.

## 7. Unit/Integration Testing in Spring Security

Create **src/test/java/demo/preauth/HeaderPreauthApplicationTests.java**:

~~~java
package demo.preauth;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class HeaderPreauthApplicationTests {

    @Autowired
    MockMvc mvc;

    @Test
    void missingHeaderDoesNotAuthenticate() throws Exception {
        mvc.perform(get("/api/documents"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void trustedHeaderForReaderPassesApplicationRule()
            throws Exception {
        mvc.perform(get("/api/documents")
                        .header("X-Verified-User", "alice"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.user").value("alice"))
                .andExpect(jsonPath("$.documents[0]").value("DOC-001"));
    }

    @Test
    void userWithoutRoleIsForbidden() throws Exception {
        mvc.perform(get("/api/documents")
                        .header("X-Verified-User", "bob"))
                .andExpect(status().isForbidden());
    }

    @Test
    void unrelatedHeaderIsNotAcceptedAsPrincipal()
            throws Exception {
        mvc.perform(get("/api/documents")
                        .header("X-Forwarded-User", "alice"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void unrelatedRouteIsDeniedEvenWithValidPrincipal()
            throws Exception {
        mvc.perform(get("/api/other")
                        .header("X-Verified-User", "alice"))
                .andExpect(status().isForbidden());
    }
}
~~~

Run:

~~~bash
mvn test
~~~

These tests confirm **header-to-Authentication mapping**, the 401/403/200 rules, and the **deny-all fallback**. They are **not end-to-end anti-spoofing proof**: MockMvc calls the Spring application directly without a real gateway sanitizing headers. The "trustedHeaderForReaderPassesApplicationRule" test intentionally illustrates that once a request carrying header alice **reaches the Servlet filter**, the backend accepts it as pre-authentication.

**Running only these unit tests and claiming the system prevents spoofed headers would be a false conclusion.** The most critical testing belongs in the next section.

## 8. Testing Header Spoofing Prevention at the Right Boundary

Mandatory test plan on a staging environment matching production architecture:

~~~text
External client -> Public Gateway -> Internal Backend
                                    (no direct public route)
~~~

| Test case | Expected behavior |
| --- | --- |
| **Unauthenticated** client sends request without header | Gateway denies/redirects per contract; creates no authenticated user |
| Unauthenticated client **self-attaches X-Verified-User: alice** | Gateway rejects request or strips header; backend never sees request as alice |
| Client logged in genuinely as **bob**, also sends **X-Verified-User: alice** | Gateway strips self-declared header and attaches real identity bob; READER-only endpoint still returns 403 |
| Client logged in genuinely as **alice**, sends another fake header | Gateway normalizes identity to alice; app applies alice's true permissions |
| Client tries calling **backend IP/port directly** | Blocked by network/firewall/TLS before reaching RequestHeaderAuthenticationFilter |
| Client sends **multiple headers with same name** or case variants | Gateway and backend handle consistently; client-controlled identity cannot be chosen |
| Header has blank value, excessive length, or odd characters | Rejected or fails closed per contract; never yields a privileged default user |
| Gateway loses IdP connection or token check fails | Request receives no trusted identity; service never turns anonymous into a valid account |
| User is locked/revoked between requests | Backend/IdP updates permissions per business rules; old privileges do not persist indefinitely |
| State-changing request via browser holding SSO cookie | CSRF policy enforced cleanly at gateway/backend; never infer safety from backend stateless sessions |

**Testing principle:** verify the **actual identity received by the backend**, authorities, and returned data; do not check status codes alone. With bob impersonating alice, the test must prove **bob never receives alice's data**.

### 8.1. Example Test Action at the Gateway

Call the **public gateway address** (never call the backend directly) while the client is unauthenticated:

~~~bash
curl -i https://gateway.example.test/api/documents \
  -H "X-Verified-User: alice"
~~~

**Expectation:** the gateway rejects or routes into the proper authentication flow, never granting alice's permissions. When testing as user bob logged in through the gateway, attach the extra alice header and confirm the backend still processes **bob** or rejects per policy; it must never switch to alice.

This is an **architectural test pattern**, with no single HTTP code shared by all gateways (401, 302, or 403 depending on contract). **example.test** is an illustrative domain, not a live endpoint. Test against staging infrastructure owned by your organization; never test third-party systems without authorization.

### 8.2. Header Normalization Scenarios to Inspect

HTTP header names are case-insensitive in principle, while proxy/CGI-style middleware may convert header names into environment variables or alternate internal forms. Therefore inspect all of the following:

- Equivalent header names differing in uppercase/lowercase.
- **-** and **_** characters in names that middleware might normalize differently.
- Multiple occurrences of the same header, multi-value lists, and length limits.
- Whether CDN, WAF, Ingress Controller, mesh/sidecars, and backend enforce the same policy for stripping/setting identity headers.
- Hop-by-hop headers, request smuggling, and related path mutations when infrastructure mixes distinct parsers.

Simply **deleting a header name in Java code** after RequestHeaderAuthenticationFilter has read it is **too late**. Sanitization must occur **before** backend header-based authentication, ideally at a trusted gateway combined with network access controls preventing client bypass.

## 9. Gateway Role: Trust Contract to Document Explicitly

A pre-authentication architecture must document at minimum:

**Inputs:** the gateway accepts login session cookies, OIDC access tokens, client certificates, or the chosen authentication method. It must validate issuer/audience/signature/expiry and required policies if JWT; validate handshake, certificate, and identity mapping if mTLS; never trust a caller-created X-User.

**Outputs:** a canonical identity header, e.g. **X-Verified-User**, carrying the verified subject ID. Only the gateway may create it. The backend should not infer roles from caller-provided display names or emails.

**Transport:** TLS/mTLS or appropriate private network policy, gateway identity, and an allowlist of truly trusted sources. Never treat self-sent **X-Forwarded-For**, **X-Real-IP**, or Forwarded headers as proof a request came from the gateway; these headers also require authentication/sanitization at the trust boundary.

**Error handling:** when the IdP times out, verification fails, user is locked, header is invalid, or session is missing, **fail closed**; never fall back to a privileged user, and never skip auth just to boost availability.

**Authorization:** the backend verifies roles/permissions and per-resource access. In multi-tenant systems, identity should bind tenant/issuer under a strict security contract; prevent two tenants with the same username from merging into one.

**Lifecycle management:** gateway session TTL, refresh/revocation, permission changes, logout, clock skew, key/certificate management, and auditing. If the backend caches UserDetails, specify how quickly privilege revocation takes effect.

**Operations:** metrics for requests lacking the canonical header past the gateway, authorization denial distributions, duplicate header occurrences, and misrouted requests hitting the backend; alert on anomalies. Log only necessary data with proper access control.

## 10. CSRF, Sessions, CORS, and Other Boundaries

### 10.1. CSRF Does Not Disappear Just Because the Backend Trusts a Header

A common flawed argument:

> The backend is stateless and uses no Java session cookies, so disabling CSRF is safe.

That holds only after verifying **every authentication method** and how browsers attach credentials automatically. If the **gateway** uses SSO session cookies, browsers can automatically send cookies on requests through the gateway. The gateway validates the cookie and sets X-Verified-User, making the backend see an authenticated request even though the user never consented to the action. Thus, for state-changing operations like POST/PUT/DELETE, you need CSRF defenses or an authentication design that browsers cannot send automatically in attack contexts.

The sample only has GET to isolate pre-auth mechanics; CSRF remains at its default. Never apply **csrf.disable()** globally merely because RequestHeaderAuthenticationFilter is present.

### 10.2. CORS Is Not an Anti-Spoofing Mechanism

CORS controls whether JavaScript from another origin can read responses and send preflighted requests. It **does not block curl/Postman/backend clients from setting headers themselves**. A backend exposed directly to the Internet can still be impersonated via X-Verified-User even when CORS permits only a single trusted origin.

### 10.3. Sessions and Identity Switching

When the backend both uses sessions and reads identity headers, define clearly which request serves as the primary identity source. If the same HttpSession is reused for requests of a different identity, stale session/context state can grant wrong permissions. You can use the pre-auth filter's principal-change check alongside proper invalidation, yet **never treat that as a substitute for gateway sanitization**. A stateless model for APIs can be easier to reason about if every request's identity comes from the gateway and infrastructure guarantees assertion authenticity.

### 10.4. Relationship to OAuth2 Resource Server

**Resource Server JWT** typically reads **Authorization: Bearer ...**, verifies signature, issuer, expiration/audience itself, and maps scopes/authorities. This fits when the API must validate client-presented tokens directly.

**RequestHeaderAuthenticationFilter** reads an **unsigned** header containing a username and **trusts an external gateway** to have authenticated it. Both models can be safe when implemented with proper trust boundaries, but they are not equivalent: Resource Server verifies tokens at the API, whereas header pre-auth depends on gateway + network path guarantees.

| Scenario | Option to evaluate |
| --- | --- |
| Public API receiving OAuth2 Bearer tokens from many clients | Resource Server with JWT/opaque validation |
| Legacy backend that can run only behind a tightly managed SSO gateway | Pre-auth via RequestHeaderAuthenticationFilter, with complete trust boundary |
| Browser web app logging in directly via OIDC and holding sessions | oauth2Login() / OAuth2 Client; identity headers not needed by default |
| Gateway validates JWT, yet backend still wants to verify tokens itself | Token relay to Resource Server or appropriate zero-trust solution |
| Multiple backend access paths without uniform policy enforcement | **Do not use plain header pre-auth** as login proof |

## 11. Common Errors and Diagnostics

| Symptom | Likely cause | Check / fix |
| --- | --- | --- |
| Manually adding X-Verified-User grants system access | Backend reachable directly or gateway forwards client header | Close direct path; gateway strips and recreates header post-auth |
| Request lacks header yet filter does not fail immediately | setExceptionIfHeaderMissing(false) was set | Verify endpoints require authenticated/role; must fail closed |
| Valid user still gets 401 | Gateway omits header, wrong header name, user missing from UserDetailsService | Trace across gateway/app via request ID; check contract |
| User has principal yet gets 403 | Missing authority or insufficient resource rights | Check ROLE_/SCOPE_ and service-layer permissions |
| MockMvc tests pass yet production is spoofable | MockMvc bypasses gateway/network boundary | Write black-box integration tests through gateway; probe direct backend externally |
| X-Forwarded-User unexpectedly accepted | Another proxy/filter maps that header to principal | Audit all proxy/filter layers and canonical contract |
| Duplicate headers yield unexpected user | Duplicate/normalization handled differently across hops | Reject/normalize at gateway before issuing assertion |
| User B's request uses A's permissions | Old session/context, stale principal, or identity switching | Inspect stateful context, principal-change policy, and multi-request tests |
| Client-sent ADMIN role header works | App trusts client-declared permissions | Drop untrusted permission sources; load roles from trusted store |
| CSRF occurs despite stateless backend | Gateway uses browser cookies sent automatically | Keep appropriate CSRF controls at the cookie-bearing boundary |
| Unauthenticated client calls API inside internal network | Overly broad network trust or gateway bypass | Restrict ingress, use mTLS/service identity, and audit |
| Login errors or stale access after IdP timeout | Gateway fails open or holds stale assertions | Fail closed; check TTL, session revocation, and outage handling |

**Short debug workflow:** confirm whether the request went through the **right gateway** → did authentication succeed at the gateway → was the header created by the gateway post-sanitization or sent by the client → which principal did the backend filter read → which UserDetails/authorities did the provider load → which authorization rule decided 401/403 → were object-level permissions and CSRF checked. Never widen permissions or add **permitAll()** just to hide symptoms.

## 12. Pre-Production Review Checklist

- [ ] Pre-auth model was chosen deliberately over direct Resource Server/JWT validation.
- [ ] Backend cannot be accessed directly from untrusted networks, including secondary ingress paths.
- [ ] Gateway performs genuine authentication and **strips all client-supplied identity headers** before issuing a fresh assertion.
- [ ] Gateway → backend hop has appropriate transport protection and gateway identification.
- [ ] Canonical header name and duplicate/blank/encoding/normalization rules are defined.
- [ ] Neither forwarded address headers nor "secret" header names are used as authentication proof.
- [ ] UserDetails/authorities load from a trusted source under least privilege.
- [ ] Black-box gateway tests cover spoofing, bypass, user-switching, and permission revocation.
- [ ] Critical routes enforce role-based **and** resource-level authorization.
- [ ] CSRF protections are evaluated alongside gateway cookies/sessions; never disabled mechanically.
- [ ] Logging, tracing, and alerting never expose tokens/cookies or unnecessary personal data.
- [ ] Ownership, threat model, rollback plan, and post-rollout monitoring are in place.

## 13. Self-Check Questions

1. Does **RequestHeaderAuthenticationFilter** verify JWT signatures or user SSO sessions itself? **No.** It consumes an identity header already authenticated by a trusted component.
2. If callers can call the backend directly with **X-Verified-User: alice**, can UserDetailsService stop impersonation just because alice exists? **No.** The flaw is the untrusted header source.
3. What must happen at the gateway before attaching the identity header? **Authenticate the caller, strip all untrusted incoming identity headers, and emit a canonical assertion.**
4. Why does **hasRole("READER")** still matter? Because authenticating identity does not mean permission to view every endpoint or dataset.
5. Does strict CORS alone stop curl from sending identity headers? **No.** CORS is primarily a browser mechanism.
6. Is a stateless backend behind an SSO-cookie gateway guaranteed not to need CSRF? **No.** Browser auto-sent credentials at the gateway and across the whole system must be analyzed.
7. What does a passing MockMvc test with header alice returning 200 prove? **It proves the backend filter/provider/authorization work**, not that the gateway stops spoofing.
8. What mechanism should a public API directly receiving Bearer tokens consider? **OAuth2 Resource Server** validating tokens itself, rather than trusting client username headers.

**Conclusion:** **RequestHeaderAuthenticationFilter is trustworthy only when the identity header comes from an authenticated component over a protected path**. To prevent spoofing, ensure the gateway authenticates and sanitizes headers, no direct backend bypass exists, the backend loads trusted authorities, and authorization/CSRF are enforced in the right places. Renaming headers, enabling CORS, or merely checking user existence **does not create a trust boundary**.
