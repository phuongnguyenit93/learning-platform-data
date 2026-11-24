# Overriding Global Requirements for Public Endpoints

In many Spring Boot applications, most APIs require authentication via JWT, API key, or OAuth 2.0. Consequently, the OpenAPI document often declares a security requirement at the whole-document level. However, certain endpoints such as login, registration, service health checks, or public catalog retrieval do not require credentials.

OpenAPI allows each operation to override the global security requirement. With `springdoc-openapi`, you can place an empty `@SecurityRequirements` annotation on a method to publish that the operation has no security requirements. It is essential to understand the difference between security metadata in the documentation and actual authentication/authorization rules in Spring Security: annotations only control OpenAPI, while runtime security configuration decides whether requests are permitted through.

## 1. How do global security requirements work?

OpenAPI can declare `security` at the root level to apply to all operations. For example, an API using bearer JWT:

```yaml
openapi: 3.0.3
security:
  - bearerAuth: []
components:
  securitySchemes:
    bearerAuth:
      type: http
      scheme: bearer
      bearerFormat: JWT
```

`components.securitySchemes` defines an authentication mechanism named `bearerAuth`. Root-level `security` requires operations to use that mechanism, unless an operation declares its own `security` to override it.

If an operation lacks a `security` field, it inherits the root-level requirement. Therefore, merely omitting the `@SecurityRequirement` annotation from a method does not automatically make that method public when the document has global security.

## 2. Distinguishing `SecurityScheme` and `SecurityRequirement`

These two components serve different purposes:

| Component | Location in OpenAPI | Role |
| --- | --- | --- |
| Security scheme | `components.securitySchemes` | Describes how clients provide credentials, such as bearer tokens, API keys, or OAuth 2.0. |
| Security requirement | `security` at root or operation level | Specifies which operations require one or more defined security schemes. |

Simply declaring `bearerAuth` in `components.securitySchemes` does not mandate operations to use a bearer token. A security requirement at the root or operation level is needed to express that requirement in the contract.

Conversely, a security requirement must reference the exact declared scheme name. If the document uses `bearerAuth` while components only contain `jwtAuth`, the specification is inconsistent and Swagger UI may not handle authentication as intended.

## 3. Declaring global security in springdoc

You can define schemes and requirements using an `OpenAPI` bean:

```java
import io.swagger.v3.oas.models.Components;
import io.swagger.v3.oas.models.OpenAPI;
import io.swagger.v3.oas.models.info.Info;
import io.swagger.v3.oas.models.security.SecurityRequirement;
import io.swagger.v3.oas.models.security.SecurityScheme;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class OpenApiConfiguration {

    @Bean
    OpenAPI customOpenAPI() {
        return new OpenAPI()
            .info(new Info()
                .title("Store API")
                .version("1.0.0"))
            .components(new Components()
                .addSecuritySchemes("bearerAuth",
                    new SecurityScheme()
                        .type(SecurityScheme.Type.HTTP)
                        .scheme("bearer")
                        .bearerFormat("JWT")))
            .addSecurityItem(new SecurityRequirement()
                .addList("bearerAuth"));
    }
}
```

In the example:

- `addSecuritySchemes("bearerAuth", ...)` registers the scheme in `components.securitySchemes`.
- `type(HTTP)` and `scheme("bearer")` describe HTTP Bearer Authentication.
- `bearerFormat("JWT")` provides a token format hint for documentation tools.
- `addSecurityItem(...)` adds a security requirement at the root level, applying by default to operations.

You can declare the scheme with `@SecurityScheme` and global security with `@OpenAPIDefinition(security = ...)`. Pick one consistent configuration style to avoid duplicate declarations or mismatched scheme names. Springdoc also supports defining security schemes via an OpenAPI bean in its official FAQ documentation.

## 4. Overriding global security for a public endpoint

Place an empty `@SecurityRequirements` on the method to be made public:

```java
import io.swagger.v3.oas.annotations.security.SecurityRequirements;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class PublicController {

    @GetMapping("/api/public/status")
    @SecurityRequirements
    PublicStatus getStatus() {
        return new PublicStatus("UP");
    }
}
```

`@SecurityRequirements` is a container annotation holding a list of `@SecurityRequirement`. Placing this annotation empty on a method lets springdoc explicitly record that the operation has an empty list of security requirements, thereby overriding the root-level requirement.

The generated OpenAPI looks like:

```yaml
security:
  - bearerAuth: []
paths:
  /api/public/status:
    get:
      responses:
        '200':
          description: Service status
      security: []
  /api/private/profile:
    get:
      responses:
        '200':
          description: User profile
```

Operation `/api/public/status` has `security: []`, meaning it does not inherit the root-level security requirement. Operation `/api/private/profile` declares no custom `security` and continues to inherit `bearerAuth`.

Apply the annotation on the specific method that needs to be public. Placing `@SecurityRequirements` at the controller level may affect all operations in that controller.

