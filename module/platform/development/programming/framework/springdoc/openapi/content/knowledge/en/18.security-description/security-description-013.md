# Describing 401, 403, and Related Headers to Match Actual Behavior

When an API is protected, clients need to know why a request was rejected and what to do next. Two common statuses are **401 Unauthorized** and **403 Forbidden**. They carry distinct HTTP meanings and are often accompanied by authentication headers such as the Authorization request header and the WWW-Authenticate response header.

In OpenAPI, Authorization is described using Security Schemes and Security Requirements. WWW-Authenticate is described as a response header on a 401 response; in certain Bearer Token flows, this header can also appear on a 403 when a token is valid yet lacks required scopes. Springdoc-openapi only publishes the contract. Spring Security, the resource server, or the gateway must actually return the corresponding status, headers, and body.

## 1. Distinguishing 401 and 403

These two statuses cannot be used interchangeably:

| Status | HTTP Meaning | Common scenarios |
|---|---|---|
| **401 Unauthorized** | The request lacks valid authentication credentials for the resource. The server rejects because the client is not authenticated. | Missing Bearer token, expired token, wrong signature, or invalid token. |
| **403 Forbidden** | The server understood the request but refuses to fulfill it. | The user is signed in yet lacks the required role, authority, or access permission. |

A practical distinction:

- **401**: the client needs to supply or refresh authentication credentials.
- **403**: the identity is known, yet that identity does not have permission to perform this action; resending the same credentials usually will not resolve the issue.

Do not assume every 403 means a user is signed in. A server can use 403 to deny based on policy, IP, tenant, or other business conditions. Similarly, an API may intentionally return 404 instead of 403 to avoid disclosing whether a resource exists. Document the application's actual behavior and security policy.

### 1.1. 401 must include an authentication challenge

According to HTTP semantics, a 401 response must include at least one challenge in the WWW-Authenticate header indicating the authentication method required by the resource. Example:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer realm="documents-api"
Content-Type: application/json

{
  "code": "AUTHENTICATION_REQUIRED",
  "message": "Authentication is required to access this resource"
}
~~~

The challenge depends on the authentication mechanism. For HTTP Basic it might be Basic realm="api"; for OAuth 2.0 Bearer Token it is typically Bearer realm="api". Do not hard-describe a Bearer challenge if the endpoint actually uses Basic, Mutual TLS, or another mechanism.

### 1.2. 403 does not require WWW-Authenticate

A typical 403 response only needs to state that the client lacks permission:

~~~http
HTTP/1.1 403 Forbidden
Content-Type: application/json

{
  "code": "ACCESS_DENIED",
  "message": "You do not have permission to perform this action"
}
~~~

Do not automatically add WWW-Authenticate to every 403 response. However, with Bearer Tokens per RFC 6750, cases where a token is valid yet lacks required scopes can return 403 with a challenge:

~~~http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer error="insufficient_scope", scope="documents:write"
Content-Type: application/json

{
  "code": "INSUFFICIENT_SCOPE",
  "message": "Token lacks the documents:write scope"
}
~~~

This is a specific case of Bearer authentication. If an application only uses role-based authorization and does not publish scopes in challenges, the 403 response does not need this header.

## 2. Authentication-related headers

| Header | Direction | Role | How to describe |
|---|---|---|---|
| Authorization | Request | Client sends credentials, such as a Bearer access token. | Declare a Security Scheme, not a regular query/header parameter. |
| WWW-Authenticate | Response | Server sends an authentication challenge in 401 responses; may describe Bearer errors in 403. | Declare in headers of the corresponding response. |
| Access-Control-Allow-Headers | Preflight response | Indicates which request headers browsers are allowed to send via CORS. | Configure CORS at server/gateway; usually not a per-operation business response header. |
| Access-Control-Expose-Headers | CORS response | Lets JavaScript read response headers not among CORS-safelisted response headers. | Configure CORS; WWW-Authenticate must be exposed if browser clients need to read it. |
| X-Request-ID | Response (application convention) | Provides an ID for log lookup or support. | Can be described as a response header if the server actually returns it. |

HTTP header names are case-insensitive. In OpenAPI, maintain consistent casing so the documentation stays readable.

### 2.1. Authorization is a security scheme, not a regular parameter

Do not declare Authorization as a Parameter Object like this:

~~~yaml
parameters:
  - name: Authorization
    in: header
    required: true
    schema:
      type: string
~~~

