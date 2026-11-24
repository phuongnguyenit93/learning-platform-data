# Generating an SBOM with Compatible Tools Such as CycloneDX

## 1. What Is an SBOM and Why Generate It in the Build Pipeline?

A **Software Bill of Materials (SBOM)** is a structured, machine-readable inventory describing the software components that make up a product or artifact. A useful SBOM typically records application and library names/versions, suppliers, package URLs (PURLs), dependency relationships, licenses, and checksums when available.

Imagine a Spring Boot service:

~~~text
catalog-service 1.0.0
├── application classes
├── Spring Boot
│   ├── Spring Framework
│   ├── Jackson
│   └── ...
├── logging libraries
└── other runtime dependencies
~~~

When a new CVE emerges in a library, development and operations teams need to answer quickly:

- Which products contain the affected package?
- Is the package used directly or pulled in via a transitive dependency?
- Which version is currently deployed?
- Is the package inside the executable JAR, the container image, or only on the test/build classpath?
- What patch or alternative version is available?
- Does the SBOM accurately describe the released artifact?

**An SBOM provides a catalog and component traceability.** It does not by itself prove software is secure, does not automatically detect all vulnerabilities, and does not prove a dependency is actually invoked at runtime. To manage supply-chain risk, combine SBOMs with vulnerability scanning, license reviews, provenance, signing, VEX, and update workflows.

This lesson walks through generating SBOMs for Java/Spring Boot projects with **CycloneDX**, integrating with Maven/Gradle, embedding the SBOM in the executable JAR so Spring Boot Actuator can serve it, generating container image SBOMs with Syft or Buildpacks, validating schemas, and scanning for CVEs.

### Learning Outcomes

After this lesson, you will be able to:

1. Distinguish SBOMs for a Maven dependency graph, an executable JAR, and a container image.
2. Explain key CycloneDX fields: bomFormat, specVersion, metadata, components, dependencies, PURL, and serial number.
3. Generate CycloneDX JSON using CycloneDX Maven Plugin; choose appropriately between makeBom and makeAggregateBom.
4. Integrate the plugin with Spring Boot 4.1.2 and Java 17, and inspect META-INF/sbom/application.cdx.json inside the JAR.
5. Use Spring Boot Actuator /actuator/sbom to retrieve SBOMs under controlled access.
6. Know how to use CycloneDX Gradle Plugin, Paketo SBOMs, and Syft to cover both application dependencies and image packages.
7. Validate an SBOM, compare inventory against the dependency graph, scan with Grype, and link results to image digests.
8. Design CI gates, store SBOM artifacts, and handle missing dependencies, wrong scopes, or incompatible schemas.

## 2. Choosing the Right SBOM Scope

A common mistake is generating one SBOM file and assuming it describes everything deployed. In practice, there are multiple inventory layers:

| SBOM type | Suitable tool | Typically described components | Limitations to understand |
| --- | --- | --- | --- |
| **Project/dependency SBOM** | CycloneDX Maven/Gradle Plugin | Direct and transitive dependencies in the build model | Does not automatically include container OS packages |
| **Executable JAR SBOM** | CycloneDX + Spring Boot packaging | Dependency inventory embedded in the application | Does not necessarily reflect runtime components outside the JAR |
| **Container image SBOM** | Syft, Docker Scout, Buildpacks SBOM | OS packages, JRE, Java libraries, and packages detected in the image | Results depend on the scanner's catalogers |
| **Build-time SBOM** | CNB/Paketo build output | Tool/build dependencies and components used only during build | May not appear in the final runtime image |
| **Runtime inventory** | Runtime/host inventory tools | Components present on the host or running | Requires clearly defining environment, timing, and collection method |

**Example:** CycloneDX Maven Plugin reads the Maven project/dependency model. It is useful for knowing which Java libraries were resolved. However, if the container also includes CA certificates, shell utilities, font packages, or a JRE from the run image, those packages are not necessarily in the Maven SBOM. A scanner run against the final image can discover those additional components.

A mature pipeline typically stores **both an application SBOM and an image SBOM**, linking them to the same release/version, source commit, and image digest. Do not merge the two inventories arbitrarily because they serve different scopes and purposes.

## 3. CycloneDX and Key Data Fields

CycloneDX is an SBOM standard developed by OWASP and published as Ecma International standard **ECMA-424**. The standard supports describing software components, services, dependency relationships, licenses, vulnerabilities, cryptographic assets, and many other BOM types. Tools typically use JSON or XML.

Abbreviated example of the JSON structure:

~~~json
{
  "bomFormat": "CycloneDX",
  "specVersion": "1.6",
  "serialNumber": "urn:uuid:...",
  "version": 1,
  "metadata": {
    "component": {
      "type": "application",
      "name": "catalog-service",
      "version": "1.0.0"
    }
  },
  "components": [
    {
      "type": "library",
      "group": "org.springframework",
      "name": "spring-core",
      "version": "6.x",
      "purl": "pkg:maven/org.springframework/spring-core@6.x"
    }
  ],
  "dependencies": [
    {
      "ref": "pkg:maven/org.springframework/spring-core@6.x",
      "dependsOn": []
    }
  ]
}
~~~

