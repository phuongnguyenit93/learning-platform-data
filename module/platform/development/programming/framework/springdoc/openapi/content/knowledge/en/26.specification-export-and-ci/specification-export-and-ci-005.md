# Integrating the Gradle Plugin and Tasks for Running the Application and Generating Specifications

springdoc-openapi can serve an OpenAPI Description directly from a Spring Boot application at an endpoint such as **/v3/api-docs**. When you need to save the documentation to a file during the build, you can use **springdoc-openapi-gradle-plugin**. The plugin starts the Spring Boot application, calls the documentation endpoint, writes JSON or YAML into the build directory, and then stops the application.

The plugin's primary task is **generateOpenApiDocs**. This task brings documentation generated from the running application into the build and CI workflow: you can store artifacts, check contract changes, run validators, or pass the documentation to a client generator.

A key distinction is that the Gradle plugin does not analyze controllers on its own to produce schemas. The application still needs the springdoc-openapi dependency to expose the documentation endpoint. The Gradle plugin simply starts the application and downloads the content from that endpoint.

## 1. The plugin's role in the build

General workflow:

~~~mermaid
flowchart TD
    A["Gradle build"] --> B["Resolve application runtime classpath"]
    B --> C["Start Spring Boot application"]
    C --> D["Wait until application is ready"]
    D --> E["GET /v3/api-docs or grouped URL"]
    E --> F["Write OpenAPI JSON/YAML to outputDir"]
    F --> G["Stop application"]
    G --> H["Validate / diff / publish / generate client"]
~~~

Each component has its own responsibility:

| Component | Responsibility |
|---|---|
| Spring Boot application | Initializes controllers, routers, security, configuration, and runtime environment |
| springdoc-openapi starter | Analyzes Spring metadata and serves the OpenAPI Description |
| springdoc-openapi-gradle-plugin | Starts the application, calls the API docs endpoint, and writes the file |
| Gradle task | Coordinates when the plugin runs in the build |
| CI pipeline | Runs the build, stores artifacts, validates, compares contracts, or publishes documentation |

Because the plugin fetches documentation over HTTP from the running application, the result reflects the runtime configuration used during that launch. Profiles, environment variables, command-line arguments, database seeds, or feature flags can change the published endpoints and schemas.

## 2. Required dependencies

The application must have the springdoc starter matching its web stack so the OpenAPI endpoint exists. For example, a Spring MVC application using the API starter:

~~~kotlin
val springdocVersion = providers.gradleProperty("springdocVersion").get()

dependencies {
    implementation(
        "org.springdoc:springdoc-openapi-starter-webmvc-api:" + springdocVersion
    )
}
~~~

In this example, springdocVersion is a Gradle property that must be declared in gradle.properties or supplied via a version catalog. The value must belong to the springdoc branch compatible with the application's Spring Boot version.

For a WebFlux application, use the corresponding WebFlux starter:

~~~kotlin
dependencies {
    implementation(
        "org.springdoc:springdoc-openapi-starter-webflux-api:" + springdocVersion
    )
}
~~~

Set the version in gradle.properties or the version catalog and pick a springdoc version compatible with the Spring Boot version in use. The common matrix of the springdoc project pairs Spring Boot 4.x with springdoc 3.x, Spring Boot 3.x with springdoc 2.x, and Spring Boot 2.x with springdoc 1.x. Check the matrix for the exact release before upgrading.

If Swagger UI is needed in the application, you can use the starter with the webmvc-ui or webflux-ui suffix. If the pipeline only needs the OpenAPI file, the API starter is usually sufficient and avoids packaging UI assets.

## 3. Adding the Gradle plugin

The plugin ID is **org.springdoc.openapi-gradle-plugin**. Kotlin DSL example:

~~~kotlin
plugins {
    java
    id("org.springframework.boot") version "3.5.16"
    id("org.springdoc.openapi-gradle-plugin") version "2.1.0"
}
~~~

Groovy DSL example:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.16'
    id 'org.springdoc.openapi-gradle-plugin' version '2.1.0'
}
~~~

Spring Boot version 3.5.16 and Gradle plugin version 2.1.0 in the examples are illustrative versions for a Spring Boot 3.x setup. For an actual project, replace the Spring Boot version per the platform in use and check the plugin version on the Gradle Plugin Portal.

