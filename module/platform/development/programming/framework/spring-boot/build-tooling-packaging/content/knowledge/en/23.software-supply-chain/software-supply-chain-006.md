# Checking Licenses and Redistributable Components in Spring Boot Applications

## 1. Objective: Knowing Exactly What Is Being Released

A Spring Boot application can build cleanly and run properly yet still not be cleared for release. An executable JAR typically contains many direct and transitive libraries; a container image also contains a JRE, operating system, and base packages. A project may also distribute fonts, icons, images, JavaScript, native libraries, scripts, documentation, and source code copied from elsewhere. Each component may carry its own licensing terms and distribution obligations.

A **license review** must be able to answer:

- Which components actually appear in the release?
- Who is the owner or licensor? What is the version and where was it obtained?
- Which terms apply to that specific component/file?
- Does the project have the right to use, modify, package, redistribute, or ship the component through the intended channel?
- Is it required to retain copyright/license text, NOTICE files, attribution, provide source code, or fulfill other obligations?
- Are there any components with unknown licenses, missing evidence, prohibited by policy, or governed by commercial contracts that require review?

This lesson belongs to the **Supply Chain** section of **Spring Boot Build Tooling Packaging**. After this lesson, you will be able to:

1. Inventory source code, direct/transitive Maven dependencies, and files actually packaged.
2. Distinguish license metadata in a POM from actual license texts and legal terms.
3. Use SPDX identifiers/expressions to represent a single license, multi-license choices, and exceptions.
4. Configure License Maven Plugin to generate `THIRD-PARTY.txt`, detect missing metadata, and enforce allowlist/denylist policies.
5. Generate a CycloneDX SBOM from the Maven dependency graph and understand what the SBOM does not yet cover.
6. Use Maven Enforcer to block forbidden artifact coordinates per policy.
7. Build a Java 17/Spring Boot executable JAR containing the project LICENSE and third-party notices, then inspect archive entries using a standalone Java program.
8. Extend inventorying to Docker base images, OS packages, fonts, icons, native libraries, and frontend assets.
9. Organize CI gates, evidence, approvals, and release the exact reviewed artifact.

**Illustrative example:** Java `17`, Spring Boot `3.5.16`, Maven, `license-maven-plugin 2.7.1`, and `cyclonedx-maven-plugin 2.9.3`. The fictional demo project chooses Apache License 2.0 solely to illustrate metadata. Do not infer this as the license of any real project; when applying this in practice, replace it with your project's actual licensing decision and rights record.

## 2. “Permitted for Distribution” Depends on Component and Distribution Channel

A component may be permitted for internal use yet carry different conditions when shipped in a public binary, container image, SDK, source bundle, OEM product, or hosted service. Never use a single `license` column to answer every scenario.

| Distribution channel | Components to inspect |
| --- | --- |
| Executable JAR | Application classes/resources, all nested dependency JARs, license/NOTICE files, native resources |
| WAR | Application classes, `WEB-INF/lib`, `WEB-INF/lib-provided`, JSP/taglibs, servlet/container dependencies per deployment model |
| Source archive | Source code, copied snippets, generated sources, vendored files, tests, docs, examples, and build scripts |
| Docker/OCI image | JAR, JRE, base OS, OS packages, CA certificates, fonts, native libraries, startup scripts, and image metadata |
| SDK/library | Main JAR, distributed transitive dependencies, source/Javadoc, examples, and API docs |
| Marketplace/OEM distribution | All components transferred to customers along with vendor terms, sublicensing, and redistribution rights |
| SaaS/hosted service | Source/runtime components, network-use clauses, and license-specific obligations; do not assume identical to binary redistribution |

Downloading a Maven dependency from Maven Central **does not automatically mean** your organization has the right to redistribute it in every product. Similarly, a dependency whose POM declares `Apache-2.0` is not sufficient proof that the downloaded JAR is genuinely the release licensed under those terms; verify the source, version, artifact integrity, and license text.

**Distinguish three decisions:**

1. **Technical inventory:** which components are built, bundled, or shipped?
2. **License evidence:** which license applies, and is there text/notice/source evidence?
3. **Distribution approval:** do the terms fit the specific product, integration method, and distribution channel?

Build tools assist with part 1 and gather evidence for part 2. Approval in part 3 requires organizational policy and qualified reviewers evaluating the terms. No single Maven flag makes legal determinations for all cases.

## 3. Scoping Components in Maven/Spring Boot

### 3.1. The Dependency Tree and Final Artifact Are Not Identical Lists

Maven manages dependencies by coordinates, version, transitivity, and scope. A project can have:

- Direct dependencies declared in `<dependencies>`.
- Transitive dependencies pulled in through other libraries.
- Optional dependencies.
- Provided dependencies supplied by the container/runtime.
- Test-only dependencies.
- System-scoped JARs loaded from a local path.
- Maven plugins and plugin dependencies used only during the build.

First command:

~~~bash
mvn dependency:tree
~~~

Export the dependency tree to a file for review:

~~~bash
mvn dependency:tree -DoutputFile=target/dependency-tree.txt
mvn dependency:tree -Dscope=runtime -DoutputFile=target/runtime-dependencies.txt
~~~

`dependency:tree` displays the tree resolved by Maven, including direct and transitive dependencies. Running with scope `runtime` shows components serving runtime per the Maven classpath. **Do not rely solely on the runtime command to conclude what the executable Spring Boot JAR packaged**, because Boot's repackage has its own rules.

### 3.2. Maven Scopes

| Scope | Maven meaning | Handling in license review |
| --- | --- | --- |
| `compile` | On compile, test, and runtime classpaths; default if omitted | Usually shipped in the executable JAR |
| `runtime` | Not needed to compile, needed at runtime | Usually shipped in the executable JAR |
| `provided` | Available for compile/test; expected from runtime/container | Check carefully: Spring Boot repackage still includes provided dependencies in the executable JAR by default |
| `test` | Only for test compile/run | Usually absent from executable JAR; review separately if shipping source/test bundles or build environments |
| `system` | Taken from a local file specified by `systemPath` | Hard to reproduce and trace; verify binary, source, and distribution rights separately |
| `import` | Imports dependency management from a BOM inside `<dependencyManagement>` | Not a standalone runtime dependency; inspect actual managed dependencies |

