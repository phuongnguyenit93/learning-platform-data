# Multiple Required Schemes vs. Alternative Options

An API may support multiple authentication mechanisms: bearer tokens, API keys, HTTP Basic, or OAuth2. When describing security in OpenAPI, you must specify whether clients must provide multiple mechanisms simultaneously or simply choose one of the supported alternatives.

OpenAPI represents these two cases using the Security Requirement structure:

- Multiple security schemes inside the same Security Requirement Object mean all schemes must be satisfied (AND).
- Multiple Security Requirement Objects in the security array mean any single object can be satisfied (OR).

This is a core distinction when documenting security with springdoc-openapi. If the two structures are swapped by mistake, Swagger UI may instruct clients to send the wrong credentials and the documentation will misrepresent API policy.

## 1. Distinguishing Security Scheme and Security Requirement

These two components answer two different questions:

| Component | Role | Example |
| --- | --- | --- |
| Security Scheme | Defines an authentication mechanism that can be used | Bearer JWT, API key in header, OAuth2 |
| Security Requirement | Specifies which mechanisms an operation requires | Bearer JWT and Partner API key simultaneously |

Security Schemes are typically declared in components.securitySchemes. Security Requirements are placed at the document or operation level via the security field.

Example defining two schemes:

~~~yaml
components:
  securitySchemes:
    bearerAuth:
      type: http
      scheme: bearer
      bearerFormat: JWT
    partnerApiKey:
      type: apiKey
      in: header
      name: X-Partner-Key
~~~

This definition only creates two referenceable mechanisms. It does not state whether an endpoint needs both or just one of them. That is determined by the security structure.

## 2. Multiple schemes in the same object is AND

If an operation requires both a bearer token and an API key simultaneously, place both scheme names inside the same Security Requirement Object:

~~~yaml
security:
  - bearerAuth: []
    partnerApiKey: []
~~~

The client must send both:

~~~http
POST /api/partner/orders
Authorization: Bearer eyJhbGciOi...
X-Partner-Key: partner-key-value
Content-Type: application/json
~~~

If either the bearer token or the API key is missing, the request fails to meet the published requirement. This representation fits when the system needs a user/service identity via a bearer token while also requiring a partner identification key via an API key.

A single Security Requirement Object can contain multiple schemes. All schemes within that object must be satisfied for the object to be considered valid.

## 3. Multiple objects in the array is OR

If the API accepts either a bearer token or an API key as two independent options, declare two separate objects:

~~~yaml
security:
  - bearerAuth: []
  - partnerApiKey: []
~~~

The client can choose one of the two methods:

~~~http
GET /api/orders
Authorization: Bearer eyJhbGciOi...
~~~

Or:

~~~http
GET /api/orders
X-Partner-Key: partner-key-value
~~~

The two objects are two separate elements of the security array, so they represent alternatives. Clients do not need to supply both simply because both schemes appear in the documentation.

## 4. Direct comparison of AND and OR

| YAML | Logic | Condition for a request to be accepted under the contract |
| --- | --- | --- |
| One object containing bearerAuth and partnerApiKey | AND | Must include both bearer token and partner key |
| Two separate objects, one with bearerAuth and one with partnerApiKey | OR | Either bearer token or partner key |
| One object containing oauth2 with scope orders:read | Single scheme with scope | OAuth token must have the orders:read scope |
| One empty object {} | Anonymous | Allows unauthenticated requests |

Pay close attention to YAML indentation. Simply turning partnerApiKey into a new array item changes the logic from AND to OR.

## 5. Declaring security schemes with annotations

Springdoc reads swagger-core annotations to generate security schemes. Multiple SecurityScheme annotations can be placed on a configuration class:

~~~java
import io.swagger.v3.oas.annotations.enums.SecuritySchemeIn;
import io.swagger.v3.oas.annotations.enums.SecuritySchemeType;
import io.swagger.v3.oas.annotations.security.SecurityScheme;
import io.swagger.v3.oas.annotations.security.SecuritySchemes;
import org.springframework.context.annotation.Configuration;

