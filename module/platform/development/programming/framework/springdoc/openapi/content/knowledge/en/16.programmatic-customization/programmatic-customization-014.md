# Testing Customizers Independently of Whether the UI Renders Nicely

When customizing OpenAPI with springdoc-openapi, the output to verify is the JSON/YAML document the application publishes. Swagger UI is merely an interface reading that document. A Swagger UI page that looks nice does not prove a customizer added the right metadata, preserved schemas, avoided dropping operations, or created accurate security requirements.

Therefore, test customizers at two levels: unit tests for the OpenAPI model transformation logic and integration tests for the actual document served by the springdoc endpoint. This catches both bugs inside customization code and bugs caused by Spring configuration, groups, customizer scope, or specification generation.

## 1. Identifying Outputs to Test

An OpenAPI document is a machine-readable contract. Key sections typically include:

| Component | What to Verify |
| --- | --- |
| info | title, version, description, contact, license, and terms |
| servers | Base URLs that clients are actually permitted to use |
| paths | Operations matching the right set of endpoints and HTTP methods |
| parameters | Names, locations, types, and required flags |
| requestBody | Media types, schemas, and examples |
| responses | Status codes, content, and schemas |
| components | Referenced schemas, responses, parameters, and security schemes |
| security | Schemes and requirements matching endpoint policies |
| tags and externalDocs | Accurate operation groupings and documentation links |

A customizer may affect one or more sections in this list. Before writing tests, determine exactly which fields the customizer is allowed to change and which fields must remain untouched.

For example, a customizer that only adds contact details to info should be tested to verify:

- Contact appears with the right name and email.
- Existing title, version, and description remain preserved.
- Paths, schemas, responses, and security are not altered unexpectedly.
- The logic applies to the right default document or selected group.

## 2. Distinguishing Customizer Types Before Testing

Springdoc has customization mechanisms with differing scopes. Choosing the wrong customizer type can allow isolated unit tests to pass while the actual group document remains unupdated.

| Mechanism | Scope | How to Test |
| --- | --- | --- |
| Standalone OpenApiCustomizer bean | Default document | Invoke logic directly and inspect /v3/api-docs |
| GlobalOpenApiCustomizer | Default document and groups | Inspect multiple doc endpoints, including each group |
| GroupedOpenApi.builder().addOpenApiCustomizer(...) | The group to which the customizer is attached | Inspect the target group and an unrelated group |
| OperationCustomizer | Processed operations | Inspect each path/method after document generation |
| OpenApiMethodFilter | Filtering which methods appear in docs | Verify operations are present or absent |

For springdoc 2.x and 3.x, GroupedOpenApi normally resides in org.springdoc.core.models; customizers reside in org.springdoc.core.customizers. The springdoc 1.x line uses some different packages. Use the API matching your project's dependencies.

Do not merely verify that a customizer bean is created. Inspect the final document to confirm springdoc applied the bean to the right document.

## 3. Extracting Transformation Logic into Testable Functions

A straightforward way to unit test is separating OpenAPI model update logic into its own method, then having the customizer call that method.

Example adding shared metadata:

~~~java
import io.swagger.v3.oas.models.OpenAPI;
import io.swagger.v3.oas.models.info.Contact;
import io.swagger.v3.oas.models.info.Info;
import org.springdoc.core.customizers.GlobalOpenApiCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class OpenApiConfiguration {

    static void applySharedMetadata(OpenAPI openApi) {
        Info info = openApi.getInfo();
        if (info == null) {
            info = new Info();
            openApi.setInfo(info);
        }

        if (info.getContact() == null) {
            info.setContact(new Contact()
                .name("API Platform Team")
                .email("api-support@example.com"));
        }
    }

    @Bean
    GlobalOpenApiCustomizer sharedMetadataCustomizer() {
        return OpenApiConfiguration::applySharedMetadata;
    }
}
~~~

The applySharedMetadata method only adds contact if absent. It preserves title, version, description, and other Info fields. Extracting the method lets you test the logic without booting Spring or launching Swagger UI.

