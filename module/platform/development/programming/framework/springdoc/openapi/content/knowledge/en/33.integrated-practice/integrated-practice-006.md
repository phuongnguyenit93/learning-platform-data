# Adding Shared Metadata via Customizers with Tests

In a Spring Boot application, multiple controllers and API groups often need to share documentation metadata: the owning team's contact details, license, documentation links, platform tags, or a request correlation header. Repeating this information across every controller makes it easy for details to drift when support addresses, team names, or integration conventions change.

springdoc-openapi allows adding metadata via an `OpenAPI` bean and customizers. Choosing the right scope is key: platform-wide metadata can apply to all documents; group-specific metadata should appear only in that group; operation-specific metadata belongs on the corresponding operation. After configuring, test the generated JSON to confirm the metadata actually appears in both the default document and the groups.

## 1. Distinguishing the extension points

Not all customizers share the same scope:

| Mechanism | Scope | Suitable examples |
| --- | --- | --- |
| `OpenAPI` bean | Baseline definition shared across OpenAPI documents | `info`, `components`, security schemes, shared parameters or headers. |
| `GlobalOpenApiCustomizer` | Modifies the default document and `GroupedOpenApi` documents | Adding contact, external docs, tags, or common parameters across all groups. |
| `OpenApiCustomizer` attached to `GroupedOpenApi` | Only the configured group's document | Descriptions, extensions, or metadata specific to a partner group. |
| Regular `OpenApiCustomizer` bean | Default document | Adjusting the default document without affecting groups. |
| Annotations like `@Operation`, `@Tag`, `@Schema` | Corresponding controller, operation, or model | Describing behavior and schemas at the API declaration source. |

According to the springdoc FAQ, a regular `OpenApiCustomizer` bean applies only to the default document. If a customizer must also run for groups, use `GlobalOpenApiCustomizer`. An `OpenAPI` bean can supply baseline definitions that appear in groups, even when a group has its own controller/path filters.

`OperationCustomizer` is an operation-level extension point and typically receives both the operation and the handler method. Use it when metadata depends on a specific method or controller. For metadata shared across an entire document, `GlobalOpenApiCustomizer` usually expresses the scope more accurately.

## 2. Identifying which metadata is genuinely shared

Before writing code, classify your metadata:

| Metadata | Example | Recommended scope |
| --- | --- | --- |
| Document title and version | Store API, 1.4.0 | Per API/group if groups have separate lifecycles; use baseline config if identical. |
| Contact | API Platform Team, support email | All documents if owned by the same team. |
| License | Apache 2.0 or internal terms | All documents if policies match. |
| Terms of service | Terms of use URL | All documents if policies match. |
| External documentation | Authentication guides, error conventions | All documents, or per group if target readers differ. |
| Shared tag | Platform, Common | All documents if used by operations across multiple groups. |
| Correlation header | `X-Correlation-Id` | Attach only to operations that actually accept this header. |
| Custom extension | `x-audience`, `x-owner` | Per agreement with consumers reading the extension. |

Do not put every piece of metadata into every document just because you can. For instance, public documentation should not contain internal runbook links; a partner group should not receive an internal operations team contact if that address is not meant for partners. Identify the audience and scope before adding a customizer.

## 3. Creating an OpenAPI bean for baseline metadata

With springdoc v2 for Spring Boot 3, you can define an `OpenAPI` bean to declare baseline information. The following example sets a shared title and version while keeping them separate from controllers:

~~~java
import io.swagger.v3.oas.models.OpenAPI;
import io.swagger.v3.oas.models.info.Info;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class OpenApiBaseConfiguration {

    @Bean
    OpenAPI baseOpenApi(
        @Value("${service.api.version:1.0.0}") String apiVersion
    ) {
        return new OpenAPI()
            .info(new Info()
                .title("Store API")
                .version(apiVersion)
                .description("Store platform API."));
    }
}
~~~

