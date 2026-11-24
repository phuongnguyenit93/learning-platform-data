# @SecurityScheme to Register Authentication Mechanisms

OpenAPI describes how clients authenticate when calling an API through security schemes. With springdoc-openapi, the <code>@SecurityScheme</code> annotation registers a reusable authentication mechanism in <code>components.securitySchemes</code>. Then, <code>@SecurityRequirement</code> references that scheme at the API or operation level to indicate which endpoints require authentication.

Registering a scheme helps Swagger UI understand which credential type to display, such as a Bearer token, API key, Basic authentication, or OAuth2. The annotation only describes the contract for tools and clients. The application must still configure Spring Security, authentication filters, or the corresponding runtime credential-checking mechanism.

## 1. Security scheme and security requirement are different

These two concepts are often confused:

| Component | Role | Where it is placed in OpenAPI |
|---|---|---|
| <code>@SecurityScheme</code> | Defines a reusable authentication mechanism | <code>components.securitySchemes</code> |
| <code>@SecurityRequirement</code> | Attaches a defined mechanism to an API or operation | <code>security</code> at the root or operation level |

For example, a scheme named <code>bearerAuth</code> describes an HTTP Bearer token. Simply registering this scheme does not mean all endpoints require a token. To apply it, you must add a security requirement referencing the exact name <code>bearerAuth</code>.

The name in the requirement must match the registered name. If the scheme is named <code>bearerAuth</code> but the requirement references <code>bearerToken</code>, OpenAPI will have no matching component.

## 2. Registering an HTTP Bearer token

For an API using an access token in the <code>Authorization</code> header, declare the scheme as follows:

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
    description = "Access token sent in the Authorization header"
)
class OpenApiSecurityConfiguration {
}
~~~

Key attributes:

- <code>name</code>: component name for requirements to reference.
- <code>type = HTTP</code>: uses the HTTP authentication mechanism.
- <code>scheme = "bearer"</code>: uses HTTP Bearer authentication.
- <code>bearerFormat = "JWT"</code>: hints at the token format for readers and tools.
- <code>description</code>: explains how clients obtain and send the token.

When the scheme is displayed in Swagger UI, users typically see the **Authorize** button and can enter a token. The UI will add a header in the format:

~~~http
Authorization: Bearer eyJ...example-token
~~~

<code>bearerFormat = "JWT"</code> is only descriptive metadata. It does not verify the JWT signature, issuer, audience, expiration, or scopes. Those tasks are the responsibility of the resource server and runtime security configuration.

### 2.1. Attaching the Bearer scheme to an operation

To describe an endpoint requiring a Bearer token, use <code>@SecurityRequirement</code>:

~~~java
import io.swagger.v3.oas.annotations.security.SecurityRequirement;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/profile")
class ProfileController {

    @GetMapping
    @SecurityRequirement(name = "bearerAuth")
    ProfileResponse getProfile() {
        return new ProfileResponse("user-100", "An");
    }
}

record ProfileResponse(String userId, String displayName) {}
~~~

<code>@SecurityRequirement</code> references the declared scheme. Swagger UI knows this operation needs a Bearer token and can send the token entered in Authorize when executing requests.

## 3. Registering multiple schemes with @SecuritySchemes

An API can support multiple authentication methods, such as Bearer tokens for users and API keys for integration partners. Use <code>@SecuritySchemes</code> to declare multiple schemes on the same configuration:

This is an alternative configuration to the class that only registered Bearer in the previous section. In an application, keep a single consolidated configuration with unique scheme names; do not declare two classes with the same name <code>OpenApiSecurityConfiguration</code>.

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
        description = "User access token"
    ),
    @SecurityScheme(
        name = "partnerApiKey",
        type = SecuritySchemeType.APIKEY,
        in = SecuritySchemeIn.HEADER,
        paramName = "X-API-Key",
        description = "API key issued to partner systems"
    )
})
class OpenApiSecurityConfiguration {
}
~~~

Each scheme has its own name. <code>partnerApiKey</code> describes an API key in the <code>X-API-Key</code> header; <code>bearerAuth</code> describes a token in the Authorization header.

Different schemes can be attached to different endpoint groups:

~~~java
import io.swagger.v3.oas.annotations.security.SecurityRequirement;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/partner")
@SecurityRequirement(name = "partnerApiKey")
class PartnerController {
    // Operations for partners
}
~~~

~~~java
import io.swagger.v3.oas.annotations.security.SecurityRequirement;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/account")
@SecurityRequirement(name = "bearerAuth")
class AccountController {
    // Operations for signed-in users
}
~~~

Placing the requirement at the controller level applies it to operations belonging to that controller. You can place it at the method level if only one operation needs a specific authentication mechanism. Inspect the generated document to confirm the scope matches expectations.

