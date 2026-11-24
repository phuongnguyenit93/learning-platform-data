# Integrating the Maven Plugin into the Right Build Lifecycle Phase

springdoc-openapi-maven-plugin retrieves the OpenAPI document from a running Spring Boot application and writes that content to a file during the Maven build. Because the plugin calls an HTTP endpoint such as /v3/api-docs, the application must be started before the generate goal runs and stopped after the documentation is collected. This is why the plugin fits Maven's integration-test phase: the Spring Boot Maven Plugin can start the application in pre-integration-test, springdoc downloads the documentation in integration-test, and the Spring Boot Maven Plugin stops the application in post-integration-test.

Choosing the right phase ensures the build produces a specification reflecting runtime configuration while avoiding calling the endpoint before the server is ready or leaving an application process lingering after the build. The commonly used command is mvn verify, because it walks through the preparation phases, runs integration tests, stops the application, and verifies the result.

## 1. What does the Maven plugin do?

The springdoc-openapi runtime generates the OpenAPI document from controllers, DTOs, annotations, and Spring configuration. The Maven plugin does not scan source code or analyze controllers itself. It sends an HTTP request to the running application's documentation endpoint, receives JSON or YAML, and writes the received content verbatim to a file.

Processing flow:

~~~mermaid
flowchart TD
    A[mvn verify] --> B[package: package the application]
    B --> C[pre-integration-test: spring-boot:start]
    C --> D[Application starts and is ready]
    D --> E[integration-test: springdoc:generate]
    E --> F[GET /v3/api-docs]
    F --> G[write target/openapi.json]
    G --> H[post-integration-test: spring-boot:stop]
    H --> I[verify: check build result]
~~~

The two plugins have distinct responsibilities:

| Plugin | Goal | Responsibility |
|---|---|---|
| spring-boot-maven-plugin | start | Starts the application in a separate process without blocking Maven |
| springdoc-openapi-maven-plugin | generate | Calls the application's OpenAPI endpoint and writes the response to a file |
| spring-boot-maven-plugin | stop | Stops the process started by the start goal |
| maven-failsafe-plugin (if used) | integration-test, verify | Runs and verifies integration tests against the running application |

Because the springdoc plugin only calls an HTTP endpoint, it can work with any application exposing an OpenAPI description at the configured URL. However, the project's standard integration example uses the Spring Boot Maven Plugin to manage the process lifecycle.

## 2. Why does the generate goal fit integration-test?

Maven's default lifecycle has phases in a fixed order. Several key phases:

| Phase | Role | Is the application running yet? |
|---|---|---|
| validate | Validates project structure and metadata | No |
| compile | Compiles source code | No |
| test | Runs unit tests | Typically no standalone packaged server is running yet |
| package | Builds JAR/WAR | Not by default |
| pre-integration-test | Prepares environment for integration tests | The start goal can launch the server here |
| integration-test | Runs integration tests and operations needing a live application | Yes |
| post-integration-test | Cleans up environment after integration tests | The stop goal can shut down the server here |
| verify | Checks build and integration test results | Server has stopped if the lifecycle completed normally |
| install | Installs artifact into local repository | Server not needed |
| deploy | Deploys artifact to remote repository | Server not needed |

The springdoc-openapi:generate goal has a default phase of integration-test. At this point, the application can already be started by the spring-boot:start goal in pre-integration-test. If you bind the generate goal to compile, package, or generate-resources, the server is typically not running yet, so the plugin cannot fetch the documentation.

Do not pick verify simply because you want the build to fail if the documentation is wrong. Let OpenAPI downloading happen in integration-test, and use verify as the final phase for Maven to finish checks and verify integration tests.

## 3. Roles of pre-integration-test, integration-test, and post-integration-test

These three phases form a workspace with setup, execution, and teardown:

1. **pre-integration-test:** prepares infrastructure and starts the application.
2. **integration-test:** downloads the OpenAPI document and runs HTTP or contract tests.
3. **post-integration-test:** stops the application and releases resources.

