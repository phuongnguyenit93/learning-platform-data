# Preserving Shared Metadata Without Breaking Per-Group Contracts

When a Spring Boot application exports multiple OpenAPI documents using GroupedOpenApi, those documents often share common information such as API ownership, contact details, licensing, terms of service, and authentication schemes. Still, each group may serve a different audience and need its own document title, version, servers, or security policy.

The goal is to keep genuinely shared metadata consistent across groups while letting each contract publish its exact scope. springdoc-openapi provides the OpenAPI bean, OpenApiCustomizer, GlobalOpenApiCustomizer, and customizers attached directly to GroupedOpenApi to organize this cleanly.

## 1. Which Metadata Should Be Shared?

An OpenAPI document contains many metadata sections. Not every field should be identical across all groups.

| Component | Meaning | Usage Across Groups |
| --- | --- | --- |
| Info.title | Display name of the document | Usually distinct per group |
| Info.version | Version of the described API contract | Shared or separate depending on API lifecycle |
| Info.description | Description of scope and target audience | Usually distinct per group |
| Info.termsOfService | Terms of service URL | Can be shared |
| Info.contact | Owning unit or support channel | Usually shared; may differ by product |
| Info.license | Licensing information | Shared when the same policy applies |
| Servers | Base URLs for client requests | Shared or separate by environment/audience |
| Tags | Operation groups and descriptions | Some tags shared; some specific to one group |
| Components | Reusable schemas, parameters, responses, and security schemes | Include only where operations need them or per shared policy |
| Security requirements | Document-level or operation-level auth requirements | Must match the policy of each operation/group |
| External docs | Links to supplemental guides | Shared at API level or tailored per group |

For example, contact and license can be shared organizational metadata. Meanwhile, Public API and Partner API should have distinct titles and descriptions so integrators recognize the right contract. A partner API may use a dedicated server URL; internal hosts should never appear in public documentation.

## 2. Distinguishing Group Names from Info Metadata

A group name is a springdoc configuration identifier and usually appears in the document retrieval URL. Info.title is the display title inside the OpenAPI document and Swagger UI.

For example:

~~~java
@Bean
GroupedOpenApi partnerApi() {
    return GroupedOpenApi.builder()
        .group("partner-api")
        .pathsToMatch("/api/partner/**")
        .build();
}
~~~

Here, partner-api is the group id. It does not automatically set Info.title, Info.version, or Info.description. Without Info customization, the document may use default metadata or the application's shared metadata.

You can think of the fields as follows:

| Value | Role |
| --- | --- |
| group = partner-api | Selects the document and defines the group URL |
| Info.title = Partner API | Display name shown to integrators |
| Info.version = v1 | Version of the contract being described |
| openapi = 3.1.0 | OpenAPI Specification version, not the API version |

Do not use group id as a substitute for API version. Changing the group id can break document URLs; changing Info.version simply updates contract metadata.

## 3. Customization Levels in springdoc-openapi

There are three primary ways to supply metadata to documents:

| Mechanism | Scope | When to Use |
| --- | --- | --- |
| OpenAPI bean | Shared metadata and components across documents, including groups | Declaring organization details, security schemes, or common components |
| GlobalOpenApiCustomizer bean | Customizations applied to the default document and all groups | Enforcing or standardizing metadata across every document |
| OpenApiCustomizer attached to GroupedOpenApi | Only the document of the attached group | Setting per-group title, description, servers, or tags |

A common pitfall: a standalone OpenApiCustomizer bean typically applies only to the default OpenAPI document. To have a customizer bean run for all groups as well, use GlobalOpenApiCustomizer. To modify only one group, attach an OpenApiCustomizer via addOpenApiCustomizer on that group's builder.

Springdoc's FAQ clearly explains the difference between default customizers and global customizers. Check the docs for your major version since packages and some APIs can change across springdoc releases.

## 4. Declaring Shared Metadata with an OpenAPI Bean

An OpenAPI bean is well suited for elements every document needs. For example, an organization sharing contact, license, terms of service, and an HTTP bearer scheme:

~~~java
import io.swagger.v3.oas.models.Components;
import io.swagger.v3.oas.models.OpenAPI;
import io.swagger.v3.oas.models.info.Contact;
import io.swagger.v3.oas.models.info.Info;
import io.swagger.v3.oas.models.info.License;
import io.swagger.v3.oas.models.security.SecurityScheme;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class SharedOpenApiConfig {

    @Bean
    OpenAPI sharedOpenAPI() {
        return new OpenAPI()
            .info(new Info()
                .title("Shop API")
                .version("v1")
                .termsOfService("https://developer.example.com/terms")
                .contact(new Contact()
                    .name("API Platform Team")
                    .email("api-support@example.com")
                    .url("https://developer.example.com/support"))
                .license(new License()
                    .name("Internal API License")
                    .url("https://developer.example.com/license")))
            .components(new Components()
                .addSecuritySchemes("bearerAuth",
                    new SecurityScheme()
                        .type(SecurityScheme.Type.HTTP)
                        .scheme("bearer")
                        .bearerFormat("JWT")));
    }
}
~~~

This bean provides shared metadata and components. You do not have to apply the same security requirement to every operation just because bearerAuth is declared. A security scheme only defines how authentication works; a security requirement dictates that clients must use it.

If the project already defines another OpenAPI bean, merge configurations rather than creating competing OpenAPI beans. A single clear configuration source prevents unexpected overwriting of metadata or components.

## 5. Preserving Shared Metadata with GlobalOpenApiCustomizer

GlobalOpenApiCustomizer fits when you need to apply the same convention to every document, including groups. For instance, ensuring every document has contact and license if initial metadata omitted them:

~~~java
import io.swagger.v3.oas.models.info.Contact;
import io.swagger.v3.oas.models.info.Info;
import io.swagger.v3.oas.models.info.License;
import org.springdoc.core.customizers.GlobalOpenApiCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class SharedOpenApiCustomizerConfig {

    @Bean
    GlobalOpenApiCustomizer sharedInfoCustomizer() {
        return openApi -> {
            Info info = openApi.getInfo();
            if (info == null) {
                info = new Info()
                    .title("API")
                    .version("v1");
                openApi.setInfo(info);
            }

            if (info.getContact() == null) {
                info.setContact(new Contact()
                    .name("API Platform Team")
                    .email("api-support@example.com")
                    .url("https://developer.example.com/support"));
            }

            if (info.getLicense() == null) {
                info.setLicense(new License()
                    .name("Internal API License")
                    .url("https://developer.example.com/license"));
            }
        };
    }
}
~~~

This example fills contact and license only when missing. That preserves metadata already declared at the group or OpenAPI bean level. If you want to enforce a mandatory organizational value, you can overwrite it deliberately, understanding that every group will receive that same value.

Avoid replacing the entire Info object inside a global customizer if each group already has its own title, version, or description. Calling openApi.setInfo(new Info().title(...)) can wipe out fields set earlier.

## 6. Setting Group-Specific Metadata with Per-Group OpenApiCustomizer

Each group can customize title, version, and description while retaining shared contact, license, and other common metadata.

~~~java
import io.swagger.v3.oas.models.info.Info;
import org.springdoc.core.customizers.OpenApiCustomizer;
import org.springdoc.core.models.GroupedOpenApi;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class GroupMetadataConfig {

    @Bean
    GroupedOpenApi publicApi() {
        return GroupedOpenApi.builder()
            .group("public-api")
            .pathsToMatch("/api/public/**")
            .addOpenApiCustomizer(openApi -> {
                Info info = openApi.getInfo();
                if (info == null) {
                    info = new Info();
                    openApi.setInfo(info);
                }
                info.setTitle("Public API");
                info.setVersion("v1");
                info.setDescription(
                    "Contract for web, mobile applications, and public integrating clients.");
            })
            .build();
    }

    @Bean
    GroupedOpenApi partnerApi() {
        return GroupedOpenApi.builder()
            .group("partner-api")
            .pathsToMatch("/api/partner/**")
            .addOpenApiCustomizer(openApi -> {
                Info info = openApi.getInfo();
                if (info == null) {
                    info = new Info();
                    openApi.setInfo(info);
                }
                info.setTitle("Partner API");
                info.setVersion("v2");
                info.setDescription(
                    "Contract for shipping and sales partners.");
            })
            .build();
    }
}
~~~

In this example, each customizer writes only fields belonging to that group's scope. Contact and license are preserved from the shared configuration. If a group needs its own contact or license, set them explicitly inside that group's customizer.

Do not rely on execution ordering between multiple customizers to resolve metadata conflicts. Ideally, every field has a single clear owner: global customizers supply shared fields; group customizers set per-group fields. If two places write the same field, consolidate the logic or test the actual order in your library version.

## 7. OpenAPI Bean, Annotation, or Customizer?

Choose the mechanism based on the nature of the metadata:

| Need | Suitable Mechanism |
| --- | --- |
| Shared, fixed, statically declared metadata | @OpenAPIDefinition |
| Shared metadata read from Spring configuration | OpenAPI bean |
| Enforcing rules across every group | GlobalOpenApiCustomizer |
| Metadata or structure specific to one group | GroupedOpenApi.builder().addOpenApiCustomizer(...) |
| Describing specific operations or schemas | @Operation, @ApiResponse, @Schema, and related annotations |

@OpenAPIDefinition works well for application-level title, version, description, contact, and tags when conditional logic is not needed. An OpenAPI bean is more flexible when metadata comes from application.yml or environment variables. Customizers fit when logic depends on the group or needs direct manipulation of the OpenAPI model.

Annotation example for shared static metadata:

~~~java
import io.swagger.v3.oas.annotations.OpenAPIDefinition;
import io.swagger.v3.oas.annotations.info.Contact;
import io.swagger.v3.oas.annotations.info.Info;
import io.swagger.v3.oas.annotations.info.License;
import org.springframework.context.annotation.Configuration;

@Configuration
@OpenAPIDefinition(
    info = @Info(
        title = "Shop API",
        version = "v1",
        description = "E-commerce platform API",
        termsOfService = "https://developer.example.com/terms",
        contact = @Contact(
            name = "API Platform Team",
            email = "api-support@example.com"
        ),
        license = @License(
            name = "Internal API License",
            url = "https://developer.example.com/license"
        )
    )
)
class StaticOpenApiDefinition {
}
~~~

This annotation suits metadata that stays identical across all documents. If title or version must vary by group, set those fields inside each group's customizer.

Example externalizing shared metadata in application.yml:

~~~yaml
app:
  api-docs:
    contact-name: API Platform Team
    contact-email: api-support@example.com
    support-url: https://developer.example.com/support
    license-name: Internal API License
    license-url: https://developer.example.com/license
~~~

You can inject these values into an OpenAPI bean via @Value or @ConfigurationProperties. Never hardcode internal environment addresses into metadata if the document is published to external clients.

## 8. Managing Servers Per Contract

Servers specify the base URLs clients use to call the API. One application may serve multiple groups over the same host, though partner APIs sometimes sit behind a separate gateway or public APIs use a distinct base URL.

Example where public and partner use different servers:

~~~java
import java.util.List;
import io.swagger.v3.oas.models.servers.Server;

// Inside the public-api customizer
openApi.setServers(List.of(
    new Server()
        .url("https://api.example.com")
        .description("Public production")
));

// Inside the partner-api customizer
openApi.setServers(List.of(
    new Server()
        .url("https://partner-api.example.com")
        .description("Partner production")
));
~~~

Servers should reflect URLs clients can actually reach. If the application runs behind a reverse proxy, check forwarded headers and public URLs. Ensure public documentation never leaks localhost, Kubernetes hostnames, private IPs, or unintended staging URLs.

If groups share a base URL, you can declare servers once. If only environments differ (development/staging/production), you can use server variables or environment-specific doc generation, while taking care never to publish docs pointing to an environment unintended for integrators.

## 9. Keeping Components and $refs Consistent Across Groups

Each OpenAPI document has its own components section. A schema, parameter, response, or security scheme exists only in the document where it is declared. Consequently, a $ref in partner-api cannot automatically reference components in public-api.

For example:

~~~yaml
components:
  schemas:
    PartnerOrder:
      type: object
      properties:
        partnerOrderId:
          type: string
~~~

If an operation in the partner-api group references:

~~~yaml
schema:
  $ref: '#/components/schemas/PartnerOrder'
~~~

then PartnerOrder must exist inside the partner-api document itself. Springdoc normally populates components with schemas referenced by DTOs in that group's operations. For components added manually via customizers or an OpenAPI bean, ensure they are included in every document that references them.

Do not dump all internal schemas into every group if consumers of that group do not need them. Shared components should belong genuinely to the shared contract; keep the rest scoped to their respective groups to avoid exposing unrelated structures.

## 10. Security Schemes Can Be Shared; Security Requirements Should Be Selective

A scheme describes an authentication mechanism, such as bearer JWT or OAuth2. A security requirement indicates that an operation or entire document requires that scheme.

You can define a shared bearer scheme in the OpenAPI bean:

~~~java
new Components().addSecuritySchemes("bearerAuth",
    new SecurityScheme()
        .type(SecurityScheme.Type.HTTP)
        .scheme("bearer")
        .bearerFormat("JWT"))
~~~

If every operation in a group requires a bearer token, you can set a document-level requirement for that group:

~~~java
openApi.addSecurityItem(
    new SecurityRequirement().addList("bearerAuth")
);
~~~

