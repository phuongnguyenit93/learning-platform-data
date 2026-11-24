# Security Requirements at the Document Level and Operation Level

OpenAPI describes the authentication mechanisms clients must use to call an API through two separate parts: `components.securitySchemes` defines the security mechanisms, while `security` indicates which operations require which mechanisms. These two parts usually go together, yet they have distinct responsibilities. Merely defining a Bearer token or API key does not mean every endpoint requires credentials; the documentation must attach security requirements at the document or operation level.

OpenAPI allows placing `security` at the document root to apply by default to operations. An individual operation can override the general requirement—for example, a login or health check endpoint requiring no authentication. When using Springdoc, you can declare these using `@OpenAPIDefinition`, `@SecurityScheme`, `@SecurityRequirement`, `@Operation`, and `@SecurityRequirements`, or configure the OpenAPI model directly via a bean.

Crucially, security in OpenAPI only describes the contract for Swagger UI, client generators, and integrators. It does not configure Spring Security, issue tokens, or block requests at runtime.

## 1. Distinguishing Security Scheme and Security Requirement

A `Security Scheme` describes how clients provide credentials. For example:

- HTTP Bearer token in the `Authorization` header.
- HTTP Basic authentication.
- API key in a header, query parameter, or cookie.
- OAuth 2.0 with flows and scopes.
- OpenID Connect.

A `Security Requirement` references a defined scheme and specifies that the scheme must be used for an operation. In OpenAPI, schemes are stored under `components.securitySchemes`, while requirements reside in `security` at the document or operation level.

Condensed example:

```yaml
components:
  securitySchemes:
    bearerAuth:
      type: http
      scheme: bearer
      bearerFormat: JWT

security:
  - bearerAuth: []
```

In this example:

- `bearerAuth` is the scheme name.
- `type: http` and `scheme: bearer` describe HTTP Bearer authentication.
- `bearerFormat: JWT` is an informational hint for readers, not a token verification rule.
- Root-level `security` requires operations to use a Bearer token by default.
- The empty scope array `[]` is correct for HTTP Bearer; scopes are only meaningful for OAuth 2.0 or OpenID Connect.

The name `bearerAuth` in the requirement must match the key declared in `components.securitySchemes` exactly. This name is case-sensitive.

## 2. Document-level security

When most endpoints require the same authentication mechanism, declare `security` at the root to avoid repetition on every operation.

```yaml
openapi: 3.0.3
info:
  title: Order API
  version: 1.0.0
components:
  securitySchemes:
    bearerAuth:
      type: http
      scheme: bearer
      bearerFormat: JWT
security:
  - bearerAuth: []
paths:
  /api/orders:
    get:
      summary: List orders
      responses:
        '200':
          description: List of orders
  /api/orders/{id}:
    get:
      summary: View order
      responses:
        '200':
          description: Order details
```

Root-level `security` serves as the default for operations in the document. When an operation does not declare its own `security` property, it inherits the document-level requirement.

With the configuration above, Swagger UI knows operations require a Bearer token and displays the **Authorize** button. After the user enters a token, the UI sends requests with an `Authorization: Bearer ...` header to the selected server.

Do not treat root `security` as a runtime protection rule. Someone calling the API with cURL or a custom client can still send requests without opening Swagger UI. Spring Security must independently authenticate and reject invalid requests.

## 3. Operation-level security overrides the default

An operation may need a different security mechanism from the general requirement. When an operation declares `security`, that list replaces the document-level security requirement for that operation.

Example where the document defaults to requiring a Bearer token, but the login endpoint is public:

```yaml
security:
  - bearerAuth: []
paths:
  /api/auth/login:
    post:
      summary: Log in
      security: []
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/LoginRequest'
      responses:
        '200':
          description: Login successful
  /api/orders:
    get:
      summary: List orders
      responses:
        '200':
          description: List of orders
```

Here:

- `POST /api/auth/login` has `security: []`, meaning the operation requires no security scheme.
- `GET /api/orders` declares no custom security, so it continues to inherit `bearerAuth` from the root.

