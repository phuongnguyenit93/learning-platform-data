# Reading the SBOM Catalog, File Locations, and Configured Additional SBOMs

## 1. What Questions Does SBOM Help Answer?

An SBOM is a **Software Bill of Materials**. When inspecting a deployment, you may need to know which document describes the application, whether that document lives inside the application package or in an external file, and whether separate manifests exist for other parts of the system.

Spring Boot added support for the `sbom` endpoint starting in version 3.3.0. The endpoint serves existing SBOM documents; generating the bill of materials during the build is a separate task. [SbomEndpoint Javadoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/sbom/SbomEndpoint.html)

Three concepts to distinguish:

| Concept | Meaning | Example |
| --- | --- | --- |
| SBOM identifier | Name used to select the document via the endpoint. | `application`, `platform` |
| Resource location | Where the process reads the document's bytes from. | `classpath:sbom/application.cdx.json` |
| Content and format | The actual manifest returned. | CycloneDX JSON document |

The identifier is not a file path. Nor does a `.json` extension alone determine whether the content is CycloneDX, SPDX, or another format.

This article uses **Java 21 and Spring Boot 3.3.13**. The focus is on reading the catalog, tracing location configuration, and verifying returned documents; vulnerability scanning or verifying manifest completeness requires additional tools and evidence.

## 2. Two Types of Requests to Read

| GET Request | Result |
| --- | --- |
| `/actuator/sbom` | Object containing the `ids` array of available SBOMs. |
| `/actuator/sbom/{id}` | Content of the selected SBOM document. |

Catalog example:

```json
{
  "ids": ["application", "platform"]
}
```

The catalog lists only names. It does not return an object per document with `location`, `fileName`, or `components` fields. When an id is selected, the response body conforms to the corresponding SBOM format. [`sbom` REST contract](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/sbom.html)

Reading flow:

```text
GET /actuator/sbom
    -> pick a name from ids
    -> GET /actuator/sbom/{id}
    -> inspect Content-Type and document contents
    -> match id against resource location configuration
```

For example, `/actuator/sbom/application` may return CycloneDX JSON. You must read configuration or deployment package info to know where the source document resides; do not infer the file path from that URL.

## 3. How Should File Location Configuration Be Read?

Key properties in Boot 3.3:

```properties
management.endpoint.sbom.application.location=classpath:sbom/application.cdx.json
management.endpoint.sbom.application.media-type=application/vnd.cyclonedx+json

management.endpoint.sbom.additional.platform.location=classpath:sbom/platform.cdx.json
management.endpoint.sbom.additional.platform.media-type=application/vnd.cyclonedx+json
```

