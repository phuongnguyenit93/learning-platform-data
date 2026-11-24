# `@OpenAPIDefinition` and Application-Level Documentation Info

An OpenAPI document needs to describe the API at an overall level before diving into individual endpoints. Readers need to know what the API is named, which documentation version is being published, who is responsible for it, where the terms of service are located, and which server clients should send requests to. Springdoc allows declaring this general information using `@OpenAPIDefinition` in a Spring Boot application.

`@OpenAPIDefinition` is a document-level annotation. It adds shared metadata for the entire OpenAPI specification, whereas `@Operation`, `@Parameter`, `@ApiResponse`, and `@Schema` describe individual operations or data structures. When an application has configuration values that vary by environment, you can create an `OpenAPI` bean to build metadata in Java and read values from Spring configuration.

## 1. What is `@OpenAPIDefinition` used for?

`@OpenAPIDefinition` is an annotation from OpenAPI 3 annotations, located in the `io.swagger.v3.oas.annotations` package. Springdoc reads this annotation to include application-level information in the generated document.

Commonly used attributes include:

| Attribute | Meaning | Annotation or data type |
| --- | --- | --- |
| `info` | Name, description, version, contact, and license of the API | `@Info` |
| `servers` | Server addresses that clients can send requests to | `@Server` |
| `tags` | Name and description metadata for operation groups | `@Tag` |
| `externalDocs` | Link to external reference documentation | `@ExternalDocumentation` |
| `security` | Default security requirement for the document or operations | `@SecurityRequirement` |

For example, an API document can publish the name `Books API`, documentation version `1.0.0`, the production server, and a link to the integration guide. This information helps consumers understand the context of the entire API without repeating it in every controller.

## 2. Declaring General Information with `@OpenAPIDefinition`

Create a configuration class in a package scanned by Spring Boot, for example `com.example.books.config.OpenApiDocumentationConfig`:

```java
package com.example.books.config;

import io.swagger.v3.oas.annotations.OpenAPIDefinition;
import io.swagger.v3.oas.annotations.info.Contact;
import io.swagger.v3.oas.annotations.info.Info;
import io.swagger.v3.oas.annotations.info.License;
import io.swagger.v3.oas.annotations.servers.Server;
import org.springframework.context.annotation.Configuration;

@Configuration
@OpenAPIDefinition(
    info = @Info(
        title = "Books API",
        version = "1.0.0",
        description = "API for looking up and managing book information",
        termsOfService = "https://example.com/terms",
        contact = @Contact(
            name = "Books API Team",
            url = "https://example.com/support",
            email = "api-support@example.com"
        ),
        license = @License(
            name = "Apache 2.0",
            url = "https://www.apache.org/licenses/LICENSE-2.0.html"
        )
    ),
    servers = {
        @Server(
            url = "https://api.example.com",
            description = "Production server"
        ),
        @Server(
            url = "http://localhost:8080",
            description = "Local development server"
        )
    }
)
public class OpenApiDocumentationConfig {}
```

`@Configuration` helps Spring detect the configuration class. `@OpenAPIDefinition` declares metadata for the entire document. `@Info` describes the API; `@Contact` provides contact channels; `@License` publishes the license; `@Server` lists servers that Swagger UI can use as request targets.

The URLs and email in the example are illustrative addresses. When applying this to a project, replace them with real information confirmed by your team. Do not publish internal servers or contact details not intended for API consumers.

## 3. Understanding the Fields in `@Info`

`@Info` is the most important metadata section of the document. The commonly used fields are as follows:

| Field | Purpose | How to choose a value |
| --- | --- | --- |
| `title` | Display name of the API | Easily recognizable product or service name |
| `version` | Published contract/documentation version | Value following the team's versioning convention |
| `description` | Explains the main scope and capabilities of the API | Brief description of target users and functionality |
| `termsOfService` | Terms of service URL | Officially published terms page |
| `contact` | Support team or unit information | Team name, support URL, or active email |
| `license` | API/documentation license information | License name and URL to the license text |

The `info.version` value does not automatically version endpoint URLs. For example, setting `version = "2.0.0"` does not automatically change `/api/v1/books` to `/api/v2/books`. The documentation version and the endpoint versioning strategy are two separate decisions; the team must maintain them consistently.

Avoid overly generic descriptions such as "API for managing data". A useful description should state which business domain the API serves, who can integrate with it, and the main scope of its operations. Contact and license information must also reflect your organization's actual policies.

## 4. Declaring Servers with `@Server`

The `servers` field specifies one or more base URLs of the API. Swagger UI uses this list to build the request URL when users select **Try it out**.

Example:

```java
servers = {
    @Server(url = "https://api.example.com", description = "Production"),
    @Server(url = "https://staging-api.example.com", description = "Staging")
}
```

