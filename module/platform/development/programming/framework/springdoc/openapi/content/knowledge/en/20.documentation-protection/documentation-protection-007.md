# Hiding Operations Does Not Replace Authentication or Authorization

Springdoc-openapi allows hiding controllers or operations from OpenAPI documentation using `@Hidden`, `@Operation(hidden = true)`, and `GroupedOpenApi` filters. These techniques only control what appears in documentation and Swagger UI. They do not remove Spring MVC mappings, block HTTP requests, or grant or revoke access permissions.

An endpoint hidden from Swagger UI can still be called directly with curl, Postman, another application, or a known URL. Therefore, API protection must be enforced at runtime using Spring Security, method security, and per-resource permission checks. OpenAPI documents and Swagger UI are also surfaces that need separate control because they can expose paths, schemas, examples, and system capabilities.

## 1. What Does Hiding an Operation Do?

Hiding an operation can help:

- Exclude internal endpoints from partner-facing documentation.
- Omit experimental or operational endpoints from public documentation.
- Reduce noise in Swagger UI so users focus on the APIs they are meant to call.
- Split documentation by audience using different OpenAPI groups.

For example, a controller with an internal endpoint:

```java
@RestController
@RequestMapping("/internal/cache")
class CacheMaintenanceController {

    @PostMapping("/clear")
    void clearCache() {
        cacheService.clear();
    }
}
```

If the operation does not appear in Swagger UI, the `/internal/cache/clear` mapping still exists in Spring MVC. Any client sending a request to this URL can still reach the controller. The access outcome depends on runtime security configuration.

Hiding is a documentation-publishing decision. Authentication and authorization determine who is permitted to perform the action.

## 2. Hiding a Controller with `@Hidden`

You can place `@Hidden` at the controller level so springdoc omits all operations of that controller from the OpenAPI document:

```java
import io.swagger.v3.oas.annotations.Hidden;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@Hidden
@RestController
@RequestMapping("/internal/cache")
class CacheMaintenanceController {

    @PostMapping("/clear")
    void clearCache() {
        cacheService.clear();
    }
}
```

`@Hidden` prevents the controller from appearing in springdoc-generated documentation. Spring still registers the controller and its mappings as usual. If the endpoint must be restricted to administrators or internal services, a dedicated authorization rule is required.

Do not rely on `@Hidden` as a security measure for high-impact endpoints such as clearing caches, running background jobs, altering configuration, or managing data.

## 3. Hiding a Single Operation with `@Operation(hidden = true)`

If you only want to hide one method in a controller while still publishing the others, use the `hidden` attribute of `@Operation`:

```java
import io.swagger.v3.oas.annotations.Operation;
import java.util.List;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class ReportController {

    @GetMapping("/api/reports")
    List<ReportResponse> listReports() {
        return reportService.list();
    }

    @Operation(hidden = true)
    @PostMapping("/internal/reports/rebuild-index")
    void rebuildIndex() {
        reportService.rebuildIndex();
    }
}
```

In this example, `GET /api/reports` remains in the documentation while `POST /internal/reports/rebuild-index` is hidden. Both mappings are still registered by Spring MVC.

Choose `@Hidden` when hiding an entire controller or annotated element; choose `@Operation(hidden = true)` when hiding a specific operation. After adding the annotation, inspect the OpenAPI JSON/YAML to confirm the intended operation disappears from the document.

## 4. Filtering Operations Out of a Group with `GroupedOpenApi`

An operation may not need to be hidden globally. For instance, an internal endpoint should appear in employee documentation but stay out of public documentation. In that case, filtering by path or package per group is an appropriate choice.

```java
import org.springdoc.core.models.GroupedOpenApi;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class OpenApiGroupsConfiguration {

    @Bean
    GroupedOpenApi publicApi() {
        return GroupedOpenApi.builder()
                .group("public")
                .pathsToMatch("/api/**")
                .pathsToExclude("/api/internal/**")
                .build();
    }

    @Bean
    GroupedOpenApi internalApi() {
        return GroupedOpenApi.builder()
                .group("internal")
                .pathsToMatch("/api/internal/**", "/internal/**")
                .build();
    }
}
```

