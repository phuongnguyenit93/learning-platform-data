# Scope Lists and Their Meaning for Operations

OAuth 2.0 allows applications to request access permissions by individual scopes. An access token can be granted one or more scopes such as `products:read`, `products:write`, or `orders:cancel`. APIs use these scopes to determine which group of actions a client is permitted to perform. OpenAPI can describe the scope list in a security scheme and specify required scopes for each operation, helping integrators understand which permissions are required when calling an endpoint.

In springdoc-openapi, this description is generated from annotations such as `@SecurityScheme`, `@OAuthFlow`, `@OAuthScope`, and `@SecurityRequirement`, or declared in OpenAPI YAML. Two responsibilities must be clearly distinguished: the OpenAPI specification publishes the security requirements for clients; Spring Security and the resource server actually validate tokens and access permissions when requests reach the application.

This lesson focuses on defining scopes, linking scopes to operations, reading the OR/AND semantics of Security Requirement Objects, and inspecting the generated documentation.

## Objectives

After this lesson, you can:

- Explain scopes in OAuth 2.0 and OpenID Connect.
- Distinguish scopes, roles, authorities, and permissions on a specific resource.
- Define scopes in an OpenAPI OAuth2 flow.
- Link scopes to individual operations using Security Requirement Objects.
- Understand OR relationships between requirement objects and AND relationships between schemes within one object.
- Use `@SecurityScheme`, `@OAuthScope`, and `@SecurityRequirement` with springdoc-openapi.
- Design scope lists following the principle of least privilege and consistent naming.
- Synchronize OpenAPI documentation with permission-checking policies in Spring Security.
- Test scopes in `/v3/api-docs` and test access permissions at runtime.

## 1. What is a scope?

A scope is a string identifying a permission boundary that a client requests when obtaining an access token. The authorization server decides whether to grant those scopes based on the client, user, consent, policy, and grant type. The resource server receives the token and checks the permissions expressed in the token before allowing the operation.

For example, a product management API might define:

| Scope | Meaning |
|---|---|
| `products:read` | Read product information |
| `products:write` | Create or update products |
| `products:delete` | Delete products |
| `orders:read` | Read orders |
| `orders:cancel` | Cancel orders |

A client that only needs to view product listings can request `products:read`. An admin application may need both `products:read` and `products:write`. A token does not necessarily contain every scope the API knows; the authorization server grants only the permissions approved for that token issuance.

Scopes typically appear in an access token as a `scope` or `scp` claim, depending on the authorization server and configuration. The value may be a space-separated string of scopes or a string array. OpenAPI describes scope names and meanings; it does not mandate a single way for the authorization server to serialize claims in tokens.

### Scope is not a role

Scopes and roles may both participate in access decisions, yet they serve different purposes:

| Concept | Question answered | Example |
|---|---|---|
| Scope | Which group of actions is the token authorized to perform? | `products:read` |
| Role | Which business group does the user or principal belong to? | `PRODUCT_MANAGER` |
| Authority | Which permission does Spring Security use to evaluate rules? | `SCOPE_products:read` |
| Resource permission | Is the principal permitted to act on a specific record? | Allowed to edit products belonging to the current tenant |

An authorization server can map roles into scopes when issuing tokens, or an application can convert claims into authorities. Do not assume role names and scope names are identical. Nor do scopes replace per-record permission checks: a token with `products:read` does not imply the user can read every product across all tenants.

### Scope is not a security scheme name

A security scheme is an authentication mechanism declared in `components.securitySchemes`, such as `oauth2`, `bearerAuth`, or `apiKeyAuth`. A scope is a permission inside an OAuth2 flow or listed in a security requirement.

Example:

- `oauth2` is the scheme name.
- `products:read` is the scope.
- The operation requires the `oauth2` scheme with the `products:read` scope.

The scheme name in the security requirement must match the name declared in components exactly. Scopes must also match scope names defined in the OAuth2 flow.

## 2. Defining scopes in an OAuth2 flow

OpenAPI places scopes inside a security scheme of type `oauth2`, within the corresponding flow. Each flow can publish its own scope set and descriptions.

Authorization code flow example:

~~~yaml
components:
  securitySchemes:
    oauth2:
      type: oauth2
      flows:
        authorizationCode:
          authorizationUrl: https://auth.example.com/oauth2/authorize
          tokenUrl: https://auth.example.com/oauth2/token
          scopes:
            products:read: Read product information
            products:write: Create and update products
            products:delete: Delete products
            orders:read: Read orders
            orders:cancel: Cancel orders
~~~

In the example:

- `oauth2` is the security scheme name.
- `authorizationCode` is the OAuth2 flow.
- `authorizationUrl` is the endpoint redirecting users to the authorization server.
- `tokenUrl` is the endpoint exchanging an authorization code for a token.
- `scopes` is a map between scope names and descriptions shown to integrators.

The scope name is the map key; the description is the value. Do not use a Vietnamese description as a scope name if the API needs a stable identifier. The client sends the scope name in the token request; the description only helps readers understand that permission.

### Scopes per flow

OpenAPI allows declaring different flows:

- `authorizationCode`: commonly used for applications where users sign in and need the authorization code flow.
- `clientCredentials`: commonly used for service-to-service communication.
- `implicit`: legacy flow, should not be chosen for new applications.
- `password`: legacy resource owner password credentials grant, should not be used for new designs.

Each flow has its own `scopes` map. If a scheme publishes multiple flows, ensure operations only require scopes meaningful for flows clients can use. For example, a server application might request `products:read` using client credentials, while a user-facing app might receive the same scope via the authorization code flow if the authorization server supports it.

Do not declare scopes in OpenAPI and assume the authorization server knows to issue them automatically. Scopes must be configured and supported on the authorization server; the resource server must also enforce them per policy.

## 3. Security Requirement Object and scope lists

OpenAPI links scopes to an operation using a Security Requirement Object. For OAuth2, this object uses the security scheme name as the key and the list of required scopes as the value:

~~~yaml
security:
  - oauth2:
      - products:read
~~~

This means the operation requires an access token via the `oauth2` scheme and the token must have the `products:read` scope.

If the operation needs multiple scopes:

~~~yaml
security:
  - oauth2:
      - products:read
      - inventory:read
~~~

Within a single requirement object, all scopes listed for an OAuth2 scheme are required scopes. The client needs a token satisfying the entire list per authorization server and resource server semantics.

### Scopes must match definitions

If `products:read` is required on an operation, that scope should be declared in `scopes` of the corresponding OAuth2 flow:

~~~yaml
components:
  securitySchemes:
    oauth2:
      type: oauth2
      flows:
        clientCredentials:
          tokenUrl: https://auth.example.com/oauth2/token
          scopes:
            products:read: Read product information
~~~

Avoid typos or using different names for the same permission, such as declaring `product:read` while the operation requires `products:read`. Tools may still generate documentation, yet integrators will request a scope not described in the flow.

For security schemes other than OAuth2 or OpenID Connect, the scope list must be empty. For example, HTTP bearer authentication or API keys do not use scopes in Security Requirement Objects:

~~~yaml
security:
  - bearerAuth: []
  - apiKeyAuth: []
~~~

Do not attach `products:read` to `bearerAuth` simply because a JWT access token contains a scope claim. If you want OpenAPI to express scopes per the standard, declare an appropriate OAuth2 or OpenID Connect scheme. A bearer scheme only describes the mechanism for sending a bearer token.

## 4. OR and AND semantics in security

A common point of confusion is that OpenAPI uses two collection levels to express logical relationships:

- A `security` list containing multiple Security Requirement Objects: the objects are alternatives (OR).
- A single Security Requirement Object containing multiple security schemes: all schemes within that object must be satisfied (AND).

Example where clients can choose either a bearer token or an API key:

~~~yaml
security:
  - bearerAuth: []
  - apiKeyAuth: []
~~~

This is OR: satisfying either authentication method is sufficient.

Example where an operation requires both an OAuth2 scope and an API key:

~~~yaml
security:
  - oauth2:
      - products:write
    apiKeyAuth: []
~~~

This is AND: the OAuth2 token must have `products:write` and the request must simultaneously send the API key.

If the same OAuth2 scheme requires multiple scopes:

~~~yaml
security:
  - oauth2:
      - products:write
      - inventory:read
~~~

The client must have both scopes in the token. If having either one of the scopes is sufficient, express it as two requirement objects:

~~~yaml
security:
  - oauth2:
      - products:write
  - oauth2:
      - inventory:read