`security: []` is an empty array. It differs from omitting the `security` property from the operation altogether. Omitting the property means inheriting the root; an empty array means applying no security requirement to that operation.

### Endpoints allowing both anonymous and authenticated requests

If you want an operation to accept both unauthenticated users and users who already have a Bearer token, you can declare an anonymous option:

```yaml
security:
  - {}
  - bearerAuth: []
```

The empty object `{}` represents the option requiring no authentication. The other object represents the option using a Bearer token. The two options are alternatives.

This differs from `security: []`: an empty array removes all security requirements, whereas an array containing `{}` explicitly documents an anonymous option within the set of security alternatives. Only use this structure when the server truly accepts both types of requests.

## 4. OR and AND rules in Security Requirements

This is the most error-prone part when an operation supports multiple authentication mechanisms.

- Multiple objects in the `security` array express **OR**: the client can satisfy any one of the objects.
- Multiple scheme keys inside the same object express **AND**: the client must satisfy all schemes in that object.

### OR: Bearer token or API key

```yaml
security:
  - bearerAuth: []
  - tenantApiKey: []
```

The client can use either a Bearer token or an API key. Sending both is not mandatory.

### AND: Bearer token and API key simultaneously

```yaml
security:
  - bearerAuth: []
    tenantApiKey: []
```

The client must send both a Bearer token and a tenant API key to satisfy this requirement.

### Two options, where one option requires two schemes

```yaml
security:
  - bearerAuth: []
    tenantApiKey: []
  - partnerOAuth:
      - orders:read
```

The client can choose one of two approaches:

1. Send both a Bearer token and a tenant API key.
2. Use an OAuth2 token with the `orders:read` scope.

Do not place schemes in separate objects if you intend to require them simultaneously. YAML structure determines OR/AND logic, not the order of schemes.

## 5. Defining common Security Scheme types

### HTTP Bearer

```yaml
components:
  securitySchemes:
    bearerAuth:
      type: http
      scheme: bearer
      bearerFormat: JWT
```

Typical request format:

```http
Authorization: Bearer eyJhbGciOi...
```

### HTTP Basic

```yaml
components:
  securitySchemes:
    basicAuth:
      type: http
      scheme: basic
```

Clients send username/password credentials via HTTP Authorization Basic. Only use Basic over TLS/HTTPS; never place real passwords in documentation examples.

### API key in header

```yaml
components:
  securitySchemes:
    tenantApiKey:
      type: apiKey
      in: header
      name: X-Tenant-Key
```

Client sends:

```http
X-Tenant-Key: <TENANT_API_KEY>
```

### API key in query or cookie

OpenAPI also supports `in: query` and `in: cookie`:

```yaml
components:
  securitySchemes:
    queryApiKey:
      type: apiKey
      in: query
      name: api_key
    sessionCookie:
      type: apiKey
      in: cookie
      name: SESSION
```

API keys in queries are easily recorded in access logs, browser history, proxy logs, or referrer headers. Only choose this location if the system has a clear compatibility reason and key exposure risks have been assessed. Cookie authentication also depends on browser cookie policies and CSRF protection.

## 6. OAuth 2.0 and scopes

With OAuth 2.0, the Security Scheme declares flows and scopes issued by the authorization server. An operation's Security Requirement lists the needed scopes.

Authorization code flow example:

```yaml
components:
  securitySchemes:
    partnerOAuth:
      type: oauth2
      flows:
        authorizationCode:
          authorizationUrl: https://identity.example.com/oauth2/authorize
          tokenUrl: https://identity.example.com/oauth2/token
          scopes:
            orders:read: Read order information
            orders:write: Create and update orders
security:
  - partnerOAuth:
      - orders:read
```

In this example, the operation requires an OAuth2 token with the `orders:read` scope. If both scopes are needed, list both:

```yaml
security:
  - partnerOAuth:
      - orders:read
      - orders:write
```

