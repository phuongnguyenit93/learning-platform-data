# bearerFormat as Descriptive Token Format Metadata

In OpenAPI, an API can require clients to send a bearer token via the **Authorization** HTTP header. A Security Scheme describes this mechanism with **type: http** and **scheme: bearer**. The **bearerFormat** property adds a hint about the token format, such as **JWT**.

What must be understood precisely is that bearerFormat is purely descriptive metadata in the specification. It does not determine the signing algorithm, decode tokens, verify signatures, validate claims, or configure Spring Security. Token validation is still performed by the application's runtime security mechanism.

In springdoc-openapi, you can declare a bearer scheme using the **@SecurityScheme** annotation or OpenAPI model configuration. Then use **@SecurityRequirement** to attach the scheme to the entire document or specific operations. This guide focuses on the meaning of bearerFormat, how to describe it accurately, and how to verify both the documentation and authentication behavior.

## 1. How is a bearer token sent?

With HTTP bearer authentication, the client sends the token in a header:

~~~http
GET /api/profile
Authorization: Bearer eyJhbGciOi...
~~~

Where:

- **Authorization** is the HTTP header name.
- **Bearer** is the scheme in the header value.
- The part after Bearer is the token the server receives for authentication.

OpenAPI describes this mechanism using a Security Scheme Object:

~~~yaml
type: http
scheme: bearer
bearerFormat: JWT
~~~

**scheme: bearer** specifies the HTTP authentication type used. **bearerFormat: JWT** only provides additional information that the token is expected to have a JWT format. The client still sends the token following the bearer convention in the Authorization header.

Do not confuse a bearer token with a single token type. Bearer is how credentials are presented in HTTP; the carried token can be a JWT, an opaque token, or another format accepted by the system.

## 2. What is bearerFormat?

**bearerFormat** is an optional string in OpenAPI's HTTP Bearer Security Scheme. It helps readers or tools understand the token format that the API expects to use.

Some descriptive values you may encounter:

| Value | Descriptive meaning |
|---|---|
| JWT | Token is structured as a JSON Web Token |
| Opaque | Token does not expose internal structure to clients |
| JWT (JWS) | Hints that the JWT token is represented in signed JWS form |

This is a free-form text value, not a mandatory OpenAPI enum. The names above are descriptive conventions; tools reading the documentation must not infer algorithms, issuers, or validation rules from this string alone.

Example:

~~~yaml
components:
  securitySchemes:
    bearerAuth:
      type: http
      scheme: bearer
      bearerFormat: JWT
      description: JWT access token sent via the Authorization header.
~~~

In documentation, bearerFormat may be presented by Swagger UI or other tools as a hint. How a specific interface displays it depends on the tool version. Changing bearerFormat does not alter issued tokens or how the server processes requests.

### bearerFormat is optional

If the system does not want to commit to a specific format, you can omit this property:

~~~yaml
components:
  securitySchemes:
    bearerAuth:
      type: http
      scheme: bearer
      description: Access token sent via the Authorization header.
~~~

Leaving bearerFormat empty is usually better than writing a guessed value. Only document JWT when the system's actual token is a JWT; if tokens are opaque, clarify this in the description or use an appropriate descriptive label.

## 3. bearerFormat is not an authentication mechanism

The following responsibilities do not belong to bearerFormat:

- Parsing the compact structure of a JWS-form JWT; JWE-form JWTs have a different structure.
- Verifying signatures or signing algorithms.
- Validating issuer, audience, expiration, or not-before.
- Checking whether a token has been revoked.
- Calling an introspection endpoint for opaque tokens.
- Mapping claims or scopes into access permissions.
- Rejecting requests missing a token or carrying an invalid token.

For example, the following two documents differ only in their descriptive label:

~~~yaml
bearerAuth:
  type: http
  scheme: bearer
  bearerFormat: JWT
~~~

~~~yaml
bearerAuth:
  type: http
  scheme: bearer
  bearerFormat: Opaque
~~~

Neither line in these two configurations causes Spring Security to switch between a JWT decoder and opaque token introspection. The application must be configured separately to verify the actual token type.

