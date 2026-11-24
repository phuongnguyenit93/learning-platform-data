# Declaring an OpenID Connect Discovery URL

OpenID Connect (OIDC) adds an identity authentication layer on top of OAuth 2.0. An OpenID Provider publishes a discovery document containing metadata such as issuer, authorization endpoint, token endpoint, and the JSON Web Key Set (JWKS) address. Clients can read this document to learn how to initiate the login flow and locate public keys used to verify tokens.

In OpenAPI, a security scheme of type `openIdConnect` links to the discovery document using the `openIdConnectUrl` property. With `springdoc-openapi`, you can declare this scheme using the `@SecurityScheme` annotation or by creating a `SecurityScheme` model inside an `OpenAPI` bean. The URL must point directly to the identity provider's JSON discovery document; it is not the plain issuer URL, authorization endpoint, or token endpoint.

## 1. Distinguishing issuer and discovery URL

The issuer is the identifier of the OpenID Provider. It appears in discovery metadata and in the `iss` claim of the ID token. The discovery URL is the HTTP(S) address used to download the issuer's metadata document.

Example with a realm that has an issuer:

```text
Issuer:
https://sso.example.com/realms/store

Discovery document:
https://sso.example.com/realms/store/.well-known/openid-configuration
```

For OIDC Discovery 1.0, the path `/.well-known/openid-configuration` is appended to the issuer identifier according to the specification rules. When the issuer has a path such as a realm or tenant, that path portion still belongs to the discovery URL. Many providers display the discovery URL directly on the application settings page; prefer the exact URL published by the provider rather than assembling it manually without verification.

Distinguish these URLs:

| Value | Purpose | Example |
| --- | --- | --- |
| Issuer | Identifier of the identity provider | `https://sso.example.com/realms/store` |
| Discovery URL | Downloads OIDC metadata | `https://sso.example.com/realms/store/.well-known/openid-configuration` |
| Authorization endpoint | Starts the login/authorization flow | URL present in `authorization_endpoint` |
| Token endpoint | Exchanges authorization code or refresh token | URL present in `token_endpoint` |
| JWKS URI | Downloads the issuer's public key set | URL present in `jwks_uri` |

Do not pass `authorization_endpoint`, `token_endpoint`, or `jwks_uri` into `openIdConnectUrl`. OpenAPI needs the URL of the discovery document so clients or tools can read the metadata and discover the remaining endpoints themselves.

## 2. What information does the discovery document contain?

An OpenID Provider typically returns a JSON document at the discovery URL. Condensed example:

```json
{
  "issuer": "https://sso.example.com/realms/store",
  "authorization_endpoint": "https://sso.example.com/realms/store/protocol/openid-connect/auth",
  "token_endpoint": "https://sso.example.com/realms/store/protocol/openid-connect/token",
  "userinfo_endpoint": "https://sso.example.com/realms/store/protocol/openid-connect/userinfo",
  "jwks_uri": "https://sso.example.com/realms/store/protocol/openid-connect/certs",
  "response_types_supported": ["code"],
  "subject_types_supported": ["public"],
  "id_token_signing_alg_values_supported": ["RS256"],
  "scopes_supported": ["openid", "profile", "email"],
  "code_challenge_methods_supported": ["S256"]
}
```

Core and commonly encountered fields:

- `issuer`: identifier of the OpenID Provider; must match the issuer trusted by the client and the `iss` value in ID tokens.
- `authorization_endpoint`: endpoint receiving authorization requests.
- `token_endpoint`: endpoint issuing tokens or exchanging authorization codes.
- `jwks_uri`: endpoint providing public keys to verify token signatures.
- `response_types_supported`: response types supported by the provider, such as `code`.
- `subject_types_supported`: subject identifier types.
- `id_token_signing_alg_values_supported`: ID token signing algorithms advertised by the provider.
- `scopes_supported`: list of scopes supported by the provider; this is optional metadata in discovery.
- `code_challenge_methods_supported`: supported PKCE methods if published by the provider.