An `OpenAPI` bean fits baseline information needed by all documents. If each group has a different title or version, do not force a single shared value onto all of them; set group-specific metadata in a group customizer or per-audience configuration.

Avoid declaring multiple competing `OpenAPI` beans in the same application context without a clear reason. Maintain one baseline configuration source and use customizers for conditional additions.

## 4. Adding shared metadata and parameters with GlobalOpenApiCustomizer

The example below adds contact, license, external documentation, a `Platform` tag, and a shared `X-Correlation-Id` header. The customizer checks before adding the parameter to avoid creating duplicates if an operation already declares this header.

~~~java
import io.swagger.v3.oas.models.OpenAPI;
import io.swagger.v3.oas.models.Components;
import io.swagger.v3.oas.models.ExternalDocumentation;
import io.swagger.v3.oas.models.Operation;
import io.swagger.v3.oas.models.info.Contact;
import io.swagger.v3.oas.models.info.Info;
import io.swagger.v3.oas.models.info.License;
import io.swagger.v3.oas.models.media.StringSchema;
import io.swagger.v3.oas.models.parameters.Parameter;
import io.swagger.v3.oas.models.tags.Tag;
import org.springdoc.core.customizers.GlobalOpenApiCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import java.util.List;
import java.util.Objects;

@Configuration
class SharedOpenApiMetadataConfiguration {

    private static final String CORRELATION_ID_NAME = "X-Correlation-Id";
    private static final String CORRELATION_ID_REF =
        "#/components/parameters/CorrelationId";

    @Bean
    GlobalOpenApiCustomizer sharedMetadataCustomizer() {
        return openApi -> {
            addSharedInfo(openApi);
            addExternalDocumentation(openApi);
            addSharedTag(openApi);
            addCorrelationIdComponent(openApi);
            addCorrelationIdToOperations(openApi);
        };
    }

    private static void addSharedInfo(OpenAPI openApi) {
        if (openApi.getInfo() == null) {
            openApi.setInfo(new Info());
        }

        Info info = openApi.getInfo();
        if (info.getContact() == null) {
            info.setContact(new Contact());
        }
        Contact contact = info.getContact();
        if (contact.getName() == null) {
            contact.setName("API Platform Team");
        }
        if (contact.getEmail() == null) {
            contact.setEmail("api-support@example.com");
        }
        if (contact.getUrl() == null) {
            contact.setUrl("https://developer.example.com/support");
        }

        if (info.getLicense() == null) {
            info.setLicense(new License()
                .name("Internal API Terms")
                .url("https://developer.example.com/terms"));
        }
    }

    private static void addExternalDocumentation(OpenAPI openApi) {
        if (openApi.getExternalDocs() == null) {
            openApi.setExternalDocs(new ExternalDocumentation()
                .description("API integration guide")
                .url("https://developer.example.com/guides"));
        }
    }

    private static void addSharedTag(OpenAPI openApi) {
        boolean exists = openApi.getTags() != null
            && openApi.getTags().stream()
                .anyMatch(tag -> "Platform".equals(tag.getName()));

        if (!exists) {
            openApi.addTagsItem(new Tag()
                .name("Platform")
                .description("Shared platform information and conventions."));
        }
    }

    private static void addCorrelationIdComponent(OpenAPI openApi) {
        if (openApi.getComponents() == null) {
            openApi.setComponents(new Components());
        }

        Components components = openApi.getComponents();
        Parameter existing = components.getParameters() == null
            ? null
            : components.getParameters().get("CorrelationId");

        if (existing == null) {
            components.addParameters("CorrelationId", new Parameter()
                .name(CORRELATION_ID_NAME)
                .in("header")
                .description("Correlation ID to trace a request across services.")
                .required(false)
                .schema(new StringSchema()));
        } else if (!CORRELATION_ID_NAME.equals(existing.getName())
            || !"header".equals(existing.getIn())) {
            throw new IllegalStateException(
                "components.parameters.CorrelationId is reserved for X-Correlation-Id");
        }
    }

