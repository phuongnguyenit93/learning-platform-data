# Configuring Documentation URL, Output Directory, and Filename

springdoc-openapi generates the OpenAPI specification while the Spring Boot application is running and serves the documentation over HTTP. When you need to save the specification as a file during the build, you can use the springdoc-openapi Maven Plugin or Gradle Plugin. Both plugins call the application's documentation endpoint, download the JSON/YAML content, and write it to the configured directory and filename.

Three values must be distinguished:

1. **Documentation URL (apiDocsUrl):** the HTTP URL the plugin calls to fetch OpenAPI.
2. **Output directory (outputDir):** the directory on the build machine used to store the downloaded file.
3. **Output filename (outputFileName):** the filename created inside that directory.

For example, the plugin calls `http://localhost:8080/v3/api-docs` and writes the content to `target/openapi/openapi.json`. If the application changes the documentation endpoint to `/docs/spec`, the fetch URL must change. If you want to save to `build/contracts`, change outputDir. If you want to name it `shop-api-v1.json`, change outputFileName.

These properties belong to the build plugin. They do not change springdoc's runtime endpoint and do not change the Swagger UI URL.

## 1. Distinguishing the runtime endpoint from the export file

By default, Springdoc serves OpenAPI JSON at `/v3/api-docs` and YAML at `/v3/api-docs.yaml`. You can change the JSON endpoint with `springdoc.api-docs.path`:

~~~yaml
springdoc:
  api-docs:
    path: /docs/spec
~~~

Then the application serves JSON at `/docs/spec`. If the build plugin still calls the default URL `/v3/api-docs`, the plugin will hit the wrong endpoint.

The Swagger UI path is a separate setting. `springdoc.swagger-ui.path` only changes the UI page URL; it does not change the OpenAPI endpoint that the plugin needs to call.

| Component | Example | Controlled by |
| --- | --- | --- |
| OpenAPI JSON runtime | `/v3/api-docs` | `springdoc.api-docs.path` |
| OpenAPI YAML runtime | `/v3/api-docs.yaml` | springdoc's YAML endpoint |
| Swagger UI page | `/swagger-ui.html` | `springdoc.swagger-ui.path` |
| URL the plugin fetches from | `http://localhost:8080/v3/api-docs` | `apiDocsUrl` |
| Directory where file is written | `target/openapi` | `outputDir` |
| Name of written file | `shop-api.json` | `outputFileName` |

Determine the runtime URL first, then configure the plugin to point to that exact URL. Only then choose where to save and what to name the file on the build machine.

## 2. Export flow during the build

The plugin does not analyze Java source code to reconstruct schemas on its own. It starts the Spring Boot application, calls the HTTP endpoint provided by springdoc, and saves the response to a file.

~~~mermaid
flowchart TD
    A[Build starts] --> B[Start Spring Boot]
    B --> C[Springdoc generates runtime OpenAPI]
    C --> D[Plugin calls apiDocsUrl]
    D --> E{HTTP response successful?}
    E -->|Yes| F[Download JSON or YAML]
    F --> G[Write outputDir/outputFileName]
    G --> H[Send file to artifact or CI]
    E -->|No| I[Report error or continue per failOnError]
    H --> J[Stop application]
~~~

Because the documentation is retrieved from a running application, profiles, environment variables, databases, security, and beans can affect the generated OpenAPI. The plugin must be able to start the application in the build environment and the endpoint must be reachable from the build process.

## 3. Choosing the right apiDocsUrl

The default URL is usually:

~~~text
http://localhost:8080/v3/api-docs
~~~

If the application changes its port or context path, the URL must reflect the new address:

| Application configuration | Corresponding apiDocsUrl |
| --- | --- |
| Port 8080, no context path | `http://localhost:8080/v3/api-docs` |
| Port 9090 | `http://localhost:9090/v3/api-docs` |
| Context path `/shop` | `http://localhost:8080/shop/v3/api-docs` |
| Custom API docs path `/docs/spec` | `http://localhost:8080/docs/spec` |
| Management port 9090, base path `/actuator` | For example `http://localhost:9090/actuator/openapi` if that is the exposed springdoc endpoint |

Do not guess the URL from the application name or Swagger UI URL. Open the endpoint directly or inspect the springdoc and Actuator configuration to confirm the exact URL.

If API docs require authentication, the plugin must send the appropriate headers. If using a reverse proxy, gateway, or HTTPS, the URL must be reachable from the build environment and the certificate must be trusted by the JVM.