The Spring Boot Maven Plugin provides start and stop goals to handle both ends of the cycle. The start goal runs the application in a separate process and returns control to Maven so other plugins can proceed. The stop goal uses JMX to ask that process to shut down.

The Springdoc Maven Plugin runs in the middle phase to call the endpoint. If no application is running at that URL, the download fails—or the build might still continue if failOnError is left at its default of false.

## 4. Configuring both plugins in pom.xml

The example below uses the Spring Boot Maven Plugin to manage the application and springdoc-openapi-maven-plugin to export JSON. The Spring Boot Maven Plugin version should be managed by the Spring Boot parent or dependency management. The springdoc Maven plugin version is a build plugin version, independent of the springdoc runtime library version in the application.

~~~xml
<properties>
    <springdoc-openapi-maven-plugin.version>1.6</springdoc-openapi-maven-plugin.version>
</properties>

<build>
    <plugins>
        <plugin>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-maven-plugin</artifactId>
            <configuration>
                <jvmArguments>-Dspring.application.admin.enabled=true</jvmArguments>
            </configuration>
            <executions>
                <execution>
                    <id>start-application-for-openapi</id>
                    <phase>pre-integration-test</phase>
                    <goals>
                        <goal>start</goal>
                    </goals>
                </execution>
                <execution>
                    <id>stop-application-after-openapi</id>
                    <phase>post-integration-test</phase>
                    <goals>
                        <goal>stop</goal>
                    </goals>
                </execution>
            </executions>
        </plugin>

        <plugin>
            <groupId>org.springdoc</groupId>
            <artifactId>springdoc-openapi-maven-plugin</artifactId>
            <version>${springdoc-openapi-maven-plugin.version}</version>
            <executions>
                <execution>
                    <id>generate-openapi-description</id>
                    <phase>integration-test</phase>
                    <goals>
                        <goal>generate</goal>
                    </goals>
                </execution>
            </executions>
            <configuration>
                <apiDocsUrl>http://localhost:8080/v3/api-docs</apiDocsUrl>
                <outputDir>${project.build.directory}/openapi</outputDir>
                <outputFileName>openapi.json</outputFileName>
                <timeout>90</timeout>
                <failOnError>true</failOnError>
            </configuration>
        </plugin>
    </plugins>
</build>
~~~

In this example:

- spring.application.admin.enabled=true enables the Spring Application Admin MBean so the Spring Boot Maven Plugin can manage the application lifecycle via JMX.
- start runs in pre-integration-test.
- generate runs in integration-test.
- stop runs in post-integration-test.
- The file is written to target/openapi/openapi.json.
- failOnError=true fails the build if the document cannot be downloaded or written.
- timeout=90 increases the connection/read wait time to 90 seconds compared to the springdoc plugin's default of 60 seconds.

Version 1.6 in the example is the build plugin version from the project's README example. When applying it, check the release approved by your organization and pin a specific version; do not use a dynamic version or omit the plugin version.

### Why must Spring Application Admin be enabled?

The Spring Boot Maven Plugin launches the application in a separate process. It uses JMX to communicate with the MBean managing the application lifecycle. spring.application.admin.enabled=true allows Spring Boot to register the required MBean. Without this configuration, the start goal may launch the application, but the stop goal will not be able to control it as expected.

The Spring Boot Maven Plugin defaults to JMX port 9001. If multiple applications run concurrently on the same agent or that port is already in use, configure a different port and share that configuration between start and stop.

## 5. Running the build with mvn verify

After configuring the plugins, run:

~~~bash
mvn clean verify
~~~

Maven executes the phases preceding verify in the exact order. With the configuration above, the expected output is:

~~~text
target/
└── openapi/
    └── openapi.json
~~~

