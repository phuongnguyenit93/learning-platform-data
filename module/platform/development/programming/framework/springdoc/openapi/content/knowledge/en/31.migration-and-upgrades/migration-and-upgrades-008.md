# Comparing Configuration Properties and Default Values After Upgrading

After upgrading Spring Boot or springdoc-openapi, the application may still start and Swagger UI may still open while the OpenAPI document has changed. The cause does not come solely from properties in application.yml. Library defaults, bundled Swagger UI versions, profile-specific configuration, environment variables, and changes in how Springdoc infers schemas can all alter the output.

Therefore, when upgrading, compare three layers:

1. **Declared properties** in application.yml, application.properties, profiles, environment variables, or command-line arguments.
2. **Effective values** after Spring Boot binds configuration and applies defaults from the new library version.
3. **Output behavior** in OpenAPI JSON/YAML, swagger-config, and the Swagger UI interface.

Do not conclude configuration is compatible simply because the keys in application.yml are unchanged. An undeclared property may receive a different default after upgrading; an unchanged default may still yield different output when Springdoc, swagger-core, or Swagger UI changes how it processes it.

## 1. Distinguish versions before comparing configuration

Several kinds of versions coexist in an application:

| Version type | Example | Meaning |
|---|---|---|
| Spring Boot | 3.5.x or 4.1.x | Runtime platform and Spring ecosystem. |
| springdoc-openapi | 2.10.x or 3.2.x | Library that inspects the Spring application and generates docs. |
| OpenAPI Specification | 3.0.x or 3.1.x | Specification version written in the openapi field. |
| API release version | info.version: 2.4.0 | Product-managed API version. |
| Spring Framework API versioning | Header or query parameter such as X-API-Version | Mechanism for selecting an operation version when the app implements API versioning. |

These versions are independent. Upgrading springdoc 2.x to 3.x does not automatically alter the API's info.version. Switching OpenAPI 3.0 to 3.1 does not mean changing the REST API's URL version. The springdoc.api-docs.version property controls the specification version, not the business version of the API.

## 2. Select springdoc by Spring Boot major version

Choose the right compatible branch before examining properties:

| Spring Boot | springdoc branch | Notes |
|---|---|---|
| 4.x | 3.x | For Spring Boot 4 and Spring Framework 7. |
| 3.5.x | 2.8.x–2.10.x | Use the springdoc 2.x branch. |
| 3.4.x | 2.7.x–2.8.x | Use the springdoc 2.x branch. |
| 3.3.x | 2.6.x | Use the springdoc 2.x branch. |
| 3.2.x | 2.3.x–2.5.x | Use the springdoc 2.x branch. |
| 3.1.x | 2.2.x | Use the springdoc 2.x branch. |
| 3.0.x | 2.0.x–2.1.x | Use the springdoc 2.x branch. |
| 2.x and 1.x | 1.8.0 is the final open-source release for legacy branches | Check extended support policies if still maintained. |

Compatibility matrices change across releases. When upgrading, check the official matrix when selecting a version; do not pick the latest springdoc merely because it is newer.

## 3. Key changes from springdoc v1 to v2

springdoc v2 was built for Spring Boot 3, using Spring Framework 6 and the Jakarta ecosystem. Beyond swapping dependencies, migration may require updating package imports and annotations.

### 3.1. Renamed dependency artifacts

| springdoc v1 | springdoc v2 and v3 |
|---|---|
| springdoc-openapi-ui | springdoc-openapi-starter-webmvc-ui |
| springdoc-openapi-webflux-ui | springdoc-openapi-starter-webflux-ui |
| springdoc-openapi-webmvc-core | springdoc-openapi-starter-webmvc-api |
| springdoc-openapi-webflux-core | springdoc-openapi-starter-webflux-api |
| springdoc-openapi-common | springdoc-openapi-starter-common |

Additional modules such as Data REST, Security, HATEOAS, Kotlin, and Javadoc are integrated via starter-common in v2. Audit old dependencies to avoid keeping superseded artifacts.

