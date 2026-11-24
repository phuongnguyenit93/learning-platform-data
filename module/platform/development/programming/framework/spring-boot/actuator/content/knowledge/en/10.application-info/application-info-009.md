# Distinguishing info from the sbom Endpoint and Requirements for Providing a Software Bill of Materials

## 1. Two Different Questions About the Same Application

When a service is running, operators may need to know two things:

- "Which application is this, which version is it, and which build or commit produced it?"
- "Which software components make up this application build, with what versions and dependency relationships?"

`info` serves the first question with overview information provided by the application. `sbom` serves the second question with a software component inventory document, called a **Software Bill of Materials — SBOM**.

You can think of `info` as an identification label on a product, whereas an SBOM is the ingredients list accompanying that exact product. A label saying "payment service, version 1.0.0" is not enough to infer all libraries packaged inside.

The `sbom` endpoint was added in Spring Boot 3.3.0. This lesson uses the behavior of the **Spring Boot 3.3.x** line and Java 21; do not apply endpoint configurations from other version lines verbatim. [Spring Boot 3.3 Release Notes](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-3.3-Release-Notes)

## 2. info and sbom Differ in Data and Responsibilities

| Criterion | `info` | `sbom` |
| --- | --- | --- |
| Purpose | Identifying and describing the application | Providing a document of software components |
| Primary source | `InfoContributor` beans | Pre-generated or supplied SBOM files |
| Output format | JSON object containing contributed info sections | List of SBOM IDs, or contents of a document by ID |
| Level of detail | Determined by each info contributor | Determined by the SBOM generator tool, format, and collection scope |
| Does it scan vulnerabilities automatically? | No | No; the SBOM document can be used by other tools for analysis |
| Do they replace each other? | Does not replace the component inventory | Does not replace application identification info |

### 2.1. info Aggregates Information from Contributors

`GET /actuator/info` returns information contributed by `InfoContributor` beans. For example, an application may expose its name, version, build info, or Git info. [Info REST API 3.3](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/info.html)

The JSON example below is merely one intentional info configuration, not a structure every application is required to have:

```json
{
  "app": {
    "name": "payment-service",
    "version": "1.0.0"
  }
}
```

Common fields have their own conditions: `build` info ties to `META-INF/build-info.properties`; `git` info ties to `git.properties`. Specifically, `info.*` properties require enabling the `env` contributor in the 3.3 line. Having a `version` field does not mean you have a list of all dependencies. [Application Information](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.info)

If no contributor produces data, `{}` can still be a successful response from `info`. You must distinguish "the endpoint handled the request yet had no data" from "the URL does not exist".

### 2.2. sbom Has a List Operation and a Fetch-Document Operation

With the default `/actuator` prefix:

| HTTP request | Meaning |
| --- | --- |
| `GET /actuator/sbom` | Retrieve available SBOM IDs |
| `GET /actuator/sbom/application` | Retrieve the document with ID `application` |
| `GET /actuator/sbom/{id}` | Retrieve another registered document |

If only the application SBOM exists, the list operation returns:

```json
{"ids":["application"]}
```

The response when fetching an SBOM depends on the document's own format. For example, CycloneDX JSON uses media type `application/vnd.cyclonedx+json`. Do not mistake the `ids` object for the full component inventory. [SBOM REST API 3.3](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/sbom.html)

A useful SBOM can describe names, versions, package identifiers, licenses, hashes, and dependency relationships; completeness depends on inputs and the generator tool. Do not assert that every SBOM includes all of these fields.

It is also necessary to separate **the Java application's SBOM** from **the SBOM of the entire runtime environment**. A document generated from Java dependencies does not prove it also lists the OS, JVM, container image, or additional software installed on the host.

## 3. Requirements to Actually Serve an SBOM Over HTTP

These are two consecutive processing paths:

```text
At build time:
Dependency graph → SBOM generator tool → file attached to the build → packaging/distribution

At runtime:
Readable SBOM resource → endpoint enabled and exposed → access control → user retrieves document
```

Creating the file does not mean it is accessible over HTTP. Conversely, having the endpoint URL does not mean the application has a document to serve.

### 3.1. Having Actuator and HTTP Infrastructure

