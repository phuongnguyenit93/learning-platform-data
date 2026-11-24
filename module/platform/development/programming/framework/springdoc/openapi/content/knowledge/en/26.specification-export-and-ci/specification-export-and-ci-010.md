# Stabilizing Output Ordering and Handling Volatile Metadata

When exporting OpenAPI for Git tracking, SDK publishing, or running contract tests in CI, the document must remain stable across builds that do not change the API contract. If only key ordering shifts, diffs can become huge even though the content is unchanged. If metadata such as server URLs, API versions, or locales changes unexpectedly, the pipeline may falsely report that the contract changed.

With springdoc-openapi, three things must be distinguished:

1. **Output structure ordering:** keeping key ordering in JSON/YAML stable so diffs are readable.
2. **Display ordering:** controlling tag and operation ordering inside Swagger UI.
3. **Controlling volatile metadata:** standardizing versions, server URLs, locales, groups, and data added by customizers.

These three concerns are related but do not replace one another. Enabling key sorting does not pin the request host; sorting operations in Swagger UI does not stabilize the OpenAPI JSON file; caching cannot fix metadata generated from an inconsistent source.

## 1. What does deterministic output mean?

Deterministic output means that identical source code, dependencies, configuration, locale, and inputs produce the exact same OpenAPI document in both content and the representation order chosen by the project.

For example, the two documents below are structurally equivalent JSON because object key order does not alter meaning:

~~~json
{
  "openapi": "3.1.0",
  "info": {
    "title": "Order API",
    "version": "1.4.0"
  }
}
~~~

~~~json
{
  "info": {
    "version": "1.4.0",
    "title": "Order API"
  },
  "openapi": "3.1.0"
}
~~~

However, when stored in Git, the two orderings produce different diffs. A single key-order shift can change many lines in a file even when the contract did not change.

Stable output helps:

- Review real API changes.
- Reduce noisy diffs in pull requests.
- Produce reproducible checksums.
- Compare specs across builds.
- Detect breaking changes more reliably.
- Generate consistent SDKs.
- Avoid publishing documents that differ solely due to the runtime environment.

Stability does not mean every value in the spec stays frozen forever. When the API version, schemas, or public servers genuinely change, the document must change accordingly. The goal is that every diff has a clear reason.

## 2. Distinguishing key order from array order

OpenAPI is represented in JSON or YAML. You must distinguish objects from arrays:

- An object is a collection of key/value pairs; key order carries no meaning in JSON.
- An array has element order; order may affect display or how tools interpret it.

For example, paths and components.schemas are objects. Sorting keys alphabetically stabilizes diffs without altering meaning.

Conversely, servers, tags, security, and certain other lists are arrays. Their order can be user-visible or carry meaning in tool selection. Do not apply a blanket sort across all arrays.

| Structure | Data type | How to handle |
|---|---|---|
| paths | Object | Keys can be sorted |
| components.schemas | Object | Keys can be sorted |
| components.responses | Object | Keys can be sorted |
| components.securitySchemes | Object | Keys can be sorted |
| tags | Array | Choose display order intentionally |
| servers | Array | Preserve meaningful selection order |
| security requirements | Array | Preserve exact OR/AND logic and desired order |
| examples | Object or array depending on location | Do not reorder examples arbitrarily |
| enum | Array | May carry presentation order; follow API conventions |

Sorting keys is a presentation operation. Ordering arrays must respect the semantics of each field.

## 3. Enabling deterministic key ordering in springdoc

springdoc provides the springdoc.writer-with-order-by-keys property. This property enables deterministic, alphabetical key ordering when writing the document.

application.yml:

~~~yaml
springdoc:
  writer-with-order-by-keys: true
~~~

application.properties:

~~~properties
springdoc.writer-with-order-by-keys=true
~~~

By default this property is false. When enabled, output is written with more stable key ordering, reducing diffs caused purely by map iteration order or serialization.

It can be used in the export profile:

~~~yaml
springdoc:
  writer-with-order-by-keys: true
  api-docs:
    enabled: true
~~~

Test the generated JSON/YAML on the exact springdoc version you run. If the project has custom serializers, custom OpenAPI converters, or post-processing steps, test those as well.

This property does not automatically normalize dynamic values such as info.version, servers[].url, locale-dependent descriptions, or extensions added by customizers.

