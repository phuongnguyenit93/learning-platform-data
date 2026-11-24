# Application Version Information and Environment-Specific Metadata

## 1. Why Does OpenAPI Need Version and Environment Information?

An OpenAPI document does more than list paths and HTTP methods. Its metadata tells clients which API the document describes, which contract version it represents, which server to call, and who owns or supports it.

In Spring Boot, an application may run across multiple environments such as local, development, staging, and production. Each environment can have a different public base URL, description, contact, or documentation distribution policy. At the same time, the application's build version may change frequently while the API contract remains unchanged.

Therefore, manage these information groups separately:

- **OpenAPI Specification version**: the OpenAPI standard version the document conforms to, represented by the `openapi` field.
- **API contract version**: the published API contract version, typically located in `info.version`.
- **Application/build version**: the version of the Spring Boot artifact built and deployed.
- **Source revision**: the commit or revision that produced the artifact, if your organization needs to expose it.
- **Environment metadata**: the environment name and server URL described by the document.

Springdoc OpenAPI generates the document from controllers, DTOs, and configured metadata. You can use an `OpenAPI` bean, annotations, or customizers to supply this information. When values vary by environment, use Spring Boot externalized configuration instead of hardcoding production URLs in Java.

## 2. Distinguishing Three Types of Versions

A common mistake is using the same value for the OpenAPI version, the API version, and the application version.

| Item | Example | Meaning |
|---|---|---|
| OpenAPI Specification version | `3.1.0` | Version of the specification format describing the document |
| API contract version | `1.4.0` | Version of the API contract clients integrate against |
| Application version | `2.8.3` | Version of the deployed Spring Boot artifact |
| Source revision | `a1b2c3d` | Source commit or revision that produced the artifact |

Example beginning of an OpenAPI document:

~~~yaml
openapi: 3.1.0
info:
  title: Catalog API
  version: "1.4.0"
~~~

The `openapi` field indicates the document uses OpenAPI Specification 3.1.0. The `info.version` field indicates the version of the API/document being described. These are not two ways of writing the same version.

If an application is built at version 2.8.3 while the API contract stays at 1.4.0, that is completely reasonable. A new build may contain only internal bug fixes, library updates, or deployment changes without altering the public contract.

Do not automatically increment `info.version` on every build unless your API versioning policy requires it. Conversely, when contract changes impact clients, update the API version according to your organization's versioning rules.

## 3. Common Metadata Fields in the Info Object

The OpenAPI Info Object has these commonly used fields:

| Field | Purpose |
|---|---|
| `title` | API name displayed in Swagger UI and documentation |
| `summary` | Short summary, supported in OpenAPI 3.1 |
| `description` | Description of the API's purpose, scope, and usage |
| `version` | API/document version |
| `termsOfService` | URL to terms of service |
| `contact` | Support team or owner details |
| `license` | License information |

YAML example:

~~~yaml
info:
  title: Catalog API
  summary: Product catalog management API
  description: |
    This API provides endpoints to query, create, and update products.
    Clients must use the security scheme published in the document.
  version: "1.4.0"
  contact:
    name: API Platform Team
    email: api-support@example.com
    url: https://developer.example.com/support
  license:
    name: Internal API Terms
    url: https://developer.example.com/terms
~~~

The `summary` field belongs to OpenAPI 3.1. If your project exports OpenAPI 3.0 or the model dependency does not yet support this field, use `description` for the short overview.

Contact and license links should point to maintained addresses. Do not put personal emails or internal URLs if the documentation is published to partners.

## 4. Declaring Static Metadata with @OpenAPIDefinition

For APIs with static metadata, you can use Swagger Core annotations:

~~~java
@Configuration
@OpenAPIDefinition(
    info = @Info(
        title = "Catalog API",
        version = "1.4.0",
        description = "Product catalog management API.",
        contact = @Contact(
            name = "API Platform Team",
            email = "api-support@example.com",
            url = "https://developer.example.com/support"
        )
    )
)
public class OpenApiDefinitionConfiguration {
}
~~~