    private static void addCorrelationIdToOperations(OpenAPI openApi) {
        if (openApi.getPaths() == null) {
            return;
        }

        openApi.getPaths().values().stream()
            .flatMap(pathItem -> pathItem.readOperations().stream())
            .forEach(SharedOpenApiMetadataConfiguration::addCorrelationId);
    }

    static void addCorrelationId(Operation operation) {
        List<Parameter> parameters = operation.getParameters();
        boolean alreadyDeclared = parameters != null
            && parameters.stream().anyMatch(parameter ->
                Objects.equals(CORRELATION_ID_REF, parameter.get$ref())
                    || (Objects.equals("header", parameter.getIn())
                        && CORRELATION_ID_NAME.equalsIgnoreCase(parameter.getName()))
            );

        if (!alreadyDeclared) {
            operation.addParametersItem(new Parameter()
                .$ref(CORRELATION_ID_REF));
        }
    }
}
~~~

`GlobalOpenApiCustomizer` is used because the changes must appear in both the default document and grouped documents. The parameter component is registered once in `components.parameters`; each operation references it with `$ref`. This keeps header documentation consistent and avoids duplicating the full description across every controller.

The customizer also verifies that any existing component key actually corresponds to the `X-Correlation-Id` header. If the `CorrelationId` key is already used by another parameter, the configuration fails fast rather than silently referencing the wrong component. The `Platform` tag is declared at the document level; declaring it there does not automatically tag every operation. Only add a tag to an operation if it is genuinely an appropriate category.

The example uses the `example.com` domain for illustration. Replace contacts, licenses, and URLs with values approved by your organization before release. Never put tokens, personal emails, or private runbook URLs into public documents.

A header should only be added if all operations within scope actually accept it. If certain APIs do not support correlation IDs, restrict the customizer by path/group or use dedicated metadata for that endpoint group. OpenAPI describes server capabilities; adding a header to the document does not automatically make Spring MVC read or log that header.

## 5. Customizing metadata for a specific group

Suppose partners are only allowed to view endpoints under `/api/partner/**`. This group needs an audience-specific description while still sharing the contact and correlation header:

~~~java
import io.swagger.v3.oas.models.info.Info;
import org.springdoc.core.customizers.OpenApiCustomizer;
import org.springdoc.core.models.GroupedOpenApi;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class PartnerOpenApiConfiguration {

    @Bean
    GroupedOpenApi partnerApi() {
        OpenApiCustomizer partnerMetadata = openApi -> {
            if (openApi.getInfo() == null) {
                openApi.setInfo(new Info());
            }
            openApi.getInfo()
                .description("Integration documentation for partners.")
                .addExtension("x-audience", "partner");
        };

        return GroupedOpenApi.builder()
            .group("partner-v1")
            .pathsToMatch("/api/partner/**")
            .addOpenApiCustomizer(partnerMetadata)
            .build();
    }
}
~~~

For the group to contain an actual operation for integration tests, the application needs a controller matching the path filter. Minimal example:

~~~java
import io.swagger.v3.oas.annotations.Operation;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;

@RestController
class PartnerOrderController {

    @GetMapping("/api/partner/orders")
    @Operation(operationId = "listPartnerOrders")
    List<PartnerOrderSummary> listOrders() {
        return List.of();
    }
}

record PartnerOrderSummary(String orderId, String status) {}
~~~

This controller only illustrates the mapping and operation included in the group. In a real application, the method invokes a service and returns data conforming to the defined contract.

Here `OpenApiCustomizer` is attached directly to `GroupedOpenApi`, so it only adds the description and extension to `partner-v1`. `GlobalOpenApiCustomizer` from the previous section remains responsible for shared metadata.