If the endpoint is `/api/books`, the production server above forms the complete request URL `https://api.example.com/api/books`. Therefore, the server URL is typically the base address; do not repeat individual operation paths in the `url` attribute.

A few notes when declaring servers:

- Only publish servers that documentation readers are permitted to use.
- Verify the `https`/`http` scheme, hostname, port, and base path.
- If the application runs behind a reverse proxy or gateway, the published URL must reflect the address clients actually access.
- Listing a server in OpenAPI does not automatically configure DNS, TLS, proxy, or application routing.
- Multiple servers in the document give Swagger UI users options; they do not automatically make the application run on all those environments.

OpenAPI also supports relative server URLs or URLs with variables. However, for new applications, start with explicit URLs and verify the final URL generated by Swagger UI before using complex patterns.

## 5. Adding Reference Documentation with `@ExternalDocumentation`

When the API has business documentation, authentication guides, or integration conventions on another page, you can include that link in the metadata:

```java
import io.swagger.v3.oas.annotations.ExternalDocumentation;
import io.swagger.v3.oas.annotations.OpenAPIDefinition;
import org.springframework.context.annotation.Configuration;

@Configuration
@OpenAPIDefinition(
    externalDocs = @ExternalDocumentation(
        description = "Books API Integration Guide",
        url = "https://docs.example.com/books-api"
    )
)
public class OpenApiExternalDocsConfig {}
```

`externalDocs` provides a reference link at the document level. It serves as a pointer for users to learn more; Springdoc does not generate the content of that page and does not verify reader access permissions. Use a stable URL and ensure the target page is maintained.

If the documentation has a dedicated reference link for a schema or operation, OpenAPI also provides external documentation locations at the corresponding scope. Choose the right scope so readers can find relevant information.

## 6. Publishing Security Requirements at the Document Level

An API may require a Bearer JWT for most operations. You can declare a security scheme and default security requirement in the document:

```java
package com.example.books.config;

import io.swagger.v3.oas.annotations.OpenAPIDefinition;
import io.swagger.v3.oas.annotations.enums.SecuritySchemeType;
import io.swagger.v3.oas.annotations.security.SecurityRequirement;
import io.swagger.v3.oas.annotations.security.SecurityScheme;
import org.springframework.context.annotation.Configuration;

@Configuration
@SecurityScheme(
    name = "bearerAuth",
    type = SecuritySchemeType.HTTP,
    scheme = "bearer",
    bearerFormat = "JWT"
)
@OpenAPIDefinition(
    security = @SecurityRequirement(name = "bearerAuth")
)
public class OpenApiSecurityDocumentationConfig {}
```

`@SecurityScheme` defines how clients send credentials. `@SecurityRequirement` at the `@OpenAPIDefinition` level applies that requirement as the default in the document. For public endpoints that do not require a token, you can describe the exception at the operation level using the appropriate OpenAPI structure.

The declaration above only describes the security contract. It does not configure Spring Security, validate JWTs, issue tokens, or protect endpoints. The application must still implement real authentication/authorization mechanisms; the rules described in OpenAPI must match those mechanisms.

## 7. When to Use `@OpenAPIDefinition` vs. an `OpenAPI` Bean?

Springdoc also supports creating an `OpenAPI` bean. The two approaches serve different needs:

| Criterion | `@OpenAPIDefinition` | `OpenAPI` Bean |
| --- | --- | --- |
| Declaration style | Annotation and nested annotations | Java object model |
| Configuration values | Suitable for static metadata known at compile time | Can read from properties, profiles, or Spring beans |
| Structure | Concise for simple metadata | Flexible when conditional logic or programmatic construction is needed |
| Best suited when | Title, description, contact, and servers rarely change | Server URL, title, or version depends on the environment |

Example of creating a bean with values read from `application.properties`:

```java
package com.example.books.config;

import io.swagger.v3.oas.models.OpenAPI;
import io.swagger.v3.oas.models.info.Info;
import io.swagger.v3.oas.models.servers.Server;
import java.util.List;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class OpenApiBeanConfig {

    @Bean
    public OpenAPI booksOpenAPI(
            @Value("${api.docs.title:Books API}") String title,
            @Value("${api.docs.version:1.0.0}") String version,
            @Value("${api.docs.server-url:http://localhost:8080}") String serverUrl) {

        return new OpenAPI()
            .info(new Info()
                .title(title)
                .description("API for looking up and managing books")
                .version(version))
            .servers(List.of(
                new Server()
                    .url(serverUrl)
                    .description("Server for the current environment")
            ));
    }
}
```

In `application.properties`:

```properties
api.docs.title=Books API
api.docs.version=1.0.0
api.docs.server-url=https://api.example.com
```

You can use Spring profiles or environment variables to provide different `api.docs.server-url` values for local, staging, and production. The example above uses the default value syntax in `@Value`, ensuring the application still has a fallback value if the property is not declared.