Scopes in the same requirement form the set of required scopes. Scopes must be defined in the corresponding scheme's flow and match by name. For HTTP or API key schemes, the scope list must remain empty.

OpenID Connect uses `type: openIdConnect` together with `openIdConnectUrl`. Security Requirements can list scopes published by the provider. Distinguish OpenAPI scopes from internal Spring Security roles/authorities: they can be mapped to one another, but are not automatically synonymous.

## 7. Declaring Security Schemes and requirements with Springdoc annotations

Springdoc uses Swagger annotations to translate security metadata into OpenAPI.

Example declaring a Bearer scheme and a default document-level security requirement:

```java
import io.swagger.v3.oas.annotations.OpenAPIDefinition;
import io.swagger.v3.oas.annotations.info.Info;
import io.swagger.v3.oas.annotations.security.SecurityRequirement;
import io.swagger.v3.oas.annotations.security.SecurityScheme;
import io.swagger.v3.oas.annotations.enums.SecuritySchemeType;
import org.springframework.context.annotation.Configuration;

@Configuration
@OpenAPIDefinition(
    info = @Info(
        title = "Order API",
        version = "1.0.0",
        description = "Order management API"
    ),
    security = {
        @SecurityRequirement(name = "bearerAuth")
    }
)
@SecurityScheme(
    name = "bearerAuth",
    type = SecuritySchemeType.HTTP,
    scheme = "bearer",
    bearerFormat = "JWT"
)
class OpenApiSecurityConfiguration {
}
```

Expected output:

- `components.securitySchemes.bearerAuth` defines the Bearer scheme.
- Root-level `security` has the `bearerAuth` requirement.
- Operations without their own security declaration inherit the root requirement.

You can declare the scheme using an `OpenAPI` bean instead of `@SecurityScheme`, especially when building configuration dynamically from properties:

```java
import io.swagger.v3.oas.models.Components;
import io.swagger.v3.oas.models.OpenAPI;
import io.swagger.v3.oas.models.info.Info;
import io.swagger.v3.oas.models.security.SecurityRequirement;
import io.swagger.v3.oas.models.security.SecurityScheme;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class OpenApiBeanConfiguration {

    @Bean
    OpenAPI customOpenAPI() {
        return new OpenAPI()
            .info(new Info().title("Order API").version("1.0.0"))
            .components(new Components().addSecuritySchemes(
                "bearerAuth",
                new SecurityScheme()
                    .type(SecurityScheme.Type.HTTP)
                    .scheme("bearer")
                    .bearerFormat("JWT")
            ))
            .addSecurityItem(new SecurityRequirement().addList("bearerAuth"));
    }
}
```

Do not define the same scheme with both annotations and a bean unintentionally. Avoid creating two configuration sources with the same name but different types or parameters.

### Declaring an OAuth2 scheme with annotations

For OAuth2, `@SecurityScheme` can describe the corresponding flows and scopes:

```java
import io.swagger.v3.oas.annotations.enums.SecuritySchemeType;
import io.swagger.v3.oas.annotations.security.OAuthFlow;
import io.swagger.v3.oas.annotations.security.OAuthFlows;
import io.swagger.v3.oas.annotations.security.OAuthScope;
import io.swagger.v3.oas.annotations.security.SecurityScheme;

@SecurityScheme(
    name = "partnerOAuth",
    type = SecuritySchemeType.OAUTH2,
    flows = @OAuthFlows(
        authorizationCode = @OAuthFlow(
            authorizationUrl = "https://identity.example.com/oauth2/authorize",
            tokenUrl = "https://identity.example.com/oauth2/token",
            scopes = {
                @OAuthScope(name = "orders:read", description = "Read orders"),
                @OAuthScope(name = "orders:write", description = "Create and update orders")
            }
        )
    )
)
class OAuthSchemeConfiguration {
}
```

Then operations can reference scopes using `@SecurityRequirement(name = "partnerOAuth", scopes = {"orders:read"})`. Authorization/token URLs must be real endpoints of the identity provider; the example above only illustrates structure.

