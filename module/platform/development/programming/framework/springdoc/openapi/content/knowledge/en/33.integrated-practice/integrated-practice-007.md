# Documenting Bearer or OAuth2 and Verifying with Real Security Configuration

OpenAPI can describe how clients send an access token, but the documentation itself does not protect endpoints. For an API to actually enforce Bearer JWT or OAuth2, the application must have a Spring Security configuration that validates tokens and authorizes each request. Both parts must align:

1. **Documenting in OpenAPI:** declare security schemes, scopes, and which operations require authentication.
2. **Enforcing in Spring Security:** validate tokens, verify signatures, issuer, and expiry, and decide whether a request is permitted.

With springdoc-openapi, you can declare schemes via annotations or an OpenAPI bean configuration. Then use MockMvc integration tests to verify the generated document and call endpoints in unauthenticated, unauthorized, and authorized states. This catches cases where Swagger UI shows a padlock while the API remains public, or where the API is protected while the documentation fails to explain how to obtain a token.

## 1. Distinguishing Bearer JWT and OAuth2

The two terms are related but belong to different layers:

- **Bearer authentication** is how a client sends credentials in the HTTP header `Authorization: Bearer <token>`. The server accepts the token if it is valid and the request holds sufficient permissions.
- **JWT** is a structured token format typically carrying claims such as `iss`, `sub`, `aud`, `exp`, and `scope`. A JWT can be signed so a resource server can verify it.
- **OAuth2** is an authorization framework defining how clients obtain access tokens and how scopes express permissions. An OAuth2 access token can be a JWT or an opaque token.
- **Resource Server** is the API that receives and verifies access tokens. It is not necessarily the component that issues tokens.

If the system only needs to document a Bearer header, use an OpenAPI HTTP security scheme with `scheme: bearer`. If it needs to document an OAuth2 flow so developers can obtain tokens, use an OAuth2 security scheme with the appropriate flows and scopes.

| Need | Common OpenAPI scheme |
|---|---|
| Client obtains JWT from another system and sends a Bearer token | HTTP Bearer |
| Swagger UI logs in via Identity Provider using Authorization Code + PKCE | OAuth2 Authorization Code |
| Service-to-service fetches tokens from a token endpoint | OAuth2 Client Credentials |
| API accepts opaque tokens and introspects via Identity Provider | HTTP Bearer or OAuth2 scheme depending on how the contract is published |

Do not declare `bearerFormat: JWT` just because the header says Bearer if the actual token is not a JWT. `bearerFormat` is only a hint for readers/tools; it does not make Spring Security verify JWT signatures.

## 2. Documenting HTTP Bearer in OpenAPI

For an API receiving a JWT in the Authorization header, declare the security scheme:

~~~java
import io.swagger.v3.oas.annotations.OpenAPIDefinition;
import io.swagger.v3.oas.annotations.enums.SecuritySchemeType;
import io.swagger.v3.oas.annotations.security.SecurityRequirement;
import io.swagger.v3.oas.annotations.security.SecurityScheme;
import org.springframework.context.annotation.Configuration;

@Configuration
@OpenAPIDefinition(
    security = {
        @SecurityRequirement(name = "bearerAuth")
    }
)
@SecurityScheme(
    name = "bearerAuth",
    type = SecuritySchemeType.HTTP,
    scheme = "bearer",
    bearerFormat = "JWT",
    description = "JWT access token in the Authorization header"
)
public class OpenApiBearerConfiguration {
}
~~~

In the OpenAPI document, the corresponding scheme looks like:

~~~yaml
components:
  securitySchemes:
    bearerAuth:
      type: http
      scheme: bearer
      bearerFormat: JWT
      description: JWT access token in the Authorization header
security:
  - bearerAuth: []
~~~

`components.securitySchemes` only defines the authentication mechanism. The root-level `security` array applies that requirement to operations across the document, unless an operation overrides it with its own security setting.

If you only want to protect a single controller, place `@SecurityRequirement(name = "bearerAuth")` at the class or operation level instead of applying it globally. This is useful when a single document contains both public endpoints and token-protected endpoints.

### Marking an operation as public

When a global security requirement is declared, public operations must override it with an empty security array:

~~~java
@Operation(
    summary = "Check service health",
    security = {}
)
@GetMapping("/health")
public HealthResponse health() {
    return new HealthResponse("UP");
}
~~~

In OpenAPI, `security: []` at the operation level means the operation does not require the global security scheme. This only documents the contract; Spring Security must still configure `/health` as public if that is the desired runtime behavior.

