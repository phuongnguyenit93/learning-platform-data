# Distinguishing Contract Export from Client or Server Code Generation

Springdoc-openapi and OpenAPI Generator both work with OpenAPI, but they solve two different jobs. **Springdoc exports the API contract from a running Spring Boot application**; **OpenAPI Generator reads a contract to generate client code or a server code skeleton**. Understanding the data direction helps place each tool in the right build stage, avoiding the misconception that having an OpenAPI file means you already have an SDK or a server implementation.

With the SPRINGDOC_OPENAPI module, the typical flow is:

1. Spring Boot controllers, DTOs, validation, and annotations provide information about the API.
2. Springdoc analyzes the application and produces OpenAPI JSON/YAML.
3. CI captures the specification as a versioned artifact.
4. CI validates the specification and then uses OpenAPI Generator to generate a client SDK or server stub if the project needs one.

## 1. Distinguishing the three outputs

| Task | Input | Output | Typical tool |
|---|---|---|---|
| Contract export | Controllers, DTOs, Spring configuration, validation, and OpenAPI annotations in the application | OpenAPI JSON/YAML | springdoc-openapi |
| Client code generation | Approved OpenAPI JSON/YAML file | SDK, API classes, models, serializers, and HTTP client | OpenAPI Generator with a CLIENT generator |
| Server code generation | Approved OpenAPI JSON/YAML file | Server project, API interface/controller stubs, models, and bootstrap configuration | OpenAPI Generator with a SERVER generator |

Examples:

- Springdoc inspects ProductController and exports the GET /api/products/{id} operation along with the ProductResponse schema.
- OpenAPI Generator reads that operation and generates ProductApi along with the ProductResponse model in a Java client.
- If you choose the spring server generator, the tool can generate a Spring Boot server skeleton with the corresponding API contract for the development team to fill in business logic.

The OpenAPI file is an intermediate contract. It is neither client source code nor a server implementation.

## 2. Two common API workflows

### 2.1. Code-first: implement first, export contract later

In the code-first model, the development team writes controllers, DTOs, validation, and annotations in Spring Boot. Springdoc reads those components to generate the documentation:

~~~mermaid
flowchart TD
    A[Spring Controller + DTO + Validation] --> B[springdoc-openapi]
    B --> C[OpenAPI JSON / YAML]
    C --> D[Validate and Review]
    D --> E[Client SDK]
    D --> F[API documentation portal]
    D --> G[Contract artifact]
~~~

This flow fits when the Spring Boot application is already the primary source of implementation. The contract is extracted from running code or from a build/test environment with configuration equivalent to production.

### 2.2. API-first: approve contract first, generate skeleton later

In the API-first model, the development team writes and reviews the OpenAPI specification before implementing:

~~~mermaid
flowchart TD
    A[OpenAPI contract] --> B[Validate and Review]
    B --> C[Generate server stubs]
    B --> D[Generate client SDK]
    C --> E[Implement business logic]
    E --> F[Spring Boot application]
    F --> G[springdoc or contract verification]
~~~

Server stubs create a starting point for implementing controllers/interfaces according to the contract. The client SDK can be published for frontend or other services before the server is complete. Once the server runs, you need to verify that the actual API still matches the approved contract.

Both approaches can coexist. Whether code-first or API-first, the team needs to establish one authoritative contract source and a process for handling drift between code and OpenAPI.

## 3. Springdoc exports OpenAPI at runtime

When integrating springdoc into Spring Boot, the application typically exposes these endpoints:

| Format | Default URL | Purpose |
|---|---|---|
| OpenAPI JSON | /v3/api-docs | Machine-readable for validation, diffing, and code generation. |
| OpenAPI YAML | /v3/api-docs.yaml | Artifact easy to review in Git and pull requests. |
| Swagger UI | /swagger-ui.html | Users browse operations, schemas, and try requests. |

If GroupedOpenApi is configured, each group's documentation typically has a URL of the form /v3/api-docs/{group}. Paths may vary depending on springdoc.api-docs.path, context path, or deployment configuration.

Example fetching JSON and YAML documentation from a running application:

~~~bash
curl -fsS http://localhost:8080/v3/api-docs -o build/openapi/catalog.json
curl -fsS http://localhost:8080/v3/api-docs.yaml -o build/openapi/catalog.yaml
~~~

The -f option causes curl to fail on non-successful HTTP statuses; -sS keeps output quiet while still showing errors. CI should check the exit code and output file before moving to the next step.

### 3.1. Exporting documentation in CI