## 4. Commonly used SecurityScheme types

OpenAPI supports several scheme types. <code>type</code> determines which attributes need to be declared:

| Type | Annotation | Common attributes | Use case |
|---|---|---|---|
| HTTP Basic | <code>type = HTTP</code>, <code>scheme = "basic"</code> | <code>scheme</code> | Username/password via HTTP Basic |
| HTTP Bearer | <code>type = HTTP</code>, <code>scheme = "bearer"</code> | <code>scheme</code>, <code>bearerFormat</code> | Access token in the Authorization header |
| API key | <code>type = APIKEY</code> | <code>in</code>, <code>paramName</code> | Integration key in header, query, or cookie |
| OAuth2 | <code>type = OAUTH2</code> | <code>flows</code> | Access token issued via an OAuth2 flow |
| OpenID Connect | <code>type = OPENIDCONNECT</code> | <code>openIdConnectUrl</code> | Discover OpenID Provider configuration |

Do not use <code>scheme = "bearer"</code> for an API key. For an API key, specify where the key is passed using <code>in</code> and the parameter name using <code>paramName</code>.

### 4.1. HTTP Basic

Declaring Basic authentication:

~~~java
import io.swagger.v3.oas.annotations.enums.SecuritySchemeType;
import io.swagger.v3.oas.annotations.security.SecurityScheme;

@SecurityScheme(
    name = "basicAuth",
    type = SecuritySchemeType.HTTP,
    scheme = "basic",
    description = "HTTP Basic authentication for internal environments"
)
class BasicSecurityDocumentation {
}
~~~

The client sends credentials in the <code>Authorization</code> header using the Basic mechanism. Because credentials can be decoded from Base64, only use it over HTTPS and in accordance with the system's security policy.

### 4.2. API key in a header

Example of an API key passed in a header:

~~~java
import io.swagger.v3.oas.annotations.enums.SecuritySchemeIn;
import io.swagger.v3.oas.annotations.enums.SecuritySchemeType;
import io.swagger.v3.oas.annotations.security.SecurityScheme;

@SecurityScheme(
    name = "partnerKey",
    type = SecuritySchemeType.APIKEY,
    in = SecuritySchemeIn.HEADER,
    paramName = "X-Partner-Key",
    description = "Partner application identification key"
)
class PartnerKeyDocumentation {
}
~~~

Swagger UI can generate the <code>X-Partner-Key</code> header when calling operations that require this scheme.

An API key can also be placed in a query parameter or cookie using <code>SecuritySchemeIn.QUERY</code> or <code>SecuritySchemeIn.COOKIE</code>. However, keys in query strings easily appear in access logs, browser history, proxy logs, and shared URLs. For new APIs, prefer headers over HTTPS unless the contract has a specific reason to use another location.

Once an API key is described with a security scheme, do not also declare the same header as a regular parameter using <code>@RequestHeader</code>/<code>@Parameter</code> without a specific reason; doing so can cause the documentation to display the authentication header twice.

Do not put real API keys in annotations, examples, source code, or the OpenAPI document. The scheme name and header name are metadata; key values must be issued and managed outside the documentation.

## 5. Declaring OAuth2 and scopes

An OAuth2 scheme needs to describe the flows that clients are permitted to use. Example of a web application using the Authorization Code flow:

~~~java
import io.swagger.v3.oas.annotations.enums.SecuritySchemeType;
import io.swagger.v3.oas.annotations.security.OAuthFlow;
import io.swagger.v3.oas.annotations.security.OAuthFlows;
import io.swagger.v3.oas.annotations.security.OAuthScope;
import io.swagger.v3.oas.annotations.security.SecurityScheme;

