# mockOpaqueToken() and OAuth2AuthenticatedPrincipal Data

In a Spring Security WebFlux Resource Server, when an API receives an **opaque access token**, Spring Security calls a ReactiveOpaqueTokenIntrospector to query the Authorization Server for the token's status and metadata. The introspection result is converted into an Authentication whose principal is of type OAuth2AuthenticatedPrincipal along with GrantedAuthorities.

When writing tests for WebFlux, you do not always need to spin up an Authorization Server or send a real token. **SecurityMockServerConfigurers.mockOpaqueToken()** pre-populates a mock BearerTokenAuthentication and OAuth2AuthenticatedPrincipal in the ServerWebExchange's SecurityContext. This lets tests focus on controllers, principal data, scopes, authorities, and authorization.

This lesson explains:

- How to use mockOpaqueToken() with WebTestClient.
- Default data and how to customize attributes and authorities.
- How to supply a complete OAuth2AuthenticatedPrincipal.
- How controllers and services read the principal during reactive requests.
- Distinguishing Authentication, principal, token attributes, and GrantedAuthority.
- The boundary between mock authorization testing and real introspection testing.
- How to test scopes, tenants, subjects, and missing-data scenarios.

## 1. Opaque Token Authentication in WebFlux

An opaque access token is typically an unstructured string without claims that the Resource Server can decode on its own. The Resource Server sends the token to an introspection endpoint. The Authorization Server returns an active status along with relevant attributes.

~~~mermaid
sequenceDiagram
    participant C as Client
    participant R as WebFlux Resource Server
    participant I as ReactiveOpaqueTokenIntrospector
    participant AS as Authorization Server

    C->>R: Authorization: Bearer opaque-token
    R->>I: introspect(token)
    I->>AS: POST /introspect
    AS-->>I: active=true + attributes
    I-->>R: OAuth2AuthenticatedPrincipal
    R->>R: Create BearerTokenAuthentication
    R->>R: Check scope and authorization
    R-->>C: Response
~~~

When introspection succeeds, the Authentication is typically **BearerTokenAuthentication**. Its principal implements **OAuth2AuthenticatedPrincipal**.

Parts to distinguish:

| Component | Meaning |
|---|---|
| **Access token** | Credential sent by the client in the Authorization header |
| **ReactiveOpaqueTokenIntrospector** | Calls or handles introspection and returns the principal |
| **OAuth2AuthenticatedPrincipal** | Represents the verified subject along with attributes and authorities |
| **BearerTokenAuthentication** | Authentication holding the principal, token, and authorities |
| **GrantedAuthority** | Permission used by Spring Security during authorization |
| **SecurityContext** | Stores the Authentication for the current request in the reactive flow |

The principal is not the raw token. Attributes are not authorities. A claim named `role` inside attributes does not automatically become `ROLE_ADMIN` without an appropriate mapping.

## 2. What Is OAuth2AuthenticatedPrincipal?

OAuth2AuthenticatedPrincipal is the interface representing a principal authenticated with OAuth 2.0. Key members include:

- **getName()**: the principal name used in Authentication.
- **getAttributes()**: a Map of attributes from the introspection result.
- **getAttribute(name)**: retrieves a single attribute by name.
- **getAuthorities()**: the principal's collection of GrantedAuthority objects.

Example principal data:

~~~json
{
  "sub": "alice",
  "user_id": "u-1001",
  "tenant_id": "tenant-a",
  "client_id": "web-client",
  "scope": "messages:read messages:write",
  "email": "alice@example.com"
}
~~~

Attributes can be read in a controller:

~~~java
@GetMapping("/api/profile")
public Mono<Map<String, String>> profile(
        @AuthenticationPrincipal OAuth2AuthenticatedPrincipal principal) {

    String subject = principal.getAttribute("sub");
    String tenant = principal.getAttribute("tenant_id");

    return Mono.just(Map.of(
        "name", principal.getName(),
        "subject", subject,
        "tenant", tenant
    ));
}
~~~

This example assumes all required attributes are present. If a claim can be missing, production code should handle nulls instead of passing them directly into Map.of.

### 2.1. getName() Does Not Always Equal sub

Many Authorization Servers use the `sub` claim as the principal name, but you should not hard-code this assumption if the contract can differ.

For example, the AS sends:

~~~json
{
  "user_name": "alice",
  "subject_id": "u-1001"
}
~~~

The principal can use `user_name` as its name:

~~~java
OAuth2AuthenticatedPrincipal principal =
    new DefaultOAuth2AuthenticatedPrincipal(
        "alice",
        attributes,
        authorities
    );
~~~

When you need to test a specific principal name, configure the entire principal using mockOpaqueToken()'s principal(...) method rather than only adding an attribute and assuming getName() will change automatically.

### 2.2. Attributes and Authorities Are Two Separate Sets of Data

Example:

~~~text
Attributes:
  sub = alice
  tenant_id = tenant-a
  scope = messages:read

Authorities:
  SCOPE_messages:read
~~~

Attributes describe the token/principal. Authorities are the mapped permissions used by Spring Security.

If a test sets:

~~~text
attributes.roles = ["ADMIN"]
~~~

that does not mean the principal automatically has **ROLE_ADMIN**. To test a `hasRole("ADMIN")` rule, grant the `ROLE_ADMIN` authority or test the converter/policy actually responsible for mapping roles.

## 3. mockOpaqueToken() Creates a Mock Authentication

Spring Security Test provides:

~~~java
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockOpaqueToken;
~~~

Using it with WebTestClient:

~~~java
webTestClient
    .mutateWith(mockOpaqueToken())
    .get()
    .uri("/api/profile")
    .exchange()
    .expectStatus().isOk();
~~~

mockOpaqueToken() configures the ServerWebExchange so the SecurityContext contains a **BearerTokenAuthentication** with an **OAuth2AuthenticatedPrincipal** as its principal.

This helper has been available since Spring Security **5.3**. You need the spring-security-test dependency and must keep its version aligned with the Spring Security runtime.

### 3.1. Default Data

According to current test support, mockOpaqueToken() creates a principal with default data:

~~~text
Attributes:
  sub = user
  scope = read

Authorities:
  SCOPE_read
~~~

This allows an endpoint requiring SCOPE_read to be tested without declaring extra data.

Example:

~~~java
webTestClient
    .mutateWith(mockOpaqueToken())
    .get()
    .uri("/api/messages")
    .exchange()
    .expectStatus().isOk();
~~~

This example only succeeds if the security configuration and endpoint allow that default authority.

### 3.2. The Helper Does Not Require a Valid Token

mockOpaqueToken() constructs Authentication data as declared by the test. It does not need an actual access token issued by an Authorization Server.

This is useful when the goal is to:

- Check scopes/authorities.
- Check how controllers read principal attributes.
- Check method security.
- Check tenant/subject authorization.
- Check responses when the principal has different data.

It does not verify the token, does not call the introspection endpoint, and does not prove that client credentials or network connectivity to the Authorization Server work.

## 4. Customizing Attributes with attributes(...)

The attributes method accepts a Consumer<Map<String, Object>> to add or modify principal data.

~~~java
webTestClient
    .mutateWith(mockOpaqueToken()
        .attributes(attributes -> {
            attributes.put("sub", "alice");
            attributes.put("user_id", "u-1001");
            attributes.put("tenant_id", "tenant-a");
            attributes.put("client_id", "web-client");
            attributes.put("scope", "messages:read");
        })
    )
    .get()
    .uri("/api/profile")
    .exchange()
    .expectStatus().isOk();
~~~

In the test support implementation, default attributes are created first and then the Consumer is applied. Therefore, if you only add `user_id`, defaults such as `sub=user` and `scope=read` may still be present.

If you want accurate tests, explicitly set the claims meaningful to the scenario instead of relying accidentally on default values.

### 4.1. Adding tenant_id

A multi-tenant API often needs a tenant claim:

~~~java
webTestClient
    .mutateWith(mockOpaqueToken()
        .attributes(attributes -> {
            attributes.put("sub", "alice");
            attributes.put("tenant_id", "tenant-a");
            attributes.put("scope", "orders.read");
        })
    )
    .get()
    .uri("/api/orders")
    .exchange()
    .expectStatus().isOk();
~~~

Controllers or services can use tenant_id to restrict data. Tests must confirm a `tenant-a` request cannot read records belonging to `tenant-b`.

Do not take the tenant from a caller-supplied query parameter if policy requires the tenant to be bound to the principal.

### 4.2. Adding client_id

Introspection attributes may contain client_id:

~~~java
.attributes(attributes -> {
    attributes.put("sub", "service-user");
    attributes.put("client_id", "reporting-client");
    attributes.put("scope", "reports.read");
})
~~~

This is useful when authorization distinguishes between users and OAuth2 clients. However, client_id is principal data; it does not automatically become an authority.

If an endpoint only permits a specific set of clients, you need a policy checking client_id and tests for both allowed and denied clients.

### 4.3. Data Types Must Match the Contract

Attributes are a Map<String, Object>, so values can be String, Boolean, Number, List, or other types depending on the introspection contract.

Example:

~~~java
.attributes(attributes -> {
    attributes.put("sub", "alice");
    attributes.put("email_verified", Boolean.TRUE);
    attributes.put("groups", List.of("support", "operations"));
    attributes.put("account_level", 3);
})
~~~

The controller must read the right types:

~~~java
Boolean verified = principal.getAttribute("email_verified");
List<String> groups = principal.getAttribute("groups");
Integer accountLevel = principal.getAttribute("account_level");
~~~

Do not force every attribute into a String. When testing malformed or missing claims, define the expected behavior explicitly rather than letting a ClassCastException happen by accident.

## 5. Customizing Authorities with authorities(...)

To test authorization, you can specify authorities directly:

~~~java
import org.springframework.security.core.authority.SimpleGrantedAuthority;

webTestClient
    .mutateWith(mockOpaqueToken()
        .authorities(
            new SimpleGrantedAuthority("SCOPE_messages:read")
        )
    )
    .get()
    .uri("/api/messages")
    .exchange()
    .expectStatus().isOk();
~~~

OpaqueTokenMutator has two overloads:

- authorities(Collection<GrantedAuthority>)
- authorities(GrantedAuthority...)

Multiple permissions example:

~~~java
webTestClient
    .mutateWith(mockOpaqueToken()
        .authorities(
            new SimpleGrantedAuthority("SCOPE_messages:read"),
            new SimpleGrantedAuthority("SCOPE_messages:write"),
            new SimpleGrantedAuthority("ROLE_MESSAGE_ADMIN")
        )
    )
    .get()
    .uri("/api/messages")
    .exchange();
~~~

### 5.1. Explicit Authorities Replace Scope-Derived Authorities

By default, the helper reads the `scope` claim to create authorities with the **SCOPE_** prefix. For example, `scope=read` produces `SCOPE_read`.

When calling authorities(...), the test directly provides the list of authorities used for the principal. Treat this as input data for an authorization test, not a test of the introspector's scope-to-authority converter.