verify is suitable for CI because it runs through post-integration-test and the verify phase, where Failsafe can validate integration test results. Calling only mvn integration-test can stop the lifecycle before teardown runs in some Maven versions, leaving the application process alive. Use a terminal phase like verify rather than an intermediate phase when the build manages a start/stop environment.

Do not confuse mvn springdoc-openapi:generate with mvn verify. Invoking the plugin goal directly only runs the file download operation; it does not start the application automatically unless you prepared the server beforehand.

## 6. Execution order when multiple goals participate in the lifecycle

Maven runs phases in lifecycle order. Goals bound to the same phase execute in the order they are declared in the POM. Therefore:

- spring-boot:start must finish before springdoc-openapi:generate calls the HTTP endpoint.
- springdoc-openapi:generate must finish before spring-boot:stop shuts down the server.
- If Failsafe runs integration tests, they also need the application running during the integration-test phase.

In the sample configuration, the goals sit in three separate phases, so the order is explicit without relying on declaration order between the two plugins.

If multiple plugins run in integration-test, arrange declarations and executions so the server is ready before tests or exports run. Do not place the stop goal in the same phase as generate without controlling order, because the application could be stopped before the documentation is downloaded.

## 7. Configuring the endpoint and output file

Key parameters of the generate goal:

| Parameter | User property | Default | Meaning |
|---|---|---|---|
| apiDocsUrl | springdoc.apiDocsUrl | http://localhost:8080/v3/api-docs | URL returning OpenAPI JSON or YAML |
| outputDir | springdoc.outputDir | ${project.build.directory} | Directory where the file is written |
| outputFileName | springdoc.outputFileName | openapi.json | Filename |
| attachArtifact | springdoc.attachArtifact | false | Attaches the file to the Maven project for install/deploy with artifacts |
| attachArtifactClassifier | springdoc.attachArtifactClassifier | openapi | Classifier when attaching |
| headers | No separate user property | None | HTTP headers sent when calling the endpoint |
| timeout | springdoc.timeout | 60 seconds | Connection and response read timeout |
| skip | springdoc.skip | false | Skips the generate goal |
| failOnError | No separate user property | false | Fails the build if downloading/writing documentation errors |

outputDir defaults to ${project.build.directory}, which typically maps to target. Choose a subdirectory such as ${project.build.directory}/openapi to separate specification files from JARs, test reports, and other artifacts.

Do not set outputDir to a path starting with a slash like an arbitrary absolute path in plugin configuration. The plugin documentation requires a relative directory name; you can use ${project.build.directory}/openapi as shown in the example.

## 8. Exporting YAML instead of JSON

The Springdoc runtime provides both JSON and YAML. To export YAML, change the endpoint URL and filename:

~~~xml
<configuration>
    <apiDocsUrl>http://localhost:8080/v3/api-docs.yaml</apiDocsUrl>
    <outputDir>${project.build.directory}/openapi</outputDir>
    <outputFileName>openapi.yaml</outputFileName>
    <failOnError>true</failOnError>
</configuration>
~~~

The plugin saves the response returned by the endpoint. It does not convert JSON to YAML or vice versa. Therefore, the URL format and file extension must match:

| Endpoint | Suggested filename |
|---|---|
| /v3/api-docs | openapi.json |
| /v3/api-docs.yaml | openapi.yaml |

If the application changes springdoc.api-docs.path, update apiDocsUrl to the new path. If using a context path or reverse proxy, use a URL that the Maven process can reach from the build environment.

## 9. Saving multiple OpenAPI groups in the same build

If the application declares multiple GroupedOpenApi beans, each group has its own endpoint, such as:

~~~text
/v3/api-docs/public
/v3/api-docs/admin
/v3/api-docs/internal
~~~

You can declare one execution per group. Each execution needs its own URL and filename; if attaching as Maven artifacts, use separate classifiers to avoid collisions:

~~~xml
<plugin>
    <groupId>org.springdoc</groupId>
    <artifactId>springdoc-openapi-maven-plugin</artifactId>
    <version>${springdoc-openapi-maven-plugin.version}</version>
    <executions>
        <execution>
            <id>generate-public-api</id>
            <phase>integration-test</phase>
            <goals>
                <goal>generate</goal>
            </goals>
            <configuration>
                <apiDocsUrl>http://localhost:8080/v3/api-docs/public</apiDocsUrl>
                <outputFileName>openapi-public.json</outputFileName>
                <attachArtifact>true</attachArtifact>
                <attachArtifactClassifier>openapi-public</attachArtifactClassifier>
                <failOnError>true</failOnError>
            </configuration>
        </execution>
        <execution>
            <id>generate-admin-api</id>
            <phase>integration-test</phase>
            <goals>
                <goal>generate</goal>
            </goals>
            <configuration>
                <apiDocsUrl>http://localhost:8080/v3/api-docs/admin</apiDocsUrl>
                <outputFileName>openapi-admin.json</outputFileName>
                <attachArtifact>true</attachArtifact>
                <attachArtifactClassifier>openapi-admin</attachArtifactClassifier>
                <failOnError>true</failOnError>
            </configuration>
        </execution>
    </executions>
</plugin>
~~~

Place shared settings such as version and outputDir at the plugin level if executions share them; place apiDocsUrl, filename, and classifier at the execution level when they differ. Verify that the plugin version in use supports per-execution configuration as shown in the example.

One important note: if group endpoints require different security, the build process must send the appropriate header for each execution. Do not use an admin token to export public documentation when that token is unnecessary.

## 10. Attaching the OpenAPI file to a Maven artifact

By default attachArtifact=false, so the file only lives in the build's output directory. When enabled:

~~~xml
<attachArtifact>true</attachArtifact>
<attachArtifactClassifier>openapi</attachArtifactClassifier>
~~~

Maven attaches the specification file to the project as a secondary artifact with the classifier openapi. When running mvn install, the artifact can be installed into the local repository alongside the main JAR; when running mvn deploy, it can be published to the remote repository alongside other artifacts.

Example secondary artifact coordinates:

~~~text
com.example:catalog-service:1.0.0:openapi:json
~~~

The classifier lets consumers distinguish the executable JAR from the OpenAPI file. With multiple groups, use distinct classifiers like openapi-public and openapi-admin. Avoid letting two executions attach the same classifier to the same project, as that causes conflicts or overwrites the artifact.

Do not enable attach if the pipeline only needs to upload the file as a CI artifact or pass it to lint/contract test steps. You can keep the file in target/openapi and use the CI system's artifact upload mechanism.

## 11. Sending headers when the OpenAPI endpoint is protected

If Spring Security protects /v3/api-docs, the plugin needs to send an authentication header. Configure headers:

~~~xml
<configuration>
    <apiDocsUrl>http://localhost:8080/v3/api-docs</apiDocsUrl>
    <headers>
        <Authorization>Bearer ${env.OPENAPI_EXPORT_TOKEN}</Authorization>
    </headers>
    <failOnError>true</failOnError>
</configuration>
~~~

Store the token in a CI environment variable; do not commit tokens into the POM. The example above illustrates how headers are passed; the element name inside headers becomes the HTTP header name sent. For endpoints not requiring authentication, no header needs to be added.

If each OpenAPI group has different access permissions, configure the appropriate header in the corresponding execution. Be careful with Maven logs: do not enable debug logging or print the entire environment when secrets are present.

## 12. Changing the port and passing arguments to the application

If port 8080 is occupied or CI runs multiple services, change the application port and plugin URL together:

~~~xml
<plugin>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-maven-plugin</artifactId>
    <configuration>
        <jvmArguments>-Dspring.application.admin.enabled=true</jvmArguments>
        <arguments>
            <argument>--server.port=9090</argument>
        </arguments>
    </configuration>
    <executions>
        <execution>
            <id>start-application-for-openapi</id>
            <phase>pre-integration-test</phase>
            <goals>
                <goal>start</goal>
            </goals>
        </execution>
        <execution>
            <id>stop-application-after-openapi</id>
            <phase>post-integration-test</phase>
            <goals>
                <goal>stop</goal>
            </goals>
        </execution>
    </executions>