These annotations belong to the `io.swagger.v3.oas.annotations` package. Springdoc reads this metadata when building the OpenAPI document.

This approach is straightforward for simple configurations that rarely vary by environment. However, annotations take static values and are inconvenient when title, API version, or server URL must come from environment variables, profiles, or build metadata.

Do not declare the same field across multiple sources without designating a primary source. If both `@OpenAPIDefinition` and an `OpenAPI` bean or customizer modify `Info`, the final result may depend on document generation order and library version. Choose one primary source for global metadata and verify the resulting JSON.

## 5. Using an OpenAPI Bean When Metadata Comes from Configuration

When metadata varies by environment, create an `OpenAPI` bean:

~~~java
@Configuration
public class OpenApiConfiguration {

    @Bean
    public OpenAPI applicationOpenAPI() {
        return new OpenAPI()
            .info(new Info()
                .title("Catalog API")
                .description("Product catalog management API.")
                .version("1.4.0"))
            .servers(List.of(
                new Server()
                    .url("https://api.example.com")
                    .description("Production")
            ));
    }
}
~~~

Springdoc uses this bean as the base metadata for the document and merges operations inferred from controllers.

Model imports in this example come from `io.swagger.v3.oas.models`; `@Configuration` and `@Bean` come from Spring Framework.

An `OpenAPI` bean is appropriate when you need to:

- Read title and version from application properties.
- Choose server URLs by profile.
- Add contact, license, or external documentation.
- Place build metadata in vendor extensions.
- Construct the document from runtime configuration.

If the application already defines an `OpenAPI` bean, extend that bean rather than declaring multiple beans whose merging behavior is unclear.

## 6. Putting Metadata in application.yml

You can centralize environment-varying values in configuration:

~~~yaml
app:
  api:
    title: Catalog API
    version: ${API_CONTRACT_VERSION:1.4.0}
    description: Product catalog management API.
    environment: ${APP_ENV:local}
    server-url: ${PUBLIC_API_URL:http://localhost:8080}
    expose-build-metadata: false
~~~

Here:

- `title` is the API name.
- `version` is the API contract version.
- `description` is the API description.
- `environment` is the environment name.
- `server-url` is the public base URL clients should call.
- `expose-build-metadata` controls whether build information is published.

Spring Boot supports externalized configuration. Placeholders can take values from environment variables or profile settings. For example, `API_CONTRACT_VERSION` can be set by the release pipeline and `PUBLIC_API_URL` by the deployment environment.

Never place passwords, tokens, private keys, or secrets in OpenAPI metadata. The document can be downloaded and shared even when Swagger UI is protected.

## 7. Grouping Configuration with @ConfigurationProperties

With multiple related metadata fields, `@ConfigurationProperties` groups settings into a strongly typed Java object.

Example using a Java record:

~~~java
@ConfigurationProperties(prefix = "app.api")
public record ApiMetadataProperties(
    String title,
    String version,
    String description,
    String environment,
    URI serverUrl,
    boolean exposeBuildMetadata
) {
}
~~~

Register the configuration properties class:

~~~java
@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(ApiMetadataProperties.class)
public class ApiMetadataConfiguration {
}
~~~

Spring Boot binds values from `app.api.*` to the record. Using `URI` represents the server URL structurally instead of manipulating arbitrary strings.

If the project already uses `@ConfigurationPropertiesScan`, let Boot discover the class automatically rather than adding `@EnableConfigurationProperties` for every configuration class.

In larger projects, you can add validation to ensure title and version are non-blank, server URL has a valid scheme, and environment belongs to an allowed set. Choose a validation approach compatible with your Spring Boot version and validation dependencies.

## 8. Creating an OpenAPI Bean from Bound Metadata

Once properties are bound, you can build the document:

~~~java
@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(ApiMetadataProperties.class)
public class OpenApiConfiguration {

    @Bean
    public OpenAPI applicationOpenAPI(ApiMetadataProperties metadata) {
        Info info = new Info()
            .title(metadata.title())
            .description(metadata.description())
            .version(metadata.version());

        OpenAPI openAPI = new OpenAPI()
            .info(info);

        if (metadata.serverUrl() != null) {
            openAPI.addServersItem(
                new Server()
                    .url(metadata.serverUrl().toString())
                    .description(metadata.environment())
            );
        }

        return openAPI;
    }
}
~~~

This example keeps `Info.version` tied to the API contract version and the Server URL tied to the environment. Locally, the document can describe `http://localhost:8080`; in production, the same code can use the production public URL.

Do not generate a server URL from a container hostname or internal address and publish it in public documentation. The `server-url` value must be a URL clients can actually reach.

If an OpenAPI document contains multiple servers, Swagger UI lets users switch between them. List multiple servers only when all of them are supported endpoints allowed for that document's audience. Never include staging, development, or internal hostnames in public documentation just for testing convenience.

## 9. Using Spring Profiles for Environment-Specific Metadata

Keep default values in `application.yml`:

~~~yaml
app:
  api:
    title: Catalog API
    version: "1.4.0"
    description: Product catalog management API.
    environment: local
    server-url: http://localhost:8080
    expose-build-metadata: false
~~~

Staging configuration in `application-staging.yml`:

~~~yaml
app:
  api:
    environment: staging
    server-url: https://staging-api.example.com
~~~

Production configuration in `application-prod.yml`:

~~~yaml
app:
  api:
    environment: production
    server-url: https://api.example.com
~~~

Activate the profile via deployment configuration, for example:

~~~bash
SPRING_PROFILES_ACTIVE=prod
~~~

Spring Boot loads the corresponding profile configuration and overrides defaults. The same artifact can be deployed across environments with distinct metadata.

Avoid building separate artifacts just to change the server URL when externalized configuration already handles it. Reusing the same artifact reduces drift across environments and simplifies build traceability.

## 10. Using Environment Variables in Containers and Pipelines

When running in containers or deployment platforms, pass metadata via environment variables:

~~~text
SPRING_PROFILES_ACTIVE=prod
API_CONTRACT_VERSION=1.4.0
APP_ENV=production
PUBLIC_API_URL=https://api.example.com
~~~

Docker Compose example:

~~~yaml
services:
  catalog-api:
    image: example/catalog-api:2.8.3
    environment:
      SPRING_PROFILES_ACTIVE: prod
      API_CONTRACT_VERSION: "1.4.0"
      APP_ENV: production
      PUBLIC_API_URL: https://api.example.com
~~~

Image tag `2.8.3` is the application build version in this example; `API_CONTRACT_VERSION=1.4.0` is the API contract version. Both values are managed independently.

Pipelines should supply metadata values from controlled sources. Do not allow end users to pass arbitrary query parameters or headers to alter the OpenAPI document's title, version, or server URL in production.

If each request can return different metadata in the document, caching and contract testing become unpredictable. Environment metadata should remain stable throughout a deployment's lifecycle.

## 11. Adding Build Version with Spring Boot BuildProperties

The Spring Boot Maven Plugin provides the `build-info` goal to generate `META-INF/build-info.properties` inside the artifact. Maven configuration example:

~~~xml
<plugin>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-maven-plugin</artifactId>
    <executions>
        <execution>
            <goals>
                <goal>build-info</goal>
            </goals>
        </execution>
    </executions>
</plugin>
~~~

With Gradle, the Spring Boot Gradle Plugin supports:

~~~groovy
springBoot {
    buildInfo()
}
~~~

When the build info file is present in the artifact, Spring Boot provides a `BuildProperties` bean containing details such as artifact, group, name, version, and time.

Without the build-info file, this bean may not exist. Therefore, do not require injecting `BuildProperties` unconditionally if local/test profiles do not generate that metadata. Use `ObjectProvider` or conditional configuration to handle the absent bean case.

Build version should come from the actually running artifact rather than a manually maintained value that could diverge from the packaged version.

## 12. Including Build Metadata in OpenAPI via Vendor Extensions

Build version does not have to replace the API contract version. If you need to display which build is serving the documentation, add a vendor extension:

~~~java
@Configuration(proxyBeanMethods = false)
public class OpenApiConfiguration {

    @Bean
    public OpenAPI applicationOpenAPI(
            ApiMetadataProperties metadata,
            ObjectProvider<BuildProperties> buildPropertiesProvider) {

        OpenAPI openAPI = new OpenAPI()
            .info(new Info()
                .title(metadata.title())
                .description(metadata.description())
                .version(metadata.version()));

        if (metadata.serverUrl() != null) {
            openAPI.addServersItem(
                new Server()
                    .url(metadata.serverUrl().toString())
                    .description(metadata.environment())
            );
        }

        BuildProperties build = buildPropertiesProvider.getIfAvailable();

        if (metadata.exposeBuildMetadata()
                && build != null
                && StringUtils.hasText(build.getVersion())) {
            openAPI.addExtension(
                "x-application-version",
                build.getVersion()
            );
        }

        return openAPI;
    }
}
~~~

In this example, `x-application-version` is an organization-defined vendor extension. The `x-` prefix is used for custom extensions. Clients or tools only understand this extension if specifically designed to read it.

Required imports:

- `org.springframework.boot.info.BuildProperties`
- `org.springframework.beans.factory.ObjectProvider`
- `org.springframework.util.StringUtils`
- Model classes `OpenAPI`, `Info`, and `Server` from `io.swagger.v3.oas.models`

The extension is added only when configuration allows exposing build metadata and the BuildProperties bean is available. By default, leave it disabled if documentation is broadly public.

## 13. Source Revision and GitProperties

In some systems, operations teams want to know which commit produced the running build. Spring Boot can read `git.properties` to provide a `GitProperties` bean if the build is configured to generate this file.

You can conditionally add the revision to the document:

~~~java
GitProperties git = gitPropertiesProvider.getIfAvailable();

if (metadata.exposeBuildMetadata()
        && git != null
        && StringUtils.hasText(git.getShortCommitId())) {
    openAPI.addExtension(
        "x-source-revision",
        git.getShortCommitId()
    );
}
~~~

Add the parameter `ObjectProvider<GitProperties> gitPropertiesProvider` to the bean method and import `org.springframework.boot.info.GitProperties`.

Git metadata may include branch, commit ID, commit time, or repository details. Expose only fields that are truly necessary. Branch names, repository URLs, or commit messages can disclose internal organizational details.

If the goal is solely operational traceability, keep the revision in actuator/build info or internal logs rather than exposing it in public OpenAPI. Availability of the GitProperties bean depends on the build plugin and configuration generating `git.properties`; never assume the bean always exists.

## 14. Do Not Confuse Environment Metadata with Server URL

OpenAPI's `servers` field describes base URLs clients can use to call the API. `info.description` describes the API. An extension like `x-environment` can record the environment name, but it does not replace the Server Object.

Example:

~~~yaml
openapi: 3.1.0
info:
  title: Catalog API
  version: "1.4.0"
servers:
  - url: https://api.example.com
    description: Production
x-environment: production
x-application-version: "2.8.3"
~~~

Here:

- `info.version` is the API contract version.
- `servers[0].url` is the public base URL.
- `servers[0].description` helps readers identify the server.
- `x-environment` is custom metadata.
- `x-application-version` is the build version.

Not every tool understands custom extensions. Client generators typically rely on standard OpenAPI structures; extensions are strictly supplementary information.

If the document is published externally, adding the environment name or build version is not strictly necessary. Expose only what helps clients without revealing topology or deployment details.

## 15. Separate Metadata per Document Group

An application can generate multiple OpenAPI documents using `GroupedOpenApi`. For example, a public API and a partner API can have different titles, versions, or server URLs.

~~~java
@Bean
public GroupedOpenApi partnerApi() {
    return GroupedOpenApi.builder()
        .group("partner")
        .pathsToMatch("/api/partner/**")
        .addOpenApiCustomizer(openApi -> {
            if (openApi.getInfo() != null) {
                openApi.getInfo()
                    .title("Partner API")
                    .version("2.1.0")
                    .description("API for integration partners.");
            }

            openApi.addExtension("x-audience", "partners");
        })
        .build();
}
~~~

The customizer is attached to the group to modify that group's document. Verify how group customizers and the global `OpenAPI` bean are applied in your Springdoc version.

If each group represents a distinct API contract, it can have its own API contract version. Do not assign different versions just because a group runs in a different environment; version reflects the contract, whereas environment reflects where it is deployed.

When using group-specific server URLs, inspect the `/v3/api-docs/partner` endpoint and ensure servers point only to hosts accessible by that group's audience.

## 16. Managing Multiple Environments Without Exposing Internal Endpoints

Some organizations want the same documentation across local, staging, and production. You can choose one of these approaches:

- Generate documents by profile so each environment has its own server URL.
- Publish a single public server and handle routing through an API gateway.
- Distribute a normalized OpenAPI artifact in CI rather than deriving metadata from runtime requests.
- Separate internal and public documents using document groups.

Do not list every hostname such as `localhost`, `staging.internal`, and `prod-db` inside a single public OpenAPI document. Swagger UI allows users to pick a server and send requests to those URLs.

If a document includes multiple Server Objects, every server must actually be supported and appropriate for the audience. Never include database URLs, service discovery addresses, admin hosts, or internal addresses in `servers`.

For production environments, consider configuring an explicit public base URL from deployment manifests or managed environment variables rather than inferring it from untrusted Host headers.

## 17. API Versioning and Contract Changes

`info.version` is the version label of the API/document; it does not automatically create versioned endpoints. For example:

- `/api/v1/products` and `/api/v2/products` are path versioning.
- `info.version: 1.4.0` describes the document's contract version.
- `application.version: 2.8.3` describes the artifact version.

You can use path versioning, media type versioning, or header-based versioning depending on policy. The OpenAPI document should accurately describe how clients select the API version.

When changing the contract:

- Adding optional fields is usually less breaking for clients than removing fields.
- Renaming properties, changing data types, or removing operations can be breaking changes.
- Changing response statuses or security requirements can affect clients.
- Changing paths or parameter names usually requires migration.
- Bumping the application build version is not necessarily a breaking API change.

Use a contract diff or OpenAPI compatibility checker in CI to detect client-impacting changes. Version-increment policies should be clearly defined, such as using semantic versioning for API contracts if suitable for your organization.

Do not let pipelines automatically bump the API version on every commit. Tie API version increments to contract release decisions.

## 18. Using Customizers to Supplement Metadata

If metadata needs to be added after the OpenAPI document is constructed, use an `OpenApiCustomizer`:

~~~java
@Bean
public OpenApiCustomizer environmentMetadataCustomizer(
        ApiMetadataProperties metadata) {
    return openApi -> {
        openApi.addExtension(
            "x-environment",
            metadata.environment()
        );
    };
}
~~~

Customizers work well for adding extensions or updating specific fields. Avoid replacing the entire Info or Servers object when you only need to add one value, as doing so can discard metadata already declared by beans or annotations.

To apply metadata to a single group, attach the customizer to the group's builder instead of applying it globally. If you need it across all documents, verify your Springdoc version's global customizer mechanism.

Extensions must start with `x-`. Never create extension names mimicking standard fields such as `version` or `servers`; use distinct, clearly namespaced names.

## 19. Verifying Metadata in OpenAPI JSON

After the application starts, fetch:

~~~http
GET /v3/api-docs
~~~

Verify these fields:

- `openapi` matches the specification version the application exports.
- `info.title`, `info.description`, and `info.version` match the API contract.
- `servers` has the right public URL and scheme.
- `servers[].description` accurately describes the environment.
- Build metadata extensions appear only when enabled.
- No internal hostnames, secrets, or unintended details for the audience are present.
- Document groups have their configured per-group metadata.

You can use MockMvc to test metadata:

~~~java
mockMvc.perform(get("/v3/api-docs"))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$.info.title").value("Catalog API"))
    .andExpect(jsonPath("$.info.version").value("1.4.0"))
    .andExpect(jsonPath("$.servers[0].url")
        .value("https://api.example.com"));
~~~

If the application has multiple servers, do not assume the target server is always at index 0 unless ordering is explicitly controlled. Parse the JSON and locate the server by URL or description.

Also check document groups:

~~~http
GET /v3/api-docs/partner
~~~

Swagger UI should also be opened under the corresponding profile to confirm title, version, and the server selector render properly.

## 20. Testing Profile Configurations in CI/CD

You can verify each profile via integration tests or by booting the application with dedicated configuration:

| Profile | Value to Verify |
|---|---|
| local | localhost or local URL |
| dev | dev API base URL |
| staging | staging public URL |
| prod | production public URL |

Pipelines should verify:

1. Artifact carries the expected application build version.
2. API contract version is passed accurately.
3. The intended profile is activated.
4. Server URL belongs to the environment's allowlist.
5. OpenAPI JSON contains appropriate metadata.
6. No internal hostnames or internal extensions are exposed.
7. Contract diff finds no unexpected breaking changes.

You can archive OpenAPI JSON as a pipeline artifact and diff it against the previous release. This catches unexpected metadata or schema changes before publishing documentation.

Do not rely on a single OpenAPI snapshot if the document's server URL varies per environment without a normalization policy. Decide whether CI compares pure contracts or deployment metadata as well.

## 21. Common Mistakes When Managing Versions and Metadata

| Symptom | Cause to Investigate |
|---|---|
| info.version changes on every build | Using application build version as the API contract version |
| The openapi field is mistaken for the API version | Confusing OpenAPI Specification version with Info.version |
| Server URL remains localhost in production | Profile or PUBLIC_API_URL was not loaded |
| Swagger UI calls a container hostname | Server URL inferred from internal request or misconfigured |
| Metadata varies between requests | Values taken from request headers or unstable runtime sources |
| BuildProperties bean is missing | Artifact does not contain build-info.properties |
| GitProperties bean is missing | Build did not generate git.properties |
| Document group has wrong title/version | Group customizer or global config overrides metadata |
| Extension does not appear in Swagger UI | UI does not render vendor extensions; inspect JSON directly |
| Internal branch or commit leaked | Unnecessary Git metadata exposed |
| Unexpected multiple servers appear | Uncontrolled mix of beans, annotations, and customizers |
| API version bumps despite unchanged contract | Pipeline auto-increments version from build number |
| OpenAPI document does not reflect profile | Wrong profile or property source precedence |

When investigating, inspect the active environment, values bound into ConfigurationProperties, and the final OpenAPI JSON. Do not check YAML files alone because environment variables or command-line arguments may override settings.

## 22. Principles for Designing Environment Metadata

When managing version information and metadata for Springdoc OpenAPI:

1. Distinguish OpenAPI Specification version, API contract version, and application build version.
2. Use Info.version for the API contract version.
3. Use BuildProperties to read build version from the artifact when needed.
4. Use GitProperties conditionally when source revision traceability is required.
5. Use ConfigurationProperties to group metadata and externalized configuration.
6. Use Spring Profiles or environment variables for environment-specific server URLs.
7. Pick one primary source for global metadata, avoiding unclear overrides across beans/annotations/customizers.
8. Include in the document only server URLs the audience is actually permitted to call.
9. Never publish secrets, internal hostnames, branches, or revisions unless required.
10. Verify both the default document and every document group.
11. Use contract diffs in CI to detect client-impacting changes.
12. Inspect the final OpenAPI JSON rather than relying solely on source configuration.

Version information helps clients identify the API contract; build metadata helps operations trace artifacts; environment metadata tells clients which server to call. When these three groups are managed separately and injected into OpenAPI from controlled configuration, Springdoc documentation stays consistent across local, staging, and production without conflating deployment versions with contract versions.

