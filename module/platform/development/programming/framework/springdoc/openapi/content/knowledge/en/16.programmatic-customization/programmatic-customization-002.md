# OpenApiCustomizer for Document-Level Changes

springdoc-openapi can generate an OpenAPI document from controllers, DTOs, and annotations. When metadata must be computed per environment, shared across many endpoints, or added after the document has been generated, annotations on individual controllers may no longer be convenient. **OpenApiCustomizer** provides an extension point to modify the OpenAPI model at the entire document level.

With a customizer, an application can update the title and contact information, add server URLs, declare shared tags, and add security schemes, extensions, or other metadata. Changes can be applied to the default document, to a specific document group, or across multiple groups. A customizer only modifies the published specification; it does not by itself alter routes, access permissions, or Spring MVC request-handling behavior.

## 1. OpenApiCustomizer in the Document Generation Pipeline

~~~text
Spring MVC controllers + DTO + annotations
                  |
                  v
          springdoc scans API
                  |
                  v
        OpenAPI model is created
                  |
                  v
       OpenApiCustomizer callbacks
                  |
                  v
       OpenAPI JSON/YAML document
                  |
                  v
              Swagger UI
~~~

Springdoc scans mappings and metadata, then constructs the Java model of the OpenAPI specification. The customizer receives that model and can add, modify, or remove information before the document is exported.

In source code, a customizer is typically a lambda or a bean implementing the `OpenApiCustomizer` interface. The input object is `io.swagger.v3.oas.models.OpenAPI`, which is the document model rather than an active HTTP request.

## 2. What Is OpenApiCustomizer?

In Springdoc 2.x, the interface is usually imported from:

~~~java
import org.springdoc.core.customizers.OpenApiCustomizer;
~~~

It is a functional interface, so a customizer can be created with a lambda:

~~~java
OpenApiCustomizer metadataCustomizer = openApi -> {
    // Modify the OpenAPI model here.
};
~~~

`openApi` is the root object of the document. From it, you can access these components:

| Component | Purpose |
|---|---|
| `info` | API name, description, version, contact, license |
| `servers` | Server addresses that clients can call |
| `tags` | List of tags and tag descriptions at the document level |
| `paths` | Discovered paths and operations |
| `components` | Reusable schemas, responses, parameters, security schemes |
| `security` | Default security requirements at the document level |
| `externalDocs` | Links to supplementary documentation |
| `extensions` | Extended metadata following the `x-...` convention |

Customizers should be used for metadata or rules that truly belong at the document level. Descriptions specific to an individual operation, such as a summary, request parameters, or specific responses, should generally be placed via the corresponding annotations or `OperationCustomizer`.

## 3. Declaring OpenApiCustomizer as a Spring Bean

Springdoc can pick up an `OpenApiCustomizer` bean to customize the default OpenAPI document:

~~~java
import io.swagger.v3.oas.models.info.Info;
import org.springdoc.core.customizers.OpenApiCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class OpenApiConfiguration {

    @Bean
    OpenApiCustomizer documentMetadataCustomizer() {
        return openApi -> {
            Info info = openApi.getInfo();
            if (info == null) {
                info = new Info();
                openApi.setInfo(info);
            }

            info.setDescription(
                "API documentation for the store management system."
            );
        };
    }
}
~~~

The snippet only adds a description. If `Info` was already created from `@OpenAPIDefinition` or an `OpenAPI` bean, other properties such as title and version are preserved.

A regular `OpenApiCustomizer` bean applies to the default document. If you need to apply the same rule across document groups, see `GlobalOpenApiCustomizer`; if you only want to modify one group, attach the customizer to `GroupedOpenApi`.

## 4. Updating Info Without Losing Existing Metadata

`Info` holds API identification metadata. You can supplement description, terms of service, contact, and license:

~~~java
import io.swagger.v3.oas.models.info.Contact;
import io.swagger.v3.oas.models.info.Info;
import io.swagger.v3.oas.models.info.License;
import org.springdoc.core.customizers.OpenApiCustomizer;

@Bean
OpenApiCustomizer apiInfoCustomizer() {
    return openApi -> {
        Info info = openApi.getInfo();
        if (info == null) {
            info = new Info();
            openApi.setInfo(info);
        }

        info.setDescription(
            "API for looking up products, orders, and customers."
        );
        info.setTermsOfService("https://example.com/terms");

        Contact contact = info.getContact();
        if (contact == null) {
            contact = new Contact();
            info.setContact(contact);
        }
        contact.setName("API Support");
        contact.setEmail("api-support@example.com");
        contact.setUrl("https://example.com/support");

        License license = info.getLicense();
        if (license == null) {
            license = new License();
            info.setLicense(license);
        }
        license.setName("Internal API Terms");
        license.setUrl("https://example.com/api-license");
    };
}
~~~

