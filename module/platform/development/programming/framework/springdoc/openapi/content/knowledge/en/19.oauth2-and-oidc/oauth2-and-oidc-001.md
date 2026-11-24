# OAuth Flows Object and Description Configuration URLs

OpenAPI describes OAuth2 using an **OAuth Flows Object**. This object indicates which flows the API supports and the authorization server URLs used in those flows. With Springdoc, this declaration is typically created using `@SecurityScheme`, `@OAuthFlows`, and `@OAuthFlow`.

The three common URLs serve different roles: `authorizationUrl` directs the user to the authorization endpoint, `tokenUrl` is where the client exchanges an authorization code or grant credentials for a token, and `refreshUrl` describes the URL used during refresh token exchange according to the flow supported by the provider. These URLs belong to the OAuth2 description configuration, not the root URL of the REST API.

## 1. What is the OAuth Flows Object?

In OpenAPI 3, an OAuth2 security scheme contains the `flows` property. This is an OAuth Flows Object, which can describe one or more flows that the API supports.

The flows are defined by the following keys:

| Flow | Purpose | Important URLs |
| --- | --- | --- |
| `implicit` | Legacy flow that returns an access token directly via the authorization response | `authorizationUrl` |
| `password` | Client sends the user's credentials to the token endpoint | `tokenUrl` |
| `clientCredentials` | Application authenticates using the client's own credentials | `tokenUrl` |
| `authorizationCode` | User grants permission, client receives a code and exchanges it for a token | `authorizationUrl`, `tokenUrl` |

Each flow is an OAuth Flow Object. This object can contain:

- `authorizationUrl`: URL of the authorization endpoint.
- `tokenUrl`: URL of the token endpoint.
- `refreshUrl`: URL used during obtaining/refreshing a token with a refresh token, if described separately.
- `scopes`: list of scopes supported by the flow, along with a description for each scope.

In Java annotations, `@OAuthFlows` contains attributes corresponding to the flow names: `implicit`, `password`, `clientCredentials`, and `authorizationCode`. Each attribute takes an `@OAuthFlow`.

## 2. Distinguishing OAuth2 URLs

| Property | Role | Path Example |
| --- | --- | --- |
| `authorizationUrl` | Browser or user-agent redirects the user here to begin authorization | `https://identity.example.com/oauth2/authorize` |
| `tokenUrl` | Client sends a grant to receive an access token; can be used for authorization code, client credentials, or refresh grant depending on provider configuration | `https://identity.example.com/oauth2/token` |
| `refreshUrl` | URL used for refresh token exchange when the provider publishes a suitable endpoint | `https://identity.example.com/oauth2/refresh` |

These URLs usually belong to an identity provider or authorization server. For example, `https://api.example.com` might be the REST API server, while `https://identity.example.com/oauth2/authorize` and `/oauth2/token` are OAuth2 endpoints.

Do not put a Spring MVC controller URL into `authorizationUrl` or `tokenUrl`. Those endpoints do not handle business requests like `/api/books`; they perform the token issuance flow.

## 3. Which fields are required in each flow?

According to the OpenAPI OAuth2 Flow Object structure:

| Flow | `authorizationUrl` | `tokenUrl` | `refreshUrl` |
| --- | --- | --- | --- |
| `implicit` | Required | Not used | Optional |
| `password` | Not used | Required | Optional |
| `clientCredentials` | Not used | Required | Optional |
| `authorizationCode` | Required | Required | Optional |

`refreshUrl` is optional. If the authorization server uses the token endpoint itself to handle the refresh token grant, the documentation may not need a separate refresh URL; if the provider has a separate refresh endpoint, describe that URL. The specific meaning and usage of the refresh endpoint depend on the provider's contract. Follow the official documentation of the identity provider rather than inferring paths from the flow name.

Do not declare a dummy URL just to fill out the annotation. The flow must reflect the endpoints that the authorization server actually provides.

## 4. Declaring the authorization code flow with Springdoc

Authorization Code is a common choice for applications where users log in. For public client applications such as SPAs or mobile apps, PKCE should be used according to the authorization server configuration.

Example configuration for Spring Boot 3 and Springdoc 2.x:

```java
package com.example.config;

import io.swagger.v3.oas.annotations.OpenAPIDefinition;
import io.swagger.v3.oas.annotations.enums.SecuritySchemeType;
import io.swagger.v3.oas.annotations.info.Info;
import io.swagger.v3.oas.annotations.security.OAuthFlow;
import io.swagger.v3.oas.annotations.security.OAuthFlows;
import io.swagger.v3.oas.annotations.security.OAuthScope;
import io.swagger.v3.oas.annotations.security.Scopes;
import io.swagger.v3.oas.annotations.security.SecurityScheme;
import org.springframework.context.annotation.Configuration;

@Configuration
@OpenAPIDefinition(
    info = @Info(title = "Books API", version = "1.0.0")
)
@SecurityScheme(
    name = "oauth2",
    type = SecuritySchemeType.OAUTH2,
    description = "OAuth2 Authorization Code flow",
    flows = @OAuthFlows(
        authorizationCode = @OAuthFlow(
            authorizationUrl = "https://identity.example.com/oauth2/authorize",
            tokenUrl = "https://identity.example.com/oauth2/token",
            refreshUrl = "https://identity.example.com/oauth2/refresh",
            scopes = @Scopes({
                @OAuthScope(name = "books:read", description = "Read book information"),
                @OAuthScope(name = "books:write", description = "Create and update books")
            })
        )
    )
)
public class OpenApiOAuthConfig {}
```

In this example, `authorizationUrl` and `tokenUrl` are the two required endpoints for the Authorization Code flow. `refreshUrl` is declared because the example assumes the provider has a separate refresh endpoint. If the system uses a shared token endpoint for the refresh grant, adjust according to the provider's contract.

`@OAuthScope` creates each scope along with its description. `@Scopes` groups them into a list of scopes for the flow. Scope names must match the scopes actually supported by the authorization server and the API.

## 5. Attaching security requirements and scopes to operations

After defining the scheme, an operation references the scheme name using `@SecurityRequirement`:

```java
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.security.SecurityRequirement;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class BookController {

    @GetMapping("/api/books")
    @Operation(
        summary = "List books",
        security = @SecurityRequirement(
            name = "oauth2",
            scopes = {"books:read"}
        )
    )
    public String listBooks() {
        return "books";
    }
}
```

The name `oauth2` in the requirement must match `name = "oauth2"` in `@SecurityScheme`. The scope `books:read` must exist in the `scopes` of the corresponding flow. If the scheme name or scope differs, the documentation may reference a nonexistent configuration or cause Swagger UI/client generators to misunderstand the required permissions.

The requirement only describes the permissions that the operation requires. Spring Security or the resource server still has to verify the access token and check authorities/scopes when a request arrives at the application.

## 6. Describing the client credentials flow

Client Credentials is typically used for service-to-service communication when no end user is directly involved. This flow requires `tokenUrl` and does not require `authorizationUrl`:

```java
@SecurityScheme(
    name = "serviceOAuth",
    type = SecuritySchemeType.OAUTH2,
    description = "OAuth2 Client Credentials for system integration",
    flows = @OAuthFlows(
        clientCredentials = @OAuthFlow(
            tokenUrl = "https://identity.example.com/oauth2/token",
            scopes = @Scopes({
                @OAuthScope(name = "inventory:read", description = "Read inventory"),
                @OAuthScope(name = "inventory:sync", description = "Sync inventory")
            })
        )
    )
)
```

An operation can reference the scheme and scope:

```java
@Operation(
    summary = "Read inventory",
    security = @SecurityRequirement(
        name = "serviceOAuth",
        scopes = {"inventory:read"}
    )
)
```

`clientCredentials` has no step redirecting the user to an authorization endpoint. The client sends its own credentials to the token endpoint as configured by the authorization server.

Do not put real `client_id` or `client_secret` values into annotations, OpenAPI examples, or documentation. Secret values must be managed using a secret store or runtime environment security configuration.

## 7. Password and implicit flows in modern documentation

OpenAPI still defines `password` and `implicit` to describe legacy OAuth2 systems:

```java
@SecurityScheme(
    name = "legacyPasswordOAuth",
    type = SecuritySchemeType.OAUTH2,
    flows = @OAuthFlows(
        password = @OAuthFlow(
            tokenUrl = "https://identity.example.com/oauth2/token",
            scopes = @Scopes({
                @OAuthScope(name = "profile:read", description = "Read profile")
            })
        )
    )
)
```

The implicit flow only needs `authorizationUrl`:

```java
@SecurityScheme(
    name = "legacyImplicitOAuth",
    type = SecuritySchemeType.OAUTH2,
    flows = @OAuthFlows(
        implicit = @OAuthFlow(
            authorizationUrl = "https://identity.example.com/oauth2/authorize",
            scopes = @Scopes({
                @OAuthScope(name = "profile:read", description = "Read profile")
            })
        )
    )
)
```

These are examples to recognize the OpenAPI structure, not recommendations for new designs. Resource Owner Password Credentials (password grant) and Implicit flow are no longer recommended for new applications; prefer Authorization Code with PKCE for applications with users and Client Credentials for service-to-service communication.