This is an **illustrative template**, not an SBOM generated from an actual project. Specific versions and dependency relationships must come from a resolved build.

| Field | Meaning | Usage |
| --- | --- | --- |
| **bomFormat** | BOM format, e.g., CycloneDX | Identifies the appropriate parser |
| **specVersion** | CycloneDX schema version | Selects a compatible validator/scanner |
| **serialNumber** | Identifier of a BOM document | Distinguishes BOM instances |
| **version** | Revision of the BOM document | Do not confuse with the application version |
| **metadata.component** | Product described by the BOM | Verifies matching artifact/name/version |
| **components** | List of components | Package/library inventory |
| **dependencies** | Relationships between components | Understands the dependency graph |
| **purl** | Package URL identifying a package | Matches packages against advisories/databases |
| **bom-ref** | Unique reference for a component in the BOM | Links components in the dependency graph |
| **hashes** | Artifact checksums when available | Verifies package bytes |
| **licenses** | License metadata when provided | Supports license compliance |
| **externalReferences** | Links to source, VCS, website, or docs | Traces origin |

**Do not assume every component includes complete hashes, licenses, or PURLs.** A plugin can only record data supplied by the build model/repository/tool. Empty values or NOASSERTION do not prove a component has no license; they may simply indicate the data has not been determined.

### Choosing a Schema Version

The examples below use CycloneDX Maven Plugin **2.9.3** and schema **1.6**, a published compatible release pair. CycloneDX 1.7 is a newer schema; upgrade the plugin and schema together once your registry, scanners, validators, and SBOM consumers support it. Do not set schemaVersion 1.7 on a plugin that only supports 1.6.

References: [CycloneDX Specification](https://cyclonedx.org/specification/overview/) · [ECMA-424](https://ecma-international.org/publications-and-standards/standards/ecma-424/) · [CycloneDX Maven Plugin](https://cyclonedx.github.io/cyclonedx-maven-plugin/).

## 4. Right Tool for Each Stage

| Tool | Primary input | Output | When to use |
| --- | --- | --- | --- |
| **CycloneDX Maven Plugin** | Maven POM and dependency resolution | CycloneDX XML/JSON | Maven projects, multi-module reactors |
| **CycloneDX Gradle Plugin** | Gradle configurations/dependency graph | CycloneDX SBOM | Gradle projects |
| **Spring Boot SBOM integration** | SBOM generated during build | SBOM inside JAR/WAR and Actuator endpoint | When embedding the SBOM in the executable artifact |
| **Syft** | Container image, directory, archive, filesystem | CycloneDX, SPDX, Syft JSON | Inventorying the final image and OS packages |
| **Paketo/CNB SBOM** | Buildpacks contributing to the image | Syft, SPDX, CycloneDX per buildpack support | Images built with Cloud Native Buildpacks |
| **CycloneDX CLI** | CycloneDX BOM | Validate, diff, merge, convert, sign/verify | BOM QA and management |
| **Grype** | Image or SBOM | Vulnerability findings | Matching packages against vulnerability databases |

You do not need to use every tool. Choose at least one tool to generate an application SBOM and a step to verify the inventory of the **exact released artifact**. If the container includes OS/JRE packages supplied by a builder, add an image-level SBOM.

## 5. Maven + Spring Boot 4.1.2 + Java 17: Complete Example

Spring Boot integrates with CycloneDX Maven Plugin. When using spring-boot-starter-parent, the parent POM already provides suitable plugin configuration. To enable SBOM generation, declare the plugin in the project's build/plugins.

### 5.1. Directory Structure

~~~text
sbom-demo/
├── pom.xml
└── src/
    └── main/
        ├── java/dev/example/sbom/
        │   └── SbomDemoApplication.java
        └── resources/
            └── application.properties
~~~

### 5.2. pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>4.1.2</version>
        <relativePath/>
    </parent>

    <groupId>dev.example</groupId>
    <artifactId>sbom-demo</artifactId>
    <version>1.0.0</version>
    <name>sbom-demo</name>
    <packaging>jar</packaging>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webmvc</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-actuator</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
            <plugin>
                <groupId>org.cyclonedx</groupId>
                <artifactId>cyclonedx-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**Why does the POM omit the CycloneDX plugin version?** This example uses the Spring Boot starter parent, where Spring Boot manages the plugin version and SBOM configuration. The parent also configures the SBOM to be generated where the application can package it into the JAR. If your project uses a corporate parent or only imports the spring-boot-dependencies BOM, you must manage the plugin version/execution/output path explicitly as shown in Section 7.

### 5.3. SbomDemoApplication.java

File src/main/java/dev/example/sbom/SbomDemoApplication.java:

~~~java
package dev.example.sbom;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@RestController
public class SbomDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(SbomDemoApplication.class, args);
    }

    @GetMapping("/api/status")
    public String status() {
        return "SBOM_DEMO_OK";
    }
}
~~~