~~~

These are two alternatives. The resource server must enforce policies matching this contract; the documentation only describes the logic clients must satisfy.

### Quick-reference table

| Structure | Meaning |
|---|---|
| One object, one scheme, one scope | Requires one scope |
| One object, one scheme, multiple scopes | Requires all listed scopes |
| One object, multiple schemes | Requires all schemes |
| Multiple objects in `security` list | Accepts any one of the options |
| One empty object `{}` in list | Allows anonymous access as an option |
| `security: []` on operation | Requires no security for that operation |

Do not treat the requirement list as an additive permission list. Placing two separate objects with `products:read` and `products:write` gives OR semantics, not requiring both.

## 5. Scopes at document level and operation level

You can place `security` at the OpenAPI root to apply by default to operations:

~~~yaml
security:
  - oauth2:
      - products:read
~~~

Operations inherit the default security if they do not declare their own `security`. When an operation has a `security` property, that property replaces the root requirement for that operation.

Example:

~~~yaml
paths:
  /api/products:
    get:
      summary: Read product list
      security:
        - oauth2:
            - products:read
    post:
      summary: Create product
      security:
        - oauth2:
            - products:write
  /api/health:
    get:
      summary: Check service health
      security: []
~~~

In the example, GET `/api/products` requires `products:read`, POST `/api/products` requires `products:write`, while `/api/health` is public even if the root sets default security. `security: []` clearly expresses that the operation requires no security.

### Distinguishing omitting security vs. allowing anonymous access

The following two configurations have different meanings:

~~~yaml
security: []
~~~

An empty list means no security requirement applies to the operation.

~~~yaml
security:
  - {}
  - oauth2:
      - products:read
~~~

A list with an empty object allows anonymous access as one option, while also accepting the OAuth2 option with the stated scope. This represents an endpoint that can be called publicly or authenticated depending on the request.

Choose the configuration matching actual server behavior. Do not use an empty object to document an endpoint that requires sign-in.

## 6. Declaring scopes with springdoc annotations

You can define an OAuth2 security scheme using swagger-core annotations read by springdoc when generating documentation:

~~~java
import io.swagger.v3.oas.annotations.security.OAuthFlow;
import io.swagger.v3.oas.annotations.security.OAuthFlows;
import io.swagger.v3.oas.annotations.security.OAuthScope;
import io.swagger.v3.oas.annotations.security.SecurityScheme;
import io.swagger.v3.oas.annotations.enums.SecuritySchemeType;
import org.springframework.context.annotation.Configuration;

@Configuration
@SecurityScheme(
    name = "oauth2",
    type = SecuritySchemeType.OAUTH2,
    flows = @OAuthFlows(
        authorizationCode = @OAuthFlow(
            authorizationUrl = "https://auth.example.com/oauth2/authorize",
            tokenUrl = "https://auth.example.com/oauth2/token",
            scopes = {
                @OAuthScope(
                    name = "products:read",
                    description = "Read product information"
                ),
                @OAuthScope(
                    name = "products:write",
                    description = "Create and update products"
                ),
                @OAuthScope(
                    name = "products:delete",
                    description = "Delete products"
                )
            }
        )
    )
)
public class OpenApiSecurityConfiguration {
}
~~~

This annotation creates `components.securitySchemes.oauth2` and declares scopes in the authorization code flow. The URLs in the example are illustrative addresses; replace them with your authorization server's real endpoints. Never place a client secret in OpenAPI annotations or published documentation.

The annotations belong to the `io.swagger.v3.oas.annotations.security` package, while `SecuritySchemeType` belongs to `io.swagger.v3.oas.annotations.enums`. Package names can be auto-imported by your IDE from the swagger-annotations dependency managed by springdoc.

### Attaching scopes to each operation

Use `@Operation` to describe required scopes for an endpoint:

~~~java
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.security.SecurityRequirement;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class ProductController {

    @GetMapping("/api/products")
    @Operation(
        summary = "Read product list",
        security = @SecurityRequirement(
            name = "oauth2",
            scopes = {"products:read"}
        )
    )
    public List<ProductResponse> list() {
        return productService.findAll();
    }

    @PostMapping("/api/products")
    @Operation(
        summary = "Create product",
        security = @SecurityRequirement(
            name = "oauth2",
            scopes = {"products:write"}
        )
    )
    public ProductResponse create(@RequestBody CreateProductRequest request) {
        return productService.create(request);
    }
}
~~~