If an existing system still supports these two legacy flows, the documentation should accurately describe the actual state and include a migration plan. Do not advertise a flow merely because the annotation allows declaring it.

## 8. Multiple flows in the same OAuth2 scheme

An OAuth Flows Object can contain multiple flows if the authorization server and API actually support them. For example, one scheme describing Authorization Code for users and Client Credentials for services:

```java
@SecurityScheme(
    name = "platformOAuth",
    type = SecuritySchemeType.OAUTH2,
    flows = @OAuthFlows(
        authorizationCode = @OAuthFlow(
            authorizationUrl = "https://identity.example.com/oauth2/authorize",
            tokenUrl = "https://identity.example.com/oauth2/token",
            scopes = @Scopes({
                @OAuthScope(name = "orders:read", description = "Read orders")
            })
        ),
        clientCredentials = @OAuthFlow(
            tokenUrl = "https://identity.example.com/oauth2/token",
            scopes = @Scopes({
                @OAuthScope(name = "orders:sync", description = "Sync orders")
            })
        )
    )
)
```

In this example, the two flows share the same token endpoint but have different purposes and sets of scopes. Not every identity provider enables both flows for the same client; the client and corresponding permissions must be configured at the authorization server.

If the two client types have completely different policies, audiences, or endpoints, you can split them into two separate security schemes so Swagger UI and client generators present the choice clearly.

## 9. How is OpenAPI YAML generated?

From the annotations above, Springdoc generates a structure similar to:

```yaml
components:
  securitySchemes:
    oauth2:
      type: oauth2
      description: OAuth2 Authorization Code flow
      flows:
        authorizationCode:
          authorizationUrl: https://identity.example.com/oauth2/authorize
          tokenUrl: https://identity.example.com/oauth2/token
          refreshUrl: https://identity.example.com/oauth2/refresh
          scopes:
            books:read: Read book information
            books:write: Create and update books
paths:
  /api/books:
    get:
      security:
        - oauth2:
            - books:read
```

Points to verify:

1. The scheme is under `components.securitySchemes` and has `type: oauth2`.
2. The flow is placed under the right key, such as `authorizationCode` or `clientCredentials`.
3. The URLs appear in the right fields and point to the right endpoints.
4. `scopes` is a map from scope name to description.
5. The security requirement references the right scheme name and scopes.

This is a condensed example; actual documentation also contains `info`, `servers`, paths, and API responses.

## 10. Distinguishing OAuth flow URLs from the API server URL

OpenAPI has the `servers` property to describe the base URL of the API. OAuth2 URLs live inside the flow object and point to the authorization server. The two groups of URLs do not replace each other:

```yaml
servers:
  - url: https://api.example.com
components:
  securitySchemes:
    oauth2:
      type: oauth2
      flows:
        authorizationCode:
          authorizationUrl: https://identity.example.com/oauth2/authorize
          tokenUrl: https://identity.example.com/oauth2/token
          scopes: {}
```

- `servers.url` is the base address where clients call operations such as `/api/books`.
- `authorizationUrl` is where the authorization process begins.
- `tokenUrl` is where a grant is exchanged for a token.
- `refreshUrl` is a separate refresh URL if published by the authorization server.

If you switch environments from staging to production, both the API server and OAuth endpoints may change. Configure and verify each URL group separately.

## 11. Distinguishing `authorizationUrl` from the redirect/callback URL

`authorizationUrl` is the authorization server endpoint to which the browser navigates to begin authorization. `redirect_uri` is the client's callback address, where the authorization server redirects the user back with the authorization code or corresponding result.

The redirect URI is not a property of the OAuth Flow Object in OpenAPI. It is configured on the OAuth client and registered with the identity provider. With Swagger UI, the OAuth callback path is usually the UI's dedicated redirect endpoint, which can be configured via Swagger UI's `oauth2RedirectUrl` option or the corresponding Springdoc property.

Examples of URLs with different roles:

| URL | Role |
| --- | --- |
| `https://identity.example.com/oauth2/authorize` | Authorization endpoint (`authorizationUrl`) |
| `https://identity.example.com/oauth2/token` | Token endpoint (`tokenUrl`) |
| `https://docs.example.com/swagger-ui/oauth2-redirect.html` | Swagger UI/client callback (`redirect_uri`) |

The authorization server must register the exact redirect URI used by the client. Do not put the Swagger UI callback into `authorizationUrl`; doing so causes the browser to call the wrong endpoint and breaks the OAuth flow.

## 12. Distinguishing OAuth2 flows from the OpenID Connect discovery URL