## 3. Declaring OAuth2 Authorization Code + PKCE

For developers signing in through an Identity Provider directly inside Swagger UI, the Authorization Code flow combined with PKCE is typically appropriate for public browser clients. OpenAPI must describe the authorization endpoint, token endpoint, and the scopes required by the API.

~~~java
import io.swagger.v3.oas.annotations.OpenAPIDefinition;
import io.swagger.v3.oas.annotations.security.OAuthFlow;
import io.swagger.v3.oas.annotations.security.OAuthFlows;
import io.swagger.v3.oas.annotations.security.OAuthScope;
import io.swagger.v3.oas.annotations.security.SecurityRequirement;
import io.swagger.v3.oas.annotations.security.SecurityScheme;
import io.swagger.v3.oas.annotations.enums.SecuritySchemeType;
import org.springframework.context.annotation.Configuration;

@Configuration
@OpenAPIDefinition(
    security = {
        @SecurityRequirement(
            name = "ordersOAuth",
            scopes = {"orders.read"}
        )
    }
)
@SecurityScheme(
    name = "ordersOAuth",
    type = SecuritySchemeType.OAUTH2,
    flows = @OAuthFlows(
        authorizationCode = @OAuthFlow(
            authorizationUrl = "https://id.example.com/oauth2/authorize",
            tokenUrl = "https://id.example.com/oauth2/token",
            scopes = {
                @OAuthScope(
                    name = "orders.read",
                    description = "Read orders"
                ),
                @OAuthScope(
                    name = "orders.write",
                    description = "Create and update orders"
                )
            }
        )
    )
)
public class OpenApiOAuthConfiguration {
}
~~~

The generated document describes the OAuth2 flow and scopes under `components.securitySchemes.ordersOAuth.flows.authorizationCode`. The root requirement requires the `orders.read` scope.

If an operation needs a different scope, attach the requirement to the operation:

~~~java
@Operation(
    summary = "Create an order",
    security = {
        @SecurityRequirement(
            name = "ordersOAuth",
            scopes = {"orders.write"}
        )
    }
)
@PostMapping("/api/orders")
public OrderResponse create(@RequestBody CreateOrderRequest request) {
    return orderService.create(request);
}
~~~

Scopes in OpenAPI describe the permissions a client needs. They do not create scopes in the Identity Provider and do not configure Spring Security. Scopes must exist in the token-issuing system and be mapped by the resource server to the authorities checked by the application.

## 4. Configuring Spring Security to enforce Bearer JWT

With Spring Boot 3 and Spring Security 6, you can configure the application as an OAuth2 Resource Server. The following example requires a JWT with matching scopes when calling the API:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://id.example.com/realms/acme
~~~

`issuer-uri` lets Spring Security discover the issuer's metadata and the public keys used to verify JWTs. Production environments must use HTTPS and an issuer matching tokens issued by the Identity Provider.

Configuring the filter chain:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class ApiSecurityConfiguration {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        return http
            .csrf(csrf -> csrf.disable())
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS)
            )
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers(
                    "/v3/api-docs",
                    "/v3/api-docs/**",
                    "/v3/api-docs.yaml",
                    "/swagger-ui/**",
                    "/swagger-ui.html"
                ).permitAll()
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .requestMatchers(HttpMethod.POST, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.write")
                .anyRequest().authenticated()
            )
            .oauth2ResourceServer(resourceServer -> resourceServer
                .jwt(Customizer.withDefaults())
            )
            .build();
    }
}
~~~

In the example, OpenAPI docs and Swagger UI are public so developers can read the contract; business endpoints require tokens. If documentation is internal, replace `permitAll()` with your organization's authentication/authorization policy and write tests for that policy.

Disabling CSRF is only appropriate for stateless APIs authenticating via Bearer tokens in headers without cookies/sessions. If the application uses session cookies, form login, or browser auto-sent credentials, do not blindly copy `csrf.disable()`; design proper CSRF protection instead.

`SessionCreationPolicy.STATELESS` instructs Spring Security not to create sessions to store authentication state. Tokens are sent again with each request.

### How Spring Security maps scopes to authorities

For JWTs carrying a `scope` or `scp` claim, Spring Security Resource Server by default maps each scope to an authority prefixed with `SCOPE_`. For example:

~~~json
{
  "iss": "https://id.example.com/realms/acme",
  "sub": "user-42",
  "scope": "orders.read orders.write",
  "exp": 1900000000
}
~~~