### 5.2. Scope Strings Are Not Automatically Authorities

Example:

~~~text
scope = messages:read
~~~

authority commonly used in Spring Security:

~~~text
SCOPE_messages:read
~~~

Rule:

~~~java
.hasAuthority("SCOPE_messages:read")
~~~

If the test passes:

~~~java
new SimpleGrantedAuthority("messages:read")
~~~

then the authority does not match the rule expecting the SCOPE_ prefix.

### 5.3. Roles Require the ROLE_ Prefix

If authorization uses:

~~~java
.hasRole("ADMIN")
~~~

the required authority is typically:

~~~text
ROLE_ADMIN
~~~

Test:

~~~java
webTestClient
    .mutateWith(mockOpaqueToken()
        .authorities(new SimpleGrantedAuthority("ROLE_ADMIN"))
    )
    .delete()
    .uri("/api/admin/messages/42")
    .exchange()
    .expectStatus().isNoContent();
~~~

This role is granted directly to the mock principal. It does not prove that the real Authorization Server includes the corresponding role claim or that the production converter maps that role properly.

## 6. Providing a Complete OAuth2AuthenticatedPrincipal with principal(...)

When a test needs to change the principal name, use a custom principal implementation, or test complex data, you can construct a **DefaultOAuth2AuthenticatedPrincipal** and pass it via principal(...).

~~~java
import java.util.Map;

import org.springframework.security.core.authority.AuthorityUtils;
import org.springframework.security.oauth2.core.DefaultOAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;

Map<String, Object> attributes = Map.of(
    "user_name", "alice",
    "subject_id", "u-1001",
    "tenant_id", "tenant-a"
);

OAuth2AuthenticatedPrincipal principal =
    new DefaultOAuth2AuthenticatedPrincipal(
        "alice",
        attributes,
        AuthorityUtils.createAuthorityList("SCOPE_messages:read")
    );

webTestClient
    .mutateWith(mockOpaqueToken().principal(principal))
    .get()
    .uri("/api/profile")
    .exchange()
    .expectStatus().isOk();
~~~

This configures the entire principal, including:

- Name.
- Attributes.
- Authorities.

Use it when the principal name does not come from `sub`, when the application has a custom OAuth2AuthenticatedPrincipal, or when you want to test the exact principal structure returned by a custom introspector.

### 6.1. When to Use attributes() vs. principal()?

| Need | Suitable approach |
|---|---|
| Only adding sub, tenant_id, or user_id | attributes(...) |
| Changing scope/claims for a test | attributes(...) |
| Granting a specific authority | authorities(...) |
| Granting multiple authorities | authorities(...) |
| Changing the principal name to user_name | principal(...) |
| Using a custom OAuth2AuthenticatedPrincipal | principal(...) |
| Testing the application's principal implementation | principal(...) |

There is no need to construct a full principal for simple tests. attributes() and authorities() are easier to read when only changing a few values.

### 6.2. Principal Name and Attribute Name Are Different Things

Example principal:

~~~java
new DefaultOAuth2AuthenticatedPrincipal(
    "alice@example.com",
    Map.of(
        "user_name", "alice",
        "sub", "u-1001"
    ),
    authorities
);
~~~

Then:

~~~text
principal.getName() = alice@example.com
principal.getAttribute("user_name") = alice
principal.getAttribute("sub") = u-1001
~~~

Do not assume getName() equals sub or email. Use principal(...) when a test depends on a name defined by contract.

## 7. Reading the Principal in a WebFlux Controller

There are two common ways.

### 7.1. Injecting OAuth2AuthenticatedPrincipal

~~~java
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
class ProfileController {

    @GetMapping("/api/profile")
    Mono<String> profile(
            @AuthenticationPrincipal OAuth2AuthenticatedPrincipal principal) {

        return Mono.just(principal.getName());
    }
}
~~~

This is a good choice when the controller needs to read the principal name or attributes.

### 7.2. Injecting BearerTokenAuthentication

~~~java
import org.springframework.security.oauth2.server.resource.authentication.BearerTokenAuthentication;

@RestController
class TokenInfoController {

    @GetMapping("/api/token-info")
    Mono<String> tokenInfo(BearerTokenAuthentication authentication) {
        String subject =
            (String) authentication.getTokenAttributes().get("sub");

        return Mono.just(subject);
    }
}
~~~

BearerTokenAuthentication provides opaque-token authentication details, where getTokenAttributes() returns the token attributes.

This approach is useful when the controller needs to work directly with BearerTokenAuthentication.

### 7.3. Reading Authentication in a Reactive Service

If you need to access SecurityContext in a reactive pipeline, use ReactiveSecurityContextHolder:

~~~java
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.core.Authentication;
import reactor.core.publisher.Mono;

Mono<String> currentName =
    ReactiveSecurityContextHolder.getContext()
        .map(context -> context.getAuthentication().getName());
~~~

In WebFlux, SecurityContext is passed via the **Reactor Context**; do not assume it is always available in ThreadLocal like Servlet's SecurityContextHolder.

Do not manually call subscribe() just to grab Authentication and store it in a global variable. Compose publishers so the context continues propagating with the request.

### 7.4. Do Not Log Access Tokens

BearerTokenAuthentication contains the credential/token value. When debugging the principal, only log allowed and necessary attributes; do not write raw tokens or Authorization headers to logs.

Principal attributes may also contain personal data or sensitive information. Only include necessary fields in responses, logs, and traces.

## 8. Setting Up WebTestClient with Spring Security

Spring Security Test provides:

~~~java
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockOpaqueToken;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.springSecurity;
~~~

One way to create a WebTestClient bound to the application context:

~~~java
import org.springframework.context.ApplicationContext;
import org.springframework.test.web.reactive.server.WebTestClient;

WebTestClient webTestClient =
    WebTestClient.bindToApplicationContext(applicationContext)
        .apply(springSecurity())
        .configureClient()
        .build();
~~~

springSecurity() configures Spring Security test support in WebTestClient. The application context must contain the SecurityWebFilterChain actually used by the application.

### 8.1. Using a Spring Boot Integration Test

Example skeleton:

~~~java
@SpringBootTest
class OpaqueTokenWebFluxTests {

    @Autowired
    ApplicationContext applicationContext;

    WebTestClient webTestClient;

    @BeforeEach
    void setUp() {
        this.webTestClient =
            WebTestClient.bindToApplicationContext(applicationContext)
                .apply(springSecurity())
                .configureClient()
                .build();
    }
}
~~~

This example assumes the project uses JUnit 5 and already has WebFlux/Spring Security dependencies.

### 8.2. Using a WebFlux Slice Test

With @WebFluxTest, include the controller and necessary security configuration in the test slice. If SecurityWebFilterChain requires a ReactiveOpaqueTokenIntrospector bean, the test context still needs a suitable bean to initialize the configuration.

mockOpaqueToken() skips introspection during test requests, but **does not automatically create every bean the application context needs to start**.

You can use a test configuration or mock bean for dependencies outside the test scope.

### 8.3. Required Dependency

Gradle:

~~~groovy
dependencies {
    testImplementation("org.springframework.security:spring-security-test")
}
~~~

Keep the spring-security-test version synchronized with the Spring Security runtime, usually via Spring Boot dependency management or the Spring Security BOM.

If the test module is missing, the static imports from SecurityMockServerConfigurers will not be found.

## 9. Testing Controllers That Read Attributes

Suppose the endpoint returns the subject:

~~~java
@GetMapping("/api/profile")
Mono<String> profile(
        @AuthenticationPrincipal OAuth2AuthenticatedPrincipal principal) {
    return Mono.just(principal.getAttribute("sub"));
}
~~~

Test:

~~~java
@Test
void profileReturnsSubjectFromPrincipalAttributes() {
    webTestClient
        .mutateWith(mockOpaqueToken()
            .attributes(attributes -> {
                attributes.put("sub", "alice");
                attributes.put("tenant_id", "tenant-a");
                attributes.put("scope", "profile.read");
            })
        )
        .get()
        .uri("/api/profile")
        .exchange()
        .expectStatus().isOk()
        .expectBody(String.class)
        .isEqualTo("alice");
}
~~~

This test proves the controller reads `sub` from the OAuth2AuthenticatedPrincipal injected into the request. It does not prove the real Authorization Server emitted that claim.

### 9.1. Testing the Tenant Attribute

~~~java
@GetMapping("/api/tenant")
Mono<String> tenant(
        @AuthenticationPrincipal OAuth2AuthenticatedPrincipal principal) {

    return Mono.just(principal.getAttribute("tenant_id"));
}
~~~

Test:

~~~java
@Test
void tenantIsReadFromAuthenticatedPrincipal() {
    webTestClient
        .mutateWith(mockOpaqueToken()
            .attributes(attributes -> {
                attributes.put("sub", "alice");
                attributes.put("tenant_id", "tenant-a");
            })
        )
        .get()
        .uri("/api/tenant")
        .exchange()
        .expectStatus().isOk()
        .expectBody(String.class)
        .isEqualTo("tenant-a");
}
~~~

Do not take the tenant from a query parameter if the tenant must be determined by the token/principal.

## 10. Testing Scopes and Authorities

Suppose SecurityWebFilterChain requires:

~~~java
.authorizeExchange(exchanges -> exchanges
    .pathMatchers("/api/messages/**")
        .hasAuthority("SCOPE_messages:read")
    .anyExchange().authenticated()
)
~~~

### 10.1. Token with the Required Scope

~~~java
@Test
void readScopeCanAccessMessages() {
    webTestClient
        .mutateWith(mockOpaqueToken()
            .authorities(
                new SimpleGrantedAuthority("SCOPE_messages:read")
            )
        )
        .get()
        .uri("/api/messages")
        .exchange()
        .expectStatus().isOk();
}
~~~

### 10.2. Token Missing the Scope

~~~java
@Test
void writeScopeCannotReadMessages() {
    webTestClient
        .mutateWith(mockOpaqueToken()
            .authorities(
                new SimpleGrantedAuthority("SCOPE_messages:write")
            )
        )
        .get()
        .uri("/api/messages")
        .exchange()
        .expectStatus().isForbidden();
}
~~~

This is an authorization test. The authority is granted directly to the mock principal; it does not test how scopes in an introspection response are mapped by a converter.

### 10.3. Testing Authorities Derived from the Scope Attribute

If you want to use the mutator's default logic, you can configure the `scope` attribute:

~~~java
webTestClient
    .mutateWith(mockOpaqueToken()
        .attributes(attributes ->
            attributes.put("scope", "messages:read messages:write")
        )
    )
    .get()
    .uri("/api/messages")
    .exchange()
    .expectStatus().isOk();
~~~

By default, the mutator converts each scope into an authority with the SCOPE_ prefix. When a test needs special authorities, use authorities(...) directly.

### 10.4. Testing Roles