</plugin>
~~~

And:

~~~xml
<apiDocsUrl>http://localhost:9090/v3/api-docs</apiDocsUrl>
~~~

arguments passes application arguments to the started process. If you change the port via command line arguments but forget to update apiDocsUrl, the plugin will still call port 8080 and could accidentally fetch from another application running on the machine.

You can pass profiles, datasource configuration, or environment properties via arguments, environmentVariables, or profiles of the Spring Boot Maven Plugin. Use the exact profile intended for generating OpenAPI in CI; profiles can affect endpoints, security, feature flags, and generated schemas.

## 13. Adjusting the wait time during application startup

Spring Boot Maven Plugin start checks whether the application is ready by polling at intervals. Current documentation lists maxAttempts and wait parameters; the default is 60 attempts, 500 ms each, corresponding to roughly 30 seconds.

If the application starts slowly due to database migrations, cache warm-up, or configuration loading, you can increase the wait time:

~~~xml
<plugin>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-maven-plugin</artifactId>
    <configuration>
        <jvmArguments>-Dspring.application.admin.enabled=true</jvmArguments>
        <maxAttempts>120</maxAttempts>
        <wait>500</wait>
    </configuration>
    <!-- executions start/stop -->
</plugin>
~~~

Do not use long timeouts to mask startup failures. Read the application process logs to find root causes such as an unreachable datasource, an occupied port, a wrong profile, or a bean initialization failure.

springdoc-openapi-maven-plugin has its own timeout for requests to the endpoint, defaulting to 60 seconds. Startup wait time and OpenAPI download time are two separate limits:

- maxAttempts and wait control waiting for the application to become ready.
- The springdoc plugin's timeout controls connecting to and reading the response from apiDocsUrl.

If the document is large, has many schemas, or customizers take long to run, you can increase timeout without altering startup wait time.

## 14. Pretty formatting and saved file content

The plugin saves the exact content returned by the OpenAPI endpoint. It does not reformat JSON, sort keys, or normalize YAML. If you want indented JSON for easier review in Git, configure the springdoc runtime:

~~~yaml
springdoc:
  writer-with-default-pretty-printer: true
~~~

Or pass the property when the Spring Boot Maven Plugin starts the application:

~~~xml
<arguments>
    <argument>--springdoc.writer-with-default-pretty-printer=true</argument>
</arguments>
~~~

Do not run an arbitrary formatter after export if the pipeline needs to compare the exact document served at runtime. If there is a normalization step, treat it as an explicit, versioned, and CI-tested step.

## 15. Combining with Maven Failsafe

Spring Boot Maven Plugin start/stop is designed to work alongside integration tests. Maven Failsafe has two main goals:

- integration-test: runs integration tests while the application is active.
- verify: aggregates test results and fails the build if any tests failed.

Example configuration:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-failsafe-plugin</artifactId>
    <executions>
        <execution>
            <id>run-integration-tests</id>
            <goals>
                <goal>integration-test</goal>
                <goal>verify</goal>
            </goals>
        </execution>
    </executions>
</plugin>
~~~

Failsafe is designed to defer reporting build failures until the verify phase. This allows Maven to pass through post-integration-test and run the stop goal before test results are verified. That is an advantage over placing integration tests in Surefire during the test phase when a separately managed server is needed around tests.

If you both export OpenAPI and run integration tests, both use the application started in pre-integration-test. Decide the goal ordering in the integration-test phase based on your needs. For example, you can fetch OpenAPI first to save the application's contract, then run integration tests.

## 16. Handling environment-based skipping

The springdoc plugin supports the springdoc.skip user property. You can skip export alone:

~~~bash
mvn verify -Dspringdoc.skip=true
~~~

