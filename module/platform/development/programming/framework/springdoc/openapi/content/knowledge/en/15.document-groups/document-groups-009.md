# Customizations Applied Specifically to One Group

A Spring Boot application can publish multiple OpenAPI documents using `GroupedOpenApi`: for example, documentation for public clients, administrative documentation, and internal documentation. Groups may share controllers or contain distinct sets of endpoints. In many cases, each group also needs its own metadata such as title, version, server URLs, tags, security requirements, or operation descriptions.

Springdoc lets you attach customizers directly to a `GroupedOpenApi` configuration. This confines changes to the selected group's document. Contrast this with an `OpenApiCustomizer` bean targeting the default document and a `GlobalOpenApiCustomizer` bean applying across all documents. Choosing the right customizer scope prevents changes meant for the admin group from accidentally appearing in public documentation.

## 1. Each Group Is a Separate OpenAPI Document

When multiple `GroupedOpenApi` beans are declared, Springdoc generates independent documents. Each document can have its own `info`, `servers`, `tags`, `security`, `paths`, and `components`.

For example, an application with three groups:

| Group | Endpoint Scope | Documentation Purpose |
|---|---|---|
| `public` | `/api/public/**` | Contract for client applications |
| `admin` | `/api/admin/**` | Contract for administrative UIs |
| `internal` | `/internal/**` | Contract for internal integrations |

Documentation endpoints typically take the form:

```text
/v3/api-docs/public
/v3/api-docs/admin
/v3/api-docs/internal
```

Swagger UI can load each URL and let users pick a document. Each URL returns a distinct OpenAPI document, so the `admin` group can set a different title, version, and security requirement from the `public` group.

Grouping only organizes documentation and filters which operations enter a document. It does not create new routes, alter controller request mappings, or enforce access control. To protect administrative APIs, the application still needs Spring Security or runtime authorization rules.

## 2. Creating Groups with `GroupedOpenApi`

In Springdoc v2, `GroupedOpenApi` resides in package `org.springdoc.core.models`. A group can filter endpoints by path, package, media type, or method conditions.

Example declaring two groups:

```java
import org.springdoc.core.models.GroupedOpenApi;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class ApiGroupConfiguration {

    @Bean
    GroupedOpenApi publicApi() {
        return GroupedOpenApi.builder()
            .group("public")
            .pathsToMatch("/api/public/**")
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
```

`group(...)` names the document. `pathsToMatch(...)` specifies which paths are included in the group. You can use `packagesToScan(...)` to constrain by controller package, or combine filter criteria aligned with how the application is structured.

An endpoint can appear in multiple groups if group filter criteria overlap. This is valid behavior when you want the same operation presented across multiple documents. To prevent overlap, design non-overlapping path or package scopes.

## 3. Attaching `OpenApiCustomizer` Directly to a Group

To modify metadata for a single group only, use `.addOpenApiCustomizer(...)` on that group's builder.

```java
import io.swagger.v3.oas.models.info.Info;
import org.springdoc.core.models.GroupedOpenApi;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class ApiGroupConfiguration {

    @Bean
    GroupedOpenApi publicApi() {
        return GroupedOpenApi.builder()
            .group("public")
            .pathsToMatch("/api/public/**")
            .addOpenApiCustomizer(openApi -> {
                Info info = openApi.getInfo();
                if (info == null) {
                    info = new Info();
                    openApi.setInfo(info);
                }
                info.setTitle("Public API");
                info.setVersion("1.0.0");
                info.setDescription("API contract for client applications.");
            })
            .build();
    }
}
```

The customizer receives the `OpenAPI` model built by Springdoc for the group. You can edit `Info`, add `Server`, `Tag`, `SecurityScheme`, extensions, or adjust other parts of the document.

In this example, the customizer only changes `info` on the `public` group. Other groups do not receive this title or version unless they attach the same customizer or a global customizer modifies those fields.

If `Info` was already populated from `@OpenAPIDefinition` or an `OpenAPI` bean, the code above preserves other properties and updates only title, version, and description. Replacing the entire object via `openApi.setInfo(new Info()...)` could discard prior metadata such as contact, license, or terms of service.

## 4. Distinguishing Customizers by Scope