## 8. Dedicated security requirements for a single operation

If an operation needs a specific OAuth2 scope, declare security on the method:

```java
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.security.SecurityRequirement;
import org.springframework.web.bind.annotation.GetMapping;

@GetMapping("/api/orders")
@Operation(
    summary = "Read list of orders",
    security = {
        @SecurityRequirement(
            name = "partnerOAuth",
            scopes = {"orders:read"}
        )
    }
)
List<OrderResponse> listOrders() {
    return orderService.findAll();
}
```

The requirement on the operation replaces the root requirement for that operation. In the example, the operation uses `partnerOAuth` with the `orders:read` scope and does not simultaneously inherit `bearerAuth` from the root.

You can place `@SecurityRequirement` directly on a method instead of inside `@Operation`'s `security` attribute. Placing it at the controller level applies the requirement to the controller's operations via annotation processing; placing it inside `@OpenAPIDefinition.security` sets the document level.

When declaring multiple repeated `@SecurityRequirement` annotations, they represent alternative options (OR). To require multiple schemes simultaneously (AND), the OpenAPI Security Requirement Object must contain multiple schemes inside the same object. Newer Swagger annotations have `combine`/`SecurityRequirementEntry` attributes for combined cases; if using an older annotations version or wanting explicit representation, customize the OpenAPI model and inspect the output.

## 9. Disabling inherited security for public operations

This is an important case when a document has root `security`, yet certain endpoints like login, registration, or health checks do not need a token.

In OpenAPI, the standard representation is:

```yaml
paths:
  /api/health:
    get:
      security: []
      responses:
        '200':
          description: Service status
```

With Swagger annotations, use an empty `@SecurityRequirements` on the method to indicate the operation has no requirements and override higher-level requirements:

```java
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.security.SecurityRequirements;
import org.springframework.web.bind.annotation.GetMapping;

@GetMapping("/api/health")
@Operation(summary = "Check service status")
@SecurityRequirements
HealthResponse health() {
    return healthService.currentStatus();
}
```

Do not rely on `@Operation(security = {})` to clear global security. An empty annotation array may be interpreted as declaring no override and emit no `security` field on the operation. An empty `@SecurityRequirements` is used to produce an empty override; inspect the generated OpenAPI JSON and confirm the operation has `security: []`.

If your version of Swagger Core/Springdoc does not handle the empty annotation as expected, you can use an `OperationCustomizer` to set an empty security list on selected operations:

```java
import java.util.ArrayList;
import org.springdoc.core.customizers.OperationCustomizer;
import org.springframework.context.annotation.Bean;

@Bean
OperationCustomizer publicHealthSecurityOverride() {
    return (operation, handlerMethod) -> {
        if (handlerMethod.getMethod().getName().equals("health")) {
            operation.setSecurity(new ArrayList<>());
        }
        return operation;
    };
}
```

In a real application, mark operations with a dedicated annotation or check path/method instead of relying on method names. If you only want this applied inside one `GroupedOpenApi`, register the customizer on that group's builder. After customizing, confirm the operation has `security: []` in the target document.

## 10. Security requirements do not replace Spring Security

OpenAPI describes how clients must send credentials. Spring Security decides whether the server accepts the request. Both configurations must agree, yet remain independent.