OpenAPI specifies that Authorization is described via a security scheme. For Bearer JWT, declare an HTTP-type scheme:

~~~yaml
components:
  securitySchemes:
    bearerAuth:
      type: http
      scheme: bearer
      bearerFormat: JWT
~~~

Then attach the security requirement to operations or the whole document:

~~~yaml
security:
  - bearerAuth: []
~~~

Swagger UI will display the matching Authorize mechanism and send credentials per the scheme. Describing a security scheme does not protect endpoints on its own; Spring Security or gateway configuration must still enforce authentication.

### 2.2. WWW-Authenticate is a response header

WWW-Authenticate belongs to HTTP responses. Do not place it in request parameters. In OpenAPI, it sits under the specific response:

~~~yaml
responses:
  '401':
    description: Unauthenticated or invalid credentials
    headers:
      WWW-Authenticate:
        description: Challenge for the authentication mechanism supported by the endpoint
        schema:
          type: string
        example: 'Bearer realm="documents-api"'
~~~

For a 401 response, the server can send multiple challenges for multiple supported schemes. An OpenAPI Header Object typically describes the header value as a string. Examples and descriptions should reflect the challenges the server actually emits; do not assume clients always receive one fixed Bearer string.

## 3. Describing Bearer authentication in Springdoc

You can register a security scheme using the OpenAPI model in a bean:

~~~java
import io.swagger.v3.oas.models.Components;
import io.swagger.v3.oas.models.OpenAPI;
import io.swagger.v3.oas.models.info.Info;
import io.swagger.v3.oas.models.security.SecurityRequirement;
import io.swagger.v3.oas.models.security.SecurityScheme;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class OpenApiSecurityConfiguration {

    @Bean
    OpenAPI apiSecurity() {
        return new OpenAPI()
                .info(new Info()
                        .title("Documents API")
                        .version("1.0.0"))
                .components(new Components()
                        .addSecuritySchemes(
                                "bearerAuth",
                                new SecurityScheme()
                                        .type(SecurityScheme.Type.HTTP)
                                        .scheme("bearer")
                                        .bearerFormat("JWT")
                        ))
                .addSecurityItem(
                        new SecurityRequirement().addList("bearerAuth")
                );
    }
}
~~~

In the example, the scheme is named bearerAuth, uses HTTP Bearer, and the token format is JWT. bearerFormat is only an informational hint for documentation; OpenAPI does not verify JWT signatures or claims.

If the application already has an OpenAPI bean declaring title, servers, schemas, or response components, add the security scheme and requirement to that existing bean. Do not create multiple independent OpenAPI beans with overlapping configurations.

### 3.1. Protecting only operations that need authentication

You can place security requirements at the controller or operation level via annotations:

~~~java
import io.swagger.v3.oas.annotations.security.SecurityRequirement;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import java.util.List;

@RestController
@SecurityRequirement(name = "bearerAuth")
class DocumentController {

    @GetMapping("/api/documents")
    List<DocumentResponse> list() {
        return documentService.findAll();
    }
}
~~~

If every endpoint is protected, a document-level requirement in the OpenAPI bean is concise. If only certain operations are protected, place the requirement at the appropriate operation/controller level.

When a security requirement is set globally while a public operation exists, that OpenAPI operation needs to override it with empty security (security: []). Inspect the final JSON to ensure Swagger UI does not require a token for public endpoints.

## 4. Declaring 401 and WWW-Authenticate with annotations

A 401 response should have a clear description, an error body if the application returns one, and the challenge header:

~~~java
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.headers.Header;
import io.swagger.v3.oas.annotations.media.Content;
import io.swagger.v3.oas.annotations.media.Schema;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import io.swagger.v3.oas.annotations.responses.ApiResponses;
import io.swagger.v3.oas.annotations.security.SecurityRequirement;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;
import java.util.UUID;

@RestController
class DocumentController {

    @GetMapping("/api/documents/{id}")
    @Operation(
            summary = "Get document by ID",
            security = @SecurityRequirement(name = "bearerAuth")
    )
    @ApiResponses({
        @ApiResponse(
            responseCode = "200",
            description = "Document found",
            content = @Content(
                mediaType = "application/json",
                schema = @Schema(implementation = DocumentResponse.class)
            )
        ),
        @ApiResponse(
            responseCode = "401",
            description = "Missing or invalid Bearer token",
            headers = @Header(
                name = "WWW-Authenticate",
                description = "Bearer authentication challenge",
                schema = @Schema(
                    type = "string",
                    example = "Bearer realm=\"documents-api\""
                )
            ),
            content = @Content(
                mediaType = "application/json",
                schema = @Schema(implementation = ApiError.class)
            )
        )
    })
    DocumentResponse findById(@PathVariable UUID id) {
        return documentService.findById(id);
    }
}
~~~

