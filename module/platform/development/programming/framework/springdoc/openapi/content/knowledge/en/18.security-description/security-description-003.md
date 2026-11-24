# `@SecurityRequirement` and Reference Name Must Match the Scheme

OpenAPI describes security using two linked parts: the **security scheme** defines the authentication mechanism, while the **security requirement** references that scheme to indicate which API or operation requires it. In Springdoc, `@SecurityScheme` declares the scheme; `@SecurityRequirement` uses the scheme name to attach the security requirement.

The reference name must match the declared name exactly. If a scheme is named `bearerAuth` but an operation references `BearerAuth`, OpenAPI has no scheme matching that name. Swagger UI may fail to display the Authorize mechanism as expected, and client generators may produce incorrect security configurations.

## 1. Distinguishing security scheme and security requirement

These two concepts answer two different questions:

- **Security scheme:** Which authentication type does the API use, and where are credentials transmitted? For example, HTTP Bearer, API key in a header, or OAuth2.
- **Security requirement:** Which API or operation requires the defined scheme? The requirement references the scheme by name.

In OpenAPI 3, schemes are placed in `components.securitySchemes`. Requirements at the document or operation level reference that scheme's key:

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

In this example, `bearerAuth` is the scheme name. The requirement also uses the exact string `bearerAuth`; the empty array indicates HTTP Bearer has no OAuth scope list.

Declaring `components.securitySchemes` alone does not mean every operation requires authentication. A scheme only describes the mechanism. You must add a security requirement at the document or operation level to attach that mechanism to the API.

## 2. Declaring an HTTP Bearer scheme with `@SecurityScheme`

For an API using a Bearer token, you can declare the scheme in your OpenAPI configuration:

```java
package com.example.config;

import io.swagger.v3.oas.annotations.OpenAPIDefinition;
import io.swagger.v3.oas.annotations.info.Info;
import io.swagger.v3.oas.annotations.security.SecurityScheme;
import io.swagger.v3.oas.annotations.enums.SecuritySchemeType;
import org.springframework.context.annotation.Configuration;

@Configuration
@OpenAPIDefinition(
    info = @Info(
        title = "Books API",
        version = "1.0.0",
        description = "API for managing and querying books"
    )
)
@SecurityScheme(
    name = "bearerAuth",
    type = SecuritySchemeType.HTTP,
    scheme = "bearer",
    bearerFormat = "JWT",
    description = "Enter the access token issued by the system"
)
public class OpenApiSecurityConfig {}
```

Key attributes:

| Attribute | Meaning |
| --- | --- |
| `name` | Key name in `components.securitySchemes` and the name referenced by requirements |
| `type` | Scheme type, such as `HTTP`, `APIKEY`, `OAUTH2`, `OPENIDCONNECT` |
| `scheme` | HTTP scheme name, such as `bearer` or `basic` |
| `bearerFormat` | Token format hint, such as `JWT`; this is descriptive information |
| `description` | Explains how to use the scheme |

Here, `name = "bearerAuth"` creates the reference name. This name is case-sensitive and must be kept identical when declaring `@SecurityRequirement`.

`bearerFormat = "JWT"` only describes the token format for readers. It does not enable JWT signature verification, issuer/audience checks, expiration checks, or access control in Spring Security.

## 3. Attaching requirements at the API-wide level

If most endpoints require a Bearer token, you can place the security requirement in `@OpenAPIDefinition`:

```java
import io.swagger.v3.oas.annotations.OpenAPIDefinition;
import io.swagger.v3.oas.annotations.security.SecurityRequirement;

@OpenAPIDefinition(
    security = {
        @SecurityRequirement(name = "bearerAuth")
    }
)
```

OpenAPI then describes the security requirement at the root level:

```yaml
security:
  - bearerAuth: []
```

A document-level security requirement acts as the default for operations. Readers can understand that operations inherit the Bearer token policy, except for operations that declare their own security to replace or remove that requirement.

Only set global security if that matches the API contract. If the API has public endpoints such as health checks, login, or metadata retrieval that do not require a token, clearly document the exception on the corresponding operation and verify the generated specification.

## 4. Attaching a requirement to an operation with `@Operation`

If only certain endpoints require authentication, attach the requirement directly to the operation:

```java
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.security.SecurityRequirement;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class AccountController {

    @GetMapping("/api/account/profile")
    @Operation(
        summary = "View account profile",
        security = {
            @SecurityRequirement(name = "bearerAuth")
        }
    )
    public ProfileResponse profile() {
        return new ProfileResponse("user_demo_001");
    }
}

record ProfileResponse(String userId) {}
```

