# Springdoc Plugin Principle: Start the Application, Then Fetch the Specification Over HTTP

The specification export plugin of springdoc-openapi operates on a simple principle: **the Spring Boot application must run first, and then the plugin sends an HTTP request to the OpenAPI endpoint and saves the response to a file**. The plugin does not parse controller source code to construct documentation on its own, does not replace the springdoc library running inside the application, and does not start a server by itself merely by declaring the plugin dependency.

This has important implications when bringing OpenAPI export into Maven or CI. The output is retrieved from a running application with the actual profiles, configuration, beans, routes, security, data, and dependencies of that startup. If the application is not ready, the endpoint is blocked, or it is running under the wrong profile, the exported file may fail or fail to reflect the contract the team expects.

This lesson uses springdoc-openapi-maven-plugin as an illustration. This plugin calls an HTTP endpoint such as /v3/api-docs, receives the OpenAPI JSON content, and writes it to the build directory. Therefore, three parts must work together: the springdoc runtime in the application, a mechanism to start and stop the application in Maven, and the HTTP fetch plugin in the appropriate phase of the Maven lifecycle.

## 1. There are two different Springdoc components

In a Maven project, you must distinguish between the library running with the application and the plugin running during the build:

| Component | Where it runs | Responsibility |
|---|---|---|
| springdoc runtime starter | Spring Boot application classpath | Discovers controllers, DTOs, annotations, and generates the OpenAPI document at runtime |
| springdoc-openapi-maven-plugin | Maven build process | Sends an HTTP request to the OpenAPI URL and saves the response to a file |

Example runtime dependency for Spring MVC:

~~~xml
<dependency>
    <groupId>org.springdoc</groupId>
    <artifactId>springdoc-openapi-starter-webmvc-ui</artifactId>
    <version>${springdoc.version}</version>
</dependency>
~~~

If the application does not need Swagger UI but still needs the JSON/YAML endpoint, you can choose the API starter matching your web stack. The key point is that the application must have the springdoc runtime to expose the endpoint that the plugin will call.

The Maven plugin is declared in build/plugins and does not replace the runtime dependency:

~~~xml
<plugin>
    <groupId>org.springdoc</groupId>
    <artifactId>springdoc-openapi-maven-plugin</artifactId>
    <version>1.4</version>
</plugin>
~~~

The version of the Maven plugin and the version of the runtime starter belong to two different artifacts. Do not assume they must share the same version number. Choose each version based on the compatibility documentation and the project's dependency management.

## 2. The plugin does not analyze source code to generate documentation

When Maven runs the plugin, the plugin does not scan Java files such as @RestController, @GetMapping, or @Schema to generate OpenAPI on its own. Analyzing controllers and data models is already handled by the springdoc runtime when the application starts and serves documentation requests.

Actual flow:

~~~text
Maven build
   |
   | 1. Start Spring Boot application
   v
Spring Boot process
   |
   | springdoc runtime discovers controllers, DTOs,
   | annotations, configuration, and active routes
   v
OpenAPI endpoint: /v3/api-docs
   ^
   | 2. HTTP GET from Maven plugin
   |
springdoc-openapi-maven-plugin
   |
   | 3. Save response body
   v
target/openapi.json
~~~

If the application does not start, there is no OpenAPI endpoint to fetch. If the application runs without the springdoc runtime loaded, the plugin cannot add documentation generation capability by itself.

Therefore, the first question when the plugin fails is: does the configured URL return a valid OpenAPI document from a running application?

## 3. HTTP fetch is the central step

Under springdoc's default configuration, the JSON endpoint is typically:

~~~text
http://localhost:8080/v3/api-docs
~~~

The plugin sends an HTTP request to this URL. The response body is typically a JSON-formatted OpenAPI document. The plugin writes the received content to the file configured via outputFileName and outputDir.

You can simulate the plugin's step with curl:

~~~bash
curl -i http://localhost:8080/v3/api-docs
~~~

A successful response typically has:

- An HTTP status in the 2xx range, usually 200.
- A Content-Type corresponding to JSON.
- A body containing the openapi, info, and paths fields.
- Content that is an OpenAPI document, not an HTML login page or error page.

Because the plugin performs an HTTP fetch, it depends on network, host, port, context path, authentication, and application readiness. It cannot bypass those layers to read beans or controllers directly.

## 4. The endpoint must exist when the plugin runs

The application needs the OpenAPI endpoint enabled:

~~~yaml
springdoc:
  api-docs:
    enabled: true
