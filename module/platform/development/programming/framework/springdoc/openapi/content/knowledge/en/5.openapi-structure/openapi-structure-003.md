# Contact, license, termsOfService, and API Ownership Information

An OpenAPI document needs to tell integrators who is responsible for supporting the API, which legal terms apply, and which organization publishes the service. In OpenAPI, this information lives inside the `info` object through `contact`, `license`, and `termsOfService`. springdoc-openapi can generate them from Swagger annotations or from an `OpenAPI` bean configured by the application.

These three fields serve different roles:

- `contact` indicates the person or team that consumers can reach when they need API support.
- `license` publishes the license applied to the API.
- `termsOfService` points to the terms of service.

API ownership information also needs to be expressed clearly, though OpenAPI has no standard field named `owner`. You can publish the owning organization through `contact.name` when appropriate, or use a vendor extension such as `x-api-owner` to represent custom metadata. Distinguish between the legal owner, the operations team, and the support contact; these three roles may belong to different organizations.

## 1. Position of Metadata in an OpenAPI Document

The `contact`, `license`, and `termsOfService` fields are part of `info` at the top level:

~~~yaml
openapi: 3.1.1
info:
  title: Orders API
  version: 2.4.0
  description: Order management API for e-commerce applications.
  termsOfService: https://api.example.com/terms
  contact:
    name: Example Platform API Support
    url: https://support.example.com/api
    email: api-support@example.com
  license:
    name: Apache 2.0
    identifier: Apache-2.0
  x-api-owner:
    organization: Example Corporation
    team: Commerce Platform
servers:
  - url: https://api.example.com/v2
paths: {}
~~~

`info` describes the API across the entire document. It does not sit inside individual paths or operations. If the application produces multiple documents using groups, each document can carry its own metadata suited to that API or consumer group.

The two fields `title` and `version` are required in the Info Object. `version` is the version of the OpenAPI document; it does not automatically equal the OpenAPI Specification version in the `openapi` field or the API version in the server URL.

Metadata helps people and tools understand the document's provenance, but it does not automatically grant access, authenticate contacts, or enforce legal terms. Operational and legal rules must still be published and governed in their respective systems.

## 2. Distinguishing contact, license, and termsOfService

| Field | Question the Field Answers | Content Example |
|---|---|---|
| `contact` | Who do I contact when I need API support? | API Support team, support email, ticket portal |
| `license` | What license is published for the API? | Apache-2.0, MIT, or URL to the license text |
| `termsOfService` | What terms of use must users comply with? | URL to terms of service |
| `x-api-owner` | Which organization/unit owns the API by internal convention? | Company name or accountable team |

Do not reuse one URL for all three fields just because that URL contains legal information. A support page is not a license; a source code license is not necessarily the API terms of service; and terms of service are not contact information.

For example, an API may be owned by Example Corporation, operated by Commerce Platform, have support email `api-support@example.com`, be released under the Apache-2.0 license, and be governed by separate terms of service. Each piece of information must go into the right field so consumers and document-reading tools do not misinterpret it.

## 3. What Does the Contact Object Contain?

According to the OpenAPI Specification, the Contact Object has three fields:

| Field | Meaning | Rules |
|---|---|---|
| `name` | Name of the contact person or organization | Descriptive string |
| `url` | Contact information page | Must be a valid URI |
| `email` | Contact email address | Must be in email format |

All three fields are not required to be present simultaneously. However, a public document should have at least one contact channel that someone is responsible for monitoring. If the support email changes over time, use a mailing list or ticketing system managed by the organization rather than an individual employee's personal email.

Example:

~~~yaml
info:
  contact:
    name: API Platform Support
    url: https://support.example.com/api
    email: api-support@example.com
~~~

`contact.name` can be a team, department, or organization name. Avoid naming an individual if the support role needs to outlast that person's tenure on the project.

`contact.url` should point to a support or contact page that consumers can access. Do not use an internal URL such as an employee-only admin portal if the document is published to partners.

`contact.email` should be a mailbox with controlled access and an intake workflow. If the API has no email support channel, you can publish only the contact URL.

## 4. License Object and Choosing URL vs. SPDX Identifier

The License Object has a required `name` field. OpenAPI 3.1 and later additionally support `identifier` for an SPDX license expression. The `identifier` and `url` fields are mutually exclusive; choose only one of the two.

### Using a License URL

This approach is compatible with OpenAPI 3.0:

~~~yaml
info:
  license:
    name: Apache 2.0
    url: https://www.apache.org/licenses/LICENSE-2.0.html
~~~