With this setup, internal endpoints are excluded from the `public` document yet can appear in the `internal` document. Filters affect only the corresponding documentation; they do not change request mappings or the security filter chain.

You can filter by package using `packagesToScan(...)` and `packagesToExclude(...)`. Whether filtering by path or package, never treat an endpoint's absence from the public group as proof that the endpoint is protected.

## 5. Comparing Global Hiding and Group Filtering

| Approach | Effect on Documentation | Effect on Runtime Endpoint |
|---|---|---|
| `@Hidden` on controller | Hides controller from springdoc-generated documentation | None |
| `@Operation(hidden = true)` | Hides operation from documentation | None |
| `pathsToExclude(...)` | Excludes paths from the configured group | None |
| `packagesToExclude(...)` | Excludes controller packages from the configured group | None |
| Not registering Swagger UI | Does not serve the UI under that configuration | None |
| Disabling `springdoc.api-docs.enabled` | Does not serve OpenAPI endpoints under that configuration | None |
| Spring Security authorization rules | May deny runtime requests | Yes |
| Method security and resource-level checks | May deny unauthorized method/data access | Yes |

Hiding operations and protecting operations can be applied together. For example, an internal endpoint can be omitted from public documentation while still requiring the `OPS_ADMIN` role at runtime.

## 6. Why Hiding Operations Is Not a Security Boundary

An OpenAPI document is a description of operations. Swagger UI is an interface for reading documentation and sending test requests. Neither sits on the mandatory execution path of all HTTP clients.

Clients can call APIs using:

- `curl` or HTTPie.
- Postman or Insomnia.
- Another backend service.
- Previously generated SDKs.
- Custom scripts or tools.
- URLs captured in logs, browser history, or older documentation.

These clients do not need to open Swagger UI and do not need the operation to appear in OpenAPI. If the server permits the request, the controller executes.

For example, even if `/internal/cache/clear` is hidden, the following request still reaches the server:

```bash
curl -i -X POST \
  https://api.example.com/internal/cache/clear
```

If Spring Security does not block the request and the controller does not check permissions, the action can execute. The fact that users do not see the endpoint in the UI does not prevent this request.

## 7. Protecting Runtime Endpoints with Spring Security

Authorization rules must be based on paths, HTTP methods, roles, authorities, or suitable policies. For example, an administrative endpoint restricted to users with the `OPS_ADMIN` role:

```java
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
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/internal/**")
                            .hasRole("OPS_ADMIN")
                        .requestMatchers("/api/admin/**")
                            .hasRole("ADMIN")
                        .requestMatchers("/api/**")
                            .authenticated()
                        .anyRequest().authenticated()
                )
                .httpBasic(Customizer.withDefaults())
                .build();
    }
}
```

This is a Basic auth configuration example illustrating authorization rules; real applications can use a JWT Resource Server, sessions, or another authentication mechanism. An appropriate `AuthenticationProvider`/user store is needed to verify identities. Never use sample accounts or hard-coded passwords in production.

Matcher order matters. Specific rules `/internal/**` and `/api/admin/**` must precede the broader `/api/**` rule. If `.anyRequest().authenticated()` is placed first, matchers after it will never be evaluated.

Actual URLs may be affected by context paths, servlet paths, or reverse proxies. Verify matchers against the paths Spring Security actually receives.

## 8. Protecting Swagger UI and OpenAPI Endpoints Separately

Even when runtime APIs are protected, OpenAPI documentation may still be public. Documentation can reveal:

- Internal path and operation names.
- Request/response schemas and data fields.
- Error codes, examples, and business workflows.
- Service names, server URLs, versions, or extensions.
- Authentication mechanisms and scopes in use.

If documentation is for employees only, protect both Swagger UI and JSON/YAML endpoints. Example:

Add documentation matchers to the application's filter chain:

```java
.authorizeHttpRequests(auth -> auth
        .requestMatchers(
                "/swagger-ui.html",
                "/swagger-ui/**",
                "/v3/api-docs",
                "/v3/api-docs.yaml",
                "/v3/api-docs/**",
                "/v3/api-docs/*.yaml"
        ).hasRole("API_DOCS")
        .requestMatchers("/internal/**").hasRole("OPS_ADMIN")
        .anyRequest().authenticated()
)
```