@Configuration
@SecuritySchemes({
    @SecurityScheme(
        name = "bearerAuth",
        type = SecuritySchemeType.HTTP,
        scheme = "bearer",
        bearerFormat = "JWT",
        description = "JWT access token."
    ),
    @SecurityScheme(
        name = "partnerApiKey",
        type = SecuritySchemeType.APIKEY,
        in = SecuritySchemeIn.HEADER,
        paramName = "X-Partner-Key",
        description = "API key issued to partners."
    )
})
class ApiSecuritySchemes {
}
~~~

The name values are reference names in Security Requirements. Names must match the keys in components.securitySchemes exactly. paramName is the header/query parameter name carrying the API key; it is not the scheme name.

Do not declare an API key as HTTP bearer merely because both are sent in headers. Schemes must accurately reflect how the server reads credentials.

## 6. Describing OR with repeated @SecurityRequirement annotations

The SecurityRequirement annotation can be repeated on a method or class. Multiple separate annotations represent multiple alternative requirements, i.e., OR:

~~~java
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.security.SecurityRequirement;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class OrderController {

    @Operation(
        summary = "Get list of orders",
        security = {
            @SecurityRequirement(name = "bearerAuth"),
            @SecurityRequirement(name = "partnerApiKey")
        }
    )
    @GetMapping("/api/orders")
    List<OrderResponse> listOrders() {
        return orderService.findAll();
    }
}
~~~

Corresponding generated document:

~~~yaml
paths:
  /api/orders:
    get:
      security:
        - bearerAuth: []
        - partnerApiKey: []
~~~

These are two alternatives. Do not use two repeated annotations expecting them to mean both credentials are simultaneously required.

## 7. Describing AND with the combine annotation in newer swagger-core versions

Newer versions of swagger-annotations provide a combine attribute on SecurityRequirement. This attribute lets you group multiple schemes into a single requirement object:

~~~java
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.security.SecurityRequirement;
import io.swagger.v3.oas.annotations.security.SecurityRequirementEntry;

@Operation(
    summary = "Create a partner order",
    security = {
        @SecurityRequirement(
            combine = {
                @SecurityRequirementEntry(name = "bearerAuth"),
                @SecurityRequirementEntry(name = "partnerApiKey")
            }
        )
    }
)
~~~

Expected result:

~~~yaml
security:
  - bearerAuth: []
    partnerApiKey: []
~~~

combine appears in the Javadoc for swagger-annotations 2.2.53. Not every version of swagger-annotations bundled with springdoc includes this attribute. If your IDE does not recognize combine or SecurityRequirementEntry, check the actual dependency version; do not upgrade swagger-annotations independently in an ad-hoc way if doing so causes a version mismatch with the swagger-core used by springdoc.

With older versions lacking combine, use the OpenAPI model in a customizer to build a single requirement object containing multiple schemes.

## 8. Expressing AND with OpenApiCustomizer

You can build a requirement object directly using io.swagger.v3.oas.models.security.SecurityRequirement. Call addList multiple times on the same object to add schemes to a single requirement:

~~~java
import io.swagger.v3.oas.models.security.SecurityRequirement;
import org.springdoc.core.customizers.OpenApiCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import java.util.List;

@Configuration
class PartnerSecurityConfig {

    @Bean
    OpenApiCustomizer partnerAndSecurity() {
        return openApi -> {
            SecurityRequirement requirement = new SecurityRequirement()
                .addList("bearerAuth")
                .addList("partnerApiKey");

            openApi.setSecurity(List.of(requirement));
        };
    }
}
~~~

This snippet sets the requirement at the level of the document processed by the customizer. If the customizer is attached to a GroupedOpenApi, the requirement applies to that group's document. If used as a standalone default customizer, verify which document your springdoc version applies it to.