The GET operation requires `products:read`; the POST operation requires `products:write`. `@SecurityRequirement.name` must match the scheme name `oauth2`, while `scopes` holds scope names, not scope descriptions.

The controller snippet above focuses on security annotations; in a real application, declare constructor injection for `ProductService` and the DTOs `ProductResponse` and `CreateProductRequest`. Also import `org.springframework.web.bind.annotation.RequestBody` for the body parameter.

### Scopes displayed in Swagger UI

When Swagger UI reads an OAuth2 scheme with a `scopes` map, the Authorize dialog can display the scopes with descriptions for users to select during OAuth2 authorization. An operation's security requirement indicates which scopes are required in the contract. Swagger UI does not grant permissions itself: the authorization server still decides which scopes are issued to the client and user.

For Authorize to work, the application also needs appropriate OAuth client configuration such as client ID, redirect URL, and PKCE depending on client type. Do not place client secrets in public documentation or JavaScript running in browsers.

If an operation needs multiple scopes simultaneously, list them in the same annotation:

~~~java
@Operation(
    summary = "Export inventory report",
    security = @SecurityRequirement(
        name = "oauth2",
        scopes = {"products:read", "inventory:read"}
    )
)
~~~

This corresponds to one requirement object with one OAuth2 scheme and two required scopes. It does not mean the client can pick either one of the two scopes.

### Multiple authentication alternatives via annotations

`@SecurityRequirements` is a container annotation for declaring multiple security requirements. Each separate requirement in the list is an alternative option (OR):

~~~java
import io.swagger.v3.oas.annotations.security.SecurityRequirement;
import io.swagger.v3.oas.annotations.security.SecurityRequirements;

@GetMapping("/api/partner/products")
@SecurityRequirements({
    @SecurityRequirement(
        name = "oauth2",
        scopes = {"products:read"}
    ),
    @SecurityRequirement(name = "partnerApiKey")
})
public List<ProductResponse> partnerProducts() {
    return productService.findAll();
}
~~~

The document expresses OAuth2 with scope `products:read` or API key `partnerApiKey`. The client only needs to satisfy one of the two requirement objects. If you want multiple schemes required simultaneously (AND), inspect the final OpenAPI structure; declaring multiple `@SecurityRequirement` annotations does not automatically build an AND object.

To express AND across multiple schemes, OpenAPI YAML shows it most clearly:

~~~yaml
security:
  - oauth2:
      - products:write
    partnerApiKey: []
~~~

A single requirement object contains both schemes, so the request needs a token with the scope and an API key. If you must construct this structure in Java, use a customizer on the OpenAPI model and test the JSON output rather than relying on annotation interpretation.

### Scopes at controller and method levels

Swagger annotations allow placing security metadata at the type or method level. When used together, verify the final operation in `/v3/api-docs` to see how annotations are inherited or replaced in your project's version of swagger-core/springdoc. For APIs with differing permissions per endpoint, declaring explicitly on each `@Operation` lets readers directly see that operation's scopes.

## 7. OpenID Connect scopes

OpenID Connect builds on OAuth 2.0 and uses scopes to request user identity information. Common standard scopes:

- `openid`: required for a request to be an OpenID Connect authentication request.
- `profile`: requests supported user profile claims.
- `email`: requests supported email information.
- `address` and `phone`: request address or phone claim groups if supported by the provider.

OpenAPI can declare an OpenID Connect scheme using a discovery URL:

~~~yaml
components:
  securitySchemes:
    oidc:
      type: openIdConnect
      openIdConnectUrl: https://auth.example.com/.well-known/openid-configuration
~~~

Operations can require OIDC scopes:

~~~yaml
security:
  - oidc:
      - openid
      - profile
      - email
~~~

With `openIdConnect`, scopes are listed in the security requirement using the provider's scope names. There is no `flows.*.scopes` map in this OpenAPI scheme like in an OAuth2 scheme; discovery metadata is fetched from `openIdConnectUrl`.

OIDC scopes such as `profile` or `email` describe permission to request identity claims. They do not automatically grant permission to read business data such as products or orders. If an API needs business permissions, use API scopes defined by the authorization server, or clearly document how the provider combines OIDC scopes with API scopes.

