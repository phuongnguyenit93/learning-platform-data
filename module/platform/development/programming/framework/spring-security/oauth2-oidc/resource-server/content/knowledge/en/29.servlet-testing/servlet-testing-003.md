# opaqueToken() and Simulating an Introspected Token Principal

When testing a **Spring Security OAuth 2.0 Resource Server using opaque access tokens**, we often want to verify controllers, HTTP authorization, and how the application uses the principal returned by introspection. Not every test needs to call a real Authorization Server (AS) or send a real access token over the network. Spring Security Test provides the **opaqueToken()** request post-processor to construct an authentication matching the shape of an opaque token authentication result.

The key is understanding the tool's scope:

- **opaqueToken()** enables fast testing of processing **after authentication succeeds**: authorities, principal attributes, controller arguments, method security, and HTTP authorization.
- It creates a mock authentication in the test request; **it does not call OpaqueTokenIntrospector**, does not send a Bearer token to the AS, does not verify whether the token is active, and does not check client credentials/the introspection endpoint.
- To test the full Bearer filter and introspection integration, send an **Authorization: Bearer ...** header through MockMvc and use a test/stub OpaqueTokenIntrospector or a real test AS.

These two types of tests complement each other. A test using opaqueToken() does not prove introspection works; an introspection integration test does not necessarily have to repeat every controller/authorization test. Choose the right tool for the question you need to answer.

## 1. How does opaque token authentication work?

An opaque access token is typically a string that carries no readable claims and cannot have its signature verified at the Resource Server. When a client calls the API:

~~~mermaid
sequenceDiagram
    participant C as OAuth Client
    participant API as Spring Resource Server
    participant AS as Authorization Server
    C->>API: Authorization: Bearer opaque-token
    API->>API: BearerTokenAuthenticationFilter
    API->>AS: Token introspection (RFC 7662)
    AS-->>API: active + claims + scope
    API->>API: OpaqueTokenAuthenticationProvider
    API->>API: Build BearerTokenAuthentication
    API->>API: Authorization rules
    API-->>C: Response
~~~

In the Servlet stack, the main components are:

| Component | Responsibility |
|---|---|
| **BearerTokenAuthenticationFilter** | Reads the Bearer credential from the HTTP request and initiates the authentication request |
| **AuthenticationManager / OpaqueTokenAuthenticationProvider** | Coordinates opaque token authentication |
| **OpaqueTokenIntrospector** | Sends the token to the AS introspection endpoint and returns the authenticated principal |
| **OAuth2AuthenticatedPrincipal** | Represents the subject, attributes, and authorities returned by the introspector |
| **BearerTokenAuthentication** | Successful authentication for an opaque bearer token |
| **HTTP/method authorization** | Checks authorities after authentication |

The AS typically returns metadata according to RFC 7662, for example:

~~~json
{
  "active": true,
  "sub": "alice",
  "scope": "orders.read orders.write",
  "client_id": "orders-web",
  "aud": ["orders-api"],
  "tenant_id": "tenant-a"
}
~~~

When introspection succeeds, Spring Security creates a principal from the attributes and maps scopes to authorities. Under the common default configuration, scope **orders.read** is converted to authority **SCOPE_orders.read**. If the token is inactive, the introspector does not create a successful authenticated principal.

## 2. What is opaqueToken()?

**opaqueToken()** is a **MockMvc request post-processor** in the **spring-security-test** module. It allows a test to attach an authenticated opaque-token-style authentication to a request so the Security filter chain processes authorization and the controller as if the principal had been verified by introspection.

Common static import:

~~~java
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.opaqueToken;
~~~

The dependency must be on the same version line as Spring Security in the application:

~~~groovy
dependencies {
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

With Maven:

~~~xml
<dependency>
    <groupId>org.springframework.security</groupId>
    <artifactId>spring-security-test</artifactId>
    <scope>test</scope>
</dependency>
~~~

If the project uses Spring Boot dependency management, let the BOM manage the appropriate version; avoid pinning a `spring-security-test` version different from the runtime version.

### 2.1. Simple test

~~~java
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.opaqueToken;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@Test
void requestWithMockOpaqueTokenIsAuthenticated() throws Exception {
    mockMvc.perform(get("/api/orders").with(opaqueToken()))
        .andExpect(status().isOk());
}
~~~

The example assumes the endpoint accepts the post-processor's default authority or has a rule requiring only authenticated access. In real tests, configure the **specific authority the endpoint requires** so the test accurately reflects policy rather than relying on the helper's default authorities.

### 2.2. Pre-built authentication

When using opaqueToken(), the test does not need to supply a token string formatted like a real opaque token. The post-processor prepares the security context for the request with a principal/Authentication simulating an opaque token. That keeps tests independent of an AS and avoids storing real tokens in fixtures.

The helper's defaults are designed to provide a basic principal and sample read authority. Default details can change across Spring Security versions; **do not rely on defaults in business tests**. Set attributes and authorities explicitly so the test documents the conditions it requires.

### 2.3. It does not run introspection

This is the boundary to remember:

~~~text
mockMvc.perform(get(...).with(opaqueToken()))
    |
    +-- Create mock Authentication
    +-- SecurityContext has Authentication
    +-- Authorization rules
    +-- Controller / method security
    |
    X Does not call OpaqueTokenIntrospector
    X Does not call token introspection endpoint
    X Does not check active=true
    X Does not check Resource Server client_id/secret
~~~

Therefore, this test cannot detect introspection URL errors, Basic authentication errors toward the AS, timeouts, JSON mapping issues, or introspection caching bugs. Those parts require other tests.

## 3. Simulating principal attributes and authorities

An opaque principal is typically an **OAuth2AuthenticatedPrincipal**. It contains:

- Principal name, usually based on the **sub** claim per the introspector.
- Attributes returned by the AS, e.g., **sub**, **client_id**, **aud**, **tenant_id**.
- Authorities, usually mapped from **scope** or custom configuration.

### 3.1. Customizing attributes

opaqueToken() allows setting the principal's attributes:

~~~java
mockMvc.perform(get("/api/orders")
        .with(opaqueToken().attributes(attributes -> {
            attributes.put("sub", "alice");
            attributes.put("tenant_id", "tenant-a");
            attributes.put("client_id", "orders-web");
        })))
    .andExpect(status().isOk());
~~~

Here `sub` is the subject and `tenant_id` is a custom claim per the system's contract. These values are only **test fixtures**. Putting `tenant_id=tenant-a` into the map does not prove the real AS issues that claim or that a real token grants access to tenant A.

### 3.2. Customizing authorities

To test scope-based authorization, set the exact authority the application checks:

~~~java
import org.springframework.security.core.authority.SimpleGrantedAuthority;

mockMvc.perform(get("/api/orders")
        .with(opaqueToken()
            .authorities(
                new SimpleGrantedAuthority("SCOPE_orders.read"))))
    .andExpect(status().isOk());
~~~

If the endpoint requires **hasAuthority("SCOPE_orders.read")**, the test needs this exact authority. The following strings are not equivalent:

| Authority | Satisfies hasAuthority("SCOPE_orders.read")? |
|---|---|
| **SCOPE_orders.read** | Yes |
| **orders.read** | No |
| **ROLE_orders.read** | No |
| **SCOPE_orders.write** | No |
| **ROLE_ADMIN** | No, unless another rule permits it |

**hasRole("ADMIN")** looks for **ROLE_ADMIN** by default; scopes and roles use different prefixes. Do not change production authorization rules just because a test uses the wrong authority.

### 3.3. Setting attributes and authorities together

A test often needs a principal with the right tenant and scope:

~~~java
mockMvc.perform(get("/api/orders")
        .with(opaqueToken()
            .attributes(attributes -> {
                attributes.put("sub", "alice");
                attributes.put("tenant_id", "tenant-a");
                attributes.put("client_id", "orders-web");
            })
            .authorities(
                new SimpleGrantedAuthority("SCOPE_orders.read"))))
    .andExpect(status().isOk());
~~~

Separate the two concepts:

- **Attributes** describe principal/token metadata.
- **Authorities** are the permissions checked by the Security authorization engine.

Putting a `scope` claim into attributes does not necessarily cause the test helper to map authorities from that claim automatically. When using opaqueToken(), set authorities explicitly. If you want to test scope-to-authority mapping of the production introspector/provider, use an integration test through the Bearer filter with a real or stub introspector.

### 3.4. Testing the principal name

A controller can retrieve the principal:

~~~java
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class CurrentPrincipalController {

    @GetMapping("/api/me")
    String me(@AuthenticationPrincipal OAuth2AuthenticatedPrincipal principal) {
        return principal.getAttribute("sub");
    }
}
~~~

Test:

~~~java
mockMvc.perform(get("/api/me")
        .with(opaqueToken().attributes(attributes ->
            attributes.put("sub", "alice"))))
    .andExpect(status().isOk())
    .andExpect(content().string("alice"));
~~~

For opaque tokens, the principal has the general type **OAuth2AuthenticatedPrincipal**; do not cast it to **Jwt**. A controller taking **@AuthenticationPrincipal Jwt** fits a JWT Resource Server, not an opaque principal.

### 3.5. Reading BearerTokenAuthentication

If the controller/service needs to inspect authentication metadata:

~~~java
import org.springframework.security.oauth2.server.resource.authentication
    .BearerTokenAuthentication;

@GetMapping("/api/token-info")
Map<String, Object> tokenInfo(BearerTokenAuthentication authentication) {
    return authentication.getTokenAttributes();
}
~~~

In production, avoid returning all token attributes to the client if there are internal/PII claims. A test can verify a required field:

~~~java
mockMvc.perform(get("/api/token-info")
        .with(opaqueToken().attributes(attributes -> {
            attributes.put("sub", "alice");
            attributes.put("tenant_id", "tenant-a");
        })))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$.tenant_id").value("tenant-a"));
~~~

BearerTokenAuthentication holds the constructed token attributes and principal; the helper does not prove those attributes came from a real AS.

## 4. Resource Server configuration in the application under test

A Servlet security chain using opaque tokens can be configured as:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class ApiSecurityConfiguration {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        return http
            .securityMatcher("/api/**")
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .requestMatchers(HttpMethod.POST, "/api/orders")
                    .hasAuthority("SCOPE_orders.write")
                .anyRequest().denyAll())
            .oauth2ResourceServer(oauth2 ->
                oauth2.opaqueToken(Customizer.withDefaults()))
            .build();
    }
}
~~~