OpenID Connect builds on OAuth2 but has its own security scheme in OpenAPI: `type: openIdConnect`. This scheme uses `openIdConnectUrl` to point to the provider's discovery document, typically the `/.well-known/openid-configuration` endpoint.

Example:

```yaml
components:
  securitySchemes:
    oidc:
      type: openIdConnect
      openIdConnectUrl: https://identity.example.com/.well-known/openid-configuration
```

`openIdConnectUrl` is not `authorizationUrl`, `tokenUrl`, or `refreshUrl`. The OIDC discovery document provides metadata such as the authorization endpoint, token endpoint, JWKS URI, and provider capabilities. If declaring an `openIdConnect` scheme, do not put OAuth Flow Object URLs into the `openIdConnectUrl` field.

## 13. Environment-specific URLs and OpenAPI customization

Java annotations require attribute values to be compile-time constants. Therefore, you cannot put a Spring configuration placeholder such as `${OAUTH_TOKEN_URL}` directly into `@OAuthFlow` and expect the annotation to read the value from the environment.

If environments use different URLs, you can:

- Use `OpenApiCustomizer` to update URLs in the OpenAPI model from Spring configuration.
- Create separate documentation per environment or group when the published contract needs to differ.
- Use build/deployment configuration to generate documentation with values substituted before release.

Example idea for updating the authorization code flow with `OpenApiCustomizer` in Springdoc 2.x:

```java
import io.swagger.v3.oas.models.security.OAuthFlow;
import io.swagger.v3.oas.models.security.SecurityScheme;
import org.springdoc.core.customizers.OpenApiCustomizer;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class OAuthDocsCustomizerConfig {

    @Bean
    OpenApiCustomizer oauthUrlsCustomizer(
            @Value("${docs.oauth.authorization-url}") String authorizationUrl,
            @Value("${docs.oauth.token-url}") String tokenUrl) {

        return openApi -> {
            if (openApi.getComponents() == null
                    || openApi.getComponents().getSecuritySchemes() == null) {
                return;
            }

            SecurityScheme scheme = openApi.getComponents()
                .getSecuritySchemes().get("oauth2");
            if (scheme == null || scheme.getFlows() == null) {
                return;
            }

            OAuthFlow flow = scheme.getFlows().getAuthorizationCode();
            if (flow != null) {
                flow.setAuthorizationUrl(authorizationUrl);
                flow.setTokenUrl(tokenUrl);
            }
        };
    }
}
```

Example `application.yml`:

```yaml
docs:
  oauth:
    authorization-url: https://identity.example.com/oauth2/authorize
    token-url: https://identity.example.com/oauth2/token
```

If using multiple `GroupedOpenApi` beans, make sure the customizer is applied to each group document that needs updating; how global and group-level customizers are registered depends on the Springdoc version. Check each `/v3/api-docs/{group}` endpoint after configuration.

Do not let production documentation accidentally point to a staging authorization server or vice versa. URLs in OpenAPI are public information for clients, so they must be verified alongside environment configuration before release.

## 14. URLs must be valid and secure

OAuth2 URLs in documentation should meet these rules:

1. Use HTTPS in real environments to protect authorization codes, tokens, and exchanged data.
2. Use official endpoints published by the authorization server; do not guess `/authorize`, `/token`, or `/refresh` paths.
3. Do not embed client secrets, access tokens, refresh tokens, or API keys into URLs.
4. Avoid query parameters containing sensitive information or values that can expire.
5. Verify that URLs are reachable from the browser/client in the deployment environment.
6. Keep hostnames, paths, and endpoint versions synchronized across documentation, OAuth client configuration, and the authorization server.
7. If there are multiple tenants or realms, state the corresponding URLs clearly and do not mix endpoints across tenants.

`authorizationUrl`, `tokenUrl`, and `refreshUrl` are metadata describing endpoints. Springdoc does not call these endpoints, verify TLS certificates, authenticate clients, or guarantee that the server is running.

## 15. Swagger UI configuration is a separate part

The OAuth Flow Object describes the OAuth2 capabilities of the API. For Swagger UI to perform the login flow, the UI's OAuth client configuration must match the authorization server.

Examples of information Swagger UI may need:

- A dedicated Client ID for Swagger UI.
- Default scopes requested by the UI.
- Swagger UI's redirect URI registered with the identity provider.
- PKCE for public clients if supported and required by the authorization server.

These values belong to Swagger UI's OAuth client configuration, not all of which are properties of `@OAuthFlow`. Do not put a confidential client's client secret in browser-executed JavaScript or OpenAPI documentation. For public clients, do not use a client secret as if it could be kept secret.