An easily overlooked detail: Spring Boot Maven Plugin `repackage` includes `provided` dependencies in the executable JAR by default; optional and system-scoped dependencies have separate include settings. Therefore, never infer package contents solely from standard Maven runtime classpath rules. Inspect the effective plugin configuration and the **actual JAR**.

In this lesson's example POM, the executable JAR inventory aligns with Boot's configuration:

- License Maven Plugin: `includedScopes=compile,provided,runtime`, `includeOptional=false`, `includeTransitiveDependencies=true`.
- Spring Boot repackage: includes provided dependencies by default; optional/system can be configured differently.
- CycloneDX: compile/provided/runtime enabled; test/system disabled in the example.

If you change `includeOptional`, `includeSystemScope`, or exclude rules on the Boot plugin, update the license report/BOM scopes and re-verify the final archive.

### 3.3. What the Dependency Tree Cannot See

`mvn dependency:tree` does not automatically inventory everything:

- JARs copied manually into resource folders or shaded/embedded by custom plugins.
- JavaScript/CSS/fonts/icons/images downloaded or vendored into the repository.
- Native `.so`, `.dll`, `.dylib`, CLI binaries, and data files.
- Source snippets, generated code, schemas, documentation, and sample datasets.
- OS packages and the JRE inside Docker base images.
- Maven plugins, plugin dependencies, and CI build images if not distributed with the app.

Therefore, the final inventory must reconcile **the dependency graph against the contents of the shipped product** and audit non-Maven component sources.

## 4. License Metadata, License Texts, and Evidence

A dependency POM may declare:

~~~xml
<licenses>
    <license>
        <name>Apache License, Version 2.0</name>
        <url>https://www.apache.org/licenses/LICENSE-2.0</url>
        <distribution>repo</distribution>
    </license>
</licenses>
~~~

This is metadata authored by the publisher in the POM. It is useful for collection and reporting, but it does not contain the full terms and does not guarantee the publisher declared it accurately. Cross-check:

1. The license file in the source release or official repository.
2. Copyright headers, NOTICE, and attribution files of the component.
3. POM/metadata for the **exact resolved artifact version**.
4. Release page, upstream repository, and hashes/signatures if available.
5. Files actually placed into the product and any modifications made.

Never lump every dependency under “Apache” just because most Spring Boot projects use Apache 2.0. A dependency may carry a different license, dual license, exception, or incomplete metadata.

### 4.1. POM Licenses Only Describe the Current Project

The `<licenses>` block in a POM describes the license of the **project publishing that POM**. It does not alter the licenses of Spring, Tomcat, Jackson, or transitive dependencies.

If the demo project is licensed under Apache-2.0, it should contain:

~~~text
LICENSE
src/main/resources/META-INF/LICENSE
src/main/resources/META-INF/NOTICE   (if the project has a NOTICE to distribute)
~~~

`LICENSE` at the repository root informs readers of the source project's license. The copy under `src/main/resources/META-INF/LICENSE` gets packaged into the executable JAR. If the license requires keeping NOTICE files or an upstream component supplies a NOTICE that must be passed along, include the required notices in the distribution per applicable terms.

Never fabricate a LICENSE file just to make a build pass. Its content must reflect the actual license chosen and applied by the organization.

## 5. SPDX Identifiers and Expressions

SPDX maintains a standard list of identifiers to represent licenses and exceptions. Examples:

| SPDX ID | Name |
| --- | --- |
| `Apache-2.0` | Apache License 2.0 |
| `MIT` | MIT License |
| `BSD-2-Clause` | BSD 2-Clause License |
| `BSD-3-Clause` | BSD 3-Clause License |
| `MPL-2.0` | Mozilla Public License 2.0 |
| `GPL-3.0-only` | GNU General Public License v3.0 only |
| `GPL-3.0-or-later` | GNU General Public License v3.0 or later |
| `LGPL-2.1-only` | GNU Lesser General Public License v2.1 only |

The SPDX License List also includes exceptions. Never invent an identifier that looks close to a license name and treat it as a valid SPDX ID; look up the exact list and version.

### 5.1. OR, AND, and WITH Have Distinct Meanings

SPDX license expressions allow describing scenarios more complex than a single license:

| Expression | General meaning |
| --- | --- |
| `Apache-2.0` | A single applicable license |
| `MIT OR Apache-2.0` | Choice between two licenses; determine your choice and satisfy the chosen license's terms |
| `Apache-2.0 AND MIT` | Must comply with both licenses |
| `GPL-2.0-or-later WITH Bison-exception-2.2` | GPL with a specific exception attached via the WITH operator |
| `LicenseRef-Internal-Asset-License` | Custom/non-standard license without an SPDX ID, defined and accompanied by evidence in the SPDX document |

**OR does not mean** you can automatically pick whichever license feels easiest without reading its terms. **AND does not mean** two interchangeable alternatives. **WITH** specifies an exception; an exception is not a standalone license.

Two special values must also be distinguished:

- `NONE`: indicates no license applies as declared.
- `NOASSERTION`: no determination has been made regarding the license.

`NOASSERTION` does not mean “approved.” If a component's license is undetermined, its release status should remain **review required** until evidence is obtained.

Example header in source code when the project genuinely applies Apache-2.0:

~~~java
/*
 * SPDX-License-Identifier: Apache-2.0
 */
package demo;
~~~

An SPDX header records a file/source license per policy; it does not replace LICENSE files, NOTICE files, attribution, or other distribution obligations.

## 6. License Maven Plugin: Creating a Third-Party Inventory

`org.codehaus.mojo:license-maven-plugin` supports:

- Generating `THIRD-PARTY.txt` listing dependencies and license metadata.
- Downloading license files from URLs in dependency POMs.
- Reporting dependencies missing license metadata.
- Using verified missing-file/override metadata.
- Applying included/excluded license names to fail builds per policy.
- Checking project license headers and license files.

The plugin version used in this example is `2.7.1`. The `license:add-third-party` goal generates a dependencies report; depending on configuration, it can add the output directory as a resource so the notice file is packaged into the artifact. Because it reads license names/URLs from POMs and supports missing-metadata overrides, **never treat its output as an automated legal conclusion**.