`name` is the displayed license name. `url` points to the official license text.

### Using an SPDX Identifier in OpenAPI 3.1+

~~~yaml
openapi: 3.1.1
info:
  title: Catalog API
  version: 1.6.0
  license:
    name: Apache 2.0
    identifier: Apache-2.0
~~~

`identifier` should use an exact SPDX value, such as `Apache-2.0` or `MIT`. Do not invent a shortened license name that is not on the SPDX License List.

### Notes When Using OpenAPI 3.0

OpenAPI 3.0 does not define the `identifier` field in the License Object. If the document is exported as 3.0, use `name` and `url`. Do not add `identifier` to a 3.0 document and expect every validator or older tool to understand it.

The `license` field only announces the license associated with the API. It does not prove the organization holds licensing rights for third-party data, content, or upstream systems. Clearly establish what is being licensed before publishing.

## 5. TermsOfService Is a URI to the Terms of Use

`termsOfService` is a URI pointing to the API terms of service. The value must be a valid URI; for public APIs, use HTTPS and ensure the page is externally accessible.

~~~yaml
info:
  termsOfService: https://api.example.com/legal/terms-of-service
~~~

Terms of service may specify:

- Who is allowed to register for and use the API.
- Traffic limits, quotas, and rate limits.
- Rules for protecting credentials and data.
- Prohibited behaviors and abuse handling procedures.
- Responsibilities of the provider and the consumer.
- Procedures for changing terms, terminating, or suspending the service.

OpenAPI only stores the URL. It does not embed the full legal text, record user acceptance, or replace consent mechanisms or contracts in the registration system.

Do not use a Privacy Policy page in place of Terms of Service if that page only describes privacy practices. The two documents may link to each other, but they serve different purposes.

## 6. API Ownership Information Has No Dedicated Standard Field

OpenAPI does not define a fixed field named `owner` or `copyrightHolder` in the Info Object. Therefore, choose a publishing approach based on your needs:

1. Use `contact.name` to indicate the contact team/organization when that organization is also the support point of contact.
2. Use `info.description` to include a sentence stating the owning unit or service provider if this information must be visible to all consumers.
3. Use a vendor extension starting with `x-` when structured metadata is needed for a portal or internal pipeline to read.
4. Use the official terms or legal page to publish ownership, copyright, and licensing scope.

Extension example:

~~~yaml
info:
  title: Partner API
  version: 1.3.0
  contact:
    name: Partner API Support
    url: https://partners.example.com/support
  x-api-owner:
    legal-entity: Example Corporation
    product: Partner Platform
    accountable-team: API Governance
    support-channel: https://partners.example.com/support
~~~

The name `x-api-owner` is an organization-specific convention, not a standard field understood by all OpenAPI consumers. Tools unaware of this extension may ignore it. If other systems need to process the extension, document its schema, valid values, and versioning in internal documentation.

Do not place sensitive information such as internal account names, personal phone numbers, home addresses, or intranet URLs in a public document. Use legal entity names, functional teams, and official contact channels.

## 7. Declaring Metadata with Swagger Annotations

springdoc-openapi supports annotations from Swagger Core. You can place `@OpenAPIDefinition` on a Spring-managed configuration class:

~~~java
import io.swagger.v3.oas.annotations.OpenAPIDefinition;
import io.swagger.v3.oas.annotations.info.Contact;
import io.swagger.v3.oas.annotations.info.Info;
import io.swagger.v3.oas.annotations.info.License;
import org.springframework.context.annotation.Configuration;

@Configuration
@OpenAPIDefinition(
    info = @Info(
        title = "Orders API",
        version = "2.4.0",
        description = "API for managing orders and delivery status.",
        termsOfService = "https://api.example.com/terms",
        contact = @Contact(
            name = "Example Platform API Support",
            url = "https://support.example.com/api",
            email = "api-support@example.com"
        ),
        license = @License(
            name = "Apache 2.0",
            url = "https://www.apache.org/licenses/LICENSE-2.0.html"
        )
    )
)
public class OpenApiMetadataConfiguration {
}
~~~

Annotations make it convenient to declare static metadata close to API configuration. `@Info` maps to the Info Object; `@Contact` maps to the Contact Object; `@License` maps to the License Object.

Place the configuration class in a package scanned by Spring component scan so springdoc detects it. springdoc documentation recommends declaring `@OpenAPIDefinition` on a Spring-managed bean so metadata scanning works reliably and efficiently.

With `@License`, the example uses `name` and `url` so it stays compatible with OpenAPI 3.0 documents as well. If you need the SPDX `identifier` from OpenAPI 3.1+, the model-object configuration shown later is a better fit.