## 4. Sorting operations and tags in Swagger UI

Swagger UI has two common sorting options:

- operationsSorter: sorts operations within each tag group.
- tagsSorter: sorts tags.

Example:

~~~yaml
springdoc:
  swagger-ui:
    operations-sorter: alpha
    tags-sorter: alpha
~~~

Or application.properties:

~~~properties
springdoc.swagger-ui.operationsSorter=alpha
springdoc.swagger-ui.tagsSorter=alpha
~~~

operationsSorter can use:

- alpha: sorts operations alphabetically by path.
- method: sorts by HTTP method.
- A custom JavaScript sort function per Swagger UI configuration.

tagsSorter can use alpha or a suitable sort function. If unspecified, Swagger UI preserves the operation order received from the server.

These options change UI display. They do not alter the /v3/api-docs content, do not sort the exported JSON file, and do not affect client generators.

Therefore, if the requirement is stable OpenAPI JSON diffs, you must configure the writer and metadata; enabling operationsSorter alone is not enough.

## 5. Combined configuration example for reviewable output

A configuration can combine writer ordering and UI sorters:

~~~yaml
springdoc:
  writer-with-order-by-keys: true
  swagger-ui:
    operations-sorter: alpha
    tags-sorter: alpha
    display-operation-id: true
~~~

Meaning:

- The writer sorts keys when generating the document.
- Swagger UI displays tags alphabetically.
- Swagger UI displays operations by path.
- Operation IDs are displayed so developers can easily cross-reference client methods.

This configuration serves both file review and lookup experience. If the API needs a specific business order for tags, do not enable sorters just for alphabetical order everywhere.

Define the goal per environment. For example, CI may need deterministic writer ordering for artifact export; production UI may preserve a tag order designed by the API team.

## 6. Standardizing API metadata

OpenAPI metadata typically lives inside info:

~~~yaml
info:
  title: Order API
  description: Order management API
  version: 1.4.0
  termsOfService: https://example.com/terms
  contact:
    name: API Support
    email: api-support@example.com
  license:
    name: Apache 2.0
    url: https://www.apache.org/licenses/LICENSE-2.0
~~~

Distinguish between:

- openapi: the OpenAPI Specification version, e.g. 3.1.0.
- info.version: the API contract version, e.g. 1.4.0.
- Spring Boot application version: the deployed artifact version.
- springdoc version: the documentation-generation library version.

Do not reuse one value for all concepts. Upgrading springdoc from 2.x to 3.x does not mean the business API automatically jumps from 1.4.0 to 3.0.0.

info.version should come from an intentional versioning source, typically the API or release contract version agreed by the team.

## 7. Setting info.version from build configuration

You can supply the API version via application.yml:

~~~yaml
api:
  release-version: 1.4.0
~~~

Then use an OpenAPI bean to configure metadata:

~~~java
import io.swagger.v3.oas.models.OpenAPI;
import io.swagger.v3.oas.models.info.Info;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.Environment;

@Configuration
class OpenApiMetadataConfiguration {

    @Bean
    OpenAPI openApiMetadata(Environment environment) {
        String apiVersion =
            environment.getRequiredProperty("api.release-version");

        return new OpenAPI()
            .info(new Info()
                .title("Order API")
                .description("Order management API")
                .version(apiVersion));
    }
}
~~~

In CI, you can pass the version from the release pipeline or a pinned build property. The same commit and release input must produce the same info.version value.

Do not derive info.version from runtime clock calls like LocalDateTime.now(). If every startup creates a different version, the spec will change even when the API contract has not changed.

If using Maven or Gradle to inject the project version into configuration, check the final value loaded by Spring and ensure the export profile does not accidentally override it.

## 8. Avoiding volatile timestamps in the contract unless necessary

A common mistake is a customizer adding the document generation timestamp:

~~~yaml
info:
  x-generated-at: "2026-11-20T10:15:30Z"
~~~

On every export, the timestamp changes and makes the OpenAPI file differ. This creates noisy diffs, new checksums, and can trigger unnecessary SDK publishing workflows.

If you need to record when the artifact was created, prefer storing it in:

- CI job metadata.
- Artifact name or manifest.
- Release records.
- Build provenance.
- Deployment headers or logs.

If a timestamp must appear in an OpenAPI extension, explicitly classify it as volatile metadata and exclude it from contract comparisons or normalize it to a fixed value during diffing.