Example for Spring MVC needing both OpenAPI documents and Swagger UI:

~~~xml
<dependency>
    <groupId>org.springdoc</groupId>
    <artifactId>springdoc-openapi-starter-webmvc-ui</artifactId>
    <version>2.10.0</version>
</dependency>
~~~

For Spring WebFlux, pick starter-webflux-ui. If only JSON/YAML is needed without a UI, pick starter-webmvc-api or starter-webflux-api accordingly.

### 3.2. Moved packages and classes

| v1 | v2 |
|---|---|
| org.springdoc.core.SpringDocUtils | org.springdoc.core.utils.SpringDocUtils |
| org.springdoc.api.annotations.ParameterObject | org.springdoc.core.annotations.ParameterObject |
| org.springdoc.core.GroupedOpenApi | org.springdoc.core.models.GroupedOpenApi |
| org.springdoc.core.customizers.OpenApiCustomiser | org.springdoc.core.customizers.OpenApiCustomizer |
| org.springdoc.core.Constants | org.springdoc.core.utils.Constants |
| org.springdoc.core.SwaggerUiConfigParameters | org.springdoc.core.properties.SwaggerUiConfigParameters |

OpenApiCustomiser was standardized to OpenApiCustomizer. Update imports and customizer code to match the new version's API instead of bumping only the dependency while keeping old imports.

### 3.3. Migrating from javax to jakarta

Spring Boot 3 moved many Java EE APIs from javax to jakarta. If controllers or DTOs use Bean Validation, Servlet API, or related annotations, check dependencies and imports:

- javax.validation.Valid → jakarta.validation.Valid
- javax.validation.constraints.NotNull → jakarta.validation.constraints.NotNull
- javax.servlet.* → jakarta.servlet.*

If validation annotations stay on the old namespace, Spring Boot 3 may not apply validation as expected; schemas inferred by Springdoc from those annotations may also lack constraints.

## 4. A major default change from v1 to v2

The springdoc.api-docs.version property changed its default between v1 and v2:

| Branch | Default | Meaning |
|---|---|---|
| springdoc v1 | openapi_3_0 | Generates documents following OpenAPI 3.0. |
| springdoc v2 | openapi_3_1 | Generates documents following OpenAPI 3.1. |
| springdoc v3 | openapi_3_1 | Continues using OpenAPI 3.1 per the current property reference. |

This change can directly affect client generators, API gateways, and validators. OpenAPI 3.1 aligns Schema Object closely with JSON Schema Draft 2020-12; nullable, type unions, exclusiveMinimum, and schema keywords may be represented differently than in 3.0.

If upgrading from v1 and needing to preserve a 3.0 contract for downstream systems, declare it explicitly:

~~~yaml
springdoc:
  api-docs:
    version: OPENAPI_3_0
~~~

If all consumers already support 3.1, declare OPENAPI_3_1 explicitly to state intent. Do not rely on defaults for a decision that affects contracts.

Pinning OPENAPI_3_0 preserves only the specification dialect. It does not guarantee schema output identical to v1 because annotation handling, Jackson, swagger-core, and model converters can still change; you must still run a semantic diff after upgrading.

## 5. Common defaults to compare

The table below summarizes common defaults in the v1 property reference and current branches. Unchanged defaults should still be verified because profiles or environment variables can override them.

### 5.1. Core properties