Note: the command above only skips the generate goal. If the Spring Boot Maven Plugin still has start/stop configured, the application will still start and stop according to the lifecycle.

If you want to skip the entire integration environment in certain builds, use a shared property across start, stop, Failsafe, and springdoc:

~~~xml
<properties>
    <skip.it>false</skip.it>
</properties>

<plugin>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-maven-plugin</artifactId>
    <executions>
        <execution>
            <id>start-application-for-tests</id>
            <phase>pre-integration-test</phase>
            <goals>
                <goal>start</goal>
            </goals>
            <configuration>
                <skip>${skip.it}</skip>
            </configuration>
        </execution>
        <execution>
            <id>stop-application-after-tests</id>
            <phase>post-integration-test</phase>
            <goals>
                <goal>stop</goal>
            </goals>
            <configuration>
                <skip>${skip.it}</skip>
            </configuration>
        </execution>
    </executions>
</plugin>
~~~

Apply the same property to the springdoc plugin and Failsafe:

~~~xml
<configuration>
    <skip>${skip.it}</skip>
</configuration>
~~~

Run:

~~~bash
mvn verify -Dskip.it=true
~~~

Do not use springdoc's individual skip flag to indicate that all integration tests are disabled. Make sure start, stop, and tests all obey the same flag if the goal is to skip the whole environment.

## 17. Handling build failures and lingering application processes

The stop goal is bound to post-integration-test. If the build fails before Maven reaches this phase, Maven may skip the stop goal. The springdoc plugin README also warns that when a build fails, the application launched by spring-boot:start may keep running and serving requests for the next build.

This is especially important when:

- The application fails to start completely.
- springdoc cannot download OpenAPI and failOnError=true halts the build.
- An integration test fails the build right in the integration-test phase.
- A CI agent reuses the same machine or the same port across multiple jobs.

Measures to take:

1. Run builds in single-use containers or ephemeral runners if possible.
2. Use dedicated ports per job or per module.
3. Add a CI cleanup step configured to always run, even when Maven fails.
4. Do not assume post-integration-test always runs after a build failure.
5. If using external processes or sidecar services outside Maven, manage their lifecycle with separate cleanup mechanisms.

Setting failOnError=true is necessary so CI does not silently ignore a missing OpenAPI file, but it also stops the build immediately when export fails. Therefore, external cleanup steps outside Maven need to be designed carefully.

## 18. The report goal and Maven Site vs. the generate goal

The plugin also has a report goal, used to add a Swagger UI documentation page to the Project Reports section of Maven Site. This goal has a default phase of site, not integration-test.

Differences:

| Goal | Default phase | Result |
|---|---|---|
| generate | integration-test | Writes OpenAPI JSON/YAML to a file |
| report | site | Creates a documentation page rendered with Swagger UI in Maven Site |

To generate a site report, declare the plugin in reporting:

~~~xml
<reporting>
    <plugins>
        <plugin>
            <groupId>org.springdoc</groupId>
            <artifactId>springdoc-openapi-maven-plugin</artifactId>
            <version>${springdoc-openapi-maven-plugin.version}</version>
            <reportSets>
                <reportSet>
                    <reports>
                        <report>report</report>
                    </reports>
                </reportSet>
            </reportSets>
        </plugin>
    </plugins>
</reporting>
~~~

After generating the document, you can run:

~~~bash
mvn verify site
~~~

By default, report reads the file produced by the generate goal, usually target/openapi.json. If the file does not exist, report can fetch the document from apiDocsUrl. The page is created in Maven Site under the springdoc-openapi directory.

Limitations to know:

- The report goal requires maven-site-plugin version 3.9.1 or higher.
- report currently supports JSON documents only, not YAML.
- Swagger UI assets are loaded from unpkg.com when the site page is viewed, so the browser needs Internet access.
- report is a documentation presentation page; it does not replace the OpenAPI artifact file used for linting, diffing, or code generation.

