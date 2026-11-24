# Scope of Default Customizers and Group-Attached Customizers

Springdoc can generate a default OpenAPI document as well as multiple separate documents through `GroupedOpenApi`. When you need to add metadata, servers, security schemes, extensions, or adjust operations, customizers are a key extension point. However, a customizer's execution scope depends on how it is registered: a regular `OpenApiCustomizer` bean serves the default document; `GlobalOpenApiCustomizer` applies to the default document and groups; and a customizer attached directly to `GroupedOpenApi.Builder` serves only that group.

Clearly distinguishing these three scopes prevents two common mistakes: changes intended for one group leaking into another document, or a customizer assumed to apply to groups actually running only on `/v3/api-docs`.

## 1. Default Document and Group Documents

When an application uses Springdoc without declaring groups, the default documentation endpoint is typically:

```text
/v3/api-docs
```

When `GroupedOpenApi` is declared, each group has its own document. Example:

```java
import org.springdoc.core.models.GroupedOpenApi;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class ApiGroupsConfiguration {

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

The corresponding documentation URLs are typically:

| Document | Default URL |
|---|---|
| Default OpenAPI | `/v3/api-docs` |
| Public group | `/v3/api-docs/public` |
| Admin group | `/v3/api-docs/admin` |

If `springdoc.api-docs.path` is changed, the base URLs change accordingly. A group only creates a document with a filtered scope of operations; it does not create business routes and does not enforce authorization itself.

Crucial point: the default document and group documents are separate documents. A customizer that runs on the default document does not automatically run on all group documents.

## 2. Three Ways to Register Customizers and Their Scopes

Springdoc provides three main ways to customize an OpenAPI document:

| Registration Method | Scope | When to Use |
|---|---|---|
| `OpenApiCustomizer` bean | Default document at `/v3/api-docs` | Metadata or changes meant only for the default document |
| `GlobalOpenApiCustomizer` bean | Default document and every document created from `GroupedOpenApi` | Rules truly shared across all documents |
| `.addOpenApiCustomizer(...)` on `GroupedOpenApi.Builder` | Only the document of the group being configured | Title, servers, security, or metadata specific to one group |

All three use logic that customizes an `OpenAPI` model, but their scope of application differs. Do not choose based solely on the interface name; choose based on which documents need to receive the changes.

### `OpenApiCustomizer` bean: default document only

Example:

```java
import io.swagger.v3.oas.models.OpenAPI;
import io.swagger.v3.oas.models.info.Info;
import org.springdoc.core.customizers.OpenApiCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class DefaultOpenApiConfiguration {

    @Bean
    OpenApiCustomizer defaultDocumentCustomizer() {
        return openApi -> {
            Info info = openApi.getInfo();
            if (info == null) {
                info = new Info();
                openApi.setInfo(info);
            }

            info.setDescription("Default OpenAPI documentation of the application.");
            openApi.addExtension("x-document-scope", "default");
        };
    }
}
```

Springdoc applies this bean to the default document. If the application has `public` and `admin` groups, do not expect the description or extension above to automatically appear in `/v3/api-docs/public` and `/v3/api-docs/admin`.

This is a good fit when the default document represents the entire API or a consolidated contract, while groups need their own metadata.

### `GlobalOpenApiCustomizer` bean: default document and all groups

If a rule must apply to every document, use `GlobalOpenApiCustomizer`:

```java
import org.springdoc.core.customizers.GlobalOpenApiCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class GlobalOpenApiConfiguration {

    @Bean
    GlobalOpenApiCustomizer organizationCustomizer() {
        return openApi -> openApi.addExtension(
            "x-organization",
            "Example Platform"
        );
    }
}
```

The `x-organization` extension will be added to the default document and all group documents. Global customizers can be used to add owner information, compliance standards, system codes, or shared metadata.

Do not use a global customizer for data belonging to only one group. For example, if only admin has an internal server or specific security requirement, place that logic on the admin group's builder.

### Customizer attached directly to one group

When only the admin group needs to change its title and server, attach the customizer in that group's builder:

```java
import java.util.List;
import io.swagger.v3.oas.models.info.Info;
import io.swagger.v3.oas.models.servers.Server;
import org.springdoc.core.models.GroupedOpenApi;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class AdminApiConfiguration {

    @Bean
    GroupedOpenApi adminApi() {
        return GroupedOpenApi.builder()
            .group("admin")
            .pathsToMatch("/api/admin/**")
            .addOpenApiCustomizer(openApi -> {
                Info info = openApi.getInfo();
                if (info == null) {
                    info = new Info();
                    openApi.setInfo(info);
                }
                info.setTitle("Administration API");
                info.setVersion("1.0.0");
                info.setDescription("API contract for the administration interface.");

                openApi.setServers(List.of(
                    new Server()
                        .url("https://admin-api.example.com")
                        .description("Administration API server")
                ));
            })
            .build();
    }
}
```

This customizer is tied to the `admin` group. The `public` group and default document do not receive this custom title or server, unless another customizer modifies them as well.

If you want to keep existing servers and append a new one, use `addServersItem(...)` instead of `setServers(...)`, since `setServers(...)` replaces the entire list.

## 3. When Multiple Customizer Types Coexist

An application can register all three approaches simultaneously:

```java
import org.springdoc.core.customizers.OpenApiCustomizer;
import org.springdoc.core.customizers.GlobalOpenApiCustomizer;
import org.springdoc.core.models.GroupedOpenApi;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class OpenApiCustomizationConfiguration {

    @Bean
    OpenApiCustomizer defaultDocumentCustomizer() {
        return openApi -> openApi.addExtension(
            "x-default-document",
            true
        );
    }

    @Bean
    GlobalOpenApiCustomizer globalDocumentCustomizer() {
        return openApi -> openApi.addExtension(
            "x-platform-owner",
            "API Platform Team"
        );
    }

    @Bean
    GroupedOpenApi adminApi() {
        return GroupedOpenApi.builder()
            .group("admin")
            .pathsToMatch("/api/admin/**")
            .addOpenApiCustomizer(openApi -> openApi.addExtension(
                "x-audience",
                "administrators"
            ))
            .build();
    }

    @Bean
    GroupedOpenApi publicApi() {
        return GroupedOpenApi.builder()
            .group("public")
            .pathsToMatch("/api/public/**")
            .build();
    }
}
```

Scope outcome:

| Document | `x-default-document` | `x-platform-owner` | `x-audience` |
|---|---|---|---|
| `/v3/api-docs` | Yes | Yes | No |
| `/v3/api-docs/admin` | No | Yes | Yes |
| `/v3/api-docs/public` | No | Yes | No |

The table above shows the registration scope of each customizer. It does not represent execution order. If multiple customizers modify the same field, the final result may depend on the order in which Springdoc and Spring apply them. For maintainability, give each field one primary source of ownership or use distinct fields/extensions for each scope.

## 4. Distinguishing OpenAPI Customizers and Operation Customizers

In addition to document-level customizers, Springdoc supports operation-level customizers. They differ in the object being modified:

| Interface or Builder Method | Received Object | Scope |
|---|---|---|
| `OpenApiCustomizer` bean | `OpenAPI` | Default document |
| `GlobalOpenApiCustomizer` bean | `OpenAPI` | Default document and groups |
| `OperationCustomizer` bean | `Operation` and `HandlerMethod` | Operations in the default document |
| `GlobalOperationCustomizer` bean | `Operation` and `HandlerMethod` | Operations in the default document and groups |
| `.addOpenApiCustomizer(...)` | `OpenAPI` | Document of the configured group |
| `.addOperationCustomizer(...)` | `Operation` and `HandlerMethod` | Operations belonging to the configured group |

Example of an `OperationCustomizer` bean for the default document only:

```java
import org.springdoc.core.customizers.OperationCustomizer;
import org.springframework.context.annotation.Bean;