Never put secrets, tokens, internal hostnames, or per-user data into descriptions, examples, or extensions.

## 9. Standardizing server URLs

The server URL can be inferred by springdoc from the current request. This is convenient when the application runs behind multiple hostnames or reverse proxies, but it can cause CI artifacts to change depending on which host called the documentation.

For example, the same API called through:

~~~text
http://localhost:8080
https://api.example.com
https://partner.example.com/gateway
~~~

If the document uses a request-inferred server URL, the output can differ. CI running on localhost might export:

~~~yaml
servers:
  - url: http://localhost:8080
~~~

Whereas the published artifact needs:

~~~yaml
servers:
  - url: https://api.example.com
~~~

For published documentation, pick a stable URL source:

- Declare public servers explicitly.
- Take the server URL from a fixed property in the export profile.
- Use ServerBaseUrlCustomizer to normalize inferred URLs.
- Check forwarded headers if the URL must be inferred from a reverse proxy.

Do not export from an arbitrary request and commit an internal URL into the spec.

## 10. Declaring fixed servers for the export profile

You can configure an OpenAPI bean to set the server URL from a property:

~~~yaml
api:
  public-base-url: https://api.example.com/v1
  release-version: 1.4.0
~~~

Example:

~~~java
@Bean
OpenAPI openApiMetadata(Environment environment) {
    String apiVersion =
        environment.getRequiredProperty("api.release-version");
    String publicBaseUrl =
        environment.getRequiredProperty("api.public-base-url");

    return new OpenAPI()
        .info(new Info()
            .title("Order API")
            .version(apiVersion))
        .servers(List.of(
            new Server()
                .url(publicBaseUrl)
                .description("Public API")
        ));
}
~~~

In the CI profile, set a fixed value. The export profile must use the same value across all runs of the same release.

If you need to export a spec not tied to a specific environment, consider a relative `/` server URL or distributing the artifact so consumers configure their own base URL; verify how client tools handle relative servers.

## 11. When should the cache be disabled?

springdoc caches the computed OpenAPI document. By default, caching is enabled; it can be disabled with:

~~~yaml
springdoc:
  cache:
    disabled: true
~~~

In application.properties, the corresponding property name is:

~~~properties
springdoc.cache.disabled=true
~~~

Disabling the cache is useful when metadata depends on the request, for example:

- The server URL changes per host.
- Proxies send different forwarded headers.
- Documents are generated per tenant.
- Locale is chosen per Accept-Language.
- Customizers read request data and intentionally produce varying content.

If the documentation should stay stable and metadata does not depend on the request, keeping the cache enabled usually makes more sense.

Do not disable the cache expecting source code changes to hot-reload in a running process. When controllers, DTOs, or annotations change, the standard approach is building and restarting/redeploying the application.

Disabling the cache does not normalize dynamic data. It only forces the document to be recomputed instead of reusing the cached copy.

## 12. Cache, locale, and Accept-Language

If descriptions or summaries are localized, the same OpenAPI endpoint can return different content depending on Accept-Language.

Example:

~~~bash
curl -H "Accept-Language: vi-VN" \
  http://localhost:8080/v3/api-docs
~~~

~~~bash
curl -H "Accept-Language: en-US" \
  http://localhost:8080/v3/api-docs
~~~

If CI exports Vietnamese documentation in one build and English in the next, the diff will be huge even though the API has not changed.

For stable artifacts:

- Choose a fixed export locale.
- Send the same Accept-Language on every build.
- Keep message bundles and translations under version control.
- Do not let the default locale depend on the CI runner machine.
- If exporting multiple languages, save each locale as a separate artifact.

springdoc's cache can hold one document per requested locale. Preloading locales does not replace specifying the header in the export step.

## 13. Metadata per group and customizer

An application can generate multiple OpenAPI documents with GroupedOpenApi. Each group has its own paths, packages, tags, and customizers.

Distinguish three scopes:

| Mechanism | Scope |
|---|---|
| OpenAPI bean | Shared baseline metadata |
| OpenApiCustomizer | Customizes the default document; per the springdoc FAQ, does not automatically apply to every group |
| GlobalOpenApiCustomizer | Global customization, can apply to grouped documents as well |
| Customizer attached inside GroupedOpenApi | Customizes only that specific group |