In a typical Spring Boot web application, you need:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
}
```

The snippet above is a **dependency declaration excerpt**, assuming versions are managed by a BOM or dependency management mechanism. It is not a standalone `build.gradle`.

`spring-boot-starter-web` here chooses Spring MVC for illustration. Applications using WebFlux can use the corresponding starter; there is no need to add both just to use SBOM.

### 3.2. Enabling the Endpoint and Exposing Over HTTP Are Two Separate Things

With Spring Boot 3.3:

```properties
management.endpoint.info.enabled=true
management.endpoint.sbom.enabled=true
management.endpoints.web.exposure.include=health,info,sbom
```

- `management.endpoint.sbom.enabled` controls enabling the endpoint.
- `management.endpoints.web.exposure.include` selects which endpoints are exposed over HTTP.
- If a matching `management.endpoints.web.exposure.exclude` exists, the exclusion list takes precedence.
- By default only `health` is exposed over HTTP; an endpoint being enabled does not automatically make its URL reachable.

`management.endpoint.*` properties are singular; the `management.endpoints.web.*` group is plural. Mistyping the group can prevent configuration from affecting the intended endpoint. [Enabling and Exposing Endpoints — Spring Boot 3.3](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.enabling)

Examples in this lesson assume unchanged management port, context path, endpoint prefix, and path mapping. If the application changes any of those values, use the actual address instead of `http://localhost:18083/actuator/...`.

### 3.3. Having the Document in a Location the Endpoint Recognizes and Can Read

With default detection in the 3.3 line, the standard locations are:

```text
classpath:META-INF/sbom/bom.json
classpath:META-INF/sbom/application.cdx.json
```