Other metadata may include `userinfo_endpoint`, `end_session_endpoint`, token endpoint authentication methods, supported claims, and logout configuration. Do not assume every provider publishes all optional fields or uses the same extension names.

Clients should verify that the discovery document is returned over HTTPS, confirm the exact `issuer`, and trust metadata only from configured providers. Do not take a discovery URL from untrusted user input and automatically fetch it, as doing so can create SSRF risks or cause the application to trust the wrong issuer.

## 3. Declaring an OpenID Connect scheme using annotations

Swagger Annotations provides `@SecurityScheme` with `SecuritySchemeType.OPENIDCONNECT`. The `openIdConnectUrl` attribute takes the URL of the discovery document:

```java
import io.swagger.v3.oas.annotations.OpenAPIDefinition;
import io.swagger.v3.oas.annotations.info.Info;
import io.swagger.v3.oas.annotations.security.SecurityRequirement;
import io.swagger.v3.oas.annotations.security.SecurityScheme;
import io.swagger.v3.oas.annotations.enums.SecuritySchemeType;
import org.springframework.context.annotation.Configuration;

@Configuration
@OpenAPIDefinition(
    info = @Info(title = "Store API", version = "1.0.0"),
    security = {
        @SecurityRequirement(
            name = "storeOidc",
            scopes = {"openid", "profile"}
        )
    }
)
@SecurityScheme(
    name = "storeOidc",
    type = SecuritySchemeType.OPENIDCONNECT,
    openIdConnectUrl = "https://sso.example.com/realms/store/.well-known/openid-configuration",
    description = "OpenID Connect provider for Store API"
)
class OpenApiOidcConfiguration {}
```

Meaning of the components:

- `name = "storeOidc"` is the scheme name referenced in security requirements.
- `type = SecuritySchemeType.OPENIDCONNECT` creates an OpenID Connect scheme.
- `openIdConnectUrl` points to the JSON discovery document.
- `@OpenAPIDefinition.security` applies the requirement at the document level; operations inherit this requirement unless overridden.
- `scopes` lists scopes required for the operation/client per the API contract.

The name `storeOidc` must match exactly between `@SecurityScheme` and `@SecurityRequirement`. This name is an internal key within OpenAPI, not the issuer, client ID, or realm name.

If only some operations require OIDC, do not set global security; attach `@SecurityRequirement(name = "storeOidc", scopes = {...})` to each corresponding `@Operation`. Public operations can override the global requirement with an empty `@SecurityRequirements` per OpenAPI security rules.

## 4. Declaring the scheme using an `OpenAPI` bean

If the project manages documentation through Java configuration instead of annotations, you can construct `SecurityScheme` directly:

```java
import io.swagger.v3.oas.models.Components;
import io.swagger.v3.oas.models.OpenAPI;
import io.swagger.v3.oas.models.info.Info;
import io.swagger.v3.oas.models.security.SecurityRequirement;
import io.swagger.v3.oas.models.security.SecurityScheme;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import java.util.List;

@Configuration
class OpenApiOidcBeanConfiguration {

    @Bean
    OpenAPI storeOpenAPI() {
        SecurityScheme oidc = new SecurityScheme()
            .type(SecurityScheme.Type.OPENIDCONNECT)
            .openIdConnectUrl(
                "https://sso.example.com/realms/store/.well-known/openid-configuration"
            )
            .description("OpenID Connect provider for Store API");

        SecurityRequirement requirement = new SecurityRequirement()
            .addList("storeOidc", List.of("openid", "profile"));

        return new OpenAPI()
            .info(new Info().title("Store API").version("1.0.0"))
            .components(new Components().addSecuritySchemes("storeOidc", oidc))
            .addSecurityItem(requirement);
    }
}
```

