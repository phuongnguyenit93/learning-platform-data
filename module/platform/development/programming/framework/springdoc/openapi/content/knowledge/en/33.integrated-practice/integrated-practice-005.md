# Grouping Public, Internal, and Admin APIs

A Spring Boot application can serve multiple user groups: external customers, internal services, and administrative staff. Each group should see only the operations it needs. Springdoc-openapi supports generating separate documents for each group via GroupedOpenApi; Spring Security protects both the documentation and the endpoints by access permissions.

This hands-on exercise builds three groups:

- **Public API**: public operations for customers or integrating partners.
- **Internal API**: operations intended for service-to-service communication.
- **Admin API**: administrative operations requiring administrative staff permissions.

The expected outcome is that each group has its own OpenAPI document, Swagger UI can list the documents, and document retrieval permissions match the runtime API security policy.

## 1. Designing API boundaries before configuration

Suppose a Catalog application has the following endpoints:

| Group | Path | Users |
|---|---|---|
| Public | /api/public/products/** | Customers and partners. |
| Internal | /api/internal/inventory/** | Internal services with the appropriate scope. |
| Admin | /api/admin/products/** | Staff with administrative privileges. |

Endpoints should follow a consistent path convention. This allows Springdoc to select operations by path and Spring Security to enforce authorization along the exact same boundaries.

Example controller skeletons:

~~~java
@RestController
@RequestMapping("/api/public/products")
class PublicProductController {

    @GetMapping
    List<ProductSummary> listProducts() {
        // Return publicly exposed data.
        return List.of();
    }
}

@RestController
@RequestMapping("/api/internal/inventory")
class InternalInventoryController {

    @PostMapping("/reservations")
    ReservationResponse reserve(@RequestBody ReservationRequest request) {
        // Called by internal services.
        return new ReservationResponse();
    }
}

@RestController
@RequestMapping("/api/admin/products")
class AdminProductController {

    @PostMapping
    ProductResponse create(@RequestBody CreateProductRequest request) {
        // Administrative operation.
        return new ProductResponse();
    }
}
~~~

This illustrates path separation. In a real application, controllers should invoke services and return appropriate DTOs; never return persistence entities directly just because an endpoint resides in a separate group.

## 2. Creating three OpenAPI groups

Use GroupedOpenApi so each group generates an independent document:

~~~java
import org.springdoc.core.models.GroupedOpenApi;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class ApiDocumentationGroups {

    @Bean
    GroupedOpenApi publicApi() {
        return GroupedOpenApi.builder()
                .group("public")
                .pathsToMatch("/api/public/**")
                .build();
    }

    @Bean
    GroupedOpenApi internalApi() {
        return GroupedOpenApi.builder()
                .group("internal")
                .pathsToMatch("/api/internal/**")
                .build();
    }

    @Bean
    GroupedOpenApi adminApi() {
        return GroupedOpenApi.builder()
                .group("admin")
                .pathsToMatch("/api/admin/**")
                .build();
    }
}
~~~

The application will serve three OpenAPI documents:

| Group | URL |
|---|---|
| public | /v3/api-docs/public |
| internal | /v3/api-docs/internal |
| admin | /v3/api-docs/admin |

Each group can also be fetched in YAML format by appending the .yaml suffix, such as /v3/api-docs/admin.yaml. If both JSON and YAML are exposed, protect both URLs with the same policy.

Each group contains only operations matching its path filter. If a path matches multiple groups, an operation may appear in multiple documents. Therefore, review patterns carefully to avoid accidentally exposing internal endpoints in public documentation.

### 2.1. Disabling the default ungrouped document

Springdoc can generate a default document at /v3/api-docs alongside the groups. The default document can include all discovered controllers. If the goal is to publish only the three grouped documents, disable the default document:

~~~yaml
springdoc:
  enable-default-api-docs: false
~~~

After disabling it, verify the group URLs still work. Do not rely on Swagger UI showing only one group to ensure other operations do not appear in the default document.

## 3. Listing groups in Swagger UI

A single Swagger UI can let viewers switch between OpenAPI documents:

~~~yaml
springdoc:
  swagger-ui:
    path: /docs
    urls:
      - name: Public API
        url: /v3/api-docs/public
      - name: Internal API
        url: /v3/api-docs/internal
      - name: Admin API
        url: /v3/api-docs/admin
    urls-primary-name: Public API
    doc-expansion: none
    operations-sorter: alpha
    tags-sorter: alpha
~~~

When opening /docs, users can select a document by group. urls-primary-name selects the default document. This is merely a list of documents the UI can load; it does not merge paths and does not protect endpoints.

### 3.1. Choosing the audience for Swagger UI

The example above suits an internal developer portal for users authorized to view documentation. Do not expose a Swagger UI with a dropdown containing Internal API and Admin API to external customers.

There are two implementation options:

1. **Internal documentation portal**: protect the entire Swagger UI, swagger-config, and group docs; the portal lists public, internal, and admin.
2. **Dedicated public documentation portal**: configure the UI solely with /v3/api-docs/public; omit internal/admin URLs from the public portal configuration.

If you only need to provide the public contract to partners, they can fetch /v3/api-docs/public directly or use a public UI containing only that document. Internal documentation is delivered through an internal portal or a separate pipeline.

## 4. Protecting documentation per audience

Group filters are not security boundaries. Anyone who can reach a document URL can read the operations, schemas, parameters, and security metadata inside it. Enforce authorization on both documentation and the runtime API.

Sample policy:

| Resource | Permission |
|---|---|
| /v3/api-docs/public | Public |
| /v3/api-docs/internal | Authority SCOPE_internal.docs |
| /v3/api-docs/admin | Role DOCS_ADMIN |
| /docs, /swagger-ui.html, /swagger-ui/** | Role DOCS_VIEWER |
| /v3/api-docs/swagger-config | Role DOCS_VIEWER |
| /api/public/** | Public |
| /api/internal/** | Authority SCOPE_internal |
| /api/admin/** | Role ADMIN |

Example SecurityFilterChain with Spring Security:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class ApiSecurityConfiguration {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/v3/api-docs/swagger-config")
                            .hasRole("DOCS_VIEWER")
                        .requestMatchers(
                                "/v3/api-docs/public",
                                "/v3/api-docs/public.yaml"
                        )
                            .permitAll()
                        .requestMatchers(
                                "/v3/api-docs/internal",
                                "/v3/api-docs/internal.yaml"
                        )
                            .hasAuthority("SCOPE_internal.docs")
                        .requestMatchers(
                                "/v3/api-docs/admin",
                                "/v3/api-docs/admin.yaml"
                        )
                            .hasRole("DOCS_ADMIN")
                        .requestMatchers("/v3/api-docs/**")
                            .denyAll()
                        .requestMatchers(
                                "/docs",
                                "/swagger-ui.html",
                                "/swagger-ui/**"
                        ).hasRole("DOCS_VIEWER")
                        .requestMatchers("/api/public/**")
                            .permitAll()
                        .requestMatchers("/api/internal/**")
                            .hasAuthority("SCOPE_internal")
                        .requestMatchers("/api/admin/**")
                            .hasRole("ADMIN")
                        .anyRequest()
                            .authenticated()
                )
                .build();
    }
}
~~~

These are the authorization rules; the application still needs appropriate authentication configuration such as OAuth2 Resource Server, JWT, session, or the chosen login mechanism. Matcher ordering is critical: group docs and swagger-config are declared before the catch-all /v3/api-docs/** matcher.

### 4.1. Separating documentation viewing permissions from API operation permissions

DOCS_VIEWER allows opening the developer portal; DOCS_ADMIN allows fetching admin docs; ADMIN allows calling administrative operations. These permissions can be granted to different groups of people.

Do not grant ADMIN merely so a developer can read documentation. Conversely, having DOCS_ADMIN does not mean a user is permitted to create or delete products.

### 4.2. Preventing the default document from leaking groups

If enable-default-api-docs is disabled, the default /v3/api-docs route is no longer exposed. If you keep the default document enabled, protect it with strict authorization because it can aggregate public, internal, and admin operations.

Do not protect only Swagger UI. Users can call /v3/api-docs/{group} directly with curl or an HTTP client.

## 5. Documenting security in OpenAPI

SecurityFilterChain enforces permissions at runtime. OpenAPI security schemes describe the authentication mechanism so clients understand how to call the API.

Example Bearer scheme declaration:

~~~java
import io.swagger.v3.oas.annotations.OpenAPIDefinition;
import io.swagger.v3.oas.annotations.security.SecurityScheme;
import io.swagger.v3.oas.annotations.enums.SecuritySchemeType;
import org.springframework.context.annotation.Configuration;

@Configuration
@OpenAPIDefinition
@SecurityScheme(
        name = "bearerAuth",
        type = SecuritySchemeType.HTTP,
        scheme = "bearer",
        bearerFormat = "JWT"
)
class OpenApiSecuritySchemeConfiguration {
}
~~~

Internal or admin controllers can reference the scheme:

~~~java
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.security.SecurityRequirement;

@Operation(
        summary = "Create product",
        security = @SecurityRequirement(name = "bearerAuth")
)
~~~

The HTTP Bearer scheme describes a token sent in the Authorization header. If the API uses OAuth2 scopes and needs to document scopes, declare an OAuth2 SecurityScheme with the corresponding flows/scopes. Specific roles or authorities must still be enforced by Spring Security.

## 6. Testing the contents of each group

Use MockMvc to verify each document contains only operations belonging to its audience:

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
class ApiDocumentationGroupsTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void publicDocumentContainsOnlyPublicPaths() throws Exception {
        mockMvc.perform(get("/v3/api-docs/public"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.paths['/api/public/products']").exists())
                .andExpect(jsonPath("$.paths['/api/internal/inventory/reservations']").doesNotExist())
                .andExpect(jsonPath("$.paths['/api/admin/products']").doesNotExist());
    }
}
~~~

This test checks document contents. You also need security tests to verify that users without sufficient permissions cannot download internal/admin documents.

## 7. Testing documentation access permissions

Example with a user who only has DOCS_VIEWER:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class ApiDocumentationAuthorizationTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void docsViewerCannotReadAdminDocument() throws Exception {
        mockMvc.perform(get("/v3/api-docs/admin")
                        .with(user("reader").roles("DOCS_VIEWER")))
                .andExpect(status().isForbidden());
    }

    @Test
    void docsAdminCanReadAdminDocument() throws Exception {
        mockMvc.perform(get("/v3/api-docs/admin")
                        .with(user("docs-admin")
                                .roles("DOCS_VIEWER", "DOCS_ADMIN")))
                .andExpect(status().isOk());
    }
}
~~~

If the application uses JWT scopes for internal APIs, use a JWT test postprocessor and grant the SCOPE_internal.docs authority. Do not substitute a user role if SecurityFilterChain requires a scope authority.

### 7.1. Testing public/internal/admin APIs at runtime

Beyond documentation, test real endpoints:

- Public endpoints are accessible according to the public policy.
- Internal endpoints reject requests lacking SCOPE_internal.
- Admin endpoints reject users without ADMIN.
- Users with DOCS_ADMIN but without ADMIN are denied administrative operations.

These tests prove runtime API access permissions are enforced independently of documentation.

## 8. Checking Swagger UI config

When Swagger UI lists three groups, the swagger-config endpoint must contain the right URLs:

~~~bash
curl -fsS -u docs-viewer:password \
  http://localhost:8080/v3/api-docs/swagger-config
~~~

Verify:

- urls includes the exact public, internal, and admin documents.
- urlsPrimaryName points to the desired entry.
- Internal/admin documents still require credentials when fetched.
- Public document contains no internal paths.

Do not hardcode real credentials into CI scripts or logs. Use test identities and pipeline-managed secrets.

If a public Swagger UI is needed, create a separate UI configuration containing only /v3/api-docs/public. Do not reuse the internal URL list on a public page.

## 9. Checking the default document and group endpoints

With springdoc.enable-default-api-docs=false:

- Group endpoints must still be tested individually.
- The default ungrouped document must not be published.
- swagger-config must still point to the grouped documents.

If you do not disable the default document, add tests verifying it is protected by an appropriate role and not publicly accessible.

Do not rely on the UI dropdown to confirm a group is hidden. Always request the OpenAPI document URLs directly in tests.

## 10. Common mistakes

- **Using GroupedOpenApi without Security configuration**: groups do not protect documents or runtime endpoints.
- **Leaving default /v3/api-docs public**: the aggregated document may contain internal/admin operations.
- **Putting internal/admin URLs in a public Swagger UI**: group names and paths can leak; endpoints still require protection.
- **Protecting UI while forgetting JSON endpoints**: clients can call /v3/api-docs/{group} directly.
- **Treating DOCS_ADMIN as ADMIN**: permission to read docs should not automatically grant administrative operation rights.
- **Using overly broad paths-to-match**: internal operations can leak into the public group.
- **Allowing path overlap between groups**: an operation may appear in multiple documents.
- **Testing only docs, not endpoints**: accurate documentation does not prove runtime authorization works.
- **Declaring Bearer scheme without enforcing Spring Security**: an OpenAPI security requirement is only a contract, not a request filter.
- **Protecting swagger-config without protecting Swagger UI assets**: users can load the page without the config, or vice versa.
- **Using one public Swagger UI for all audiences**: urls configuration is static and does not filter documents per user.

## 11. Implementation workflow for three audiences

1. **Design path conventions**: public, internal, and admin have clear prefixes.
2. **Create groups**: each audience gets its own GroupedOpenApi and group name.
3. **Disable the default document if unneeded**: prevent an aggregated endpoint from exposing operations.
4. **Create Swagger UI config**: list only the documents appropriate for the portal.
5. **Document security**: add security schemes and requirements for operations needing tokens.
6. **Protect document endpoints**: permitAll for public, scope for internal, role for admin.
7. **Protect runtime APIs**: apply independent authorization to controllers.
8. **Test group contents**: verify each document contains only permitted paths.
9. **Test access permissions**: unauthorized users cannot fetch documents or call APIs.
10. **Check the browser portal**: Swagger UI loads the right config and group documents.
11. **Review deployment**: ensure reverse proxy, CORS, and network policies do not open unintended access paths.

## 12. Review checklist

- [ ] Public, internal, and admin have clear path conventions.
- [ ] Each group has a unique name.
- [ ] Path filters do not overlap unintentionally.
- [ ] Public document contains no internal/admin operations.
- [ ] Default document is disabled or protected.
- [ ] Swagger UI urls are configured per audience.
- [ ] Swagger UI config endpoint is appropriately protected.
- [ ] Internal document requires the right scope/authority.
- [ ] Admin document requires the admin documentation role.
- [ ] Runtime APIs have separate authorization.
- [ ] OpenAPI security schemes accurately describe how credentials are sent.
- [ ] Tests exist for each group's contents.
- [ ] Tests exist for document retrieval and endpoint invocation permissions.
- [ ] Browser portal loads the right documents and static resources.
- [ ] Reverse proxy/CORS/network policies preserve access boundaries.

## 13. References

- [springdoc-openapi – Multiple OpenAPI definitions and GroupedOpenApi](https://springdoc.org/index.html#how-can-i-define-multiple-openapi-definitions-in-one-spring-boot-project)
- [springdoc-openapi – Configuration properties](https://springdoc.org/properties.html)
- [springdoc-openapi – Security support](https://springdoc.org/#how-can-i-add-authorization-header-in-requests)
- [Spring Security – Authorize HTTP Requests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html)
- [Spring Security – Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html)
- [Swagger UI – Configuration](https://swagger.io/docs/open-source-tools/swagger-ui/usage/configuration/)
- [OpenAPI Specification – Security Requirement Object](https://spec.openapis.org/oas/latest.html#security-requirement-object)

GroupedOpenApi separates documents by audience; Spring Security controls who can fetch documents and invoke endpoints; Swagger UI is merely the interface consuming those documents. Keep the three layers distinct, disable or protect the default document, and test both group contents and runtime access controls. When public, internal, and admin are grouped and protected consistently, development teams can distribute documentation to the right audience without exposing internal operations.