With Spring Boot, the introspection URI and client credentials can be supplied via:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: https://identity.example.com/oauth2/introspect
          client-id: orders-resource-server
          client-secret: INTROSPECTION_CLIENT_SECRET_FROM_SECRET_STORE
~~~

This is production-style configuration for Spring to create the introspector. Tests using opaqueToken() do not need a real endpoint because authentication is pre-built. If a test needs to go through the introspector, you must supply a dedicated test introspector or test AS.

### 4.1. CSRF in tests

The example above is a stateless API using a Bearer header, assuming credentials are not automatically sent by a browser like cookies. If the application uses session cookies or has browser authentication in the same chain, do not mechanically copy disabling CSRF. When testing POST/PUT/DELETE with session-based security, use the appropriate CSRF test post-processor and preserve production policy.

### 4.2. Ensuring tests actually load SecurityFilterChain

MockMvc must run with the Spring Security filter chain to test authorization. In Spring Boot, **@AutoConfigureMockMvc** with the application context usually configures the filter automatically. If building MockMvc manually, integrate Spring Security with the corresponding configuration (e.g., **springSecurity()** when using `webAppContextSetup`).

If a test calls the controller directly or builds MockMvc without security filters, a 200 result does not prove `opaqueToken()`/authorization rules are working.

## 5. Complete example: controller, authority, and principal

Suppose the API has an endpoint returning the list of orders for the tenant in the principal:

~~~java
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class OrdersController {

    @GetMapping("/api/orders")
    @PreAuthorize("hasAuthority('SCOPE_orders.read')")
    String list(@AuthenticationPrincipal
                OAuth2AuthenticatedPrincipal principal) {
        String subject = principal.getAttribute("sub");
        String tenant = principal.getAttribute("tenant_id");
        return subject + ":" + tenant;
    }
}
~~~

If using method security, enable:

~~~java
@Configuration
@EnableMethodSecurity
class MethodSecurityConfiguration {
}
~~~

Test:

~~~java
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.opaqueToken;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class OrdersControllerTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void returnsPrincipalAttributesForAuthorizedOpaquePrincipal()
            throws Exception {

        mockMvc.perform(get("/api/orders")
                .with(opaqueToken()
                    .attributes(attributes -> {
                        attributes.put("sub", "alice");
                        attributes.put("tenant_id", "tenant-a");
                    })
                    .authorities(
                        new SimpleGrantedAuthority("SCOPE_orders.read"))))
            .andExpect(status().isOk())
            .andExpect(content().string("alice:tenant-a"));
    }
}
~~~

The illustrative example focuses on the controller/security contract. A real project needs MockMvc configuration, component scanning, method security, and dependencies matching the application. If the Spring context initializes a production introspector requiring properties, provide test properties or replace the introspector in the test context; the request post-processor will not call it.

## 6. Testing 401, 403, and least privilege

Three states should be separated:

- **401 Unauthorized:** request lacks valid Authentication (e.g., no Bearer token or token not authenticated).
- **403 Forbidden:** Authentication exists, but lacks the required authority or is denied by policy.
- **2xx:** Authentication and authorization are sufficient for the request (it may still be rejected by business logic).

### 6.1. Missing token: 401

~~~java
@Test
void missingBearerTokenIsUnauthorized() throws Exception {
    mockMvc.perform(get("/api/orders"))
        .andExpect(status().isUnauthorized());
}
~~~

This test requires the security chain protecting the endpoint and the Resource Server entry point to be configured. It does not use `opaqueToken()` because it tests the **no Authentication** case.

### 6.2. Principal present but missing scope: 403

~~~java
@Test
void authenticatedPrincipalWithoutReadScopeIsForbidden()
        throws Exception {
    mockMvc.perform(get("/api/orders")
            .with(opaqueToken()
                .attributes(attributes ->
                    attributes.put("sub", "alice"))
                .authorities(
                    new SimpleGrantedAuthority("SCOPE_profile.read"))))
        .andExpect(status().isForbidden());
}
~~~

This is a classic use case for `opaqueToken()`: the principal is considered authenticated, but lacks `SCOPE_orders.read`.

### 6.3. Having the right scope does not mean access to every object

If a user has `SCOPE_orders.read` but accesses another tenant's orders, service/domain policy must still deny it. You can test with a tenant principal:

~~~java
mockMvc.perform(get("/api/tenants/tenant-b/orders")
        .with(opaqueToken()
            .attributes(attributes -> {
                attributes.put("sub", "alice");
                attributes.put("tenant_id", "tenant-a");
            })
            .authorities(
                new SimpleGrantedAuthority("SCOPE_orders.read"))))
    .andExpect(status().isForbidden());
~~~

The result depends on the actual tenant authorization implementation. The test goal is to ensure the tenant claim is enforced by policy, not merely because the test helper added an attribute. If tenant logic lives in the service, mock the repository/service to verify the service receives the right verified principal and tenant; add database integration tests when needed to prove queries filter by tenant.

### 6.4. Do not use authenticated() instead of scopes

A test might pass because the rule only requires:

~~~java
.anyRequest().authenticated()
~~~

while the production endpoint needs:

~~~java
.requestMatchers(GET, "/api/orders/**")
    .hasAuthority("SCOPE_orders.read")
~~~

Test the exact rule the endpoint uses. If tests only use a default principal and status 200, you may not have proved scope mapping or least privilege.

## 7. Comparing opaqueToken() with @WithMockUser

**@WithMockUser** creates a generic user authentication (usually `UsernamePasswordAuthenticationToken`) for tests. **opaqueToken()** simulates OAuth2 opaque Resource Server authentication.

| Aspect | @WithMockUser | opaqueToken() |
|---|---|---|
| Authentication type | Username/password-style mock user | Bearer/opaque-token authentication |
| Principal | UserDetails-like principal | OAuth2AuthenticatedPrincipal |
| Attributes sub, tenant_id, client_id | Not available per opaque-token contract | Customizable |
| Authorities | Can declare roles/authorities | Can declare scope authorities |
| Suitable for testing | Controllers/security needing only generic user/role | Resource Server opaque-token authorization and principal |
| Calls introspector | No | No |
| Checks token active | No | No |

If code has:

~~~java
@AuthenticationPrincipal OAuth2AuthenticatedPrincipal principal
~~~