~~~

If springdoc.api-docs.enabled: false is set, the /v3/api-docs endpoint is no longer served under the default configuration. In that case, the plugin cannot fetch the specification from this URL.

Swagger UI is not required for exporting JSON. You can disable the UI while keeping the documentation endpoint:

~~~yaml
springdoc:
  swagger-ui:
    enabled: false
  api-docs:
    enabled: true
~~~

This is often the right choice for CI: the application only needs to serve the OpenAPI document for the plugin to download. There is no need to bundle UI resources if the pipeline does not use Swagger UI.

If springdoc.api-docs.path is changed, the URL in the plugin configuration must change accordingly. For example:

~~~yaml
springdoc:
  api-docs:
    path: /internal/openapi
~~~

In that case, the plugin needs to call /internal/openapi and cannot keep using the default /v3/api-docs.

## 5. Why must the application start first?

Springdoc typically generates documentation from an active ApplicationContext. This process can depend on:

- Controller and handler beans created per profile.
- Jackson configuration and serialization modules.
- Bean Validation and DTO metadata.
- GroupedOpenApi and OpenApiCustomizer beans.
- Security schemes and OAuth2 configuration.
- MVC or WebFlux web stack.
- Context path, server port, and forwarded headers.
- Feature flags, conditional beans, and environment configuration.

This information is only fully available after the application initializes. Running the plugin before the server starts serving requests will not produce documentation.

In addition, if a controller or bean is only registered under the contract profile, that profile must be active when the application starts. The plugin does not infer the desired profile from the OpenAPI filename.

## 6. The Maven plugin does not start Spring Boot automatically

This is a common misconception. springdoc-openapi-maven-plugin only fetches documentation over HTTP. To automate the entire process in a single Maven command, another component must start the application.

The Spring Boot Maven Plugin provides start and stop goals that can be bound to the Maven lifecycle:

| Maven phase | Task |
|---|---|
| pre-integration-test | Start the Spring Boot application |
| integration-test | Springdoc Maven plugin calls the OpenAPI endpoint and saves the file |
| post-integration-test | Stop the started application |
| verify | Complete verification checks and validate the build |

Separating responsibilities makes troubleshooting easier: the Spring Boot Maven Plugin manages the application process, while the Springdoc Maven Plugin only performs the HTTP fetch.

## 7. Minimal Maven configuration for OpenAPI export

The example below illustrates a Spring Boot Maven project running on port 8080:

~~~xml
<build>
    <plugins>
        <plugin>
            <groupId>org.springdoc</groupId>
            <artifactId>springdoc-openapi-maven-plugin</artifactId>
            <version>1.4</version>
            <executions>
                <execution>
                    <id>export-openapi</id>
                    <phase>integration-test</phase>
                    <goals>
                        <goal>generate</goal>
                    </goals>
                </execution>
            </executions>
            <configuration>
                <apiDocsUrl>http://localhost:8080/v3/api-docs</apiDocsUrl>
                <outputFileName>openapi.json</outputFileName>
                <outputDir>${project.build.directory}</outputDir>
            </configuration>
        </plugin>
    </plugins>
</build>
~~~

Key properties:

| Property | Meaning |
|---|---|
| apiDocsUrl | HTTP URL the plugin calls to fetch the specification |
| outputFileName | Name of the generated file |
| outputDir | Directory to save the file |
| phase | Maven lifecycle phase in which the goal runs |
| goal generate | Performs fetching and saving the documentation |

The example uses project.build.directory, so the file typically resides at target/openapi.json. Do not write auto-generated files into src/main/resources or source directories just for convenience; the build directory is more appropriate because the file can be regenerated on every run.

## 8. Combining with Spring Boot Maven Plugin for start and stop

So a single mvn verify command can start the application automatically, configure the Spring Boot Maven Plugin:

~~~xml
<plugin>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-maven-plugin</artifactId>
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
    <configuration>
        <jvmArguments>-Dspring.profiles.active=contract</jvmArguments>
    </configuration>
</plugin>
~~~

The start goal launches the application in a separate process so Maven can continue executing goals in the lifecycle. The stop goal asks the process managed by the plugin to shut down.

The contract profile in the example is a profile dedicated to contract generation. Define this profile in the application configuration so the OpenAPI endpoint works and required dependencies are ready.

Combine this start/stop configuration with the Springdoc plugin in the previous section. When running mvn verify, Maven proceeds through pre-integration-test to start the application, to integration-test to fetch OpenAPI, and then to post-integration-test to stop the application if the lifecycle completes normally.