### 6.1. Configuring Generation of THIRD-PARTY.txt

The following fragment is used in the POM in Section 10:

~~~xml
<plugin>
    <groupId>org.codehaus.mojo</groupId>
    <artifactId>license-maven-plugin</artifactId>
    <version>2.7.1</version>
    <executions>
        <execution>
            <id>third-party-notices</id>
            <phase>generate-resources</phase>
            <goals>
                <goal>add-third-party</goal>
            </goals>
            <configuration>
                <includeTransitiveDependencies>true</includeTransitiveDependencies>
                <includeOptional>false</includeOptional>
                <includedScopes>compile,provided,runtime</includedScopes>
                <useMissingFile>true</useMissingFile>
                <missingFile>${project.basedir}/src/license/THIRD-PARTY.properties</missingFile>
                <failOnMissing>true</failOnMissing>
                <generateBundle>true</generateBundle>
                <bundleThirdPartyPath>META-INF/THIRD-PARTY.txt</bundleThirdPartyPath>
                <addOutputDirectoryAsResourceDir>true</addOutputDirectoryAsResourceDir>
                <encoding>UTF-8</encoding>
            </configuration>
        </execution>
    </executions>
</plugin>
~~~

Explanation:

- `add-third-party` collects dependencies from the Maven project and produces a third-party license list.
- `includeTransitiveDependencies=true` ensures transitive dependencies are scanned as well.
- `includedScopes` in the example matches the scopes used for the executable JAR: compile, provided, runtime.
- `includeOptional=false` matches Boot repackage's default of excluding optional dependencies; if the project enables includeOptional, update the inventory accordingly.
- `useMissingFile=true` allows supplying manually verified metadata when a dependency POM lacks a license.
- `failOnMissing=true` fails the build if unresolved license metadata remains.
- `generateBundle=true` places a notice copy at resource path `META-INF/THIRD-PARTY.txt`.
- `addOutputDirectoryAsResourceDir=true` causes the generated resource to be packaged; always verify the final archive as well.

By default, the license plugin processes a broader dependency graph than just direct dependencies. Scope/optional filters must align with **what is actually distributed**. If packaging changes, adjust and reconcile against the final file.

### 6.2. Initial Discovery of Dependencies Missing Licenses

Never guess a library's license from its artifact name. During initial discovery, you can temporarily allow reporting missing metadata to generate a to-do list:

~~~bash
mvn license:add-third-party \
  -Dlicense.useMissingFile=true \
  -Dlicense.failOnMissing=false
~~~

The plugin can create or update the file:

~~~text
src/license/THIRD-PARTY.properties
~~~

Example line **illustrating format**:

~~~properties
com.example.vendor--legacy-component--1.2.3=Apache License, Version 2.0
~~~

The key fields are `groupId--artifactId--version`. License values may only be filled in after a reviewer confirms the exact version, source release, and license text of the component. Never use the sample above as a default license for any arbitrary artifact.

After resolving all entries:

1. Record the evidence source and rationale for each override.
2. Inspect the license name/URL in the dependency POM; if wrong, check the upstream release and apply a governed override mechanism.
3. Re-run with `failOnMissing=true`.
4. Review the contents of `THIRD-PARTY.txt` and the final archive.

A dependency with license metadata that is inaccurate can still make a report look “clean.” Therefore, review both **unknown/missing** and **incorrect declarations**.

### 6.3. Downloading License Files

You can run the goal:

~~~bash
mvn license:download-licenses
~~~

By default, the plugin downloads license files into `target/licenses` from URLs declared in dependency POMs. URLs may be missing, broken, or point to documents other than the exact license text; every downloaded file must be reviewed.

`THIRD-PARTY.txt` is an **informational list of dependencies and license names**, not a complete bundle of every license text. If terms require distributing license texts/copyright notices, include the required files in the package—for example under `META-INF/third-party/`—in a project-controlled manner. Do not assume the download goal automatically fulfills all obligations.

## 7. Enforcing Policy Allowlists/Denylists

License Maven Plugin supports `includedLicenses`, `excludedLicenses`, and `failOnBlacklist`. When `failOnBlacklist=true`:

- Licenses outside the `includedLicenses` allowlist can fail the build.
- Licenses listed in `excludedLicenses` fail the build.
- Matched values are **license names** read from dependency POMs/metadata, which are not always SPDX identifiers.

Example policy fragment:

~~~xml
<configuration>
    <includedLicenses>
        <includedLicense>The Apache Software License, Version 2.0</includedLicense>
        <includedLicense>Apache License, Version 2.0</includedLicense>
        <includedLicense>MIT License</includedLicense>
        <includedLicense>BSD 3-Clause License</includedLicense>
    </includedLicenses>
    <excludedLicenses>
        <excludedLicense>Example Restricted License</excludedLicense>
    </excludedLicenses>
    <failOnBlacklist>true</failOnBlacklist>
</configuration>
~~~

This is an **illustrative allowlist**, not a universal recommendation for every company. POMs may use varying names for the same license, declare dual licenses, or omit complete metadata. Before enabling enforcement, generate a report and normalize names under a verified, approved policy.

Do not treat `OSI Approved` as the sole criterion for permitting distribution. An OSI-approved license can still conflict with a specific product, linking model, business model, or distribution obligation.

### 7.1. Maven Enforcer Blocking Components by Coordinates

Maven Enforcer `bannedDependencies` can fail a build if dependency coordinates match a forbidden pattern:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-enforcer-plugin</artifactId>
    <version>3.6.3</version>
    <executions>
        <execution>
            <id>block-unapproved-component</id>
            <goals>
                <goal>enforce</goal>
            </goals>
            <configuration>
                <rules>
                    <bannedDependencies>
                        <searchTransitive>true</searchTransitive>
                        <excludes>
                            <exclude>com.example.policy:blocked-component</exclude>
                        </excludes>
                    </bannedDependencies>
                </rules>
                <fail>true</fail>
            </configuration>
        </execution>
    </executions>
</plugin>
~~~

`com.example.policy:blocked-component` is a fictional coordinate for illustration; replace it with artifacts actually prohibited by policy. This rule checks direct/transitive dependency coordinates by pattern. It **does not read license texts or determine license compatibility**. Use Enforcer for explicit component blacklists; use inventory/license reviews to evaluate distribution rights.