Corresponding authorities:

~~~text
SCOPE_orders.read
SCOPE_orders.write
~~~

Thus, `hasAuthority("SCOPE_orders.read")` checks for the `orders.read` scope. If your Identity Provider uses a custom claim or different format, configure `JwtAuthenticationConverter`/`JwtGrantedAuthoritiesConverter` to map correctly; do not assume every token uses the same claim name.

## 5. Spring Security does not issue access tokens

When configuring:

~~~java
.oauth2ResourceServer(resourceServer -> resourceServer
    .jwt(Customizer.withDefaults())
)
~~~

the application is verifying incoming access tokens. It does not become an OAuth2 Authorization Server and does not automatically expose `/oauth2/authorize` or `/oauth2/token` endpoints.

Authorization/token endpoints in `@SecurityScheme` must point to your actual Identity Provider or Authorization Server. Do not enter the Resource Server API's URL in these fields if the API does not issue tokens.

With OAuth2 Authorization Code + PKCE, Swagger UI redirects the user to the Identity Provider, receives an authorization code, exchanges the code for an access token, and then sends the Bearer token to the API. The Identity Provider must register the exact redirect URI of Swagger UI, such as the public URL of `oauth2-redirect.html`. Domain, HTTPS scheme, and context path must match on both sides.

Never embed a client secret in JavaScript or browser-side Swagger UI configuration. Browser clients should use PKCE and a client registration suitable for public clients.

## 6. Configuring Swagger UI for OAuth2 login

When using the Authorization Code flow, Swagger UI needs the client ID and PKCE enabled:

~~~yaml
springdoc:
  swagger-ui:
    oauth:
      client-id: swagger-ui-public-client
      use-pkce-with-authorization-code-grant: true
~~~

Property names and support may vary across springdoc/Swagger UI versions. Check the configuration properties for your exact version and verify the public redirect URL in the Identity Provider configuration.

After opening Swagger UI:

1. Click **Authorize**.
2. Select the OAuth2 security scheme.
3. Select the required scopes, such as `orders.read`.
4. Complete sign-in at the Identity Provider.
5. Swagger UI receives the access token and sends requests with `Authorization: Bearer ...`.

With an HTTP Bearer scheme, users typically paste the access token directly into the Authorize dialog. Swagger UI automatically prepends the Bearer prefix for HTTP bearer schemes; do not paste an extra `Bearer ` prefix if the UI asks for the raw token.

Do not enable credential persistence on shared browsers or public machines. Likewise, do not use Swagger UI as a production token manager; the UI is primarily for API discovery and testing in developer environments.

## 7. Attaching security requirements to controllers and operations

If you prefer not to apply security globally, declare the scheme in configuration and attach requirements at the controller level:

~~~java
import io.swagger.v3.oas.annotations.security.SecurityRequirement;

@RestController
@RequestMapping("/api/orders")
@SecurityRequirement(name = "bearerAuth")
public class OrderController {
    // Operations in this controller require a Bearer token.
}
~~~

An operation requiring a specific scope can use:

~~~java
@Operation(
    summary = "Read orders",
    security = {
        @SecurityRequirement(
            name = "ordersOAuth",
            scopes = {"orders.read"}
        )
    }
)
~~~

Do not declare a security requirement simply because an endpoint accepts an arbitrary header. Schemes and requirements must reflect the real runtime mechanism: HTTP bearer, OAuth2, API key, or another mechanism.

If using global security while keeping some endpoints public, mark those operations with `@Operation(security = {})` and configure matching `permitAll()` rules in Spring Security. Both sides must agree.

## 8. Verifying real security configuration with MockMvc

You can use `spring-boot-starter-test` alongside `spring-security-test`:

~~~xml
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
~~~

Tests should verify three baseline cases:

| Request | Expected outcome |
|---|---|
| No token | `401 Unauthorized` |
| Valid token lacking authority/scope | `403 Forbidden` |
| Valid token with required authority/scope | `200 OK` or endpoint success status |