## 8. Designing manageable scope lists

Scope lists should reflect API actions and integration needs. A readable naming pattern is `resource:action`:

| Group | Suggested scope | Example operation |
|---|---|---|
| Products | `products:read` | GET `/api/products`, GET `/api/products/{id}` |
| Products | `products:write` | POST `/api/products`, PUT `/api/products/{id}` |
| Products | `products:delete` | DELETE `/api/products/{id}` |
| Orders | `orders:read` | GET `/api/orders` |
| Orders | `orders:cancel` | POST `/api/orders/{id}/cancel` |
| Reports | `reports:read` | GET `/api/reports/sales` |

This is a convention, not mandatory OAuth2 syntax. Some systems use dots or hyphens; what matters is that names are stable, consistent, and supported by the authorization server.

### Scope naming principles

1. Use short, stable names describing a clear group of actions.
2. Separate read and write permissions when clients have different needs.
3. Create dedicated scopes only for sensitive actions such as delete, approve, refund, or cancel.
4. Avoid creating one scope per URL when operations share the same business permission.
5. Avoid overly broad scopes like `admin:all` if narrower least-privilege scopes can express the permission.
6. Never embed dynamic user IDs, tenant IDs, or resource IDs into scopes; those values belong in token claims or resource permission checks.
7. Keep casing and delimiters identical across the authorization server, resource server, and OpenAPI.
8. Write scope descriptions in terms of actions clients are permitted to perform, not internal role names.

OAuth2 scope names are identifier tokens and should be treated as case-sensitive. `products:read` and `Products:Read` should not be considered the same scope. Avoid renaming published scopes without a compatibility plan for existing clients and tokens.

### Avoiding overly broad or overly granular scopes

Overly broad scopes grant clients more permissions than needed. Overly granular scopes force the authorization server, documentation, and clients to manage a large, confusing list. Start from business action groups and split further when real authorization requirements arise.

For example, `products:manage` could cover read, create, update, and delete. If many clients only need read or update, `products:read`, `products:write`, and `products:delete` enable better least-privilege grants.

Conversely, there is rarely a need to create `products:read:name`, `products:read:price`, and `products:read:description` if the API has no requirement for per-field permission separation. Masking sensitive fields may call for dedicated policies or DTOs rather than creating a scope per property.

## 9. Synchronizing OpenAPI scopes with Spring Security

OpenAPI annotations neither grant scopes to tokens nor block requests. They only describe the contract for clients. At runtime, the resource server must validate the token, convert scopes into authorities, and check those authorities before executing the operation.

With Spring Security Resource Server using JWT, the default `JwtGrantedAuthoritiesConverter` can read the `scope` or `scp` claim and convert each scope into an authority prefixed with `SCOPE_`. For example, a token with scope `products:read` corresponds to authority `SCOPE_products:read` under default configuration.

You can protect methods using method security:

~~~java
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class ProductController {

    @GetMapping("/api/products")
    @PreAuthorize("hasAuthority('SCOPE_products:read')")
    @Operation(
        summary = "Read product list",
        security = @SecurityRequirement(
            name = "oauth2",
            scopes = {"products:read"}
        )
    )
    public List<ProductResponse> list() {
        return productService.findAll();
    }
}
~~~

For `@PreAuthorize` to take effect, enable method security:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@Configuration
@EnableMethodSecurity
class MethodSecurityConfiguration {
}
~~~

If using URL authorization instead of method security, check authorities by HTTP method and path in `SecurityFilterChain`. Whichever approach you choose, runtime rules must match the scopes described in OpenAPI.

### Distinguishing 401 and 403

- `401 Unauthorized`: the request lacks valid credentials; the token is missing, expired, or cannot be authenticated.
- `403 Forbidden`: the principal is authenticated but lacks the authority/scope required for the operation.

The status name `401` can be confused with the everyday meaning of the word "Unauthorized"; in HTTP semantics, it indicates missing or invalid authentication credentials. `403` means the server understood the request but refuses access.

### Checking both scopes and resource permissions

Scopes typically represent permissions at the action-group level. The application must still verify:

- Whether the principal belongs to the tenant owning the resource.
- Whether the user is allowed to read the specific order.
- Whether the record is in a state allowing update or cancellation.
- Whether the user has access to data belonging to the current business unit or customer.