then `opaqueToken()` reflects the matching principal type better than `@WithMockUser`. If an endpoint only uses `hasRole("ADMIN")` and does not care about Authentication type, both may work, though an opaque token test still describes the API's credential type more accurately.

Do not replace all tests with `@WithMockUser` just for convenience when production is an OAuth2 Resource Server. Doing so can miss bugs when controllers/services expect `OAuth2AuthenticatedPrincipal` or `BearerTokenAuthentication`.

## 8. Distinguishing mock principal from real introspection tests

This is the most important boundary when choosing tools.

### 8.1. Test A: using opaqueToken() to test post-authentication behavior

~~~text
MockMvc request
  .with(opaqueToken().attributes(...).authorities(...))
          |
          v
Mock Authentication / SecurityContext
          |
          v
Authorization + Controller + Method Security
~~~

Suitable for testing:

- Which scope a URL requires.
- How principal attributes are read by controllers.
- Whether method security blocks properly.
- Whether tenant/owner policy uses the principal properly.
- HTTP 401/403/2xx based on the Authentication fixture.

Not suitable for testing:

- How the Bearer header is parsed.
- Whether `OpaqueTokenIntrospector` receives the right token.
- Whether the AS returns `active=true`.
- How scopes in the introspection response map to authorities.
- Client authentication, TLS, timeouts, error mapping, or caching.

### 8.2. Test B: sending a Bearer header and stubbing the introspector

To test filter/provider/introspector wiring, send the token via the HTTP header:

~~~http
GET /api/orders HTTP/1.1
Authorization: Bearer test-opaque-token
~~~

In the test context, provide a stub `OpaqueTokenIntrospector` returning a principal:

~~~java
import java.util.List;
import java.util.Map;

import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.core.DefaultOAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.server.resource.introspection
    .BadOpaqueTokenException;
import org.springframework.security.oauth2.server.resource.introspection
    .OpaqueTokenIntrospector;

final class StubOpaqueTokenIntrospector
        implements OpaqueTokenIntrospector {

    @Override
    public OAuth2AuthenticatedPrincipal introspect(String token) {
        if (!"test-opaque-token".equals(token)) {
            throw new BadOpaqueTokenException("Unknown test token");
        }

        return new DefaultOAuth2AuthenticatedPrincipal(
            "alice",
            Map.of(
                "sub", "alice",
                "tenant_id", "tenant-a",
                "scope", "orders.read"
            ),
            List.of(
                new SimpleGrantedAuthority("SCOPE_orders.read")
            )
        );
    }
}
~~~

The stub only accepts a specific test token and returns a test-defined principal; it does not contact an AS. You can inject the stub using `@TestConfiguration`/test beans or a bean override mechanism matching your Spring Boot version.

Test:

~~~java
mockMvc.perform(get("/api/orders")
        .header(HttpHeaders.AUTHORIZATION,
            "Bearer test-opaque-token"))
    .andExpect(status().isOk());
~~~

The request passes through the Bearer authentication filter and calls the stub introspector. This tests **wiring and mapping through the provider**, though it still does not test an HTTP request to a real AS.

### 8.3. Test C: mocked introspection endpoint over HTTP

An integration test can run a mock HTTP server (e.g., MockWebServer/WireMock) as the introspection endpoint:

1. Configure `introspection-uri` pointing to the mock server.
2. Send `Authorization: Bearer opaque-test-token` to the API via MockMvc.
3. Mock server receives `POST /introspect`.
4. Mock server returns JSON `active=true`, `sub`, `scope`, `aud`.
5. Verify the API creates Authentication and returns the response per policy.
6. Return `active=false` or a server error in another test and verify the request is rejected.

This is a good test for verifying the HTTP introspection client, form request, client authentication, response parsing, and error mapping. It is still not testing against a real production issuer; rather, it allows deterministic response control.

### 8.4. Test D: real AS in an integration environment

Some projects need contract tests with a real AS in a staging/identity sandbox environment:

- Obtain a token from a managed test flow.
- Send the Bearer token through the API.
- Verify audience/scope/active.
- Revoke the token and retry.
- Measure cache/propagation.

Do not put production access tokens/refresh tokens in test source, CI logs, or fixture repositories. Prefer test credentials/tenants, post-test cleanup, and CI secret injection.