The example checks nested objects before instantiating new ones to preserve metadata declared from other sources. If you want to override a single field, override that specific field rather than replacing the entire `Info` with a new object. This avoids accidentally erasing an already configured title, version, or contact.

Do not include personal contact details or internal URLs in public documentation if they are not permitted to be published.

## 5. Adding Environment-Specific Server URLs

`servers` specifies the base addresses clients use to call the API. An application may run on localhost, staging, and production with different base URLs.

Do not hardcode a production address in a customizer shared across all environments. Load the URL from configuration:

~~~yaml
app:
  openapi:
    server-url: https://api.example.com
~~~

The customizer reads the configuration using Spring `Environment` and adds the server if it is not already present:

~~~java
import io.swagger.v3.oas.models.servers.Server;
import java.util.ArrayList;
import org.springdoc.core.customizers.OpenApiCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.core.env.Environment;

@Bean
OpenApiCustomizer serverCustomizer(Environment environment) {
    String serverUrl = environment.getRequiredProperty(
        "app.openapi.server-url"
    );

    return openApi -> {
        if (openApi.getServers() == null) {
            openApi.setServers(new ArrayList<>());
        }

        boolean exists = openApi.getServers().stream()
            .anyMatch(server -> serverUrl.equals(server.getUrl()));

        if (!exists) {
            openApi.addServersItem(
                new Server()
                    .url(serverUrl)
                    .description("Server for the current environment.")
            );
        }
    };
}
~~~

Configuration can be overridden per profile:

~~~yaml
# application-local.yml
app:
  openapi:
    server-url: http://localhost:8080
~~~

~~~yaml
# application-prod.yml
app:
  openapi:
    server-url: https://api.example.com
~~~

If the application runs behind a reverse proxy or API gateway, the public server URL may differ from the address the application sees inside its container. Publish the URL that clients actually use. Configuring servers in OpenAPI does not automatically configure proxies, CORS, or gateway routing.

If you need to keep multiple servers for Swagger UI users to choose from, add multiple items intentionally. Avoid adding duplicate servers each time the customizer is applied; the example above checks the URL before adding.

## 6. Adding Document-Level Tags

Document-level tags describe operation group names and meanings. Shared tags can be added using a customizer:

~~~java
import io.swagger.v3.oas.models.tags.Tag;
import java.util.ArrayList;
import org.springdoc.core.customizers.OpenApiCustomizer;

@Bean
OpenApiCustomizer commonTagsCustomizer() {
    return openApi -> {
        if (openApi.getTags() == null) {
            openApi.setTags(new ArrayList<>());
        }

        boolean catalogExists = openApi.getTags().stream()
            .anyMatch(tag -> "Catalog".equals(tag.getName()));

        if (!catalogExists) {
            openApi.addTagsItem(
                new Tag()
                    .name("Catalog")
                    .description("Look up and manage products.")
            );
        }
    };
}
~~~

The document tag list defines tag metadata. Which tag an operation actually belongs to is still indicated in each operation's `tags` property, typically declared via `@Tag` or `@Operation(tags = ...)`.

The customizer above only adds the tag definition if that name does not already exist. It does not automatically attach the `Catalog` tag to all operations. If you want to assign tags based on paths or business rules, you can iterate over `paths` and operations, though consider using `OperationCustomizer` when the logic pertains only to operations.

## 7. Adding Components and Shared Schemas

`components` contains definitions that can be referenced from multiple operations. A customizer can add a shared schema when that schema is not inferred from a DTO:

~~~java
import io.swagger.v3.oas.models.Components;
import io.swagger.v3.oas.models.media.ObjectSchema;
import io.swagger.v3.oas.models.media.StringSchema;
import org.springdoc.core.customizers.OpenApiCustomizer;

@Bean
OpenApiCustomizer sharedSchemaCustomizer() {
    return openApi -> {
        if (openApi.getComponents() == null) {
            openApi.setComponents(new Components());
        }

        if (openApi.getComponents().getSchemas() == null
                || !openApi.getComponents().getSchemas()
                    .containsKey("CorrelationInfo")) {
            ObjectSchema schema = new ObjectSchema()
                .addProperty("requestId", new StringSchema()
                    .description("Request identifier."))
                .addProperty("traceId", new StringSchema()
                    .description("Trace identifier for log lookup."));

            openApi.getComponents().addSchemas("CorrelationInfo", schema);
        }
    };
}
~~~