## 8. CycloneDX SBOM: Capturing Components and License Metadata

An SBOM (*Software Bill of Materials*) is a list of components in a product, along with identifiers/versions and available metadata such as licenses, hashes, suppliers, and dependency relationships. It supports security, license review, incident response, and supply-chain traceability.

`CycloneDX Maven Plugin` generates a BOM from the Maven dependency graph:

- `makeBom` creates a BOM for each Maven module.
- `makeAggregateBom` creates a consolidated BOM for a multi-module reactor.
- `makePackageBom` supports WAR/EAR packaging modules.
- BOMs are typically produced as XML/JSON and can be attached with classifier `cyclonedx` during install/deploy.

In the example, version `2.9.3` supports CycloneDX schema `1.6`. Configuration:

~~~xml
<plugin>
    <groupId>org.cyclonedx</groupId>
    <artifactId>cyclonedx-maven-plugin</artifactId>
    <version>2.9.3</version>
    <executions>
        <execution>
            <id>create-application-bom</id>
            <phase>package</phase>
            <goals>
                <goal>makeBom</goal>
            </goals>
        </execution>
    </executions>
    <configuration>
        <projectType>application</projectType>
        <schemaVersion>1.6</schemaVersion>
        <includeCompileScope>true</includeCompileScope>
        <includeProvidedScope>true</includeProvidedScope>
        <includeRuntimeScope>true</includeRuntimeScope>
        <includeSystemScope>false</includeSystemScope>
        <includeTestScope>false</includeTestScope>
        <outputFormat>all</outputFormat>
        <outputName>bom</outputName>
    </configuration>
</plugin>
~~~

With `outputName=bom` and `outputFormat=all`, outputs typically include:

~~~text
target/bom.json
target/bom.xml
~~~

Both BOMs are **separate documents** generated from project dependencies; they do not automatically appear inside the executable JAR. The plugin can attach them under the `cyclonedx` classifier during Maven install/deploy.

### 8.1. An SBOM Is Not Distribution Approval

A BOM can record license metadata declared by dependency publishers. It does not prove that metadata is accurate, does not interpret all legal terms, does not decide whether an integration method triggers extra obligations, and does not replace inspecting LICENSE/NOTICE files.

Reconcile the BOM against:

- Resolved `mvn dependency:tree`.
- Nested libraries inside `BOOT-INF/lib` of the executable JAR.
- Manually copied/embedded resources and files.
- Container base image dependencies and OS packages if the product is a Docker/OCI image.

A Maven BOM does not automatically inventory every package inside the base OS/JRE layers. When shipping an image, generate an **image-level SBOM** with an organization-approved scanner/tool and review the licenses of those image packages separately.

## 9. SPDX Documents and the Role of SPDX Maven Plugin

CycloneDX is one SBOM format. SPDX is another standard with a model for expressing licenses, copyrights, packages, files, relationships, and document provenance. Depending on customer/registry policy, one or both formats may be required.

`spdx-maven-plugin` offers the `spdx:createSPDX` goal to generate an SPDX document from artifact/POM data and file-level configuration. Example plugin declaration per project documentation:

~~~xml
<plugin>
    <groupId>org.spdx</groupId>
    <artifactId>spdx-maven-plugin</artifactId>
    <version>1.0.4</version>
    <executions>
        <execution>
            <id>build-spdx-document</id>
            <goals>
                <goal>createSPDX</goal>
            </goals>
        </execution>
    </executions>
</plugin>
~~~

Direct invocation:

~~~bash
mvn spdx:createSPDX
~~~

The plugin writes the document under `target/site/` with a filename derived from groupId/artifactId/version and output format. Configure SPDX package/file fields, source information, licenses, and custom license references per plugin documentation.

**Never assume** that merely adding the plugin scans the entire binary or settles every component. Inspect the actual SPDX document, verify package/file scope, and supplement information that cannot be inferred from the POM. When a license is absent from the SPDX License List, use `LicenseRef-...` accompanied by proper license text/evidence—never invent SPDX IDs.

## 10. Complete POM: Spring Boot, License Notices, and BOM

The demo project arbitrarily assumes Apache-2.0. The POM below:

- Builds an executable JAR using Spring Boot Maven Plugin.
- Generates `THIRD-PARTY.txt` from dependency metadata.
- Fails if unresolved license metadata remains.
- Generates a CycloneDX XML/JSON BOM.
- Sets Java target 17.

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>

    <groupId>example.learning</groupId>
    <artifactId>distribution-audit-demo</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <name>Distribution Audit Demo</name>
    <description>Spring Boot packaging and license inventory example</description>

    <properties>
        <java.version>17</java.version>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <licenses>
        <license>
            <name>Apache License, Version 2.0</name>
            <url>https://www.apache.org/licenses/LICENSE-2.0</url>
            <distribution>repo</distribution>
        </license>
    </licenses>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>

            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>license-maven-plugin</artifactId>
                <version>2.7.1</version>
                <executions>
                    <execution>
                        <id>third-party-notices</id>
                        <phase>generate-resources</phase>
                        <goals>
                            <goal>add-third-party</goal>
                        </goals>
                        <configuration>
                            <includeTransitiveDependencies>true</includeTransitiveDependencies>
                            <includeOptional>false</includeOptional>
                            <includedScopes>compile,provided,runtime</includedScopes>
                            <useMissingFile>true</useMissingFile>
                            <missingFile>${project.basedir}/src/license/THIRD-PARTY.properties</missingFile>
                            <failOnMissing>true</failOnMissing>
                            <generateBundle>true</generateBundle>
                            <bundleThirdPartyPath>META-INF/THIRD-PARTY.txt</bundleThirdPartyPath>
                            <addOutputDirectoryAsResourceDir>true</addOutputDirectoryAsResourceDir>
                            <encoding>UTF-8</encoding>
                        </configuration>
                    </execution>
                </executions>
            </plugin>

            <plugin>
                <groupId>org.cyclonedx</groupId>
                <artifactId>cyclonedx-maven-plugin</artifactId>
                <version>2.9.3</version>
                <executions>
                    <execution>
                        <id>create-application-bom</id>
                        <phase>package</phase>
                        <goals>
                            <goal>makeBom</goal>
                        </goals>
                    </execution>
                </executions>
                <configuration>
                    <projectType>application</projectType>
                    <schemaVersion>1.6</schemaVersion>
                    <includeCompileScope>true</includeCompileScope>
                    <includeProvidedScope>true</includeProvidedScope>
                    <includeRuntimeScope>true</includeRuntimeScope>
                    <includeSystemScope>false</includeSystemScope>
                    <includeTestScope>false</includeTestScope>
                    <outputFormat>all</outputFormat>
                    <outputName>bom</outputName>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**What to understand before using this POM:**

