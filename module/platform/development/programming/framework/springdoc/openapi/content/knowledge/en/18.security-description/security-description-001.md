# Security Scheme Object and Security Requirement Object

An OpenAPI document needs to describe two distinct aspects of security: which authentication mechanisms the API supports and which operations require them. OpenAPI represents the mechanism definitions using the **Security Scheme Object** in `components.securitySchemes`; the application across the entire API or per operation is represented using the **Security Requirement Object** in the `security` property.

springdoc-openapi can generate these structures from swagger-annotations or from an `OpenAPI` bean. When designing, keep scheme names consistent between the definition and the requirement, accurately describe how clients send credentials, and inspect the generated specification. These objects describe the contract for tools and integrators; they do not automatically configure Spring Security authentication filters.

## 1. Two objects with different roles

A **Security Scheme Object** describes how a client provides credentials. For example: sending a bearer token in the `Authorization` header, sending an API key in the `X-API-Key` header, or using OAuth 2.0 or OpenID Connect.

A **Security Requirement Object** references one or more defined schemes to indicate which mechanism an operation requires. It does not redefine how authentication works and does not contain real tokens.

| Component | Location in OpenAPI | Question answered |
| --- | --- | --- |
| Security Scheme Object | `components.securitySchemes` | Which authentication mechanisms does the API support, and where does the client send credentials? |
| Security Requirement Object | `security` at the OpenAPI or Operation level | Which scheme does the API or operation require? |

Short example:

~~~yaml
components:
  securitySchemes:
    bearerAuth:
      type: http
      scheme: bearer
      bearerFormat: JWT

security:
  - bearerAuth: []
~~~

The `components.securitySchemes` section defines a scheme named `bearerAuth`. The `security` section requires clients to use that scheme for operations that inherit the global configuration. The name `bearerAuth` in the requirement must match the name declared in components exactly.

## 2. Types of Security Scheme Objects

OpenAPI 3.1.2 defines five main scheme types:

| `type` | Purpose | Key fields |
| --- | --- | --- |
| `apiKey` | API key sent via header, query, or cookie | `name`, `in` |
| `http` | HTTP Authentication such as Basic or Bearer | `scheme`, optionally `bearerFormat` |
| `oauth2` | Authentication/authorization via OAuth 2.0 | `flows` |
| `openIdConnect` | Sign-in based on OpenID Connect | `openIdConnectUrl` |
| `mutualTLS` | Client authentication using a TLS certificate | optional `description` |

`mutualTLS` is supported in OpenAPI 3.1. If your document or toolchain still uses OpenAPI 3.0.x, check compatibility before using this scheme type. Do not assume all validators and code generators handle every scheme identically.

## 3. API key via header, query, or cookie

For `apiKey`, OpenAPI requires two properties:

- `name`: the name of the header, query parameter, or cookie parameter that the client must send.
- `in`: the location of the key, taking one of the values `header`, `query`, or `cookie`.

Example of an API requiring the `X-API-Key` header:

~~~yaml
components:
  securitySchemes:
    partnerApiKey:
      type: apiKey
      in: header
      name: X-API-Key
      description: API key issued by the partner portal.

security:
  - partnerApiKey: []
~~~

The corresponding request includes the header:

~~~http
GET /api/partner/orders HTTP/1.1
Host: api.example.com
X-API-Key: <partner-api-key>
~~~

Do not put real API keys in OpenAPI, examples, or source code. The value in the request is only a placeholder so Swagger UI users can enter a key via the Authorize button.

An API key can be placed in a query parameter:

~~~yaml
components:
  securitySchemes:
    queryApiKey:
      type: apiKey
      in: query
      name: api_key
~~~

The request will look like `GET /api/orders?api_key=...`. This approach is generally less secure than a header because URLs can appear in access logs, browser history, analytics systems, and intermediary logs. Use it only when required by the contract or platform; prefer HTTPS and avoid logging key values.

An API key can also be passed via a cookie:

~~~yaml
components:
  securitySchemes:
    sessionKey:
      type: apiKey
      in: cookie
      name: SESSION_KEY
~~~