## 4. Configuring URL, directory, and filename with Maven

The Springdoc OpenAPI Maven Plugin has the `generate` goal, which runs in the `integration-test` phase by default. The plugin works alongside `spring-boot-maven-plugin`: the application is started before integration tests, the plugin fetches the documentation, and the application is stopped in the `post-integration-test` phase.

Default values:

| Maven property | Default | Meaning |
| --- | --- | --- |
| `apiDocsUrl` | `http://localhost:8080/v3/api-docs` | URL to fetch JSON or YAML |
| `outputDir` | `target` (project.build.directory) | Directory where the file is written |
| `outputFileName` | `openapi.json` | Output filename |
| `attachArtifact` | `false` | Whether to attach the file as a Maven artifact for install/deploy |
| `attachArtifactClassifier` | `openapi` | Classifier when attaching |
| `timeout` | `60` seconds | Connection and read timeout |
| `failOnError` | `false` | Whether the build fails if fetching/writing documentation errors |

Configuration example in `pom.xml`:

~~~xml
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
          <id>pre-integration-test</id>
          <goals><goal>start</goal></goals>
        </execution>
        <execution>
          <id>post-integration-test</id>
          <goals><goal>stop</goal></goals>
        </execution>
      </executions>
    </plugin>

    <plugin>
      <groupId>org.springdoc</groupId>
      <artifactId>springdoc-openapi-maven-plugin</artifactId>
      <version>1.6</version>
      <executions>
        <execution>
          <id>generate-openapi</id>
          <phase>integration-test</phase>
          <goals><goal>generate</goal></goals>
        </execution>
      </executions>
      <configuration>
        <apiDocsUrl>http://localhost:8080/v3/api-docs</apiDocsUrl>
        <outputDir>${project.build.directory}/openapi</outputDir>
        <outputFileName>shop-api.json</outputFileName>
        <failOnError>true</failOnError>
        <timeout>60</timeout>
      </configuration>
    </plugin>
  </plugins>
</build>
~~~

Run:

~~~bash
mvn verify
~~~

The file is written at `target/openapi/shop-api.json`. In this configuration, apiDocsUrl points to the JSON endpoint, outputDir selects the `target/openapi` directory, outputFileName sets the name `shop-api.json`, and failOnError makes the build report an error if downloading or writing the documentation fails.

`outputDir` is a directory, not the full path of the file. `outputFileName` is the filename placed inside that directory. Separating the two values lets you change the directory without changing the filename.

## 5. Exporting YAML with Maven

To export YAML, call the YAML endpoint and set the matching file extension:

~~~xml
<configuration>
  <apiDocsUrl>http://localhost:8080/v3/api-docs.yaml</apiDocsUrl>
  <outputDir>${project.build.directory}/openapi</outputDir>
  <outputFileName>shop-api.yaml</outputFileName>
  <failOnError>true</failOnError>
</configuration>
~~~

Result: `target/openapi/shop-api.yaml`.

Do not just rename a JSON file to `.yaml`. The extension does not convert the content. The `/v3/api-docs.yaml` endpoint is what asks springdoc to return YAML; the filename only helps users and tools recognize the downloaded format.

## 6. Using Maven properties to change directory and filename

You can use Maven properties to reuse and override settings per build:

~~~xml
<properties>
  <openapi.output.dir>${project.build.directory}/contracts</openapi.output.dir>
  <openapi.output.file>shop-api.json</openapi.output.file>
  <openapi.url>http://localhost:8080/v3/api-docs</openapi.url>
</properties>

<plugin>
  <groupId>org.springdoc</groupId>
  <artifactId>springdoc-openapi-maven-plugin</artifactId>
  <version>1.6</version>
  <configuration>
    <apiDocsUrl>${openapi.url}</apiDocsUrl>
    <outputDir>${openapi.output.dir}</outputDir>
    <outputFileName>${openapi.output.file}</outputFileName>
    <failOnError>true</failOnError>
  </configuration>
</plugin>
~~~

Override from the command line:

~~~bash
mvn verify \
  -Dopenapi.output.dir=target/contracts/public \
  -Dopenapi.output.file=public-api.json
~~~

The plugin's user properties can also be passed directly:

~~~bash
mvn verify \
  -Dspringdoc.outputDir=target/contracts \
  -Dspringdoc.outputFileName=shop-api.json \
  -Dspringdoc.apiDocsUrl=http://localhost:8080/v3/api-docs
~~~

## 7. Attaching the OpenAPI file as a Maven artifact

By default `attachArtifact` is false. When set to true, the plugin attaches the OpenAPI file to the project artifact so it can be installed or deployed alongside other artifacts:

~~~xml
<configuration>
  <apiDocsUrl>http://localhost:8080/v3/api-docs</apiDocsUrl>
  <outputDir>${project.build.directory}/openapi</outputDir>
  <outputFileName>shop-api.json</outputFileName>
  <attachArtifact>true</attachArtifact>
  <attachArtifactClassifier>openapi</attachArtifactClassifier>
  <failOnError>true</failOnError>
</configuration>
~~~

The default classifier is `openapi`. If building multiple documents together, each execution needs its own classifier when attaching to avoid colliding artifact coordinates.

Attaching does not change where the file is written locally. outputDir and outputFileName still govern the file's location in the workspace; attachArtifact governs whether the file is attached to the Maven project for publishing with artifacts.

## 8. Exporting multiple groups with Maven

If the application declares groups such as public, admin, or partner, each group has its own OpenAPI endpoint. You can create multiple executions, each using its own URL and filename:

~~~xml
<plugin>
  <groupId>org.springdoc</groupId>
  <artifactId>springdoc-openapi-maven-plugin</artifactId>
  <version>1.6</version>
  <executions>
    <execution>
      <id>export-public-api</id>
      <goals><goal>generate</goal></goals>
      <configuration>
        <apiDocsUrl>http://localhost:8080/v3/api-docs/public</apiDocsUrl>
        <outputDir>${project.build.directory}/openapi</outputDir>
        <outputFileName>public-api.json</outputFileName>
        <attachArtifactClassifier>public-openapi</attachArtifactClassifier>
        <attachArtifact>true</attachArtifact>
        <failOnError>true</failOnError>
      </configuration>
    </execution>
    <execution>
      <id>export-admin-api</id>
      <goals><goal>generate</goal></goals>
      <configuration>
        <apiDocsUrl>http://localhost:8080/v3/api-docs/admin</apiDocsUrl>
        <outputDir>${project.build.directory}/openapi</outputDir>
        <outputFileName>admin-api.json</outputFileName>
        <attachArtifactClassifier>admin-openapi</attachArtifactClassifier>
        <attachArtifact>true</attachArtifact>
        <failOnError>true</failOnError>
      </configuration>
    </execution>
  </executions>
</plugin>
~~~

The results include `target/openapi/public-api.json` and `target/openapi/admin-api.json`. The group name in the URL must match the group declared in the application.

## 9. Configuring URL, directory, and filename with Gradle

The Springdoc OpenAPI Gradle Plugin provides the `generateOpenApiDocs` task. The plugin starts the application using the `bootRun` task's configuration, downloads the OpenAPI description, and then stops the application. By default, the file is written at `build/openapi.json`.

Kotlin DSL example in `build.gradle.kts`:

~~~kotlin
plugins {
    java
    id("org.springframework.boot") version "3.5.16"
    id("org.springdoc.openapi-gradle-plugin") version "2.1.0"
}

dependencies {
    implementation("org.springdoc:springdoc-openapi-starter-webmvc-api:2.10.0")
}

openApi {
    apiDocsUrl.set("http://localhost:8080/v3/api-docs")
    outputDir.set(layout.buildDirectory.dir("openapi"))
    outputFileName.set("shop-api.json")
    waitTimeInSeconds.set(60)
}
~~~

Run:

~~~bash
./gradlew generateOpenApiDocs
~~~

Result: `build/openapi/shop-api.json`.

In Gradle, apiDocsUrl is the HTTP URL fetched; outputDir is the output directory; outputFileName is the filename; waitTimeInSeconds is the wait time for the application to start and become ready to serve the endpoint. The Gradle Plugin requires the application to have the springdoc dependency to provide the endpoint.

## 10. Equivalent configuration in Groovy DSL

If the project uses `build.gradle` instead of `build.gradle.kts`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.16'
    id 'org.springdoc.openapi-gradle-plugin' version '2.1.0'
}

dependencies {
    implementation 'org.springdoc:springdoc-openapi-starter-webmvc-api:2.10.0'
}