For instance, `products:write` authorizes the product-writing action group, yet the service must still check whether the caller is allowed to edit the product with that specific ID. Never use scopes as the sole mechanism for ownership checks or tenant isolation.

### When scope claims use a different format

Some identity providers place permissions in custom claims or use different claim names. In that case, configure `JwtAuthenticationConverter`/`JwtGrantedAuthoritiesConverter` to convert claims into consistent authorities. If tokens emit `permissions: ["products:read"]` while Spring Security only reads `scope` or `scp`, the `SCOPE_products:read` rule will not match automatically.

When changing converters, test with real tokens or JWT fixtures. Do not change scope names in OpenAPI merely to hide mapping differences; make the contract clear between the authorization server and resource server.

## 10. Complete OpenAPI example for multiple operations

The following example describes three operations with different scopes:

~~~yaml
openapi: 3.0.3
info:
  title: Product API
  version: 1.0.0
components:
  securitySchemes:
    oauth2:
      type: oauth2
      flows:
        authorizationCode:
          authorizationUrl: https://auth.example.com/oauth2/authorize
          tokenUrl: https://auth.example.com/oauth2/token
          scopes:
            products:read: Read product information
            products:write: Create and update products
            products:delete: Delete products
paths:
  /api/products:
    get:
      summary: Read product list
      security:
        - oauth2:
            - products:read
      responses:
        '200':
          description: Product list
    post:
      summary: Create product
      security:
        - oauth2:
            - products:write
      responses:
        '201':
          description: Product created
  /api/products/{id}:
    delete:
      summary: Delete product
      security:
        - oauth2:
            - products:delete
      responses:
        '204':
          description: Product deleted
        '403':
          description: Token lacks required scope
~~~

When integrators view the documentation:

- GET `/api/products` displays the `products:read` requirement.
- POST `/api/products` displays the `products:write` requirement.
- DELETE `/api/products/{id}` displays the `products:delete` requirement.

If operations have multiple responses, document both authentication and authorization errors according to actual behavior. A `403` response does not appear automatically just because an operation has scopes; declare the response with annotations or shared response configuration if the API actually returns that status.

## 11. Checking scopes in the generated document

After adding annotations, call:

~~~http
GET /v3/api-docs
~~~

In the JSON, inspect two regions:

1. `components.securitySchemes.oauth2.flows.authorizationCode.scopes` contains scope names and descriptions.
2. Operation `paths` contain `security` with the right scheme and scopes.

Example of expected document fragment:

~~~json
{
  "components": {
    "securitySchemes": {
      "oauth2": {
        "type": "oauth2",
        "flows": {
          "authorizationCode": {
            "authorizationUrl": "https://auth.example.com/oauth2/authorize",
            "tokenUrl": "https://auth.example.com/oauth2/token",
            "scopes": {
              "products:read": "Read product information",
              "products:write": "Create and update products"
            }
          }
        }
      }
    }
  },
  "paths": {
    "/api/products": {
      "get": {
        "security": [
          {
            "oauth2": [
              "products:read"
            ]
          }
        ]
      }
    }
  }
}
~~~

Scheme and scope names must match between components and operations. If a security requirement references `oauth2` while components only contain `oauth`, Swagger UI cannot link the scheme properly.

### Testing with MockMvc

You can verify documented scopes in `/v3/api-docs`:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class ProductSecurityDocumentationTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void documentsProductReadScope() throws Exception {
        mockMvc.perform(get("/v3/api-docs"))
            .andExpect(status().isOk())
            .andExpect(jsonPath(
                "$.components.securitySchemes.oauth2.flows.authorizationCode.scopes['products:read']"
            ).value("Read product information"))
            .andExpect(jsonPath(
                "$.paths['/api/products'].get.security[0].oauth2[0]"
            ).value("products:read"));
    }
}
~~~

JSONPath uses bracket notation for keys containing colons. If documentation is split into groups, call the corresponding `/v3/api-docs/{group}` endpoint and check scopes in that specific group.

Main imports for the test:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
~~~

## 12. Testing access permissions at runtime

Documentation testing does not replace authorization testing. You must verify that requests with matching scopes are allowed and requests missing scopes are rejected.