Group example:

~~~java
@Bean
GroupedOpenApi partnerApi(OpenApiCustomizer partnerCustomizer) {
    return GroupedOpenApi.builder()
        .group("partner")
        .pathsToMatch("/api/partner/**")
        .addOpenApiCustomizer(partnerCustomizer)
        .build();
}
~~~

If a piece of metadata must appear in all groups, choose an OpenAPI bean or GlobalOpenApiCustomizer according to purpose. If only one group has a custom server URL, contact, or description, attach the customizer to that group.

Do not assume the default document and grouped documents share the same metadata merely because they are generated in the same application.

## 14. Writing deterministic customizers

A customizer should be a transformation function yielding consistent results for the same input. Avoid depending on:

- Current wall-clock time.
- Random numbers.
- CI machine hostnames.
- Unstandardized HashMap iteration order.
- External data not under version control.
- Request user or tenant if the artifact is shared.
- Query results without an ORDER BY.

Example updating the version from configuration:

~~~java
@Bean
GlobalOpenApiCustomizer releaseVersionCustomizer(
    Environment environment
) {
    return openApi -> {
        if (openApi.getInfo() != null) {
            openApi.getInfo().setVersion(
                environment.getRequiredProperty("api.release-version")
            );
        }
    };
}
~~~

This customizer uses a fixed property in the export profile. The same input yields the same info.version.

If a customizer adds tags or servers, define an explicit order. Avoid appending the same element every time the customizer runs without checking whether it already exists, especially when caching is disabled or the document is generated multiple times.

## 15. Sorting tags in the OpenAPI model

If you want tags in the document to always appear alphabetically, you can sort the tag list with a customizer:

~~~java
@Bean
GlobalOpenApiCustomizer stableTagOrder() {
    return openApi -> {
        if (openApi.getTags() != null) {
            openApi.getTags().sort(
                Comparator.comparing(
                    Tag::getName,
                    Comparator.nullsLast(String::compareTo)
                )
            );
        }
    };
}
~~~

The example requires importing GlobalOpenApiCustomizer, Tag, and Comparator matching the project's springdoc/swagger-models version.

Only sort when tag order is not an intentional business order designed by the team. If the team wants important tags to appear first, declare an explicit order instead of sorting alphabetically.

This modifies the OpenAPI model and can affect exported documents—unlike tagsSorter, which only changes how Swagger UI renders them.

## 16. Customizer order and idempotency

An application can have multiple customizers:

- A customizer adding servers.
- A customizer updating Info.
- A customizer adding security schemes.
- A customizer attaching shared responses.
- A customizer sorting tags.

If a customizer depends on the output of an earlier customizer, execution order must be controlled. Do not let one customizer overwrite metadata just added by another.

Several principles:

1. Give each customizer a single clear responsibility.
2. Avoid replacing the entire Info object if only changing the version.
3. Check for null before mutating the model.
4. Avoid adding duplicate elements when a customizer runs multiple times.
5. Keep the same bean/configuration ordering across profiles.
6. Write tests against the final output instead of inferring order from method names.

If using @Order or Spring ordering mechanisms, verify that the specific extension point honors that order in the version in use. Do not infer execution order merely from how beans are declared in a Java file.

## 17. Sorting keys via a JSON post-processing step

If you need to normalize a JSON artifact after downloading, you can use a JSON tool that sorts keys. For example, jq -S sorts object keys:

~~~bash
jq -S . target/openapi.json > target/openapi.sorted.json
~~~

jq -S does not sort arrays automatically. That is beneficial because arrays can carry meaning or display order that must be preserved.

If using a post-processing step:

- Do not alter schema values.
- Do not change number/string/null types.
- Do not strip extensions.
- Do not sort arrays indiscriminately.
- Run a validator after the normalization step.
- Keep the raw file for comparison when investigating serializer issues.

Do not use a plain text sort command on JSON or YAML because it can corrupt nested structures.

## 18. Standardizing build metadata

Several metadata fields are commonly included in OpenAPI:

- info.version.
- info.description.
- info.contact.
- servers.
- externalDocs.
- Extensions starting with x-.

Classify them carefully:

| Metadata | Suggested stable source | Should it vary per build? |
|---|---|---|
| info.title | Module configuration | No |
| info.version | API release version | Only when the release contract changes |
| info.description | Version-controlled source/config | No |
| contact/license | Reviewed configuration | No |
| servers | Public base URL per profile | Only when environment or public endpoint changes intentionally |
| x-build-revision | Commit SHA | Intentionally per commit |
| x-generated-at | Build timestamp | Generally best kept out of the spec |

If build traceability is needed, x-build-revision can be useful because a commit SHA is deterministic for a given source revision. However, do not put all environment variables, internal hostnames, or secrets into extensions.

## 19. Creating a dedicated CI export profile

You can create application-ci.yml to pin metadata:

~~~yaml
springdoc:
  writer-with-order-by-keys: true
  cache:
    disabled: false
  swagger-ui:
    enabled: false

api:
  release-version: 1.4.0
  public-base-url: https://api.example.com/v1
~~~

This profile can:

- Enable the OpenAPI endpoint for export.
- Disable Swagger UI if CI only needs JSON/YAML.
- Enable writer key ordering.
- Keep caching enabled when metadata is stable.
- Use a fixed API version and public base URL.

If exporting a document whose server URL depends on the request, use explicit servers in the profile or pin the request URL/forwarded headers. Never let CI export localhost and commit that artifact for a public API.

The export profile should be version-controlled. Put no secrets in the profile; if authentication is needed to fetch docs, pull credentials from the CI secret store.

## 20. Exporting OpenAPI JSON in CI

A simple workflow is starting the application with the export profile and fetching the spec:

~~~bash
java -jar app.jar --spring.profiles.active=ci
~~~

Once the application is ready:

~~~bash
curl -fsS -H "Accept-Language: en-US" http://localhost:8080/v3/api-docs -o target/openapi.json
~~~

When using multiple groups:

~~~bash
curl -fsS http://localhost:8080/v3/api-docs/public -o target/openapi-public.json
curl -fsS http://localhost:8080/v3/api-docs/partner -o target/openapi-partner.json
~~~

Each group should have its own artifact file and be checked independently. Do not merge multiple groups by concatenating JSON strings.

After downloading:

1. Check the file is non-empty.
2. Check the openapi field.
3. Check info metadata.
4. Check servers.
5. Check critical paths and schemas.
6. Run parser/validator.
7. Compare against the previous release's artifact.

## 21. Exporting YAML if the pipeline requires it

If the application exposes the default YAML endpoint:

~~~bash
curl -fsS -H "Accept-Language: en-US" http://localhost:8080/v3/api-docs.yaml -o target/openapi.yaml
~~~

JSON is usually convenient for processing with jq, parsers, and generators. YAML is convenient for manual review and configuration management systems.

Whichever format you choose, keep the same profile, API version, locale, server URL, group, dependency versions, and customizer configuration.

Do not compare YAML and JSON directly with a text diff and conclude the contract differs. If both formats must be cross-checked, parse them into the same OpenAPI model or normalize to the same representation before comparing.

## 22. Checking the artifact before committing

You can quickly inspect JSON:

~~~bash
jq -e '.openapi and .info.title and .info.version and .paths' target/openapi.json
~~~

Check server URLs:

~~~bash
jq '.servers' target/openapi.json
~~~

Check the list of paths:

~~~bash
jq -r '.paths | keys[]' target/openapi.json
~~~

Check schemas:

~~~bash
jq '.components.schemas | keys' target/openapi.json
~~~

Check for unexpected internal URLs with PowerShell:

~~~powershell
Select-String -Path target/openapi.json -Pattern 'localhost|127\.0\.0\.1|10\.[0-9]+\.[0-9]+\.[0-9]+'
~~~

The last command is a suggested check on Windows. Adjust the pattern to match your system's internal network ranges and hostnames; do not treat a simple regex as a complete security audit.

## 23. Comparing the spec with the previous version

After exporting, compare the new artifact with the released version:

~~~bash
git diff --no-index contracts/released/openapi.json target/openapi.json
~~~

If using a dedicated OpenAPI diff tool, changes can be classified:

- Removed paths or methods.
- New required parameters.
- Request body schema changes.
- Removed response statuses.
- Field type or format changes.
- Narrowed enums.
- Security requirement changes.
- Server URL or media type changes.

Before reviewing, strip or normalize non-contract metadata if generated from the build or request. Do not strip metadata merely because diffs are inconvenient; determine whether that change matters to consumers.