With cookies, also consider the `Secure`, `HttpOnly`, and `SameSite` attributes, domain, path, and the browser's cookie-sending policy. OpenAPI only describes the cookie name and location; it does not configure server-side cookie attributes.

## 4. HTTP Basic and Bearer authentication

For HTTP authentication, use `type: http` and specify `scheme`.

Basic authentication:

~~~yaml
components:
  securitySchemes:
    basicAuth:
      type: http
      scheme: basic
      description: HTTP Basic authentication.

security:
  - basicAuth: []
~~~

The client sends credentials in the header:

~~~http
Authorization: Basic <base64-credentials>
~~~

Base64 is only an encoding representation, not cryptographic encryption. Basic authentication must be used over HTTPS to prevent exposing credentials in transit. Do not include real usernames or passwords in the specification.

For a bearer token:

~~~yaml
components:
  securitySchemes:
    bearerAuth:
      type: http
      scheme: bearer
      bearerFormat: JWT
      description: Send the access token in the Authorization header.

security:
  - bearerAuth: []
~~~

The client sends:

~~~http
Authorization: Bearer <access-token>
~~~

`bearerFormat: JWT` is only a hint to let readers know the token typically uses the JWT format. It does not enforce that the token must be a JWT, does not verify the signature, issuer, audience, expiration, or claims, and does not configure a JWT decoder for the application. Those checks must be performed in the runtime authentication system.

Do not declare a bearer token using `type: apiKey` with `name: Authorization` if the API actually uses HTTP Bearer. Using `type: http`, `scheme: bearer` helps Swagger UI and other tools understand the standard mechanism properly.

## 5. OAuth 2.0 and the OAuth Flows Object

With `type: oauth2`, the Security Scheme Object must include `flows`. Each flow describes how the client obtains a token and which scopes the API supports. OpenAPI 3.1.2 defines four flows:

| Flow | Main URL fields | Scenario |
| --- | --- | --- |
| `authorizationCode` | `authorizationUrl`, `tokenUrl` | Application redirects the user to the authorization server, receives an authorization code, and exchanges it for a token |
| `clientCredentials` | `tokenUrl` | Backend service authenticates as a client |
| `password` | `tokenUrl` | Legacy flow using the user's username/password directly; should not be chosen for new designs |
| `implicit` | `authorizationUrl` | Legacy flow returning the token directly via the authorization response; not recommended for new designs |

Authorization code example:

~~~yaml
components:
  securitySchemes:
    ordersOAuth:
      type: oauth2
      flows:
        authorizationCode:
          authorizationUrl: https://identity.example.com/oauth2/authorize
          tokenUrl: https://identity.example.com/oauth2/token
          refreshUrl: https://identity.example.com/oauth2/refresh
          scopes:
            orders:read: Read orders
            orders:write: Create and update orders
            profile:read: Read basic profile information
~~~

`authorizationUrl` is where the client starts the authorization flow; `tokenUrl` is where the code is exchanged for a token; `refreshUrl` is an optional URL for obtaining a new token. OAuth endpoint URLs must use HTTPS. The `scopes` list maps scope names to short descriptions so clients know which permissions can be requested.

For user-facing applications running in a browser or on mobile devices, the Authorization Code Flow combined with PKCE is typically the preferred choice. OpenAPI describes the endpoints and scopes; enabling PKCE, client registration, redirect URIs, and token issuance policies must be configured on the authorization server and the corresponding Swagger UI/client.

Client credentials example for service-to-service communication:

~~~yaml
components:
  securitySchemes:
    serviceOAuth:
      type: oauth2
      flows:
        clientCredentials:
          tokenUrl: https://identity.example.com/oauth2/token
          scopes:
            inventory:read: Read inventory data
            inventory:write: Update inventory data
~~~

Do not use `password` or `implicit` for new systems unless there are special compatibility constraints. The OAuth 2.0 Security Best Current Practice recommends removing these flows in new designs; Authorization Code with PKCE is more suitable for user-facing applications.

## 6. OpenID Connect

OpenID Connect builds on OAuth 2.0 and adds a user identity layer. In OpenAPI, declare the scheme with `type: openIdConnect` and `openIdConnectUrl` pointing to the provider's discovery endpoint:

~~~yaml
components:
  securitySchemes:
    oidc:
      type: openIdConnect
      openIdConnectUrl: https://identity.example.com/.well-known/openid-configuration
      description: Sign in via OpenID Connect provider.

security:
  - oidc: []
~~~

The URL above is the discovery metadata address according to the identity provider's configuration. The discovery document provides information such as the issuer, authorization endpoint, token endpoint, and related endpoints. Use the provider's actual discovery URL; do not guess the path if the issuer has a custom structure.

With `openIdConnect` and `oauth2`, a Security Requirement Object can list the required scopes. If no specific scopes are required, the scope list can be empty.

## 7. Mutual TLS

Mutual TLS (mTLS) authenticates both the server and the client during the TLS handshake. The client presents a digital certificate; the server validates the certificate against its trust store and policy.

OpenAPI 3.1 represents this scheme as:

~~~yaml
components:
  securitySchemes:
    clientCertificate:
      type: mutualTLS
      description: Client must present a certificate issued by a partner-trusted CA.

security:
  - clientCertificate: []
~~~

There is no `name` or `in` field for mTLS. Certificate selection, trust chain validation, certificate revocation, and client identity mapping are TLS/runtime configurations at the gateway or server. Swagger UI cannot automatically generate or substitute a client certificate solely from the scheme definition.

## 8. Defining a Security Scheme with springdoc annotations

springdoc supports the `@SecurityScheme` annotation to add a scheme to `components.securitySchemes`. Example configuring bearer JWT:

~~~java
import org.springframework.context.annotation.Configuration;

import io.swagger.v3.oas.annotations.enums.SecuritySchemeType;
import io.swagger.v3.oas.annotations.security.SecurityScheme;

@Configuration
@SecurityScheme(
    name = "bearerAuth",
    type = SecuritySchemeType.HTTP,
    scheme = "bearer",
    bearerFormat = "JWT",
    description = "Access token sent in the Authorization header."
)
public class OpenApiSecurityConfiguration {
}
~~~

The name `bearerAuth` is the identifier in OpenAPI. Another name can be used, but the Security Requirement must reference that exact name.

An API key can be declared using an annotation:

~~~java
import org.springframework.context.annotation.Configuration;

import io.swagger.v3.oas.annotations.enums.SecuritySchemeIn;
import io.swagger.v3.oas.annotations.enums.SecuritySchemeType;
import io.swagger.v3.oas.annotations.security.SecurityScheme;

@Configuration
@SecurityScheme(
    name = "partnerApiKey",
    type = SecuritySchemeType.APIKEY,
    paramName = "X-API-Key",
    in = SecuritySchemeIn.HEADER,
    description = "Partner API key."
)
public class PartnerApiKeyConfiguration {
}
~~~

With OAuth2 authorization code:

~~~java
import org.springframework.context.annotation.Configuration;

import io.swagger.v3.oas.annotations.enums.SecuritySchemeType;
import io.swagger.v3.oas.annotations.security.SecurityScheme;
import io.swagger.v3.oas.annotations.security.OAuthFlow;
import io.swagger.v3.oas.annotations.security.OAuthFlows;
import io.swagger.v3.oas.annotations.security.OAuthScope;

@Configuration
@SecurityScheme(
    name = "ordersOAuth",
    type = SecuritySchemeType.OAUTH2,
    flows = @OAuthFlows(
        authorizationCode = @OAuthFlow(
            authorizationUrl = "https://identity.example.com/oauth2/authorize",
            tokenUrl = "https://identity.example.com/oauth2/token",
            scopes = {
                @OAuthScope(
                    name = "orders:read",
                    description = "Read orders"
                ),
                @OAuthScope(
                    name = "orders:write",
                    description = "Create and update orders"
                )
            }
        )
    )
)
public class OAuthOpenApiConfiguration {
}
~~~

Place the annotation on a configuration class scanned by Spring. Imports and enums must match the version of `swagger-annotations` managed by springdoc. When an annotation field is not available in the current version, check the dependency's Javadoc instead of adding unsupported attributes.