Each annotation has a specific role:

- SecurityRequirement describes that the operation needs the bearerAuth scheme.
- ApiResponse with responseCode 401 describes the unauthenticated response.
- Header places WWW-Authenticate on the response, not as a request parameter.
- Content and Schema describe the error body if runtime returns JSON.

If an endpoint returns 401 with no body, omit content from the response. Do not document ApiError merely because the application has some error DTO; the schema must match the actual body.

## 5. Describing 403 according to access permissions

A 403 response typically describes the reason permission was denied. For standard role-based authorization, the body can contain an error code and helpful information:

~~~java
@ApiResponse(
    responseCode = "403",
    description = "Authenticated but lacks permission to access the document",
    content = @Content(
        mediaType = "application/json",
        schema = @Schema(implementation = ApiError.class)
    )
)
~~~

Do not attach WWW-Authenticate to this response if the server does not emit a challenge. If the application uses OAuth2 Bearer Tokens and returns insufficient_scope, you can document the header:

~~~java
@ApiResponse(
    responseCode = "403",
    description = "Valid token but lacks required scope",
    headers = @Header(
        name = "WWW-Authenticate",
        description = "Bearer challenge indicating insufficient scope",
        schema = @Schema(
            type = "string",
            example = "Bearer error=\"insufficient_scope\", scope=\"documents:write\""
        )
    ),
    content = @Content(
        mediaType = "application/json",
        schema = @Schema(implementation = ApiError.class)
    )
)
~~~

If an API has multiple distinct types of 403 responses, describe each response accurately or separate operations/response components semantically. Do not reuse a single insufficient_scope example for all permission-denial cases.

## 6. Bearer Token errors per RFC 6750

For OAuth 2.0 Bearer Tokens, common errors have characteristic representations:

| Scenario | Common status | Challenge |
|---|---:|---|
| No token sent for a resource requiring authentication | 401 | Bearer realm="api" |
| Access token expired, wrong, or invalid | 401 | Bearer error="invalid_token" |
| Request uses token improperly or uses multiple token submission methods | 400 in invalid_request cases | Bearer error="invalid_request" |
| Valid token lacking sufficient scopes | 403 | Bearer error="insufficient_scope"; may include required scopes. |

Error values and challenges must adhere to what the server actually implements. Never expose tokens, signatures, sensitive claims, or overly detailed internal reasons in error_description.

Example challenge for an invalid token:

~~~http
WWW-Authenticate: Bearer error="invalid_token", error_description="The access token expired"
~~~

Example challenge for insufficient scope:

~~~http
WWW-Authenticate: Bearer error="insufficient_scope", scope="documents:write"
~~~

Not every API using JWTs must expose error_description externally. Minimal information is usually enough for clients to know they need to re-authenticate or request appropriate permissions.

## 7. Reusing 401 and 403 responses in components

If many operations share the same responses, declare them in components.responses and reference them via $ref. OpenAPI model configuration example:

~~~java
import io.swagger.v3.oas.models.Components;
import io.swagger.v3.oas.models.OpenAPI;
import io.swagger.v3.oas.models.info.Info;
import io.swagger.v3.oas.models.media.Content;
import io.swagger.v3.oas.models.media.MediaType;
import io.swagger.v3.oas.models.media.Schema;
import io.swagger.v3.oas.models.media.StringSchema;
import io.swagger.v3.oas.models.headers.Header;
import io.swagger.v3.oas.models.responses.ApiResponse;
import io.swagger.v3.oas.models.security.SecurityRequirement;
import io.swagger.v3.oas.models.security.SecurityScheme;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class ApiContractConfiguration {

    @Bean
    OpenAPI apiContract() {
        Schema<?> errorSchema = new Schema<>()
                .type("object")
                .addRequiredItem("code")
                .addRequiredItem("message")
                .addProperty("code", new StringSchema())
                .addProperty("message", new StringSchema());

        Content errorContent = new Content().addMediaType(
                "application/json",
                new MediaType().schema(
                        new Schema<>().$ref("#/components/schemas/ApiError")
                )
        );

        ApiResponse unauthorized = new ApiResponse()
                .description("Unauthenticated or invalid Bearer token")
                .addHeaderObject(
                        "WWW-Authenticate",
                        new Header()
                                .description("Bearer authentication challenge")
                                .schema(new StringSchema()
                                        .example("Bearer realm=\"documents-api\""))
                )
                .content(errorContent);

        ApiResponse forbidden = new ApiResponse()
                .description("Authenticated but lacks permission to perform the action")
                .content(errorContent);

        Components components = new Components()
                .addSchemas("ApiError", errorSchema)
                .addResponses("Unauthorized", unauthorized)
                .addResponses("Forbidden", forbidden)
                .addSecuritySchemes(
                        "bearerAuth",
                        new SecurityScheme()
                                .type(SecurityScheme.Type.HTTP)
                                .scheme("bearer")
                                .bearerFormat("JWT")
                );

        return new OpenAPI()
                .info(new Info().title("Documents API").version("1.0.0"))
                .components(components)
                .addSecurityItem(new SecurityRequirement().addList("bearerAuth"));
    }
}
~~~