## 4. Unit Testing Customizer Logic

You can use JUnit 5 to construct a minimal OpenAPI model, invoke the transformation method, and assert the result:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

import io.swagger.v3.oas.models.OpenAPI;
import io.swagger.v3.oas.models.info.Contact;
import io.swagger.v3.oas.models.info.Info;
import org.junit.jupiter.api.Test;

class OpenApiConfigurationTest {

    @Test
    void addsContactAndPreservesExistingInfo() {
        OpenAPI openApi = new OpenAPI()
            .info(new Info()
                .title("Partner API")
                .version("v2")
                .description("Partner contract."));

        OpenApiConfiguration.applySharedMetadata(openApi);

        assertEquals("Partner API", openApi.getInfo().getTitle());
        assertEquals("v2", openApi.getInfo().getVersion());
        assertEquals(
            "Partner contract.",
            openApi.getInfo().getDescription());

        Contact contact = openApi.getInfo().getContact();
        assertNotNull(contact);
        assertEquals("API Platform Team", contact.getName());
        assertEquals("api-support@example.com", contact.getEmail());
    }
}
~~~

This test protects an important invariant: the customizer adds metadata without overwriting group-specific metadata. If an implementation replaces existing Info with a new object, the title/version/description assertions will catch the regression.

Add a case where openApi.getInfo() starts as null to confirm the customizer initializes the object safely:

~~~java
@Test
void createsInfoWhenDocumentHasNoInfo() {
    OpenAPI openApi = new OpenAPI();

    OpenApiConfiguration.applySharedMetadata(openApi);

    assertNotNull(openApi.getInfo());
    assertNotNull(openApi.getInfo().getContact());
}
~~~

## 5. Testing Idempotency and Preventing Shared Mutable State

Customizers may be invoked when springdoc generates multiple documents or rebuilds a document. Logic should avoid appending duplicate entries on repeated runs.

For example, a customizer adding a tag:

~~~java
import java.util.ArrayList;
import io.swagger.v3.oas.models.OpenAPI;
import io.swagger.v3.oas.models.tags.Tag;

static void addOrdersTag(OpenAPI openApi) {
    if (openApi.getTags() == null) {
        openApi.setTags(new ArrayList<>());
    }

    boolean exists = openApi.getTags().stream()
        .anyMatch(tag -> "Orders".equals(tag.getName()));

    if (!exists) {
        openApi.addTagsItem(new Tag()
            .name("Orders")
            .description("Order management operations"));
    }
}
~~~

Testing two invocations:

~~~java
@Test
void addingTagTwiceDoesNotCreateDuplicates() {
    OpenAPI openApi = new OpenAPI();

    OpenApiConfiguration.addOrdersTag(openApi);
    OpenApiConfiguration.addOrdersTag(openApi);

    long count = openApi.getTags().stream()
        .filter(tag -> "Orders".equals(tag.getName()))
        .count();

    assertEquals(1, count);
}
~~~

For servers, security, tags, or response lists, decide explicitly whether the customizer replaces the list or appends entries. Never call add... unconditionally if the customizer can run multiple times.

Never keep a mutable OpenAPI, Info, Components, or List in a static field and share it across multiple groups. Each document should receive objects scoped to itself; shared data should be created fresh or intentionally copied so one group does not mutate another group.

## 6. Unit Testing Group-Specific Customizers

Suppose a partner group requires its own title:

~~~java
static void applyPartnerMetadata(OpenAPI openApi) {
    Info info = openApi.getInfo();
    if (info == null) {
        info = new Info();
        openApi.setInfo(info);
    }
    info.setTitle("Partner API");
    info.setVersion("v2");
}
~~~

Configuration bean:

~~~java
import org.springdoc.core.models.GroupedOpenApi;
import org.springframework.context.annotation.Bean;

@Bean
GroupedOpenApi partnerApi() {
    return GroupedOpenApi.builder()
        .group("partner-api")
        .pathsToMatch("/api/partner/**")
        .addOpenApiCustomizer(
            OpenApiConfiguration::applyPartnerMetadata)
        .build();
}
~~~