This snippet illustrates rules for the documentation surface. If the application has multiple `SecurityFilterChain` beans, set `securityMatcher` and `@Order` appropriately so this filter chain does not accidentally permit other API requests. Within a single filter chain, integrate documentation matchers into the API rule set and place them before broader matchers.

Swagger UI fetches the OpenAPI document from JSON/YAML endpoints. If opening the UI is permitted while docs endpoints require a role the user lacks, the UI page may load yet display errors when fetching the spec. Grant consistent permissions to both surfaces or omit the UI for that user group.

If you changed `springdoc.api-docs.path`, `springdoc.swagger-ui.path`, group names, or context path, update request matchers accordingly. For group docs, check the actual generated group and YAML URLs.

## 9. Hiding Swagger UI Does Not Mean Hiding the OpenAPI Document

The two components have separate URLs and configurations:

| Component | Common Default URL | Springdoc Configuration |
|---|---|---|
| Swagger UI | `/swagger-ui.html`, `/swagger-ui/index.html` | `springdoc.swagger-ui.enabled`, `springdoc.swagger-ui.path` |
| OpenAPI JSON | `/v3/api-docs` | `springdoc.api-docs.enabled`, `springdoc.api-docs.path` |
| OpenAPI YAML | `/v3/api-docs.yaml` | Same api-docs configuration |
| Grouped OpenAPI | `/v3/api-docs/{group}` and corresponding YAML forms | `GroupedOpenApi` or `springdoc.group-configs` |

Disabling Swagger UI does not automatically disable JSON/YAML endpoints. Conversely, disabling API docs can leave Swagger UI with no document to load. Decide separately whether to expose the UI or the spec.

Example disabling both in production:

```yaml
springdoc:
  api-docs:
    enabled: false
  swagger-ui:
    enabled: false
```

Disabling springdoc only stops serving documentation per configuration; it does not disable API controllers. Business endpoints still require their own security rules. After changing configuration, test the UI and JSON/YAML URLs directly to confirm they are no longer served.

## 10. Separating Public and Internal Documentation

An application can create groups by audience:

```java
@Bean
GroupedOpenApi publicApi() {
    return GroupedOpenApi.builder()
            .group("public")
            .pathsToMatch("/api/**")
            .pathsToExclude("/api/internal/**", "/api/admin/**")
            .build();
}

@Bean
GroupedOpenApi internalApi() {
    return GroupedOpenApi.builder()
            .group("internal")
            .pathsToMatch("/api/internal/**", "/api/admin/**")
            .build();
}
```

The public group is strictly documentation for partners or external consumers. The internal group may contain administrative or internal integration operations. Define who can access `/v3/api-docs/internal` and any `/swagger-ui` displaying that group.

If an endpoint should not be published in any documentation, use `@Hidden` or exclude it from all relevant groups. If an endpoint needs protection, add runtime authorization regardless of whether documentation displays it.

For public APIs, review schemas and examples as well. Even when internal operations are excluded from a group, shared schemas or extensions can accidentally leak property names, enums, structures, or internal details.

## 11. Method-Level Authorization

Path-based authorization is the first layer of defense. For complex business rules, use method security to verify authorities at the service or method requiring protection.

```java
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
class CacheAdministrationService {

    @PreAuthorize("hasAuthority('CACHE_CLEAR')")
    public void clearCache() {
        // Perform cache clearing operation.
    }
}
```

Enable method security:


```java
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@Configuration
@EnableMethodSecurity
class MethodSecurityConfiguration {
}
```

## 12. Per-Resource Authorization, Not Just Per-URL

Checking only a general role may not be enough. For instance, a user with role `USER` may read orders, but only orders belonging to their own account. If the API only authenticates the user and allows `GET /api/orders/{id}` for any ID, an attacker can swap IDs to access someone else's data.

This object-level authorization flaw is commonly known as Broken Object Level Authorization (BOLA) or IDOR. Permissions must be checked on the specific requested resource:

```java
@Service
class OrderQueryService {

    @PreAuthorize("@orderAccess.canRead(authentication, #orderId)")
    public Order getOrder(UUID orderId) {
        return orderRepository.findById(orderId)
                .orElseThrow(OrderNotFoundException::new);
    }
}
```