However, do not apply a global security requirement if a group contains public endpoints or endpoints using different auth mechanisms. Instead, attach requirements per operation using @SecurityRequirement or an appropriate customizer. Schemes can be shared, whereas requirements must match each endpoint's policy.

Declaring security in OpenAPI only documents how clients authenticate. Spring Security and the gateway enforce actual access control. Never rely on documentation in place of runtime security configuration.

## 11. Selectively Sharing Tags and externalDocs

Tags organize operations inside each document. If multiple groups cover the same domain, they can share tag names and descriptions, though only tags with relevant operations should appear in a document.

For example:

~~~yaml
tags:
  - name: Orders
    description: Order management operations
    externalDocs:
      description: Order lifecycle workflow
      url: https://docs.example.com/orders/lifecycle
~~~

Some groups may use the Orders tag while containing only partner-facing operations. The description should accurately reflect the scope visible to that group's consumers. If the same tag name carries different meanings across audiences, use more specific tag names such as Partner Orders or Public Orders.

Document-level externalDocs fit general guides. Detailed partner workflow docs should be attached specifically to the partner group or partner tag. Avoid putting internal links or employee-only docs inside public API documents.

## 12. Avoiding Broken Contracts When Customizing Metadata

Common mistakes:

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Using an OpenApiCustomizer bean for all groups | Metadata only appears in the default document | Use GlobalOpenApiCustomizer or attach customizers to each GroupedOpenApi |
| Overwriting the entire Info object | Loses contact, license, terms, or group metadata | Update individual fields on the existing Info |
| Using the same title/description for every audience | Readers cannot tell contract scopes apart | Set Info per group |
| Putting internal server URLs in public docs | External clients cannot reach them or internal infra leaks | Use environment-appropriate public URLs |
| Adding a global security requirement | Public endpoints get falsely documented as requiring a token | Apply requirements per operation or per group |
| Adding a component missing from referencing documents | $ref breaks in some groups | Verify components inside every document |
| Reusing the same tag name for two different meanings | Swagger UI groups operations confusingly | Choose scope-clear tag names |
| Using group id as API version | Users confuse document URLs with contract versions | Manage group id and Info.version separately |
| Relying on unguaranteed customizer order | Metadata gets overwritten differently across environments | Assign clear field ownership and test output |

## 13. Comprehensive Example: Shared and Group-Specific Metadata

A complete configuration can split responsibilities like this:

~~~java
import io.swagger.v3.oas.models.Components;
import io.swagger.v3.oas.models.ExternalDocumentation;
import io.swagger.v3.oas.models.OpenAPI;
import io.swagger.v3.oas.models.info.Contact;
import io.swagger.v3.oas.models.info.Info;
import io.swagger.v3.oas.models.info.License;
import io.swagger.v3.oas.models.security.SecurityScheme;
import io.swagger.v3.oas.models.servers.Server;
import org.springdoc.core.customizers.GlobalOpenApiCustomizer;
import org.springdoc.core.models.GroupedOpenApi;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import java.util.List;

@Configuration
class ApiDocumentationConfig {

    @Bean
    OpenAPI sharedOpenAPI() {
        return new OpenAPI()
            .info(new Info()
                .title("Shop API")
                .version("v1")
                .termsOfService("https://developer.example.com/terms")
                .contact(new Contact()
                    .name("API Platform Team")
                    .email("api-support@example.com"))
                .license(new License()
                    .name("Internal API License")
                    .url("https://developer.example.com/license")))
            .components(new Components()
                .addSecuritySchemes("bearerAuth",
                    new SecurityScheme()
                        .type(SecurityScheme.Type.HTTP)
                        .scheme("bearer")
                        .bearerFormat("JWT")));
    }

    @Bean
    GlobalOpenApiCustomizer commonMetadata() {
        return openApi -> {
            if (openApi.getExternalDocs() == null) {
                openApi.setExternalDocs(new ExternalDocumentation()
                    .description("Developer documentation portal")
                    .url("https://developer.example.com"));
            }
        };
    }

    @Bean
    GroupedOpenApi publicApi() {
        return GroupedOpenApi.builder()
            .group("public-api")
            .pathsToMatch("/api/public/**")
            .addOpenApiCustomizer(openApi -> {
                Info info = openApi.getInfo();
                if (info == null) {
                    info = new Info();
                    openApi.setInfo(info);
                }
                info.setTitle("Public API");
                info.setVersion("v1");
                info.setDescription("Contract for public applications and customers.");
                openApi.setServers(List.of(
                    new Server().url("https://api.example.com")
                        .description("Public production")
                ));
            })
            .build();
    }