If an API declares bearerFormat as JWT while the server accepts opaque tokens, the documentation misstates client expectations. Conversely, changing it to Opaque while the server still verifies JWTs leaves runtime behavior unchanged while making the documentation misleading.

## 4. Declaring an HTTP bearer scheme with @SecurityScheme

In springdoc-openapi 2.x, you can use annotations from swagger-annotations to declare the scheme:

~~~java
import io.swagger.v3.oas.annotations.enums.SecuritySchemeType;
import io.swagger.v3.oas.annotations.security.SecurityScheme;
import org.springframework.context.annotation.Configuration;

@Configuration
@SecurityScheme(
    name = "bearerAuth",
    type = SecuritySchemeType.HTTP,
    scheme = "bearer",
    bearerFormat = "JWT",
    description = "JWT access token in the Authorization header."
)
public class OpenApiSecurityConfiguration {
}
~~~

Main attributes:

| Attribute | Role |
|---|---|
| **name** | Identifier name for the scheme in components/securitySchemes |
| **type** | Scheme type; for HTTP bearer this is SecuritySchemeType.HTTP |
| **scheme** | HTTP authentication scheme name; bearer must be written as bearer |
| **bearerFormat** | Token format hint, such as JWT |
| **description** | Describes how clients obtain and send the token |

The name **bearerAuth** is chosen by the application. This name must match the Security Requirement referencing the scheme.

### Scheme name is not token format

In the example:

- bearerAuth is the reference name of the security scheme.
- bearer is the HTTP authentication scheme.
- JWT is the bearerFormat.

These three values have different roles. Do not set name to JWT thinking the token format has been configured; nor should you change scheme to JWT because JWT is not an HTTP authentication scheme.

## 5. Registering a scheme does not automatically apply security to operations

Declaring @SecurityScheme creates a definition in components. For an operation to require that scheme, you must add a **Security Requirement**.

Attach to an operation:

~~~java
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.security.SecurityRequirement;

@RestController
@RequestMapping("/api/profile")
public class ProfileController {

    @Operation(
        summary = "Get current profile",
        security = @SecurityRequirement(name = "bearerAuth")
    )
    @GetMapping
    public ProfileResponse currentProfile() {
        // ...
        return null;
    }
}
~~~

Or use the @SecurityRequirement annotation directly at the class or method level:

~~~java
@SecurityRequirement(name = "bearerAuth")
@RestController
@RequestMapping("/api/orders")
public class OrderController {
    // Controller operations are documented with the bearerAuth requirement
}
~~~

Defining a scheme and applying a requirement are two distinct steps:

1. **Security Scheme** describes the authentication mechanism.
2. **Security Requirement** specifies which operation or entire document requires which mechanism.

If only components.securitySchemes exists without security requirements, Swagger UI may know the scheme exists, but the specification does not indicate which operations require it.

## 6. Applying bearer authentication across the entire document

If most or all endpoints require a bearer token, you can declare the requirement at the document level using @OpenAPIDefinition:

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
    bearerFormat = "JWT"
)
public class OpenApiSecurityConfiguration {
}
~~~

Then the document can contain:

~~~yaml
security:
  - bearerAuth: []
~~~

The empty list after bearerAuth is valid for an HTTP bearer scheme. OAuth2 requirements can list scopes; HTTP bearer does not declare scopes in this structure.

If only a few endpoints need a token, do not apply a global requirement and leave readers guessing which public endpoints are exempt. You can attach individual requirements to each operation or override security on public operations.

## 7. How to override security for public operations

OpenAPI allows an operation to override document-level security requirements. If the API requires a bearer token by default but the health endpoint is public, you can document the operation as requiring no security:

~~~yaml
security:
  - bearerAuth: []
paths:
  /health:
    get:
      security: []
      responses:
        "200":
          description: Service is healthy
~~~

In OpenAPI, **security: []** on an operation means the operation requires no security scheme, overriding higher-level requirements.

Do not confuse this case with:

~~~yaml
security:
  - bearerAuth: []
  - {}
~~~

A list containing an empty security requirement {} expresses that authentication is optional: requests can use bearerAuth or use no security scheme at all. That has different semantics from security: [] on an operation.

The documentation must reflect actual policy. If the health endpoint genuinely requires a token, do not set empty security just so Swagger UI allows unauthenticated calls.