If the export goal or an integration test step fails early, Maven may halt the lifecycle before reaching post-integration-test. CI should have process cleanup at the job or runner level to avoid leaving a background server running after a failed build.

## 9. Maven lifecycle order determines the outcome

A valid configuration bound to the wrong phase can still fail. For example, if the generate plugin runs at package while the application is only started at pre-integration-test, the lifecycle order no longer matches the intent.

The typical order should be:

~~~text
validate
  |
compile
  |
test
  |
package
  |
pre-integration-test
  |-- spring-boot:start
  |
integration-test
  |-- springdoc-openapi:generate
  |
post-integration-test
  |-- spring-boot:stop
  |
verify
~~~

Placing the generate goal at integration-test ensures it runs after the start step at pre-integration-test. If Failsafe or another integration test plugin is present, check the execution order in the POM and ensure the server is ready before requests are sent.

Do not run only mvn package and expect a plugin bound to integration-test to run automatically. package stops before pre-integration-test and integration-test. Use mvn verify to go through all required phases.

## 10. Checking that the application is ready to receive requests

The start goal manages the Spring Boot process, but a process having started does not mean all business dependencies are ready.

The application may need to:

- Connect to a database and run migrations.
- Initialize caches or message brokers.
- Register clients with other services.
- Load configuration from a secret/config server.
- Initialize custom beans used during schema generation.
- Wait for a port or health endpoint to become ready.

If the plugin fetches immediately before the endpoint is ready, the build may hit connection refused, timeouts, or 5xx errors.

You can check readiness before fetching:

~~~bash
curl --fail --silent --show-error http://localhost:8080/actuator/health/readiness
~~~

The readiness endpoint is only available if Spring Boot Actuator is enabled and properly configured. Without Actuator, you can use a custom health endpoint or a script polling the OpenAPI endpoint with a bounded timeout.

Do not use an infinite polling loop. CI needs an explicit wait deadline and must print application logs upon timeout so developers can find the root cause.

## 11. Port and address must match

apiDocsUrl must point to the exact host, port, context path, and endpoint of the started application.

Example:

~~~yaml
server:
  port: 8091
  servlet:
    context-path: /store
~~~

With Spring MVC, the documentation URL will include the context path:

~~~text
http://localhost:8091/store/v3/api-docs
~~~

In that case, apiDocsUrl must use the corresponding full URL. If the configuration still calls http://localhost:8080/v3/api-docs, the plugin will call the wrong address.

With WebFlux, context path configuration may differ depending on the Spring Boot version; determine the actual URL the server is serving instead of copying Servlet MVC configuration.

In CI, use a dedicated, fixed port for the export process. If server.port=0 is used, Spring picks a random port; the plugin cannot guess that port from a static URL. To use a random port, an orchestration step is needed to capture the actual port and pass the corresponding URL to the plugin.

## 12. Profiles and environment configuration affect the specification

OpenAPI is retrieved from the running application, so the documentation depends on the active profile.

Example:

~~~yaml
spring:
  config:
    activate:
      on-profile: contract

springdoc:
  api-docs:
    enabled: true
  swagger-ui:
    enabled: false
~~~

In the contract profile, the team can enable the documentation endpoint and disable the UI. Controllers or beans that belong in the contract must be registered under this profile.

If the application uses the prod profile when exporting, the documentation may reflect production routes, security, or feature flags. If using the dev profile, experimental endpoints that must not be published may appear.

Create a dedicated contract profile if you need a stable, intentional configuration. Do not rely on the developer machine's default profile because it may differ from CI.

## 13. Data and dependent services during startup

Although springdoc does not need to invoke every business operation to generate schemas, the ApplicationContext must still start successfully. If controller beans depend on a database, service discovery, or secret manager, those dependencies can affect startup.

Ways to prepare the environment:

- Use a dedicated database for contract tests.
- Use Testcontainers or CI-managed service containers.
- Use fixed, reproducible seed data.
- Stub external services if they are unrelated to schema generation.
- Do not use production data to export contracts.
- Ensure migrations and seed data finish before calling the endpoint.

If schemas are customized based on runtime data, clearly identify which data affects the output. Ideally, OpenAPI should be stable per code version and contract configuration, not change unexpectedly based on personal data in the database.

## 14. Choosing JSON or YAML as output

The default /v3/api-docs endpoint typically returns JSON. If the application supports the YAML endpoint, you can configure the plugin to fetch that URL:

~~~xml
<configuration>
    <apiDocsUrl>http://localhost:8080/v3/api-docs.yaml</apiDocsUrl>
    <outputFileName>openapi.yaml</outputFileName>
    <outputDir>${project.build.directory}</outputDir>
</configuration>
~~~

The expected result is a YAML file in the build directory. Verify that the YAML endpoint is actually provided by the runtime version and configuration in use.

JSON is generally convenient for scripts, automation tools, and processing with jq. YAML is easy to read during manual review. Both formats must describe the same OpenAPI document.

Do not rename a JSON file extension to .yaml to fake YAML. The file format must match the response body received from the endpoint.

## 15. Naming and locating the exported file

The plugin allows configuring the filename and output directory:

~~~xml
<configuration>
    <apiDocsUrl>http://localhost:8080/v3/api-docs</apiDocsUrl>
    <outputFileName>store-openapi.json</outputFileName>
    <outputDir>${project.build.directory}/openapi</outputDir>
</configuration>
~~~

With this configuration, the file is expected at:

~~~text
target/openapi/store-openapi.json
~~~

Auto-generated files should be saved in target or an equivalent build directory. Maven may delete this directory on clean, so do not keep the sole authoritative source document there.

If you want to commit a contract copy to Git, create a deliberate copy step from the build artifact to a version-controlled directory after validation succeeds. Do not let the plugin directly overwrite reviewed documents in the source tree on every build.

## 16. Exporting multiple document groups

If the application declares multiple GroupedOpenApi beans, each group has its own endpoint, typically of the form:

~~~text
/v3/api-docs/public
/v3/api-docs/partner
/v3/api-docs/internal
~~~

The plugin only fetches the URL configured for that execution. If you need to export multiple groups, create separate executions with different URLs and filenames, or run the plugin multiple times with the corresponding configurations.

Example configuration layout:

~~~xml
<executions>
    <execution>
        <id>export-public-api</id>
        <phase>integration-test</phase>
        <goals>
            <goal>generate</goal>
        </goals>
        <configuration>
            <apiDocsUrl>http://localhost:8080/v3/api-docs/public</apiDocsUrl>
            <outputFileName>public-api.json</outputFileName>
            <outputDir>${project.build.directory}/openapi</outputDir>
        </configuration>
    </execution>
    <execution>
        <id>export-partner-api</id>
        <phase>integration-test</phase>
        <goals>
            <goal>generate</goal>
        </goals>
        <configuration>
            <apiDocsUrl>http://localhost:8080/v3/api-docs/partner</apiDocsUrl>
            <outputFileName>partner-api.json</outputFileName>
            <outputDir>${project.build.directory}/openapi</outputDir>
        </configuration>
    </execution>
</executions>
~~~

This is an execution organization pattern; check how the plugin version in use applies per-execution configuration and avoid unintended overrides from plugin-level configuration. Output filenames must be unique so executions do not overwrite each other's files.

The internal group may contain sensitive endpoints. Export and store that group only in artifacts or pipelines with appropriate access permissions.

## 17. Authentication and protecting documentation endpoints

The plugin is an HTTP client. If /v3/api-docs requires authentication, requests from the plugin must also satisfy that policy.

Common errors:

- HTTP 401 because the request lacks credentials.
- HTTP 403 because the CI account lacks authority.
- HTTP 302 to an HTML login page.
- Gateway blocking requests from the runner.
- Token expiring before the plugin fetches.

In a contract-test environment, you can choose one of these approaches:

1. Allow the documentation endpoint only from the runner's internal network and only in the contract profile.
2. Grant read permission for documentation to a dedicated CI service identity.
3. Configure an authentication HTTP header if the plugin version in use supports passing headers.
4. Use a separate HTTP fetch step that can pass credentials securely, then save the response as an artifact.

Do not hardcode tokens or passwords in a POM committed to Git. Use the CI secret store and scope the credentials strictly to reading documentation. Do not disable Spring Security completely in the export profile if unnecessary.

If using a profile that only allows documentation from localhost, ensure the server only opens in an isolated build environment and never release that profile to production.

## 18. Network and CI runtime environment

localhost in apiDocsUrl refers to the machine or network namespace where the Maven plugin runs. In a CI container, localhost points to that container itself, not necessarily the host machine or another Spring Boot container.

If the application and Maven run in the same container, localhost is usually appropriate. If they run in two different containers:

- Use the service hostname in the CI network, such as http://store-app:8080/v3/api-docs.
- Ensure the service container has started and its health check succeeds.
- Expose the right port between containers.
- Do not use localhost from the Maven container to call a different application container.

When using Kubernetes jobs or distributed runner environments, define DNS and network policies clearly. A request that works on a developer's machine may not work from a runner.

## 19. A complete build command

Once Spring Boot start/stop and Springdoc generate are configured in their respective phases, the typical command is:

~~~bash
mvn clean verify
~~~

This command runs preceding phases, including compile, test, package, starting the application at pre-integration-test, fetching OpenAPI at integration-test, stopping the application at post-integration-test, and running configured verify steps.

If you only run:

~~~bash
mvn springdoc-openapi:generate
~~~

then the generate goal is invoked directly, which does not mean Maven started Spring Boot beforehand. The application must be started separately and the URL must be reachable.

When debugging, you can run the application in a separate terminal and invoke the plugin. Only after confirming the HTTP endpoint works should you wire start/fetch/stop into the automated lifecycle.

## 20. Verifying the generated file

After the build, inspect the output file:

~~~text
target/openapi/openapi.json
~~~

You can do a quick check with:

~~~bash
test -s target/openapi/openapi.json
jq -e '.openapi and .info and .paths' target/openapi/openapi.json
~~~

The first command confirms the file exists and is non-empty. The second checks some basic JSON structure. This is only a smoke check; it does not replace an OpenAPI validator.

Check further:

- openapi has the expected version.
- info.title and info.version are correct.
- Important paths are present.
- Methods and operationIds are not missing.
- Request body and response schemas are accurate.
- Security schemes and scopes are not lost.
- Groups contain the right endpoints.
- No HTML login page or error content is inside the file.

If the file has content but the JSON parser reports an error, check the raw response from the URL and the plugin logs. Do not simply rename the file or hand-edit the output before finding the cause.

## 21. Plugin fetch does not replace contract validation

The plugin's job is to retrieve the HTTP response and write the file. Creating the file successfully does not prove the specification is valid OpenAPI, nor does it prove the contract is compatible with the previous version.

The pipeline should have separate steps:

~~~text
Start application
      |
      v
Fetch OpenAPI over HTTP
      |
      v
Check file exists and is not empty
      |
      v
Parse JSON/YAML
      |
      v
Validate OpenAPI document
      |
      v
Compare contract with baseline
      |
      v
Publish build artifact
~~~

You can use the OpenAPI Generator CLI to validate structure:

~~~bash
openapi-generator-cli validate -i target/openapi/openapi.json
~~~

Choose a validator version that supports the OpenAPI version and Schema Objects used by the project. An older validator may report errors or ignore new keywords even when the document is valid under the newer specification.

If you need to check for breaking changes, add a tool to compare OpenAPI against the baseline version. A successful fetch and a compatible contract are two separate criteria.

## 22. Integrating into a CI pipeline

A typical CI job can perform:

1. Check out source code and install the right JDK/Maven versions.
2. Resolve dependencies and run unit tests.
3. Start required dependent services.
4. Run Spring Boot with the contract profile.
5. Wait for the readiness endpoint.
6. Invoke the Springdoc Maven Plugin to export JSON/YAML.
7. Verify the file exists and is parseable.
8. Validate OpenAPI and check for breaking changes.
9. Upload the file as a build artifact.
10. Stop the application and clean up test services.

Example CI script snippet:

~~~bash
mvn clean verify
test -s target/openapi/openapi.json
openapi-generator-cli validate -i target/openapi/openapi.json
~~~

The exact commands depend on how the plugin is bound to the Maven lifecycle and the configured output location. If the plugin writes to target/openapi, the pipeline must use that exact path.

Do not publish the file if the fetch or validation step fails. The artifact must be tied to a specific commit/build so the team can trace the contract version.

## 23. Comparing the specification with a baseline

To control API changes, CI can compare the newly exported file against the OpenAPI version from the previous release.

Changes to watch for:

- Removing paths or HTTP methods.
- Removing required request parameters or changing data types.
- Adding a new required request field.
- Narrowing enums or value ranges.
- Changing response schemas in ways older clients cannot read.
- Changing security requirements or scopes.
- Changing status codes or media types.

Not every change is a breaking change. Adding an optional response field is usually less risky than removing a field or changing a type. The diff tool should be configured according to the organization's compatibility policy.

The baseline should be a reviewed or released artifact. Do not automatically take the latest file from an unstable branch as the baseline because that can mask contract-breaking changes.