With Spring Security Test and the JWT request post-processor, a test can assign authorities directly:

~~~java
import org.springframework.security.core.authority.SimpleGrantedAuthority;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.jwt;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@Test
void allowsProductReadAuthority() throws Exception {
    mockMvc.perform(get("/api/products")
            .with(jwt().authorities(
                new SimpleGrantedAuthority("SCOPE_products:read")
            )))
        .andExpect(status().isOk());
}

@Test
void deniesRequestWithoutProductReadAuthority() throws Exception {
    mockMvc.perform(get("/api/products")
            .with(jwt().authorities(
                new SimpleGrantedAuthority("SCOPE_orders:read")
            )))
        .andExpect(status().isForbidden());
}
~~~

The example assumes the endpoint is protected by `@PreAuthorize` or URL authorization and the test context configures the resource server. Import `spring-security-test`, `jwt()` from `SecurityMockMvcRequestPostProcessors`, and `SimpleGrantedAuthority`. If the endpoint uses method security, enable `@EnableMethodSecurity` in the configuration loaded by the test.

With URL authorization, use matching request matchers. If the test uses `@WebMvcTest`, import the security configuration and mock required services; if using `@SpringBootTest`, load the full application configuration.

Testing with direct authorities verifies Spring Security rules. To verify actual claim mapping, add tests for `JwtAuthenticationConverter` or use JWT fixtures containing `scope`/`scp` claims resembling tokens issued by the authorization server.

### Suggested test matrix

| Token/request | Expected result | What to verify |
|---|---|---|
| No token | `401` | Resource server requires authentication |
| Valid token with `products:read` | `200` on GET | Read scope mapped properly |
| Valid token with only `orders:read` | `403` on product GET | No cross-resource permission granted |
| Valid token with `products:write` | `201` on POST | Write scope mapped properly |
| Valid token with only `products:read` | `403` on POST | Read scope does not grant write permission |
| Token with right scope but different tenant | Per policy, usually `403` | Separate tenant/resource permission check |

Exact status codes also depend on exception handlers and resource server configuration. Verify the application's actual outcomes and describe corresponding responses in OpenAPI.

## 13. Common errors when describing scopes

| Error | Consequence | Fix |
|---|---|---|
| Using scope name as security scheme name | Swagger UI cannot find a matching scheme | Declare a separate scheme like `oauth2`; scopes are like `products:read` |
| Operation requires a scope not declared in the flow | Clients do not know what the scope means | Synchronize keys in `flows.*.scopes` and operation requirements |
| Placing multiple scopes in two separate requirement objects when all are required | OpenAPI interprets as OR; client only needs one option | Place the scopes in the same requirement object |
| Placing two scopes in the same object when either one is enough | OpenAPI states both are required | Create two requirement objects to express OR |
| Putting scopes into a bearer scheme | Does not match security scheme scope semantics | Use an OAuth2/OIDC scheme to describe scopes properly |
| Declaring scopes only in OpenAPI | Docs state permissions are needed, yet server does not check them | Configure authorization on the resource server |
| Checking only scopes while skipping tenant/ownership | Token with broad scope can access out-of-scope data | Check resource permissions in the service/policy |
| Confusing `security: []` with an empty object | Public operation or login requirement has wrong intent | Use `[]` to remove security; `{}` to allow anonymous as an option |
| Using overly broad scopes | Clients receive more permissions than needed | Split scopes by business actions and least-privilege principles |
| Renaming scopes without managing compatibility | Legacy clients may receive 403 or fail to obtain tokens | Provide a transition period and update authorization server and clients |
| Scopes in token fail to map to `SCOPE_...` authorities | `hasAuthority` rules fail to match | Check claims and JwtAuthenticationConverter configuration |
| Class and method annotations yield unexpected results | Operation receives wrong security requirements | Inspect final JSON at `/v3/api-docs` |

## 14. Managing scope changes and API compatibility

Scopes are part of the contract between clients, the authorization server, and the resource server. Changing scopes can impact clients even when URLs and response schemas remain unchanged.

### Adding a new scope

Adding a new scope is usually compatible if a new operation uses that scope and existing clients do not need to call the new operation. If a new scope is attached to an existing operation already in use, clients may need to request tokens with additional permissions.