Here, `.type(SecurityScheme.Type.OPENIDCONNECT)` and `.openIdConnectUrl(...)` produce the same structure as the annotation. `addSecuritySchemes` registers the scheme; `addSecurityItem` applies the requirement. Choose one primary declaration method to avoid accidentally creating two schemes with the same meaning or two different names for the same provider.

If using multiple OpenAPI documents via `GroupedOpenApi`, determine which schemes and requirements are shared and which are specific to each group. Check each `/v3/api-docs/{group}` URL because group-specific customizers can make a document differ from the default document.

## 5. What does the generated OpenAPI document look like?

With the annotation configuration above, the key structure in OpenAPI will resemble:

```yaml
openapi: 3.0.3
components:
  securitySchemes:
    storeOidc:
      type: openIdConnect
      openIdConnectUrl: https://sso.example.com/realms/store/.well-known/openid-configuration
      description: OpenID Connect provider for Store API
security:
  - storeOidc:
      - openid
      - profile
paths:
  /api/orders:
    get:
      responses:
        '200':
          description: List of orders
```

The points to check are that `type` has value `openIdConnect`, `openIdConnectUrl` matches the discovery URL, and the security requirement references the exact name `storeOidc`. The OpenAPI document only stores the URL and scope requirements; it does not embed the entire discovery JSON inside `components`.

If a scheme is declared but does not appear in `security`, Swagger UI may not know that operations need that scheme. Conversely, if a requirement references a name not declared in `components.securitySchemes`, the document is inconsistent.

## 6. OIDC scopes and API scopes

The `openid` scope is a special scope requesting an OpenID Connect flow and an ID token. Standard scopes such as `profile`, `email`, `address`, or `phone` request corresponding claims if supported by the provider and allowed by consent policy.

An API can also define its own authorization scopes, such as `orders.read` or `orders.write`. These scopes typically express access permissions on API resources and are not synonymous with OIDC profile scopes. When writing them in an OpenAPI security requirement, use the scope names that the authorization server and API actually understand.

Example operation that only reads orders:

```java
@GetMapping("/api/orders")
@Operation(
    summary = "List orders",
    security = @SecurityRequirement(
        name = "storeOidc",
        scopes = {"openid", "orders.read"}
    )
)
List<OrderResponse> listOrders() {
    return orderService.findAll();
}
```

Scope names in security requirements are part of the contract. Synchronize them with client configuration, the authorization server, and the policies checked by the API. Adding `orders.read` to an annotation does not create the scope on the Identity Provider and does not enforce permissions in Spring Security.

## 7. Distinguishing `openIdConnect` from `oauth2` and HTTP Bearer

Three common security scheme types have different meanings:

| OpenAPI Type | How it is described | When appropriate |
| --- | --- | --- |
| `openIdConnect` | Links to the OIDC discovery document via `openIdConnectUrl`. | The API uses an OpenID Provider and wants to publish discovery metadata to clients/tooling. |
| `oauth2` | Explicitly declares OAuth2 `flows`, authorization URL, token URL, and scopes. | The contract needs to describe directly the OAuth2 flows clients use. |
| `http` with `scheme: bearer` | Describes clients sending a bearer token in the `Authorization` header. | The API only needs to publish how to send an access token; no need to describe discovery/authorization flows. |

OIDC is built on OAuth 2.0, adding user identity and ID tokens. If the API only verifies bearer access tokens and does not need to publish a login flow, HTTP Bearer may be simpler. If clients need discovery to locate login endpoints, `openIdConnect` expresses that clearly. If fine-grained control over each OAuth2 flow is needed in OpenAPI, use an `oauth2` scheme with appropriate `flows`.

Do not confuse ID tokens with access tokens. An ID token proves user authentication results to the OIDC client; an access token is issued to access a resource server/API. The API needs to check the token type, audience, and its own policies; do not accept ID tokens as access tokens by default.

## 8. Discovery URL does not replace Swagger UI OAuth client configuration