    @Bean
    GroupedOpenApi partnerApi() {
        return GroupedOpenApi.builder()
            .group("partner-api")
            .pathsToMatch("/api/partner/**")
            .addOpenApiCustomizer(openApi -> {
                Info info = openApi.getInfo();
                if (info == null) {
                    info = new Info();
                    openApi.setInfo(info);
                }
                info.setTitle("Partner API");
                info.setVersion("v2");
                info.setDescription("Contract for integrating partners.");
                openApi.setServers(List.of(
                    new Server().url("https://partner-api.example.com")
                        .description("Partner production")
                ));
            })
            .build();
    }
}
~~~

This comprehensive example shows how to divide shared and group-specific parts. Imports are listed in the snippet; check your springdoc version to verify packages for GroupedOpenApi and GlobalOpenApiCustomizer.

In this example, the OpenAPI bean supplies contact, license, terms, and security scheme. GlobalOpenApiCustomizer adds externalDocs to every document if absent. Each group sets its own title, version, description, and server. Security requirements are not added globally because authentication policies can vary by operation.

## 14. Verifying Metadata Across Every Document

After starting the application, fetch each OpenAPI document:

~~~bash
# Default document
curl -sS http://localhost:8080/v3/api-docs

# Public document
curl -sS http://localhost:8080/v3/api-docs/public-api

# Partner document
curl -sS http://localhost:8080/v3/api-docs/partner-api
~~~

If jq is available, quickly inspect metadata sections:

~~~bash
curl -sS http://localhost:8080/v3/api-docs/public-api \
  | jq '{info, servers, tags, security, components}'
~~~

Perform the same check on partner-api and verify:

1. Do title, version, and description match the audience?
2. Are contact, license, and terms consistent with shared policy?
3. Do servers match the group's public host?
4. Are security schemes present wherever needed?
5. Do security requirements accurately reflect public vs. protected endpoints?
6. Do tags and externalDocs describe the group's scope properly?
7. Do all $refs to schemas, parameters, and responses exist within the same document?
8. Are internal hostnames, unpublished endpoints, or another audience's metadata prevented from leaking?

Swagger UI is only a documentation viewer. The JSON/YAML at OpenAPI endpoints is the authoritative output to verify when validating contracts.

## 15. Testing and Managing Metadata Changes

Write integration tests for each group to verify critical metadata. Tests can fetch the OpenAPI endpoint and assert on title, version, servers, security schemes, and representative paths.

Example test idea:

~~~java
mockMvc.perform(get("/v3/api-docs/partner-api"))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$.info.title").value("Partner API"))
    .andExpect(jsonPath("$.info.version").value("v2"))
    .andExpect(jsonPath("$.servers[0].url")
        .value("https://partner-api.example.com"));
~~~

When modifying shared metadata, check all groups because GlobalOpenApiCustomizer and the OpenAPI bean can affect multiple documents simultaneously. When modifying a group-specific customizer, inspect both the target group and unrelated groups to ensure nothing else changed unexpectedly.

You can archive exported OpenAPI files in CI and run contract diffs to detect breaking changes. Metadata title or description changes usually do not alter request/response structures, whereas changing servers, security, schemas, or paths can directly impact clients.

## 16. Workflow for Organizing Metadata

When an application serves multiple documents:

1. List shared organizational metadata and per-group metadata.
2. Choose an OpenAPI bean or @OpenAPIDefinition for shared info.
3. Use GlobalOpenApiCustomizer for rules applied across every document.
4. Use OpenApiCustomizer attached to GroupedOpenApi for per-group title, version, description, or servers.
5. Keep security schemes shared when appropriate, but apply security requirements per operation/group.
6. Ensure components and $refs exist within each document.
7. Verify JSON/YAML for all groups after changes.
8. Add integration tests and contract diffs to protect metadata and contracts over time.

With clear boundaries between shared and group-specific metadata, OpenAPI documents retain consistent organizational branding while accurately reflecting the audience, servers, versions, and policies of each group.

## References

- [springdoc-openapi – FAQ: Customize OpenAPI object and grouped definitions](https://springdoc.org/faq.html)
- [springdoc-openapi v2 – FAQ for Spring Boot 3](https://springdoc.org/v2/faq.html)
- [OpenAPI Specification – Info Object](https://spec.openapis.org/oas/latest.html#info-object)
- [OpenAPI Specification – Server Object](https://spec.openapis.org/oas/latest.html#server-object)
- [OpenAPI Specification – Security Requirement Object](https://spec.openapis.org/oas/latest.html#security-requirement-object)