To apply only to a single operation, modify that operation's security:

~~~java
@Bean
OpenApiCustomizer partnerOrdersSecurity() {
    return openApi -> {
        if (openApi.getPaths() == null) {
            return;
        }

        var pathItem = openApi.getPaths().get("/api/partner/orders");
        if (pathItem == null || pathItem.getPost() == null) {
            return;
        }

        SecurityRequirement requirement = new SecurityRequirement()
            .addList("bearerAuth")
            .addList("partnerApiKey");

        pathItem.getPost().setSecurity(List.of(requirement));
    };
}
~~~

When using customizers, ensure both schemes are already declared in components.securitySchemes. A Security Requirement only references schemes; it does not define missing schemes.

## 9. Expressing OR with OpenApiCustomizer

To create two alternatives in Java, create two separate objects in the list:

~~~java
@Bean
OpenApiCustomizer partnerOrSecurity() {
    return openApi -> openApi.setSecurity(List.of(
        new SecurityRequirement().addList("bearerAuth"),
        new SecurityRequirement().addList("partnerApiKey")
    ));
}
~~~

Result:

~~~yaml
security:
  - bearerAuth: []
  - partnerApiKey: []
~~~

Do not merge two addList calls onto the same object if the goal is OR. Nor should you create two separate objects if the API mandates both credentials.

## 10. Combining OAuth2 scopes with multiple schemes

OAuth2/OpenID Connect can require one or more scopes. Scopes are specific permissions inside a single scheme, distinct from combining multiple schemes.

Example OAuth2 definition:

~~~yaml
components:
  securitySchemes:
    oauth2:
      type: oauth2
      flows:
        clientCredentials:
          tokenUrl: https://auth.example.com/oauth/token
          scopes:
            orders:read: Read orders
            orders:write: Create or update orders
~~~

A requirement requiring scopes:

~~~yaml
security:
  - oauth2:
      - orders:read
      - orders:write
~~~

This is still one oauth2 scheme. The scope list describes required OAuth permissions, not two alternative authentication methods.

If the API requires an OAuth2 token and an API key at the same time:

~~~yaml
security:
  - oauth2:
      - orders:write
    partnerApiKey: []
~~~

Both OAuth2 with scope orders:write and the partner API key must be satisfied. If you want OAuth2 or the API key as two alternatives, place them in two separate objects.

With annotations, SecurityRequirement(name = "oauth2", scopes = {"orders:read"}) describes scopes of an OAuth2 scheme. For requirements combining multiple schemes, use combine in supported versions or an OpenAPI model customizer.

## 11. Global security and operation-level overrides

You can place security at the document level as a default for all operations:

~~~yaml
security:
  - bearerAuth: []
~~~

Operations inherit this requirement unless they declare their own security. An operation can override the default policy.

Example of a public health endpoint:

~~~yaml
paths:
  /actuator/health:
    get:
      security: []
      responses:
        '200':
          description: Application status
~~~

security: [] on an operation removes the inherited document-level security requirement. It means the operation requires no scheme under the OpenAPI contract.

Another case is an endpoint allowing anonymous access or a bearer token:

~~~yaml
paths:
  /api/catalog:
    get:
      security:
        - {}
        - bearerAuth: []
~~~

The empty object {} is a requirement for anonymous access. When placed alongside the bearerAuth object in the array, clients can call anonymously or send a bearer token.

Distinction:

| Declaration on operation | Meaning |
| --- | --- |
| No security field | Inherits document-level security |
| security: [] | Removes inherited security requirement; operation requires no authentication per OpenAPI |
| security: [{}] | Allows anonymous access |
| security: [{}, {bearerAuth: []}] | Allows anonymous access or bearer token |
| security: [{bearerAuth: []}] | Requires bearer token |

Do not add {} to security if the endpoint actually mandates authentication. An anonymous requirement can make the documentation claim unauthenticated requests are permitted.