- `<licenses>` describes the license of the **demo project**, not of its dependencies.
- `spring-boot-maven-plugin` is managed by the Boot parent and creates the executable JAR during the package lifecycle.
- The license plugin uses compile/provided/runtime scopes to inventory dependencies likely to appear in the executable JAR; transitive is enabled and optional is disabled to match Boot repackage defaults.
- `failOnMissing=true` intentionally fails the build if license metadata is missing. Complete `src/license/THIRD-PARTY.properties` before releasing.
- The CycloneDX plugin produces a separate BOM and does not replace `THIRD-PARTY.txt` or legal approval.
- The POM omits repository credentials, corporate allowlists, or distribution decisions for a real product.

In a real project, pin plugin versions per build governance, inspect the effective POM, and verify every plugin execution actually triggers.

## 11. Application Source Code and License Resources

### 11.1. Application.java

Create `src/main/java/demo/DistributionAuditDemoApplication.java`:

~~~java
/*
 * SPDX-License-Identifier: Apache-2.0
 */
package demo;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class DistributionAuditDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(
                DistributionAuditDemoApplication.class, args);
    }

    @Bean
    CommandLineRunner report() {
        return args ->
                System.out.println("distribution-audit-demo:ready");
    }
}
~~~

The SPDX header is only valid if this project genuinely selected Apache-2.0 and the organization holds the rights to grant that license. If the project uses another license or multiple licenses, update the header according to the verified decision.

Run the application:

~~~bash
java -jar target/distribution-audit-demo-1.0.0.jar \
  --spring.main.banner-mode=off \
  --logging.level.root=OFF
~~~

Exact line printed by the application code:

~~~text
distribution-audit-demo:ready
~~~

Spring Boot startup logs may vary by environment; the line above is the output of `CommandLineRunner`.

### 11.2. Placing License Text in Resources

In the demo project, create:

~~~text
LICENSE
src/main/resources/META-INF/LICENSE
src/main/resources/META-INF/NOTICE        (if NOTICE obligations apply)
src/license/THIRD-PARTY.properties        (when verified missing metadata exists)
~~~

`LICENSE` at the repository root should hold the full license text of the source project. `META-INF/LICENSE` is placed on the executable JAR's classpath/resources. If you must distribute a NOTICE for the project itself or upstream components, put the required contents in `META-INF/NOTICE` or the location required by policy.

Do not mechanically copy raw license files from every dependency without inspecting contents and filename collisions. Use `license:download-licenses` to aid collection, then determine which license texts/notices must be shipped per license and channel.

## 12. Build, Generate SBOM, and Inspect Dependency Inventory

From the project root:

~~~bash
mvn -B -ntp clean verify
~~~

The build includes:

1. `generate-resources`: License Maven Plugin resolves dependencies and generates third-party notices.
2. Compile/test/package: Maven builds the project.
3. Spring Boot `repackage`: creates the executable JAR.
4. `package`: CycloneDX plugin generates the BOM.

Main outputs:

~~~text
target/distribution-audit-demo-1.0.0.jar
target/bom.json
target/bom.xml
target/generated-sources/license/THIRD-PARTY.txt
~~~

The License Plugin output path depends on `outputDirectory` if customized; the path above is the common default location. Verify actual files after building.

Capture the dependency tree:

~~~bash
mvn dependency:tree -DoutputFile=target/dependency-tree.txt
mvn dependency:tree -Dscope=runtime -DoutputFile=target/runtime-dependencies.txt
~~~

If missing license metadata remains during discovery, you can temporarily run:

~~~bash
mvn license:add-third-party \
  -Dlicense.useMissingFile=true \
  -Dlicense.failOnMissing=false
~~~

Inspect the items needing attention, verify upstream licenses, populate the missing-metadata file, and re-run the strict build. Never keep unverified overrides just to keep CI green.

### 12.1. Inspecting the BOM

Inspect the JSON/XML files with an appropriate tool:

~~~text
target/bom.json
target/bom.xml
~~~

The BOM must accurately reflect the Maven module, version, direct/transitive components, available license metadata, and dependency relationships. CycloneDX plugin attaches the BOM with classifier `cyclonedx` during install/deploy by default; if storing it with the release, verify the artifact is actually attached and published.

### 12.2. Inspecting the Executable JAR

~~~bash
jar tf target/distribution-audit-demo-1.0.0.jar
~~~

For an executable Spring Boot JAR, check these entry groups:

~~~text
META-INF/MANIFEST.MF
BOOT-INF/classes/demo/DistributionAuditDemoApplication.class
BOOT-INF/classes/META-INF/LICENSE
BOOT-INF/classes/META-INF/THIRD-PARTY.txt
BOOT-INF/lib/...
~~~

This is an illustrative list of expected entries in the example, not the full `jar tf` output. `BOOT-INF/lib` holds nested runtime libraries. If the app has a NOTICE to distribute, also confirm `BOOT-INF/classes/META-INF/NOTICE`.

**Do not stop at checking `target/generated-sources/license/THIRD-PARTY.txt`**. The file could be generated yet excluded or omitted from the final JAR. Only the final archive proves what is shipped.

## 13. Java 17 Validator Checking License Resources in the Executable JAR

Create `DistributionArchiveCheck.java` at the project root, outside `src/main/java`:

~~~java
import java.nio.file.Path;
import java.util.jar.JarFile;

public class DistributionArchiveCheck {

    private static void require(boolean condition, String message) {
        if (!condition) {
            throw new IllegalStateException(message);
        }
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            throw new IllegalArgumentException(
                    "Usage: java DistributionArchiveCheck.java <jar-file>");
        }