Then controllers can reference them:

~~~java
@ApiResponses({
    @ApiResponse(
        responseCode = "401",
        ref = "#/components/responses/Unauthorized"
    ),
    @ApiResponse(
        responseCode = "403",
        ref = "#/components/responses/Forbidden"
    )
})
~~~

The two response components above assume identical JSON error bodies. If 401 has no body or 403 has a different structure, create separate appropriate components. If 403 uses Bearer insufficient_scope, define another response component with the WWW-Authenticate header and describe that challenge accurately.

## 8. Configuring Spring Security so statuses reflect actual flow

For an OAuth2 Resource Server using JWT, authorization configuration can look like:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class ApiSecurityConfiguration {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(authorize -> authorize
                        .requestMatchers("/api/public/**").permitAll()
                        .requestMatchers("/api/admin/**").hasAuthority("SCOPE_admin")
                        .anyRequest().authenticated()
                )
                .oauth2ResourceServer(resourceServer -> resourceServer
                        .jwt(Customizer.withDefaults())
                )
                .build();
    }
}
~~~

With this configuration, unauthenticated requests to protected endpoints pass through the authentication entry point and return 401. Authenticated users lacking required authorities are access-denied and return 403. Spring Security's Resource Server has default Bearer handlers to generate challenges matching Bearer Token errors.

If you replace AuthenticationEntryPoint or AccessDeniedHandler to produce custom error bodies, preserve the status and WWW-Authenticate matching the error type. In particular, custom handlers must not silently drop the 401 challenge. For Bearer Tokens lacking scopes, check whether the handler emits the insufficient_scope challenge if the contract publishes it.

### 8.1. Why might @RestControllerAdvice not catch 401/403?

Authentication and authorization errors typically occur in the Spring Security filter chain before the request reaches a controller. Therefore, a `@RestControllerAdvice` handling Spring MVC exceptions does not automatically handle every error from security filters.

To standardize bodies for 401/403, configure AuthenticationEntryPoint and AccessDeniedHandler in SecurityFilterChain or use the Resource Server's default handlers combined with an appropriate body mechanism. Then inspect both headers and bodies in actual HTTP responses.

## 9. CORS and browser visibility of WWW-Authenticate

A frontend application running on a different origin may receive a 401 response yet JavaScript cannot read WWW-Authenticate because it is not a CORS-safelisted response header. If the frontend needs to read the challenge to decide whether to prompt re-login, the server must expose the header via CORS.

Example:

~~~java
import java.util.List;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.CorsConfigurationSource;
import org.springframework.web.cors.UrlBasedCorsConfigurationSource;

@Configuration
class ApiCorsConfiguration {

    @Bean
    CorsConfigurationSource corsConfigurationSource() {
        CorsConfiguration configuration = new CorsConfiguration();
        configuration.setAllowedOrigins(List.of("https://app.example.com"));
        configuration.setAllowedMethods(
                List.of("GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"));
        configuration.setAllowedHeaders(
                List.of("Authorization", "Content-Type", "X-Correlation-ID"));
        configuration.setExposedHeaders(
                List.of("WWW-Authenticate", "X-Request-ID"));

        UrlBasedCorsConfigurationSource source =
                new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration("/api/**", configuration);
        return source;
    }
}
~~~

Enable CORS in SecurityFilterChain with http.cors(Customizer.withDefaults()) when the application uses a CorsConfigurationSource as above.