`orderAccess.canRead(...)` is an application policy bean responsible for verifying whether the caller has permission to read that order. It can check owner ID, tenant, organizational relationships, or sharing rules. Never rely on a hidden endpoint or hard-to-guess IDs as a substitute for authorization.

If hiding the existence of a resource is desired, the application can choose to return `404` instead of `403` under a consistent policy. This is a runtime decision; OpenAPI should describe the responses clients can actually receive.

## 13. Authentication, Authorization, and Hiding Documentation

Three concepts address three distinct concerns:

| Concept | Question | Common Mechanisms |
|---|---|---|
| Hiding/publishing docs | Which operations appear in the spec and Swagger UI? | `@Hidden`, `hidden = true`, group filters |
| Authentication | Who is the client and are their credentials valid? | HTTP Basic, Bearer/JWT, OAuth2, sessions |
| Authorization | May the authenticated client perform this action on this resource? | Request matchers, roles/authorities, method security, domain policies |

An operation can be hidden yet still require authentication and authorization. An operation can be publicly visible in documentation yet still require a token at runtime. Documentation should describe security requirements accurately matching real behavior.

## 14. Avoiding Ineffective Concealment Techniques

The following measures are not enough to protect an API:

- Changing an endpoint URL to a hard-to-guess string.
- Omitting the endpoint from READMEs or Swagger UI.
- Removing the operation from OpenAPI while leaving the route publicly accessible.
- Checking buttons or menus only on the frontend.
- Using JavaScript to hide action buttons.
- Relying on CORS to stop all clients from calling the API.
- Using uncommon HTTP methods expecting outsiders won't guess them.

CORS is a browser policy controlling whether cross-origin web pages can read responses; it does not prevent curl, Postman, or backend clients from sending requests. Secret URLs can also leak via logs, history, telemetry, or network traffic. Security must be enforced on the server for every request.

## 15. Managing Documentation by Environment

Not every environment needs to expose Swagger UI and OpenAPI documents in the same way. Separate profiles can be used:

`application-dev.yml`:

```yaml
springdoc:
  api-docs:
    enabled: true
  swagger-ui:
    enabled: true
```

`application-prod.yml`:

```yaml
springdoc:
  api-docs:
    enabled: false
  swagger-ui:
    enabled: false
```

If operations teams need documentation in production, you can keep docs enabled while restricting access with Spring Security, internal networks, gateways, or identity-aware proxies. Do not rely solely on profiles if environment settings can be overridden unexpectedly; verify effective configuration upon deployment.

Another option is generating and storing OpenAPI artifacts in the CI/CD pipeline and distributing docs via a controlled developer portal. This separates spec publishing from runtime services. Whichever distribution model you choose, review content before making it public.

## 16. Testing That Hidden Operations Remain Protected

After using `@Hidden` or group filters, verify two separate things: that the operation disappears from documentation and that direct requests are properly controlled.

Sample test matrix:

| Check | Expected Result |
|---|---|
| Search for hidden operation in `/v3/api-docs` | Absent from the selected document |
| Open Swagger UI and look for hidden operation | That operation is not displayed |
| Call protected endpoint unauthenticated | `401` or appropriate challenge |
| Call with authenticated user lacking role | `403` or resource-hiding response per policy |
| Call with user having appropriate role/permission | Succeeds per business logic |
| Call with valid user who does not own resource | Denied per object-level policy |
| Direct access to `/v3/api-docs/internal` without permission | Denied if internal docs are protected |
| Access to Swagger UI without permission | Denied if UI is restricted |

You can test runtime endpoints with curl:

```bash
# Without credentials: must be rejected if the endpoint requires authentication
curl -i -X POST https://api.example.com/internal/cache/clear

# With test credentials having appropriate permissions
curl -i -X POST \
  -H "Authorization: Bearer <access-token>" \
  https://api.example.com/internal/cache/clear
```

Use only test tokens issued in an appropriate environment. Never put real tokens into shell history or shared logs.

## 17. Checking That Documentation Does Not Leak Unintended Information