CI can start the application with a test profile, wait for the health check to succeed, and then download /v3/api-docs or /v3/api-docs.yaml. You must use the same profiles, feature flags, and configuration affecting the API as the environment the contract represents.

A simple flow:

1. Build the application.
2. Start the application in an integration-test environment.
3. Wait for the readiness or health check endpoint to succeed.
4. Download OpenAPI JSON/YAML.
5. Verify the file is non-empty and contains openapi, info, and paths fields.
6. Validate and review changes.
7. Save the file as a CI artifact.

If CI cannot start the application, you can use an integration test step or a dedicated pipeline to produce the specification. Do not hand-craft an OpenAPI file by copying a few endpoints and treat it as springdoc's output.

### 3.2. Exporting a contract does not mean generating code

After downloading /v3/api-docs, you only have a document describing the API. To get a Java client, TypeScript SDK, or server stub, you must invoke a separate code generator with the specification file as input.

Springdoc does not automatically generate an ApiClient, HTTP transport, SDK models, or server controller implementations just because it exports JSON/YAML. Swagger UI also only presents and tests the contract; it does not generate SDKs for the project.

## 4. OpenAPI Generator generates code from the contract

OpenAPI Generator takes an OpenAPI file and selects a generator matching the desired output. Two common Java choices:

| Generator name | Type | Output |
|---|---|---|
| java | CLIENT | Java client library, API classes, models, and HTTP client per the chosen library. |
| spring | SERVER | Java Spring Boot server application/stubs, APIs, and models. |

Do not confuse OpenAPI Generator's spring generator with the springdoc-openapi library. The spring generator produces server code from a contract; springdoc is a library running inside Spring Boot to export OpenAPI documentation.

Generator lists, stability levels, and options change across versions. Inspect the generator before adding it to a pipeline:

~~~bash
openapi-generator-cli list
openapi-generator-cli config-help -g java
openapi-generator-cli config-help -g spring
~~~

The list command shows available generators; config-help shows options supported by that specific generator. Do not copy options from the Java generator to the Spring generator without verifying them first.

### 4.1. Generating a Java client via CLI

Example creating a Java SDK from catalog.yaml:

~~~bash
openapi-generator-cli generate \
  -i build/openapi/catalog.yaml \
  -g java \
  -o build/generated/catalog-client \
  --api-package com.example.catalog.client.api \
  --model-package com.example.catalog.client.model \
  --additional-properties=library=webclient,dateLibrary=java8,hideGenerationTimestamp=true
~~~

In the example:

- -i specifies the input OpenAPI file.
- -g java selects the Java client generator.
- -o is the directory for generated code.
- api-package and model-package separate API classes from models.
- library=webclient chooses the HTTP client library for the Java generator.
- hideGenerationTimestamp=true helps reduce unnecessary diffs between code generation runs.

Libraries and options may vary by generator version. Use config-help -g java to confirm before applying.

The generated code is a client SDK. Applications use the SDK to call the API over HTTP; the SDK does not contain the API server implementation.

### 4.2. Generating server stubs for Spring

Example creating a Spring server skeleton:

~~~bash
openapi-generator-cli generate \
  -i build/openapi/catalog.yaml \
  -g spring \
  -o build/generated/catalog-server \
  --api-package com.example.catalog.server.api \
  --model-package com.example.catalog.server.model \
  --additional-properties=apiFirst=true
~~~

The spring generator is a server generator. The apiFirst option indicates generating APIs from the OpenAPI specification during the server's compile phase via the mechanism supported by the generator.

Server stubs establish API and model structures consistent with the contract. The development team still needs to implement services, repositories, authorization, transactions, business validation, persistence, observability, and error handling. Do not treat scaffolded code as a complete production server.

### 4.3. Choosing the right generator

Before generating code, check:

- Does the generator have the right CLIENT or SERVER type for your purpose?
- Is the generator status STABLE, BETA, or EXPERIMENTAL?
- Are the HTTP client library, framework, and runtime version compatible?
- Do options for nullability, date/time, enums, and discriminators meet the contract?
- Does the generated code comply with license, dependency, and security policies?
- Is the input's OpenAPI version fully supported?

OpenAPI Generator currently announces OpenAPI 3.1 support in beta status. If the contract uses 3.1, you must test the specific generator and schemas in use, run validation/generation on the exact pinned version, and review the output. Do not assume all generators support all 3.1 keywords equally.

## 5. Integrating OpenAPI Generator into Maven

If the project uses Maven, you can place generation in the generate-sources lifecycle phase. The example below generates a Java client from a contract stored in the repository:

~~~xml
<build>
    <plugins>
        <plugin>
            <groupId>org.openapitools</groupId>
            <artifactId>openapi-generator-maven-plugin</artifactId>
            <version>7.27.0</version>
            <executions>
                <execution>
                    <id>generate-catalog-client</id>
                    <phase>generate-sources</phase>
                    <goals>
                        <goal>generate</goal>
                    </goals>
                    <configuration>
                        <inputSpec>src/main/openapi/catalog.yaml</inputSpec>
                        <generatorName>java</generatorName>
                        <output>target/generated-sources/openapi/catalog-client</output>
                        <apiPackage>com.example.catalog.client.api</apiPackage>
                        <modelPackage>com.example.catalog.client.model</modelPackage>
                        <configOptions>
                            <library>webclient</library>
                            <dateLibrary>java8</dateLibrary>
                            <hideGenerationTimestamp>true</hideGenerationTimestamp>
                        </configOptions>
                    </configuration>
                </execution>
            </executions>
        </plugin>
    </plugins>
</build>
~~~

Run:

~~~bash
./mvnw clean compile
~~~

The plugin runs the generate goal in the configured phase. Code is generated into target, which is a regenerable build directory. Check the README/plugin documentation for the exact version to learn how to register generated source roots and configure skip/cleanup options matching your project setup.

### 5.1. When should generation be placed at generate-sources?

Place generation at generate-sources when the generated code is source input required before compilation. Subsequent phases such as compile and test will use those sources.

If you only export the OpenAPI artifact from a running application, there is no need to add OpenAPI Generator to the service's Maven lifecycle. The two tasks can live in two separate jobs:

- Documentation job: starts the application and saves OpenAPI JSON/YAML.
- SDK job: takes the approved OpenAPI artifact and generates client/server code.

Separating jobs keeps the service free from code generator dependencies if it does not consume generated code.

## 6. Integrating OpenAPI Generator into Gradle

The Gradle plugin provides the openApiGenerate task and extensions to configure the generator. Example using Kotlin DSL:

~~~kotlin
plugins {
    id("org.openapi.generator") version "7.27.0"
}

tasks.register<org.openapitools.generator.gradle.plugin.tasks.GenerateTask>(
    "generateCatalogClient"
) {
    generatorName.set("java")
    inputSpec.set(file("src/main/openapi/catalog.yaml").absolutePath)
    outputDir.set(layout.buildDirectory.dir("generated-sources/openapi/catalog-client").get().asFile.absolutePath)
    apiPackage.set("com.example.catalog.client.api")
    modelPackage.set("com.example.catalog.client.model")
    configOptions.set(
        mapOf(
            "library" to "webclient",
            "dateLibrary" to "java8",
            "hideGenerationTimestamp" to "true"
        )
    )
}
~~~

If generated sources need to be compiled in the same module, wire the generation task to the compile task and register the output directory as a source set in a way appropriate for your project's Gradle version. Avoid letting the generation task overwrite hand-written developer sources.

The Gradle plugin also provides a spec validation task. You can run openApiValidate before openApiGenerate or place validation in a separate CI step to fail early when the contract is invalid.

## 7. Validating the contract before generating code

Do not invoke a code generator on a newly downloaded file without checking it first. At minimum, verify:

- The file is non-empty and parseable.
- Appropriate openapi, info, and paths fields are present.
- References resolve properly and there are no unintended references.
- Request/response schemas match actual payloads.
- Security schemes and requirements are accurately described.
- Server URLs and API version match the release environment.
- Operations have stable, non-duplicate operationIds.
- Keywords/schemas are supported by the generator.

OpenAPI Generator has a validate command:

~~~bash
openapi-generator-cli validate \
  -i build/openapi/catalog.yaml \
  --recommend
~~~

The validate command helps detect specification errors and can offer recommendations. It does not replace style linting, breaking-change detection, contract tests, or testing against real endpoints.

### 7.1. Comparing contracts between builds

When the OpenAPI artifact changes, CI should produce a diff against the released version or main branch:

- Removed paths or HTTP methods.
- New required request fields.
- Response schemas changing type or nullability.
- Changed status codes or security requirements.
- Removed or renamed enum values.
- Changed operationId, schema names, or references.
- Unplanned changes to server URLs or API version.

Not every schema change is a breaking change for every client, but the team needs agreed compatibility rules. Contract diffs help reviewers see the impact before a new SDK is published.

## 8. Complete CI/CD workflow

A pipeline can be divided into steps:

~~~mermaid
flowchart TD
    A[Build / Start test application] --> B[Export OpenAPI JSON/YAML]
    B --> C[Validate specification]
    C --> D[Lint + Contract diff]
    D --> E[Generate client SDK / server stubs]
    E --> F[Compile generated code]
    F --> G[Run contract and integration tests]
    G --> H[Publish versioned OpenAPI artifact]
    H --> I[Publish SDK package or server scaffold]
~~~

Suggested organization:

1. **Export**: fetch the specification from springdoc in an environment with defined configuration.
2. **Validate**: run a parser/validator and check JSON/YAML.
3. **Lint**: enforce naming, tags, operationId, error response, and security rules.
4. **Diff**: compare against the baseline artifact to detect incompatible changes.
5. **Generate**: run OpenAPI Generator with pinned generator/version/options.
6. **Compile**: compile the client SDK or server stubs to catch errors in generated code.
7. **Test**: verify serialization, nullability, auth headers, and sample requests/responses.
8. **Publish**: store the OpenAPI artifact and SDK package under the approved version.

Not every project must generate both client and server. If you only serve an API to a frontend, a client SDK job may be enough. If the team writes the server code-first using controllers, a server generator may not be needed.

## 9. Keeping code generation output stable and reproducible

Generated code depends on more than the OpenAPI file:

- OpenAPI Generator version.
- Generator name and library.
- Generator options/config file.
- Custom templates.
- JDK/Node or corresponding runtime version.
- Input OpenAPI artifact.

For reproducible builds:

- Pin the exact generator version in Maven/Gradle or the CLI wrapper.
- Store config options in source control.
- Use the exact same reviewed OpenAPI artifact.
- Suppress dynamic timestamps if the generator supports it.
- Record the generator version and input checksum/hash in build metadata.
- Only upgrade the generator version via a pull request with output diffs and tests.

Do not use the latest tag or dynamic dependency versions in production pipelines. A generator upgrade can change model names, data types, imports, HTTP clients, or payload serialization behavior.

### 9.1. How should generated code be managed?

There are two common approaches:

| Approach | When appropriate | What to note |
|---|---|---|
| Generate on every build into target/ or build/ | Generated code is an implementation detail of the module and can be reproduced reliably. | Do not manually edit generated files; compile must depend on the generation task. |
| Commit generated code or publish as a separate package | Consumers need stable source/packages or do not run the generator in their build. | Code must be updated whenever contract/generator changes and diffs must be reviewed. |

If you need to change how code is generated, use config options, templates, or a custom generator. Direct edits to generated files are typically lost on the next generation run.

### 9.2. Custom templates and ignore files

OpenAPI Generator supports custom templates. You can extract generator templates and modify certain Mustache files, for example to add a logging wrapper, license header, or package convention:

~~~bash
openapi-generator-cli author template \
  -g java \
  -o tools/openapi-templates/java
~~~

Then use the -t or --template option when generating:

~~~bash
openapi-generator-cli generate \
  -i build/openapi/catalog.yaml \
  -g java \
  -t tools/openapi-templates/java \
  -o build/generated/catalog-client
~~~

The .openapi-generator-ignore file can exclude specific files from regeneration. Use it deliberately and review the results to avoid keeping stale files that no longer match the new contract.

## 10. Publishing contracts and generated code

OpenAPI artifacts and SDK packages have related but distinct lifecycles:

- The OpenAPI artifact records the API version in info.version and the specification version in openapi.
- The SDK package has its own version per the team's package policy.
- OpenAPI Generator has its own tool version.
- The server application has its own release version.

For example, a release might consist of:

| Artifact | Example version |
|---|---|
| API contract info.version | 2.4.0 |
| OpenAPI Specification | 3.1.0 |
| Java SDK package | 2.4.0 or version per client policy |
| OpenAPI Generator | 7.27.0 |
| Spring Boot server | 4.1.x |

Do not force these numbers to match. They represent different lifecycles. Attach build metadata or release tags to trace which OpenAPI artifact and generator version produced each SDK.

## 11. Notes when using OpenAPI 3.1

OpenAPI Generator announces OpenAPI 3.1 support in beta status. Therefore:

- Check the specific release/version instead of inferring from the CLI accepting the file.
- Test with the target generator, not just generic validation.
- Verify type unions with null, oneOf/anyOf, discriminators, and the JSON Schema keywords in use.
- Compare generated models and serializers against real payloads.
- Run contract tests for nullable, required, and enum fields.
- If a generator does not handle a 3.1 schema properly, evaluate a controlled conversion or keep a 3.0 contract for that consumer; do not just edit the openapi field by hand to force the parser.