The /api/status endpoint simply confirms the executable JAR runs. It does not generate or compute an SBOM at runtime; the CycloneDX plugin generated the SBOM during the build.

### 5.4. application.properties

File src/main/resources/application.properties:

~~~properties
spring.application.name=sbom-demo
server.port=8080

management.endpoints.web.exposure.include=health,sbom
management.endpoint.sbom.access=read-only
~~~

The sbom endpoint is exposed over HTTP for this lab. In production, protect it with Spring Security, network policies, or a separate management port. An SBOM can reveal library names/versions and dependency structure; **do not leave this endpoint publicly exposed**.

### 5.5. Build and Locate the SBOM

In the directory containing pom.xml:

~~~bash
java -version
mvn -version
mvn clean verify
~~~

With the Spring Boot parent configuration, the application SBOM is generated at:

~~~text
target/classes/META-INF/sbom/application.cdx.json
~~~

The Spring Boot executable JAR contains this resource on the application classpath:

~~~text
BOOT-INF/classes/META-INF/sbom/application.cdx.json
~~~

Verify the file in output classes:

~~~bash
test -s target/classes/META-INF/sbom/application.cdx.json
~~~

Verify the entry in the executable JAR:

~~~bash
jar tf target/sbom-demo-1.0.0.jar | grep 'META-INF/sbom/application.cdx.json'
~~~

**Expected result:** an entry ending with:

~~~text
BOOT-INF/classes/META-INF/sbom/application.cdx.json
~~~

If you see an SBOM at target/bom.json but not inside the JAR, you generated a project SBOM without configuring the resource to be packaged into the executable archive. Those are two different goals.

### 5.6. Inspect Contents with jq

~~~bash
jq '{
  bomFormat,
  specVersion,
  serialNumber,
  application: .metadata.component,
  componentCount: (.components | length),
  dependencyEdges: (.dependencies | length)
}' target/classes/META-INF/sbom/application.cdx.json
~~~

Actual values depend on the dependency graph and plugin version. Never hard-code a component count or expected library list without inspecting the generated SBOM.

### 5.7. Run the Application and Confirm Runtime

~~~bash
java -jar target/sbom-demo-1.0.0.jar
~~~

In another terminal:

~~~bash
curl -fsS http://127.0.0.1:8080/api/status
~~~

**Exact HTTP response body:**

~~~text
SBOM_DEMO_OK
~~~

After checking, stop the application with Ctrl+C.

## 6. Retrieving the SBOM via Spring Boot Actuator

Spring Boot Actuator includes an sbom endpoint that reads SBOMs available on the classpath. Once the plugin packages CycloneDX into the executable JAR, Actuator can automatically detect the SBOM named application.

### 6.1. Listing SBOMs

While the application is running:

~~~bash
curl -i http://127.0.0.1:8080/actuator/sbom
~~~

Illustrative response:

~~~http
HTTP/1.1 200 OK
Content-Type: application/vnd.spring-boot.actuator.v3+json

{
  "ids": [
    "application"
  ]
}
~~~

### 6.2. Downloading the Application SBOM

~~~bash
curl -fsS http://127.0.0.1:8080/actuator/sbom/application \
  -o target/actuator-application.cdx.json
~~~

The response carries the CycloneDX JSON media type, typically:

~~~text
application/vnd.cyclonedx+json
~~~

You can inspect part of the content:

~~~bash
jq '{bomFormat, specVersion, application: .metadata.component}' \
  target/actuator-application.cdx.json
~~~

Actuator returns the resource built into the application; it does not resolve new dependencies or scan the container on every request.

### 6.3. Adding Additional SBOMs

Actuator can expose multiple SBOMs. For example, if an SPDX file exists at /system.spdx.json:

~~~properties
management.endpoint.sbom.additional.system.location=optional:file:/system.spdx.json
management.endpoint.sbom.additional.system.media-type=application/spdx+json
~~~

When the file exists and is configured properly, the endpoint can list the ID system. The optional: prefix lets the application start even if the file is absent. Manage the file location and read permissions carefully.

**Security note:** do not treat the SBOM endpoint as a public information API. Restrict access to operations/security teams or use a protected management network. If you only need to feed the SBOM to scanners, exporting the file in CI and storing it alongside the release artifact may be safer than exposing the endpoint in production.

## 7. Configuring CycloneDX Maven Plugin Without Spring Boot Parent

If your project does not inherit from spring-boot-starter-parent, or you want explicit control over output path/format, configure the plugin explicitly. The following example creates a JSON SBOM and places the resource in target/classes so the JAR packages it.

**This is a fragment** in the POM's build/plugins; the plugin version is pinned at 2.9.3 and schema at 1.6.