@SecurityScheme(
    name = "ordersOAuth",
    type = SecuritySchemeType.OAUTH2,
    flows = @OAuthFlows(
        authorizationCode = @OAuthFlow(
            authorizationUrl = "https://auth.example.com/oauth2/authorize",
            tokenUrl = "https://auth.example.com/oauth2/token",
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
    ),
    description = "OAuth2 Authorization Code flow"
)
class OAuthDocumentation {
}
~~~

In the configuration:

- <code>authorizationUrl</code> is the endpoint that directs users to the authorization server.
- <code>tokenUrl</code> is the endpoint that exchanges an authorization code for a token.
- <code>scopes</code> lists the permissions that clients can request.

Names and URLs must match the actual configuration of the Authorization Server. The <code>example.com</code> URLs in the snippet are illustrative only and must be replaced with your system's endpoints.

Attaching an OAuth2 requirement with the needed scope:

~~~java
import java.util.List;

import io.swagger.v3.oas.annotations.security.SecurityRequirement;
import org.springframework.web.bind.annotation.GetMapping;

@GetMapping("/api/orders")
@SecurityRequirement(
    name = "ordersOAuth",
    scopes = {"orders:read"}
)
List<OrderResponse> listOrders() {
    // ...
    return List.of();
}
~~~

For write operations, you can require <code>orders:write</code>. Scopes in OpenAPI describe required permissions; the server must still verify the claims/scopes in the access token before processing the request.

Do not declare an OAuth2 flow just to get an Authorize button. Choose the flow based on the client type, Identity Provider capabilities, and current security guidelines. For browser or public mobile applications, Authorization Code combined with PKCE is usually the appropriate choice; do not embed client secrets in public client code.

## 6. Declaring OpenID Connect

If the system uses OpenID Connect Discovery, you can register the discovery URL:

~~~java
import io.swagger.v3.oas.annotations.enums.SecuritySchemeType;
import io.swagger.v3.oas.annotations.security.SecurityScheme;

@SecurityScheme(
    name = "openId",
    type = SecuritySchemeType.OPENIDCONNECT,
    openIdConnectUrl =
        "https://identity.example.com/.well-known/openid-configuration",
    description = "OpenID Connect provider"
)
class OpenIdDocumentation {
}
~~~

<code>openIdConnectUrl</code> points to the OpenID Provider's discovery document. Clients can use the metadata there to locate endpoints and supported capabilities. The URL must be reachable from the environment used by clients.

OpenID Connect is an identity layer built on OAuth2. Do not confuse OpenID Connect with an arbitrary HTTP scheme or treat the discovery URL as a business request endpoint.

## 7. Applying security globally and per operation

You can declare a security requirement at the API-wide level using <code>@OpenAPIDefinition</code>:

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
class OpenApiDefinitionConfiguration {
}
~~~

When declared at the root level, operations inherit the global security requirement unless an operation has its own security configuration. If a public endpoint does not require authentication, that operation's specification needs <code>security: []</code> to override the root requirement. Check the OpenAPI output to confirm that public operations genuinely do not inherit security requirements.

You can place requirements at the controller or method level to limit scope:

~~~java
import io.swagger.v3.oas.annotations.security.SecurityRequirement;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/admin")
@SecurityRequirement(name = "bearerAuth")
class AdminController {

    @GetMapping("/reports")
    List<String> reports() {
        return List.of();
    }
}
~~~

If the same controller has both public and protected endpoints, consider placing requirements on methods to avoid accidentally describing the wrong scope. Security configuration in OpenAPI must reflect the actual policy of each operation.

## 8. Understanding AND and OR semantics for multiple security requirements

OpenAPI allows multiple authentication options:

~~~yaml
security:
  - bearerAuth: []
  - partnerApiKey: []
~~~

Two objects in the array are **OR** alternatives: the client can authenticate with either a Bearer token or an API key.

If a request must provide two schemes simultaneously, they must be inside the same Security Requirement Object:

~~~yaml
security:
  - bearerAuth: []
    partnerApiKey: []
~~~

Schemes in the same object mean **AND**: the request requires both a Bearer token and an API key. Do not confuse two separate objects in the array with two schemes inside a single object.

When repeating multiple <code>@SecurityRequirement</code> annotations, each requirement typically becomes a separate option in the <code>security</code> array, i.e., OR logic. If AND is needed, inspect the output and use an <code>OpenApiCustomizer</code> to create a single Security Requirement Object containing both schemes together.

## 9. Combining with Spring Security

Registering <code>@SecurityScheme</code> does not configure Spring Security. For example, declaring a Bearer scheme does not create a JWT decoder, verify signatures, or protect endpoints.

At runtime, the application needs to configure the corresponding resource server or filters. With Spring Security OAuth2 Resource Server, a basic configuration might look like this:

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
                .requestMatchers("/public/**").permitAll()
                .anyRequest().authenticated()
            )
            .oauth2ResourceServer(oauth2 ->
                oauth2.jwt(Customizer.withDefaults())
            )
            .build();
    }
}
~~~