@Bean
OperationCustomizer defaultOperationCustomizer() {
    return (operation, handlerMethod) -> {
        operation.addExtension("x-reviewed", true);
        return operation;
    };
}
```

If you want to apply an operation rule to both the default document and all groups, use `GlobalOperationCustomizer`. If you only want to modify operations in one group, use `.addOperationCustomizer(...)` on that group's builder.

Example where the admin group attaches a tag only to marked methods:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import org.springdoc.core.models.GroupedOpenApi;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
@interface AdminOnly {
}

@Configuration
class AdminOperationConfiguration {

    @Bean
    GroupedOpenApi adminApi() {
        return GroupedOpenApi.builder()
            .group("admin")
            .pathsToMatch("/api/admin/**")
            .addOperationCustomizer((operation, handlerMethod) -> {
                if (handlerMethod.getMethod().isAnnotationPresent(AdminOnly.class)) {
                    operation.addTagsItem("Administration");
                }
                return operation;
            })
            .build();
    }
}
```

`OperationCustomizer` only modifies the operation's descriptive model. It does not add mappings, change HTTP methods, or grant permissions to that method.

## 5. Customizing Shared Metadata While Preserving Specific Details

A common mistake is replacing the entire `Info` object in a shared customizer:

```java
openApi.setInfo(new Info().title("Company API"));
```