`openIdConnectUrl` describes the location of the provider's metadata. It is not a client ID, does not contain a client secret, and does not register the Swagger UI application with the Identity Provider.

If you want to use the **Authorize** button for interactive login, you still need to configure an appropriate OAuth client in Swagger UI and register the redirect URI used by Swagger UI on the provider side. For browser-based applications, use a public client and Authorization Code Flow with PKCE; do not embed client secrets in JavaScript or the OpenAPI document.

OAuth-related Swagger UI configuration properties may include `springdoc.swagger-ui.oauth.client-id`, `springdoc.swagger-ui.oauth.use-pkce-with-authorization-code-grant`, and the redirect URL per UI configuration. Automatic discovery reading and the **Authorize** experience depend on the Swagger UI version and client settings. After declaring the scheme, verify the actual UI instead of assuming the discovery URL completes the entire login setup.

The discovery URL also does not cause Spring Security to automatically configure a resource server. The Spring Boot application still needs to configure issuer/JWK or a token verifier, checking signature, `iss`, `aud`, `exp`, validity window, and authorities/scopes per policy. With Spring Security Resource Server, configuring `issuer-uri` allows the framework to use issuer metadata to discover keys and verify JWTs, but that is a separate runtime configuration from `openIdConnectUrl` in OpenAPI.

## 9. Protecting and managing the discovery URL

A discovery URL is public metadata by OIDC design, but must be managed as part of trusted configuration:

- Use HTTPS with valid TLS certificates.
- Obtain the URL from environment configuration or official Identity Provider details.
- Verify the `issuer` field in the document matches the configured issuer exactly.
- Check that `jwks_uri`, authorization endpoint, and token endpoint belong to the expected provider.
- Do not put client secrets, passwords, access tokens, or refresh tokens in the discovery URL or OpenAPI document.
- If using multiple tenants/realms, each issuer needs a discovery URL scoped to that tenant.
- When changing domain, realm, or issuer, update documentation configuration and runtime token verification configuration together.

The discovery document can be cached according to the provider's policy. Avoid fetching it arbitrarily on every business request; OIDC/resource server libraries typically manage metadata and JWKS caching separately. When keys rotate, follow the refresh/caching mechanism of the token verification library.

## 10. Verifying discovery and the OpenAPI document

Before publishing documentation, verify both the provider metadata and the schema generated by springdoc:

1. Open the discovery URL directly or fetch it with curl to confirm it returns JSON over HTTPS.
2. Check that `issuer` matches the configured issuer exactly.
3. Confirm required endpoints such as `authorization_endpoint`, `token_endpoint`, and `jwks_uri` are present.
4. Check `response_types_supported`, ID token signing algorithms, and PKCE methods if client flows require them.
5. Open `/v3/api-docs` and locate `components.securitySchemes.storeOidc`.
6. Confirm `type` is `openIdConnect` and `openIdConnectUrl` points to the right discovery document.
7. Check that `security` at the root or operations references `storeOidc` with the right scopes.
8. Open Swagger UI, confirm the scheme is displayed, and test **Authorize** if the application has configured an OAuth client/redirect URI.
9. Call the runtime API with a valid access token, a wrong-issuer/wrong-audience token, and an expired token to verify the resource server enforces checks properly.

Example quick discovery check:

```bash
curl -i https://sso.example.com/realms/store/.well-known/openid-configuration
```

Example OpenAPI check:

```bash
curl -s http://localhost:8080/v3/api-docs
```

If running across multiple groups, repeat the check with `/v3/api-docs/{group}` for each document to be published.

## 11. Testing documentation with MockMvc

You can verify the schema generated by springdoc using JSONPath:

```java
@SpringBootTest
@AutoConfigureMockMvc
class OidcOpenApiDocumentTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void exposesOpenIdConnectDiscoveryUrl() throws Exception {
        mockMvc.perform(get("/v3/api-docs"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.components.securitySchemes.storeOidc.type")
                .value("openIdConnect"))
            .andExpect(jsonPath("$.components.securitySchemes.storeOidc.openIdConnectUrl")
                .value("https://sso.example.com/realms/store/.well-known/openid-configuration"))
            .andExpect(jsonPath("$.security[0].storeOidc").isArray());
    }
}
```