Do not register the same group ID via two separate `GroupedOpenApi` beans. If a group needs multiple customizers, chain them on the same builder or decompose the logic into functions invoked from one customizer.

The `x-audience` extension is optional metadata. Consumers understand it only if both sides agree on its name, data type, and meaning. If no specific consumer uses it, standard descriptions in `info` are usually sufficient.

## 6. When to use OperationCustomizer?

Document-level metadata differs from operation-level metadata:

- `GlobalOpenApiCustomizer`: modifies `info`, `externalDocs`, `tags`, `components`, or iterates over all operations in the document.
- `OpenApiCustomizer`: modifies a single OpenAPI document, typically attached to a group or applied to the default document.
- `OperationCustomizer`: modifies an operation based on `HandlerMethod`, such as adding extensions for methods carrying a specific annotation or residing in a given package.

If all operations need a shared header, you can iterate over `paths` inside `GlobalOpenApiCustomizer` as shown above. If only methods annotated with `@InternalApi` need special metadata, use an operation-level customizer and inspect the handler method's annotations. Avoid placing complex endpoint classification logic in a large document customizer when clear group filters or annotations can express it.

## 7. Keeping customizers idempotent across multiple runs

Customizers should be idempotent: running them again must not accumulate duplicates or cause unintended mutations. This is especially important when documents have multiple groups, multiple locales, or are recomputed.

Key principles:

1. Check for `null` before accessing `info`, `components`, `tags`, or `paths`.
2. Check component keys before adding shared components.
3. Check whether a parameter already exists before adding `$ref`.
4. Do not add the same tag multiple times.
5. Do not overwrite title, version, or description declared by a group if the customizer does not own those fields.
6. Do not store a request's `OpenAPI` model in a static or singleton field for reuse across requests.
7. Do not mutate external inputs such as shared configuration lists while the customizer is running.

The sample customizer adds contact/license only when missing, adds external docs only when missing, and checks parameters/tags before appending. If an application must force a standard value overriding every group, document the precedence rule explicitly and test the final output instead of accidentally relying on customizer ordering.

## 8. Do not use customizers to replace business configuration

Customizers modify the generated OpenAPI document. They do not automatically alter:

- Controller request mappings or HTTP methods.
- Spring Security authorization or runtime OAuth2 scopes.
- Bean Validation and service-layer data checks.
- How Jackson serializes/deserializes JSON.
- CORS, rate limits, auditing, or actual correlation ID handling.

For example, adding `X-Correlation-Id` to the document does not cause requests to magically carry that header. The application still needs to read/generate correlation IDs via filters/interceptors and propagate them through logs and downstream services per operational conventions.

Similarly, declaring `security` in OpenAPI does not enable Spring Security. Configure the resource server, authorization rules, and real request tests separately.

## 9. Testing shared metadata in default and group documents

Testing via HTTP confirms that springdoc applied the customizers to the final documents. Example using Spring MVC, MockMvc, and Jackson:

The example assumes the project has `spring-boot-starter-test` in test scope; this dependency provides JUnit Jupiter, AssertJ, and MockMvc test support under Spring Boot's dependency management.