## 8. Using Spring Properties to Manage Environment-Specific Metadata

Contact and terms information can differ between staging and production. You should not edit source code every time a support URL changes. springdoc supports the Spring property resolver for several attributes of Swagger annotations.

`application.yml` example:

~~~yaml
api:
  info:
    title: Orders API
    description: Order management API.
    version: 2.4.0
    terms-of-service: https://api.example.com/terms
    contact:
      name: Example API Support
      url: https://support.example.com/api
      email: api-support@example.com
    license:
      name: Apache 2.0
      url: https://www.apache.org/licenses/LICENSE-2.0.html
~~~

Using placeholders in annotations:

~~~java
@OpenAPIDefinition(
    info = @Info(
        title = "${api.info.title}",
        description = "${api.info.description}",
        version = "${api.info.version}",
        termsOfService = "${api.info.terms-of-service}",
        contact = @Contact(
            name = "${api.info.contact.name}",
            url = "${api.info.contact.url}",
            email = "${api.info.contact.email}"
        ),
        license = @License(
            name = "${api.info.license.name}",
            url = "${api.info.license.url}"
        )
    )
)
~~~

According to current springdoc documentation, the property resolver supports `@Info.title`, `description`, `version`, `termsOfService`; `@Info.license.name/url`; and `@Info.contact.name/email/url`. Do not assume every annotation attribute automatically resolves placeholders.

If using multiple profiles, keep official legal values and public metadata in a controlled production configuration. Do not point production's Terms of Service to an internal page or a test URL accessible only via VPN.

## 9. Configuring Metadata with an OpenAPI Bean

When you need dynamic values, an SPDX identifier, or to combine metadata with other configuration, create an `OpenAPI` bean:

~~~java
import io.swagger.v3.oas.models.OpenAPI;
import io.swagger.v3.oas.models.info.Contact;
import io.swagger.v3.oas.models.info.Info;
import io.swagger.v3.oas.models.info.License;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class OpenApiBeanConfiguration {

    @Bean
    OpenAPI customOpenAPI() {
        Info info = new Info()
            .title("Orders API")
            .version("2.4.0")
            .description("API for managing orders and delivery status.")
            .termsOfService("https://api.example.com/terms")
            .contact(new Contact()
                .name("Example Platform API Support")
                .url("https://support.example.com/api")
                .email("api-support@example.com"))
            .license(new License()
                .name("Apache 2.0")
                .url("https://www.apache.org/licenses/LICENSE-2.0.html"));

        return new OpenAPI().info(info);
    }
}
~~~

For OpenAPI 3.1+, if using an SPDX identifier:

~~~java
License license = new License()
    .name("Apache 2.0")
    .identifier("Apache-2.0");
~~~

Do not set both `url` and `identifier` on the same License Object. If the output is still OpenAPI 3.0, use `url` instead of `identifier`.

An `OpenAPI` bean is well suited when metadata needs to come from Spring configuration, environment variables, or deployment settings. You can inject values via `@Value` or use a properties bean bound with `@ConfigurationProperties`.

## 10. Choosing Annotations or an OpenAPI Bean?

| Criterion | `@OpenAPIDefinition` Annotation | `OpenAPI` Bean |
|---|---|---|
| Static metadata | Concise, easy to read | More verbose |
| Property placeholders supported | Yes, for attributes listed by springdoc | Uses Spring injection directly |
| Dynamic metadata or conditional logic | Limited | Flexible |
| SPDX license identifier | Easier to configure with model object | Can call `License.identifier` with OAS 3.1+ |
| Vendor extension | Can declare annotation extensions | Can call `addExtension` |
| Integrating multiple runtime configs | Less convenient | Well suited |

Choose one primary configuration source for the Info Object. If both annotations and a bean are declared for the same fields, inspect the actual generated document to avoid overwritten metadata or ambiguity over where values come from.

## 11. Per-Group Metadata for OpenAPI Groups

An application may publish multiple documents, such as `public`, `partner`, and `internal`. In that case, each document may need a different contact, license, or terms.

| Group | Contact | License/Terms |
|---|---|---|
| `public` | Public support channel | Public terms of service |
| `partner` | Partner Engineering team | Partner integration terms |
| `internal` | Platform Engineering team | Internal usage policy |

Do not put an internal email address into a public document just because of a shared global configuration. When metadata differs by group, attach a customizer to the specific `GroupedOpenApi`:

~~~java
import org.springdoc.core.models.GroupedOpenApi;
import org.springframework.context.annotation.Bean;