The example adds the `CorrelationInfo` schema to `components.schemas`. A schema is only useful to clients when referenced from a request, response, or another component. Adding a schema to components does not automatically add fields to runtime DTOs.

If a schema corresponds to an actual Java type, prefer declaring a DTO and letting springdoc generate the schema. Use a customizer for schemas shared from external systems, metadata that cannot be inferred from Java types, or special documentation conventions.

## 8. Adding Document-Level Security Schemes

A customizer can be used to declare the authentication mechanisms supported by the API. For example, an API using HTTP Bearer with JWT:

~~~java
import io.swagger.v3.oas.models.Components;
import io.swagger.v3.oas.models.security.SecurityScheme;
import org.springdoc.core.customizers.OpenApiCustomizer;

@Bean
OpenApiCustomizer bearerSchemeCustomizer() {
    return openApi -> {
        if (openApi.getComponents() == null) {
            openApi.setComponents(new Components());
        }

        openApi.getComponents().addSecuritySchemes(
            "bearerAuth",
            new SecurityScheme()
                .type(SecurityScheme.Type.HTTP)
                .scheme("bearer")
                .bearerFormat("JWT")
                .description("Enter a valid access token.")
        );
    };
}
~~~

Defining a scheme tells clients how to send authentication credentials. To require this scheme across the entire document, you can add a security requirement:

~~~java
import io.swagger.v3.oas.models.security.SecurityRequirement;

openApi.addSecurityItem(
    new SecurityRequirement().addList("bearerAuth")
);
~~~

A document-level security requirement applies by default to operations in the document. Only add it if every operation requires a bearer token. If there are public endpoints, describe security per operation or use `@SecurityRequirement` accordingly to indicate exceptions.

Declaring security in OpenAPI only helps Swagger UI and client generators understand the authentication contract. It does not enable Spring Security, validate JWTs, or protect endpoints. Runtime enforcement still requires Spring Security configuration and independent testing.

## 9. Adding ExternalDocumentation and Extensions

`externalDocs` provides a link to more detailed documentation:

~~~java
import io.swagger.v3.oas.models.ExternalDocumentation;

openApi.setExternalDocs(
    new ExternalDocumentation()
        .description("API integration guide")
        .url("https://docs.example.com/api")
);
~~~

OpenAPI also supports vendor-defined extensions prefixed with `x-`. Example:

~~~java
Map<String, Object> extensions = openApi.getExtensions();
if (extensions == null) {
    extensions = new LinkedHashMap<>();
    openApi.setExtensions(extensions);
}
extensions.putIfAbsent("x-audience", "partner");
~~~

The example requires importing `java.util.LinkedHashMap` and `java.util.Map`. Extensions can carry metadata for gateways, documentation portals, or internal tooling. Generic OpenAPI tools may ignore extensions they do not understand; do not use extensions to replace standard fields such as `servers`, `security`, or `tags`.

If the document already has `externalDocs` or extensions from another customizer, check before overwriting to avoid losing metadata.

## 10. OpenApiCustomizer for a Document Group

When an application creates multiple documents using `GroupedOpenApi`, each group may need its own metadata. For example, partner documentation needs a different title, description, and server from public documentation:

~~~java
import io.swagger.v3.oas.models.info.Info;
import io.swagger.v3.oas.models.servers.Server;
import java.util.List;
import org.springdoc.core.customizers.OpenApiCustomizer;
import org.springdoc.core.models.GroupedOpenApi;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class PartnerOpenApiConfiguration {

    @Bean
    GroupedOpenApi partnerApi() {
        return GroupedOpenApi.builder()
            .group("partner")
            .pathsToMatch("/api/partner/**")
            .addOpenApiCustomizer(partnerDocumentCustomizer())
            .build();
    }

    private OpenApiCustomizer partnerDocumentCustomizer() {
        return openApi -> {
            Info info = openApi.getInfo();
            if (info == null) {
                info = new Info();
                openApi.setInfo(info);
            }
            info.setTitle("Partner API");
            info.setVersion("1.0.0");
            info.setDescription(
                "API for partner integration systems."
            );

            openApi.setServers(List.of(
                new Server()
                    .url("https://partner-api.example.com")
                    .description("Partner production API")
            ));
        };
    }
}
~~~

The customizer is attached directly via `addOpenApiCustomizer`, so the scope of changes is restricted to the `partner` group. If you need to keep servers already present from other configurations, add them with a duplicate check instead of calling `setServers` to replace the entire list.

This is the right choice when each group has its own metadata. Do not create a shared `OpenApiCustomizer` bean and assume it will automatically apply to every group.

## 11. GlobalOpenApiCustomizer Across Multiple Groups