## 8. Complete OpenAPI example

The scheme definition and requirement can be represented as follows:

~~~yaml
openapi: 3.0.3
info:
  title: Profile API
  version: v1

components:
  securitySchemes:
    bearerAuth:
      type: http
      scheme: bearer
      bearerFormat: JWT
      description: JWT access token sent via the Authorization header.

security:
  - bearerAuth: []

paths:
  /api/profile:
    get:
      summary: Get current profile
      responses:
        "200":
          description: User profile
        "401":
          description: Missing or invalid token
        "403":
          description: Authenticated but insufficient permissions
~~~

In the document:

- components.securitySchemes defines bearerAuth.
- type http and scheme bearer describe HTTP bearer authentication.
- bearerFormat JWT provides a hint about the token format.
- Root-level security applies the requirement to operations in the document, except operations with overrides.
- 401 and 403 describe possible security outcomes; they are not automatically generated just by having a security requirement.

## 9. Distinguishing HTTP bearer from OAuth2 and API key

Not every token in the Authorization header should be described using bearerFormat. Choose the security scheme type that matches the mechanism clients actually use:

| Mechanism | OpenAPI type | Main properties | bearerFormat |
|---|---|---|---|
| HTTP Bearer | http | scheme: bearer | Can be used to hint at token format |
| HTTP Basic | http | scheme: basic | Do not use to describe passwords |
| API key in header | apiKey | name: Authorization or custom header; in: header | HTTP bearer semantics do not apply |
| OAuth 2.0 | oauth2 | flows, authorizationUrl, tokenUrl, scopes | Do not use bearerFormat in place of flows |
| OpenID Connect | openIdConnect | openIdConnectUrl | Do not use bearerFormat in place of discovery URL |

### HTTP bearer

Suitable when the client already has an access token and sends it directly:

~~~yaml
type: http
scheme: bearer
bearerFormat: JWT
~~~

### OAuth2

If the API describes token-issuance workflows such as Authorization Code, Client Credentials, or Refresh Token, use the **oauth2** security scheme and declare flows. Do not replace flows with bearerFormat:

~~~yaml
type: oauth2
flows:
  authorizationCode:
    authorizationUrl: https://identity.example.test/oauth2/authorize
    tokenUrl: https://identity.example.test/oauth2/token
    scopes:
      profile.read: Read profile
~~~

OAuth2 access tokens are usually sent as bearer tokens at the HTTP layer, but the OpenAPI OAuth2 scheme also describes the authorization flow and scopes. If you only need to describe an endpoint receiving an existing bearer token, an HTTP bearer scheme may be more suitable.

### API key

If the system uses a custom key string in a header, describe it with apiKey:

~~~yaml
type: apiKey
in: header
name: X-API-Key
~~~

Do not declare apiKey and add bearerFormat to imply it is a JWT bearer. The two mechanisms have different structures and transmission conventions.

## 10. JWT and opaque tokens: accurately describing the format in use

### JWT

JWT is a token format containing claims represented in a JSON structure. A JWT can be signed as JWS or encrypted as JWE. Many JWT access tokens are signed and sent as bearer tokens:

~~~yaml
type: http
scheme: bearer
bearerFormat: JWT
description: JWT access token issued by the Authorization Server.
~~~

Do not infer signing algorithms from bearerFormat. For instance, writing JWT does not specify whether the token uses RS256, ES256, or HS256; nor does it indicate the issuer, audience, lifetime, or key rotation.

### Opaque token

An opaque token is typically an identifier string not intended for clients to read claims from directly. The Resource Server can verify it via introspection or a corresponding lookup mechanism:

~~~yaml
type: http
scheme: bearer
bearerFormat: Opaque
description: Opaque access token; the server verifies it with the Authorization Server.
~~~

If the token has no stable public format, you can omit bearerFormat and explain usage in description.

### Do not put real tokens in documentation

Do not use active access tokens as examples, defaults, or in descriptions. Tokens can grant access to real data and operations. If header examples are needed, use non-validatable placeholder values and never use tokens from development or production environments.

## 11. Configuring bearerFormat with an OpenAPI bean

If the application manages documentation using an OpenAPI bean instead of annotations, you can create a SecurityScheme model:

~~~java
import io.swagger.v3.oas.models.OpenAPI;
import io.swagger.v3.oas.models.Components;
import io.swagger.v3.oas.models.security.SecurityScheme;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class OpenApiModelConfiguration {

    @Bean
    OpenAPI libraryOpenApi() {
        SecurityScheme bearerScheme = new SecurityScheme()
            .type(SecurityScheme.Type.HTTP)
            .scheme("bearer")
            .bearerFormat("JWT")
            .description("JWT access token.");

        return new OpenAPI()
            .components(new Components()
                .addSecuritySchemes("bearerAuth", bearerScheme));
    }
}
~~~

This bean declares the scheme in components. If you want to apply a global security requirement, add the requirement:

~~~java
return new OpenAPI()
    .components(new Components()
        .addSecuritySchemes("bearerAuth", bearerScheme))
    .addSecurityItem(
        new io.swagger.v3.oas.models.security.SecurityRequirement()
            .addList("bearerAuth")
    );
~~~

Do not declare multiple schemes with duplicate names simultaneously across annotations, beans, and customizers without intent. Multiple configuration sources can cause overrides or unpredictable results; pick one primary place to manage them and inspect the final JSON.

## 12. bearerFormat and Swagger UI Authorize

When the document has an HTTP bearer security scheme and operations have matching security requirements, Swagger UI can display the **Authorize** button. Users enter the token following the UI instructions; when executing operations, Swagger UI sends the Authorization header according to the declared scheme.

Expected request example:

~~~http
Authorization: Bearer <access-token>
~~~

bearerFormat can help readers recognize that the expected token is a JWT, but it does not automatically:

- Fetch tokens from an Identity Provider.
- Execute an OAuth2 login flow if only HTTP bearer is declared.
- Validate the token before sending the request.
- Expire or refresh tokens.
- Grant permissions to endpoints.

When entering a token in Authorize, inspect the request preview or Network tab to confirm the header has only a single Bearer prefix. Exact entry behavior can vary by Swagger UI version and security scheme type. Avoid entering the prefix if the UI prepends it automatically, which causes an invalid value like Bearer Bearer ....

If Swagger UI needs to execute an OAuth2 flow itself, configure a scheme of type oauth2 with the corresponding flow rather than merely setting bearerFormat to JWT.

## 13. Spring Security configuration must still be done separately

OpenAPI tells clients that endpoints need a bearer token. The application must configure Spring Security to verify the token when requests arrive.

For a JWT Resource Server, typical required parts include:

- Resource Server and JWT support dependencies matching your Spring Boot version.
- Issuer or JWK Set URI configuration to verify signatures and the issuing authority.
- Audience configuration or additional validators if required by the API.
- Authorization policies mapping scopes/authorities to endpoints.
- Handling for expired, mis-signed, or invalid tokens.

For opaque tokens, the Resource Server typically needs an introspection endpoint configuration and credentials to query the Authorization Server. These two runtime mechanisms differ even though both can be sent in the Authorization: Bearer header.

Outcomes:

| Request | Typical outcome |
|---|---|
| No token sent to an endpoint requiring authentication | 401 Unauthorized |
| Mis-signed, expired, or invalid token | 401 Unauthorized |
| Valid token lacking required authority | 403 Forbidden |
| Valid token with sufficient permissions | Request processed per endpoint logic |

Exact status codes can be customized by the application's exception handler or security configuration. OpenAPI should reflect actual responses.

## 14. Checking bearerFormat in the generated document

After running the application, open **/v3/api-docs** or the corresponding group's JSON endpoint. Locate components/securitySchemes:

~~~bash
curl -s http://localhost:8080/v3/api-docs \
  | jq '.components.securitySchemes.bearerAuth'
~~~

Expected output looks like:

~~~json
{
  "type": "http",
  "scheme": "bearer",
  "bearerFormat": "JWT",
  "description": "JWT access token in the Authorization header."
}
~~~

Check document-level security requirements:

~~~bash
curl -s http://localhost:8080/v3/api-docs | jq '.security'
~~~

Check requirements on a specific operation:

~~~bash
curl -s http://localhost:8080/v3/api-docs \
  | jq '.paths["/api/profile"].get.security'