~~~java
@Test
void adminRoleCanAccessAdminEndpoint() {
    webTestClient
        .mutateWith(mockOpaqueToken()
            .authorities(new SimpleGrantedAuthority("ROLE_ADMIN"))
        )
        .delete()
        .uri("/api/admin/messages/42")
        .exchange()
        .expectStatus().isNoContent();
}
~~~

This role test only verifies the authorization rule with the ROLE_ADMIN authority. If production derives roles from a claim like `roles`, test the actual mapper/introspector separately.

## 11. Testing a Principal Name Different from sub

Suppose the Authorization Server uses `user_name` as the display name:

~~~java
Map<String, Object> attributes = Map.of(
    "user_name", "alice",
    "sub", "u-1001"
);

OAuth2AuthenticatedPrincipal principal =
    new DefaultOAuth2AuthenticatedPrincipal(
        "alice",
        attributes,
        AuthorityUtils.createAuthorityList("SCOPE_profile.read")
    );
~~~

Test:

~~~java
webTestClient
    .mutateWith(mockOpaqueToken().principal(principal))
    .get()
    .uri("/api/profile")
    .exchange()
    .expectStatus().isOk()
    .expectBody(String.class)
    .isEqualTo("alice");
~~~

If the controller returns `sub`, the result will be `u-1001`. If the controller returns `principal.getName()`, the result is `alice`.

This test helps distinguish **principal name** from **subject claim**.

## 12. Testing Missing Attributes and Invalid Data

A principal may lack a claim because the Authorization Server changed its contract, scopes were trimmed, or the token belongs to a different client.

Example:

~~~java
.attributes(attributes -> {
    attributes.put("sub", "alice");
    attributes.remove("tenant_id");
})
~~~

If the controller requires `tenant_id`, decide clearly:

- Return 400 if request data is missing.
- Deny authentication/authorization if the token lacks a mandatory claim.
- Return 403 if the principal lacks permission.
- Return a controlled internal error if the contract is violated at the mapping layer.

Do not let a NullPointerException or ClassCastException become an accidental response.

### 12.1. Missing Attributes Are Not the Same as an Inactive Token

mockOpaqueToken() still creates a mock Authentication even when test-configured attributes omit a field. It does not run introspection active rules.

In a real system, an inactive token typically does not produce an authenticated principal. Testing inactive tokens requires testing the real introspector/Resource Server authentication flow.

### 12.2. Testing Type Mismatches

If production expects `tenant_id` to be a String but the introspection response returns a Number or List, tests should simulate wrong-typed data to define the behavior.

Do not cast blindly in controllers. It is better to have a mapper/adapter layer converting OAuth2AuthenticatedPrincipal into a domain identity with explicit validation.

## 13. Principal Data and Method Security

WebFlux can use reactive method security to enforce scopes/authorities at the service layer.

Enable:

~~~java
@Configuration
@EnableReactiveMethodSecurity
class ReactiveMethodSecurityConfiguration {
}
~~~

Example:

~~~java
@Service
class MessageService {

    @PreAuthorize("hasAuthority('SCOPE_messages:read')")
    Mono<List<Message>> findMessages() {
        return repository.findAll().collectList();
    }
}
~~~

Test via WebTestClient:

~~~java
@Test
void principalWithReadScopeCanInvokeService() {
    webTestClient
        .mutateWith(mockOpaqueToken()
            .authorities(
                new SimpleGrantedAuthority("SCOPE_messages:read")
            )
        )
        .get()
        .uri("/api/messages")
        .exchange()
        .expectStatus().isOk();
}
~~~

Method security checks authorities in Authentication. If policy requires `tenant_id` or `subject`, the service can accept the principal/Authentication or use an authorization component reading the reactive SecurityContext.

### 13.1. Checking Owner and Tenant in the Service

Logic example:

~~~java
@PreAuthorize("hasAuthority('SCOPE_orders.read')")
public Mono<Order> getOrder(UUID orderId) {
    return ReactiveSecurityContextHolder.getContext()
        .map(context -> context.getAuthentication().getPrincipal())
        .cast(OAuth2AuthenticatedPrincipal.class)
        .flatMap(principal -> {
            String subject = principal.getAttribute("sub");
            String tenantId = principal.getAttribute("tenant_id");

            return repository.findByIdAndTenantIdAndOwnerSubject(
                orderId, tenantId, subject
            );
        });
}
~~~

Tests need to create a principal with the right `sub` and `tenant_id`, then verify owner, non-owner, and cross-tenant cases.

Do not only check hasAuthority if the endpoint returns tenant-scoped data. The `messages.read` scope does not by itself authorize reading every tenant's messages.

### 13.2. Preserving Principal Data in the Reactive Flow

SecurityContext in WebFlux is stored in the Reactor Context. When composing Mono/Flux, Spring Security can provide context per subscription.

Do not read Authentication on an arbitrary thread and store it in a static variable. Do not use ThreadLocal to pass the principal across async boundaries. Tests must go through the real WebFlux filter chain and reactive service path.

## 14. Distinguishing mockOpaqueToken(), mockJwt(), mockUser(), and mockOAuth2Login()

These helpers create different Authentication types:

| Helper | Authentication | Principal |
|---|---|---|
| **mockOpaqueToken()** | BearerTokenAuthentication | OAuth2AuthenticatedPrincipal |
| **mockJwt()** | JwtAuthenticationToken | Jwt |
| **mockUser()** | UsernamePasswordAuthenticationToken | UserDetails |
| **mockOAuth2Login()** | OAuth2AuthenticationToken | OAuth2User |
| **mockOidcLogin()** | OAuth2AuthenticationToken | OidcUser |