| Property | Common default | Upgrade notes |
|---|---|---|
| springdoc.api-docs.path | /v3/api-docs | Consistent across common branches. |
| springdoc.api-docs.enabled | true | Disabling this turns off the docs endpoint. |
| springdoc.packages-to-scan | * | Changing package scan can drop operations. |
| springdoc.paths-to-match | /* | Path filters control which operations enter the document. |
| springdoc.writer-with-default-pretty-printer | false | Affects JSON formatting only, not semantics. |
| springdoc.writer-with-order-by-keys | false | Enabling yields more deterministic key ordering. |
| springdoc.override-with-generic-response | true | May add generic responses from @ControllerAdvice. |
| springdoc.api-docs.version | v1: openapi_3_0; v2/v3: openapi_3_1 | Default changed in v2; pin if downstream needs 3.0. |
| springdoc.cache.disabled | false | OpenAPI document caching is enabled by default. |
| springdoc.cache.max-entries | 100 in branches with bounded cache | Added in v2.9.1; verify when using multiple locales or many documents. |

### 5.2. Swagger UI properties

| Property | springdoc v1 | springdoc v2 | springdoc v3 | Impact |
|---|---|---|---|---|
| springdoc.swagger-ui.path | /swagger-ui.html | /swagger-ui.html | /swagger-ui.html | HTML page URL. |
| springdoc.swagger-ui.enabled | true | true | true | Toggles UI independently from API docs. |
| springdoc.swagger-ui.configUrl | /v3/api-docs/swagger-config | /v3/api-docs/swagger-config | /v3/api-docs/swagger-config | UI config JSON URL. |
| springdoc.swagger-ui.tryItOutEnabled | true | false | false | Default changed in v2; UI no longer enables Try it out automatically on page load. |
| springdoc.swagger-ui.filter | false | false | false | Filter bar hidden by default. |
| springdoc.swagger-ui.displayOperationId | false | false | false | operationId hidden by default. |
| springdoc.swagger-ui.displayRequestDuration | false | false | false | Request duration hidden by default. |
| springdoc.swagger-ui.docExpansion | Swagger UI: list | Swagger UI: list | Swagger UI: list | Internal Swagger UI default; can be pinned via doc-expansion. |
| springdoc.swagger-ui.operationsSorter | Server order | Server order | Server order | Operations remain unsorted unless configured. |
| springdoc.swagger-ui.tagsSorter | Document order | Document order | Document order | Keeps tag order from the OpenAPI document. |
| springdoc.swagger-ui.supportedSubmitMethods | All methods | All methods | All methods | Methods enabled for Try it out; an empty array disables all. |
| springdoc.swagger-ui.defaultModelsExpandDepth | 1 | 1 | 1 | Model list expansion depth. |
| springdoc.swagger-ui.defaultModelExpandDepth | 1 | 1 | 1 | Individual model expansion depth. |
| springdoc.swagger-ui.persistAuthorization | false | false | false | Does not persist authorization data by default. |
| springdoc.swagger-ui.queryConfigEnabled | false | false | false | Query strings cannot override UI config by default; disabled since v1.6.0. |

Swagger UI has several internal defaults, such as doc expansion and operation/tag sorting. Those values also depend on the Swagger UI version bundled in the starter. If the UI must stay consistent across upgrades, explicitly set key properties such as doc-expansion, operations-sorter, and tags-sorter instead of relying on the UI library's defaults.

To preserve springdoc v1's Try it out behavior after upgrading to v2/v3, declare it explicitly:

~~~yaml
springdoc:
  swagger-ui:
    try-it-out-enabled: true
~~~

The default supportedSubmitMethods still allows all HTTP methods supported by Swagger UI; changing tryItOutEnabled affects only the initial active state of the Try it out panel.

## 6. New properties introduced in newer branches

Not every new property changes an old default. Some only add opt-in capabilities:

| Property | Default in current docs | Impact |
|---|---|---|
| springdoc.cache.max-entries | 100 | Caps cached OpenAPI documents; available since v2.9.1. |
| springdoc.model-converters.polymorphic-converter.one-of-as-ref | false | When enabled, polymorphic schemas can be emitted as component references. |
| springdoc.model-converters.polymorphic-converter.one-of-ref-suffix | Variant | Suffix for component names generated from polymorphic schemas. |
| springdoc.model-converters.java-nullable-property-customizer.enabled | false | Allows JSpecify, Spring, or JSR-305 @Nullable to mark Java properties nullable in schemas. |
| springdoc.model-converters.kotlin-nullable-property-customizer.enabled | true | Preserves nullable support for Kotlin properties. |

These properties appear in newer releases such as v2.9.1/v2.10.0 and current v3 documentation. Check the release notes for your exact patch version before adding them to shared configuration.

## 7. Output changes that can happen even when properties stay the same

Several changes in v3.2.0 affect schemas and OpenAPI output, not just property names:

- **Spring Framework API versioning**: the default API version appears in the version header/query parameter only for operations actually serving that version or handlers without an explicit version. Operations serving other versions no longer list that default version as allowed/default.
- **PagedModel and PageMetadata**: properties are marked required because they are always serialized.
- **MonetaryAmount**: amount and currency are marked required because they are always present in output.
- **Java @Nullable**: a new customizer can mark properties nullable without altering shared component schemas; check the corresponding opt-in property.

These changes can cause client SDKs to generate non-nullable fields or alter advertised version parameters. If your application uses Spring Data Page, MonetaryAmount, Kotlin nullability, or Spring API versioning, inspect schemas after upgrading.

### 7.1. Distinguish default OpenAPI version from default API version

Two similar-sounding concepts have different meanings:

- springdoc.api-docs.version selects OpenAPI 3.0 or 3.1.
- Default API version in Spring Framework API versioning selects the request version when a handler does not specify its own version.

Changing default API version behavior in v3.2.0 does not mean springdoc changed the OpenAPI Specification version. When reading release notes, confirm which version type a property or behavior refers to.

## 8. Determine the effective values actually applied

Reading application.yml shows only one configuration source. Effective values may be overridden by:

- application-{profile}.yml.
- Environment variables.
- Java system properties.
- Command-line arguments.
- Config imports or a config server.
- Default values in classes bound with @ConfigurationProperties.

For example, the same application could run with these environment variables even if application.yml declares neither property:

~~~bash
SPRINGDOC_API_DOCS_VERSION=OPENAPI_3_0
SPRINGDOC_SWAGGER_UI_TRYITOUTENABLED=true
~~~

For environment variables, Spring Boot converts dots to underscores, strips dashes, and uppercases property names. Command-line arguments such as --springdoc.api-docs.version=OPENAPI_3_0 can also override file values. When comparing pre- and post-upgrade behavior, record active profiles and override sources so both runs use identical conditions.

### 8.1. Use Actuator configprops and env

In secured test or admin environments, you can expose the necessary endpoints:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include:
          - health
          - info
          - env
          - configprops
~~~

The two endpoints serve different purposes:

| Endpoint | Purpose |
|---|---|
| /actuator/configprops | Inspect @ConfigurationProperties beans and bound values. |
| /actuator/env/springdoc.api-docs.version | Inspect the property source and origin of a specific property. |

Example:

~~~bash
curl -fsS http://localhost:8080/actuator/configprops
curl -fsS http://localhost:8080/actuator/env/springdoc.api-docs.version
~~~

Actuator endpoints may contain sensitive details. Expose them only in diagnostic environments, protect them with Spring Security/network policies, and apply appropriate sanitization. Never expose env/configprops publicly in production.

### 8.2. Inspect dependency metadata

Spring Boot configuration metadata in META-INF/spring-configuration-metadata.json can list property names, types, descriptions, and defaultValue if published by the library.

When upgrading springdoc:

1. Compare metadata from the old and new artifacts.
2. Find properties that were renamed, deprecated, or removed.
3. Check defaultValue entries in metadata.
4. Cross-check against documentation for the target version branch.
5. Verify effective values via configprops/env and actual output.

Metadata does not replace runtime tests. A property may bind cleanly while document generation behavior still shifts due to processing code or underlying dependencies.

## 9. Pre- and post-upgrade comparison workflow

Run under the same profile, sample data, and deployment config so results remain comparable.

1. **Record baseline dependencies**: save Spring Boot, Spring Framework, springdoc, swagger-core, and Swagger UI versions.
2. **Record baseline configuration**: save application.yml, profiles, environment variables, and relevant command-line properties.
3. **Save old OpenAPI artifacts**: fetch JSON/YAML from the previous release.
4. **Save old Swagger UI config**: fetch swagger-config to record url, urls, OAuth, and UI options.
5. **Upgrade along the right compatibility line**: choose springdoc 2.x for Boot 3 or 3.x for Boot 4.
6. **Update dependencies/imports**: update starter artifacts, packages, and javax/jakarta if required by the migration.
7. **Compare property defaults**: pay attention to api-docs.version, cache, model converters, and UI defaults.
8. **Verify effective values**: inspect via Actuator or configuration beans in tests.
9. **Fetch new OpenAPI artifacts**: use the same profile and data as the baseline.
10. **Semantic diff**: compare paths, operations, parameters, request/response schemas, required flags, nullability, security, and servers.
11. **Inspect Swagger UI**: compare swagger-config, doc fetch URLs, layout, and Try it out.
12. **Run contract/integration tests**: verify runtime still matches the approved contract.

## 10. Pin critical defaults in application.yml

If API consumers are not ready for OpenAPI 3.1, keep 3.0 explicitly:

~~~yaml
springdoc:
  api-docs:
    enabled: true
    path: /v3/api-docs
    version: OPENAPI_3_0
  swagger-ui:
    enabled: true
    path: /swagger-ui.html
    try-it-out-enabled: false
    persist-authorization: false
~~~

Once all downstream systems move to OpenAPI 3.1, update version to OPENAPI_3_1. Do not pin every default property. Explicitly specify only values impacting contracts, security, or user experience that the system needs to keep stable across upgrades.

## 11. Verify output after upgrading

### 11.1. Check OpenAPI dialect and paths

A MockMvc test can confirm the OpenAPI document emits the expected version:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.startsWith;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class SpringdocUpgradeContractTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void publishesExpectedOpenApiVersion() throws Exception {
        mockMvc.perform(get("/v3/api-docs"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.openapi", startsWith("3.1.")));
    }

    @Test
    void keepsExpectedOperationAfterUpgrade() throws Exception {
        mockMvc.perform(get("/v3/api-docs"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.paths['/api/products/{id}'].get").exists());
    }
}
~~~

If pinning OPENAPI_3_0, change the matcher to startsWith("3.0."). Do not hard-code the patch version if it depends on swagger-core or springdoc.

### 11.2. Check Swagger UI config

Fetch the configuration endpoint:

~~~bash
curl -fsS http://localhost:8080/v3/api-docs/swagger-config \
  -o build/swagger-config.json
~~~

Compare url, urls, urlsPrimaryName, oauth2RedirectUrl, and key UI options against the baseline. If configUrl or context path changed, adjust the endpoint accordingly.

### 11.3. Compare OpenAPI artifacts

Save post-upgrade artifacts:

~~~bash
curl -fsS http://localhost:8080/v3/api-docs \
  -o build/openapi-current.json

curl -fsS http://localhost:8080/v3/api-docs.yaml \
  -o build/openapi-current.yaml
~~~

Compare structure rather than doing text-only diffs. Focus on:

- The openapi field and info.version.
- Paths and HTTP methods.
- OperationId.
- Required request fields and response fields.
- Nullability, enums, formats, and default values.
- oneOf/allOf/discriminator and $ref.
- Security schemes and operation security.
- Server URLs and response codes.

## 12. Common pitfalls

- **Upgrading springdoc v1 to v2 without checking OpenAPI version**: default changed from 3.0 to 3.1.
- **Only bumping the dependency version**: starter artifacts, package imports, and Jakarta namespaces may require updates.
- **Using springdoc 3.x with Spring Boot 3**: the 3.x line targets Spring Boot 4.
- **Using springdoc 2.x with Spring Boot 4**: pick the Boot 4 compatible branch.
- **Confusing info.version with api-docs.version**: one is the API release, the other picks the OpenAPI dialect.
- **Assuming YAML properties are effective values**: profiles, env, system properties, and CLI flags can override them.
- **Assuming UI defaults never change**: the Swagger UI dependency may upgrade alongside the starter, changing browser behavior.
- **Overlooking cache max entries**: since v2.9.1 there is a bounded cache defaulting to 100.
- **Overlooking Page/MonetaryAmount requiredness**: new schemas may cause SDKs to emit non-nullable fields.
- **Overlooking API versioning behavior in v3.2.0**: an operation's allowed/default versions may change.
- **Testing only application startup**: you must also inspect OpenAPI JSON/YAML and swagger-config.
- **Exposing actuator env/configprops publicly**: those endpoints can leak sensitive configuration.
- **Relying solely on spring-boot-properties-migrator**: it assists with Spring Boot properties, not comparing springdoc-specific properties.
- **Diffing YAML text only**: key reordering creates noise; use semantic diff for contracts.

## 13. Review workflow

1. **Identify the runtime line**: Spring Boot, Spring Framework, Java, and WebMVC/WebFlux.
2. **Select compatible springdoc line**: v1 legacy, v2 for Boot 3, or v3 for Boot 4.
3. **Compare starters and packages**: update artifacts/modules/imports per the migration guide.
4. **Compare property names**: find deprecated, renamed, or removed properties.
5. **Compare defaults**: especially OpenAPI dialect, cache, and model converters.
6. **Verify effective values**: use configprops/env or configuration beans.
7. **Compare OpenAPI output**: check schemas, paths, security, and servers.
8. **Compare Swagger UI config**: URLs, layout, Try it out, OAuth, and persistence.
9. **Run contract tests**: verify runtime requests/responses.
10. **Document intentional changes**: pin properties if behavior must remain stable across future upgrades.

## 14. Review checklist

- [ ] Spring Boot and springdoc are on the matching compatibility line.
- [ ] Starter artifacts updated per the migration guide.
- [ ] Package imports and javax/jakarta annotations reviewed.
- [ ] Checked default springdoc.api-docs.version.
- [ ] Distinguished OpenAPI version from info.version and API versioning.
- [ ] Compared core property defaults.
- [ ] Compared Swagger UI defaults and bundled version.
- [ ] Checked cache max entries if using v2.9.1 or newer.
- [ ] Checked schema requiredness, nullability, and polymorphic models.
- [ ] Verified effective values via configprops/env or tests.
- [ ] Ran semantic diff between new OpenAPI JSON/YAML and baseline.
- [ ] Verified Swagger UI config and browser runtime behavior.
- [ ] Contract tests pass against actual requests/responses.
- [ ] Actuator diagnostics are secured.
- [ ] Critical defaults pinned if consumers depend on them.

## 15. References

- [springdoc-openapi v1 – Properties for Spring Boot 2](https://springdoc.org/v1/index.html)
- [springdoc-openapi v2 – Migration from v1](https://springdoc.org/v2/migrating-from-springdoc-v1.html)
- [springdoc-openapi v2 – Properties](https://springdoc.org/v2/properties.html)
- [springdoc-openapi current – Properties](https://springdoc.org/properties.html)
- [springdoc-openapi current – Compatibility matrix](https://springdoc.org/index.html#what-is-the-compatibility-matrix-of-springdoc-openapi-with-spring-boot)
- [springdoc-openapi – Releases](https://github.com/springdoc/springdoc-openapi/releases)
- [Spring Boot – Actuator endpoints](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html)
- [Spring Boot – Externalized configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html)

Upgrading Springdoc requires checking dependencies, property defaults, effective values, and generated documentation. The most impactful change from v1 to v2 is the default shifting from OpenAPI 3.0 to 3.1; newer branches also add cache bounds and schema updates for certain models. Capture a baseline before upgrading, verify runtime configuration and semantic diff OpenAPI JSON/YAML before releasing so clients continue reading the contract accurately.