## 12. Using @OpenAPIDefinition for default security

You can declare global security requirements using @OpenAPIDefinition:

~~~java
import io.swagger.v3.oas.annotations.OpenAPIDefinition;
import io.swagger.v3.oas.annotations.security.SecurityRequirement;
import org.springframework.context.annotation.Configuration;

@Configuration
@OpenAPIDefinition(
    security = {
        @SecurityRequirement(name = "bearerAuth")
    }
)
class OpenApiDefinition {
}
~~~

This snippet sets bearerAuth as the default requirement at the document level. Operations needing different security or public access can define their own security via @Operation or customizers.

When declaring multiple SecurityRequirement annotations at the OpenAPI definition level, they are alternative requirements (OR). If multiple schemes are required together globally, use combine if your swagger-annotations version supports it, or a customizer creating a single SecurityRequirement model with multiple keys.

## 13. Comprehensive example for a partner API

Suppose a partner API supports two calling methods:

- Partner internal services use a bearer token.
- A legacy system uses an API key.

If the server accepts either option, the documentation should express OR:

~~~java
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.enums.SecuritySchemeIn;
import io.swagger.v3.oas.annotations.enums.SecuritySchemeType;
import io.swagger.v3.oas.annotations.security.SecurityRequirement;
import io.swagger.v3.oas.annotations.security.SecurityScheme;
import io.swagger.v3.oas.annotations.security.SecuritySchemes;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SecuritySchemes({
    @SecurityScheme(
        name = "bearerAuth",
        type = SecuritySchemeType.HTTP,
        scheme = "bearer",
        bearerFormat = "JWT"
    ),
    @SecurityScheme(
        name = "partnerApiKey",
        type = SecuritySchemeType.APIKEY,
        in = SecuritySchemeIn.HEADER,
        paramName = "X-Partner-Key"
    )
})
class PartnerSecuritySchemes {
}

@RestController
class PartnerOrderController {

    private final OrderService orderService;

    PartnerOrderController(OrderService orderService) {
        this.orderService = orderService;
    }

    @Operation(
        summary = "Look up partner orders",
        security = {
            @SecurityRequirement(name = "bearerAuth"),
            @SecurityRequirement(name = "partnerApiKey")
        }
    )
    @GetMapping("/api/partner/orders")
    List<OrderResponse> listPartnerOrders() {
        return orderService.findPartnerOrders();
    }
}
~~~

If the security requirement changes so that both a bearer token and an API key are mandatory, change security into a combined requirement or configure a customizer as shown earlier. You do not need to change the definitions of the two schemes; only change how the operation references them.

## 14. Checking security in the generated document

After configuring, call the OpenAPI JSON:

~~~bash
curl -sS http://localhost:8080/v3/api-docs
~~~

Verify schemes:

~~~yaml
components:
  securitySchemes:
    bearerAuth:
      type: http
      scheme: bearer
    partnerApiKey:
      type: apiKey
      in: header
      name: X-Partner-Key
~~~

Verify AND logic:

~~~yaml
security:
  - bearerAuth: []
    partnerApiKey: []
~~~

Verify OR logic:

~~~yaml
security:
  - bearerAuth: []
  - partnerApiKey: []
~~~

Checklist:

1. Does every name in security have a matching scheme in components.securitySchemes?
2. Are multiple required schemes inside the same object?
3. Are alternative options placed as separate objects?
4. Do OAuth2 scopes have the right names and operations?
5. Do operations override global security as intended?
6. Do public endpoints have security: [] or requirement {} as intended?
7. Does Swagger UI display authentication options matching the document structure?

You can verify with JSON tests:

~~~java
mockMvc.perform(get("/v3/api-docs"))
    .andExpect(status().isOk())
    .andExpect(jsonPath(
        "$.paths['/api/partner/orders'].post.security[0].bearerAuth"
    ).exists())
    .andExpect(jsonPath(
        "$.paths['/api/partner/orders'].post.security[0].partnerApiKey"
    ).exists());
