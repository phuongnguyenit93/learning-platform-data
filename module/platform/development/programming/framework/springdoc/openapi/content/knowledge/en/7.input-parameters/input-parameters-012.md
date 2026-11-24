# Hiding Infrastructure Parameters Such as Principal or Request Info

A Spring Boot controller can accept framework-provided objects for request handling, such as the authenticated user, authentication details, servlet request, or response. These objects serve endpoint execution, not necessarily data that clients must supply. If they appear as input parameters in OpenAPI, Swagger UI may display fields meaningless to API callers, and clients generated from the specification may misunderstand the contract.

With **springdoc-openapi**, you can hide a parameter from documentation using **@Parameter(hidden = true)**. Springdoc also automatically excludes certain special Spring MVC parameter types, such as **Principal**, **Locale**, **HttpServletRequest**, and **HttpServletResponse**. However, custom parameters or principals injected via Spring Security may require explicit hiding.

It is essential to distinguish internal framework-injected data from parameters that actually belong to the HTTP contract. A header sent by a client still needs to be documented even if the controller reads it through **HttpServletRequest**.

## 1. Identifying Infrastructure Parameters

Infrastructure parameters are data or objects provided by Spring, the servlet container, Spring Security, or an argument resolver during request processing. They are typically not fields clients enter in Swagger UI.

| Parameter Type | Provider | Role in Controller |
| --- | --- | --- |
| **Principal** | Servlet container or authentication mechanism | Caller's identity |
| **Authentication** | Spring Security | Principal, authorities, and authentication state |
| **@AuthenticationPrincipal** | Spring Security | Retrieves current principal or a custom principal type |
| **HttpServletRequest** | Servlet container | Reads headers, URI, session, request attributes, and HTTP metadata |
| **HttpServletResponse** | Servlet container | Writes headers, cookies, or controls response |
| **Locale** | Spring locale resolution or request | Determines language or formatting locale |
| **HttpSession** | Servlet container | Accesses user session |
| Custom context type | HandlerMethodArgumentResolver or integration layer | Supplies tenant, current user, or request context |

By default, springdoc excludes several special parameters that Spring MVC supports injecting from documentation. The list documented in the FAQ includes **Principal**, **Locale**, **HttpServletRequest**, **HttpServletResponse**, and other injectable types. When adding Spring Security or custom argument resolvers, do not assume every custom type is automatically excluded from OpenAPI.

Ask two questions before hiding a parameter:

1. Must the client send this value in the request?
2. Is the value part of the API contract that clients need to know about?

If the answer to both is no, the parameter is usually an infrastructure detail and can be hidden from documentation. If the client must pass the value, it must be documented even when the controller reads it from a generic request object.

## 2. Using @Parameter(hidden = true) on a Parameter

The **@Parameter** annotation belongs to the **io.swagger.v3.oas.annotations** package. Place **hidden = true** on the exact parameter to exclude from OpenAPI:

~~~java
import io.swagger.v3.oas.annotations.Parameter;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class ProfileController {

    @GetMapping("/api/profile")
    ProfileView currentProfile(
        @Parameter(hidden = true)
        @AuthenticationPrincipal AppPrincipal principal
    ) {
        return profileService.findByUserId(principal.userId());
    }
}
~~~

In this example, **AppPrincipal** is an application-defined principal type. Spring Security retrieves the principal from **SecurityContext** and injects it into the parameter via **@AuthenticationPrincipal**. Clients do not send a field named principal in the request body or query string; identity is determined by the authentication mechanism. Thus, the parameter is marked hidden.

You can also explicitly hide the request object to make intent clear in source code:

~~~java
import jakarta.servlet.http.HttpServletRequest;

@GetMapping("/api/profile/details")
ProfileDetailsView details(
    @Parameter(hidden = true)
    @AuthenticationPrincipal AppPrincipal principal,

    @Parameter(hidden = true)
    HttpServletRequest request
) {
    String traceId = request.getHeader("X-Trace-Id");
    return profileService.loadDetails(principal.userId(), traceId);
}
~~~