At the time of writing, the plugin portal lists plugin 2.1.0. The current line requires Gradle 8.0 or higher and has been tested up to Gradle 9.8. The plugin supports builds using Kotlin DSL or Groovy DSL. It requires the Spring Boot Gradle plugin along with the Java plugin or Kotlin plugin so it can start the application using the bootRun task's classpath.

Starting from version 2.1, the plugin no longer automatically applies the Spring Boot Gradle plugin. Therefore, org.springframework.boot must be declared explicitly in the project's plugins block.

## 4. How does the generateOpenApiDocs task work?

After applying the plugin, run:

~~~bash
./gradlew generateOpenApiDocs
~~~

On Windows:

~~~powershell
.\gradlew.bat generateOpenApiDocs
~~~

The task performs these steps:

1. Prepares the runtime classpath and startup configuration of the application.
2. Checks whether the port of apiDocsUrl is already occupied by another process.
3. Launches the Spring Boot application in a background process.
4. Waits for the application to become ready to serve the documentation endpoint.
5. Sends an HTTP request to apiDocsUrl or each URL in groupedApiMappings.
6. Writes the received content to outputDir with the configured filename.
7. Stops the application after downloading the documentation.

By default, the task fetches documentation from:

~~~text
http://localhost:8080/v3/api-docs
~~~

The default file is written to:

~~~text
build/openapi.json
~~~

Starting from plugin 2.0, starting and stopping the application are built into generateOpenApiDocs. The forkedSpringBootRun and forkedSpringBootStop tasks from the 1.x line have been removed. Do not add dependencies or configuration for the old tasks when using plugin 2.x.

## 5. Basic configuration in Kotlin DSL

Full configuration example in build.gradle.kts:

~~~kotlin
openApi {
    apiDocsUrl.set("http://localhost:9090/v3/api-docs")
    outputDir.set(layout.buildDirectory.dir("openapi"))
    outputFileName.set("catalog-openapi.json")
    waitTimeInSeconds.set(60)

    customBootRun {
        args.set(listOf("--spring.profiles.active=openapi"))
    }
}
~~~

After running generateOpenApiDocs, the file is created at:

~~~text
build/openapi/catalog-openapi.json
~~~

Where:

- **apiDocsUrl** is the endpoint from which the plugin downloads the OpenAPI Description.
- **outputDir** is the directory containing the resulting file.
- **outputFileName** is the name of the written file.
- **waitTimeInSeconds** is the maximum time the plugin waits for the application to start and serve the endpoint.
- **customBootRun** customizes how the application is launched specifically for documentation generation.

All properties have default values; only reconfigure the values you need to change.

## 6. Equivalent configuration in Groovy DSL

In build.gradle:

~~~groovy
openApi {
    apiDocsUrl = 'http://localhost:9090/v3/api-docs'
    outputDir = layout.buildDirectory.dir('openapi')
    outputFileName = 'catalog-openapi.json'
    waitTimeInSeconds = 60

    customBootRun {
        args = ['--spring.profiles.active=openapi']
    }
}
~~~

Kotlin DSL uses property setters such as set(), while Groovy DSL can assign directly. Do not mix syntax from both DSLs in the same build file.

## 7. Main configuration properties

| Property | Default | Purpose |
|---|---|---|
| apiDocsUrl | http://localhost:8080/v3/api-docs | URL for downloading the OpenAPI document |
| outputDir | build | Directory where the file is written |
| outputFileName | openapi.json | Output filename |
| waitTimeInSeconds | 30 | Wait time for the application to become ready |
| groupedApiMappings | None | Maps multiple group URLs to separate filenames |
| requestHeaders | None | HTTP headers sent when calling the API docs endpoint |
| trustStore | None | Trust store containing trusted certificates for HTTPS calls |
| trustStorePassword | None | Password to open the trust store |
| customBootRun | bootRun configuration | Customizes how the application launches for documentation generation |

If the application starts slowly due to migrations, cache initialization, or dependency connections, increase waitTimeInSeconds. If it still times out after a long wait, inspect startup logs and the endpoint URL rather than increasing the timeout indefinitely.

## 8. Generating a YAML file instead of JSON