## 9. Defining a scheme with an OpenAPI bean

If you prefer configuring in Java instead of annotations, you can add a scheme to `Components` on an `OpenAPI` bean:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import io.swagger.v3.oas.models.Components;
import io.swagger.v3.oas.models.OpenAPI;
import io.swagger.v3.oas.models.security.SecurityScheme;

@Configuration
public class OpenApiSecurityConfiguration {

    @Bean
    public OpenAPI customOpenAPI() {
        return new OpenAPI()
            .components(new Components()
                .addSecuritySchemes(
                    "bearerAuth",
                    new SecurityScheme()
                        .type(SecurityScheme.Type.HTTP)
                        .scheme("bearer")
                        .bearerFormat("JWT")
                )
            );
    }
}
~~~

This code only defines the scheme. To require the scheme across the entire document, add a Security Requirement:

~~~java
import io.swagger.v3.oas.models.security.SecurityRequirement;

return new OpenAPI()
    .components(new Components()
        .addSecuritySchemes(
            "bearerAuth",
            new SecurityScheme()
                .type(SecurityScheme.Type.HTTP)
                .scheme("bearer")
                .bearerFormat("JWT")
        )
    )
    .addSecurityItem(
        new SecurityRequirement().addList("bearerAuth")
    );
~~~

In an application that already has an `OpenAPI` bean declaring `Info`, servers, tags, or other schemes, extend the existing bean and merge components. Do not create competing beans that manage the same part of the document if doing so makes the configuration hard to follow.

## 10. Security Requirement Object at the API-wide level

The `security` property at the OpenAPI level applies by default to operations in the document. Example:

~~~yaml
openapi: 3.1.0
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
  /orders:
    get:
      summary: List orders
      responses:
        '200':
          description: Success
~~~

In the example, the `/orders` operation inherits the global requirement. The empty array `[]` is the scheme's scope list; for HTTP Bearer, Basic, or API key, no OAuth scopes are declared, so an empty array is used.

If the API has multiple global alternative schemes, you can declare multiple Security Requirement Objects:

~~~yaml
security:
  - bearerAuth: []
  - partnerApiKey: []
~~~

This is an **OR** relationship: the client can use either a bearer token or an API key. Only one requirement object in the list needs to be satisfied.

## 11. Security Requirement Object at the operation level

An operation can declare its own `security` to override the global configuration. For example, an endpoint for reading orders requires the `orders:read` scope:

~~~yaml
paths:
  /orders:
    get:
      security:
        - ordersOAuth:
            - orders:read
      responses:
        '200':
          description: Success
~~~

If an operation requires multiple scopes from the same OAuth2 scheme, list the scopes in that scheme's array. Scope names must be declared in the corresponding flow and must match the scopes issued by the authorization server.

With springdoc, you can attach a requirement to an operation using `@SecurityRequirement`:

~~~java
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.security.SecurityRequirement;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class OrderController {

    @GetMapping("/api/orders")
    @Operation(
        summary = "List orders",
        security = @SecurityRequirement(
            name = "ordersOAuth",
            scopes = {"orders:read"}
        )
    )
    public List<OrderResponse> findAll() {
        return orderService.findAll();
    }
}
~~~

`@SecurityRequirement.name` must match a declared scheme name. `scopes` is used for OAuth2 or OpenID Connect; for HTTP Basic, Bearer, or API key, leave scopes empty.

If you want to apply a scheme to most of the API directly via annotation, you can declare security on `@OpenAPIDefinition`:

~~~java
import org.springframework.context.annotation.Configuration;

import io.swagger.v3.oas.annotations.OpenAPIDefinition;
import io.swagger.v3.oas.annotations.security.SecurityRequirement;

@Configuration
@OpenAPIDefinition(
    security = @SecurityRequirement(name = "bearerAuth")
)
public class OpenApiGlobalSecurityConfiguration {
}
~~~

This example assumes the `bearerAuth` scheme has already been defined via `@SecurityScheme` or an `OpenAPI` bean. Operations will inherit the global requirement; an operation with its own security configuration will override that requirement.