## 24. Common errors when exporting

| Symptom | Possible cause | Resolution |
|---|---|---|
| Connection refused to /v3/api-docs | Application not running or wrong port in apiDocsUrl | Place start in pre-integration-test and check port/path |
| OpenAPI file not created but build stays green | failOnError is false | Set failOnError=true in CI |
| 401 or 403 when downloading document | Endpoint protected by Spring Security | Configure plugin headers using a token from a CI secret |
| File fetched from an old service | Port already occupied by a stale process | Use a dedicated port, check processes, and clean up prior jobs |
| 404 when calling a group | Wrong group name or endpoint URL | Check URL /v3/api-docs/{group} |
| Application does not stop after build | Missing Spring Application Admin or JMX port mismatch | Enable spring.application.admin.enabled and share JMX config between start/stop |
| Application keeps running after a failed build | Maven did not reach post-integration-test | Add an always-run CI cleanup or use ephemeral runners/containers |
| Generate goal runs before server is ready | Goal bound to wrong phase or slow startup | Bind generate to integration-test, increase maxAttempts/wait with justification |
| Plugin times out even though server is running | Document takes long to build or endpoint responds slowly | Increase springdoc plugin timeout and inspect server logs |
| Exported wrong profile | Spring Boot process started with another profile | Pass the right profiles/arguments to the start goal |
| Exported YAML but file has JSON extension | apiDocsUrl and outputFileName do not match | Use /v3/api-docs.yaml and openapi.yaml |
| Two group files overwrite each other | Same outputFileName or classifier | Set unique filenames and classifiers |
| Parallel build fails with port errors | Multiple modules share default HTTP/JMX ports | Assign dedicated ports or run exports sequentially |
| mvn springdoc-openapi:generate fails to connect | Invoked goal directly without starting server | Use mvn verify or start the endpoint beforehand |
| Maven Site report does not render | Missing compatible maven-site-plugin or using YAML | Use site plugin >= 3.9.1 and supply JSON |

When diagnosing, always separate three questions: is the application running, does the URL return the right OpenAPI document, and is the saved file valid? Separating these helps pinpoint whether the fault lies in Spring Boot, HTTP/network/security, or artifact verification.

## 25. Workflow from local to CI

Proceed in order:

1. Add the springdoc runtime starter matching Spring MVC or WebFlux.
2. Start the application and confirm /v3/api-docs returns OpenAPI JSON.
3. Determine the profile and configuration to use during export.
4. Add the Springdoc Maven Plugin with apiDocsUrl, outputFileName, and outputDir.
5. Add the Spring Boot Maven Plugin start/stop in the right lifecycle phases.
6. Place the generate goal in integration-test.
7. Configure port, context path, readiness, and dependent services.
8. Run mvn clean verify locally.
9. Verify the output file is non-empty, parseable, and contains the expected endpoints.
10. Add an OpenAPI validator and contract diff.
11. Configure CI secrets, networking, and artifact retention.
12. Run the pipeline on a clean runner to verify no dependency on a server running on a developer's machine.

Once the pipeline is stable, record the versions of JDK, Maven, Spring Boot, springdoc runtime, and Springdoc Maven Plugin. These versions help reproduce export results and diagnose differences between builds.

## 26. Takeaways

- Springdoc runtime generates OpenAPI from the running application; the Maven plugin only fetches the document over HTTP.
- The plugin does not scan source code and does not start Spring Boot automatically.
- apiDocsUrl must point to an active endpoint returning the right OpenAPI document.
- Spring Boot Maven Plugin can manage start and stop within the Maven lifecycle.
- Start the application at pre-integration-test, fetch at integration-test, and stop at post-integration-test.
- Use mvn verify to run through the integration phases; mvn package does not reach integration-test.
- Profiles, ports, context paths, readiness, databases, and dependent services affect export output.
- You can export JSON or YAML by choosing the corresponding endpoint and filename.
- Each document group needs its own URL and output file.
- Protect documentation endpoints with appropriate policies and supply CI credentials securely when needed.
- A successful HTTP fetch does not equate to valid OpenAPI or the absence of breaking changes.
- Add parse, validate, diff, and artifact publish steps to CI.

The core principle of the Springdoc plugin is fetching the specification from a Spring Boot application actively serving HTTP requests. Make sure the application starts with the right profile and is ready, configure the plugin to call the right endpoint, and verify the output file before using it as an artifact or input for contract-testing steps in CI.