Choose a single source for managing shared metadata and avoid declaring the same `info` or `servers` fields in multiple places with conflicting values. If a project uses both annotations and an `OpenAPI` bean, inspect the generated document to determine the actual merged result for the Springdoc version in use; do not assume duplicate values will be overridden in a desired order.

## 8. Corresponding Metadata Example in OpenAPI YAML

When accessing `/v3/api-docs.yaml` (if the application has enabled the YAML endpoint), the declared metadata is represented at the document level. Abbreviated example:

```yaml
openapi: 3.0.3
info:
  title: Books API
  version: 1.0.0
  description: API for looking up and managing book information
  termsOfService: https://example.com/terms
  contact:
    name: Books API Team
    url: https://example.com/support
    email: api-support@example.com
  license:
    name: Apache 2.0
    url: https://www.apache.org/licenses/LICENSE-2.0.html
servers:
  - url: https://api.example.com
    description: Production server
externalDocs:
  description: Books API Integration Guide
  url: https://docs.example.com/books-api
```

This is an illustrative structure to show metadata placement, not a complete copy guaranteed to match the exact output of every Springdoc version. The OpenAPI version, field order, and other components may vary depending on configuration and library version.

## 9. Verifying Metadata Generated by Springdoc

After starting the application, open the commonly used documentation endpoints:

| Default URL | Content |
| --- | --- |
| `/v3/api-docs` | OpenAPI specification in JSON format |
| `/v3/api-docs.yaml` | OpenAPI specification in YAML format |
| `/swagger-ui/index.html` | Swagger UI interface |

In the JSON or YAML, verify the following fields:

1. `info.title`, `info.version`, and `info.description` have the expected values.
2. `info.contact` and `info.license` contain accurate information with accessible URLs.
3. `servers` has the appropriate hostname, scheme, and base path for the environment.
4. `externalDocs` points to the correct documentation page.
5. `components.securitySchemes` contains the declared security scheme; `security` reflects the default requirement properly.
6. Operations and schemas are still generated just as they were before adding document-level metadata.

In Swagger UI, check the API name, description, server list, and the **Authorize** button if the document has a security scheme. If Swagger UI sends requests to the wrong hostname, check `servers` in the specification before modifying proxy or controller configuration.

## 10. Common Issues and Troubleshooting

| Symptom | Possible Cause | How to Check |
| --- | --- | --- |
| Title or description does not appear | The class containing `@OpenAPIDefinition` is not detected by component scan or another configuration creates metadata | Check package scanning and `/v3/api-docs` JSON |
| Contact or license info is missing | Not declared in `@Info` or viewing the wrong document/group | Check `info.contact`, `info.license`, and the currently opened group |
| Swagger UI sends requests to the wrong server | `@Server` contains an old URL or incorrect base path | Check the `servers` array in JSON/YAML |
| Local server appears in production documentation | Static metadata lists multiple environments or configuration is not separated by profile | Use an `OpenAPI` bean with environment-specific properties or publish only the required servers |
| Authorize button does not appear | Security scheme is not declared or UI is loading a different document | Check `components.securitySchemes` and the document URL loaded by UI |
| Document shows Bearer requirement but endpoints are accessible without a token | Only OpenAPI metadata was declared without configuring Spring Security | Check the filter chain and test an actual request |
| Metadata differs from expected configuration | Both annotation and `OpenAPI` bean declare overlapping values | Pick a primary configuration source and inspect the generated output |

When using multiple groups, each group may have its own document. Check the specific `/v3/api-docs/{group}` URL instead of viewing only the default document. If the application changes `springdoc.api-docs.path` or has a context path, adjust the inspection endpoint accordingly.

## 11. Checklist for Application-Level Metadata

- [ ] `@OpenAPIDefinition` is declared in a package scanned by Spring Boot, or an appropriate `OpenAPI` bean is created.
- [ ] `info.title`, `info.version`, and `info.description` accurately describe the API.
- [ ] Contact and license use information approved for publication.
- [ ] Server URLs reflect the exact addresses clients access in the corresponding environment.
- [ ] The `externalDocs` link is stable and points to appropriate documentation.
- [ ] Security schemes and security requirements in OpenAPI match the actual security mechanism.
- [ ] `info.version` is not confused with the endpoint URL version.
- [ ] Duplicate or conflicting metadata is not declared across annotations and beans.
- [ ] JSON/YAML and Swagger UI were verified after configuration changes.

`@OpenAPIDefinition` helps centralize general API contract information at the application scope. When metadata needs to vary by environment, an `OpenAPI` bean combined with Spring configuration provides flexibility. Whichever approach you choose, verify the generated specification and ensure the servers, contact details, version, and security requirements accurately reflect how the API is operated.