openApi {
    apiDocsUrl = 'http://localhost:8080/v3/api-docs'
    outputDir = layout.buildDirectory.dir('openapi')
    outputFileName = 'shop-api.json'
    waitTimeInSeconds = 60
}
~~~

Both DSLs share the same goal. Choose the right syntax for the build script type; do not mix Kotlin DSL's `set(...)` into Groovy DSL.

## 11. Exporting YAML with Gradle

With the Gradle Plugin, a URL ending with `.yaml` causes the plugin to save the content in YAML format:

~~~kotlin
openApi {
    apiDocsUrl.set("http://localhost:8080/v3/api-docs.yaml")
    outputDir.set(layout.buildDirectory.dir("contracts"))
    outputFileName.set("shop-api.yaml")
}
~~~

Result: `build/contracts/shop-api.yaml`. If you use a JSON URL but set the filename to `.yaml`, the content will still be JSON. Keep the endpoint, content, and filename extension aligned.

## 12. Using customBootRun to choose a documentation-generation profile

Documentation is produced from the running application, so profiles affect configuration and can affect OpenAPI. For example, an `openapi` profile can disable external service connections, load test data, and enable documentation for the build.

~~~kotlin
openApi {
    apiDocsUrl.set("http://localhost:8080/v3/api-docs")
    outputDir.set(layout.buildDirectory.dir("contracts"))
    outputFileName.set("shop-api.json")
    customBootRun {
        args.set(listOf("--spring.profiles.active=openapi"))
    }
}
~~~

`customBootRun` lets you customize arguments, JVM arguments, system properties, environment variables, main class, classpath, and working directory. Specified properties override the corresponding values from `bootRun`; remaining properties continue to use `bootRun` configuration.

If the application runs on port 9090 in a custom configuration, synchronize both customBootRun and apiDocsUrl:

~~~kotlin
openApi {
    apiDocsUrl.set("http://localhost:9090/v3/api-docs")
    customBootRun {
        args.set(listOf("--server.port=9090", "--spring.profiles.active=openapi"))
    }
}
~~~

## 13. Exporting multiple groups with Gradle

The Gradle Plugin supports `groupedApiMappings`, which is a map between each group's documentation URL and its output filename:

~~~kotlin
openApi {
    outputDir.set(layout.buildDirectory.dir("contracts"))
    groupedApiMappings.set(
        mapOf(
            "http://localhost:8080/v3/api-docs/public" to "public-api.json",
            "http://localhost:8080/v3/api-docs/admin" to "admin-api.json",
            "http://localhost:8080/v3/api-docs/partner" to "partner-api.json"
        )
    )
}
~~~

When using groupedApiMappings, the plugin ignores the single apiDocsUrl and outputFileName. Each URL in the map is fetched and written to its own file inside outputDir.

## 14. URLs with authentication, HTTPS, or a reverse proxy

Some applications protect the OpenAPI endpoint with Spring Security or are reachable only over HTTPS. Both the Maven and Gradle plugins provide ways to send HTTP headers when fetching documentation.

Maven:

~~~xml
<configuration>
  <apiDocsUrl>https://localhost:8443/v3/api-docs</apiDocsUrl>
  <outputDir>${project.build.directory}/openapi</outputDir>
  <outputFileName>internal-api.json</outputFileName>
  <headers>
    <Authorization>Bearer ${env.OPENAPI_TOKEN}</Authorization>
  </headers>
  <failOnError>true</failOnError>
</configuration>
~~~

Gradle Kotlin DSL:

~~~kotlin
val openApiToken = providers.environmentVariable("OPENAPI_TOKEN")

openApi {
    apiDocsUrl.set("https://localhost:8443/v3/api-docs")
    outputDir.set(layout.buildDirectory.dir("openapi"))
    outputFileName.set("internal-api.json")
    requestHeaders.set(
        openApiToken.orNull?.let {
            mapOf("Authorization" to "Bearer $it")
        } ?: emptyMap()
    )
}
~~~

Token values should be supplied from CI secrets, not committed into pom.xml or build.gradle. If using HTTPS with an internal certificate not yet trusted by the JVM, the Gradle Plugin supports a trust store and trust store password. Create a trust store containing the trusted CA/certificate; do not disable TLS verification to bypass certificate errors.

If the application sits behind a reverse proxy, the URL must be reachable from the build machine. When the application generates server URLs based on forwarded headers, you can send x-forwarded-host or x-forwarded-port in request headers according to the application's configuration. This affects the server URL generated in OpenAPI; it does not change the output directory or filename.