If the document already has `version`, `description`, `contact`, or `license`, the operation above can wipe out those fields. When you only want to add one property, modify the existing object:

```java
import io.swagger.v3.oas.models.info.Contact;
import io.swagger.v3.oas.models.info.Info;
import org.springdoc.core.customizers.GlobalOpenApiCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class CommonMetadataConfiguration {

    @Bean
    GlobalOpenApiCustomizer contactCustomizer() {
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
}
```

You can set the contact in `GlobalOpenApiCustomizer` so every document shares the same contact details. Then, a group-specific customizer only changes the group's title, description, or server without erasing the shared contact.

## 6. Combining Default Customizers with `GroupedOpenApi`

The full example below shows a default document, a public group, and an admin group coexisting:

```java
import io.swagger.v3.oas.models.info.Info;
import org.springdoc.core.customizers.GlobalOpenApiCustomizer;
import org.springdoc.core.customizers.OpenApiCustomizer;
import org.springdoc.core.models.GroupedOpenApi;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class OpenApiConfiguration {

    @Bean
    OpenApiCustomizer defaultCustomizer() {
        return openApi -> {
            Info info = openApi.getInfo();
            if (info != null) {
                info.setDescription("Consolidated application documentation.");
            }
        };
    }

    @Bean
    GlobalOpenApiCustomizer globalCustomizer() {
        return openApi -> openApi.addExtension("x-platform", "springdoc");
    }

    @Bean
    GroupedOpenApi publicApi() {
        return GroupedOpenApi.builder()
            .group("public")
            .pathsToMatch("/api/public/**")
            .addOpenApiCustomizer(openApi -> {
                if (openApi.getInfo() != null) {
                    openApi.getInfo().setTitle("Public API");
                }
            })
            .build();
    }

    @Bean
    GroupedOpenApi adminApi() {
        return GroupedOpenApi.builder()
            .group("admin")
            .pathsToMatch("/api/admin/**")
            .addOpenApiCustomizer(openApi -> {
                if (openApi.getInfo() != null) {
                    openApi.getInfo().setTitle("Administration API");
                }
            })
            .build();
    }
}
```

According to registration scope:

- `/v3/api-docs` receives `defaultCustomizer` and `globalCustomizer`.
- `/v3/api-docs/public` receives `globalCustomizer` and the customizer attached to the public group.
- `/v3/api-docs/admin` receives `globalCustomizer` and the customizer attached to the admin group.

Therefore, the description “Consolidated application documentation.” belongs only to the default document; each group's title is set on its respective builder; and the `x-platform` extension appears in every document.

## 7. Customizer Scope Is Not Security Scope

Splitting documents by group or assigning separate customizers does not protect endpoints on its own. For example, a customizer can add `security` to the admin document, but the server still needs Spring Security to authenticate and authorize actual requests.

Similarly, the `/v3/api-docs/admin` document may expose administrative paths even when the runtime API is already secured. If policy requires admin documentation to be available only to internal users, protect the corresponding API Docs endpoint and Swagger UI with security configuration. Never rely on a customizer or group name as an access boundary.

## 8. Verifying Customizers Ran on the Right Documents

After starting the application, call each documentation endpoint directly. Example:

```bash
curl -s http://localhost:8080/v3/api-docs | jq '.info, .["x-document-scope"], .["x-platform-owner"]'
curl -s http://localhost:8080/v3/api-docs/admin | jq '.info, .["x-platform-owner"], .["x-audience"]'
curl -s http://localhost:8080/v3/api-docs/public | jq '.info, .["x-platform-owner"], .["x-audience"]'
```

When diagnosing issues, check separately:

1. Whether the URL being called is the default document or a group document.
2. Whether the customizer is registered as an `OpenApiCustomizer` bean, a `GlobalOpenApiCustomizer` bean, or a builder method.
3. Whether the group has the right `group` name and filters.
4. Whether the value to check is at the document level (`info`, `servers`, `components`) or operation level (`paths`).
5. Whether another customizer modifies the same field afterward.

Do not rely solely on observing Swagger UI. The UI might be loading a different group URL or holding a browser cache. Calling the JSON/YAML endpoints directly determines which document a customizer modified.

### Testing Scope with MockMvc