## 9. Testing introspection scope-to-authority mapping

For opaque tokens, the provider normally uses `OpaqueTokenIntrospector` to return the principal and authorities. If the AS returns:

~~~json
{
  "active": true,
  "sub": "alice",
  "scope": "orders.read orders.write"
}
~~~

the application normally expects:

~~~text
SCOPE_orders.read
SCOPE_orders.write
~~~

If a custom introspector or authority converter changes the mapping, test the exact real mapping.

### 9.1. Checking the authority converter via the introspector

The post-processor test:

~~~java
.with(opaqueToken().authorities(
    new SimpleGrantedAuthority("SCOPE_orders.read")))
~~~

only attaches the specified authority. It **does not run the production converter**. To test the converter, invoke the converter directly with a principal fixture or send a Bearer header through `OpaqueTokenAuthenticationProvider` configured with a test introspector.

### 9.2. Do not grant permissions from untrusted claims

If the introspection response contains:

~~~json
{
  "active": true,
  "sub": "alice",
  "scope": "orders.read",
  "admin": true
}
~~~

then `admin=true` does not automatically become `ROLE_ADMIN`. Only map that claim if the issuer contract defines its meaning, the audience/resource is right, and the application has an explicit policy. In `opaqueToken()` tests, adding `ROLE_ADMIN` directly to authorities can test the admin branch, but does not prove the production converter only grants permissions when the AS has verified the corresponding claim.

### 9.3. Distinguishing missing scope from inactive introspection

| Introspection result | Authentication | Authorization |
|---|---|---|
active=false | Fails | Does not reach permission rules |
active=true, missing read scope | Succeeds | GET read gets 403 |
active=true, has read scope | Succeeds | Can pass scope check |
active=true, wrong audience | Must be rejected by policy | Must not be allowed solely due to matching scope |
AS timeout/5xx | Cannot be verified | Does not create authenticated principal |

`opaqueToken()` mainly helps test the middle two rows (authenticated principal with/without authorities). Inactive/audience/timeout cases require introspector/integration tests.

## 10. Testing controllers that use principal attributes

### 10.1. Subject and tenant

An endpoint may extract subject and tenant from the principal:

~~~java
@GetMapping("/api/tenant/orders")
String tenantOrders(
        @AuthenticationPrincipal OAuth2AuthenticatedPrincipal principal) {
    String subject = principal.getAttribute("sub");
    String tenant = principal.getAttribute("tenant_id");
    return subject + ":" + tenant;
}
~~~

Test with principal attributes:

~~~java
@Test
void principalAttributesAreAvailableToController() throws Exception {
    mockMvc.perform(get("/api/tenant/orders")
            .with(opaqueToken()
                .attributes(attributes -> {
                    attributes.put("sub", "alice");
                    attributes.put("tenant_id", "tenant-a");
                })
                .authorities(
                    new SimpleGrantedAuthority("SCOPE_orders.read"))))
        .andExpect(status().isOk())
        .andExpect(content().string("alice:tenant-a"));
}
~~~

### 10.2. Principal name and the sub attribute

Do not assume the principal name is always an email or username. An opaque introspector may set the name based on `sub` or a custom principal name attribute. When code needs a stable identity, rely on issuer + subject per contract, not an email display name as primary key.

In tests, if the controller uses `principal.getName()` instead of `getAttribute("sub")`, check the behavior of the principal test fixture in your Spring Security version. You may need to create a custom principal/introspector fixture to set the principal name explicitly rather than assuming all helper defaults match production.

### 10.3. Do not treat tenant from the request as identity

If the endpoint is `/api/tenants/{tenantId}/orders`, the path variable is the data the caller requests to access, not a verified claim. Tests must prove:

- The principal's tenant claim comes from Authentication.
- The requested tenant is compared against the principal/membership.
- Service queries filter by tenant.
- One cannot change the path variable to access another tenant's data.

`opaqueToken().attributes(...)` helps construct the principal tenant in tests; the domain service still needs dedicated allow/deny tests. If tenant logic lives in the service, mock the repository/service to verify the service receives the right verified principal and tenant; add database integration tests when needed to prove queries filter by tenant.

## 11. @WebMvcTest and @SpringBootTest

The two test styles have different scopes.