If the goal is to publish a JSON/YAML file as an artifact, use the generate goal. If the goal is to generate Project Reports pages, use report; both goals can appear together in the same build.

## 19. Integrating into CI and inspecting the exported file

In CI, an export step is only valuable when the build confirms the file exists and has valid content. Configure failOnError=true so the build fails if the plugin cannot download or write the document.

A pipeline can be divided into steps:

1. Run mvn clean verify to compile, test, package, start the application, export OpenAPI, run integration tests, and stop the application.
2. Check that target/openapi/openapi.json or the corresponding YAML exists and is non-empty.
3. Parse JSON/YAML to catch truncated files or syntax errors.
4. Run OpenAPI linting or validation according to organizational rules.
5. Compare against the previous release's contract to detect breaking changes.
6. Store the file as a CI artifact or attach it to the Maven artifact.
7. Publish documentation only after checks pass.

The plugin only proves it retrieved a response from the endpoint. It does not verify by itself that schemas match business logic, operationIds are stable, all response statuses are documented, or changes are backward-compatible. Those checks require dedicated lint, diff, and contract test steps.

Example quick shell check after the build:

~~~bash
test -s target/openapi/openapi.json
python -m json.tool target/openapi/openapi.json > /dev/null
~~~

This is only an example checking that the JSON file is non-empty and parseable. If exporting YAML, use a YAML parser approved by your organization. Within the scope of this lesson, the Maven plugin only produces the artifact; choosing lint/diff tools depends on CI policy.

## 20. Notes for multi-module Maven and parallel builds

In a multi-module project, place the start/generate/stop configuration in the module that actually contains the Spring Boot application and springdoc runtime. Do not put application-startup executions into an aggregator POM with pom packaging if that module has no runnable application.

If multiple service modules export OpenAPI:

- Each module needs its own appropriate URL, port, and output directory.
- Do not let processes bind to the same HTTP port.
- If the Spring Boot Maven Plugin uses JMX, each process needs its own JMX port when running concurrently.
- Use distinct classifiers when files are attached to Maven artifacts.
- Be cautious with Maven parallel builds; services may start concurrently and contend for resources.

With a single module, the default localhost:8080 and JMX 9001 are usually enough for sequential builds. With a multi-service reactor, assign explicit ports or split exports into separate jobs.

## 21. Version compatibility and dependency management

The Springdoc Maven Plugin is a separate build plugin. Its version does not need to equal the springdoc runtime version. Pin the plugin version while using a springdoc runtime compatible with Spring Boot:

| Spring Boot | springdoc runtime line |
|---|---|
| 4.x | 3.x |
| 3.x | 2.x |
| 2.x and 1.x | 1.x |

The Springdoc Maven Plugin only calls an HTTP endpoint, so its job is to fetch the document from the application. The table above applies to the compatibility relationship between Spring Boot and the springdoc runtime library, not a rule requiring the build plugin version to match the runtime version.

The plugin README currently states a requirement of Maven 3.6.3 or higher and Java 8 or higher for the plugin itself. The Spring Boot project may require a higher Java version depending on its major version. Always check the Spring Boot/springdoc compatibility matrix and the actual CI toolchain.

If using spring-boot-starter-parent, the Spring Boot Maven Plugin version is typically managed by the parent. If not using the parent, declare the Spring Boot plugin version explicitly or use appropriate pluginManagement. Do not let plugin versions vary by environment.

## 22. Common errors and how to resolve them