## 12. Distinguishing OR and AND in Security Requirements

This is the most important rule when reading the `security` array:

- Multiple objects in the `security` array are alternative options (**OR**).
- Multiple schemes in the same object must be satisfied simultaneously (**AND**).

OR example: accept either a bearer token or an API key:

~~~yaml
security:
  - bearerAuth: []
  - partnerApiKey: []
~~~

AND example: require both a bearer token and a tenant key:

~~~yaml
components:
  securitySchemes:
    bearerAuth:
      type: http
      scheme: bearer
    tenantKey:
      type: apiKey
      in: header
      name: X-Tenant-Key

security:
  - bearerAuth: []
    tenantKey: []
~~~

In the AND example, the client must send both:

~~~http
Authorization: Bearer <access-token>
X-Tenant-Key: <tenant-key>
~~~

If written as two separate objects as follows:

~~~yaml
security:
  - bearerAuth: []
  - tenantKey: []
~~~

the result is OR, meaning only one of the two schemes is required. Misplacing a hyphen or YAML indentation can completely change the published policy.

## 13. Public endpoints and overriding global security

If a document has global `security` but an endpoint allows anonymous access, there are two representations to distinguish:

`security: []` placed on an operation means no scheme is required and overrides inherited security:

~~~yaml
paths:
  /health:
    get:
      security: []
      responses:
        '200':
          description: Service status
~~~

`security: [{}]` represents an empty requirement, meaning anonymous access is allowed:

~~~yaml
paths:
  /catalog:
    get:
      security:
        - {}
        - bearerAuth: []
      responses:
        '200':
          description: Product catalog
~~~

In the second example, the operation allows either unauthenticated access or a bearer token. If you only want to publish an endpoint with no security at all, `security: []` is the clearer approach.

When an operation has its own `security` property, it replaces the OpenAPI-level requirement; it is not automatically appended to the global requirement. Inspect the JSON output to make sure public operations do not accidentally inherit authentication requirements.

## 14. Security Scheme is not Spring Security configuration

`@SecurityScheme` and `security` only generate OpenAPI metadata. They do not:

- Create users, passwords, API keys, or JWTs.
- Validate token signatures or expiration.
- Issue OAuth scopes or check user permissions.
- Configure the filter chain, CORS, CSRF, or sessions in Spring Security.
- Reject requests when a client does not send credentials.

For example, declaring `bearerAuth` in OpenAPI does not automatically protect a controller. The application must still configure a Spring Security resource server or an appropriate authentication mechanism, verify token issuer/audience/signature, and enforce endpoint authorization.

Conversely, having Spring Security protect endpoints does not guarantee springdoc will automatically infer schemes and requirements accurately. Declare OpenAPI documentation explicitly, then verify it matches the runtime policy.

Swagger UI provides an Authorize button so users can enter credentials or execute a configured OAuth flow. This button only helps send test requests; it does not replace the authorization server or the API's authentication mechanism.

## 15. Verifying Security Schemes and Requirements in the specification

After starting the application, open `/v3/api-docs` or the corresponding group endpoint. In the JSON, verify:

1. `components.securitySchemes` defines the scheme with the expected name.
2. `type` and required fields match the scheme type.
3. The API key has the right `name` and `in`.
4. HTTP auth has the right `scheme`; a bearer token is not declared as a query parameter.
5. OAuth2 has the right flow, authorization URL, token URL, and scopes.
6. OpenID Connect has the right discovery URL.
7. Requirements reference the exact scheme name.
8. Scopes in requirements are declared in the corresponding flow.
9. Global security and operation security have the intended scope.
10. Public operations have `security: []` or an empty requirement as intended.
11. The OR/AND rules match how clients must send credentials.

You can download the document with curl:

~~~bash
curl -s http://localhost:8080/v3/api-docs
~~~

Then open Swagger UI and check:

- Does the Authorize button display the scheme with the right name and type?
- Is the bearer token sent in the `Authorization` header with the `Bearer` prefix?
- Is the API key sent in the right header/query/cookie?
- Does the OAuth flow request the right authorization URL, token URL, and scopes?
- Do public operations avoid automatically sending credentials when not needed?