The default detected resource becomes the SBOM with ID `application`. If using another location, you can specify the location explicitly instead of relying on defaults. [SBOM support in Spring Boot 3.3](https://spring.io/blog/2024/05/24/sbom-support-in-spring-boot-3-3/)

You must inspect **the artifact being run**, not only the source directory. For example, a file present only in `build/reports` on a developer machine that is neither packaged nor mounted into the runtime environment is not enough for the endpoint to serve it.

Resources must also have appropriate read permissions. With external files, a path on the development machine does not automatically exist in the container or deployment host.

### 3.4. Callers Must Be Permitted to Access

Endpoint exposure and authentication/authorization are separate layers. If Spring Security is present and the application has not defined its own `SecurityFilterChain`, Actuator's default security configuration protects endpoints other than `health`. When an application defines its own filter chain, you must check the application's own rules. [Actuator Security](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.security)

The practice example below does not add Spring Security and binds only to `127.0.0.1` to focus on observing data. In real deployments, restrict SBOM read permissions to those who need it because the document can reveal technologies and library versions.

### 3.5. Content Must Match the Exact Application Build

For the endpoint to be operationally meaningful, the document must describe the running build:

- When dependencies change, regenerate the SBOM with that build.
- Never take an SBOM from an old release and attach it to a new build.
- Check collection scope: runtime dependencies, test dependencies, and non-Java components are not the same set.
- If using an externally mounted file, maintain alignment between the application version and the file version.

For example: `info.app.version=1.0.0` and a document titled "payment-service 1.0.0" are still just two data strings. Matching names do not prove the file was generated from the exact dependencies of that build.

## 4. Standalone Practice: Observing info and sbom

The goal is to test the difference between **identification data** and **component documentation**. The example uses a handwritten sample SBOM to provide a small, easy-to-compare input. The sample file **is not the application's complete SBOM**, because it does not list the Spring and Tomcat libraries actually used.

Create a separate project already having **Gradle Wrapper 8.5** and **JDK 21**. The example pins Spring Boot at `3.3.0` to reproduce early-3.3 behavior; this is an illustrative milestone, not a claim about the latest release version.

### 4.1. Project Structure

```text
actuator-sbom-demo/
├── settings.gradle
├── build.gradle
├── gradlew
├── gradlew.bat
├── gradle/wrapper/...
└── src/main/
    ├── java/example/SbomDemoApplication.java
    └── resources/
        ├── application.properties
        └── META-INF/sbom/application.cdx.json
```

The `gradlew`, `gradlew.bat`, and `gradle/wrapper` files are the standard Wrapper bundle; do not replace them with empty text files.

`settings.gradle`:

```groovy
rootProject.name = 'actuator-sbom-demo'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.0'
}

group = 'example'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation platform('org.springframework.boot:spring-boot-dependencies:3.3.0')
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
}
```

The BOM in `platform(...)` manages dependency versions; it is not the SBOM file returned by the endpoint. Even though both contain "BOM", the two concepts have different responsibilities.

### 4.2. Java Program

`src/main/java/example/SbomDemoApplication.java`:

```java
package example;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SbomDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(SbomDemoApplication.class, args);
    }
}
```

This is the complete startup class of a Spring Boot project, compiled with the project's dependencies; it is not a standard-library-only program run with `javac SbomDemoApplication.java`.

### 4.3. Configuring Both Data Sources

`src/main/resources/application.properties`:

```properties
server.address=127.0.0.1
server.port=18083

management.endpoint.info.enabled=true
management.endpoint.sbom.enabled=true
management.endpoints.web.exposure.include=health,info,sbom

management.info.env.enabled=true
info.app.name=actuator-sbom-demo
info.app.version=1.0.0
```

Here `management.info.env.enabled` only enables the contributor reading `info.*` for the `info` endpoint. It does not generate an SBOM document and does not enable the `env` endpoint.

`src/main/resources/META-INF/sbom/application.cdx.json`:

```json
{
  "bomFormat": "CycloneDX",
  "specVersion": "1.5",
  "version": 1,
  "metadata": {
    "component": {
      "type": "application",
      "name": "actuator-sbom-demo",
      "version": "1.0.0"
    }
  },
  "components": []
}
```

`components: []` is an intentional choice for the practice data in order to observe the file-serving mechanism. Do not conclude from it that a Spring Boot application has no dependencies.

### 4.4. Build and Run

In PowerShell inside the sample project directory:

```powershell
.\gradlew.bat clean bootJar
java -jar .\build\libs\actuator-sbom-demo-1.0.0.jar
```

On Linux/macOS, use `./gradlew clean bootJar` and `java -jar build/libs/actuator-sbom-demo-1.0.0.jar`. The first build needs to download Gradle/plugins/dependencies if not already cached.

Open a second terminal. Use `curl.exe` on Windows to avoid confusion with PowerShell's alias:

```powershell
curl.exe -sS http://localhost:18083/actuator/info
curl.exe -sS http://localhost:18083/actuator/sbom
curl.exe -i http://localhost:18083/actuator/sbom/application
```

With the exact sample configuration and no extra contributors, the first two JSON bodies are equivalent to:

```json
{"app":{"name":"actuator-sbom-demo","version":"1.0.0"}}
```

```json
{"ids":["application"]}
```

The third request succeeds with the JSON document placed in `application.cdx.json`; the expected media type is `application/vnd.cyclonedx+json`. Do not compare all HTTP headers byte-for-byte because they also depend on the server and environment. For JSON, property order and whitespace carry no business meaning.

You can check the file inside the JAR with:

```powershell
jar tf .\build\libs\actuator-sbom-demo-1.0.0.jar | Select-String 'sbom'
```

With the resource file placed manually in the example, you should find the entry containing `META-INF/sbom/application.cdx.json`. The listing command only confirms the file is present; it does not confirm completeness of the component inventory.

### 4.5. Varying Each Condition to Understand Results

For each test, stop the running process and rerun the JAR with the corresponding argument.

**Test A — Disable only the env contributor:**

```powershell
java -jar .\build\libs\actuator-sbom-demo-1.0.0.jar --management.info.env.enabled=false
```

With the sample project having no build/Git data or custom contributors, `info` returns `{}`. `sbom` still has ID `application` because the document file is still present.

**Test B — Point to a non-existent optional SBOM:**

```powershell
java -jar .\build\libs\actuator-sbom-demo-1.0.0.jar --management.endpoint.sbom.application.location=optional:classpath:missing.cdx.json
```

The `application.location` property specifies another resource, so the example's default file is no longer used. Because the resource is marked optional, the application can still start; if there are no additional SBOMs, `GET /actuator/sbom` returns:

```json
{"ids":[]}
```

`info` still has the name and version. This result shows that an existing endpoint and an empty document list can happen at the same time.

**Test C — Point to a missing required resource:**

```powershell
java -jar .\build\libs\actuator-sbom-demo-1.0.0.jar --management.endpoint.sbom.application.location=classpath:missing.cdx.json
```

With the endpoint still enabled and exposed as in the sample config, endpoint creation encounters a missing required resource and fails startup. This is not a case of "starting up cleanly and returning an empty inventory".

**Test D — Remove sbom from the HTTP exposure list:**

```powershell
java -jar .\build\libs\actuator-sbom-demo-1.0.0.jar --management.endpoints.web.exposure.include=health,info
```

Accessing `/actuator/info` can still succeed, yet `/actuator/sbom` is no longer mapped over HTTP in the sample config, even though the SBOM file remains inside the JAR. Specific HTTP outcomes may be affected if security filters or a gateway are added.

## 5. From a Sample File to a Build-Generated SBOM

In real applications, replace the handwritten file with a document generated from the exact build's inputs. Spring Boot supports working with Maven/Gradle CycloneDX plugins. [Generate a CycloneDX SBOM](https://docs.spring.io/spring-boot/3.3/how-to/build.html#howto.build.generate-sbom)

For a Gradle project using Spring Boot 3.3, the integration example in the documentation uses the plugin:

```groovy
id 'org.cyclonedx.bom' version '1.8.2'
```

This is **one line added to the existing `plugins` block**, not an entire build file.

When both the Spring Boot plugin and the CycloneDX plugin are applied, Spring Boot configures the SBOM generation task, places the document into `META-INF/sbom` of the JAR/WAR, and adds location/format metadata to the manifest. [Reacting to the CycloneDX Plugin](https://docs.spring.io/spring-boot/3.3/gradle-plugin/reacting.html#reacting-to-other-plugins.cyclonedx)

When switching the example to automatic generation, remove the handwritten sample SBOM file to avoid having two sources describing the application. Then rebuild, inspect the file inside the artifact, and fetch the document again through the endpoint.

Note the difference between running from the packaged artifact and running Java classes directly from an IDE. The packaging pipeline may add the document into the JAR while the IDE's classpath lacks that same file. Therefore, if it fails only when run from the IDE, check resources in that runtime environment before concluding the endpoint is broken.

A sound verification flow is: generate the SBOM from the current build → verify contents/scope → confirm the artifact contains the document → run that exact artifact → download the document by ID → cross-check identity and version.

## 6. Specifying Different Locations, Formats, and Multiple SBOMs

Below are alternative or extended configurations; they do not all need to be enabled simultaneously to run the basic example.

### 6.1. Application Document at a Custom Path

```properties
management.endpoint.sbom.application.location=classpath:inventory/application.spdx.json
management.endpoint.sbom.application.media-type=application/spdx+json
```

The configuration above requires providing the corresponding file at `src/main/resources/inventory/application.spdx.json` before building.

`media-type` describes the returned content type. Setting an SPDX media type for a CycloneDX file does not convert the document structure. To change formats, use an appropriate document generation/conversion tool.

### 6.2. Adding an SBOM of Another Scope

```properties
management.endpoint.sbom.additional.system.location=optional:file:/opt/inventory/system.spdx.json
management.endpoint.sbom.additional.system.media-type=application/spdx+json
```

This is a Linux path example. If the file exists in the runtime environment and is readable, the endpoint gains ID `system`; retrieve that document with `GET /actuator/sbom/system`. `optional:` allows skipping when the file is missing; it does not generate a placeholder document. Specifying locations, media types, and additional SBOMs is supported by Spring Boot via these properties. [SBOM configuration](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.sbom)

Do not mistakenly place additional SBOM configuration under `info.*`. A custom object named `info.sbom` is only data for `info` if a corresponding contributor reads it; it does not register a resource with the `sbom` endpoint.

## 7. Layer-Appropriate Diagnostics

| Symptom | What to distinguish | First direction to check |
| --- | --- | --- |
| `info` returns `{}` | Endpoint may work yet have no contributed data | Contributors, `management.info.env.enabled`, `info.*` data, build/Git resources |
| `sbom` returns `{"ids":[]}` | Endpoint works yet has no registered documents | Classpath files, `application.location`, and missing optional resources |
| `/sbom` has IDs yet requesting another ID returns not found | Document URL uses an unlisted ID | Fetch the list first and use the exact ID |
| HTTP 401 or 403 | May be blocked at authentication/authorization layer | Credentials, roles, filter chains, and gateway; status code alone does not prove whether a document exists |
| HTTP 404 | May be wrong URL, port, exposure, disabled endpoint, or wrong ID | Distinguish listing URL from document URL; check path and exposure configuration |
| Startup fails after setting `location` | May reference a missing required resource | Path, mount, read permissions, and root-cause logs |
| SBOM downloads yet misses expected libraries | File presence does not guarantee data completeness | Generator tool scope, actual dependencies, and the build that produced the file |

Do not fix every symptom by enabling all endpoints. Fixes must match the failing layer: data, packaging, endpoint configuration, access address, or security.

## 8. Self-Check on Applicability

1. **If `info` has the application version, do we already know all library versions?**  
   No. The application version does not imply the dependency inventory; you need to read an appropriate SBOM document or equivalent inventory source.

2. **If the JSON file exists on the developer's machine, is adding `sbom` to exposure enough?**  
   No. The file must exist in the runtime environment at a location the endpoint recognizes or is configured with, and must be readable.

3. **Does an empty ID list mean the endpoint is disabled?**  
   No. That can be a successful response when no documents are registered.

4. **Does enabling the endpoint automatically generate or update the SBOM on each request?**  
   No. You must arrange document generation/provisioning separately; the endpoint serves the resource.

5. **Does a Java SBOM prove the entire container has no vulnerabilities?**  
   No. You must consider the scope of inventoried components and analyze them with an appropriate tool; an inventory alone is not a security conclusion.

After this hands-on lesson, learners should be able to point out three separate pieces of evidence: where `info` gets its data, where the SBOM is generated/supplied from, and which configurations allow authorized users to retrieve the document of the exact running application build.