Springdoc already skips common servlet types automatically. An explicit annotation helps controller readers recognize internal-only parameters and helps with custom types or version/configuration edge cases where parameters appear unexpectedly.

**@Parameter(hidden = true)** only changes OpenAPI documentation. It does not remove the parameter from the method signature, change how Spring injects values, or bypass authentication or authorization logic.

## 3. Principal, Authentication, and @AuthenticationPrincipal

Three common ways to retrieve caller identity carry different semantics:

- **Principal** is an abstraction of the authenticated identity. It can be injected directly by Spring MVC.
- **Authentication** is a Spring Security object holding the principal, authorities, and authentication status.
- **@AuthenticationPrincipal** extracts the current principal or a value selected from the principal per annotation configuration.

Example controller accepting **Authentication**:

~~~java
import org.springframework.security.core.Authentication;

@GetMapping("/api/account")
AccountView account(
    @Parameter(hidden = true) Authentication authentication
) {
    AppPrincipal principal = (AppPrincipal) authentication.getPrincipal();
    return accountService.findByUserId(principal.userId());
}
~~~

Example accepting **Principal**:

~~~java
import java.security.Principal;

@GetMapping("/api/account/summary")
AccountSummary summary(
    @Parameter(hidden = true) Principal principal
) {
    return accountService.summaryFor(principal.getName());
}
~~~

These parameters represent server-established authentication context. Clients interact with authentication via session cookies, bearer tokens, or another security mechanism published in the contract.

Do not expose principals, Authentication objects, or internal SecurityContext values as query parameters or request bodies just to make Swagger UI display them. Doing so turns implementation details into part of the API and creates the misconception that clients may choose user identities freely.

## 4. Hiding HttpServletRequest and HttpServletResponse

**HttpServletRequest** lets controllers read general request information. **HttpServletResponse** lets controllers write headers, cookies, or manipulate responses. These objects themselves are not individual HTTP parameters.

Example:

~~~java
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

@GetMapping("/api/download-link")
DownloadLinkView createDownloadLink(
    @Parameter(hidden = true) HttpServletRequest request,
    @Parameter(hidden = true) HttpServletResponse response
) {
    String requestId = request.getHeader("X-Request-Id");
    response.setHeader("X-Processed-By", "document-service");
    return documentService.createLink(requestId);
}
~~~

In Spring Boot applications using modern servlet stacks, these classes belong to **jakarta.servlet.http**. Older Spring Boot 2 applications may use the **javax.servlet.http** namespace. Choose imports matching the Spring Boot and servlet API generation your project uses.

Springdoc typically ignores **HttpServletRequest** and **HttpServletResponse** by default. If they appear under an operation's **parameters**, check whether custom annotations or wrappers cause springdoc to interpret them as API inputs. Mark them hidden to make intent explicit.

In Spring WebFlux, controllers can accept objects like **ServerWebExchange**, **ServerHttpRequest**, or **ServerHttpResponse**. These are reactive-stack abstractions, not regular business parameters. If they get included in OpenAPI parameter lists, hide them with **@Parameter(hidden = true)** and inspect the generated documentation for WebFlux endpoints.

## 5. Do Not Hide Headers or Cookies Belonging to the API Contract

A common point of confusion is thinking that because a controller reads data via **HttpServletRequest**, everything read from the request is internal. Distinguish between:

- **Request object:** an infrastructure object injected by the servlet container.
- **Header, cookie, query parameter, or path parameter:** can be public inputs sent by the client.

For instance, if clients must send **X-Tenant-Id** to select a tenant, that header is part of the contract. You can bind it directly with **@RequestHeader**:

~~~java
@GetMapping("/api/reports")
ReportView report(
    @RequestHeader("X-Tenant-Id") String tenantId
) {
    return reportService.createForTenant(tenantId);
}
~~~

Springdoc can infer this as a header parameter. If the controller must retain **HttpServletRequest** to read the header, declare the public header explicitly using OpenAPI metadata:

~~~java
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.enums.ParameterIn;
import io.swagger.v3.oas.annotations.Parameter;