Finally, call the real endpoints with missing credentials, invalid credentials, and valid credentials. Compare actual statuses against the responses described in OpenAPI. This is a separate verification step from checking the Swagger UI interface.

## 16. Common errors and troubleshooting

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| Authorize button does not show the scheme | Only the requirement was declared without defining the scheme, or the annotation was not scanned | Check `components.securitySchemes` in `/v3/api-docs` |
| Operation does not show a lock icon | Missing global/operation `security` or wrong requirement name | Match the name in `security` against the component name |
| Swagger UI sends the token in the wrong header | Scheme was mistakenly declared as apiKey or used the wrong `scheme` | Use `type: http`, `scheme: bearer` for bearer tokens |
| OAuth does not display scopes | Scopes were not declared in the flow or the requirement uses a different name | Synchronize scope names between the flow and operation requirement |
| Public endpoint still shows a lock icon | Operation inherits global security | Set `security: []` on the public operation |
| Only one credential is accepted even though both are needed | Two schemes were placed as two separate requirement objects | Place both schemes in the same object to express AND |
| Swagger UI allows choosing one scheme while the API requires both | The requirement list was misunderstood regarding OR/AND | Check array structure and YAML indentation |
| `bearerFormat: JWT` but invalid tokens still pass through Swagger UI | bearerFormat is only a display hint | Validate JWTs at runtime using a resource server/security filter |
| mTLS definition is rejected by the validator | Document is outputting OpenAPI 3.0.x or using an older toolchain | Use a version supporting OpenAPI 3.1 and check the validator |
| Spring Security already protects the API but the docs have no Authorize button | Runtime security and OpenAPI metadata are separate configurations | Add `@SecurityScheme`/OpenAPI bean and Security Requirement |

## 17. Design principles

Place each scheme in `components.securitySchemes` with a short, stable name and clearly describe how clients send credentials. Use `apiKey` for keys in a header, query, or cookie; use `http` for Basic/Bearer; use `oauth2` or `openIdConnect` for centralized authorization systems; use `mutualTLS` when the API actually authenticates clients via certificates and the document is compatible with OpenAPI 3.1.

Set global `security` when most operations share the same policy. Use operation-level requirements when an endpoint has different scopes, allows multiple authentication methods, or is public. Always remember: requirement objects in the array are OR, whereas schemes within the same object are AND. When using OAuth2/OIDC, keep scopes synchronized across flows, requirements, and the authorization server.

After configuring, verify the OpenAPI JSON, Swagger UI, and actual security behavior of the application. A good contract accurately describes the mechanism clients must use while reflecting exactly what Spring Security or the gateway enforces.

## 18. Official references

- [OpenAPI Specification 3.1.2 — Security Scheme Object](https://spec.openapis.org/oas/v3.1.2.html#security-scheme-object) — scheme types, required fields, OAuth flows, and examples.
- [OpenAPI Specification 3.1.2 — Security Requirement Object](https://spec.openapis.org/oas/v3.1.2.html#security-requirement-object) — scheme reference rules, OR/AND, and anonymous access.
- [springdoc-openapi v2 FAQ — Define SecurityScheme](https://springdoc.org/v2/faq.html) — declaring `@SecurityScheme`, `@SecurityRequirement`, and OpenAPI beans.
- [Swagger Annotations — SecurityScheme](https://docs.swagger.io/swagger-core/v2.2.25/apidocs/io/swagger/v3/oas/annotations/security/SecurityScheme.html) — annotation attributes for schemes.
- [Swagger Annotations — SecurityRequirement](https://docs.swagger.io/swagger-core/v2.2.25/apidocs/io/swagger/v3/oas/annotations/security/SecurityRequirement.html) — annotation for attaching security requirements to APIs.
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700.html) — OAuth 2.0 security recommendations, including deprecating flows no longer suitable for new designs.

The Security Scheme Object describes how authentication works; the Security Requirement Object specifies where and how that mechanism applies. Separating these two layers helps springdoc generate clear documentation, helps Swagger UI send credentials properly, and helps development teams reconcile the OpenAPI contract with the enforced security policy.