~~~java
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class SharedOpenApiMetadataTest {

    @Autowired
    MockMvc mockMvc;

    @Autowired
    ObjectMapper objectMapper;

    @Test
    void sharedMetadataExistsInDefaultAndPartnerDocuments() throws Exception {
        JsonNode defaultDocument = loadDocument("/v3/api-docs");
        JsonNode partnerDocument = loadDocument("/v3/api-docs/partner-v1");

        assertSharedMetadata(defaultDocument);
        assertSharedMetadata(partnerDocument);

        assertThat(defaultDocument.at("/info/x-audience").isMissingNode()).isTrue();
        assertThat(partnerDocument.at("/info/x-audience").asText())
            .isEqualTo("partner");
        assertThat(partnerDocument.at("/info/description").asText())
            .isEqualTo("Integration documentation for partners.");
    }

    private JsonNode loadDocument(String path) throws Exception {
        String body = mockMvc.perform(get(path))
            .andExpect(status().isOk())
            .andReturn()
            .getResponse()
            .getContentAsString();
        return objectMapper.readTree(body);
    }

    private static void assertSharedMetadata(JsonNode document) {
        assertThat(document.at("/info/contact/name").asText())
            .isEqualTo("API Platform Team");
        assertThat(document.at("/info/contact/email").asText())
            .isEqualTo("api-support@example.com");
        assertThat(document.at("/info/license/name").asText())
            .isEqualTo("Internal API Terms");
        assertThat(document.at("/externalDocs/url").asText())
            .isEqualTo("https://developer.example.com/guides");
        assertThat(document.at(
            "/components/parameters/CorrelationId/name").asText())
            .isEqualTo("X-Correlation-Id");
        assertThat(document.path("tags").findValuesAsText("name"))
            .contains("Platform");
    }
}
~~~

The test verifies that shared metadata appears in both the default document and the `partner-v1` group, whereas the `x-audience` extension appears only in the group. In the OpenAPI model, extensions attached to `Info` are serialized inside the `info` object, so the corresponding JSON Pointer is `/info/x-audience`. If the application protects docs endpoints with security, configure appropriate test authentication; never disable production security just for testing.

To check that the header is referenced on operations, add an assertion for the actual path:

~~~java
JsonNode parameters = partnerDocument.at(
    "/paths/~1api~1partner~1orders/get/parameters"
);
assertThat(parameters.toString())
    .contains("#/components/parameters/CorrelationId");
~~~

In JSON Pointer, `/` characters within a path are escaped as `~1`. Use the exact path and HTTP method of your application's controller. If an operation already declares `X-Correlation-Id` itself, verify the document contains only one effective parameter without duplicates of the same name.

## 10. Unit-testing customizers and idempotency

Alongside integration tests, you can test customizer logic on a minimal OpenAPI model. For example, testing the helper that adds the correlation parameter:

~~~java
import io.swagger.v3.oas.models.Operation;
import io.swagger.v3.oas.models.parameters.Parameter;
import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;

class CorrelationParameterTest {

    @Test
    void doesNotAddDuplicateCorrelationParameter() {
        Operation operation = new Operation()
            .addParametersItem(new Parameter()
                .$ref("#/components/parameters/CorrelationId"));

        SharedOpenApiMetadataConfiguration.addCorrelationId(operation);
        SharedOpenApiMetadataConfiguration.addCorrelationId(operation);

        assertThat(operation.getParameters()).hasSize(1);
    }
}
~~~

The `addCorrelationId` helper in the customizer example is kept package-private so tests in the same package can call it directly. There is no need to expose helpers as public application API just for testing. If you prefer keeping helpers private, verify idempotency via integration tests on the customizer bean instead of using reflection.

## 11. Checking multiple groups and YAML

If the application has multiple groups, verify every group that requires shared metadata. Do not test only the first group and assume every other group receives it:

| Document | Shared metadata | Specific metadata |
| --- | --- | --- |
| `/v3/api-docs` | Contact, license, external docs, tag, correlation parameter | No `x-audience=partner`. |
| `/v3/api-docs/partner-v1` | Same shared metadata | `x-audience=partner`, partner description. |
| `/v3/api-docs/internal-v1` | Same shared metadata if required by policy | May have its own internal description and owner. |

JSON and YAML must represent the exact same metadata. If your pipeline publishes YAML, add tests for the `.yaml` URL, parse the YAML into an object, and verify the fields match JSON. Testing JSON alone does not prove YAML routes, security matchers, or gateway routing work.