## 15. Exporting documentation from a management port or custom path

If springdoc is placed on a dedicated management port, the plugin must call the management endpoint URL instead of the default URL on the application port.

~~~yaml
server:
  port: 8080
management:
  server:
    port: 9090
  endpoints:
    web:
      base-path: /actuator
      exposure:
        include: "health,openapi,swagger-ui"
springdoc:
  use-management-port: true
~~~

With the configuration above, confirm the OpenAPI endpoint registered by springdoc under the Actuator base path, such as `/actuator/openapi`, then configure:

~~~kotlin
openApi {
    apiDocsUrl.set("http://localhost:9090/actuator/openapi")
    outputDir.set(layout.buildDirectory.dir("contracts"))
    outputFileName.set("shop-api.json")
}
~~~

If you change management.endpoints.web.base-path, change the plugin URL accordingly. Similarly, if springdoc.api-docs.path changes the runtime endpoint on the application port, the plugin must use the new URL. outputDir and outputFileName do not depend on those runtime paths.

## 16. Manual export with curl

You do not necessarily have to configure a build plugin for a one-off documentation download. You can call the endpoint directly with curl:

~~~bash
mkdir -p build/contracts
curl --fail --silent --show-error \
  http://localhost:8080/v3/api-docs \
  --output build/contracts/shop-api.json
~~~

Exporting YAML:

~~~bash
mkdir -p build/contracts
curl --fail --silent --show-error \
  http://localhost:8080/v3/api-docs.yaml \
  --output build/contracts/shop-api.yaml
~~~

With an endpoint requiring a token:

~~~bash
curl --fail --silent --show-error \
  -H "Authorization: Bearer $OPENAPI_TOKEN" \
  http://localhost:8080/v3/api-docs \
  --output build/contracts/internal-api.json
~~~

The `--output` parameter determines the save location and filename for that curl invocation. The directory must exist before writing. Use `--fail` so the command returns an error exit code on 4xx/5xx HTTP statuses, preventing the pipeline from silently saving an error page as an OpenAPI file.

## 17. Checking the file after export

After the build, verify location, name, format, and content:

~~~bash
ls -l target/openapi
head -n 20 target/openapi/shop-api.json
jq -r '.openapi, .info.title, .info.version' target/openapi/shop-api.json
~~~

With Gradle:

~~~bash
ls -l build/contracts
jq -r '.openapi, .info.title, .info.version' build/contracts/shop-api.json
~~~

For YAML, use an appropriate YAML reader tool to verify the content. Do not rely solely on the filename extension. Check that the content actually has the expected openapi, info, paths, and components fields.

Output formatting also has a small difference between the two plugins: Maven writes the exact content returned by the endpoint; if you want pretty-printed JSON, you can enable the springdoc.writer-with-default-pretty-printer=true property in the application. The Gradle Plugin pretty-prints JSON before writing, while YAML is written as returned by the endpoint.

You can check that the file is non-empty:

~~~bash
test -s build/contracts/shop-api.json
~~~

If the file does not exist, check apiDocsUrl, application status, startup wait time, permissions, and outputDir. If the file exists but contains an error page, check HTTP status, redirects, authentication, and response content type.

## 18. Putting exported files into CI artifacts

The target or build directory is usually treated as a build directory and may be deleted on clean. In CI, after generating documentation, configure the artifact upload step to point to the exact path:

~~~text
Maven:
target/openapi/shop-api.json

Gradle:
build/contracts/shop-api.json
~~~

If you want to store the file in the repository, choose a clearly managed directory, such as `docs/api/`, and consider committing snapshots only when the project wants to review contract changes via Git. If the goal is a CI artifact, keep it in the build directory and upload it as a build artifact.

With Maven, you can use `attachArtifact=true` to install/deploy documentation along with Maven artifacts. With Gradle, you can add a separate copy or publish task depending on the pipeline. Writing a file to outputDir by itself does not mean the file has been published to a repository or artifact store.

## 19. Common errors

**Plugin cannot connect to localhost.** The application has not started, is running on a different port, has a different context path, or the endpoint path changed. Verify the URL directly before editing outputDir.

**Changed springdoc.swagger-ui.path but the plugin still fails.** That property changes the UI page. The plugin needs the OpenAPI URL, typically /v3/api-docs or a custom springdoc.api-docs.path.