You can test the presence/absence of metadata in each document:

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
class OpenApiCustomizerScopeTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void defaultCustomizerOnlyChangesDefaultDocument() throws Exception {
        mockMvc.perform(get("/v3/api-docs"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.info.description")
                .value("Consolidated application documentation."));

        mockMvc.perform(get("/v3/api-docs/admin"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.info.description").doesNotExist());
    }

    @Test
    void globalAndGroupCustomizersApplyToAdminDocument() throws Exception {
        mockMvc.perform(get("/v3/api-docs/admin"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.info.title").value("Administration API"))
            .andExpect(jsonPath("$['x-platform']").value("springdoc"));
    }
}
```

Assertions must match the metadata the application actually configures. If API Docs is protected by Spring Security, tests should supply appropriate authentication rather than opening the endpoint in production.

## 9. Common Misconceptions

| Symptom | Cause | Resolution |
|---|---|---|
| `OpenApiCustomizer` bean does not change group documents | This bean applies to the default document | Use `GlobalOpenApiCustomizer` or `.addOpenApiCustomizer(...)` on the group |
| Admin group metadata appears in public document | Change was registered with a global customizer | Move the logic to the admin group's builder |
| Group customizer does not affect `/v3/api-docs` | Builder customizers are attached only to the group | Register a separate `OpenApiCustomizer` if the default document also needs the change |
| Operation customizer does not run on groups | Used `OperationCustomizer` bean instead of `GlobalOperationCustomizer` or builder method | Choose the right operation scope |
| Title or contact is lost | Replaced the entire `Info` object | Update only needed fields on the existing object |
| Different results with multiple customizers | Multiple customizers modify the same field or execution order differs | Separate responsibilities and inspect the final document |
| Security in document yet API remains open | Confused OpenAPI metadata with runtime authorization | Configure Spring Security independently |
| Swagger UI shows stale results | UI loads wrong group URL or caches | Call the documentation endpoint directly and check the UI URL |

## 10. Rules for Choosing Scope

- Use an `OpenApiCustomizer` bean when only the default document needs changes.
- Use a `GlobalOpenApiCustomizer` bean when every document needs the same rule.
- Use `.addOpenApiCustomizer(...)` when changes belong to only one group.
- Use an `OperationCustomizer` bean for operations in the default document.
- Use `GlobalOperationCustomizer` for operation rules across the default document and groups.
- Use `.addOperationCustomizer(...)` for operations belonging to a specific group.
- Do not let a global customizer overwrite fields that require per-group values.
- Do not replace an entire metadata object when only a single field needs updating.
- Inspect the JSON/YAML of the default document and each group directly after making changes.

## 11. Pre-Release Checklist for Customizer Configuration

- [ ] Identified target documents: default, a single group, or all groups.
- [ ] Selected the right `OpenApiCustomizer`, `GlobalOpenApiCustomizer`, or builder customizer.
- [ ] If modifying operations, selected the right `OperationCustomizer`, `GlobalOperationCustomizer`, or `.addOperationCustomizer(...)`.
- [ ] Group-specific customizers are attached to the right `GroupedOpenApi`.
- [ ] Global customizers contain only shared rules.
- [ ] Customizers do not unintentionally overwrite each other's metadata.
- [ ] `Info`, `Servers`, and `Components` are updated without losing unrelated fields.
- [ ] Verified `/v3/api-docs` and each `/v3/api-docs/{group}`.
- [ ] Confirmed group filters include the right operations in each document.
- [ ] Verified documentation endpoint security and runtime API security independently.

Customizer scope is determined by how it is registered. An `OpenApiCustomizer` bean affects the default document; a `GlobalOpenApiCustomizer` bean affects the default document and groups; `.addOpenApiCustomizer(...)` affects only the configured group. Corresponding options exist for operations as well. When you clearly identify the target document before writing a customizer and verify each document URL afterward, changes appear exactly where intended without leaking into other API contracts.

## References

- [Springdoc OpenAPI – Official documentation](https://springdoc.org/)
- [Springdoc OpenAPI v2 – FAQ](https://springdoc.org/v2/#faq)
- [Springdoc OpenAPI – FAQ](https://springdoc.org/faq.html)
- [Springdoc OpenAPI – GitHub repository](https://github.com/springdoc/springdoc-openapi)
- [Springdoc – `SpringDocConfiguration` customizer registration](https://github.com/springdoc/springdoc-openapi/blob/main/springdoc-openapi-starter-common/src/main/java/org/springdoc/core/configuration/SpringDocConfiguration.java)
- [Springdoc – `GlobalOpenApiCustomizer` API](https://javadoc.io/doc/org.springdoc/springdoc-openapi-starter-common/latest/org/springdoc/core/customizers/GlobalOpenApiCustomizer.html)
- [Springdoc – `OpenApiCustomizer` API](https://javadoc.io/doc/org.springdoc/springdoc-openapi-starter-common/latest/org/springdoc/core/customizers/OpenApiCustomizer.html)