`application` is the primary SBOM. Each key under `additional` creates an extra identifier; in the example, the key `platform` leads to `/actuator/sbom/platform`. Documents are selected independently and are not merged into a single combined component list. These property groups are published in the [Boot 3.3 configuration properties appendix](https://docs.spring.io/spring-boot/3.3/appendix/application-properties/index.html).

### 3.1. `classpath:` and `file:` Are Two Different Sources

- `classpath:sbom/application.cdx.json`: reads the resource with that name on the running application's classpath.
- `file:./inventory/platform.cdx.json`: reads an external file, resolving relative paths from the process's working directory.
- `file:/opt/demo/inventory/platform.cdx.json`: example of an absolute location on a system with that path.

In a typical Gradle project:

```text
Source file:
  src/main/resources/sbom/application.cdx.json

Runtime resource name:
  classpath:sbom/application.cdx.json

Inside Boot's executable JAR:
  BOOT-INF/classes/sbom/application.cdx.json

URL to read document:
  /actuator/sbom/application
```

`BOOT-INF/classes` packaging is a characteristic of executable JARs built by Boot. It does not become part of the `classpath:` resource name you write in configuration. [Packaging executable archives](https://docs.spring.io/spring-boot/3.3/gradle-plugin/packaging.html)

With `file:`, check the filesystem seen by the **application process**. A path on a developer machine does not automatically exist inside a container; nor is a file created outside the JAR carried along automatically when only copying the JAR to another host.

### 3.2. Auto-Detection vs. Explicit Location

When `application.location` is not specified, Boot has a supported auto-detection mechanism for the application SBOM. If a location is specified, verify that exact resource instead of assuming a document just built elsewhere will be selected.

Boot supports auto-detecting media types for CycloneDX, SPDX, and Syft; `media-type` can be set to specify it explicitly. Setting the header does not convert content from one format to another. [SBOM format and location configuration](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html)

## 4. Standalone Practice Project with Two SBOMs

### 4.1. Purpose of the Sample Documents

The two small documents below are written to verify the publishing and resource-reading flow. The application document lists only one component to keep the example clear; it is **not a complete bill of dependencies** for a Boot application. The `platform` document is a separate sample for the exercise, not a scan of the running operating system.

When applying to a real release, use a tool that generates the manifest from the exact build and check that tool's component scope.

Prepare JDK 21, Gradle 8.5, and the structure:

```text
sbom-read-demo/
├── settings.gradle
├── build.gradle
└── src/main/
    ├── java/demo/sbom/SbomReadApplication.java
    └── resources/
        ├── application.properties
        └── sbom/
            ├── application.cdx.json
            └── platform.cdx.json
```

### 4.2. Build and Startup Class

`settings.gradle`:

```groovy
rootProject.name = 'sbom-read-demo'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
}

group = 'demo'
version = '1.0.0'

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

dependencies {
    implementation platform('org.springframework.boot:spring-boot-dependencies:3.3.13')
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
}

springBoot {
    mainClass = 'demo.sbom.SbomReadApplication'
}

tasks.named('bootJar') {
    archiveFileName = 'sbom-read-demo.jar'
}
```

`src/main/java/demo/sbom/SbomReadApplication.java`:

```java
package demo.sbom;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SbomReadApplication {
    public static void main(String[] args) {
        SpringApplication.run(SbomReadApplication.class, args);
    }
}
```

### 4.3. Two CycloneDX JSON Documents

`src/main/resources/sbom/application.cdx.json`:

```json
{
  "bomFormat": "CycloneDX",
  "specVersion": "1.5",
  "version": 1,
  "metadata": {
    "component": {
      "type": "application",
      "name": "sbom-read-demo",
      "version": "1.0.0"
    }
  },
  "components": [
    {
      "type": "library",
      "group": "org.springframework.boot",
      "name": "spring-boot-actuator",
      "version": "3.3.13",
      "purl": "pkg:maven/org.springframework.boot/spring-boot-actuator@3.3.13"
    }
  ]
}
```

`src/main/resources/sbom/platform.cdx.json`:

```json
{
  "bomFormat": "CycloneDX",
  "specVersion": "1.5",
  "version": 1,
  "metadata": {
    "component": {
      "type": "application",
      "name": "platform-inventory-lab",
      "version": "1.0.0"
    }
  },
  "components": []
}
```

`bomFormat` identifies the format family; `specVersion` is the specification version; `version` at the root is the version of the manifest itself. It differs from `metadata.component.version`, which is the version of the described component. The `components` list belongs to the CycloneDX structure, not a field added by the Actuator endpoint. [CycloneDX JSON 1.5 specification](https://cyclonedx.org/docs/1.5/json/)

### 4.4. Enabling HTTP Exposure and Selecting Resources

`src/main/resources/application.properties`:

```properties
server.address=127.0.0.1
server.port=8080

management.endpoints.web.exposure.include=health,sbom

management.endpoint.sbom.application.location=classpath:sbom/application.cdx.json
management.endpoint.sbom.application.media-type=application/vnd.cyclonedx+json

management.endpoint.sbom.additional.platform.location=classpath:sbom/platform.cdx.json
management.endpoint.sbom.additional.platform.media-type=application/vnd.cyclonedx+json
```

`sbom` is enabled by default in Boot 3.3; HTTP exposes only `health` by default. If global configuration disabled endpoints by default, enable it specifically with `management.endpoint.sbom.enabled=true`. HTTP access permissions depend on the application's security setup. [Endpoint configuration](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html)

The example omits Spring Security and listens only on loopback for practice. In real environments, component names and versions can be internal information requiring appropriate read access controls.

Start with Gradle 8.5:

```shell
gradle bootRun
```

If an appropriate Gradle Wrapper is present, use `./gradlew bootRun` or `.\gradlew.bat bootRun`. Keep the application running to execute the read requests below.

## 5. Reading the Catalog and Each Document's Content

### 5.1. Confirming Exposed IDs

Open a second terminal in the project directory:

```shell
curl -i http://127.0.0.1:8080/actuator/sbom
```

In PowerShell, use `curl.exe` if `curl` points to another command. With the two created resources, the catalog has two ids: `application` and `platform`. Element order does not carry catalog meaning.

If `jq` is installed, you can sort for deterministic checks:

```bash
curl -fsS http://127.0.0.1:8080/actuator/sbom | jq '.ids | sort'
```

Filter stdout in the example:

```json
[
  "application",
  "platform"
]
```

These two ids do not mean the documents' contents have been fully validated; they tell you which names are exposed in the experiment.

### 5.2. Reading the Primary SBOM and Additional SBOM

```shell
curl -i http://127.0.0.1:8080/actuator/sbom/application
curl -i http://127.0.0.1:8080/actuator/sbom/platform
```

Both use media type `application/vnd.cyclonedx+json` because both configuration and sample contents are CycloneDX JSON. The response body is the corresponding document directly, not wrapped inside an Actuator `sbom` or `data` object. [Response for a specific SBOM](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/sbom.html)

With `jq`, read the primary component name of the application document:

```bash
curl -fsS http://127.0.0.1:8080/actuator/sbom/application \
  | jq -r '.metadata.component.name'
```

Stdout:

```text
sbom-read-demo
```

Repeat with id `platform`:

```bash
curl -fsS http://127.0.0.1:8080/actuator/sbom/platform \
  | jq -r '.metadata.component.name'
```

Stdout:

```text
platform-inventory-lab
```

Here, id `platform` differs from component name `platform-inventory-lab`. Changing the configuration key does not modify the `name` field inside the document.

### 5.3. Saving Body and Headers Separately

To verify the received document, save the body separately from headers:

```shell
curl -fsS -D application.headers -o downloaded-application.cdx.json http://127.0.0.1:8080/actuator/sbom/application
```

- `application.headers` contains HTTP headers, used to inspect status and `Content-Type`.
- `downloaded-application.cdx.json` contains the document body.

Do not pass `curl -i` output including headers as input to a JSON reader. Only when HTTP succeeds with the right content does an SBOM inspection tool have valid data to analyze.

Compare the bytes of the downloaded document against the source resource in the experiment using PowerShell:

```powershell
$sourceHash = (Get-FileHash -Algorithm SHA256 -LiteralPath 'src/main/resources/sbom/application.cdx.json').Hash
$downloadHash = (Get-FileHash -Algorithm SHA256 -LiteralPath 'downloaded-application.cdx.json').Hash
$sourceHash -eq $downloadHash
```

With unmodified example files, running from that exact resource build, the expected output is:

```text
True
```

This is a byte-level check, unlike merely opening JSON and seeing similar-looking fields. In a real release pipeline, compare against the document belonging to the **exact deployed artifact**, because files in the source directory may have changed after the build.

## 6. Checking Locations When Running from a JAR

To observe the boundary between source code, artifact, and runtime resources:

1. Stop the `bootRun` process to free the port.
2. Build the executable JAR.
3. Inspect the packaged resources.
4. Run the JAR and re-read the catalog and both documents.

```shell
gradle bootJar
jar tf build/libs/sbom-read-demo.jar
java -jar build/libs/sbom-read-demo.jar
```

In the `jar tf` listing, look for:

```text
BOOT-INF/classes/sbom/application.cdx.json
BOOT-INF/classes/sbom/platform.cdx.json
```

These are the two entries to observe, not the entire stdout of `jar tf`. When running the JAR, configuration still uses `classpath:sbom/...`; URLs still use ids. The path inside the archive is not an external file path you can arbitrarily open with `file:`.

If the IDE serves the SBOM yet the executable JAR lacks the resources, check the packaging process rather than changing endpoint URLs to source directory names.

## 7. Additional SBOMs from External Files and the optional Prefix

### 7.1. Registering an ID from an External File

Suppose the deployment process supplies `inventory/system.cdx.json` outside the JAR. You can add:

```properties
management.endpoint.sbom.additional.system.location=file:./inventory/system.cdx.json
management.endpoint.sbom.additional.system.media-type=application/vnd.cyclonedx+json
```

When the document is present in the runtime environment, the id used to read it is `system`, corresponding to `/actuator/sbom/system`. The filename `system.cdx.json` and directory `inventory` belong to the resource location, not segments automatically appended to the URL.

In the experiment, you can create the external file by copying the sample `platform.cdx.json` to that location. That only tests the path; the copied content still describes the old sample until you replace it with an actual manifest.

Check before running:

- Which working directory is the path resolved from?
- Does the file exist on the application's host/container?
- Can the OS account running the application read the file?
- Does the content match the declared format?

A path without the `optional:` prefix is treated as a mandatory resource in this configuration; a missing file can cause endpoint initialization to fail at application startup. Read the logs instead of assuming the application still serves HTTP normally.

### 7.2. Using optional When a Document Is Not Required

If the absence of the document is acceptable by design, use:

```properties
management.endpoint.sbom.additional.system.location=optional:file:./inventory/system.cdx.json
management.endpoint.sbom.additional.system.media-type=application/vnd.cyclonedx+json
```

`optional:` avoids startup failure caused by a missing file. When the file is absent at initialization, Boot skips that SBOM. This prefix does not create a document or an empty file; the presence of the configuration key does not certify the id is published. After startup, read the catalog and verify the actual document. [Optional SBOMs in Spring Boot 3.3](https://spring.io/blog/2024/05/24/sbom-support-in-spring-boot-3-3/)

Do not use `optional:` to mask a packaging error for an SBOM that is mandatory in a release. When changing configuration or resource sources in the experiment, restart and re-check; do not assume hot-reloading of runtime files without verifying that behavior.

### 7.3. Multiple Formats Can Be Exposed Together

Each id can point to its own document with its own format and media type. Example configuration for an SPDX JSON document supplied by the deployment pipeline:

```properties
management.endpoint.sbom.additional.os.location=optional:file:./inventory/os.spdx.json
management.endpoint.sbom.additional.os.media-type=application/spdx+json
```

This snippet illustrates configuration for an existing SPDX document; it does not turn the CycloneDX document in the experiment into SPDX. With different formats, parsers must read the corresponding schema; do not assume every SBOM has CycloneDX's `components` array.

The `Content-Type` value must match the actual data. Changing `media-type` alone does not convert JSON/XML, switch SBOM standards, or supply missing fields.

## 8. Connection to Build-Time Generated SBOMs

In real pipelines, the manifest is typically generated from the dependency graph of the exact build, packaged with the artifact, and then served via the endpoint.

For a project using the Spring Boot 3.3 Gradle plugin, documentation for this branch instructs adding the CycloneDX Gradle plugin:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'org.cyclonedx.bom' version '1.8.2'
}
```

This is a replacement `plugins` block for an automatic manifest-generation experiment on the sample project; the remaining dependency and Java configurations still need to be kept. The plugin version above is the example used in Boot 3.3 documentation. [Generating a CycloneDX SBOM during build](https://docs.spring.io/spring-boot/3.3/how-to/build.html)

The Boot Gradle plugin configures the CycloneDX task, places the SBOM in the artifact's `META-INF/sbom` area, and adds `Sbom-Format`/`Sbom-Location` entries to the manifest. Inspect the actual artifact and manifest to confirm the output name/location of the plugin version in use. [Boot Gradle plugin CycloneDX integration](https://docs.spring.io/spring-boot/3.3/gradle-plugin/reacting.html)

When testing auto-detection of the newly generated document, remove the `management.endpoint.sbom.application.location` property pointing to the hand-written document, rebuild, and run the new artifact. Then read `/actuator/sbom/application` and inspect the document actually received.

If an explicit location pointing to the sample file remains, adding the SBOM-generating plugin does not guarantee the endpoint switched to the new document. That is why you must trace configuration, artifact, and response together instead of merely seeing the `application` id.

Three stages have distinct responsibilities:

```text
Build tool
    -> generates bill of materials per configured dependency scope

Packaging/deployment pipeline
    -> delivers the right document to the runtime environment

sbom endpoint
    -> exposes the catalog and serves the selected document
```

Adding an additional SBOM does not expand the build tool's scan scope. For instance, an OS-layer manifest or non-JVM component manifest must be generated and supplied by a pipeline appropriate for that scope. [Overview of Spring Boot 3.3 SBOM support](https://spring.io/blog/2024/05/24/sbom-support-in-spring-boot-3-3/)

## 9. Evidence Limits and Common Errors

HTTP 200 on the catalog indicates the catalog read succeeded. HTTP 200 on a document indicates the request received content. Those two results do not automatically prove:

- The document fully complies with the declared SBOM specification.
- The component list covers the entire application, image, or operating system.
- The document accurately matches the deployed artifact if external file sources were altered.
- All components are vulnerability-free or all license info is accurate.

Those conclusions require format validation, scope verification, artifact linkage, and specialized analysis. In the experiment, two small files help test the serving flow; do not use them as full release evidence.

| Symptom | What to Check |
| --- | --- |
| 404 at `/actuator/sbom` | Are port/base path, endpoint enablement, HTTP exposure, and endpoint config right? |
| Catalog exists but expected id is missing | Check config keys, resources, deployment build, and which documents are actually present. |
| An id cannot be retrieved | Use the exact id from the catalog; check logs and resource source. |
| 401 or 403 | Check HTTP authentication and access permissions. |
| App fails to start after adding SBOM | Check whether mandatory resource exists/is readable and read startup error logs. |
| Downloaded JSON cannot be parsed | Separate headers from body; check HTTP status and actual content. |
| Headers look right but SBOM tool rejects it | Check document structure against spec; declaring media type does not validate content. |
| Works in IDE but fails in JAR | Check packaged resources, classpath config, and external file locations. |
| Built new SBOM but endpoint still serves sample | Check `application.location`, running artifact, and downloaded document. |

In multi-instance deployments, identify which instance served the response. The same `file:` path does not guarantee different hosts/containers hold identical bytes. When uniformity must be proven, compare the document or checksum against an identified release source.

## 10. Practice and Self-Check

Perform on the standalone project:

1. Run with two classpath resources, read the catalog, and confirm the two ids `application`, `platform`.
2. Read each document, check `Content-Type` and the two different `metadata.component.name` values.
3. Download the application document to a file and compare its hash against the exact experiment resource.
4. Build and run the executable JAR, locate both resources in the archive, and repeat the read step.
5. Register `system` from a prepared external file; verify the path relative to the working directory and re-read the catalog.
6. In a separate run, try configuring a nonexistent file with `optional:`; compare startup logs, catalog, and document readability against mandatory resource config.

Questions you should be able to answer:

- Why does `platform` in the URL not necessarily match the filename or component name inside the SBOM?
- How is a file placed in `src/main/resources` addressed when running from an executable JAR?
- Does `additional.system.location` merge components into `application` automatically?
- Why is `optional:` not proof that the document is currently available?
- Why does changing `media-type` not change the content format?
- What must be checked to know the endpoint serves the manifest of the exact deployed build?

Answers need to connect identifier, resource location, format configuration, artifact, and response content; that is the evidence required to read SBOMs rigorously.