An info.version change may be an intentional release bump. An unnecessary timestamp change may be noise. Both create diffs, yet require different review treatment.

## 24. Distinguishing byte-for-byte diffs from semantic diffs

There are two kinds of comparison:

- **Byte diff:** compares both files character by character.
- **Semantic diff:** parses both documents and compares OpenAPI components by meaning.

Examples:

- Changing object key order: byte diff differs, semantic diff usually does not.
- Changing tag order: byte diff differs and UI may render differently, even though operation contracts did not change.
- Changing response schema from string to integer: both byte diff and semantic diff differ.
- Changing server URL: may leave operation schemas unchanged yet affects client requests.
- Changing info.version: contract metadata changes, requiring review per release policy.

Do not rely on a single comparison for every goal. CI can run both a reproducibility check and an OpenAPI breaking-change check.

## 25. Keeping dependencies and export environment stable

Output can change when dependencies or the environment change, even if controllers remain untouched.

Pin or centrally manage:

- Spring Boot version.
- springdoc-openapi version.
- Resolved swagger-core/swagger-models versions.
- Jackson version.
- Export plugins or generators.
- Java runtime version if it affects serialization.
- Profiles and property sources.
- Locale and timezone.
- Customizer configuration.

Do not use dependency ranges or latest in release pipelines if reproducible artifacts are required.

When upgrading springdoc, schema inference, component naming, or writer behavior may change. Treat OpenAPI diffs as part of dependency upgrades rather than blindly accepting the new file simply because the build passes.

## 26. Handling per-request or per-tenant metadata

Some systems generate documentation per tenant or hostname. In such cases, distinguish shared documentation from genuinely personalized documentation.

If metadata depends on the request:

- Identify the exact fields that vary.
- Verify forwarded headers or tenant context come from trusted sources.
- Disable caching if documents must be recomputed per request.
- Check whether cache keys differentiate the necessary locale/tenant/host.
- Avoid putting user data or secrets into the spec.
- Do not commit a tenant-specific document as the shared contract.

If documents differ only in server URL per domain, consider explicit servers or server variables to avoid generating many near-identical copies.

If documents have different schemas per tenant, consider publishing separate groups or artifacts with clear versions and access controls. Do not rely on an arbitrary request-reading customizer to mutate the contract unpredictably.

## 27. Caching and stability

springdoc caches the computed OpenAPI description by default. It can be disabled with:

~~~yaml
springdoc:
  cache:
    disabled: true
~~~

Keep caching enabled when the document is stable across requests. Disable caching when server URLs or metadata genuinely depend on the current request.

If caching is disabled, customizers may execute multiple times. Therefore, customizers must be idempotent: identical input produces identical output, with no duplicate elements added and no unintended timestamps or random values.

Caching is no substitute for pinning metadata in CI. If the export profile uses a dynamic server URL, caching may simply hold onto an unwanted value longer.

## 28. Testing output stability with automated tests

You can write integration tests verifying basic metadata and output ordering:

~~~java
@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT
)
@AutoConfigureWebTestClient
class StableOpenApiExportTest {

    @Autowired
    WebTestClient webTestClient;

    @Test
    void publishesStableApiMetadata() {
        webTestClient.get()
            .uri("/v3/api-docs")
            .header(HttpHeaders.ACCEPT_LANGUAGE, "en-US")
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.info.title").isEqualTo("Order API")
            .jsonPath("$.info.version").isEqualTo("1.4.0")
            .jsonPath("$.servers[0].url")
                .isEqualTo("https://api.example.com/v1");
    }
}
~~~

This test assumes the test profile pins the server URL and version. If the document is inferred from the request, verify the URL against forwarded headers sent by the test.

You can fetch the document twice under the same configuration and compare the normalized JSON. When comparing, exclude or pin intentionally volatile metadata.

Do not test only a single request. If the application serves multiple groups or locales, test every variant that needs exporting.

## 29. Testing that customizers apply to groups

If using a default OpenApiCustomizer, verify whether it applies to groups. The springdoc FAQ states that OpenApiCustomizer normally applies to the default document; to apply across GroupedOpenApi as well, use GlobalOpenApiCustomizer.

You can write a test:

~~~java
@Test
void appliesGlobalMetadataToGroupedDocument() {
    webTestClient.get()
        .uri("/v3/api-docs/partner")
        .exchange()
        .expectStatus().isOk()
        .expectBody()
        .jsonPath("$.info.version").isEqualTo("1.4.0");
}
~~~