~~~xml
<plugin>
    <groupId>org.cyclonedx</groupId>
    <artifactId>cyclonedx-maven-plugin</artifactId>
    <version>2.9.3</version>
    <executions>
        <execution>
            <id>generate-application-sbom</id>
            <phase>prepare-package</phase>
            <goals>
                <goal>makeBom</goal>
            </goals>
            <configuration>
                <projectType>application</projectType>
                <schemaVersion>1.6</schemaVersion>
                <outputFormat>json</outputFormat>
                <outputName>application.cdx</outputName>
                <outputDirectory>${project.build.outputDirectory}/META-INF/sbom</outputDirectory>
                <includeCompileScope>true</includeCompileScope>
                <includeProvidedScope>true</includeProvidedScope>
                <includeRuntimeScope>true</includeRuntimeScope>
                <includeSystemScope>true</includeSystemScope>
                <includeTestScope>false</includeTestScope>
                <includeBomSerialNumber>true</includeBomSerialNumber>
            </configuration>
        </execution>
    </executions>
</plugin>
~~~

After mvn clean verify, expected output:

~~~text
target/classes/META-INF/sbom/application.cdx.json
~~~

### Parameter Explanation

- makeBom generates an SBOM for the current Maven module. It fits single-module projects or when you want a separate BOM per module.
- makeAggregateBom generates an aggregate BOM at the root for the entire Maven reactor and can also generate per-module BOMs.
- projectType=application describes the root component as an application rather than a library.
- schemaVersion=1.6 selects the schema supported by plugin 2.9.3.
- outputFormat=json generates JSON only; all can generate both XML and JSON.
- outputName=application.cdx produces the filename application.cdx.json.
- outputDirectory places the SBOM in resource output before the package phase so Maven JAR plugin includes it in the archive.
- includeTestScope=false excludes test-only dependencies, which is common practice for application SBOMs.
- includeProvidedScope and includeSystemScope should be evaluated based on how the application is deployed. If a dependency is provided by the runtime platform rather than packaged in the artifact, decide explicitly whether the BOM should describe it or only shipped packages.
- includeBomSerialNumber=true adds a document serial number.

**Caution when using Spring Boot starter parent:** the parent already configures CycloneDX to produce application.cdx.json in META-INF/sbom. If overriding the output path/goal, inspect mvn help:effective-pom and use a distinct execution ID when customizing. Otherwise, inherited configuration may surprise you by still writing output to Spring Boot's SBOM path.

### Inspecting Actual Maven Configuration

~~~bash
mvn help:effective-pom -Doutput=target/effective-pom.xml
mvn clean verify
~~~

Search for cyclonedx-maven-plugin and check its goal, execution, version, output format, output name, output directory, and dependency scopes. Never infer the effective configuration solely from a child POM snippet.

## 8. Multi-Module Maven: Choosing BOM Scope Across a Reactor

For a project:

~~~text
platform/
├── pom.xml
├── shared-core/
├── customer-api/
└── billing-service/
~~~

There are two needs:

- **One SBOM per module:** use makeBom. This gives each artifact its own inventory.
- **One consolidated SBOM across the reactor:** use makeAggregateBom. This is useful when releasing a system composed of multiple modules built together.

Example aggregate goal in plugin execution:

~~~xml
<execution>
    <id>aggregate-reactor-sbom</id>
    <phase>prepare-package</phase>
    <goals>
        <goal>makeAggregateBom</goal>
    </goals>
</execution>
~~~

With the Spring Boot parent, check whether the default configuration already defines an aggregate goal before adding a second execution.

Run the reactor:

~~~bash
mvn -pl billing-service -am clean verify
~~~

-am tells Maven to also build required upstream projects in the reactor. Running a module alone or relying on locally installed dependencies can alter the aggregate scope. Generate the SBOM using the **exact same build command, profiles, and reactor membership** as the release.

### Dependency Scopes and Profiles

The Maven plugin provides scope include/exclude options. Common plugin defaults cover compile, provided, runtime, and system, while excluding test scope. However, provided does not automatically mean a dependency is always inside an executable JAR. Some dependencies only exist in an application server environment or are supplied by the runtime platform.

A release SBOM should be generated with:

1. The same Maven profiles as the release pipeline.
2. Dependency versions resolved during the build.
3. Scope policies aligned with the artifact.
4. The exact modules belonging to the release.
5. Never a BOM from a local build using different profiles as production evidence.

Do not mechanically exclude test dependencies from all reporting: a separate SBOM for the build/test environment can be valuable for evaluating the build supply chain. Give the **runtime/application BOM** and **build/test BOM** distinct names and purposes.

## 9. Gradle: CycloneDX Plugin and Spring Boot Integration

With Gradle, Spring Boot 4.1 works with the CycloneDX Gradle Plugin. Groovy DSL example:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '4.1.2'
    id 'org.cyclonedx.bom' version '3.0.0'
}

group = 'dev.example'
version = '1.0.0'

repositories {
    mavenCentral()
}
~~~

When the CycloneDX plugin is applied, the Spring Boot plugin configures the cyclonedxBom task for application use, JSON output application.cdx.json, skipping XML and full license text embedding. Spring Boot also packages the SBOM into the JAR/WAR at META-INF/sbom and adds manifest headers Sbom-Format/Sbom-Location.