        Path path = Path.of(args[0]);
        try (JarFile jar = new JarFile(path.toFile())) {
            String prefix = "BOOT-INF/classes/META-INF/";

            boolean projectLicense =
                    jar.getEntry(prefix + "LICENSE") != null;
            boolean thirdPartyNotice =
                    jar.getEntry(prefix + "THIRD-PARTY.txt") != null;
            boolean runtimeLibraries = jar.stream().anyMatch(entry ->
                    entry.getName().startsWith("BOOT-INF/lib/")
                            && entry.getName().endsWith(".jar"));

            require(projectLicense,
                    "Project LICENSE is missing from executable JAR");
            require(thirdPartyNotice,
                    "THIRD-PARTY.txt is missing from executable JAR");
            require(runtimeLibraries,
                    "No nested runtime libraries found");

            System.out.println("archive.project-license=present");
            System.out.println("archive.third-party-notice=present");
            System.out.println("archive.runtime-libraries=present");
        }
    }
}
~~~

This program uses the Java 17 Standard Library `JarFile` and checks three packaging conditions:

- The project license text is packaged in classpath resources.
- The third-party notice is included in the executable JAR.
- The JAR contains nested runtime dependencies.

Run:

~~~bash
java DistributionArchiveCheck.java \
  target/distribution-audit-demo-1.0.0.jar
~~~

With the example configuration and created resources, stdout is exact:

~~~text
archive.project-license=present
archive.third-party-notice=present
archive.runtime-libraries=present
~~~

This validator **does not evaluate whether license contents are accurate, complete, or legally compatible**. It only prevents a common packaging mistake: generating a report/notice that never ends up in the archive. Reviewing the component list, license texts, NOTICE files, and obligations remains a separate step.

If using an executable WAR, application resources reside under `WEB-INF/classes/META-INF/` and libraries under `WEB-INF/lib`/`WEB-INF/lib-provided`. Adapt the validator to the WAR layout rather than assuming `BOOT-INF` paths.

## 14. Evaluating Obligations by License Type and Usage

The table below serves only as a guide to the questions you need to ask. Exact license text, version, exceptions, linking/combining model, and distribution channel determine actual obligations.

| Example license/group | Points typically needing review | What not to infer |
| --- | --- | --- |
| Apache-2.0 | Retain license text, required copyright/NOTICE; check patent grant and modification terms | Having Apache-2.0 does not permit using trademarks or dropping upstream NOTICE |
| MIT | Retain copyright and permission notice in appropriate distributions | MIT does not allow deleting attribution |
| BSD-2-Clause / BSD-3-Clause | Retain copyright, conditions, and disclaimer; BSD-3 includes a non-endorsement clause | Do not collapse all BSD licenses into a single set of terms |
| MPL-2.0 | Check file-level copyleft, which files were modified, and how source of covered files is supplied on distribution | Do not conclude the whole product automatically shares the license from one MPL file |
| LGPL | Check linking method, ability to replace/relink the library, source, and corresponding distribution terms | Static vs. dynamic linking and packaging structure can change obligations |
| GPL | Check distribution of covered work, source/corresponding source, and combination terms | Do not draw conclusions merely from a dependency appearing in the Maven tree |
| AGPL | Check network-service delivery and network-use clauses | Do not assume a hosted service is always treated like internal binary use |
| Proprietary/commercial | Check contract, redistribution rights, instance/user limits, territory, sublicensing, support, and transfer restrictions | Being able to download a JAR does not grant rights to ship it to customers |
| Custom/unknown | Read the license text, identify licensor, scope, source, and special conditions | Never invent an SPDX ID or wave it through because the POM has a URL |

Obligations may include:

- Distributing accompanying license texts and copyright notices.
- Preserving NOTICE files or adding attribution.
- Publishing/attaching corresponding source code or a written offer for source.
- Disclosing modifications to copyleft-covered files.
- Providing relinking materials or library replacement rights under specific terms.
- Clearly marking changes and copyright notices.
- Honoring patent clauses, exceptions, and trademark restrictions.
- Complying with commercial contract terms for proprietary components.

Never apply a blanket rule to every license sharing a name if a component has an exception, dual license, or modified license text. Record the **exact license version and evidence**.

## 15. Decision Matrix: Which Components May Enter the Distribution?

Each component should have a review record:

| Field | Example content |
| --- | --- |
| Component identity | `org.example:library:2.4.1` or path to asset |
| Source | Maven repository/upstream URL/vendor package |
| Version and hash | Exact version, SHA-256 if artifact exists |
| Relationship | Direct/transitive, parent dependency |
| Scope | compile/runtime/provided/test/system or non-Maven |
| Shipped? | Yes/no; which artifact/channel |
| Declared license | SPDX ID/expression or name in POM |
| Evidence | LICENSE, NOTICE, source tag, POM, contract, URL |
| Obligations | Text/notice/source/attribution/other conditions |
| Decision | APPROVED / APPROVED_WITH_OBLIGATIONS / REVIEW_REQUIRED / REJECTED / NOT_SHIPPED |
| Reviewer/date | Approver, timestamp, applicable policy/version |

**APPROVED_WITH_OBLIGATIONS** means tasks must ensure all conditions are fulfilled before release. Never let this status pass the release gate without evidence that the corresponding notice/source files are actually shipped.

### 15.1. Separating Code, Asset, and Contract Reviews

A single product can simultaneously include:

- Maven libraries with SPDX license IDs.
- Fonts/icons with separate attribution requirements.
- Images/data with non-commercial or redistribution restrictions.
- Proprietary SDKs requiring customer redistribution rights.
- Native binaries with license texts separate from any POM.
- Container base images with their own packages and notices.

Do not force all of these into a single Maven dependency tree. Maintain separate inventories linked under a common release manifest so you know which artifact each belongs to.

## 16. Non-Maven Components and Docker Base Images

### 16.1. Frontend, Fonts, Images, and Native Binaries

If the application copies any of these into `src/main/resources` or static directories, they are still distributed components:

- JavaScript packages and CSS frameworks.
- Web fonts, icon packs, SVGs, logos.
- Images, videos, datasets, maps, and sample data.
- Native executables or `.so`/`.dll`/`.dylib` libraries.
- SQL schemas, certificates, command scripts, generated templates.
- Source snippets or code copied from Stack Overflow, repositories, and documentation.