### 11.1. @WebMvcTest

Suitable when testing the controller and MVC/security slice:

~~~java
@WebMvcTest(OrdersController.class)
class OrdersControllerWebTest {
    @Autowired
    MockMvc mockMvc;
}
~~~

`@WebMvcTest` does not necessarily load every security configuration or custom bean of the application automatically. If the security chain is needed, import the corresponding configuration:

~~~java
@Import(ApiSecurityConfiguration.class)
~~~

If the Resource Server configuration needs an `OpaqueTokenIntrospector`, provide a test bean or use `opaqueToken()` to test post-authentication behavior. When only using the request post-processor, the introspector bean might not be needed for that request, though the application context may still require the bean depending on auto-configuration.

### 11.2. @SpringBootTest + @AutoConfigureMockMvc

Suitable when loading nearly the entire application context:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class OrdersSecurityIntegrationTest {
    @Autowired
    MockMvc mockMvc;
}
~~~

This can test multiple filter chains, method security, service wiring, and exception handlers. In return, the test initializes more components and may need test configuration for datasources, the introspector, or external dependencies.

### 11.3. Prevent tests from calling the AS unintentionally

If a test uses:

~~~java
mockMvc.perform(get("/api/orders").with(opaqueToken()))
~~~

the request post-processor already supplies Authentication; no AS call is needed. However, another test sending:

~~~java
mockMvc.perform(get("/api/orders")
    .header(HttpHeaders.AUTHORIZATION, "Bearer some-token"))
~~~

will go through Resource Server authentication and may call the real introspector if not overridden. To keep CI stable, explicitly provide a test introspector or mock HTTP endpoint; never let tests accidentally call a development/production IdP.

## 12. Common mistakes

| Symptom | Cause | Resolution |
|---|---|---|
opaqueToken() test returns 403 | Helper lacks the authority required by the endpoint | Set exact SCOPE_... via authorities(...) |
Controller receives null principal | Security filters did not run or request not authenticated | Check MockMvc security integration and request post-processor |
@AuthenticationPrincipal Jwt does not bind | Opaque principal is not a Jwt | Use OAuth2AuthenticatedPrincipal or BearerTokenAuthentication |
Test passes but AS receives no request | Using mock post-processor so no introspection occurs | Write integration test with Bearer header and introspector |
Test for active=false does not work | opaqueToken() builds an already-authenticated principal | Test via stub/HTTP introspector returning inactive |
Scope in attributes does not create authority | Post-processor sets attributes and authorities separately | Set authority explicitly; test converter at integration layer |
@WithMockUser passes but production fails | Mock user has different principal/Authentication type | Use opaqueToken() for Resource Server tests |
Tenant test always returns 200 | Test only checks scope, lacks domain rule | Test owner/tenant authorization |
Test calls real IdP in CI | Bearer header goes through production introspector | Inject test stub/mock server |
MockMvc does not return 401 when token missing | Security chain not loaded or rule is permitAll | Check filter chain and matchers |
POST returns 403 in test | CSRF enabled and request lacks token, or missing scope | Distinguish CSRF from authorization; add csrf() when contextually right |
Test relies on helper default scope | Defaults may change or mismatch endpoint | Set authorities explicitly |
Introspection converter is broken yet test passes | opaqueToken() skips converter | Send Bearer token through provider/test introspector |
Custom attributes do not match production | Test maps arbitrary claims not following issuer contract | Use fixtures reflecting AS response schema |

## 13. Matrix for choosing a testing approach

| Question to answer | Appropriate tool |
|---|---|
Does GET /api/orders require SCOPE_orders.read? | opaqueToken().authorities(...) |
Does controller read sub and tenant_id properly? | opaqueToken().attributes(...) |
Does @PreAuthorize block principals missing scope? | opaqueToken() with sufficient/missing authorities |
Does controller receive OAuth2AuthenticatedPrincipal properly? | opaqueToken() |
Does missing Bearer token return 401? | MockMvc request without authentication |
Is Bearer header parsed? | MockMvc with Authorization: Bearer ... |
Does OpaqueTokenIntrospector receive the right token? | Bearer header + stub/mock introspector |
Is scope from response mapped to SCOPE_...? | Test provider/introspector pipeline |
Is active=false rejected? | Stub/HTTP introspection test |
Is audience/issuer contract checked? | Introspector policy integration test |
How are AS timeouts/5xx handled? | Mock HTTP server + Bearer integration test |
Does introspection cache work? | Test cache-aware introspector and clock/TTL |
Are revoked tokens rejected? | Test introspection/denylist after revocation |
Is production AS compatible? | Controlled staging contract test |