- allowedHeaders lets browsers send Authorization and specified request headers.
- exposedHeaders lets JavaScript read WWW-Authenticate and X-Request-ID from responses.
- allowedOrigins should list trusted origins; do not carelessly allow wildcards when credentials are used.

Access-Control-Allow-Headers and Access-Control-Expose-Headers are typically generated from CORS configuration and preflight/actual requests. They do not replace Authorization or WWW-Authenticate, and usually do not need to be repeated as business response headers on each OpenAPI operation.

## 10. Inspecting the generated OpenAPI document

After configuring schemes and annotations, open /v3/api-docs or the corresponding group URL. Check the following points:

1. components.securitySchemes.bearerAuth has type: http, scheme: bearer.
2. Protected operations have security requirements pointing to bearerAuth.
3. Public operations do not unintentionally inherit security requirements.
4. 401 responses have descriptions and WWW-Authenticate headers if the server returns challenges.
5. 403 responses only include WWW-Authenticate when the actual authorization flow emits that challenge.
6. Error body schemas match runtime JSON; responses without bodies declare no content.
7. Response components referenced by $ref exist in components.responses.

Condensed OpenAPI example:

~~~yaml
paths:
  /api/documents/{id}:
    get:
      security:
        - bearerAuth: []
      responses:
        '200':
          description: Document found
        '401':
          description: Unauthenticated or invalid token
          headers:
            WWW-Authenticate:
              description: Bearer authentication challenge
              schema:
                type: string
              example: 'Bearer realm="documents-api"'
        '403':
          description: Authenticated but lacks access permission
components:
  securitySchemes:
    bearerAuth:
      type: http
      scheme: bearer
      bearerFormat: JWT
~~~

This example shows a standard 403 without WWW-Authenticate. If the API uses Bearer insufficient_scope, add the corresponding header and example to the 403 response.

## 11. Testing the contract and HTTP behavior

Inspecting the OpenAPI document is not enough to prove the security filter chain works. Both the documentation and runtime cases must be tested.

### 11.1. Verifying OpenAPI security schemes and response headers

~~~java
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
class SecurityOpenApiContractTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void documentsBearerSchemeAndUnauthorizedChallenge() throws Exception {
        mockMvc.perform(get("/v3/api-docs"))
                .andExpect(status().isOk())
                .andExpect(jsonPath(
                        "$.components.securitySchemes.bearerAuth.scheme"
                ).value("bearer"))
                .andExpect(jsonPath(
                        "$.paths['/api/documents/{id}'].get.responses['401'].headers.WWW-Authenticate"
                ).exists());
    }
}
~~~

Path names in JSONPath must match the application's actual mappings. If the response uses $ref, inspect the component and the $ref value instead of looking for headers directly inside the operation response.

### 11.2. Testing unauthenticated requests

~~~java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@Test
void returns401AndChallengeWhenCredentialIsMissing() throws Exception {
    mockMvc.perform(get("/api/admin/reports"))
            .andExpect(status().isUnauthorized())
            .andExpect(header().exists("WWW-Authenticate"));
}
~~~

This test assumes the endpoint requires Bearer authentication and the handler returns a challenge. If the application uses a different mechanism, check the corresponding challenge.

For invalid or expired tokens, add tests sending `Authorization: Bearer <invalid-token>` and confirm the server returns `401`. If the server publishes errors per RFC 6750, check that WWW-Authenticate contains the `invalid_token` error; do not assert the entire header string if parameter order or error_description can vary.

### 11.3. Testing an authenticated user lacking permissions

With Spring Security Test and the JWT request post-processor, you can create an authentication with insufficient authorities:

~~~java
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.jwt;
import org.springframework.security.core.authority.SimpleGrantedAuthority;

@Test
void returns403WhenAuthenticatedUserLacksRequiredAuthority() throws Exception {
    mockMvc.perform(get("/api/admin/reports")
                    .with(jwt().authorities(
                            new SimpleGrantedAuthority("SCOPE_documents:read"))))
            .andExpect(status().isForbidden());
}
~~~

This test verifies authorization on an endpoint requiring another authority, such as SCOPE_admin. Whether WWW-Authenticate is present on 403 depends on the handler and Bearer insufficient_scope implementation; only assert the header if the API contract explicitly specifies it.

## 12. Common errors