Run:

~~~bash
./gradlew cyclonedxBom bootJar
~~~

Inspect:

~~~bash
jar tf build/libs/sbom-demo-1.0.0.jar
~~~

The archive should contain the SBOM resource at META-INF/sbom on the application classpath. The manifest headers and SBOM path must match. If the Gradle plugin or Spring Boot version changes, inspect the actual task configuration and output path.

**Gradle differs from Maven:** do not copy Maven XML configuration into build.gradle. Check compatible Gradle plugin versions, which dependency configurations are included in the BOM, and ensure the task runs before bootJar packages the archive.

## 10. Generating an SBOM for a Container Image

An application SBOM does not fully describe every package inside the final image. If you package using a Dockerfile or Cloud Native Buildpacks, generate an **image-level SBOM** as well.

### 10.1. Using Syft to Scan an Image

Syft can catalog container images, directories, and archives, and export CycloneDX JSON:

~~~bash
syft sbom-demo:1.0.0 -o cyclonedx-json=target/image.cdx.json
~~~

For registry images, scan the exact immutable digest:

~~~bash
syft registry.example.com/team/sbom-demo@sha256:REPLACE_WITH_REAL_DIGEST \
  -o cyclonedx-json=target/image.cdx.json
~~~

The string REPLACE_WITH_REAL_DIGEST is only a placeholder in this illustrative command; replace it with the actual digest from the registry before running.

An image SBOM can include OS packages, the JRE, and Java packages recognized by the scanner. Detection coverage depends on each package's format/metadata. Never claim the scanner detected everything simply because the command exited with code 0.

### 10.2. Using Docker Scout

Another option if your organization uses Docker Scout:

~~~bash
docker scout sbom sbom-demo:1.0.0
~~~

This command generates/displays an SBOM for the image using Docker Scout. Verify permissions, CLI version, registry settings, and export formats per your organization's workflow.

### 10.3. Buildpacks/Paketo Has Its Own SBOMs

Paketo buildpacks can generate SBOMs in Syft JSON, SPDX JSON, and CycloneDX JSON formats when supported by the buildpacks. You can download an image's SBOM:

~~~bash
pack sbom download sbom-demo:1.0.0 --output-dir target/paketo-sbom
~~~

Find the JSON files:

~~~bash
find target/paketo-sbom -type f -name "*.json"
~~~

**Key point:** SBOMs downloaded via pack sbom download focus on **launch-time app dependencies**. If you also need build-time dependencies, collect SBOMs at build time using pack build with the --sbom-output-dir option:

~~~bash
pack build sbom-demo:1.0.0 \
  --path target/sbom-demo-1.0.0.jar \
  --builder paketobuildpacks/builder-noble-java-tiny \
  --sbom-output-dir target/cnb-build-sbom
~~~

The command above is an example using a Paketo builder; choose a builder matching your Java version, architecture, and policy. Different buildpacks may support different SBOM formats. Check buildpack.toml and builder metadata for actual format support.

**Do not confuse the three file types:** a Maven CycloneDX SBOM describes the dependency model; a Paketo SBOM describes what buildpacks contributed; a Syft image SBOM catalogs the final image. They complement each other but are not automatically equivalent.

## 11. Validating the SBOM Before Passing It to Scanners

A syntactically valid JSON file is not necessarily a schema-valid CycloneDX BOM. Always check both format and schema version.

### 11.1. Validating with CycloneDX CLI

With plugin 2.9.3 and schema 1.6:

~~~bash
cyclonedx validate \
  --input-file target/classes/META-INF/sbom/application.cdx.json \
  --input-version v1_6 \
  --fail-on-errors
~~~

A successful run typically prints:

~~~text
BOM validated successfully.
~~~

If validating an image SBOM:

~~~bash
cyclonedx validate \
  --input-file target/image.cdx.json \
  --input-version v1_6 \
  --fail-on-errors
~~~

Pass the input-version matching the specVersion inside the file itself. If your scanner/validator supports a newer schema, upgrade the plugin and schema in lockstep.

### 11.2. Checking Core Fields

~~~bash
jq '{
  format: .bomFormat,
  spec: .specVersion,
  subject: .metadata.component,
  components: (.components | length),
  dependencyNodes: (.dependencies | length)
}' target/classes/META-INF/sbom/application.cdx.json
~~~

Manual checks:

- bomFormat is CycloneDX.
- specVersion matches the selected version.
- metadata.component accurately describes the application and version.
- components contains the expected dependencies.
- dependencies reflects package relationships when the plugin has data.
- PURLs/versions are not empty or anomalously malformed.
- Licenses/hashes are present where supplied by data sources.
- No duplicate component references or broken dependency edges.

### 11.3. Reconciling Against Maven Dependency Tree

~~~bash
mvn dependency:tree -Dscope=runtime
~~~

Compare the dependency tree with the SBOM to spot missing or extra entries. However, the two tools have different purposes and representations; compare by package coordinates/version and scope rather than raw component counts alone.