Choose the helper matching the principal that the controller/service actually accepts.

### 14.1. When the Controller Accepts OAuth2AuthenticatedPrincipal

Use:

~~~java
@AuthenticationPrincipal OAuth2AuthenticatedPrincipal principal
~~~

Appropriate test:

~~~java
.mutateWith(mockOpaqueToken())
~~~

### 14.2. When the Controller Accepts Jwt

Use:

~~~java
@AuthenticationPrincipal Jwt jwt
~~~

Appropriate test:

~~~java
.mutateWith(mockJwt())
~~~

Do not use mockOpaqueToken() for a controller expecting Jwt, because its principal is OAuth2AuthenticatedPrincipal rather than Jwt.

### 14.3. When the Controller Accepts OidcUser

Use:

~~~java
@AuthenticationPrincipal OidcUser user
~~~

Appropriate test:

~~~java
.mutateWith(mockOidcLogin())
~~~

An OIDC login principal differs from a Resource Server opaque-token principal.

### 14.4. When You Only Need Simple Role Testing

mockUser() may suffice for a role-based rule that does not depend on an OAuth2 principal. However, if code accesses token attributes or BearerTokenAuthentication, mockUser() creates the wrong Authentication type for the test goal.

## 15. mockOpaqueToken() Does Not Invoke ReactiveOpaqueTokenIntrospector

This is the most important boundary when using the helper.

mockOpaqueToken() places a mock Authentication into SecurityContext. It **does not send an HTTP request to the Authorization Server**, does not call ReactiveOpaqueTokenIntrospector, and does not validate the token value.

Therefore, tests using the helper do not prove:

- The Authorization header is extracted properly.
- The introspection URI is right.
- The client ID/client secret are right.
- HTTP Basic/client authentication works.
- TLS certificates/hostnames are valid.
- The AS returns active=true or active=false.
- The introspection response is parsed properly.
- Timeouts, network failures, or AS 5xx errors are handled safely.
- Real scopes/attributes are mapped accurately from the response.

### 15.1. When Should You Use mockOpaqueToken()?

Use it when the focus is:

- SecurityWebFilterChain authorization.
- Controller principal binding.
- OAuth2AuthenticatedPrincipal attributes.
- Authorities and method security.
- Tenant/subject ownership policies.
- Response contracts after authentication has succeeded.

### 15.2. When Must You Test Real Introspection?

Use a different test when you need to confirm:

- BearerTokenAuthenticationWebFilter extracts the token from the HTTP request.
- ReactiveOpaqueTokenIntrospector is invoked.
- An `active=false` response is rejected.
- Attributes and scopes from the AS are mapped properly.
- HTTP errors, timeouts, TLS failures, or bad client credentials do not fail-open.
- The authentication entry point returns the proper status/challenge.

You can use a test HTTP server/stub for the introspection endpoint or a mock ReactiveOpaqueTokenIntrospector bean in a filter-chain integration test.

## 16. Testing via a ReactiveOpaqueTokenIntrospector Stub

If you want to test that the Resource Server actually calls the introspector without needing an external Authorization Server, you can supply a test ReactiveOpaqueTokenIntrospector.

Pattern:

~~~java
ReactiveOpaqueTokenIntrospector introspector = token -> {
    if (!"test-access-token".equals(token)) {
        return Mono.error(new BadOpaqueTokenException("Invalid token"));
    }

    Map<String, Object> attributes = Map.of(
        "sub", "alice",
        "tenant_id", "tenant-a",
        "scope", "messages:read"
    );

    OAuth2AuthenticatedPrincipal principal =
        new DefaultOAuth2AuthenticatedPrincipal(
            "alice",
            attributes,
            AuthorityUtils.createAuthorityList("SCOPE_messages:read")
        );

    return Mono.just(principal);
};
~~~

Then register this introspector in the Resource Server test context and send a request with a real Authorization header:

~~~java
webTestClient
    .get()
    .uri("/api/messages")
    .headers(headers ->
        headers.setBearerAuth("test-access-token")
    )
    .exchange()
    .expectStatus().isOk();
~~~

The example above simulates the introspector contract; it does not test the HTTP client or real Authorization Server. It still passes through the Bearer authentication filter and configured ReactiveOpaqueTokenIntrospector bean.

### 16.1. Comparing Three Test Levels

| Test approach | Has SecurityContext? | Runs Bearer filter? | Calls introspector? |
|---|---|---|---|
| mockOpaqueToken() | Yes, pre-populated | No real token extraction needed | No |
| HTTP Bearer + introspector stub | Created after authentication | Yes | Yes, to stub |
| HTTP Bearer + test AS/introspection server | Created after authentication | Yes | Yes, over HTTP test server |

Choose the test level based on the question you need to answer. You do not need to spin up an AS for every authorization test, but do not use mockOpaqueToken() to conclude that introspection integration works.

## 17. Testing active=false and Introspection Errors

A real introspector must not return a principal for an inactive token. Tests with a stub can:

- Return BadOpaqueTokenException for invalid tokens.
- Return a principal for active tokens.
- Return transport errors for timeouts/AS failures.
- Return a principal missing required claims to test validation/policy.

Typically expected outcomes:

| Scenario | Result |
|---|---|
| Token active with sufficient scope | Request allowed |
| Token active but missing scope | 403 |
| Token inactive/invalid | 401 |
| Introspection timeout | Does not create a successful Authentication |
| AS 5xx | Does not fail-open |
| Principal missing required tenant | Denied per policy |
| Principal has scope but wrong tenant | Resource authorization denied |