Springdoc offers several extension points. Pick the one matching your change scope:

| Mechanism | Scope | When to Use |
|---|---|---|
| `.addOpenApiCustomizer(...)` on `GroupedOpenApi.Builder` | Only the configured group's document | Group-specific metadata, servers, security, or components |
| `.addOperationCustomizer(...)` on `GroupedOpenApi.Builder` | Operations belonging to the configured group | Adjusting summary, description, tags, or parameters per handler in one group |
| `OpenApiCustomizer` bean | Default OpenAPI document, not a way to target all groups | Customizing an ungrouped document |
| `GlobalOpenApiCustomizer` bean | Default document and all groups | Rules genuinely shared across every document |
| `OperationCustomizer` bean | Operations of the default document | Shared operation logic for the default document |
| `GlobalOperationCustomizer` bean | Operations in the default document and all groups | Operation rules genuinely shared across every document |

If you only want to change the title for the `admin` group, attach the customizer inside the `adminApi()` builder. Do not create a generic `OpenApiCustomizer` bean and inspect group names assuming it runs for only one group.

If you want to add a shared extension or rule to every document, use `GlobalOpenApiCustomizer`; if you want operation-level logic across every document, use `GlobalOperationCustomizer`. When both global and group-specific customizers exist, verify the final output because a customizer running later can overwrite fields set earlier.

Customizer APIs and packages can vary across Springdoc versions. Examples here target Springdoc v2; consult the Javadoc for your project's exact dependency version when upgrading.

## 5. Customizing Server URLs Per Group

Groups can be published through different server URLs. For example, public documentation uses the public API gateway while admin documentation uses an internal hostname.

```java
import java.util.List;
import io.swagger.v3.oas.models.servers.Server;
import org.springdoc.core.models.GroupedOpenApi;
import org.springframework.context.annotation.Bean;

@Bean
GroupedOpenApi adminApi() {
    return GroupedOpenApi.builder()
        .group("admin")
        .pathsToMatch("/api/admin/**")
        .addOpenApiCustomizer(openApi -> openApi.setServers(List.of(
            new Server()
                .url("https://admin-api.example.com")
                .description("Administrative API")
        )))
        .build();
}
```

`setServers(...)` replaces the document's server list with the supplied list. If you want to keep existing servers and append another, use `addServersItem(...)` instead of replacing the entire list.

Server URLs in documentation must be URLs clients can actually reach in the corresponding environment. Do not leave internal hostnames or test URLs in public documentation if external clients cannot reach them. When running behind a reverse proxy or context path, verify that public URLs and document paths combine properly.

## 6. Customizing Security Per Group

A common scenario is that the public group requires no document-level login, whereas the admin group requires a Bearer token. You can declare the security scheme and security requirement inside the admin group's customizer.

```java
import org.springdoc.core.models.GroupedOpenApi;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import io.swagger.v3.oas.models.Components;
import io.swagger.v3.oas.models.security.SecurityRequirement;
import io.swagger.v3.oas.models.security.SecurityScheme;

@Configuration
class AdminOpenApiConfiguration {

@Bean
GroupedOpenApi adminApi() {
    return GroupedOpenApi.builder()
        .group("admin")
        .pathsToMatch("/api/admin/**")
        .addOpenApiCustomizer(openApi -> {
            Components components = openApi.getComponents();
            if (components == null) {
                components = new Components();
                openApi.setComponents(components);
            }

            components.addSecuritySchemes(
                "bearerAuth",
                new SecurityScheme()
                    .type(SecurityScheme.Type.HTTP)
                    .scheme("bearer")
                    .bearerFormat("JWT")
            );

            openApi.addSecurityItem(
                new SecurityRequirement().addList("bearerAuth")
            );
        })
        .build();
}
}
```

The admin document will include `components.securitySchemes.bearerAuth` and a document-level security requirement. Operations inherit the Bearer requirement unless overridden by operation-level security.

If an operation in the admin group is genuinely public, you can declare empty security for that operation via an annotation or appropriate operation customizer. OpenAPI uses `security: []` to clear inherited document-level security requirements.