`@SecurityRequirement(name = "bearerAuth")` does not create a new scheme. It references the scheme already declared with `@SecurityScheme(name = "bearerAuth", ...)`.

You can attach the same requirement to multiple operations. If a controller has many methods using the same security mechanism, consider declaring it at an appropriate scope and inspect the generated OpenAPI to avoid duplication or unintended differences.

## 5. Scheme names must match exactly

The most important rule is that the name in the requirement must equal the name in the scheme:

| Scheme declaration | Valid requirement | Mismatched requirement |
| --- | --- | --- |
| `name = "bearerAuth"` | `name = "bearerAuth"` | `name = "BearerAuth"` |
| `name = "apiKeyAuth"` | `name = "apiKeyAuth"` | `name = "api-key-auth"` |
| `name = "partnerOAuth"` | `name = "partnerOAuth"` | `name = "partnerOauth"` |

Example of a valid configuration:

```java
@SecurityScheme(
    name = "apiKeyAuth",
    type = SecuritySchemeType.APIKEY,
    in = SecuritySchemeIn.HEADER,
    paramName = "X-API-Key"
)
```

The requirement must reference `apiKeyAuth` exactly:

```java
@Operation(
    security = @SecurityRequirement(name = "apiKeyAuth")
)
```

The names `apiKeyAuth`, `api-key-auth`, and `ApiKeyAuth` are distinct strings. Use short names following a consistent convention, such as `bearerAuth`, `apiKeyAuth`, or `oauth2`.

## 6. API key scheme and corresponding requirement

An API key can be passed via header, query, or cookie. Example declaring an API key in a header:

```java
import io.swagger.v3.oas.annotations.enums.SecuritySchemeIn;
import io.swagger.v3.oas.annotations.enums.SecuritySchemeType;
import io.swagger.v3.oas.annotations.security.SecurityScheme;

@SecurityScheme(
    name = "apiKeyAuth",
    type = SecuritySchemeType.APIKEY,
    in = SecuritySchemeIn.HEADER,
    paramName = "X-API-Key",
    description = "API key issued by an administrator for the application"
)
```

Attaching the requirement:

```java
@Operation(
    summary = "Retrieve partner report",
    security = @SecurityRequirement(name = "apiKeyAuth")
)
```

Corresponding OpenAPI:

```yaml
components:
  securitySchemes:
    apiKeyAuth:
      type: apiKey
      in: header
      name: X-API-Key
paths:
  /api/partner/report:
    get:
      security:
        - apiKeyAuth: []
```

Do not declare an API key as a regular header parameter if its true purpose is authentication. Security schemes help Swagger UI, client generators, and OpenAPI tools recognize it as an authentication credential.

## 7. OAuth2 requirements and scopes

With OAuth2, a requirement references the scheme name and lists the scopes needed for the operation. Example of a scheme using the authorization code flow:

```java
import io.swagger.v3.oas.annotations.enums.SecuritySchemeType;
import io.swagger.v3.oas.annotations.security.OAuthFlow;
import io.swagger.v3.oas.annotations.security.OAuthFlows;
import io.swagger.v3.oas.annotations.security.OAuthScope;
import io.swagger.v3.oas.annotations.security.Scopes;
import io.swagger.v3.oas.annotations.security.SecurityScheme;

@SecurityScheme(
    name = "oauth2",
    type = SecuritySchemeType.OAUTH2,
    flows = @OAuthFlows(
        authorizationCode = @OAuthFlow(
            authorizationUrl = "https://auth.example.com/oauth/authorize",
            tokenUrl = "https://auth.example.com/oauth/token",
            scopes = @Scopes({
                @OAuthScope(name = "books:read", description = "Read books"),
                @OAuthScope(name = "books:write", description = "Create and update books")
            })
        )
    )
)
```

Operation requiring the read scope:

```java
@Operation(
    summary = "List books",
    security = @SecurityRequirement(
        name = "oauth2",
        scopes = {"books:read"}
    )
)
```

A write operation can require a different scope:

```java
@Operation(
    summary = "Create a book",
    security = @SecurityRequirement(
        name = "oauth2",
        scopes = {"books:write"}
    )
)
```

The name `oauth2` in both requirements must match `@SecurityScheme(name = "oauth2", ...)`. Scopes in requirements must be defined in the scheme's corresponding flow. Declaring scopes in OpenAPI does not grant permissions automatically; the authorization server and resource server must still validate tokens and scopes at runtime.

## 8. Understanding OR and AND rules for security requirements

In OpenAPI, the `security` field is an array of Security Requirement Objects. How schemes are grouped carries logical meaning:

- Multiple objects in the `security` array are **OR** alternatives: the client can satisfy any one of the options.
- Multiple schemes in the same object form an **AND** condition: the client must satisfy all schemes listed in that object.

Example of two alternative authentication methods (Bearer **or** API key):

```yaml
security:
  - bearerAuth: []
  - apiKeyAuth: []
```

Example requiring both Bearer and API key simultaneously:

```yaml
security:
  - bearerAuth: []
    apiKeyAuth: []
```

Combined example: accept (Bearer **and** API key) **or** OAuth2 with the `books:read` scope:

```yaml
security:
  - bearerAuth: []
    apiKeyAuth: []
  - oauth2:
      - books:read
```

Do not confuse repeating multiple `@SecurityRequirement` annotations with AND grouping. Independent requirements are typically represented as separate alternatives. If you need a complex AND combination, inspect the final OpenAPI structure and consider customizing the model with `OpenApiCustomizer` to build a single Security Requirement Object containing multiple scheme keys together.

## 9. Global security and per-operation security

OpenAPI allows placing `security` at the root level or at the operation level:

| Location | Scope | Usage |
| --- | --- | --- |
| `@OpenAPIDefinition(security = ...)` | Default for the entire document | When most or all operations require the same mechanism |
| `@Operation(security = ...)` | Single operation | When an operation has its own mechanism or scopes |
| `security: []` on an operation | Public operation, requiring no inherited security scheme | When removing global security for a public endpoint |

Example where the document defaults to Bearer but the health check endpoint is public:

```yaml
security:
  - bearerAuth: []
paths:
  /actuator/health:
    get:
      security: []
      responses:
        '200':
          description: Application status
```

In OpenAPI, operation-level security replaces the root-level requirement for that operation. If an operation has `security: []`, it does not inherit the global security requirement.

When configuring via annotations, verify that Springdoc actually emits `security: []` for public operations in your version. If the default annotation behavior does not produce an empty array as expected, you can use `OpenApiCustomizer` or an appropriate customization mechanism to set an explicit empty security list. Never allow public endpoints to accidentally inherit global requirements in the documentation.

## 10. Complete example: scheme and operation referencing the same name

A simple configuration for Books API:

```java
package com.example.books.config;

import io.swagger.v3.oas.annotations.OpenAPIDefinition;
import io.swagger.v3.oas.annotations.info.Info;
import io.swagger.v3.oas.annotations.security.SecurityRequirement;
import io.swagger.v3.oas.annotations.security.SecurityScheme;
import io.swagger.v3.oas.annotations.enums.SecuritySchemeType;
import org.springframework.context.annotation.Configuration;

@Configuration
@OpenAPIDefinition(
    info = @Info(title = "Books API", version = "1.0.0"),
    security = @SecurityRequirement(name = "bearerAuth")
)
@SecurityScheme(
    name = "bearerAuth",
    type = SecuritySchemeType.HTTP,
    scheme = "bearer",
    bearerFormat = "JWT"
)
public class OpenApiConfig {}
```

Controller:

```java
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.security.SecurityRequirement;
import java.util.List;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class BookController {

    @GetMapping("/api/books")
    @Operation(
        summary = "List books",
        security = @SecurityRequirement(name = "bearerAuth")
    )
    public List<BookResponse> list() {
        return List.of(new BookResponse(1L, "Spring Boot Fundamentals"));
    }
}

record BookResponse(Long id, String title) {}
```

In the example, both document-level and operation-level security reference `bearerAuth`. Security declared on an operation replaces document-level security for that operation rather than accumulating with it. Therefore, you can omit the operation-level requirement if you want to inherit global security; keeping an explicit declaration is only useful when an operation needs its own mechanism or scopes, or when you want the policy visible directly on the method.

## 11. How does Swagger UI use the scheme?

When OpenAPI contains `components.securitySchemes` and requirements referencing the exact names, Swagger UI can display the **Authorize** button and credential entry forms.

With HTTP Bearer:

1. Open Swagger UI.
2. Click **Authorize**.
3. Choose the `bearerAuth` scheme.
4. Enter an access token issued by the test environment.
5. Confirm and send a request to an operation that has the requirement.

For an API key, the UI prompts for a value for `apiKeyAuth`; Swagger UI attaches the value at the declared location, such as the `X-API-Key` header. For OAuth2, the UI can initiate the authorization flow depending on the flow and client configuration.

Do not put real tokens into source code, annotations, `@ExampleObject`, or documentation. Enter test credentials through the Authorize UI or use an appropriate environment secret mechanism.

The Authorize button only helps users supply credentials to test the API. It does not protect endpoints on its own and does not replace Spring Security, resource server, or gateway configurations.

## 12. Each group document must include the referenced schemes