The plugin selects the format based on the documentation URL. If apiDocsUrl ends with .yaml, the content is written as YAML:

~~~kotlin
openApi {
    apiDocsUrl.set("http://localhost:8080/v3/api-docs.yaml")
    outputDir.set(layout.buildDirectory.dir("openapi"))
    outputFileName.set("openapi.yaml")
}
~~~

Groovy equivalent:

~~~groovy
openApi {
    apiDocsUrl = 'http://localhost:8080/v3/api-docs.yaml'
    outputDir = layout.buildDirectory.dir('openapi')
    outputFileName = 'openapi.yaml'
}
~~~

For JSON, the plugin pretty-prints the content before writing. For YAML, the plugin writes the YAML content served by the application. Do not change the file extension to .yaml if the URL still returns JSON; the file extension and actual format must match.

## 9. Using a dedicated profile for documentation

Documentation can vary by Spring profile. For example, an openapi profile can:

- Use a test database or stable seed data.
- Disable integrations with external systems.
- Replace email/SMS gateways with mock adapters.
- Configure server URLs, context paths, or security fitting the documentation generation environment.
- Enable endpoints or API groups published only in the documentation profile if intentional.

Configure the profile via customBootRun:

~~~kotlin
openApi {
    customBootRun {
        args.set(listOf("--spring.profiles.active=openapi"))
    }
}
~~~

The application runs with default bootRun settings. Properties declared in customBootRun override the corresponding bootRun properties; undeclared properties continue to inherit from bootRun.

Keep the documentation-generation profile close to the actual deployment configuration. If the openapi profile disables a group of controllers or enables extra internal endpoints, the generated OpenAPI file may differ from the production contract. Document the profile's purpose and scope clearly.

## 10. Customizing JVM, environment, and working directory

customBootRun supports common launch properties:

| Property | Example purpose |
|---|---|
| args | Pass --spring.profiles.active=openapi or --server.port=9090 |
| jvmArgs | Set heap size or JVM options |
| systemProperties | Pass system properties to the Spring Environment |
| environment | Pass environment variables |
| mainClass | Select the main class to run |
| classpath | Select the runtime classpath |
| workingDir | Select the working directory |

Kotlin DSL example:

~~~kotlin
openApi {
    customBootRun {
        args.set(
            listOf(
                "--spring.profiles.active=openapi",
                "--server.port=9090"
            )
        )
        jvmArgs.set(listOf("-Xms256m", "-Xmx1g"))
        environment.put("APP_MODE", "openapi-generation")
    }
}
~~~

If customBootRun is not configured, the plugin uses the settings from the bootRun task. The application runs from the project directory and uses bootRun's Java toolchain. This helps the application locate project-relative configuration files or compose.yaml.

## 11. Generating multiple documents by GroupedOpenApi

If the application has multiple groups, use groupedApiMappings to download each document into a separate file:

~~~kotlin
openApi {
    outputDir.set(layout.buildDirectory.dir("openapi"))
    groupedApiMappings.set(
        mapOf(
            "http://localhost:8080/v3/api-docs/public" to "openapi-public.json",
            "http://localhost:8080/v3/api-docs/admin" to "openapi-admin.json",
            "http://localhost:8080/v3/api-docs/partner" to "openapi-partner.json"
        )
    )
}
~~~

Groovy DSL example:

~~~groovy
openApi {
    outputDir = layout.buildDirectory.dir('openapi')
    groupedApiMappings = [
        'http://localhost:8080/v3/api-docs/public' : 'openapi-public.json',
        'http://localhost:8080/v3/api-docs/admin' : 'openapi-admin.json',
        'http://localhost:8080/v3/api-docs/partner' : 'openapi-partner.json'
    ]
}
~~~

Result:

~~~text
build/openapi/openapi-public.json
build/openapi/openapi-admin.json
build/openapi/openapi-partner.json
~~~

When groupedApiMappings is configured, the plugin uses the URLs and filenames in the map; apiDocsUrl and outputFileName are ignored. outputDir remains the shared directory for the resulting files.

Each URL must point to a group actually exposed by springdoc. If you change a group name or springdoc.api-docs.path, update the map accordingly.

## 12. Sending request headers when fetching documentation

The plugin supports requestHeaders to send HTTP headers when calling apiDocsUrl. This is useful when:

- The API docs endpoint is protected by Basic/Bearer authentication.
- Forwarded host/port headers must be sent so OpenAPI generates public server URLs.
- A reverse proxy or staging environment requires routing headers.

Example sending forwarded headers:

~~~kotlin
openApi {
    requestHeaders.set(
        mapOf(
            "x-forwarded-host" to "api.example.com",
            "x-forwarded-port" to "443"
        )
    )
}
~~~

For forwarded headers to affect generated server URLs, the application needs server.forward-headers-strategy=framework configured and must trust headers only from controlled proxies or build sources. Do not send spoofed headers from untrusted environments.

If the docs endpoint requires Authorization, you can configure the corresponding header, but never hard-code tokens in build.gradle or commit tokens to the repository. Pull credentials from a CI secret store or environment variable and do not print values to logs.

## 13. Calling an HTTPS endpoint with a custom trust store

If the application serves HTTPS only with an internal certificate or private CA that the JVM does not yet trust, the plugin can use a trust store:

~~~bash
keytool -import -noprompt -alias api-ca -file ca.crt -keystore truststore.p12 -deststoretype PKCS12 -storepass changeit
~~~

The command above is an illustrative example for a trust store used in a test environment. Do not use the example password in production; store the real password in a secret store.

Kotlin DSL can configure:

~~~kotlin
openApi {
    apiDocsUrl.set("https://localhost:9443/v3/api-docs")
    trustStore.set("config/truststore.p12")
    trustStorePassword.set(
        providers.environmentVariable("OPENAPI_TRUSTSTORE_PASSWORD")
            .map { it.toCharArray() }
    )
}
~~~

The trust store path must exist on the machine running Gradle. Ensure the required CA certificate is in the trust store and the JVM can read the file. Do not disable TLS verification or use a trust-all certificate manager just to make the task succeed.

## 14. Integrating the task into the build lifecycle

The plugin provides the generateOpenApiDocs task. You can invoke it directly in CI or attach it to an existing build task.

Run standalone:

~~~bash
./gradlew clean generateOpenApiDocs
~~~

If you want build to depend on documentation generation:

~~~kotlin
tasks.named("build") {
    dependsOn("generateOpenApiDocs")
}
~~~

If you want to generate documentation after build:

~~~kotlin
tasks.named("build") {
    finalizedBy("generateOpenApiDocs")
}
~~~

The two approaches have different semantics:

- dependsOn requires generateOpenApiDocs to finish as a dependency before the build task completes.
- finalizedBy runs the documentation generation task as a finalizer after the build task.

Only attach it to build when every build can start the application and its required dependencies. In large projects, it is often better to create a separate CI stage that generates documentation only on branches or workflows that need contract verification.

Do not assume the plugin runs automatically on every gradle build. If you do not wire the task into the lifecycle, invoke generateOpenApiDocs explicitly.

## 15. Up-to-date checks and configuration cache

The current plugin declares inputs from the classpath and application launch configuration, including main class, arguments, JVM arguments, system properties, Java toolchain, and openApi configuration. When inputs do not change and outputs remain valid, Gradle can mark the task UP-TO-DATE and skip restarting the application.

The plugin supports Gradle configuration cache. You can test it with:

~~~bash
./gradlew generateOpenApiDocs --configuration-cache
~~~

If you change profiles, system properties, classpath, main class, or openApi settings, the task may need to re-run and fetch a fresh document. When documentation has not changed but the task still runs, inspect task inputs/outputs and whether configuration changed.

Do not clear the build cache just to force the task to run before identifying which input is causing Gradle to evaluate the task as up-to-date.

## 16. Using Testcontainers or a test application

Some APIs need a database or test service to start properly. You can choose a test main class and test runtime classpath in customBootRun:

~~~kotlin
openApi {
    customBootRun {
        mainClass.set("com.example.TestApplication")
        classpath.from(
            sourceSets.main.get().runtimeClasspath,
            sourceSets.test.get().runtimeClasspath
        )
    }
}
~~~

This approach fits when TestApplication initializes a test environment, Testcontainers, or data required for documentation to reflect the API. Ensure the test application has the same springdoc configuration and docs endpoints as the desired contract.