**Do not use component count as the sole criterion.** A BOM with 100 components is not automatically more complete than one with 90. A BOM stuffed with test/build dependencies may be less suitable for a runtime release than a properly scoped BOM.

## 12. Scanning Vulnerabilities from an SBOM

An SBOM serves as an input to a scanner. Example using Grype:

~~~bash
grype sbom:target/image.cdx.json
~~~

Or scan the image directly:

~~~bash
grype sbom-demo:1.0.0
~~~

Grype can read CycloneDX, SPDX, and Syft formats. In CI, manage the vulnerability database, update schedule, and severity policies.

### Reading Scan Results

When findings appear, verify:

1. Package URL/PURL, ecosystem, name, and version.
2. Whether the CVE/advisory applies to the exact version and build.
3. Whether a patch or supported alternative version is available.
4. Whether the vulnerability is in an application dependency, JRE, or OS package.
5. Whether an approved VEX/exception exists.
6. Whether you can rebuild/rebase/upgrade and regression-test within policy timelines.

**A scan is not an absolute proof.** Zero findings can result from a stale database, an unrecognized package, an unpublished CVE, or missing ecosystem support in the scanner. Any finding likewise needs scope and applicability verification before drawing conclusions.

## 13. How Should the Application SBOM and Image SBOM Be Linked?

A release can store a structure such as:

~~~text
release/
├── sbom/
│   ├── application.cdx.json
│   └── image.cdx.json
├── scan/
│   └── grype-report.json
└── provenance/
    └── build-attestation.json
~~~

These files should be linked with:

- Source commit SHA.
- Maven/Gradle version and JDK toolchain.
- Application version and JAR checksum.
- Container image reference and **actual digest**.
- Builder/run image or Docker base image digest.
- SBOM schema version and generator version.
- Scan database version/timestamp, policy result, and approved exceptions.

Example release metadata:

~~~text
application = sbom-demo:1.0.0
source.commit = <full Git SHA>
jar.sha256 = <calculated JAR digest>
image.reference = registry.example.com/team/sbom-demo:1.0.0
image.digest = sha256:<actual registry digest>
application.sbom = application.cdx.json
image.sbom = image.cdx.json
scan.policy = <approved policy result>
~~~

This is an **illustrative data template**, not real digests or attestations. Never bind an SBOM solely to a mutable tag such as latest. If an image tag is pushed again, its digest can change, and the old SBOM will no longer reliably describe the current bytes.

### Signing and Storing SBOMs

CycloneDX CLI supports signing/verification for BOMs; supply-chain attestation systems can also bind SBOMs to artifact digests. Select a signing mechanism per your key management policy. Store public verification keys, signing identities, provenance, and generation timestamps alongside release metadata.

Never treat an SBOM signature as proof that packages are vulnerability-free. A signature proves the document was signed by an identity and not modified after signing; its contents must still be inspected.

## 14. Recommended CI/CD Pipeline

A minimal pipeline can follow this sequence:

~~~text
Checkout commit
     |
Resolve dependencies with locked versions
     |
Compile + unit tests
     |
Generate CycloneDX application SBOM
     |
Package executable JAR (embed META-INF/sbom)
     |
Validate SBOM schema + inspect package scope
     |
Build OCI image
     |
Generate/collect image SBOM
     |
Vulnerability + license policy checks
     |
Publish image by digest + attach SBOM/provenance
     |
Deploy approved digest
~~~

| Gate | PASS condition | On FAIL |
| --- | --- | --- |
| **Generation** | SBOM file generated and non-empty | Stop release; check plugin/task |
| **Identity** | Name/version matches artifact | Fix build metadata and regenerate |
| **Schema** | Validator passes for selected schema | Check format/schema/plugin compatibility |
| **Completeness** | Direct/transitive dependencies match expected scope | Reconcile dependency tree/profiles |
| **Packaging** | SBOM embedded in JAR if required by policy | Fix outputDirectory/lifecycle ordering |
| **Image inventory** | Image SBOM linked to exact image digest | Rescan built/pushed image |
| **Vulnerability** | No severity/exception policy violations | Patch, mitigate, or obtain approved exception |
| **License** | License policy satisfied or formally decided | Legal/security review |
| **Provenance** | SBOM linked to exact commit/JAR/image digest | Regenerate/re-attest exact artifact |
| **Publication** | SBOM and scan reports stored with release | Block deployment when required evidence is missing |

Example commands in a Maven pipeline:

~~~bash
mvn -B -ntp clean verify
cyclonedx validate --input-file target/classes/META-INF/sbom/application.cdx.json --input-version v1_6 --fail-on-errors
jar tf target/sbom-demo-1.0.0.jar
syft sbom-demo:1.0.0 -o cyclonedx-json=target/image.cdx.json
grype sbom:target/image.cdx.json
~~~

These are sample commands; CI must handle exit codes, registry login, image digests, and artifact uploads according to the specific platform. If building with Buildpacks, use the builder's SBOM collection mechanism or scan the final image.

## 15. Limitations and Considerations