Do not map every introspection error into an empty principal or default user. Without a trustworthy verification result, authentication must fail.

## 18. Verifying Responses and Errors with WebTestClient

WebTestClient lets you assert status, headers, and body:

~~~java
webTestClient
    .mutateWith(mockOpaqueToken()
        .authorities(new SimpleGrantedAuthority("SCOPE_messages:read"))
    )
    .get()
    .uri("/api/messages")
    .exchange()
    .expectStatus().isOk()
    .expectHeader().contentTypeCompatibleWith(MediaType.APPLICATION_JSON)
    .expectBody()
    .jsonPath("$.count").isEqualTo(3);
~~~

If the request lacks permission:

~~~java
webTestClient
    .mutateWith(mockOpaqueToken()
        .authorities(new SimpleGrantedAuthority("SCOPE_messages:write"))
    )
    .get()
    .uri("/api/messages")
    .exchange()
    .expectStatus().isForbidden();
~~~

If the request has no Authentication:

~~~java
webTestClient
    .get()
    .uri("/api/messages")
    .exchange()
    .expectStatus().isUnauthorized();
~~~

Actual status codes also depend on SecurityWebFilterChain, entry points, authorization rules, and controllers. Test the exact contract published by your API.

## 19. A Test Matrix for OAuth2AuthenticatedPrincipal

Suppose the API requires:

~~~text
GET /api/messages
  authority: SCOPE_messages:read

GET /api/tenant/messages
  authority: SCOPE_messages:read
  tenant: tenant-a

GET /api/admin/messages
  authority: ROLE_ADMIN
~~~

Matrix:

| Principal | Authorities | Tenant | Expected outcome |
|---|---|---|---|
| Alice | SCOPE_messages:read | tenant-a | Reads messages |
| Alice | SCOPE_messages:write | tenant-a | Read denied |
| Bob | SCOPE_messages:read | tenant-b | Denied on tenant-a |
| Admin | ROLE_ADMIN | tenant-a | Passes admin policy |
| Anonymous | None | None | 401 |
| Active principal | Valid scope but missing tenant | None | Denied per policy |

Tests must demonstrate both allow and deny branches.

### 19.1. Testing Same Scope, Different Tenant

~~~java
@Test
void principalFromOtherTenantCannotReadTenantA() {
    webTestClient
        .mutateWith(mockOpaqueToken()
            .attributes(attributes -> {
                attributes.put("sub", "bob");
                attributes.put("tenant_id", "tenant-b");
                attributes.put("scope", "messages:read");
            })
        )
        .get()
        .uri("/api/tenant-a/messages")
        .exchange()
        .expectStatus().isForbidden();
}
~~~

This test keeps the scope identical while changing the tenant. If it is still allowed, tenant enforcement may be missing.

### 19.2. Testing Correct Scope but Non-Owner Subject

Create a principal with the read scope and a subject different from the resource owner. Verify the service/repository denies access. **Scope authorizes the action type; subject/tenant determines which data can be accessed.**

## 20. Reactive SecurityContext and Test Isolation

WebFlux uses Reactor Context to carry SecurityContext across publishers. Each test request needs its own principal.

Do not store principals in static fields or mutable singleton state. If tests run in parallel, two requests can mix data if the application manages Authentication improperly.

Example:

~~~text
Request A:
  sub=alice
  tenant=tenant-a

Request B:
  sub=bob
  tenant=tenant-b
~~~

Each request must read its own principal. Use a separate WebTestClient mutator per request and avoid global variables storing user info.

### 20.1. Do Not Call subscribe() Manually in Controllers

Wrong:

~~~java
@GetMapping("/api/profile")
Mono<String> profile() {
    ReactiveSecurityContextHolder.getContext()
        .subscribe(context -> saveUser(context.getAuthentication().getName()));

    return Mono.just("ok");
}
~~~

This creates a subscription detached from the response lifecycle, making errors, cancellation, and context hard to control.

Better to compose publishers:

~~~java
@GetMapping("/api/profile")
Mono<String> profile() {
    return ReactiveSecurityContextHolder.getContext()
        .map(context -> context.getAuthentication().getName());
}
~~~

## 21. Common Pitfalls

**Using mockOpaqueToken() to test HTTP introspection.** The helper skips the introspector and injects a mock Authentication.

**Confusing OAuth2AuthenticatedPrincipal with Jwt.** An opaque token principal is not a Jwt object.

**Using mockUser() for controllers accepting BearerTokenAuthentication.** The Authentication type does not match.

**Only adding tenant_id to attributes without checking tenant.** Presence of a claim does not make authorization happen automatically.

**Assuming a `roles` claim automatically creates ROLE_ADMIN.** Attributes and authorities are separate data sets.

**Confusing scope with authority.** Scope `messages:read` typically becomes `SCOPE_messages:read`.

**Confusing principal.getName() with sub.** Principal name can be configured from a different attribute.

**Relying on default values without declaring the scenario.** Defaults `sub=user`, `scope=read` can make tests pass unintentionally.

**Not configuring spring-security-test.** Static imports and mutators will be missing from the test classpath.

**Not attaching Spring Security to WebTestClient.** Tests may bypass real filters/authorization.

**Creating a SecurityFilterChain requiring an introspector when the test context lacks the bean.** mockOpaqueToken() does not auto-configure application dependencies.

**Reading attributes with the wrong type.** Can cause ClassCastException or NullPointerException.

**Logging tokens or all attributes.** Can expose credentials or sensitive data.

**Sharing one mutable principal across multiple requests.** Risks data leakage between test cases.