This test confirms that OpenAPI metadata is published properly. It does not call the Identity Provider and does not prove that JWTs are validated properly. Have separate tests for the resource server or integration tests with a simulated Identity Provider environment to verify issuer, audience, signature, expiry, and scopes.

## 12. Common errors

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| OpenAPI has `type: openIdConnect` without `openIdConnectUrl` | Missing URL attribute or wrong annotation/type used | Declare `openIdConnectUrl` on `@SecurityScheme` or the `SecurityScheme` model. |
| Discovery URL returns `404` | Wrong well-known path, realm, or tenant assembled | Use the exact discovery URL from the provider and verify the issuer path. |
| Discovery document loads but `issuer` mismatches | Wrong realm/tenant used or proxy alters issuer | Synchronize the exact issuer across metadata, client, and resource server. |
| Swagger UI does not know operations require authentication | Scheme exists but security requirement is missing | Add root `security` or `@SecurityRequirement` on operations. |
| Scheme does not appear in Authorize | Security requirement references wrong name or UI does not support that configuration | Synchronize scheme names and check Swagger UI version. |
| Authorize button opens wrong redirect URI | Swagger UI redirect URI not registered or client misconfigured | Update client registration and OAuth UI settings; use PKCE for public clients. |
| API returns `401` despite OpenAPI declaring OIDC | Discovery metadata does not configure the resource server or token is invalid | Check JWT decoder, issuer, audience, JWKS, and token expiration. |
| API accepts ID token but rejects access token or vice versa | Wrong token type or audience used | Use access tokens for the resource server and enforce proper audience/policy checks. |
| URL works locally but fails behind a proxy | Public host, scheme, or prefix differs from internal URL | Check forwarded headers and discovery/issuer URLs published by the provider. |
| Each group has different security schemes | Group-specific customizers or OpenAPI configurations | Inspect each `/v3/api-docs/{group}` and unify shared configuration. |

## 13. Application principles

- Distinguish issuer, discovery URL, authorization endpoint, token endpoint, and JWKS URI.
- Use `SecuritySchemeType.OPENIDCONNECT` along with `openIdConnectUrl` to describe OIDC discovery in OpenAPI.
- Set security requirements referencing the exact scheme name and scopes the API actually requires.
- Use `openIdConnect` when publishing discovery; use `oauth2` when describing OAuth2 flows in detail; use HTTP Bearer when only describing how to send an access token.
- Do not confuse ID tokens with access tokens.
- Do not treat the discovery URL as OAuth client configuration or resource server configuration.
- Use HTTPS, verify the issuer, and trust metadata only from configured Identity Providers.
- Verify OpenAPI JSON, Swagger UI, the discovery document, and runtime token validation as separate steps.
- Check each group document if the application has multiple `GroupedOpenApi` beans.

`openIdConnectUrl` connects a security scheme in OpenAPI with the OpenID Provider's discovery document. When the URL points to valid metadata and scheme names and scopes are declared consistently, clients can discover the authentication method published by the API. Interactive login, access token issuance, and token verification still need to be configured separately in Swagger UI, the Identity Provider, and Spring Security resource server.

## References

- [OpenID Connect Discovery 1.0](https://openid.net/specs/openid-connect-discovery-1_0.html)
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html)
- [OpenAPI Specification – OpenID Connect URL](https://spec.openapis.org/oas/latest.html)
- [Swagger Annotations – `@SecurityScheme`](https://docs.swagger.io/swagger-core/v2.2.53/apidocs/io/swagger/v3/oas/annotations/security/SecurityScheme.html)
- [Springdoc OpenAPI – official documentation](https://springdoc.org/)
- [Spring Security – OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html)