### 15.1. Dependency Graph Does Not Imply Runtime Reachability

A Maven SBOM lists dependencies resolved during the build. It does not confirm every class/method is loaded or invoked in production. Do not exclude a component solely because it “does not appear used” without proper evidence and policy.

### 15.2. Dynamically Loaded Dependencies

Some applications load plugins, scripts, extensions, or binaries at runtime. Such components may not appear in the Maven dependency graph or the image at build time. Inventory them separately via artifact repositories, runtime configurations, or image/host scans.

### 15.3. Maven Scopes and Profiles

If CI builds with different profiles than local machines, the dependency graph can change. Generate the SBOM from the exact same profiles, dependency locks, and reactor as the release. Review provided, system, test, and optional dependencies as well as module exclusions.

### 15.4. Image SBOMs Must Scan the Exact Image

If an SBOM is generated from a tag before pushing the image and the tag is later overwritten, the file may describe an older image. Scan the image after building/pushing and tie the results to the resolved digest.

### 15.5. An SBOM Does Not Replace a Vulnerability Scanner

CycloneDX describes package inventory and metadata. Finding CVEs requires a scanner paired with a vulnerability database. Determining exploitability requires context, VEX, and application analysis. Proving build origin requires provenance/attestations.

### 15.6. SBOMs Can Contain Sensitive System Information

Internal library names, versions, modules, repository URLs, and dependency relationships can be sensitive data. Review external references and custom properties before sharing outside the organization. Never add tokens, credentials, or secrets to an SBOM.

## 16. Common Issues and How to Handle Them

| Symptom | Common cause | Check/Resolution |
| --- | --- | --- |
| Missing target/classes/META-INF/sbom | CycloneDX plugin not enabled or goal did not run | Check parent POM, plugin declaration, effective POM |
| target/bom.json exists but JAR lacks SBOM | Output is not inside resource output before package | Set output to project.build.outputDirectory/META-INF/sbom or use Boot parent config |
| /actuator/sbom returns 404 | Actuator not added, endpoint not exposed, or SBOM not embedded | Check dependency, properties, JAR entries |
| /actuator/sbom/application errors | Wrong resource path or format metadata | Check file inside JAR and media type |
| Maven only generates BOM for one module | Used makeBom instead of aggregate | Use makeAggregateBom for reactor when needed |
| Aggregate misses a module | Module excluded from current reactor/profile or explicitly excluded | Check Maven reactor, profiles, and exclusion config |
| SBOM contains test libraries | Test scope enabled or config overridden | Set includeTestScope=false for runtime BOM |
| SBOM lists a package absent from the JAR | provided/system scope or overly broad scope policy | Check scopes and compare with packaged archive |
| Component missing license | Repository metadata lacks license info | Check package source and review; never guess licenses |
| Plugin reports unsupported schema | Plugin version is older than requested schema | Select a compatible plugin/schema pair |
| Validator reports wrong specVersion | Passed input-version does not match file | Read specVersion and choose the matching version |
| Image SBOM missing JRE/OS packages | Using project SBOM instead of image SBOM | Scan the final OCI image with Syft/Docker Scout |
| Paketo SBOM missing build tools | Only downloaded launch-time SBOM | Collect build-time SBOM when running pack build |
| Grype returns no results | Empty/malformed SBOM or stale database | Validate file, check DB/network, and scanner logs |
| SBOM differs between local and CI | Different profiles, dependency resolution, plugin versions, or sources | Compare commit, effective POM, dependency tree, and toolchain |
| Maven config ignores outputName | Plugin execution merged from Spring Boot parent | Inspect effective POM; use a distinct execution ID for custom goals |
| SBOM does not match image digest | Image changed after SBOM generation | Rescan the exact released digest |
| Public SBOM exposes internal dependencies | Unprotected endpoint/file | Restrict Actuator, registry, and artifact permissions |
| Build succeeds but SBOM not uploaded | Pipeline lacks artifact publishing step | Add upload/retention gate and check exit status |

**Investigation order:** did the goal/plugin run → was the file generated → are contents/schema valid → was it embedded in the JAR → was the image scanned → is the SBOM bound to the right digest → can scanners/policies read it.

## 17. Self-Check Exercises

**1. What is an SBOM?**

Answer: A structured inventory of software components and their relationships in a product or artifact. It supports traceability, vulnerability management, and license reviews.

**2. Where does CycloneDX Maven Plugin generate its SBOM from?**

Answer: From the Maven project/dependency model and resolved dependencies. It does not automatically scan all OS packages inside a container.

**3. What is the difference between makeBom and makeAggregateBom?**

Answer: makeBom generates a BOM for the current module; makeAggregateBom generates an aggregate BOM at the root for the Maven reactor and can also produce per-module BOMs.

**4. Why does Spring Boot package the SBOM inside META-INF/sbom?**

Answer: So the resource travels with the executable archive, enabling Actuator and metadata-reading tools to locate the SBOM attached to the application artifact.

**5. How do /actuator/sbom and /actuator/sbom/application differ?**