Hiding operations is not always enough to produce safe public documentation. Before publishing a spec, check:

- Do server URLs contain internal hostnames, private IPs, or base paths not meant for outsiders?
- Do descriptions mention internal system names, operational workflows, or sensitive deployment details?
- Do examples contain real emails, IDs, personal data, tokens, or credentials?
- Do schemas expose internal properties or fields that should not be published?
- Do enums list sensitive statuses or operational codes?
- Do `x-*` extensions contain internal information?
- Do security schemes accurately describe flows without containing secrets?
- Do groups accidentally include internal endpoints due to overly broad path filters?

For public documentation, add an OpenAPI artifact inspection step before release. For internal documentation, still enforce access control and audit access logs per organizational policy.

## 18. Common Pitfalls

| Symptom | Possible Cause | Resolution |
|---|---|---|
| Endpoint is hidden yet still callable | `@Hidden` affects documentation only | Add runtime authorization with Spring Security/method security |
| Swagger UI hides operation yet `/v3/api-docs` still includes it | Hidden only in UI or viewing a different group document | Check OpenAPI JSON/YAML and scope of annotations/filters |
| Disabled Swagger UI yet JSON is still accessible | UI and API docs have separate configurations | Disable or protect `springdoc.api-docs` endpoints |
| Protected `/v3/api-docs` yet UI reports spec load error | User has UI access but lacks docs endpoint access | Grant consistent access to UI and spec or remove UI |
| Regular user can call internal endpoint | Only hid operation, missing matcher or wrong matcher order | Add specific rules before general rules and test |
| User with role can read others' data | Checked role only, missing object-level authorization | Check owner, tenant, and policy on each resource |
| Public group still leaks admin endpoint | Overlapping path filters or missing exclusions | Audit all paths in the public document |
| CORS configured yet curl still calls endpoint | Confused CORS with authorization | Protect requests on the server with authentication/authorization |
| Production docs exposed unintentionally | Profile or security rules not applied as expected | Check effective configuration and call docs URLs directly |

## 19. Secure Implementation Workflow

1. Classify operations by audience: public, authenticated, admin, or internal.
2. Use `@Hidden`, `@Operation(hidden = true)`, or group filters to select published content.
3. Design Spring Security rules for all runtime endpoints, including endpoints omitted from documentation.
4. Use method security for sensitive actions and policies checking permissions on each resource.
5. Decide whether Swagger UI and JSON/YAML docs should be enabled in each environment.
6. If internal docs are enabled, protect both the UI and spec endpoints, including groups and YAML formats.
7. Review schemas, examples, server URLs, extensions, and metadata before publishing public docs.
8. Test direct requests with unauthenticated callers, under-privileged users, and authorized users.
9. Re-verify after changing paths, group names, context paths, or reverse proxies.
10. Monitor authorization and documentation access logs, stripping tokens/credentials from logs.

## 20. Design Principles

- Treat `@Hidden`, `hidden = true`, and group filters as documentation content-control tools.
- Never assume a hidden operation cannot be called.
- Protect runtime APIs with Spring Security and business-layer permission checks.
- Use method security for sensitive actions and object-level authorization for owner/tenant-scoped data.
- Protect Swagger UI and OpenAPI JSON/YAML endpoints as two separate surfaces.
- When using groups, protect each group's URLs and corresponding YAML forms.
- Disabling Swagger UI does not disable OpenAPI endpoints; disabling docs does not disable APIs.
- Review public documentation to avoid leaking internal schemas, examples, server URLs, or extensions.
- Do not rely on CORS, obscure URLs, or frontend hiding as authorization measures.
- Test with direct HTTP requests, not only through the Swagger UI interface.

## Conclusion

Hiding operations with `@Hidden`, `@Operation(hidden = true)`, or `GroupedOpenApi` filters only removes operations from the corresponding OpenAPI document. Spring MVC still keeps the endpoints active and clients can still call URLs directly. Therefore, every endpoint must be protected with runtime authentication and authorization; sensitive actions require method-level and per-resource permission checks. At the same time, Swagger UI and JSON/YAML endpoints must be protected separately if the documentation is not intended for the public. Treat hiding as managing documentation publishing scope, while Spring Security and business policies enforce access control.