@Bean
GroupedOpenApi partnerApi() {
    return GroupedOpenApi.builder()
        .group("partner")
        .pathsToMatch("/partner/**")
        .addOpenApiCustomizer(openApi -> {
            if (openApi.getInfo() != null) {
                openApi.getInfo().setContact(
                    new io.swagger.v3.oas.models.info.Contact()
                        .name("Partner API Support")
                        .url("https://partners.example.com/support")
                        .email("partner-api@example.com")
                );
                openApi.getInfo().setTermsOfService(
                    "https://partners.example.com/legal/terms"
                );
            }
        })
        .build();
}
~~~

An `OpenApiCustomizer` attached to a `GroupedOpenApi` affects only that group's document. springdoc documentation also distinguishes customizers for the default document from customizers applied to all groups; if you want to share across all groups, see `GlobalOpenApiCustomizer`. Verify the exact scope before modifying metadata.

## 12. Verifying Metadata in Generated JSON and YAML

After running the application, inspect the Info Object from the OpenAPI endpoint:

~~~bash
curl -fsS http://localhost:8080/v3/api-docs | jq '.info'
~~~

Check individual fields:

~~~bash
curl -fsS http://localhost:8080/v3/api-docs | jq '.info.contact'
curl -fsS http://localhost:8080/v3/api-docs | jq '.info.license'
curl -fsS http://localhost:8080/v3/api-docs | jq -r '.info.termsOfService'
curl -fsS http://localhost:8080/v3/api-docs | jq '.info["x-api-owner"]'
~~~

If the application has groups:

~~~bash
curl -fsS http://localhost:8080/v3/api-docs/partner | jq '.info'
~~~

To check YAML:

~~~bash
curl -fsS http://localhost:8080/v3/api-docs.yaml
~~~

Compare the output against expected configuration:

- `info.title` and `info.version` are non-empty.
- `contact.url` is a valid public URI; `contact.email` has valid formatting.
- `license.name` has a value; only `url` or `identifier` is present per the OpenAPI version.
- `termsOfService` points to the current applicable terms.
- `x-api-owner` contains only metadata that the organization permits to be public.

Do not look only at the Swagger UI page. Some UIs may not render all vendor extensions or highlight terms; JSON/YAML is the output to inspect when verifying the document.

## 13. Testing Metadata with MockMvc