## 14. Workflow for writing Servlet tests with opaqueToken()

A concise sequence:

1. **Load Spring Security:** verify MockMvc runs the right SecurityFilterChain.
2. **Select endpoint:** identify the HTTP matcher and required authority.
3. **Build principal:** use `opaqueToken().attributes(...)` for `sub`, tenant, and metadata needed by the controller.
4. **Build authorities:** use `authorities(new SimpleGrantedAuthority("SCOPE_..."))` matching production rules.
5. **Check response:** status/body/controller arguments/method security.
6. **Test negative cases:** missing authentication, missing scope, wrong tenant.
7. **Test introspection separately:** send a Bearer header and inject a stub introspector.
8. **Test provider/AS contract:** mock HTTP introspection responses for active, inactive, malformed, and error cases.
9. **Test cache/revocation separately:** prove TTL/invalidation matches policy if the application caches.

Do not cram everything into a single test. The more focused a test is, the easier it is to pinpoint failures: wrong authorization, wrong principal mapping, or wrong introspection integration.

## 15. Conclusion

~~~text
opaqueToken()
  = mock an already-authenticated opaque-token principal
  = set principal attributes + authorities
  = test MockMvc authorization/controller/method security

opaqueToken()
  != call OpaqueTokenIntrospector
  != send Bearer token to Authorization Server
  != test active/inactive response
  != test introspection credentials, HTTP mapping or cache

REAL INTROSPECTION TEST
  Authorization: Bearer test-token
       |
       v
  BearerTokenAuthenticationFilter
       |
       v
  OpaqueTokenAuthenticationProvider
       |
       v
  OpaqueTokenIntrospector (stub / mock HTTP / test AS)
       |
       v
  Authentication + authorities
       |
       v
  Authorization + Controller
~~~

**opaqueToken()** is a convenient tool for simulating an authenticated opaque token principal in **Servlet MockMvc tests**. Use `attributes` to build `sub`, `tenant_id`, and metadata needed by controllers; use `authorities` to check the exact scopes/roles required by HTTP rules. It is especially useful for testing 403 responses, method security, principal injection, and domain authorization.

However, this helper does not run `OpaqueTokenIntrospector`. When you need to test real tokens sent through the Bearer filter, scope mapping, `active=false`, audience policies, timeouts, or caching, send `Authorization: Bearer ...` and inject a test introspector or mock introspection endpoint. Keeping these two test layers separate accurately proves both **how the application handles the principal** and **how the issuer verifies the token**.

## References

- [Spring Security Reference — Testing OAuth 2.0](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/oauth2.html): MockMvc post-processors for OAuth2 Resource Server, `opaqueToken()`, and principal customization.
- [Spring Security API — SecurityMockMvcRequestPostProcessors](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/test/web/servlet/request/SecurityMockMvcRequestPostProcessors.html): `opaqueToken()` request post-processor.
- [Spring Security Reference — Opaque Token Resource Server](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/opaque-token.html): `OpaqueTokenIntrospector`, provider, and principal.
- [Spring Security API — OpaqueTokenIntrospector](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/introspection/OpaqueTokenIntrospector.html): introspection contract.
- [Spring Security API — OAuth2AuthenticatedPrincipal](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/core/OAuth2AuthenticatedPrincipal.html): principal attributes and authorities.
- [Spring Security API — BearerTokenAuthentication](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/authentication/BearerTokenAuthentication.html): authentication created from an opaque bearer token.
- [Spring Security Reference — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html): `@PreAuthorize` and method authorization.
- [Spring Security Reference — Testing Method Security](https://docs.spring.io/spring-security/reference/servlet/test/method.html): testing method security.
- [Spring Security Reference — MockMvc Setup](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/setup.html): integrating Spring Security filters into MockMvc.
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662): introspection request/response, `active`, and token metadata.
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750): Bearer authentication scheme and error semantics.