If metadata is meant only for the partner group, test other groups to ensure the customizer does not leak information or add inappropriate servers.

Each group is its own contract artifact. Verify the title, version, servers, security, paths, and schemas of each group.

## 30. Common mistakes

| Symptom | Cause to check |
|---|---|
| Large diffs despite unchanged API | Unstable key order or serializer order |
| Swagger UI is sorted but JSON still differs | operationsSorter/tagsSorter only affect UI |
| Server URL changes between local and CI | Document inferred from different requests |
| Info version changes on every build | Using timestamps or unpinned version source |
| Documentation switches languages | Accept-Language or default Locale differs |
| Group lacks shared metadata | Used OpenApiCustomizer instead of GlobalOpenApiCustomizer |
| Cache retains old server URL | Request-dependent metadata while cache is enabled |
| Disabling cache raises CPU usage | Document recomputed on every request |
| Tag order shifts unexpectedly | Array sorted or customizer lacks deterministic order |
| Enums/examples reversed | Post-processing step sorted all arrays |
| CI exports localhost | Used internal request without fixed public server |
| Spec contains unnecessary timestamps | Customizer adds runtime timestamps |
| Client SDK changes heavily after dependency upgrade | Component naming or schema inference changed |
| YAML and JSON artifacts differ | Different profile, locale, group, or export time |

## 31. Output standardization workflow for CI

A workflow you can apply:

1. Pin Spring Boot, springdoc, and related dependency versions.
2. Use a fixed export profile.
3. Pin info.version per the release contract.
4. Pin server URLs or forwarded headers.
5. Pin Accept-Language.
6. Select which groups to export.
7. Enable springdoc.writer-with-order-by-keys.
8. Decide tag/operation ordering for the UI separately.
9. Verify customizers apply accurately to the default document and groups.
10. Export JSON/YAML.
11. Validate structure and $refs.
12. Compare byte diff and semantic diff.
13. Review changes to schemas, statuses, security, and servers.
14. Store artifacts alongside build provenance.
15. Publish only when contract checks pass.

If metadata depends on the request, disable caching only when necessary; otherwise keep caching enabled to avoid unnecessary document recomputation.

## 32. Checklist

- [ ] Enabled writer-with-order-by-keys when JSON/YAML needs stable key ordering.
- [ ] Distinguished object key order from array order.
- [ ] Did not sort all arrays with a blanket post-processing step.
- [ ] Distinguished operationsSorter/tagsSorter from OpenAPI file ordering.
- [ ] Derived info.version from a stable release contract.
- [ ] Excluded volatile timestamps from the spec unless required.
- [ ] Pinned server URLs or inferred from a trusted proxy.
- [ ] Pinned Locale and Accept-Language in CI.
- [ ] Defined which groups to export.
- [ ] Customizers are deterministic and add no duplicate elements.
- [ ] OpenApiCustomizer and GlobalOpenApiCustomizer are used with the right scope.
- [ ] Cache is disabled only when metadata depends on requests.
- [ ] Dependencies and toolchain are pinned.
- [ ] JSON/YAML artifacts are validated.
- [ ] Reviewed both byte diffs and semantic diffs.
- [ ] CI stores specs alongside build provenance.
- [ ] No secrets, internal hostnames, or unintended tenant data present.

## 33. References

- [springdoc-openapi – Configuration Properties](https://springdoc.org/properties.html)
- [springdoc-openapi – Core Properties](https://springdoc.org/core-properties.html)
- [springdoc-openapi FAQ – Customizing OpenAPI and grouped documents](https://springdoc.org/faq.html)
- [Swagger UI – Configuration](https://swagger.io/docs/open-source-tools/swagger-ui/usage/configuration/)
- [OpenAPI Specification](https://spec.openapis.org/oas/latest.html)
- [jq manual – Sorting object keys](https://jqlang.org/manual/)

Deterministic output requires both consistent serialization ordering and clearly sourced metadata. Use springdoc.writer-with-order-by-keys to reduce key-order diffs, use Swagger UI sorters for display experience, and pin versions, locales, server URLs, and groups during CI export. For metadata that truly depends on the request, disable caching only when per-request recomputation is needed and control the data sources strictly.