Springdoc provides `GlobalOpenApiCustomizer` for changes that need to apply across documents, including groups. In Springdoc 2.x, the interface usually resides in:

~~~java
import org.springdoc.core.customizers.GlobalOpenApiCustomizer;
~~~

Example of adding shared metadata across documents:

~~~java
import io.swagger.v3.oas.models.info.Info;
import org.springdoc.core.customizers.GlobalOpenApiCustomizer;
import org.springframework.context.annotation.Bean;

@Bean
GlobalOpenApiCustomizer commonDocumentCustomizer() {
    return openApi -> {
        Info info = openApi.getInfo();
        if (info == null) {
            info = new Info();
            openApi.setInfo(info);
        }

        info.setTermsOfService("https://example.com/terms");
    };
}
~~~

`GlobalOpenApiCustomizer` can be used for server metadata, extensions, license info, or shared schemas when the rule is truly identical across documents. For groups with specific requirements, use `addOpenApiCustomizer` on the builder or a group-configured customizer.

The exact scope of application may depend on the springdoc version and how groups are created. After adding the bean, check the default document and each group to confirm the customizer appears in the right places. Avoid creating multiple customizers that overwrite the same field without a clear ordering convention.

## 12. Distinguishing OpenApiCustomizer and OperationCustomizer

The two interfaces have different scopes:

| Customizer | Received Object | Appropriate Scope |
|---|---|---|
| `OpenApiCustomizer` | Entire `OpenAPI` document | Metadata, servers, tags, components, security, external docs |
| `GlobalOpenApiCustomizer` | Entire `OpenAPI` document | Shared changes across group documents |
| `OperationCustomizer` | One `Operation` with `HandlerMethod` | Adjusting summary, description, parameters, or metadata per controller method |

For example, `OperationCustomizer` can add a response or tag to each operation based on a method annotation. If you need to change `Info`, `Servers`, or `Components` for the entire document, `OpenApiCustomizer` is the more appropriate abstraction.

Do not use a document-level customizer to implement overly detailed per-controller logic if annotations or `OperationCustomizer` express the rule more clearly.

## 13. Combining Multiple Changes in One Customizer

Related changes can be grouped into a single customizer for easier tracking:

~~~java
import io.swagger.v3.oas.models.OpenAPI;
import io.swagger.v3.oas.models.info.Contact;
import io.swagger.v3.oas.models.info.Info;
import io.swagger.v3.oas.models.servers.Server;
import java.util.ArrayList;
import org.springdoc.core.customizers.OpenApiCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.Environment;

@Configuration
public class ApiDocumentCustomizerConfiguration {

    @Bean
    OpenApiCustomizer apiDocumentCustomizer(Environment environment) {
        String serverUrl = environment.getRequiredProperty(
            "app.openapi.server-url"
        );
        return openApi -> customizeDocument(openApi, serverUrl);
    }

    private void customizeDocument(OpenAPI openApi, String serverUrl) {
        Info info = openApi.getInfo();
        if (info == null) {
            info = new Info();
            openApi.setInfo(info);
        }

        info.setDescription("Store management API.");

        Contact contact = info.getContact();
        if (contact == null) {
            contact = new Contact();
            info.setContact(contact);
        }
        contact.setName("API Support");
        contact.setEmail("api-support@example.com");

        if (openApi.getServers() == null) {
            openApi.setServers(new ArrayList<>());
        }

        boolean hasServer = openApi.getServers().stream()
            .anyMatch(server -> serverUrl.equals(server.getUrl()));

        if (!hasServer) {
            openApi.addServersItem(
                new Server()
                    .url(serverUrl)
                    .description("API server")
            );
        }
    }
}
~~~

A customizer can extract processing logic into separate methods for readability and testability. As the number of changes grows, split them into smaller customizers by responsibility, such as metadata, servers, and security. Avoid having multiple customizers replace an entire list, as the result depends on execution order.

## 14. Principles for Writing Safe Customizers

A good customizer should have these characteristics:

1. **Clear scope:** know whether it applies to the default document, one group, or all groups.
2. **Preserves existing metadata:** update only the needed fields, initializing objects only when absent.
3. **Safe to run repeatedly:** avoid adding duplicate tags, servers, schemas, or security requirements.
4. **Independent of request data:** documentation should not vary by the user calling the docs endpoint, unless a specific requirement is explicitly designed.
5. **Do not confuse documentation with runtime:** declaring servers or security does not configure a gateway or Spring Security.
6. **Use environment configuration:** do not hardcode hosts, contacts, or sensitive URLs.
7. **Have output tests:** verify the OpenAPI JSON after customizers run.