Do not assume the test classpath is always suitable for publishing documentation. Test configuration may enable mock endpoints, fake data, or test-only routes. Inspect the generated document and clearly record its runtime source.

## 17. Sample CI pipeline

A pipeline can separate build, documentation generation, validation, and artifact storage steps:

~~~yaml
steps:
  - name: Build and test
    run: ./gradlew clean test

  - name: Generate OpenAPI
    run: ./gradlew generateOpenApiDocs

  - name: Validate OpenAPI
    run: npx @redocly/cli lint build/openapi.json

  - name: Upload OpenAPI artifact
    uses: actions/upload-artifact@v4
    with:
      name: openapi-description
      path: build/openapi.json
~~~

This is a workflow example in GitHub Actions syntax; in other CI systems, replace the upload step with the corresponding artifact mechanism. Redocly CLI is an external validator/linter, not a built-in task of the springdoc Gradle plugin.

Checks to perform:

- Was the OpenAPI file created?
- Is the JSON/YAML parseable?
- Is the document valid under the right OpenAPI version?
- Are there unexpected changes in paths, methods, schemas, security, or responses?
- Is the artifact stored with the right build number/commit?

## 18. Comparing the contract with the released version

After generating the file, you can compare it with the OpenAPI copy stored in the repository:

~~~bash
git diff --no-index -- api/openapi.json build/openapi.json
~~~

If you want CI to fail when documentation changes without being updated, you can commit a baseline file to the repository and use:

~~~bash
git diff --no-index --exit-code -- api/openapi.json build/openapi.json
~~~

The no-index flag compares two files even if the file generated in build is not tracked by Git; exit code 1 indicates the two files differ. Paths and comparison methods must fit repository conventions. Direct text comparison can produce large diffs due to ordering or formatting. For mature pipelines, consider canonicalizing JSON or using a breaking-change detection tool to separate compatible changes from incompatible ones.

Do not blindly accept every diff. Changes to required schemas, response codes, security requirements, or removed operations can affect consumers.

## 19. Separating generation from publishing

Generating an OpenAPI file and publishing documentation are two different operations. The generateOpenApiDocs task only produces a local file in the build output. Publishing to a website, artifact repository, API portal, or Git repository requires a separate step.

A safe pipeline typically:

1. Generates the file from the commit being built.
2. Validates the OpenAPI document.
3. Checks diffs and breaking changes.
4. Stores the file as a build artifact.
5. Publishes only when branch, tag, or release policies permit.

Do not place publishing credentials in the generateOpenApiDocs task if the plugin only needs to read documentation from the application. Use separate credentials for the publish step with least-privilege permissions.

## 20. Common issues

| Symptom | Possible cause | Resolution |
|---|---|---|
| Task generateOpenApiDocs not found | Plugin not applied or plugin resolution error | Check plugins block and Gradle Plugin Portal |
| Application exits with non-zero exit code | Spring Boot failed to start | Read application logs in build output; check profile, dependencies, and configuration |
| Cannot connect to apiDocsUrl after wait time | Wrong port/path or slow application startup | Check URL, port, and increase waitTimeInSeconds in a controlled way |
| Port already occupied by another process | Another application is using apiDocsUrl's port | Stop the old process or configure a dedicated server.port for docs |
| File not in expected location | Non-default outputDir or outputFileName | Check the openApi block and build output paths |
| File is .yaml but content is JSON | apiDocsUrl does not end with .yaml | Use the YAML endpoint and a .yaml filename |
| Group is missing | groupedApiMappings uses wrong group URL | Check /v3/api-docs/{group} and group name |
| 401/403 when downloading documentation | Docs endpoint is protected | Configure requestHeaders from a secret store or use an appropriate docs profile |
| HTTPS handshake fails | JVM does not trust the server's CA | Configure trustStore and trustStorePassword |
| Generated server URL has wrong host/port | Missing forwarded headers or wrong strategy | Check requestHeaders and server.forward-headers-strategy |
| Documentation differs from production | Profile or environment during generation differs | Standardize profiles, config, and runtime data |
| Task is always UP-TO-DATE | Inputs unchanged according to Gradle | Check task inputs, outputs, and customBootRun configuration |
| Task re-runs unexpectedly | Classpath, args, or properties changed | Compare task inputs and build configuration |
| Using plugin 2.x but configuring old forked tasks | Following 1.x instructions | Remove forkedSpringBootRun/forkedSpringBootStop and use generateOpenApiDocs |
| Plugin does not auto-apply Spring Boot plugin | Behavior from version 2.1 onward | Declare org.springframework.boot in the plugins block |