If Springdoc generates multiple documents via `GroupedOpenApi`, each OpenAPI document is validated independently. A requirement in a group must reference a scheme present in `components.securitySchemes` of that same group document.

For example, the `partner` document contains:

```yaml
components:
  securitySchemes:
    partnerApiKey:
      type: apiKey
      in: header
      name: X-Partner-Key
security:
  - partnerApiKey: []
```

If the `public` group does not declare the `partnerApiKey` scheme while an operation in that group still references that name, the public document may contain an invalid or incomplete requirement. When creating groups, verify both scheme definitions and requirements, not just paths.

If each group has a different authentication mechanism, design scheme names and requirement scopes clearly. Avoid reusing the same name for two different mechanisms across documents if doing so could mislead clients about how to send credentials.

## 13. Verifying OpenAPI after declaring security

After starting the application, open `/v3/api-docs` or `/v3/api-docs.yaml`. For each scheme, confirm:

1. The scheme appears in `components.securitySchemes`.
2. The scheme key is spelled and cased accurately.
3. `type`, `scheme`, `in`, `name`, OAuth flows, and scopes match the actual mechanism.
4. Every `security` requirement references a declared key.
5. Scopes in requirements exist in the corresponding OAuth2/OpenID scheme.
6. Public operations have empty security if they need to remove global security.
7. Each group document contains all scheme definitions that its requirements reference.

Example of a valid OpenAPI snippet:

```yaml
components:
  securitySchemes:
    bearerAuth:
      type: http
      scheme: bearer
      bearerFormat: JWT
paths:
  /api/books:
    get:
      security:
        - bearerAuth: []
      responses:
        '200':
          description: List of books
```

If Swagger UI does not display Authorize, inspect the JSON document first. If the scheme exists but operations do not require it, check `security` at the root and operation levels. If Authorize appears but requests do not send credentials, check the requirement, scheme configuration, authorize state, and the actual request in the Network tab.

## 14. Common errors

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| Swagger UI has no Authorize button | Scheme is not declared or the document does not contain `components.securitySchemes` | Declare `@SecurityScheme` and inspect OpenAPI |
| Scheme exists but operation does not show security requirement | Missing `@SecurityRequirement` at root or operation level | Add a requirement referencing the exact name |
| Requirement cannot find scheme | Name in `@SecurityRequirement` differs from `@SecurityScheme` | Synchronize the exact `name` string |
| Only casing differs yet still fails | Scheme names are referenced as case-sensitive keys | Use a constant or convention and copy the exact name |
| Authorize appears but wrong header is sent | Scheme declared wrong type, scheme, `in`, or `paramName` | Cross-check configuration with the runtime auth mechanism |
| OAuth2 reports invalid scope | Requirement scope was not declared in the flow | Synchronize scopes between `@OAuthScope` and `@SecurityRequirement` |
| Public endpoint still displays Bearer requirement | Operation inherits root-level security | Ensure the operation has `security: []` in OpenAPI |
| Scheme exists in default document but is missing in a group | Group document lacks the corresponding scheme definition | Add the scheme to each document or shared configuration properly |
| Confusing requirement with actual authentication mechanism | Only OpenAPI metadata was declared without configuring Spring Security | Implement authentication/authorization at runtime |

## 15. Checklist to ensure requirements match schemes

- [ ] Schemes are declared using `@SecurityScheme` or equivalent OpenAPI configuration.
- [ ] Scheme `name` follows a stable convention, such as `bearerAuth`.
- [ ] Every `@SecurityRequirement(name = ...)` uses the exact declared name.
- [ ] Scheme names are not confused with header names such as `Authorization` or `X-API-Key`.
- [ ] HTTP Bearer schemes have `type = HTTP` and `scheme = "bearer"`.
- [ ] API key schemes declare the correct `in` and `paramName`.
- [ ] OAuth2 requirements use the exact defined scheme name and scopes.
- [ ] Document-level vs. per-operation security has been decided.
- [ ] Public endpoints have `security: []` if they need to remove global requirements.
- [ ] OR/AND requirements are grouped properly in OpenAPI.
- [ ] Each group document has all schemes referenced by its requirements.
- [ ] Verified `/v3/api-docs`, Swagger UI Authorize, and actual requests.
- [ ] Spring Security or the resource server enforces authentication and authorization independently of OpenAPI metadata.

`@SecurityScheme` defines a security mechanism; `@SecurityRequirement` references that mechanism by name. The two names must match exactly within the same OpenAPI document. When schemes, requirements, scopes, and application scopes are declared consistently, Swagger UI can guide integrators to authenticate properly and client generators can produce security configurations that match the API contract.