**Confusing mockOpaqueToken() with mockOAuth2Login().** Resource Server Bearer authentication and OIDC login are two different Authentication flows.

## 22. Test-Writing Workflow

**Step 1 — Identify the code under test.** Does the controller accept OAuth2AuthenticatedPrincipal, BearerTokenAuthentication, or generic Authentication?

**Step 2 — Choose the right helper.** For an opaque Resource Server principal, use mockOpaqueToken().

**Step 3 — Declare attributes explicitly.** Set sub, tenant_id, client_id, and any claims required by the test.

**Step 4 — Declare authorities explicitly.** Use authorities(...) when testing scopes/roles; if testing the mutator's default scope mapping, configure the `scope` attribute.

**Step 5 — Check the principal name.** If the application relies on getName(), create a custom principal when the contract does not use `sub` as the name.

**Step 6 — Set up WebTestClient with Spring Security.** Use the application context and springSecurity() to test the real filter chain.

**Step 7 — Test positive and negative cases.** Sufficient scope, missing scope, wrong tenant, non-owner, missing attributes, and anonymous.

**Step 8 — Verify reactive method security.** Enable @EnableReactiveMethodSecurity if services use @PreAuthorize.

**Step 9 — Separate authentication integration tests.** Use Bearer headers and a ReactiveOpaqueTokenIntrospector stub/HTTP test server when testing introspection.

**Step 10 — Maintain request isolation.** Never store Authentication in static/singleton mutable fields and never subscribe detached from the pipeline.

## 23. Self-Check Questions

**1. What Authentication type does mockOpaqueToken() create?**

BearerTokenAuthentication.

**2. Which interface does its principal implement?**

OAuth2AuthenticatedPrincipal.

**3. What is the helper's default data?**

sub=user, scope=read, and authority SCOPE_read.

**4. How do you add tenant_id?**

Use attributes(attributes -> attributes.put("tenant_id", "tenant-a")).

**5. How do you grant the SCOPE_messages:read authority?**

Use authorities(new SimpleGrantedAuthority("SCOPE_messages:read")).

**6. If attributes contain roles=["ADMIN"], does the principal automatically get ROLE_ADMIN?**

No. Mapping or explicit authority assignment is required.

**7. When should you use principal(...) instead of attributes(...)?**

When you need to supply a full OAuth2AuthenticatedPrincipal, a custom implementation, or a specific principal name.

**8. Does mockOpaqueToken() call ReactiveOpaqueTokenIntrospector?**

No. It creates a mock Authentication inside the test exchange.

**9. Can you use mockJwt() instead of mockOpaqueToken() for a controller accepting OAuth2AuthenticatedPrincipal?**

No. mockJwt() creates a JwtAuthenticationToken with a Jwt principal.

**10. Why should WebFlux not use ThreadLocal to hold Authentication?**

SecurityContext is propagated via the Reactor Context; ThreadLocal does not guarantee context across reactive execution.

**11. Does a passing scope test prove the introspection response is parsed correctly?**

Not if using mockOpaqueToken(). An introspector stub or HTTP integration test is needed.

**12. What should an active token missing a required scope return?**

Authentication may succeed, but authorization denies the request, typically returning 403.

## Conclusion

**mockOpaqueToken()** is the Spring Security Test tool for a WebFlux Resource Server when you need to construct a **BearerTokenAuthentication** with an **OAuth2AuthenticatedPrincipal** without a real Authorization Server.

Use:

- **attributes(...)** to set subject, tenant, client, and token attributes.
- **authorities(...)** to grant scope/role authorities for authorization tests.
- **principal(...)** to provide a complete OAuth2AuthenticatedPrincipal and verify custom principal names.
- **WebTestClient.mutateWith(mockOpaqueToken())** to test controllers, filter authorization, and reactive method security.

Keep in mind that the helper only simulates an authenticated state. It does not call the introspection endpoint, does not check `active`, does not verify client credentials, and does not test network failures. When you need to prove those parts, send a real Bearer header through the Resource Server filter chain using a ReactiveOpaqueTokenIntrospector stub or a test Authorization Server.

**A good WebFlux test simulates the exact principal your code consumes, tests attributes and authorities separately, and verifies that insufficient scopes, wrong tenants, and non-owner subjects are all rejected.**

### References

- [Spring Security — Reactive OAuth 2.0 Testing: Opaque Token Authentication](https://docs.spring.io/spring-security/reference/reactive/test/web/oauth2.html)
- [Spring Security API — SecurityMockServerConfigurers](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/test/web/reactive/server/SecurityMockServerConfigurers.html)
- [Spring Security API — OpaqueTokenMutator](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/test/web/reactive/server/SecurityMockServerConfigurers.OpaqueTokenMutator.html)
- [Spring Security API — OAuth2AuthenticatedPrincipal](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/core/OAuth2AuthenticatedPrincipal.html)
- [Spring Security API — DefaultOAuth2AuthenticatedPrincipal](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/core/DefaultOAuth2AuthenticatedPrincipal.html)
- [Spring Security API — BearerTokenAuthentication](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/authentication/BearerTokenAuthentication.html)
- [Spring Security — Reactive OAuth 2.0 Resource Server Opaque Token](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/opaque-token.html)
- [Spring Security — Reactive Method Security](https://docs.spring.io/spring-security/reference/reactive/authorization/method.html)
- [Spring Framework — WebTestClient](https://docs.spring.io/spring-framework/reference/testing/webtestclient.html)
- [Project Reactor — Context](https://projectreactor.io/docs/core/release/reference/advancedFeatures/context.html)
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662)