Each file/vendor bundle needs its source, version/commit, license, hash, and distribution terms. A file copied directly into the JAR may **not appear** in the Maven SBOM yet can still carry licensing obligations.

### 16.2. Container Images

If distributing a Docker/OCI image, the inventory must cover:

1. The executable JAR and all embedded dependencies.
2. The JRE distribution.
3. The base operating system and package manager packages.
4. CA certificates, fonts, native tools, and additionally installed packages.
5. Startup scripts, healthcheck binaries, manually copied files.
6. The image SBOM and released registry digest/version.

The Java project's CycloneDX Maven BOM does not replace an image-level SBOM. Generate an inventory from the **final image** using an organization-approved scanner, reconciling OS packages against the base image and Dockerfile-added layers.

### 16.3. Build Tools and Plugins

Maven plugins, compilers, test runners, and CI containers are usually not packaged into the executable JAR. However, they are still part of the build supply chain. If you distribute a build environment/toolchain image or source bundle to customers, they can become product components requiring review.

Clearly distinguish:

- **Runtime SBOM:** what the application needs at runtime.
- **Build SBOM:** tools and dependencies used to build the product.
- **Container/image SBOM:** all packages inside the released image.

The three inventories may overlap, but they are not necessarily identical.

## 17. CI Release Gates for Licenses and Distributable Components

A release pipeline can be organized as follows:

~~~text
1. Resolve exact dependency versions
          |
          v
2. dependency:tree + source/asset inventory
          |
          v
3. License Maven Plugin
   - generate THIRD-PARTY.txt
   - detect missing metadata
   - resolve verified overrides
   - apply approved allowlist/denylist
          |
          v
4. CycloneDX BOM (+ SPDX document if required)
          |
          v
5. Human/policy review
   - license text and version
   - distribution channel
   - required notices/source/attribution
   - commercial redistribution rights
          |
          v
6. Build executable JAR / image
          |
          v
7. Inspect final archive/image
   - nested dependencies
   - LICENSE / NOTICE / THIRD-PARTY
   - non-Maven components
          |
          v
8. Save SBOM + hashes + approval evidence
          |
          v
9. Publish exact artifact that passed gates
~~~

| Gate | PASS when | FAIL/hold when |
| --- | --- | --- |
| Dependency inventory | Direct/transitive dependencies and versions are recorded | Any dependency or version is unexplained |
| License metadata | Every component has valid evidence; no unresolved unknowns | Unreviewed missing/NOASSERTION entries exist |
| Policy allowlist/denylist | All components match approved policy | Any component is outside allowlist or banned |
| Obligations | Required license texts/NOTICE/source/attribution and contracts are fulfilled | Missing documentation or redistribution rights |
| Package inspection | Archive/image contains only reviewed components and required notices | Uninventoried files/components or missing notices |
| SBOM | BOM generated for exact product/version and saved with release evidence | SBOM omits modules, has wrong scope, or isn't bound to artifact |
| Integrity | Artifact hash and image digest are recorded | Reviewed bytes cannot be uniquely identified |
| Publish | Exact file/image that passed all gates | Rebuilt or changed dependencies after approval without re-review |

### 17.1. Minimum Release Evidence

A useful release record:

~~~text
Product / module       : distribution-audit-demo
Release version        : 1.0.0
Git revision           : exact source commit
Build toolchain        : Maven + JDK version
Dependency graph       : dependency-tree.txt
License report         : THIRD-PARTY.txt
SBOM                   : bom.json / bom.xml
Project license        : SPDX ID + LICENSE file
Third-party obligations: notices/source/attribution checklist
Non-Maven inventory    : assets/fonts/native/base-image
Approval               : reviewer, policy version, date
JAR SHA-256            : checksum of exact executable JAR
Image digest           : digest if an OCI image is shipped
Repository location    : exact published artifact coordinates
~~~

Never store passwords, tokens, or secrets in SBOMs, license reports, or build logs. If a vendor license/contract has restricted access, store a reference to the controlled document repository rather than embedding the contract in a public artifact.

### 17.2. Never Rebuild After Approval While Keeping the Old Conclusion

If dependency versions, resources, JAR bytes, base image, or Dockerfile change after review, prior release evidence may no longer apply to the new artifact. Re-run the corresponding inventory/scan steps and bind approval to the **exact artifact hashes/versions**. Never reuse approval for JAR A to ship JAR B just because the Git commit did not change.

## 18. Common Issues and How to Handle Them

| Symptom | Possible cause | Investigation step |
| --- | --- | --- |
| `THIRD-PARTY.txt` lacks transitive libraries | Incorrect plugin filters or `includeTransitiveDependencies` | Check effective POM, plugin logs, dependency tree |
| Build fails due to unknown license | Dependency POM lacks license metadata | Check upstream source/release; use missing file after verification |
| Report says Apache yet source release has another LICENSE | Inaccurate POM metadata or mismatched artifact/release | Verify exact version/hash and upstream license text |
| Allowlist fails on “Apache License” even though “Apache-2.0” was allowed | License plugin matches human-readable POM names, not directly SPDX IDs | Check exact names in report and normalize policy |
| SBOM misses a font/icon file | File is not declared as a Maven dependency | Add separate asset inventory and license evidence |
| SBOM includes a dependency absent from the JAR | Scope, optional, system, or test difference | Reconcile CycloneDX scopes against `BOOT-INF/lib` |
| JAR contains a `provided` library missing from license report | Report scope excluded provided while Boot repackage included it | Include provided in license inventory or prove it is not shipped |
| JAR has `META-INF/THIRD-PARTY.txt` but lacks license texts | Third-party summary does not bundle full license texts automatically | Download/review license files and package per obligations |
| POM `<licenses>` is Apache yet dependency is GPL | Confused project license with third-party licenses | Review each component individually |
| `NOASSERTION` treated as approved | No license determination made yet | Transition to REVIEW_REQUIRED |
| Dependency downloaded from Maven Central treated as freely redistributable | Confused download access with redistribution rights | Check license, contract, and channel |
| Container image contains packages absent from Maven BOM | Base OS/JRE and Docker layers are outside Maven graph | Generate image-level SBOM and review OS packages |
| Maven Enforcer fails to block an unapproved license | BannedDependencies matches artifact coordinates only | Use license report/allowlist; Enforcer is for component blacklists only |
| `mvn clean verify` passes yet release lacks notices | Notices were never packaged into final archive | Check `jar tf` and validator against the actual JAR |
| License file edited manually without a source | Evidence is untraceable | Record upstream URL/hash/reviewer and override revision |
| Multi-module report includes only one module | Non-aggregate goal run at root or misconfigured execution | Use aggregate goal or per-module per reactor layout |
| Docker image update introduces new packages | Mutable base image tag or changed layers | Pin/record digest, regenerate image SBOM, and review |