## 12. Common mistakes

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| Metadata exists in default doc but missing in groups | Used a regular `OpenApiCustomizer` bean | Use `GlobalOpenApiCustomizer` or attach customizer to the group. |
| Partner metadata appears in every group | Used a global customizer for group-specific data | Switch to an `OpenApiCustomizer` attached to `GroupedOpenApi`. |
| Duplicate tags or parameters | Customizer did not check existing items | Make the customizer idempotent before adding. |
| `$ref` fails to resolve | Operation references a missing parameter component | Register the component in `components.parameters` of the same document. |
| Header appears in OpenAPI but server ignores it | Only edited the doc without implementing filter/interceptor | Implement runtime header handling and test it separately. |
| Title/version overwritten | Multiple places claim ownership of one metadata field | Define precedence and have only one source write that field. |
| Contact or license differs across groups | Group has custom metadata or customizer is not global | Inspect `OpenAPI` bean and `GlobalOpenApiCustomizer` in each document. |
| Tests cannot find the group | `GroupedOpenApi` not registered or path filter mismatch | Check group ID, bean registration, and controller endpoints. |
| JSON is right but YAML is wrong | YAML endpoint or customizer/security routing not tested | Test and parse the YAML document separately. |
| Extension ignored by consumers | Consumer does not understand `x-*` convention | Agree on extension schema and verify consumers before relying on it. |

## 13. Implementation checklist

Before publishing shared metadata, confirm:

1. Baseline metadata, group metadata, and operation metadata have been classified.
2. The `OpenAPI` bean holds only baseline info with identical meaning across documents.
3. `GlobalOpenApiCustomizer` is used for changes required in the default document and all groups.
4. Dedicated `OpenApiCustomizer` instances are attached to the right `GroupedOpenApi`.
5. Shared components are registered in `components` before operations reference them with `$ref`.
6. Customizers check for `null`, duplicate components/tags/parameters, and do not overwrite unowned metadata.
7. Contact, license, external docs, and extensions do not leak internal information.
8. Headers documented in OpenAPI are also supported at runtime.
9. Integration tests verify the default document and each group.
10. Tests confirm group-specific metadata does not leak into other groups.
11. Both JSON/YAML and document download endpoints are verified.
12. Runtime security and authorization are tested independently of document content.

## 14. Application principles

- Use an `OpenAPI` bean for baseline definitions required across all documents.
- Use `GlobalOpenApiCustomizer` for metadata or components that must be added to the default document and all groups.
- Use an `OpenApiCustomizer` attached to `GroupedOpenApi` for metadata belonging to a single group.
- Use operation-level customizers when metadata depends on handler methods.
- Register shared components once and reference them via `$ref`.
- Make customizers idempotent to avoid duplicate tags, parameters, or extensions.
- Add only metadata that reflects actual runtime behavior.
- Test the serialized document, not just bean creation.
- Check the default document, all groups, JSON, and YAML before publishing.

Shared metadata needs a single clear configuration source and the right scope. An `OpenAPI` bean provides baseline definitions; `GlobalOpenApiCustomizer` adds changes required across all documents; group-attached customizers keep audience-specific metadata scoped correctly. When components are referenced via `$ref`, customizers are idempotent, and integration tests verify results in both the default document and each group, your OpenAPI contract stays consistent as the application grows or controllers change.

## References

- [Springdoc OpenAPI FAQ – Customize the OpenAPI object](https://springdoc.org/faq.html)
- [Springdoc OpenAPI v2 FAQ – GlobalOpenApiCustomizer and GroupedOpenApi](https://springdoc.org/v2/faq.html)
- [Springdoc OpenAPI v2 – Getting Started](https://springdoc.org/v2/getting-started.html)
- [OpenAPI Specification – OpenAPI Object](https://spec.openapis.org/oas/latest.html#openapi-object)
- [OpenAPI Specification – Components Object](https://spec.openapis.org/oas/latest.html#components-object)
- [OpenAPI Specification – Reference Object](https://spec.openapis.org/oas/latest.html#reference-object)