This configuration illustrates requiring authentication for endpoints outside <code>/public/**</code> and using a JWT resource server. The project needs the Resource Server dependency, appropriate issuer or public key configuration, and authorization policies as required. If the API uses an API key, Basic auth, or a custom mechanism, corresponding filters/providers are needed; OpenAPI annotations do not replace them.

When sharing documentation, cross-check three parts:

1. Security schemes in OpenAPI describe how clients must send credentials.
2. Security requirements indicate which operations need which credentials.
3. Spring Security enforces authentication and authorization on real requests.

## 10. Inspecting the generated OpenAPI document

After starting the application, open:

~~~text
http://localhost:8080/v3/api-docs
~~~

Check the following items:

1. <code>components.securitySchemes</code> contains the scheme with the right name.
2. <code>type</code>, <code>scheme</code>, <code>in</code>, <code>name</code>, OAuth2 flows, or OpenID URL match the mechanism in use.
3. <code>security</code> at the root or operation level references the right component name.
4. Public operations have empty security if they need to override global security.
5. OAuth2 scopes in requirements exist in the declared scope list.
6. All <code>GroupedOpenApi</code> documentation groups contain the required schemes and requirements in their respective documents.

An expected JSON/YAML snippet with Bearer:

~~~yaml
components:
  securitySchemes:
    bearerAuth:
      type: http
      scheme: bearer
      bearerFormat: JWT

paths:
  /api/profile:
    get:
      security:
        - bearerAuth: []
      responses:
        "200":
          description: OK
~~~

Then open Swagger UI, check the Authorize button, enter a test token, and call a protected endpoint. Verify both valid token and missing/invalid token cases. If the UI sends the right header but the server still returns <code>401</code>, check the resource server configuration, issuer, signature, and token expiration. If it returns <code>403</code>, check permissions or scopes.

## 11. Common errors

**Declaring only <code>@SecurityScheme</code> and expecting endpoints to be protected.** A scheme only defines a component. You must add <code>@SecurityRequirement</code> or configure security at the root.

**Mismatched scheme names.** The requirement must reference the exact <code>name</code> in <code>@SecurityScheme</code>. Check casing as well as the generated component name.

**Using the wrong type.** Bearer/Basic use <code>type = HTTP</code>; API key uses <code>type = APIKEY</code>; OAuth2 uses <code>type = OAUTH2</code>; OpenID Connect uses <code>type = OPENIDCONNECT</code>.

**Declaring an API key without location or parameter name.** An API key requires <code>in</code> and <code>paramName</code>; if omitted, the documentation does not fully describe where clients send the key.

**Treating bearerFormat as an authentication mechanism.** <code>bearerFormat</code> is only a hint for readers and tools; it does not validate JWTs.

**Declaring wrong OAuth2 flows or scopes.** Authorization/token URLs and scopes must match the Identity Provider and server policy.

**Protecting the UI while forgetting the JSON document.** If <code>/swagger-ui/**</code> is protected but <code>/v3/api-docs</code> remains public, users can still download the specification directly.

**Confusing OR with AND.** Multiple Security Requirement Objects in an array represent alternatives. To require multiple schemes simultaneously, place them in the same object.

**Inconsistency between OpenAPI and Spring Security.** Swagger UI might send tokens according to the documentation while the backend still allows or rejects requests differently than expected. Check both the specification and the actual filter chain.

## 12. Pre-publication checklist

- [ ] Each scheme has a unique name, clear description, and correct <code>type</code>.
- [ ] HTTP schemes have an appropriate <code>scheme</code>; API keys have <code>in</code> and <code>paramName</code>.
- [ ] OAuth2 flows, URLs, and scopes match the Identity Provider.
- [ ] OpenID Connect uses a valid discovery URL.
- [ ] <code>@SecurityRequirement</code> references the exact scheme name.
- [ ] Global, controller, and method scopes accurately reflect the API's policy.
- [ ] AND/OR logic has been verified when multiple schemes are present.
- [ ] Public endpoints are documented as requiring no security if needed.
- [ ] Spring Security actually enforces authentication and authorization at runtime.
- [ ] Swagger UI sends the right credentials and <code>/v3/api-docs</code> is not unexpectedly exposed.

## References

- [OpenAPI Specification – Security Scheme Object](https://spec.openapis.org/oas/latest.html#security-scheme-object): HTTP, API key, OAuth2, and OpenID Connect types.
- [OpenAPI Specification – Security Requirement Object](https://spec.openapis.org/oas/latest.html#security-requirement-object): how to apply one or more authentication mechanisms and AND/OR semantics.
- [Swagger Core – SecurityScheme annotation](https://docs.swagger.io/swagger-core/v2.2.0/apidocs/io/swagger/v3/oas/annotations/security/SecurityScheme.html): attributes of <code>@SecurityScheme</code>.
- [Swagger Core – SecurityRequirement annotation](https://docs.swagger.io/swagger-core/v2.2.0/apidocs/io/swagger/v3/oas/annotations/security/SecurityRequirement.html): referencing security schemes in annotations.
- [Spring Security – OAuth2 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): validating Bearer JWTs at runtime.
- [springdoc-openapi](https://springdoc.org/): integrating OpenAPI annotations with Spring Boot applications.