Answer: The first endpoint lists available SBOM IDs; the second returns the contents of a specific SBOM.

**6. Why must the SBOM endpoint be protected?**

Answer: It can reveal dependency names/versions and internal component structure. Access should be restricted to security/operations teams.

**7. Why is an image SBOM needed if you already have a Maven SBOM?**

Answer: A Maven SBOM focuses on the application's dependency graph; an image SBOM can additionally detect the JRE, OS packages, and components packaged into the final image.

**8. Does Paketo's pack sbom download include build-time dependencies?**

Answer: SBOMs downloaded this way focus on launch-time dependencies. Build-time SBOMs must be collected during the build with the appropriate output option.

**9. Is an SBOM a vulnerability report?**

Answer: No. An SBOM is an inventory; scanners like Grype match packages against vulnerability databases to produce findings.

**10. Why must an SBOM be linked to an image digest?**

Answer: Tags can change. A digest uniquely identifies the exact image contents described by the SBOM and scan report.

**11. If the plugin finds no license for a component, can you fill in MIT yourself?**

Answer: No. You must inspect license metadata/sources and mark the status as undetermined until evidence is found.

**12. Can you build a single SBOM covering application, build tools, base image, and runtime host?**

Answer: You can compose a system-level inventory using appropriate tools/methods, but you must preserve the clear origin and scope of each underlying inventory. A combined BOM must never erase which components came from the app, OS, builder, or host.

## 18. Checklist for Production Projects

- [ ] Determine whether the SBOM describes a source project, executable JAR, or container image.
- [ ] Choose a CycloneDX/SPDX schema supported by your registry, scanners, and consumers.
- [ ] Pin plugin and schema versions; avoid arbitrary snapshots.
- [ ] Maven: choose makeBom or makeAggregateBom matching your scope.
- [ ] Gradle: configure CycloneDX plugin and verify the cyclonedxBom task.
- [ ] Align profiles, scopes, dependency locks, and reactor with releases.
- [ ] Inspect component metadata, versions, PURLs, dependency graphs, licenses, and hashes.
- [ ] Validate the SBOM against the exact schema.
- [ ] Verify the SBOM is packaged into the JAR if Actuator integration is needed.
- [ ] Restrict access to /actuator/sbom via security/network policies.
- [ ] Generate an image SBOM for the final image, including OS/JRE packages where supported.
- [ ] Collect build-time SBOMs if required by policy.
- [ ] Scan SBOMs/images with an up-to-date vulnerability database.
- [ ] Review license and CVE exceptions through an approved process.
- [ ] Link SBOMs/scan reports to commit, JAR checksum, and image digest.
- [ ] Sign/attest artifacts and SBOMs when required by release policy.
- [ ] Store SBOMs alongside release artifacts with retention and access control.
- [ ] Assign an owner to maintain plugin, scanner, builder, and base image updates.

**Conclusion:** CycloneDX Maven/Gradle Plugin is well-suited for creating an **application dependency SBOM** from the build model. Spring Boot can embed that SBOM in the executable JAR and expose it via Actuator. Syft, Docker Scout, and Buildpacks SBOMs complement it at the **container image level**. To make SBOMs operationally valuable, validate schemas, verify scopes, scan for vulnerabilities, protect sensitive data, and link each SBOM to its exact source, artifact, and image digest.

## 19. Official References

1. [Spring Boot 4.1 — Generate a CycloneDX SBOM](https://docs.spring.io/spring-boot/how-to/build.html)
2. [Spring Boot 4.1 — Actuator SBOM Endpoint](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html)
3. [CycloneDX Maven Plugin — Usage and Defaults](https://cyclonedx.github.io/cyclonedx-maven-plugin/)
4. [CycloneDX Maven Plugin — makeBom Goal](https://cyclonedx.github.io/cyclonedx-maven-plugin/makeBom-mojo.html)
5. [CycloneDX Maven Plugin — makeAggregateBom Goal](https://cyclonedx.github.io/cyclonedx-maven-plugin/makeAggregateBom-mojo.html)
6. [CycloneDX Maven Plugin — Releases](https://github.com/CycloneDX/cyclonedx-maven-plugin/releases)
7. [CycloneDX Specification Overview](https://cyclonedx.org/specification/overview/)
8. [CycloneDX CLI — Validate, Diff, Merge and Sign](https://github.com/CycloneDX/cyclonedx-cli)
9. [Paketo — How to Access an SBOM](https://paketo.io/docs/howto/sbom/)
10. [Paketo — SBOM Concepts and Formats](https://paketo.io/docs/concepts/sbom/)
11. [Anchore Syft — Generate SBOMs from Images and Filesystems](https://github.com/anchore/syft)
12. [Anchore Grype — Scan an SBOM](https://oss.anchore.com/docs/guides/vulnerability/scan-targets/)
13. [Docker Scout — Generate or Display an Image SBOM](https://docs.docker.com/reference/cli/docker/scout/sbom/)
14. [Spring Boot — System Requirements](https://docs.spring.io/spring-boot/system-requirements.html)