A unit test can call applyPartnerMetadata on a synthetic model to verify title and version. Yet that unit test does not prove the group is configured properly or that springdoc actually invokes the customizer. That requires an integration test calling the group's endpoint.

## 7. Integration Testing the JSON Document with MockMvc

Test the actual OpenAPI endpoint using @SpringBootTest and MockMvc. This starts the Spring context, lets springdoc scan controllers, runs customizers, and returns the document just as the running application does.

~~~java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class OpenApiDocumentIntegrationTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void partnerDocumentContainsExpectedMetadata() throws Exception {
        mockMvc.perform(get("/v3/api-docs/partner-api"))
            .andExpect(status().isOk())
            .andExpect(content().contentTypeCompatibleWith(
                MediaType.APPLICATION_JSON))
            .andExpect(jsonPath("$.openapi").exists())
            .andExpect(jsonPath("$.info.title")
                .value("Partner API"))
            .andExpect(jsonPath("$.info.version")
                .value("v2"))
            .andExpect(jsonPath("$.info.contact.name")
                .value("API Platform Team"));
    }
}
~~~

This test does not launch a browser and does not depend on Swagger UI CSS or JavaScript. It directly verifies the JSON document that clients and contract testing tools consume.

If the application customizes springdoc.api-docs.path, use the configured endpoint instead of /v3/api-docs. If documentation is protected by Spring Security, tests must supply appropriate credentials/authorities or configure dedicated test security for the docs endpoint. Never disable production security just to make tests return 200.

## 8. Verifying Operations, Schemas, and References

Correct metadata is not enough. Customizers can accidentally overwrite paths, components, or security. Confirm critical operations remain intact:

~~~java
@Test
void partnerDocumentContainsOnlyExpectedOperations() throws Exception {
    mockMvc.perform(get("/v3/api-docs/partner-api"))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.paths['/api/partner/orders'].get")
            .exists())
        .andExpect(jsonPath("$.paths['/api/admin/users']")
            .doesNotExist())
        .andExpect(jsonPath(
            "$.paths['/api/partner/orders'].get.responses['200']"
        ).exists());
}
~~~

If a response references a schema:

~~~java
mockMvc.perform(get("/v3/api-docs/partner-api"))
    .andExpect(status().isOk())
    .andExpect(jsonPath(
        "$.paths['/api/partner/orders'].get.responses['200']"
            + ".content['application/json'].schema['$ref']"
    ).value("#/components/schemas/PartnerOrder"));
~~~

Also verify the target component exists:

~~~java
mockMvc.perform(get("/v3/api-docs/partner-api"))
    .andExpect(status().isOk())
    .andExpect(jsonPath(
        "$.components.schemas.PartnerOrder.type"
    ).value("object"));
~~~

JSONPath expressions must match your project's actual paths and schemas. These assertions catch customizers that accidentally delete components or create broken $refs.

## 9. Testing GlobalOpenApiCustomizer Across Multiple Groups

A GlobalOpenApiCustomizer must be tested on the default document and across groups. Calling only /v3/api-docs is insufficient.

Example:

~~~java
@Test
void sharedMetadataIsPresentInEveryGroup() throws Exception {
    mockMvc.perform(get("/v3/api-docs/public-api"))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.info.contact.name")
            .value("API Platform Team"));

    mockMvc.perform(get("/v3/api-docs/partner-api"))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.info.contact.name")
            .value("API Platform Team"));
}
~~~

Besides shared metadata, verify each group preserves its own details:

~~~java
@Test
void groupsKeepTheirOwnTitles() throws Exception {
    mockMvc.perform(get("/v3/api-docs/public-api"))
        .andExpect(jsonPath("$.info.title").value("Public API"));

    mockMvc.perform(get("/v3/api-docs/partner-api"))
        .andExpect(jsonPath("$.info.title").value("Partner API"));
}
~~~