For example, an operation previously required only `products:read`, and then requires both `products:read` and `inventory:read`. This is a change that tightens access conditions; existing clients may receive 403 even with valid tokens.

### Renaming or removing a scope

Never rename a scope currently used by clients without a transition plan. A rollout path may include:

1. Declare the new scope on the authorization server and in OpenAPI.
2. Temporarily allow the resource server to accept both old and new scopes under a defined policy.
3. Update clients to request the new scope.
4. Monitor tokens and clients still using the old scope.
5. Remove the old scope only after the compatibility period ends and usage is verified.

Do not keep old scopes indefinitely if they represent broad permissions or no longer match policy. The transition plan needs a deadline and an owner.

### Increasing and reducing required permissions

Adding a scope to a requirement within the same object usually makes the operation require additional permissions (AND). Adding a new requirement object can open an additional authentication alternative (OR), changing semantics in a different direction. When reviewing OpenAPI diffs, read the entire collection structure rather than merely comparing scope counts.

If reducing required permissions, verify whether the resource server actually accepts tokens with fewer scopes. Do not let documentation describe minimal permissions while runtime code still demands the broader legacy scope.

## 15. Workflow for reconciling documentation and runtime

When adding or changing scopes for an operation, follow this sequence:

1. Identify the business action and which clients need to call the operation.
2. Choose an existing scope or design a new scope following least-privilege principles.
3. Declare the scope with a description in the OAuth2 flow or verify provider-supported OIDC scopes.
4. Attach the scope to the operation using `@SecurityRequirement` or OpenAPI YAML.
5. Configure the authorization server so it can issue the scope for the right clients/grants.
6. Configure the resource server to convert scope claims into authorities.
7. Protect the endpoint with URL authorization or method security.
8. Check resource and tenant permissions separately if required by business rules.
9. Call `/v3/api-docs` to verify schemes, scopes, and requirements.
10. Test tokens with the scope, missing the scope, invalid tokens, and no-token cases.
11. Update `401`/`403` responses in OpenAPI if the endpoint actually returns those statuses.
12. Evaluate compatibility with active clients before release.

## 16. Comprehensive practice exercise

Build a security description for a product and order management API:

1. Define an OAuth2 authorization code flow named `oauth2` with scopes `products:read`, `products:write`, `products:delete`, `orders:read`, and `orders:cancel`.
2. Attach `products:read` to GET `/api/products`.
3. Attach `products:write` to POST and PUT `/api/products`.
4. Attach `products:delete` to DELETE `/api/products/{id}`.
5. Attach `orders:read` to GET `/api/orders`.
6. Attach `orders:cancel` to POST `/api/orders/{id}/cancel`.
7. Create an operation needing both `products:read` and `inventory:read` simultaneously; express both scopes in the same requirement object.
8. Create an operation accepting either OAuth2 `products:read` or an API key; verify the two requirement objects are expressed as OR.
9. Set default security at the root and create a health endpoint with `security: []`.
10. Use Spring Security to convert scopes in JWTs into authorities and protect endpoints.
11. Write tests for tokens with the right scope, missing scope, and expired or invalid tokens.
12. Inspect `/v3/api-docs` to confirm scope descriptions and security requirements of each operation.
13. Reconcile OpenAPI against the authorization server and runtime rules, then fix any discrepancies.

### Completion criteria

- [ ] OAuth2 scheme has flows and scope list fully described.
- [ ] Each operation requires the exact scopes matching its business action.
- [ ] Scope names in operations match defined scopes exactly.
- [ ] Properly distinguished OR across requirement objects from AND within a single object.
- [ ] No scopes attached to bearer/API key schemes with incorrect semantics.
- [ ] Default security and public operations are accurately documented.
- [ ] Spring Security enforces the same policy as OpenAPI.
- [ ] Tokens missing scopes are rejected and tokens with appropriate scopes are allowed.
- [ ] Tenant/resource permissions are checked beyond scopes when needed.
- [ ] Tests verify both `/v3/api-docs` and runtime behavior.
- [ ] Scope changes are evaluated for compatibility with existing clients.

## Continue learning

After this lesson, combine scopes with OAuth2 flows, OpenID Connect discovery, JWT claim mapping, and root/operation-level security requirements. When changing operation permissions, review OpenAPI, authorization server configuration, resource server configuration, and integration tests together so clients receive an accurate contract.