Runtime configuration example:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class ApiSecurityConfiguration {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/api/health", "/api/auth/login").permitAll()
                .requestMatchers(HttpMethod.GET, "/api/orders/**").hasAuthority("SCOPE_orders:read")
                .requestMatchers("/api/admin/**").hasRole("ADMIN")
                .anyRequest().authenticated()
            )
            .oauth2ResourceServer(oauth2 -> oauth2.jwt(Customizer.withDefaults()))
            .build();
    }
}
```

This is an illustrative example for a Resource Server application using JWT; decoder, issuer, and authority mapping configurations must be set up for your actual identity provider. `hasAuthority("SCOPE_orders:read")` is a Spring Security rule, while `scopes: [orders:read]` in OpenAPI is client metadata. Ensure both sides reflect the deployed policy.

If OpenAPI marks an endpoint as requiring a Bearer token while Spring Security allows anonymous access, docs and runtime are inconsistent. If OpenAPI marks an endpoint public while Spring Security still requires login, Swagger UI will send unauthenticated requests and receive 401/403. Test both the document and actual requests.

## 11. Applying security per GroupedOpenApi

Each group produces a separate OpenAPI document. If all groups need a shared scheme, you can define the scheme in an OpenAPI bean or use a shared configuration mechanism compatible with your Springdoc version. If only one group needs a specific security requirement, attach a customizer to that group.

Example where only the admin group requires a Bearer token at the document level:

```java
import io.swagger.v3.oas.models.security.SecurityRequirement;
import io.swagger.v3.oas.models.security.SecurityScheme;
import org.springdoc.core.models.GroupedOpenApi;
import org.springframework.context.annotation.Bean;

@Bean
GroupedOpenApi adminApi() {
    return GroupedOpenApi.builder()
        .group("admin")
        .pathsToMatch("/api/admin/**")
        .addOpenApiCustomizer(openApi -> {
            if (openApi.getComponents() == null) {
                openApi.setComponents(new io.swagger.v3.oas.models.Components());
            }
            openApi.getComponents().addSecuritySchemes(
                "bearerAuth",
                new SecurityScheme()
                    .type(SecurityScheme.Type.HTTP)
                    .scheme("bearer")
                    .bearerFormat("JWT")
            );
            openApi.addSecurityItem(
                new SecurityRequirement().addList("bearerAuth")
            );
        })
        .build();
}
```

If the customizer adds a requirement but forgets to define the scheme in that same document, the requirement will reference a non-existent name. If the scheme is already added from shared configuration, do not add it twice; inspect the final group document.

For public operations inside the admin group, you can use an empty `@SecurityRequirements` or an operation customizer to override the root requirement. Groups are not runtime security boundaries: Spring Security must still protect each route per policy.

## 12. Checking Security in the OpenAPI document

After the application starts, inspect the default document:

```bash
curl -s http://localhost:8080/v3/api-docs \
  | jq '{schemes: .components.securitySchemes, security: .security}'
```

Inspect an operation's requirement:

```bash
curl -s http://localhost:8080/v3/api-docs \
  | jq '.paths["/api/orders"].get.security'
```

Verify a public operation has an empty override:

```bash
curl -s http://localhost:8080/v3/api-docs \
  | jq '.paths["/api/health"].get | has("security"), .security'
```

The expected result is `true` and `[]`. If the `security` field does not exist, the operation may still be inheriting the root requirement.

Inspect specific groups via `/v3/api-docs/{group}`. Do not assume schemes/requirements in the default document are necessarily present in every group; check every document exposed by Swagger UI.

## 13. Testing the contract and runtime

You should have tests for both layers:

1. The OpenAPI document has the expected security schemes and requirements.
2. Spring Security enforces the policy when requests have no token, a valid token, or a token missing scopes.

Example integration test verifying OpenAPI metadata:

```java
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
class OpenApiSecurityDocumentationTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void orderOperationRequiresBearerScheme() throws Exception {
        mockMvc.perform(get("/v3/api-docs"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.components.securitySchemes.bearerAuth.scheme")
                .value("bearer"))
            .andExpect(jsonPath("$.paths['/api/orders'].get.security[0].bearerAuth")
                .isArray());
    }