- **Documenting 401 without WWW-Authenticate**: omitting the challenge prevents the response from accurately reflecting HTTP authentication semantics.
- **Using 401 for all insufficient-permission errors**: authenticated users lacking authorities usually receive 403.
- **Attaching WWW-Authenticate to every 403**: only add it when the server actually emits a challenge, such as Bearer insufficient_scope.
- **Declaring Authorization as a header parameter**: use components.securitySchemes and security requirements.
- **Using Bearer examples for endpoints using Basic or another mechanism**: challenges must match the actual authentication scheme.
- **Assuming @RestControllerAdvice catches all security errors**: filter chain errors typically require AuthenticationEntryPoint or AccessDeniedHandler.
- **Custom handlers dropping default challenges**: preserve status, WWW-Authenticate, and error semantics when replacing bodies.
- **Swagger UI shows Authorize yet server does not validate tokens**: OpenAPI only documents; Spring Security/gateway enforces.
- **Browsers cannot read WWW-Authenticate**: configure CORS exposed headers if the frontend needs to read it.
- **Publishing error bodies that do not match runtime**: schema, media type, and status must match actual responses.
- **Failing to check public operations**: global security requirements may unintentionally apply to endpoints needing no token.

## 13. Workflow for describing security on an operation

1. **Identify the authentication flow**: Bearer JWT, Basic, API key, OAuth2, or another mechanism.
2. **Identify rejection conditions**: missing/invalid credentials yield 401; insufficient permissions yield 403 per API policy.
3. **Identify challenges**: explicitly record the WWW-Authenticate header the server actually emits on 401 and specific 403 cases.
4. **Register the security scheme**: describe Authorization using components.securitySchemes.
5. **Attach security requirements**: place at the document, controller, or operation level with the right scope.
6. **Document responses**: add 401/403, headers, and bodies matching actual behavior.
7. **Synchronize Spring Security**: configure entry points, access denied handlers, and resource server.
8. **Configure CORS**: expose WWW-Authenticate if browser clients must read it.
9. **Inspect /v3/api-docs**: verify schemes, requirements, response headers, and schemas.
10. **Test at runtime**: missing token, invalid/expired token, and valid token lacking permissions.

## 14. Review checklist

- [ ] 401 and 403 are distinguished by authentication vs. authorization cause.
- [ ] 401 responses have an appropriate WWW-Authenticate challenge.
- [ ] 403 only has WWW-Authenticate when the server actually emits a challenge, such as insufficient_scope.
- [ ] Authorization is described via a security scheme.
- [ ] Security requirements apply only to protected operations.
- [ ] Error bodies, media types, and schemas match runtime.
- [ ] AuthenticationEntryPoint and AccessDeniedHandler return the right statuses/headers.
- [ ] Not assuming @RestControllerAdvice handles errors from the security filter chain.
- [ ] CORS allows Authorization and exposes WWW-Authenticate when needed.
- [ ] /v3/api-docs has been checked for the default document and relevant groups.
- [ ] Integration tests cover missing credentials, invalid credentials, and insufficient permissions.

## 15. References

- [RFC 9110 – HTTP Semantics: 401 Unauthorized](https://www.rfc-editor.org/rfc/rfc9110.html#section-15.5.2)
- [RFC 9110 – HTTP Semantics: 403 Forbidden](https://www.rfc-editor.org/rfc/rfc9110.html#section-15.5.4)
- [RFC 9110 – WWW-Authenticate](https://www.rfc-editor.org/rfc/rfc9110.html#section-11.6.1)
- [RFC 6750 – OAuth 2.0 Bearer Token Usage, Error Codes](https://www.rfc-editor.org/rfc/rfc6750.html#section-3.1)
- [OpenAPI Specification 3.1.2 – Security Scheme Object](https://spec.openapis.org/oas/v3.1.2.html#security-scheme-object)
- [OpenAPI Specification 3.1.2 – Security Requirement Object](https://spec.openapis.org/oas/v3.1.2.html#security-requirement-object)
- [OpenAPI Specification 3.1.2 – Response Object](https://spec.openapis.org/oas/v3.1.2.html#response-object)
- [Spring Security – OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html)
- [Spring Framework – CORS](https://docs.spring.io/spring-framework/reference/web/webmvc-cors.html)
- [springdoc-openapi documentation](https://springdoc.org/)

401 and 403 describe two distinct rejection reasons. Describe Authorization with security schemes, publish WWW-Authenticate in the right responses, and keep Spring Security, CORS, and OpenAPI reflecting one consistent HTTP behavior. When clients know when to re-authenticate and when to request additional permissions, API integration becomes clearer and more reliable.