Example using MockMvc and the JWT test post-processor:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.jwt;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class OrderSecurityTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void anonymousRequestIsRejected() throws Exception {
        mockMvc.perform(get("/api/orders"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void authenticatedTokenWithoutReadScopeIsForbidden() throws Exception {
        mockMvc.perform(
                get("/api/orders")
                    .with(jwt().authorities(() -> "SCOPE_profile.read"))
            )
            .andExpect(status().isForbidden());
    }

    @Test
    void tokenWithReadScopeCanReadOrders() throws Exception {
        mockMvc.perform(
                get("/api/orders")
                    .accept(MediaType.APPLICATION_JSON)
                    .with(jwt().authorities(() -> "SCOPE_orders.read"))
            )
            .andExpect(status().isOk());
    }
}
~~~

`jwt()` creates a mock JwtAuthenticationToken for authorization testing. It helps test authorization rules and authority mapping without calling an Identity Provider. However, it **bypasses signature, issuer, expiry verification, and real token decoding**. Do not rely solely on this test to conclude that the JWT decoder works properly.

### Verifying real tokens

To verify the JWT decoder, write an integration test using a JWT signed by a test key/JWKS or a dedicated test Identity Provider. Send the token in the HTTP header:

~~~http
Authorization: Bearer eyJ...test-token
~~~

Check:

- A token with a valid signature is accepted.
- A token with an invalid signature or unknown key is rejected.
- An expired token is rejected.
- A token with an invalid `iss` claim is rejected.
- A token missing the required scope receives `403` on scope-protected endpoints.

If you only mock `JwtDecoder`, tests can verify how the filter chain handles valid/invalid results from the decoder, but not actual signature algorithms or JWKS resolution. Keep at least one test using a controlled key pair/JWKS in the test environment.

## 9. Verifying security schemes in the OpenAPI document

Runtime tests do not confirm springdoc documented security properly. Inspect `/v3/api-docs`:

~~~java
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;

@Test
void openApiDocumentDeclaresBearerScheme() throws Exception {
    mockMvc.perform(get("/v3/api-docs"))
        .andExpect(status().isOk())
        .andExpect(jsonPath(
            "$.components.securitySchemes.bearerAuth.type"
        ).value("http"))
        .andExpect(jsonPath(
            "$.components.securitySchemes.bearerAuth.scheme"
        ).value("bearer"))
        .andExpect(jsonPath(
            "$.components.securitySchemes.bearerAuth.bearerFormat"
        ).value("JWT"))
        .andExpect(jsonPath("$.security[0].bearerAuth").exists());
}
~~~

If the document uses OAuth2, verify flows and scopes:

~~~java
@Test
void openApiDocumentDeclaresOAuth2AuthorizationCodeFlow() throws Exception {
    mockMvc.perform(get("/v3/api-docs"))
        .andExpect(status().isOk())
        .andExpect(jsonPath(
            "$.components.securitySchemes.ordersOAuth.type"
        ).value("oauth2"))
        .andExpect(jsonPath(
            "$.components.securitySchemes.ordersOAuth.flows.authorizationCode.authorizationUrl"
        ).value("https://id.example.com/oauth2/authorize"))
        .andExpect(jsonPath(
            "$.components.securitySchemes.ordersOAuth.flows.authorizationCode.scopes.orders.read"
        ).exists());
}
~~~

If security requirements are declared at the operation level rather than root, JSONPath should inspect the specific operation's `paths` entry. If an endpoint is public, verify that the operation does not inherit the global requirement.

## 10. Checking documentation endpoints under Spring Security

In the example above, `/v3/api-docs/**` and Swagger UI allow public access. Tests should lock down that policy:

~~~java
@Test
void publicOpenApiDocumentCanBeReadWithoutToken() throws Exception {
    mockMvc.perform(get("/v3/api-docs")
            .accept(MediaType.APPLICATION_JSON))
        .andExpect(status().isOk())
        .andExpect(content().contentTypeCompatibleWith(
            MediaType.APPLICATION_JSON
        ));
}
~~~

If documentation is restricted to authenticated developers, test both that anonymous requests are rejected and that requests with the appropriate role succeed. Never disable the entire filter chain with `addFilters = false` in security tests; doing so bypasses the exact configuration being verified.

URLs to review depending on actual configuration include:

- `/v3/api-docs` and `/v3/api-docs/**` for default/group documents.
- `/v3/api-docs.yaml` if YAML is published; add this path to security matchers if documentation is public.
- `/v3/api-docs/swagger-config` for Swagger UI configuration.
- `/swagger-ui.html` and `/swagger-ui/**` for the UI page and static assets.
- The OAuth2 redirect endpoint used by Swagger UI.

If you change `springdoc.api-docs.path` or `springdoc.swagger-ui.path`, update security matchers and tests to match the new URLs. Do not open `/v3/**` broadly if only documentation endpoints should be permitted.

## 11. Distinguishing 401 and 403

These two status codes represent different failures:

- `401 Unauthorized`: the request has not been successfully authenticated—e.g., missing token, invalid signature, or expired token.
- `403 Forbidden`: the request is authenticated, but the principal lacks the required permission—e.g., missing `orders.read` scope.

With OAuth2 Resource Server, a 401 response typically includes `WWW-Authenticate: Bearer`. Do not return 200 with an error body for missing tokens if the API adheres to HTTP semantics and its published contract.

If the API uses a custom `AuthenticationEntryPoint` or `AccessDeniedHandler`, response bodies may be standardized as Problem Details. In that case, OpenAPI must accurately document the status, media type, and error schema, and tests must verify all three.

## 12. CORS when Swagger UI calls an API on another origin

Swagger UI may run on a documentation domain while the API runs on another domain. Browsers enforce CORS on Try it out requests. A Bearer token typically triggers a preflight request because the `Authorization` header is not a simple header.

Example CORS configuration for Spring MVC:

~~~java
import java.util.List;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.CorsConfigurationSource;
import org.springframework.web.cors.UrlBasedCorsConfigurationSource;

@Configuration
public class ApiCorsConfiguration {

    @Bean
    CorsConfigurationSource corsConfigurationSource() {
        CorsConfiguration configuration = new CorsConfiguration();
        configuration.setAllowedOrigins(
            List.of("https://docs.example.com")
        );
        configuration.setAllowedMethods(
            List.of("GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS")
        );
        configuration.setAllowedHeaders(
            List.of("Authorization", "Content-Type", "Accept")
        );
        configuration.setExposedHeaders(List.of("Location"));

        UrlBasedCorsConfigurationSource source =
            new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration("/api/**", configuration);
        return source;
    }
}
~~~

Enable CORS in the filter chain:

~~~java
http.cors(Customizer.withDefaults());
~~~

Allow only required origins. If using cookies/sessions with `allowCredentials`, never combine credentialed requests with wildcard origins. CORS is strictly a browser policy; it does not replace server-side authentication or authorization.

If Swagger UI and the API share the same origin, CORS may not be needed. When CORS is misconfigured, the browser blocks the request before JavaScript can read the API response, even though calling the endpoint with curl still succeeds.

## 13. Verification matrix between documentation and runtime configuration

After configuring, compare across layers:

| Behavior | OpenAPI document | Spring Security runtime | Required tests |
|---|---|---|---|
| API uses Bearer JWT | `type: http`, `scheme: bearer` | `oauth2ResourceServer().jwt()` | Scheme exists in `/v3/api-docs`; valid token accepted |
| API uses OAuth2 scopes | OAuth2 flow and scopes | Authority `SCOPE_...` | With scope returns 200; without scope returns 403 |
| Request without token | Operation has security requirement | Request rejected | 401 |
| Invalid/expired token | Security scheme still documented | Decoder rejects token | 401 with real token |
| Public endpoint | Operation `security: []` or no matching requirement | `permitAll()` | Anonymous receives success status |
| Public documentation | Does not necessarily require security requirement | `/v3/api-docs/**` and UI `permitAll()` | Anonymous can read document |
| Internal documentation | Access policy may be documented in deployment docs | Docs endpoints require proper role | Anonymous rejected, valid role allowed |

A complete test suite should include at least one document test, one authority-based authorization test, and one real-token verification test in an integration environment.

## 14. Common mistakes

| Symptom | Possible cause | Resolution |
|---|---|---|
| Swagger UI shows padlock but endpoint is still public | Only declared `@SecurityScheme`/`@SecurityRequirement` without configuring Spring Security | Add Resource Server/filter chain and test anonymous requests |
| API returns 401 but Swagger UI sends no token | Scheme not attached to operation or Authorize not clicked | Check `security` in document and Authorize setup |
| Valid token still receives 401 | Wrong issuer/JWKS, expired token, signature or audience mismatch | Check claims, issuer, JWK, and decoder |
| Token receives 403 | Authenticated, but missing authority/scope | Check `scope`/`scp` claim and converter |
| Scope in OpenAPI has no runtime effect | Scopes are only document metadata | Map scopes to authorities and enforce with `hasAuthority` |
| OAuth2 login redirects to error page | Redirect URI unregistered or mismatches public URL | Align redirect URL, HTTPS, context path, and IdP client registration |
| Swagger UI fails to obtain token | Wrong Authorization/token URL or incorrect CORS/PKCE | Inspect IdP metadata, PKCE, redirect, and browser console |
| `@WithMockUser` test passes but real JWT fails | Mock user bypasses JWT decoder | Add integration test with real JWT/JWKS |
| `/v3/api-docs` returns 401 | Security matcher does not permit docs endpoints | Update matchers or grant appropriate docs permissions |
| Swagger UI loads but Try it out hits CORS error | API server has not allowed docs origin and Authorization header | Configure CORS for API endpoints |
| Public endpoint displays padlock | Global security applies to all operations | Mark `@Operation(security = {})` and configure `permitAll()` |
| `csrf.disable()` exposes session app | Copied stateless config to cookie/session app | Disable CSRF only when API is truly stateless using Bearer tokens |
| Client secret exposed in browser | Placed secret into Swagger UI OAuth config | Use a public client with PKCE; never distribute client secrets |

## 15. Implementation and testing workflow

Follow this order so the contract and enforcement layers always match:

1. Decide whether the API uses simple Bearer tokens or an OAuth2 flow; specify issuer, audience, scopes, and token format.
2. Configure the Resource Server to verify tokens; do not assume the API acts as the Authorization Server.
3. Establish authorization rules by path, HTTP method, role, or scope.
4. Declare OpenAPI security schemes and corresponding requirements via annotations or an OpenAPI bean.
5. Mark public endpoints clearly in the document and with `permitAll()` at runtime.
6. Configure Swagger UI OAuth2 client/PKCE if interactive sign-in is required.
7. Configure CORS if UI and API are on different origins.
8. Test the `/v3/api-docs` document to confirm schemes, flows, scopes, and operation security.
9. Test 401/403/200 using MockMvc and the JWT test post-processor.
10. Test real JWT signature/issuer/expiry using a test key/JWKS or a test Identity Provider.
11. Test Try it out on the public domain and verify tokens are not leaked in logs.
12. Run regression tests before release.

## 16. Pre-release checklist

- [ ] Clearly identified Bearer JWT, OAuth2 access token, or opaque token.
- [ ] Security scheme in OpenAPI matches how clients send credentials.
- [ ] `bearerFormat` is used only as a hint, not mistaken for JWT verification.
- [ ] OAuth2 authorization/token URLs point to the real Identity Provider.
- [ ] Scopes in OpenAPI match scopes issued and enforced at runtime.
- [ ] Spring Security verifies token signature, issuer, and expiration.
- [ ] Audience validation is enabled if the system requires a specific audience.
- [ ] Authorization rules are applied per required endpoint/method.
- [ ] Public endpoints are consistently documented and configured with `permitAll()`.
- [ ] API documentation is protected or public according to policy.
- [ ] Swagger UI uses PKCE for public browser clients with Authorization Code.
- [ ] No client secret is placed in JavaScript/browser configuration.
- [ ] CORS permits the right origins and `Authorization` header if needed.
- [ ] Document tests verify security schemes and requirements.
- [ ] Runtime tests verify 401, 403, and authorized access.
- [ ] Real JWT verification tests exist, not only mock authentication.

## 17. Official references

- [springdoc-openapi — Security](https://springdoc.org/#javadoc-support) — integrating Swagger/OpenAPI annotations to document security schemes and requirements.
- [OpenAPI Specification — Security Scheme Object](https://spec.openapis.org/oas/latest.html#security-scheme-object) — describing HTTP bearer and OAuth2 flows.
- [OpenAPI Specification — Security Requirement Object](https://spec.openapis.org/oas/latest.html#security-requirement-object) — applying security schemes at root or operation level.
- [Spring Security — OAuth2 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html) — configuring JWT decoder, issuer, and authorities.
- [Spring Security — Testing OAuth2](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/oauth2.html) — testing OAuth2/JWT-authenticated requests with MockMvc.
- [Swagger UI — OAuth2 Configuration](https://swagger.io/docs/open-source-tools/swagger-ui/usage/oauth2/) — configuring OAuth2 and PKCE in Swagger UI.
- [Spring Framework — CORS](https://docs.spring.io/spring-framework/reference/web/webmvc-cors.html) — configuring CORS in Spring MVC.

OpenAPI tells developers how the API expects Bearer or OAuth2 credentials; Spring Security is the layer that actually validates tokens and decides access rights. Verify both the springdoc-generated document and runtime behavior using cases with no token, invalid token, insufficient scope, and sufficient scope. Only when both sides agree does Swagger UI become a trustworthy tool for testing the API.