## 21. Upgrading from plugin 1.x to 2.x

The 2.x line changes how the application is launched:

| Plugin 1.x | Plugin 2.x |
|---|---|
| Had forkedSpringBootRun and forkedSpringBootStop | The generateOpenApiDocs task starts and stops the application itself |
| Relied on the execfork plugin | No manual execfork configuration needed |
| Might need workingDir or task dependency workarounds | Application runs from the project directory and the task declares required dependencies automatically |
| Configuration cache compatibility might need custom handling | Current plugin supports configuration cache |
| Plugin could auto-apply the Spring Boot plugin in older versions | From 2.1, the build must apply the Spring Boot plugin explicitly |

When upgrading:

1. Update the plugin version in the plugins block.
2. Declare the Spring Boot Gradle plugin explicitly.
3. Remove forkedSpringBootRun and forkedSpringBootStop configuration.
4. Remove the execfork dependency if it was only used for the old plugin.
5. Move profile, args, JVM, and system properties configuration into customBootRun.
6. Run generateOpenApiDocs and inspect the output file.
7. Enable configuration cache and verify the build in CI.

Do not copy 1.x configuration verbatim to 2.x. Read the migration guide for the release you are upgrading to for the corresponding changes.

## 22. Gradle plugin integration checklist

- [ ] Application has the springdoc starter matching Spring MVC or WebFlux.
- [ ] Spring Boot Gradle plugin and Java/Kotlin plugin are applied.
- [ ] Gradle version meets the plugin's requirements.
- [ ] Plugin ID and version are declared in the plugins block.
- [ ] apiDocsUrl points to the endpoint served by the application.
- [ ] outputDir and outputFileName are explicitly set.
- [ ] waitTimeInSeconds matches actual startup time.
- [ ] customBootRun uses the right profile, environment, and JVM options.
- [ ] groupedApiMappings contains the right URL for each group if using multiple documents.
- [ ] requestHeaders contains no hard-coded tokens or secrets committed to the repository.
- [ ] trustStore is configured if calling HTTPS with a private CA is required.
- [ ] generateOpenApiDocs runs successfully locally and in CI.
- [ ] JSON/YAML file is parsed and validated against the right OpenAPI version.
- [ ] Contract diffs are reviewed before updating the baseline.
- [ ] Artifacts are stored and published in a separate step per release policy.
- [ ] Legacy 1.x configuration is removed after upgrading to 2.x.

## 23. Official references

- [springdoc-openapi Gradle plugin](https://github.com/springdoc/springdoc-openapi-gradle-plugin): how to apply the plugin, tasks, openApi extension, grouped mappings, customBootRun, and migration.
- [Gradle Plugin Portal](https://plugins.gradle.org/plugin/org.springdoc.openapi-gradle-plugin): plugin ID, released versions, and how to declare the plugin.
- [springdoc-openapi v2 documentation](https://springdoc.org/v2/): integrating springdoc with Spring Boot 3 and Gradle plugin guide.
- [springdoc-openapi compatibility](https://github.com/springdoc/springdoc-openapi#compatibility): compatibility relationship between Spring Boot and springdoc lines.
- [Gradle task configuration](https://docs.gradle.org/current/userguide/controlling_task_execution.html): dependsOn, finalizedBy, and task orchestration.

## Conclusion

springdoc-openapi-gradle-plugin brings OpenAPI export into the build through the **generateOpenApiDocs** task. The task launches the Spring Boot application with bootRun or customBootRun configuration, waits for the documentation endpoint to be ready, downloads JSON/YAML, and stops the application. You can customize the URL, output directory, wait time, profile, headers, trust store, and multiple groups. The generated documentation reflects the profile and runtime configuration used in that run, so CI must standardize the environment, validate documents, review breaking changes, and store artifacts. With plugin 2.x, use the built-in generateOpenApiDocs task; legacy forked tasks from the 1.x line no longer apply.