~~~

To test OR, verify two distinct elements in the security array, each containing one scheme. Do not merely check that both names appear somewhere in the JSON.

## 15. OpenAPI documentation does not replace runtime authentication

Security Schemes and Security Requirements only describe the contract for clients, Swagger UI, and code generation tools. They do not configure Spring Security, generate tokens, or inspect headers when requests arrive at the server.

For instance, documentation may describe AND between bearerAuth and partnerApiKey, yet if the filter chain only checks JWTs and ignores X-Partner-Key, runtime does not enforce that contract completely. Conversely, if the server requires both while OpenAPI only describes bearerAuth, clients will lack needed information.

Test both layers separately:

| Layer | What to verify |
| --- | --- |
| OpenAPI contract | Security structure, schemes, scopes, and operation overrides |
| Runtime authorization | Missing each credential, wrong credential, expired token, invalid API key, and valid case |

For an AND requirement, runtime tests should cover at least four cases: missing both, bearer only, API key only, and having both. For OR, test each valid option individually plus a request with neither option.

## 16. Common errors

| Symptom | Cause | Resolution |
| --- | --- | --- |
| API requires both token and key yet Swagger UI asks for only one | Two schemes were declared as two separate Security Requirement Objects | Place both schemes in the same object |
| API accepts token or key yet Swagger UI asks for both | Two schemes were combined inside the same object | Create two separate objects in the security array |
| Security requirement is not recognized | Scheme name in security does not match component | Use the exact same name in both places |
| AND annotation fails to compile | Current swagger-annotations lacks the combine attribute | Use OpenApiCustomizer or a version with compatible support |
| Public endpoint still shows mandatory auth lock | Operation has not overridden global security | Use security: [] or appropriate anonymous requirement |
| Swagger UI displays scheme yet server does not validate | Only OpenAPI was declared without configuring filters/authorization | Configure and test Spring Security |
| OAuth2 token rejected despite being signed in | Missing scope required by the requirement | Issue the right scope and document it accurately in OpenAPI |
| API key sent in wrong header | Scheme declared wrong in or name | Align SecurityScheme with how the server reads credentials |

## 17. Security requirement design workflow

When an operation supports multiple authentication mechanisms:

1. Define each Security Scheme in components.securitySchemes.
2. Determine whether the API needs all schemes simultaneously or just one alternative.
3. Use a single Security Requirement Object containing multiple schemes for AND.
4. Use multiple separate Security Requirement Objects in the security array for OR.
5. Place security at the document level if it is a true default; override on operations when needed.
6. Use {} when allowing anonymous access and [] when an operation inherits no security.
7. If using annotations, check your swagger-annotations version capabilities; use a customizer when AND is needed and current annotations do not support it.
8. Inspect OpenAPI JSON/YAML and Swagger UI.
9. Test Spring Security/runtime independently from documentation.

When AND/OR relationships are properly understood, OpenAPI documentation accurately describes which credentials clients must send and which authentication options exist. This serves as the foundation for Swagger UI, client generators, and integrators to use the API properly.

## References

- [OpenAPI Specification – Security Requirement Object](https://spec.openapis.org/oas/v3.1.2.html#security-requirement-object)
- [OpenAPI Specification – Security Scheme Object](https://spec.openapis.org/oas/v3.1.2.html#security-scheme-object)
- [Swagger Core – @SecurityRequirement 2.2.53](https://docs.swagger.io/swagger-core/v2.2.53/apidocs/io/swagger/v3/oas/annotations/security/SecurityRequirement.html)
- [Swagger Core – @SecurityRequirementEntry 2.2.53](https://docs.swagger.io/swagger-core/v2.2.53/apidocs/io/swagger/v3/oas/annotations/security/SecurityRequirementEntry.html)
- [springdoc-openapi – Documentation](https://springdoc.org/)