| Symptom | Possible cause | Resolution |
|---|---|---|
| Connection refused to /v3/api-docs | Application not running or wrong port in apiDocsUrl | Place start in pre-integration-test and check port/path |
| OpenAPI file not created but build passes | failOnError is false | Set failOnError=true in CI |
| 401 or 403 when downloading document | Endpoint protected by Spring Security | Configure plugin headers with a token from a CI secret |
| File fetched from an old service | Port already has an old process listening | Use a dedicated port, check processes, and clean up prior jobs |
| 404 when calling a group | Wrong group name or endpoint URL | Check URL /v3/api-docs/{group} |
| Application does not stop after build | Missing Spring Application Admin or JMX port mismatch | Enable spring.application.admin.enabled and use matching JMX config for start/stop |
| Application still running after failed build | Maven did not reach post-integration-test | Add always-run cleanup in CI or use ephemeral runners/containers |
| Generate goal runs before server is ready | Goal bound to wrong phase or slow startup | Bind generate to integration-test, increase maxAttempts/wait if justified |
| Plugin times out even though server is running | Document takes long to build or endpoint responds slowly | Increase springdoc plugin timeout and inspect server logs |
| Exported wrong profile | Spring Boot process started with another profile | Pass the right profiles/arguments to the start goal |
| Exported YAML but file has JSON extension | apiDocsUrl and outputFileName mismatch | Use /v3/api-docs.yaml and openapi.yaml |
| Two group files overwrite each other | Same outputFileName or classifier | Set unique filenames and classifiers |
| Parallel build fails with port errors | Multiple modules share default HTTP/JMX ports | Assign dedicated ports or run exports sequentially |
| mvn springdoc-openapi:generate fails to connect | Invoked goal directly without starting server | Use mvn verify or start the endpoint beforehand |
| Maven Site report does not display | Missing compatible maven-site-plugin or using YAML | Use site plugin >= 3.9.1 and supply JSON |

## 23. Workflow for choosing phases and configuration for a project

When integrating the Maven plugin, follow this sequence:

1. Confirm the application has the springdoc runtime and a working OpenAPI endpoint.
2. Select the right Spring Boot Maven Plugin to start/stop the process.
3. Place start in pre-integration-test.
4. Place springdoc generate in integration-test.
5. Place stop in post-integration-test.
6. Enable Spring Application Admin and configure JMX appropriately.
7. Set apiDocsUrl with the right port, context path, and group.
8. Choose outputDir, outputFileName, and JSON/YAML appropriately.
9. Set failOnError=true for CI and configure a justified timeout.
10. If the endpoint requires authentication, pass tokens via CI secrets.
11. If publishing alongside artifacts is needed, enable attachArtifact and use distinct classifiers.
12. Run mvn clean verify, then verify the file, parse, lint, and diff the contract.
13. Ensure CI has cleanup when the build stops before post-integration-test.

The integration-test phase is the right place for the generate goal because the application has already started and remains active for the springdoc plugin to call the endpoint. Combining pre-integration-test, integration-test, and post-integration-test lets Maven produce documentation from the exact runtime, manage processes cleanly, and feed the OpenAPI file into verification or release pipelines.

## 24. References

- [springdoc-openapi-maven-plugin README](https://github.com/springdoc/springdoc-openapi-maven-plugin): generate/report goals, default phases, output configuration, headers, attachArtifact, YAML, groups, and failOnError.
- [Springdoc OpenAPI v2 – Maven Plugin](https://springdoc.org/v2/#maven-plugin): how to integrate the plugin into the Maven lifecycle.
- [Maven – Introduction to the Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle): phase ordering, goal binding, and how Maven executes the lifecycle.
- [Maven – Lifecycles Reference](https://maven.apache.org/ref/current/maven-core/lifecycles.html): list of phases in the default lifecycle.
- [Spring Boot Maven Plugin – Running Integration Tests](https://docs.spring.io/spring-boot/maven-plugin/integration-tests.html): start/stop goals, JMX, readiness, Failsafe, and cleanup.
- [Spring Boot Maven Plugin – Goals](https://docs.spring.io/spring-boot/maven-plugin/goals.html): parameters and behavior of Spring Boot Maven Plugin goals.
- [Springdoc OpenAPI – Compatibility Matrix](https://springdoc.org/#what-is-the-compatibility-matrix-of-spring-boot-with-springdoc-openapi-): compatibility between Spring Boot and springdoc runtime.