Parser-level support does not mean every generator and every feature produces complete output. Each generator has its own feature set.

## 12. Common mistakes

- **Assuming springdoc generates Java/TypeScript SDKs**: springdoc only exports documentation; a separate code generator is required.
- **Assuming OpenAPI JSON is server code**: JSON/YAML is only a contract, without business logic.
- **Using a client generator to create a server**: choose a SERVER generator type, such as spring.
- **Using a server generator to create an SDK**: choose a CLIENT generator type, such as java.
- **Not checking generator stability**: beta or experimental generators may not yet suit a release pipeline.
- **Generating code from an unvalidated spec**: reference, schema, or security errors can propagate into generated code.
- **Using options not supported by the generator**: verify with config-help -g name.
- **Editing generated files directly**: changes will be lost on the next regeneration.
- **Not pinning the generator version**: later builds may produce different output even if the contract has not changed.
- **Checking only compilation**: compilable code does not prove serialization and HTTP behavior match the contract.
- **Publishing only the SDK without the spec**: makes it hard to review, diff, and trace the generation source.
- **Equating API version with generator version**: the two versions have independent meanings.
- **Assuming OpenAPI 3.1 support is complete**: overall support status is beta; specific features must be tested.
- **Feeding untrusted specs/templates to the generator**: review inputs before running because untrusted templates or input data can produce dangerous code.

## 13. Selection workflow for a Spring Boot project

1. **Choose the contract source**: Spring Boot controllers with springdoc (code-first), or an approved OpenAPI file (API-first).
2. **Identify required outputs**: JSON/YAML only, client SDK, server stubs, or multiple outputs.
3. **Select tools by role**: springdoc to export the contract; OpenAPI Generator to generate code.
4. **Choose generator type**: CLIENT for SDKs, SERVER for server skeletons.
5. **Check compatibility**: OpenAPI version, generator stability, runtime, and libraries.
6. **Pin version and config**: generator version, package names, templates, and options.
7. **Place in the right build phase**: generation at generate-sources when sources need compiling; artifact export in a documentation job when generated code is not needed in the module.
8. **Validate and diff contract**: catch errors and breaking changes before generation.
9. **Compile and test generated output**: verify data types, serialization, and HTTP behavior.
10. **Publish with traceability**: store the OpenAPI artifact, SDK version, generator version, and input checksum.

## 14. Review checklist

- [ ] Distinguished between contract export, client code generation, and server stub generation.
- [ ] Identified code-first or API-first as the primary contract source.
- [ ] Springdoc is used solely to export documentation from the application.
- [ ] OpenAPI Generator is selected with the right CLIENT/SERVER generator type.
- [ ] Generator name and stability are verified.
- [ ] OpenAPI artifact is validated before generating code.
- [ ] Generator version, config options, and templates are pinned.
- [ ] Generated sources reside in a regenerable directory or are managed as a separate package.
- [ ] No manual edits are made to generated files.
- [ ] Compile and contract tests run against the new output.
- [ ] OpenAPI artifact is versioned and stored with traceability metadata.
- [ ] OpenAPI 3.1 compatibility is checked if using 3.1 schemas.
- [ ] Untrusted input specs/templates are reviewed before running the generator.

## 15. References

- [springdoc-openapi – Getting Started](https://springdoc.org/getting-started.html)
- [springdoc-openapi v2 – Getting Started for Spring Boot 3](https://springdoc.org/v2/getting-started.html)
- [OpenAPI Generator – Usage](https://openapi-generator.tech/docs/usage/)
- [OpenAPI Generator – Maven and Gradle Plugins](https://openapi-generator.tech/docs/plugins/)
- [OpenAPI Generator – Generator List](https://openapi-generator.tech/docs/generators/)
- [OpenAPI Generator – Java Client Generator](https://openapi-generator.tech/docs/generators/java/)
- [OpenAPI Generator – Spring Server Generator](https://openapi-generator.tech/docs/generators/spring/)
- [OpenAPI Generator – Configuration Options](https://openapi-generator.tech/docs/configuration/)
- [OpenAPI Generator – Templates](https://openapi-generator.tech/docs/templating/)
- [OpenAPI Generator – Compatibility Matrix](https://github.com/OpenAPITools/openapi-generator#compatibility)

Springdoc exports the contract from the Spring Boot application; OpenAPI Generator turns that contract into a client SDK or server skeleton. Keep the data direction clear, pick the right generator, validate before generating code, and pin configuration for reproducible builds. When CI stores both the OpenAPI artifact and metadata of the generated code, the team can review contracts, publish SDKs, and trace exactly which version produced each output.