@GetMapping("/api/reports")
@Operation(parameters = {
    @Parameter(
        name = "X-Tenant-Id",
        in = ParameterIn.HEADER,
        required = true,
        description = "Tenant ID requested by the client",
        example = "tenant-42"
    )
})
ReportView report(
    @Parameter(hidden = true) HttpServletRequest request
) {
    String tenantId = request.getHeader("X-Tenant-Id");
    return reportService.createForTenant(tenantId);
}
~~~

In this case, the **HttpServletRequest** object is hidden while **X-Tenant-Id** still appears in OpenAPI as a header parameter. Validate and authorize tenants on the server; publishing a header does not grant clients access to arbitrary tenants.

### Authorization Is a Special Case

Do not document the **Authorization** header using a regular **@Parameter(in = HEADER)**. OpenAPI has a dedicated security scheme mechanism for authentication. For bearer tokens, define a security scheme and attach the requirement to operations:

~~~java
import io.swagger.v3.oas.annotations.security.SecurityRequirement;
import io.swagger.v3.oas.annotations.security.SecurityScheme;
import io.swagger.v3.oas.annotations.enums.SecuritySchemeType;
import org.springframework.context.annotation.Configuration;

@Configuration
@SecurityScheme(
    name = "bearerAuth",
    type = SecuritySchemeType.HTTP,
    scheme = "bearer",
    bearerFormat = "JWT"
)
class OpenApiSecurityConfiguration {}
~~~

~~~java
@Operation(
    summary = "Get current profile",
    security = @SecurityRequirement(name = "bearerAuth")
)
@GetMapping("/api/profile")
ProfileView currentProfile(
    @Parameter(hidden = true)
    @AuthenticationPrincipal AppPrincipal principal
) {
    return profileService.findByUserId(principal.userId());
}
~~~

Swagger UI understands that the endpoint requires the defined bearer authentication mechanism. Clients enter or supply tokens through the Authorize feature; documentation does not need a separate Authorization header field in the parameter list. If the API uses OAuth2 or OpenID Connect, document the corresponding flow using an appropriate security scheme.

Authentication cookies should also be distinguished from business cookies. If a session cookie serves as the security mechanism, document an **apiKey** security scheme placed in **cookie** when fitting the OpenAPI contract. If a cookie like **language** or **viewMode** is optional client-sent data, document it as a cookie parameter rather than hiding it.

## 6. Hiding Custom Contexts from HandlerMethodArgumentResolver

Many applications create argument resolvers to inject context into controllers. For example, a **@CurrentTenant** annotation might extract the tenant from a token or header and provide a **TenantContext** object:

~~~java
@Target(ElementType.PARAMETER)
@Retention(RetentionPolicy.RUNTIME)
public @interface CurrentTenant {}
~~~

Controller accepting the context:

~~~java
@GetMapping("/api/tenant/summary")
TenantSummaryView summary(
    @Parameter(hidden = true)
    @CurrentTenant TenantContext tenantContext
) {
    return tenantService.summary(tenantContext.tenantId());
}
~~~

**TenantContext** is created by the resolver on the server, so clients do not send this object directly. If clients must specify a tenant via a header, query, or token claim, document that exact input mechanism in OpenAPI. Do not turn **TenantContext** into a request schema simply because it appears in the controller signature.

If a custom context type is used across many controllers, establish a team convention: every resolver-injected parameter must be annotated with **@Parameter(hidden = true)** unless that parameter represents a public HTTP input. This convention makes code reviews clear and avoids relying on default library inference.

## 7. Distinguishing @Parameter, @Hidden, and @Schema

These annotations have similar names yet affect different parts of OpenAPI:

| Annotation | Effect | When to Use |
| --- | --- | --- |
| **@Parameter(hidden = true)** | Hides a single parameter of an operation | Principal, request context, or custom resolver arguments |
| **@Hidden** | Hides an operation or supported component from documentation | Internal endpoints not meant for publication |
| **@Operation(hidden = true)** | Hides an entire operation | A handler outside the public API |
| **@Schema(hidden = true)** | Hides a property or schema element | Internal DTO fields that should not appear in schemas |