    @Test
    void healthOperationExplicitlyDisablesInheritedSecurity() throws Exception {
        mockMvc.perform(get("/v3/api-docs"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.paths['/api/health'].get.security").isArray())
            .andExpect(jsonPath("$.paths['/api/health'].get.security.length()")
                .value(0));
    }
}
```

For runtime, use separate tests to confirm `/api/orders` returns 401 without a token, returns the expected result with a valid token, and rejects tokens missing required scopes. The `/api/health` endpoint only responds publicly if Spring Security also configures `permitAll()`.

When testing with JSONPath, syntax may need adjustment depending on your test library version. What matters is checking that the `security` field exists and the array has the right elements or is empty; checking only `securitySchemes` is insufficient.

## 14. Common errors

| Symptom | Cause | Resolution |
|---|---|---|
| Swagger UI does not display Authorize | Only scheme defined without security requirements, or UI loads wrong document | Check `components.securitySchemes` and document/operation `security` |
| Requirement references non-existent scheme | Different key names or group missing scheme | Synchronize names and add scheme to the right document |
| Public endpoint still shows Bearer requirement | Operation lacks `security: []` override | Use empty `@SecurityRequirements` and verify output |
| `@Operation(security = {})` does not clear root security | Empty annotation array is not processed as an override | Use `@SecurityRequirements` or customizer to set an empty security list |
| Client must send both Bearer and API key when only one is needed | Two schemes are inside the same Security Requirement Object | Split into two separate objects to express OR |
| Client sends only one scheme while server requires both | Two schemes were declared as separate objects | Put both keys in the same object to express AND |
| OAuth2 token rejected despite being present | Missing scope, misspelled scope, or different runtime mapping | Reconcile scopes in OpenAPI with server authorities/claims |
| OpenAPI requires token while server allows anonymous | Missing authorization rule in Spring Security | Protect endpoint at runtime and add integration tests |
| Admin group lacks security | Customizer only edited default document or group lacks scheme | Use customizer on the right group and check group URL |
| API key appears as an unwanted query parameter | Scheme declared `in: query` instead of `header` | Choose the right scheme location matching the runtime contract |

## 15. Checklist for designing security at both levels

- [ ] Each security scheme has a unique name in `components.securitySchemes`.
- [ ] Schemes accurately describe authentication types and credential locations.
- [ ] Security requirements only reference defined schemes.
- [ ] Root `security` accurately reflects the document's default requirement.
- [ ] Operations requiring different authentication have appropriate requirement overrides.
- [ ] Public operations have `security: []` if inherited requirements must be cleared.
- [ ] Endpoints accepting anonymous or authenticated requests are described using `{}` and a scheme as OR options when appropriate.
- [ ] OR across objects and AND among schemes within one object are properly distinguished.
- [ ] OAuth2/OIDC scopes are declared and referenced with exact names.
- [ ] Authorization is not described as a regular header parameter.
- [ ] Each GroupedOpenApi has accurate schemes and requirements in its own document.
- [ ] Spring Security runtime enforces the same policy as OpenAPI.
- [ ] Checked `/v3/api-docs` and every `/v3/api-docs/{group}`.
- [ ] Tested anonymous, authenticated, and insufficient-permission requests.

`components.securitySchemes` defines how clients authenticate; `security` attaches that mechanism to the whole document or individual operations. Root requirements are inherited when an operation declares no override; `security: []` explicitly removes requirements for public operations. An array of multiple requirement objects expresses OR, while multiple schemes in the same object express AND. When Springdoc documentation and Spring Security runtime reflect the same policy, Swagger UI, client generators, and integrators know exactly which endpoints need credentials and which credential types are needed.

## References

- [OpenAPI Specification – Security Scheme Object](https://spec.openapis.org/oas/v3.1.1.html#security-scheme-object)
- [OpenAPI Specification – Security Requirement Object](https://spec.openapis.org/oas/v3.1.1.html#security-requirement-object)
- [Springdoc OpenAPI v2 – FAQ: Security schemes](https://springdoc.org/v2/faq.html)
- [Swagger Core – `@SecurityRequirement` Javadoc](https://docs.swagger.io/swagger-core/v2.2.53/apidocs/io/swagger/v3/oas/annotations/security/SecurityRequirement.html)
- [Swagger Core – `@SecurityRequirements` Javadoc](https://docs.swagger.io/swagger-core/v2.2.27/apidocs/io/swagger/v3/oas/annotations/security/SecurityRequirements.html)