Never resolve an issue by dropping a dependency from the report if it is still packaged. Exclude from an inventory only with clear rationale and evidence that the component lies outside distribution scope or is covered by another inventory.

## 19. Checklist and Self-Check Questions

### Pre-Release Checklist

- [ ] Exact product and distribution channel finalized: source, JAR, WAR, image, SDK, OEM, or hosted.
- [ ] Direct/transitive Maven dependencies, versions, and scopes recorded.
- [ ] Dependency tree reconciled against actual nested JARs/resources in the archive.
- [ ] Fonts, icons, images, frontend assets, native binaries, datasets, and vendored code inventoried.
- [ ] Maven POM license metadata verified against upstream LICENSE/NOTICE for exact versions.
- [ ] Valid SPDX IDs/expressions used; `NONE`/`NOASSERTION` never treated as approved.
- [ ] License Maven Plugin has no remaining unresolved missing license metadata.
- [ ] Allowlist/denylist uses exact license names or component coordinates per approved policy.
- [ ] `THIRD-PARTY.txt` generated and contents reviewed.
- [ ] CycloneDX BOM/SPDX document generated per release requirements.
- [ ] Project LICENSE and required NOTICE files retained in distribution.
- [ ] License texts/source/attribution identified and shipped per specific obligations.
- [ ] Base image/JRE/OS packages checked if shipping an OCI image.
- [ ] Reviewer sign-off and approval evidence recorded for components needing decisions.
- [ ] Git revision, dependency tree, SBOM, JAR SHA-256, and image digest (if applicable) retained.
- [ ] **Exact reviewed artifact bytes** published.

### Self-Check

**Question A.** A project POM declares `Apache-2.0`. Can we conclude all dependencies are Apache-2.0?

**Answer:** No. The `<licenses>` block describes the current project. Every dependency has its own license metadata and terms.

**Question B.** `mvn dependency:tree` shows direct dependencies. Is that enough?

**Answer:** Not yet. You also need transitive dependencies and inspection of the actual artifact; use the full `dependency:tree`, license reports/SBOMs, and archive inspection.

**Question C.** Are `MIT OR Apache-2.0` and `MIT AND Apache-2.0` the same?

**Answer:** No. `OR` expresses a choice of license; `AND` means you must comply with both.

**Question D.** License Maven Plugin generates `THIRD-PARTY.txt`. Does that satisfy all license obligations?

**Answer:** Not yet. That file is a metadata summary; you must still inspect license texts, NOTICE files, source/attribution, and component-specific conditions.

**Question E.** Does Maven's CycloneDX BOM record every package in the Docker base image?

**Answer:** No. A Maven BOM primarily describes the Maven project/dependencies. Container images require a separate inventory/SBOM for the JRE, OS, and layers.

**Question F.** A component is blocked by Maven Enforcer `bannedDependencies`. Does the rule know whether it uses GPL or MIT?

**Answer:** No. The rule blocks by dependency coordinates/patterns. License analysis requires separate plugins/reports and reviews.

**Question G.** Does `NOASSERTION` mean the license has been accepted?

**Answer:** No. It indicates no determination has been made. The component must be investigated before passing release policy.

**Question H.** A build passed legal review, and afterward a dependency patch version was bumped. Can the old approval be reused?

**Answer:** Not automatically. A new version can change licenses, notices, or the component set; you must re-inventory and verify corresponding release evidence.

## 20. Official Documentation

- SPDX — License List and identifiers: https://spdx.org/licenses/
- SPDX — License Exceptions: https://spdx.org/licenses/exceptions-index.html
- SPDX — License Expressions (AND/OR/WITH/LicenseRef): https://github.com/spdx/spdx-spec/blob/develop/docs/annexes/spdx-license-expressions.md
- SPDX — Handling License Information: https://spdx.dev/learn/handling-license-info/
- Apache Maven — Dependency Mechanism and Scopes: https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html
- Apache Maven — Dependency Plugin / dependency:tree: https://maven.apache.org/plugins/maven-dependency-plugin/usage.html
- MojoHaus — License Maven Plugin Usage: https://www.mojohaus.org/license-maven-plugin/usage.html
- MojoHaus — License Maven Plugin add-third-party goal and parameters: https://www.mojohaus.org/license-maven-plugin/add-third-party-mojo.html
- MojoHaus — Third-party license examples, missing metadata and allowlists: https://www.mojohaus.org/license-maven-plugin/examples/example-thirdparty.html
- CycloneDX — Maven Plugin documentation: https://cyclonedx.github.io/cyclonedx-maven-plugin/
- CycloneDX — Maven Plugin release history: https://github.com/CycloneDX/cyclonedx-maven-plugin/releases
- SPDX — SPDX Maven Plugin: https://spdx.github.io/spdx-maven-plugin/
- Apache Maven Enforcer — Banned Dependencies: https://maven.apache.org/components/enforcer/enforcer-rules/bannedDependencies.html
- Spring Boot — Packaging Executable Archives and repackage: https://docs.spring.io/spring-boot/3.5/maven-plugin/packaging.html
- Spring Boot — Build / executable archive packaging: https://docs.spring.io/spring-boot/3.5/how-to/build.html
- Java 17 — JarFile API: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/jar/JarFile.html

**Remember:** License auditing must connect **component inventory → license evidence → obligations → approval → exact distributed artifact**. The Maven tree, License Maven Plugin, and SBOMs automate collection and catch common mistakes; only inspecting the **final product**, actual license/NOTICE documents, and distribution-channel policies creates a trustworthy distribution record.