In Springdoc, Swagger UI OAuth options are configured separately under `springdoc.swagger-ui.oauth.*`; the UI callback URL is also a separate setting. Exact property names should be checked against the Springdoc/Swagger UI version the project is using.

## 16. Verifying the generated flow configuration

After starting the application, open `/v3/api-docs` or `/v3/api-docs.yaml` and locate `components.securitySchemes`. Check:

- The scheme has `type: oauth2`.
- The scheme key matches the name referenced by `@SecurityRequirement`.
- The flow is under the right key, such as `authorizationCode`.
- `authorizationUrl` and `tokenUrl` do not have their roles swapped.
- `refreshUrl` appears only when there is an appropriate endpoint.
- Scopes have accurate names and descriptions.
- Operations reference the right scheme and request only declared scopes.
- URLs point to the right environment.

In Swagger UI, select **Authorize** and verify that the scheme displays the right flow, URLs, and scopes. If you need to test login, use a client ID and redirect URI configured for the test environment. Inspect actual requests in browser developer tools to confirm the authorization request is sent to the right `authorizationUrl` and token exchange is performed according to the client configuration.

Do not rely solely on the appearance of the Authorize button to conclude that OAuth2 works. Documentation may be structurally valid while the authorization server has not registered the client, the redirect URI is wrong, scopes are not granted, or the token endpoint is not working.

## 17. Common errors

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| Authorization Code flow is missing a URL | Missing `authorizationUrl` or `tokenUrl` | Declare both URLs according to the provider |
| Client Credentials flow declares an authorization URL | Confusing a user-facing flow with a service-to-service flow | Declare only `tokenUrl` for `clientCredentials` |
| Browser navigates to REST API instead of identity provider | API server URL was placed in `authorizationUrl` | Use the identity provider's authorization endpoint |
| Token exchange calls the wrong endpoint | `authorizationUrl` and `tokenUrl` are swapped | Cross-check each field with provider documentation |
| Refresh does not work | `refreshUrl` is incorrect or provider uses the shared token endpoint | Verify the refresh grant and actual provider URL |
| Swagger UI callback fails on return | Confusing `authorizationUrl` with redirect URI or callback not registered | Configure a dedicated redirect URI for Swagger UI and register it at the provider |
| Scope does not appear in Authorize | Scope not declared in `@Scopes` or requirement uses a different name | Synchronize scope names across flow and operation |
| OpenAPI uses staging URLs in production | URLs were hard-coded in annotations | Use environment-specific customizer/configuration and inspect release docs |
| Placeholder `${...}` appears literally in documentation | Annotations do not resolve Spring property placeholders | Use `OpenApiCustomizer` or a build step to substitute URLs |
| OIDC scheme lacks discovery metadata | OAuth flow URLs were placed in the wrong attribute | Use `openIdConnectUrl` for the `openIdConnect` scheme |
| Client secret leaked in Swagger UI | Secret was placed in frontend configuration or documentation | Remove the secret, rotate if exposed, and use public-client/PKCE or an appropriate backend |

## 18. Checklist for the OAuth Flows Object

- [ ] Scheme has `type = SecuritySchemeType.OAUTH2`.
- [ ] Flow is chosen appropriately for the client type and authorization model.
- [ ] Authorization Code has `authorizationUrl` and `tokenUrl`.
- [ ] Client Credentials and Password have `tokenUrl`.
- [ ] Implicit has `authorizationUrl`; document it only when legacy systems still genuinely use it.
- [ ] `refreshUrl` is declared according to the actual endpoint, not guessed.
- [ ] Scopes are declared using `@Scopes` and `@OAuthScope`.
- [ ] `@SecurityRequirement` references the right scheme name and scopes.
- [ ] OAuth endpoints are not confused with `servers.url` or the redirect URI.
- [ ] `openIdConnectUrl` is not confused with URLs inside the OAuth Flow Object.
- [ ] URLs use HTTPS and contain no tokens, secrets, or sensitive query parameters.
- [ ] Environment-specific URLs are managed and verified before release.
- [ ] Swagger UI OAuth client is configured separately and does not expose a client secret.
- [ ] OpenAPI JSON/YAML has been checked and the flow tested in an appropriate environment.

The OAuth Flows Object describes the flows supported by an API and the authorization server endpoints for each flow. `authorizationUrl`, `tokenUrl`, and `refreshUrl` each have distinct roles; they must match the actual identity provider configuration. When these URLs are properly distinguished from the API server, redirect URI, and OIDC discovery URL, OpenAPI documentation helps clients integrate OAuth2 more accurately without confusing descriptive metadata with runtime authentication configuration.