Note: security in OpenAPI only describes the contract for Swagger UI and client tools. It does not configure Spring Security. Protect both the admin API and the `/v3/api-docs/admin` documentation endpoint according to runtime policy. Showing an Authorize button in Swagger UI does not mean the server validates tokens.

## 7. Customizing Operations Within One Group

If only certain operations in a group need extra metadata, use `.addOperationCustomizer(...)`. The customizer receives `Operation` along with `HandlerMethod`, so it can inspect method annotations or metadata to decide on changes.

Example creating a marker annotation for operations needing internal descriptions:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
public @interface AdminOperation {
    String description();
}
```

Controller using the annotation:

```java
import java.util.List;
import org.springframework.web.bind.annotation.GetMapping;

@GetMapping("/reports")
@AdminOperation(description = "Retrieve reports for administrators.")
List<ReportResponse> reports() {
    return reportService.findReports();
}
```

Attaching the customizer to the admin group:

```java
import org.springdoc.core.customizers.OperationCustomizer;
import org.springdoc.core.models.GroupedOpenApi;
import org.springframework.context.annotation.Bean;

@Bean
GroupedOpenApi adminApi() {
    return GroupedOpenApi.builder()
        .group("admin")
        .pathsToMatch("/api/admin/**")
        .addOperationCustomizer((operation, handlerMethod) -> {
            AdminOperation marker = handlerMethod.getMethod()
                .getAnnotation(AdminOperation.class);

            if (marker != null) {
                operation.setDescription(marker.description());
                operation.addTagsItem("Administration");
            }
            return operation;
        })
        .build();
}
```

In this example, the changes apply only to operations in the admin group. If a method lacks `@AdminOperation`, the operation keeps whatever metadata Springdoc infers or reads from Swagger annotations.

Do not use customizers to change URLs, HTTP methods, or runtime behavior. `OperationCustomizer` only edits the OpenAPI model; Spring mappings still govern actual requests.

## 8. Combining Group Filters and Customizers

A group typically combines filter criteria and customizers. For example, the admin group selects only endpoints in the admin package under `/api/admin/**`, then attaches dedicated metadata.

```java
import io.swagger.v3.oas.models.info.Info;
import org.springdoc.core.models.GroupedOpenApi;
import org.springframework.context.annotation.Bean;

@Bean
GroupedOpenApi adminApi() {
    return GroupedOpenApi.builder()
        .group("admin")
        .packagesToScan("com.example.admin.web")
        .pathsToMatch("/api/admin/**")
        .pathsToExclude("/api/admin/internal/**")
        .addOpenApiCustomizer(openApi -> {
            Info info = openApi.getInfo();
            if (info != null) {
                info.setTitle("Administration API");
                info.setVersion("1.0.0");
            }
        })
        .build();
}
```

In this configuration:

- `packagesToScan` limits which controller package is considered.
- `pathsToMatch` limits which paths enter the document.
- `pathsToExclude` removes internal paths from the document.
- `addOpenApiCustomizer` updates document metadata after Springdoc builds it.

Filters and customizers have distinct responsibilities. Filters choose which operations appear; customizers adjust how the document or operations are described. If a customizer manually adds new paths to the model, it can push the document beyond the original filter scope; do so only intentionally and with explicit tests.

## 9. Configuring Swagger UI to Select the Right Group

After creating groups, add document URLs to the Swagger UI list:

```yaml
springdoc:
  swagger-ui:
    urls:
      - name: Public API
        url: /v3/api-docs/public
      - name: Administration API
        url: /v3/api-docs/admin
      - name: Internal API
        url: /v3/api-docs/internal
    urls-primary-name: Public API
```

Swagger UI displays the list of documents for users to pick from. `urls-primary-name` chooses which group opens by default from the list. If there is only one document, configuring `urls` is unnecessary.

The `name` value is the UI display label, while `url` is the documentation endpoint. Display names do not have to match group IDs, but URLs must exactly match the group names declared via `.group(...)`.

If Swagger UI and API Docs sit behind a gateway or context path, use matching relative URLs or public paths. When the UI reports failure to load a document, open `/v3/api-docs/{group}` directly to separate document-generation issues from UI configuration issues.

## 10. Separating Shared Customizers and Group-Specific Customizers

In multi-group applications, you may have shared organization metadata such as contact, license, or extensions alongside per-group metadata. Keep the two scopes separate.

Global customizer example:

```java
import io.swagger.v3.oas.models.info.Info;
import org.springdoc.core.customizers.GlobalOpenApiCustomizer;
import io.swagger.v3.oas.models.info.Contact;
import org.springframework.context.annotation.Bean;

@Bean
GlobalOpenApiCustomizer organizationMetadata() {
    return openApi -> {
        Info info = openApi.getInfo();
        if (info == null) {
            info = new Info();
            openApi.setInfo(info);
        }
        info.setContact(new Contact()
            .name("API Platform Team")
            .email("api-platform@example.com"));
    };
}
```

This customizer applies contact metadata to the default document and all groups. Group-specific customizers can then set distinct titles, versions, or descriptions.

For example, the `admin` group updates only title and version in the customizer attached directly to its builder. The contact set by the global customizer stays intact because the code touches only those two fields.

When multiple customizers modify the same field, the final value depends on execution order. Avoid having global and group-specific customizers overwrite the same field without clear conventions. If ordering is needed, use the ordering mechanism supported by Spring in your running version and test the resulting output.

## 11. Reusing Configuration While Preserving Clear Scope

If multiple groups share similar customization logic, extract a plain Java helper method and invoke it from each group's builder. This reuses logic while keeping explicit which groups register it.

```java
import io.swagger.v3.oas.models.info.Contact;
import io.swagger.v3.oas.models.info.Info;
import org.springdoc.core.customizers.OpenApiCustomizer;
import org.springdoc.core.models.GroupedOpenApi;
import org.springframework.context.annotation.Bean;

private OpenApiCustomizer apiContact(String teamName, String email) {
    return openApi -> {
        Info info = openApi.getInfo();
        if (info == null) {
            info = new Info();
            openApi.setInfo(info);
        }
        info.setContact(new Contact().name(teamName).email(email));
    };
}

@Bean
GroupedOpenApi publicApi() {
    return GroupedOpenApi.builder()
        .group("public")
        .pathsToMatch("/api/public/**")
        .addOpenApiCustomizer(apiContact("Public API Team", "public@example.com"))
        .build();
}

@Bean
GroupedOpenApi adminApi() {
    return GroupedOpenApi.builder()
        .group("admin")
        .pathsToMatch("/api/admin/**")
        .addOpenApiCustomizer(apiContact("Admin API Team", "admin@example.com"))
        .build();
}
```

In this example, each group passes its own metadata. Never register a customizer as a global bean if the goal is to apply it only to select groups.

## 12. Verifying Each Group's Document

Do not rely solely on visually checking Swagger UI. Call each OpenAPI endpoint directly and inspect `info`, `servers`, `security`, `paths`, and operation metadata.

For example:

```bash
curl -s http://localhost:8080/v3/api-docs/public | jq '.info, .servers, (.paths | keys)'
curl -s http://localhost:8080/v3/api-docs/admin | jq '.info, .servers, .security, (.paths | keys)'
```

Check these conditions:

- The public document has the expected title/version and public endpoints.
- The admin document has its own title/version and contains the right administrative paths.
- Security schemes are defined before security requirements reference them.
- Server URLs match the group's published environment.
- Targeted operations are adjusted by customizers; unrelated operations remain untouched.
- No internal paths or sensitive operations leak into the public group.

When combining `pathsToMatch` and `packagesToScan`, verify the actual filter outcome via the `paths` list. Do not infer inclusion solely from package names.

## 13. Testing Groups with MockMvc

You can verify each document in integration tests. The example below assumes `public` and `admin` groups are configured:

```java
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
class ApiGroupDocumentationTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void publicDocumentContainsOnlyPublicApiMetadataAndPaths() throws Exception {
        mockMvc.perform(get("/v3/api-docs/public"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.info.title").value("Public API"))
            .andExpect(jsonPath("$.paths['/api/public/orders']").exists())
            .andExpect(jsonPath("$.paths['/api/admin/users']").doesNotExist());
    }

    @Test
    void adminDocumentContainsAdminSecurity() throws Exception {
        mockMvc.perform(get("/v3/api-docs/admin"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.info.title").value("Administration API"))
            .andExpect(jsonPath("$.components.securitySchemes.bearerAuth").exists())
            .andExpect(jsonPath("$.security[0].bearerAuth").exists());
    }
}
```

If API Docs endpoints are protected by Spring Security, tests must authenticate or use an appropriate test security setup. Never open documentation endpoints in production just to simplify tests. For tests involving customizers that depend on beans or profiles, run with a configuration close to the deployment environment.

## 14. Common Mistakes When Customizing Per Group

| Symptom | Possible Cause | Resolution |
|---|---|---|
| Admin title appears in public document | Broad-scope customizer bean or `GlobalOpenApiCustomizer` used for group-specific metadata | Attach the customizer directly to the admin group builder |
| Customizer never runs for a group | Registered an `OpenApiCustomizer` bean expecting it to apply to all groups | Use `.addOpenApiCustomizer(...)` or `GlobalOpenApiCustomizer` as appropriate |
| Group contains unwanted paths | Overlapping filters or overly broad package/path match | Narrow `pathsToMatch`, `pathsToExclude`, and `packagesToScan` |
| Admin group lacks security scheme | Added security requirement without defining scheme in components | Declare `components.securitySchemes` in the same document |
| Swagger UI does not show group | Incorrect URL in `swagger-ui.urls` or mismatched group ID | Call `/v3/api-docs/{group}` directly and fix the URL |
| Contact or license disappeared | Customizer replaced the entire `Info` object | Update only needed fields on the existing `Info` |
| Global customizer overwrote group title | Multiple customizers modify the same field | Assign clear field ownership and execution order |
| Admin docs are publicly accessible | Confusing document grouping with runtime security | Secure API Docs and APIs with Spring Security |
| Behavior changed after upgrade | Customizer APIs or packages changed across versions | Check Javadoc and re-test each group |

## 15. Principles for Designing Group-Specific Customizers

- Place customizers close to the `GroupedOpenApi` declaration so scope is immediately visible.
- Use `addOpenApiCustomizer` for document-level changes and `addOperationCustomizer` for operation-level changes.
- Use `GlobalOpenApiCustomizer` only for rules genuinely shared across all documents.
- Do not rely on a plain `OpenApiCustomizer` bean to customize all groups.
- Modify individual `Info` fields when preserving declared contact, license, or other metadata.
- Declare security schemes before adding security requirements that reference them.
- Never treat groups as runtime security boundaries or versioning mechanisms.
- Keep group filters crisp and verify overlapping paths.
- Use accurate URLs in `springdoc.swagger-ui.urls`.
- Test every `/v3/api-docs/{group}` endpoint directly after any change.

## 16. Pre-Publication Checklist for Multi-Group Documentation

- [ ] Each group has a stable name and clear purpose.
- [ ] `pathsToMatch`, `pathsToExclude`, and `packagesToScan` reflect the intended scope.
- [ ] Group-specific metadata is attached directly via customizers on the right builder.
- [ ] Global customizers contain only genuinely shared information.
- [ ] No broad customizer accidentally overwrites group-specific metadata.
- [ ] `servers`, `security`, tags, and components match the group's audience.
- [ ] Swagger UI lists accurate document URLs and display names.
- [ ] API Docs and runtime API endpoints are protected per actual policy.
- [ ] Every group is verified directly via HTTP or integration tests.
- [ ] Impact of Springdoc upgrades has been checked.

Group-specific customizations should be attached directly to the corresponding `GroupedOpenApi`. `.addOpenApiCustomizer(...)` modifies a single group's document; `.addOperationCustomizer(...)` modifies operations within that group. `GlobalOpenApiCustomizer` beans apply shared rules across all documents, while plain `OpenApiCustomizer` beans serve the default document. Keeping these scopes distinct ensures every document carries the metadata, servers, and security tailored to its audience without altering runtime controller behavior.

## References

- [Springdoc OpenAPI – Official documentation](https://springdoc.org/)
- [Springdoc OpenAPI – FAQ](https://springdoc.org/faq.html)
- [Springdoc OpenAPI – GitHub repository](https://github.com/springdoc/springdoc-openapi)
- [Swagger Core – OpenAPI model classes](https://github.com/swagger-api/swagger-core)