~~~

Cross-check:

1. Is the scheme name in components correct?
2. Is type http and is scheme bearer?
3. Does bearerFormat reflect the actual token?
4. Do operations have security requirements referencing the exact name?
5. Are public endpoints properly overriding security?
6. Do 401/403 responses accurately describe server behavior?

If bearerFormat does not appear, check whether the annotation or bean is being read by springdoc and whether your swagger-annotations version supports the attribute. Do not switch to a custom invented property in OpenAPI; bearerFormat is the standard Security Scheme Object field name for HTTP bearer.

## 15. Testing runtime independently from documentation

A document containing bearerAuth does not prove the server is validating tokens. Send requests to protected endpoints in a test environment:

~~~bash
# Without token
curl -i http://localhost:8080/api/profile

# Placeholder or invalid token
curl -i \
  -H "Authorization: Bearer invalid-token" \
  http://localhost:8080/api/profile

# Valid token issued for the test environment
curl -i \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  http://localhost:8080/api/profile
~~~

Do not write real tokens into shell history, shared logs, or documentation. Use environment variables and minimal-privilege test tokens; do not paste token values into Knowledge content.

Check separately:

- Requests without a token are rejected if the endpoint requires authentication.
- Invalid or expired tokens are rejected.
- Valid tokens lacking permissions receive an appropriate response.
- Valid tokens with sufficient permissions can call the endpoint.
- Swagger UI sends the right header when using Authorize.

## 16. Common errors

| Symptom | Possible cause | Resolution |
|---|---|---|
| Swagger UI has no Authorize button | Only scheme declared without security requirements, or scheme not generated | Check components and security |
| Operation does not display bearer requirement | Missing requirement or referencing wrong scheme name | Add @SecurityRequirement and use the exact name |
| bearerFormat shows JWT while server expects opaque token | Metadata describes wrong token type | Fix bearerFormat or description to match runtime |
| Changing bearerFormat does not cause requests to be rejected | bearerFormat is only metadata | Configure Spring Security Resource Server |
| Header becomes Bearer Bearer ... | User entered prefix while UI adds it automatically | Check request preview and enter token in the format UI expects |
| Valid token still receives 403 | Token lacks required authority or scope | Check claim mapping and authorization rules |
| Expired token is still accepted | Validator/runtime does not check expiration or misconfigured | Check JwtDecoder/opaque introspection and validators |
| Security scheme duplicated | Same name declared across multiple sources | Choose one configuration place and inspect components |
| API key mistakenly described as bearer | Wrong type/scheme chosen | Use type apiKey or HTTP bearer matching the actual mechanism |
| Swagger UI Authorize works but direct curl gets 401 | Token not sent in request or server has a different policy | Check actual headers and runtime security |
| Docs say every endpoint needs a token while health is still public | Global security requirement not properly overridden | Set security: [] for public operations if appropriate |

## 17. Principles for describing bearerFormat accurately

- Use **type: http** and **scheme: bearer** for HTTP bearer authentication.
- Only set **bearerFormat: JWT** when tokens are actually JWTs.
- Use description to explain how to obtain the token and which header carries it.
- Keep the Security Scheme name stable and matching the Security Requirement.
- Separate Security Scheme declaration from Security Requirement application.
- Do not treat bearerFormat as a signing algorithm, validator, issuer, or OAuth2 flow.
- Do not use bearerFormat to describe API keys or HTTP Basic.
- Use an OAuth2 scheme if you need to describe authorization flows and scopes.
- Do not place real tokens in examples, source code, or documentation.
- Check both the OpenAPI JSON and Spring Security runtime.

## Conclusion

**bearerFormat** is optional metadata in an HTTP Bearer Security Scheme used to hint at the token format, such as JWT. Authentication configuration is still defined by **type: http** and **scheme: bearer**; applying it to operations requires a **Security Requirement** referencing the exact scheme name. springdoc-openapi can generate this metadata from @SecurityScheme or an OpenAPI bean, but it does not verify tokens and does not replace a Spring Security Resource Server. Describe the actual token in use, inspect components/securitySchemes and security in /v3/api-docs, and test runtime requests to confirm authentication genuinely works.