This catches bugs where a global customizer replaces the entire Info and erases per-group titles. If groups are configured dynamically, load the group list from test configuration and verify each corresponding endpoint.

## 10. Verifying Security Schemes and Security Requirements

A customizer can add a security scheme to components.securitySchemes, but that does not mean every operation requires that scheme.

Example verifying the scheme:

~~~java
mockMvc.perform(get("/v3/api-docs/partner-api"))
    .andExpect(status().isOk())
    .andExpect(jsonPath(
        "$.components.securitySchemes.bearerAuth.type"
    ).value("http"))
    .andExpect(jsonPath(
        "$.components.securitySchemes.bearerAuth.scheme"
    ).value("bearer"));
~~~

If a group contains both public and protected operations, verify requirements at the right level. A document-level security requirement can apply by default to all operations; individual operations can override or clarify requirements per OpenAPI rules. Confirm the generated JSON reflects the intended policy.

OpenAPI security metadata does not replace runtime authorization tests. Write separate tests calling live endpoints with valid tokens, missing tokens, or insufficient permissions to verify Spring Security.

## 11. Verifying JSON/YAML Instead of Relying on Swagger UI

Swagger UI can change versions, styling, themes, layouts, or JavaScript. Such changes do not necessarily alter the OpenAPI contract.

When testing customizers, prioritize:

- Calling JSON/YAML endpoints.
- Parsing the document into a JSON tree or OpenAPI model.
- Asserting critical fields.
- Verifying $refs, media types, operations, and security.
- Running validators or contract diffs where appropriate.

Do not rely on screenshots or Swagger UI CSS selectors as sole proof that a customizer works. The UI may display only a subset of metadata or hide certain details; the JSON/YAML document is the structured output that must be verified.

If a project only needs to export specifications for CI or a developer portal without an interactive UI, the springdoc-openapi-starter-webmvc-api or springdoc-openapi-starter-webflux-api starter can serve the need without bundling Swagger UI. Even when using a *-ui starter, contract tests should still call the OpenAPI endpoints directly.

## 12. Verifying YAML and Multiple Output Formats

If the system publishes both JSON and YAML, confirm both representations describe the exact same contract. Default paths typically include /v3/api-docs for JSON and /v3/api-docs.yaml for YAML; paths may vary with springdoc configuration.

A YAML endpoint test can check status and content type:

~~~java
mockMvc.perform(get("/v3/api-docs.yaml"))
    .andExpect(status().isOk())
    .andExpect(content().contentTypeCompatibleWith(
        MediaType.valueOf("application/vnd.oai.openapi")));
~~~

Actual Content-Type may vary across versions and configurations. Verify your application's response headers before locking down assertions. To check contents, parse the YAML using an appropriate parser library in your project and assert fields equivalent to JSON.

For groups, YAML URLs may depend on endpoint configuration and springdoc version. Never assume a suffix; inspect the actual route exposed in your application.

## 13. Testing Customizers Under Failure and Edge Conditions

Beyond happy paths, test conditions that could break a customizer:

| Condition | Expected Outcome |
| --- | --- |
| openApi.getInfo() is null | Customizer creates a valid Info before updating |
| components do not exist yet | Customizer initializes safely if adding components |
| Target schema does not exist | Skips cleanly or reports a clear configuration error |
| Tag already exists | Does not add unintended duplicates |
| Customizer invoked twice | Does not create duplicate servers, tags, or security requirements |
| Group has no matching operations | Empty document or well-defined behavior per configuration |
| Multiple groups exist | Shared metadata applied, specific metadata not overwritten |
| Customizer sets server URLs | Does not expose localhost or internal hosts in public docs |
| Existing security schemes | Does not overwrite other schemes or drop required security items |

If a customizer relies on environment configuration, test each profile or inject explicit test properties. Never use random data or current timestamps in documentation without reason; constantly changing values complicate contract diff analysis.

## 14. Contract Diffs and Snapshots

For APIs with multiple groups, you can save normalized OpenAPI documents as CI artifacts or compare against prior releases. The goal is catching unintended contract changes:

- Removed operations or changed HTTP methods.
- Newly added required fields.
- Changed data types or formats.
- Removed response statuses or schemas.
- Expanded or narrowed security requirements.
- Unplanned server URL changes.
- $refs pointing to components that no longer exist.

Full-JSON snapshot tests can be overly sensitive to field ordering, library versions, or unstable metadata. It is better to normalize documents before comparing or assert meaningful properties directly. If using snapshots, update them only with review when contract changes are approved.

Contract diffs should run on every group, not solely the default document. A global customizer can alter all groups simultaneously.

## 15. Testing Workflow in CI

An effective pipeline can proceed in this order:

1. Unit test OpenAPI model transformation methods: verify added fields, preserved fields, and idempotency.
2. Boot the Spring test context: confirm customizer and GroupedOpenApi beans are registered.
3. Call JSON endpoints for each group: verify metadata, paths, schemas, $refs, and security.
4. Call YAML endpoints if the application publishes YAML: parse and verify equivalent content.
5. Run an OpenAPI validator or contract diff against the supported specification version.
6. Run separate runtime authorization tests for business endpoints and documentation endpoints.
7. Save generated documents as artifacts for review or distribution.

There is no need to launch a browser in the pipeline just to validate a customizer. If the team wants to test Swagger UI, treat that as an extra UI smoke test layer, not a replacement for contract verification.

## 16. Common Pitfalls

| Symptom | Cause | Resolution |
| --- | --- | --- |
| Unit tests pass yet group lacks metadata | Tests only called helper; bean not attached to GroupedOpenApi | Add integration test calling /v3/api-docs/{group} |
| Default document right yet group wrong | Used OpenApiCustomizer instead of GlobalOpenApiCustomizer or group-level customizer | Pick the right customizer scope and verify every document |
| Contact appears yet title vanishes | Replaced entire Info object | Update only the fields that need changing |
| Duplicate tags or servers | Customizer appends items without checking existence | Make logic idempotent |
| Broken $ref after customization | Component deleted or not added to the group's document | Inspect components in each document |
| Security scheme right yet operation permissions wrong | Confused scheme with security requirement | Check both levels in OpenAPI and run runtime authorization tests |
| Swagger UI looks right yet JSON is wrong | Only checked UI or UI hides certain metadata | Assert JSON/YAML directly |
| Snapshot changes constantly | Document has dynamic data or unstable ordering | Normalize and compare only meaningful fields |

## 17. Pre-Completion Checklist for Customizers

- [ ] Identified the right customizer type and document scope.
- [ ] Unit tested OpenAPI model transformation logic.
- [ ] Preserved metadata and components outside the change scope.
- [ ] Verified customizers can run repeatedly without creating duplicates.
- [ ] Integration tests call OpenAPI endpoints for the default document and every relevant group.
- [ ] Verified paths, request/response schemas, and $refs.
- [ ] Verified servers, security schemes, and security requirements.
- [ ] Verified JSON and YAML if both are published.
- [ ] Ran validators or contract diffs where appropriate.
- [ ] Tested runtime authorization independently of documentation.
- [ ] Did not rely on Swagger UI visual state as sole proof.

A well-tested customizer produces a structurally valid OpenAPI document, leaves unrelated sections untouched, and applies accurately to every group. By testing JSON/YAML and model transformation logic directly, teams can verify API contracts without depending on the Swagger UI interface.

## References

- [springdoc-openapi – FAQ and customizers](https://springdoc.org/faq.html)
- [springdoc-openapi – Documentation](https://springdoc.org/)
- [OpenAPI Specification – OpenAPI Object](https://spec.openapis.org/oas/latest.html#openapi-object)
- [OpenAPI Specification – Paths Object](https://spec.openapis.org/oas/latest.html#paths-object)
- [Spring Boot – Testing](https://docs.spring.io/spring-boot/reference/testing/index.html)
- [Spring Framework – MockMvc](https://docs.spring.io/spring-framework/reference/testing/mockmvc.html)