Prefer `putIfAbsent`, checking for existing items, or updating only required fields. If a customizer calls `setServers`, `setTags`, or `setSecurity` with a new list, make sure replacing the entire list is intentional.

## 15. Common Mistakes

| Mistake | Consequence | Fix |
|---|---|---|
| Overwriting the entire `Info` | Loses previously configured title, version, or contact | Get `getInfo()` and update only needed fields |
| Using `OpenApiCustomizer` expecting it to apply to all groups | Group documents do not receive the changes | Use `GlobalOpenApiCustomizer` or attach the customizer to the group |
| Adding a server on every run without checking | Server list contains duplicates | Check the URL before adding |
| Using `setServers` when intending to add one server | Deletes servers configured from other sources | Use `addServersItem` or merge lists |
| Adding a global security requirement despite public endpoints | Swagger UI requires a token for public endpoints | Only apply globally when every operation is protected |
| Declaring a security scheme and thinking endpoints are protected | API can still accept unauthenticated requests | Configure and test Spring Security separately |
| Adding a schema to components without referencing it | Schema is unused in operations | Reference via ref or let DTOs generate the schema |
| Using a document-level customizer for single-method metadata | Rules are hard to control and easily affect unintended operations | Use annotations or `OperationCustomizer` |
| Multiple customizers overwriting the same field | Result depends on execution order | Separate responsibilities or consolidate related logic |
| Exposing internal URLs in public documentation | Clients receive unreachable addresses or internal info | Load public URLs per profile and inspect output |

## 16. Verifying Documentation After Customization

After the application starts, open the default document:

~~~bash
curl -s http://localhost:8080/v3/api-docs
~~~

If groups exist, open the document endpoint with the corresponding group name.

Check these sections:

- `info`: title, version, description, contact, license, and terms of service.
- `servers`: public URL matching the current environment, with no duplicate entries.
- `tags`: tag names and descriptions added without erasing other metadata.
- `components.schemas`: shared schemas have the right types and are referenced when needed.
- `components.securitySchemes` and `security`: scheme names are correct and scope of application is appropriate.
- `externalDocs` and `x-...` extensions: URLs and extensions have the right values.
- `paths`: original operations remain intact and free of unexpected changes.

With Swagger UI, check the server selector, API info, tags, and Authorize button. If the documentation has multiple groups, verify each group receives the right customizer. After changing profiles or environment configuration, re-check `servers` to avoid publishing a staging URL in production or vice versa.

## 17. Testing Customizers

You can test model transformation logic by creating an `OpenAPI` object, invoking the customizer, and asserting the fields:

~~~java
@Test
void shouldAddDocumentDescription() {
    OpenAPI openApi = new OpenAPI()
        .info(new Info().title("Store API").version("1.0.0"));

    OpenApiCustomizer customizer = openApiModel -> {
        Info info = openApiModel.getInfo();
        info.setDescription("Store management API.");
    };

    customizer.customise(openApi);

    assertThat(openApi.getInfo().getTitle()).isEqualTo("Store API");
    assertThat(openApi.getInfo().getVersion()).isEqualTo("1.0.0");
    assertThat(openApi.getInfo().getDescription())
        .isEqualTo("Store management API.");
}
~~~

The example uses AssertJ and the `customise` API of the Springdoc interface. The method name and direct invocation should be verified against your dependency version; if that version uses a different signature, adapt the test to the actual API.

Unit tests only verify customizer logic. Add integration tests calling the documentation endpoint to confirm Springdoc actually applies the bean, serializes valid JSON, and preserves expected operations.

## 18. Takeaways

- `OpenApiCustomizer` receives the entire `OpenAPI` model for document-level modifications.
- Use an `OpenApiCustomizer` bean for the default document; use `GlobalOpenApiCustomizer` for shared changes across groups; use `addOpenApiCustomizer` for a specific group.
- `Info`, `Servers`, `Tags`, `Components`, `Security`, `ExternalDocumentation`, and extensions can all be customized.
- Prefer updating individual fields instead of replacing an entire object that already holds metadata.
- Customizers should be idempotent to prevent duplicate servers, tags, schemas, or security items.
- `OperationCustomizer` is suited for per-operation changes.
- Declaring security in OpenAPI does not replace Spring Security configuration.
- Declaring a server URL does not configure a reverse proxy or gateway.
- Always check the default document, each group, and Swagger UI after making changes.

When you need to add shared metadata or rules to an OpenAPI document, use `OpenApiCustomizer` to transform the document model after springdoc generates it. Define the scope clearly, preserve existing metadata, and inspect the generated JSON to ensure Swagger UI and client generators receive the right contract.