Do not put **@Hidden** at the controller level just to exclude an infrastructure parameter. Doing so can remove the entire endpoint from documentation. Likewise, do not use **@Schema(hidden = true)** instead of **@Parameter(hidden = true)** on method parameters; one controls schemas, while the other controls Parameter Objects.

## 8. Verifying Hidden Parameters in Generated Documentation

After starting the application, fetch the JSON specification:

~~~bash
curl -sS http://localhost:8080/v3/api-docs -o openapi.json
~~~

Check the endpoint's parameters list:

~~~bash
jq '.paths["/api/profile"].get.parameters' openapi.json
~~~

If the endpoint only uses internal principals and request context, those parameters should not appear in the **parameters** list or request body schema. If the endpoint has a public header such as **X-Tenant-Id**, that header must still appear.

Check security schemes:

~~~bash
jq '{
  schemes: .components.securitySchemes,
  operationSecurity: .paths["/api/profile"].get.security
}' openapi.json
~~~

The output should confirm:

- Principals, Authentication, request/response contexts, and internal custom contexts do not appear as inputs clients must supply.
- Business headers or cookies clients must send remain documented.
- Bearer token, OAuth2, or session mechanisms are represented with appropriate security schemes.
- Operations remain in documentation when only one of their parameters is hidden.
- Request bodies and schemas are not generated from internal context types.

Open Swagger UI and inspect the same operation. If a field still appears, check the OpenAPI JSON first to determine whether it is a parameter, schema property, or security scheme; each requires a different fix.

## 9. Common Issues

**Principal appears as a query parameter or request body.** Mark the parameter with **@Parameter(hidden = true)**, verify the annotation import is **io.swagger.v3.oas.annotations.Parameter**, and re-fetch **/v3/api-docs**.

**@AuthenticationPrincipal appears in Swagger UI.** This is a case where springdoc's FAQ instructs using **@Parameter(hidden = true)**. Verify the annotation is placed directly on the parameter with **@AuthenticationPrincipal**.

**Whole endpoint disappears when trying to hide one parameter.** Check whether **@Hidden** or **@Operation(hidden = true)** was placed at the controller or method level. Use **@Parameter(hidden = true)** on the specific parameter.

**Business header disappears from documentation.** If the controller reads the header from **HttpServletRequest**, bind it with **@RequestHeader** or declare the parameter explicitly via **@Operation(parameters = ...)**. Never hide a value clients must send.

**Authorization appears as a header parameter.** Switch to **SecurityScheme** and **SecurityRequirement**. OpenAPI dedicates security mechanisms to the Authorization header.

**Custom context type appears in schemas.** Annotate the resolver parameter with **@Parameter(hidden = true)** and check whether it is being treated as a request body or model attribute.

## 10. Checklist

- [ ] Identify which parameters are injected by the framework or server.
- [ ] Use **@Parameter(hidden = true)** for principals, authentication, or custom contexts that must be hidden.
- [ ] Do not generate parameters for **HttpServletRequest** or **HttpServletResponse** as if clients must send those objects.
- [ ] Keep headers, cookies, and query parameters that genuinely belong to the contract.
- [ ] Document Authorization using a security scheme, not a regular header parameter.
- [ ] Use **@Hidden** or **@Operation(hidden = true)** only when hiding an entire operation.
- [ ] Inspect **/v3/api-docs** and Swagger UI after changing annotations.
- [ ] Confirm endpoints still function and Spring still injects the right principal/context at runtime.

## 11. References

- [Springdoc OpenAPI v2 FAQ](https://springdoc.org/v2/faq.html): hiding parameters, handling **@AuthenticationPrincipal**, Spring MVC injectable types excluded from documentation, and documenting Authorization via security requirements.
- [Spring Framework — Method Arguments](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/arguments.html): special argument types that Spring MVC can supply to handler methods.
- [OpenAPI — Describing Parameters](https://swagger.io/docs/specification/describing-parameters/): parameter documentation rules and headers reserved for authentication mechanisms.

Hiding infrastructure parameters keeps OpenAPI focused on what clients actually need to send. Maintain a clear boundary between server-provided context and HTTP contract data, then inspect the generated specification to ensure Swagger UI reflects that boundary accurately.