## 5. Distinguishing `security: []` from `security: [{}]`

This is an important distinction in OpenAPI:

| Value on operation | Meaning |
| --- | --- |
| No `security` field | Inherits root-level security requirement. |
| `security: []` | Overrides and removes global security requirement for that operation. |
| `security: [{}]` | Allows anonymous access as a security option; can be combined with other authentication options. |
| `security: [{ bearerAuth: [] }]` | Requires a bearer token. |

Example of `security: [{}]` alongside a bearer option:

```yaml
security:
  - {}
  - bearerAuth: []
```

This list expresses that clients can call the operation anonymously or with a bearer token. This represents optional authentication—for example, an endpoint that can return personalized data if a client sends a token while still allowing unauthenticated guests to view basic content.

For completely public endpoints where optional authentication is not needed, use `security: []`. Do not confuse the empty array `[]` with the empty object `{}`.

## 6. Why use `@SecurityRequirements` instead of just writing `@Operation(security = {})`?

`@Operation.security` is an annotation array whose default value is empty. In some versions or annotation processing paths, an empty array may be treated as declaring no security metadata, causing the operation to continue inheriting global security.

`@SecurityRequirements` is a distinct annotation. Its presence clearly expresses the intent to override with an empty requirement list. This is the approach springdoc supports to remove global security for an operation. Therefore, use:

```java
@GetMapping("/api/public/status")
@SecurityRequirements
PublicStatus getStatus() {
    return new PublicStatus("UP");
}
```

Then inspect `/v3/api-docs` to confirm the operation actually has `security: []`. Do not just look at the annotation in source code and assume the documented output is right. If the project uses an older version of springdoc or swagger-annotations, verify that version's support before applying it broadly.

## 7. AND and OR rules in security requirements

OpenAPI represents multiple authentication mechanisms using a list of security requirement objects:

- Multiple schemes inside the same object mean the client must satisfy all of those schemes (AND).
- Multiple objects in the array mean the client can satisfy any one of the options (OR).

Example requiring both a bearer token and an API key simultaneously:

```yaml
security:
  - bearerAuth: []
    clientKey: []
```

Example allowing either a bearer token or an API key:

```yaml
security:
  - bearerAuth: []
  - clientKey: []
```

When overriding global security, inspect the entire requirement list being used. If an operation needs a different authentication mechanism, declare the new requirement on the operation instead of using an empty list. If the operation is completely public, use an empty `@SecurityRequirements`.

## 8. Overriding security in runtime Spring Security configuration

`@SecurityRequirements` only affects OpenAPI documentation. For real requests to bypass login, you must configure Spring Security to allow access to that endpoint.

Example with Spring Security:

```java
@Configuration
class SecurityConfiguration {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/api/public/**").permitAll()
                .anyRequest().authenticated())
            .build();
    }
}
```

`permitAll()` allows requests to public paths to pass the authorization step without an authenticated user. Remaining endpoints still require authentication under this configuration.

Both changes must be made and verified separately:

1. **OpenAPI:** `@SecurityRequirements` gives the operation `security: []`, preventing Swagger UI from marking that operation as requiring authentication per the global requirement.
2. **Runtime:** `requestMatchers(...).permitAll()` lets real requests reach the endpoint without logging in.

If you only do step 1, Swagger UI may send requests without a token, yet Spring Security still returns `401` or `403`. If you only do step 2, the API can be called publicly, yet the docs still show a bearer token as required.

Beyond authorization rules, inspect custom authentication filters. A custom filter might reject requests lacking a token before the request reaches `permitAll()`. In that case, the filter must skip public paths or authenticate only when credentials are present as designed. `permitAll()` does not automatically bypass every filter in the security chain.

## 9. Complete example: public API and private API

A controller can contain both types of endpoints:

```java
@RestController
@RequestMapping("/api")
class AccountController {

    @GetMapping("/public/health")
    @SecurityRequirements
    HealthResponse health() {
        return new HealthResponse("UP");
    }

    @GetMapping("/account/profile")
    ProfileResponse profile(@AuthenticationPrincipal Jwt jwt) {
        return accountService.getProfile(jwt.getSubject());
    }
}
```

The OpenAPI document can publish:

```yaml
security:
  - bearerAuth: []
paths:
  /api/public/health:
    get:
      security: []
  /api/account/profile:
    get:
      responses:
        '200':
          description: Account profile
```

The health endpoint requires no bearer token per the contract; the profile endpoint inherits the global requirement. Spring Security must also permit `/api/public/health` and protect `/api/account/profile` accordingly.

If a method allows anonymous access while optionally accepting a principal to personalize the response, design the principal parameter as nullable or optional and explicitly test behavior when no user is signed in. Never assume `@AuthenticationPrincipal` is always populated on a public endpoint.

## 10. Verifying results in OpenAPI and Swagger UI

After adding `@SecurityRequirements`, inspect the generated document:

1. Open `/v3/api-docs` or the corresponding group's documentation endpoint.
2. Confirm root `security` still contains the global requirement such as `bearerAuth`.
3. Locate the public operation and confirm the `security` field exists with an empty array `[]`.
4. Locate private operations and confirm they have no dedicated `security`, so they inherit the root requirement.
5. Open Swagger UI and confirm the public operation does not show a mandatory bearer token lock state, while private operations still show security requirements.
6. Use **Try it out** without entering a token to call the public endpoint.
7. Call a private endpoint without a token and confirm the server rejects it per runtime policy.
8. Call a private endpoint with a valid token and confirm the request is processed.

If the application has `GroupedOpenApi`, inspect the document of each group containing the endpoint. Each group may have its own customizers or different operation scopes; results in the default `/v3/api-docs` do not prove all group documents are identical.

## 11. Testing documentation and runtime

You can use MockMvc to confirm a public endpoint has an empty security array in OpenAPI:

```java
@SpringBootTest
@AutoConfigureMockMvc
class PublicSecurityDocumentationTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void publicOperationOverridesGlobalSecurity() throws Exception {
        mockMvc.perform(get("/v3/api-docs"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.security[0].bearerAuth").exists())
            .andExpect(jsonPath("$['paths']['/api/public/health']['get']['security']").isArray())
            .andExpect(jsonPath("$['paths']['/api/public/health']['get']['security']").isEmpty());
    }

    @Test
    void publicEndpointCanBeCalledWithoutAuthentication() throws Exception {
        mockMvc.perform(get("/api/public/health"))
            .andExpect(status().isOk());
    }
}
```

The first test verifies the documentation contract. The second test verifies the runtime rule. You should also add tests for private endpoints to prove they still require authentication; the exact status may be `401` or `403` depending on the authentication entry point and application configuration.

## 12. Common errors

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| Public endpoint still shows a lock icon in Swagger UI | Operation lacks `security: []` and continues inheriting root security | Place `@SecurityRequirements` on the method and inspect `/v3/api-docs`. |
| `@Operation(security = {})` does not override global security | Empty array is treated as missing metadata in the current version | Use the empty container annotation `@SecurityRequirements`. |
| Docs remove the lock yet real requests still return `401` | Only changed OpenAPI without configuring Spring Security | Add a `permitAll()` rule for the right path and inspect authentication filters. |
| API is reachable yet Swagger UI still asks for a token | Runtime was opened up while OpenAPI still inherits root security | Add `@SecurityRequirements` and verify operation security. |
| Every endpoint in the controller became public | Empty annotation placed at class level instead of method level | Move the annotation down to the specific public method. |
| Scheme disappears from Authorize | Deleted `components.securitySchemes` instead of only overriding requirements | Keep the global scheme; only set `security: []` on public operations. |
| Mismatched scheme name | Requirement references a different name than the component | Synchronize the exact name `bearerAuth`, `apiKey`, or actual scheme. |
| Endpoint is still blocked by a custom filter | Filter rejects requests lacking a token before the authorization step | Update matcher/bypass logic for public paths inside the filter. |
| One group still displays different security than the default group | Group's customizer or OpenAPI bean modifies its own document | Check `/v3/api-docs/{group}` URL and the group's customizer configuration. |

## 13. Application principles

- Define `SecurityScheme` once and use consistent names in security requirements.
- Use root `security` for the default policy of the whole document.
- Use an empty `@SecurityRequirements` on methods to override the root requirement for public endpoints.
- Distinguish `security: []` (removing global requirement) from `security: [{}]` (allowing an anonymous alternative).
- Do not delete security schemes when you only want one operation to be public.
- Configure `permitAll()` or an equivalent rule in Spring Security for runtime endpoints.
- Check custom authentication filters, because a filter can block requests before authorization rules run.
- Verify OpenAPI JSON, Swagger UI, and real HTTP requests.
- Check each group document individually if the application uses multiple `GroupedOpenApi` beans.

Overriding global security is an operation-level action in the OpenAPI contract. An empty `@SecurityRequirements` helps springdoc clearly publish that an operation does not inherit the document's security requirement; Spring Security still needs a runtime rule allowing the endpoint to be called anonymously. When both sides are verified, documentation accurately reflects public endpoints while application protection remains intact for private APIs.

## References

- [OpenAPI Specification 3.0 – Security Requirement and Operation Object](https://spec.openapis.org/oas/v3.0.3)
- [Springdoc OpenAPI FAQ – defining global SecurityScheme](https://springdoc.org/faq.html)
- [Swagger Core – `@SecurityRequirement` and `@SecurityRequirements`](https://docs.swagger.io/swagger-core/v2.2.53/apidocs/io/swagger/v3/oas/annotations/security/SecurityRequirements.html)
- [Spring Security – Authorize HTTP Requests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html)
- [Springdoc issue #259 – overriding global security with `@SecurityRequirements`](https://github.com/springdoc/springdoc-openapi/issues/259)