**Changed outputFileName but cannot find the file.** Check outputDir and outputFileName together. The file resides in the outputDir directory with the exact configured name.

**File has a YAML extension but content is JSON.** The URL still calls the JSON endpoint. Call /v3/api-docs.yaml and use a .yaml filename.

**Build succeeds but no file is produced.** The Maven plugin defaults to failOnError=false, so documentation download errors may only be logged. Enable failOnError=true in CI.

**Maven build fails but the application is still running.** If the build fails before the post-integration-test phase, the stop goal may not be called. Check and stop old processes before the next build.

**Gradle reports inability to connect after the wait time.** Inspect startup logs, URL, and increase waitTimeInSeconds when the application needs more startup time.

**Gradle reports the port is already in use.** Another process is listening on apiDocsUrl's port, possibly an application left over from a previous build. Stop that process or pick another port in sync with configuration.

**Endpoint returns 401 or 403.** Supply authentication headers to the plugin via headers/requestHeaders and pull tokens from CI secrets.

**Plugin HTTP client cannot fetch the endpoint, yet a browser can open it.** Check DNS, network routes, proxies, certificates, and authentication headers from the build environment. CORS is a browser policy; the plugin calls the endpoint from the build process, so plugin download failures typically need troubleshooting in HTTP connectivity, authentication, or TLS.

**HTTPS reports an untrusted certificate.** Configure a trust store with the appropriate CA/certificate. Do not skip TLS verification.

**Generated document has wrong host or port in server URL.** Check forwarded headers and reverse proxy configuration. requestHeaders can send forwarded headers if the application is configured to trust and process them.

**Multiple groups overwrite the same file.** Use a distinct outputFileName for each group and a distinct classifier if attaching to a Maven repository.

**Gradle groupedApiMappings ignores apiDocsUrl.** When groupedApiMappings is configured, the plugin ignores the single apiDocsUrl and outputFileName. Put each group's URL and filename into the map.

## 20. Output configuration checklist

- [ ] Identified the runtime OpenAPI endpoint serving JSON or YAML.
- [ ] Checked port, context path, custom API docs path, or management port.
- [ ] Pointed apiDocsUrl to the right endpoint, not mistakenly to Swagger UI.
- [ ] Set outputDir to the target directory.
- [ ] Set outputFileName to a filename with an extension matching the format.
- [ ] For YAML, called the .yaml endpoint and named the file .yaml.
- [ ] For Maven CI, enabled failOnError=true.
- [ ] For Gradle, set waitTimeInSeconds matching startup time.
- [ ] If the endpoint requires authentication, supplied headers/requestHeaders from CI secrets.
- [ ] For internal HTTPS, configured the trust store properly.
- [ ] If exporting multiple groups, used distinct filenames and verified each URL.
- [ ] Verified the file exists, is non-empty, and is parseable after the build.
- [ ] Configured CI to upload the exact output path.
- [ ] Distinguished saving a local file from attaching/publishing an artifact.

## 21. Conclusion

For stable OpenAPI export, first determine the runtime URL that springdoc serves. Then configure the plugin to call the right apiDocsUrl, write into outputDir, and name the file with outputFileName. Maven defaults to writing target/openapi.json; Gradle defaults to writing build/openapi.json. The JSON/YAML format depends on the called endpoint, so align the URL with the filename extension. In CI, enable fail-on-error, handle authentication and HTTPS properly, and verify and upload the exact generated file.

## 22. References

- [springdoc-openapi Maven and Gradle Plugins](https://springdoc.org/plugins.html): export workflow, Maven/Gradle configuration, URLs, directories, filenames, and build profiles.
- [springdoc-openapi Maven Plugin README](https://github.com/springdoc/springdoc-openapi-maven-plugin): apiDocsUrl, outputDir, outputFileName, attachArtifact, failOnError, headers, and YAML.
- [springdoc-openapi Gradle Plugin README](https://github.com/springdoc/springdoc-openapi-gradle-plugin): openApi configuration, groupedApiMappings, customBootRun, requestHeaders, trustStore, and YAML.
- [springdoc-openapi Configuration Properties](https://springdoc.org/properties.html): runtime properties such as springdoc.api-docs.path and springdoc.api-docs.enabled.
- [springdoc-openapi Getting Started](https://springdoc.org/getting-started.html): default JSON/YAML endpoints and Swagger UI paths.