You can lock down important fields with an integration test:

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
class OpenApiMetadataTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void documentContainsPublicOwnershipAndLegalMetadata() throws Exception {
        mockMvc.perform(get("/v3/api-docs"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.info.title").value("Orders API"))
            .andExpect(jsonPath("$.info.version").value("2.4.0"))
            .andExpect(jsonPath("$.info.contact.name")
                .value("Example Platform API Support"))
            .andExpect(jsonPath("$.info.contact.email")
                .value("api-support@example.com"))
            .andExpect(jsonPath("$.info.termsOfService")
                .value("https://api.example.com/terms"))
            .andExpect(jsonPath("$.info.license.name")
                .value("Apache 2.0"));
    }
}
~~~

If using `license.identifier`, assert that field specifically and confirm `license.url` does not appear. If using vendor extensions, assert the corresponding JSONPath. For groups with separate metadata, write tests targeting the group endpoint rather than testing only the default document.

## 14. Managing Metadata Across Environments and Releases

Legal and contact information have their own lifecycle separate from the API version. Manage them as reviewed configuration:

1. Host Terms of Service and license text at stable URLs managed by the organization.
2. Use a mailbox or support portal with clear ownership.
3. Keep public metadata in version-controlled configuration or a governed configuration store.
4. Test URLs from an external network before releasing.
5. When the legal entity, contact, or terms change, update the document and follow the corresponding notification process.
6. Archive OpenAPI artifacts with each release to know what metadata the document published at release time.

Do not automatically vary `termsOfService` per deployment if the actual legal terms have not changed. Staging and production may have different API base URLs while still sharing the same legal terms; this should be decided by the service owner.

## 15. Common Mistakes

| Symptom | Possible Cause | How to Fix |
|---|---|---|
| Swagger UI does not show contact | Annotation outside Spring component scan or Info not created | Place configuration in a Spring-managed bean and inspect JSON |
| Wrong contact email | Using an old personal mailbox or invalid string format | Use a support mailbox with a stable lifecycle |
| Contact URL points to intranet | Copied internal URL into public document | Replace with a public support page |
| License does not appear | License name only written inside description | Put it into `info.license` |
| Validator reports license error | Missing `name` or using `identifier` with OpenAPI 3.0 | Add `name`; use `url` for OAS 3.0 or `identifier` for OAS 3.1+ |
| Both license `url` and `identifier` present | Configured both mutually exclusive fields simultaneously | Pick only one |
| TermsOfService points to Privacy Policy by mistake | Confused terms of use with privacy policy | Use the actual Terms of Service URL |
| Placeholders remain unresolved in JSON | Used property resolver on an unsupported attribute or misconfigured | Check springdoc's supported attribute list and output |
| Group metadata unexpectedly identical | Used global `OpenAPI` bean or wrong customizer scope | Attach customizer to the respective group and test each endpoint |
| Owner extension not displayed in UI | UI does not render vendor extensions | Inspect JSON/YAML or configure portal to read the extension |
| Metadata overwritten | Declared both annotations and an `OpenAPI` bean | Pick one primary source and verify final output |
| Legal information outdated | URL changed or terms content was updated | Use stable URLs and a pre-release review checklist |

## 16. Workflow for Finalizing API Ownership Information

Follow this order:

1. Identify the legal entity that owns or provides the API.
2. Identify the operations team and support channels consumers can reach.
3. Identify the license that actually applies to the API; verify with the legal owner.
4. Determine the Terms of Service URL and ensure its content fits the service.
5. Choose standard fields: `contact`, `license`, `termsOfService`.
6. If structured owner information is needed, define vendor extension `x-api-owner` and document the extension schema.
7. Choose annotations or an `OpenAPI` bean to configure metadata.
8. If there are multiple groups, determine shared metadata and per-group metadata.
9. Fetch JSON/YAML from `/v3/api-docs` and check all fields.
10. Run integration tests to prevent metadata loss when upgrading springdoc or changing config.
11. Store the document alongside the release and update legal URLs when changes occur.

## 17. Pre-Publication Checklist

- [ ] `info.title` and `info.version` have clear values.
- [ ] `contact.name` points to the right contact point or organization.
- [ ] `contact.url` is a valid public URI if declared.
- [ ] `contact.email` is a mailbox monitored by a person or workflow.
- [ ] `license.name` accurately describes the license applied to the API.
- [ ] Only `license.url` or `license.identifier` is used, never both simultaneously.
- [ ] `license.identifier` is used only when outputting OpenAPI 3.1 or higher.
- [ ] `termsOfService` points to the actual terms of service.
- [ ] Terms of Service is not confused with Privacy Policy or a support page.
- [ ] Ownership information is not confused with the support contact.
- [ ] Vendor extensions start with `x-` and follow a documented convention.
- [ ] No personal data or internal URLs are exposed publicly.
- [ ] Each group's metadata has been verified separately.
- [ ] JSON/YAML has been inspected after springdoc generates it.
- [ ] Integration tests protect critical metadata fields.
- [ ] Legal and support URLs are verified before each release.

## 18. Official References

- [OpenAPI Specification 3.2.1 — Info Object](https://spec.openapis.org/oas/latest.html#info-object) — `title`, `summary`, `description`, `termsOfService`, `contact`, `license`, and `version` fields.
- [OpenAPI Specification 3.2.1 — Contact Object](https://spec.openapis.org/oas/latest.html#contact-object) — `name`, `url`, and `email` of the contact point.
- [OpenAPI Specification 3.2.1 — License Object](https://spec.openapis.org/oas/latest.html#license-object) — `name`, SPDX `identifier`, and license `url`; `identifier` and `url` are mutually exclusive.
- [OpenAPI Specification 3.0.4 — License Object](https://spec.openapis.org/oas/v3.0.4.html#license-object) — License Object structure in OAS 3.0.
- [springdoc-openapi — Adding API Information](https://springdoc.org/#adding-api-information-and-security-documentation) — declaring metadata with Swagger annotations.
- [springdoc-openapi — Spring property resolver for annotations](https://springdoc.org/#can-i-use-spring-property-with-swagger-annotations) — `@Info`, `contact`, and `license` attributes supporting placeholders.
- [springdoc-openapi — Customizing the OpenAPI object](https://springdoc.org/#can-i-customize-openapi-object-programmatically) — configuring an `OpenAPI` bean and customizers.
- [SPDX License List](https://spdx.org/licenses/) — list of valid SPDX identifiers.

`contact`, `license`, and `termsOfService` clarify who supports the API, which license is published, and which terms apply. Ownership information can be supplemented via vendor extensions when needed, while clearly distinguishing standard metadata from organization-specific conventions. Verify the JSON/YAML generated by springdoc, check each group, and keep legal and contact URLs stable across the release lifecycle.
