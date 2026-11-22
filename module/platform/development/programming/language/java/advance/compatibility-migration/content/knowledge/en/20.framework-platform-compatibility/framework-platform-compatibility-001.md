# Reading framework Java requirements and support matrices

When upgrading a Java application, a question usually emerges very early: **"Does the current framework support the JDK we want to upgrade to?"**. The answer cannot rely on the program compiling cleanly, a short article saying "works on the new Java," or a table listing only a minimum Java version. For long-lived products, the engineering team needs to know precisely **which framework version**, **which JDK version**, **which build/runtime configuration**, **until what date**, and **under what level of assurance** the publisher provides support.

For example, a framework may state "requires Java 17 or later." This sentence indicates the minimum floor within a certain scope, yet **does not automatically confirm every future JDK lies within the tested or officially supported matrix**. Another framework release might have been tested on JDK 21 while requiring a newer Gradle plugin to build, or having extensions/native-image integrations that do not yet support that environment.

This lesson guides you through reading framework **Java requirements** and **support matrices** in the context of **Java Advance Compatibility Migration**: from locating the right documentation sources, interpreting support statuses, and checking dependencies and build tools to building decision tables, planning migration paths, and verifying with representative tests.

> **Principle:** Conclude that a framework supports a combination only after identifying the scope, version, date checked, and official source of that statement. Tables in this lesson use hypothetical names and version numbers to illustrate reading methodology, **not current support announcements for any specific framework**.

## 1. "Java support" has multiple meanings

### 1.1. Minimum JDK is not maximum verified JDK

Distinguish:

- **Minimum Java version:** the lowest Java version required by the framework to run or compile according to documentation.
- **Supported Java versions:** JDK versions covered by the framework's support commitment at a given point in time and for a specific release line.
- **Tested / certified Java versions:** runtime versions included in the development team's or vendor's test or certification matrix.
- **Known to work / compatible in practice:** a configuration that may run in practice yet lacks an official commitment.
- **Unsupported / end of support:** no longer covered by support commitments or already outside the support window.
- **Unknown / not documented:** no clear evidence found; **never silently turn this into "supported" or "unsupported"**.

Hypothetical documentation example:

```text
Framework Alpha 4.2
- Requires Java 17 or higher
- Tested on Java 17 and Java 21
- Java 25 validation is planned
```

Accurate interpretation:

1. Java 17 is the declared minimum floor.
2. Java 17 and 21 have "tested" evidence according to this document.
3. Java 25 is not yet proven at the "tested" level from the description above alone.
4. You cannot deduce that Java 25 is forbidden to run, nor can you claim Java 25 is already officially supported.
5. If a support contract exists, check the actual commercial support policy rather than assuming "tested" always implies an SLA.

### 1.2. Runtime support does not mean build support

A Java project can use multiple different JDKs within the same pipeline:

```text
Developer IDE JDK          : 21
Maven/Gradle daemon JDK    : 21
Java compiler toolchain   : 21
javac --release           : 17
Test execution JVM        : 17 and 21
Production runtime        : 17
Framework minimum runtime : 17
```

This combination can be valid. Application code is compiled with the Java 21 compiler while emitting bytecode/API targeting Java 17. However, framework plugins, annotation processors, or test runners may carry their own JDK requirements.

When documentation states "Java 21 required," verify whether it applies to **runtime**, **build tools**, **compilers**, **native image builders**, or only **a development plugin**.

### 1.3. Java SE support differs from Jakarta EE and application server support

Especially for web or enterprise applications:

- **Java SE/JDK:** the Java runtime provided by the JVM.
- **Jakarta EE API:** set of APIs and specifications for enterprise applications.
- **Jakarta EE implementation/application server:** e.g., a server running applications and providing container services.
- **Servlet container:** has a different API scope from a full Jakarta EE server.
- **Framework:** may run on a servlet container, reactive server, or embedded server with distinct requirements.

A server version claiming Java 21 support does not automatically guarantee that frameworks/ORMs/drivers inside the application also support Java 21. Conversely, a framework running on Java 21 does not mean an old application server can load the new artifact.

## 2. Compatibility layers that must be read together

A real-world application may traverse this chain:

```text
                 Java runtime (vendor, version, OS, arch)
                              |
                              v
                       Application server
                              |
                              v
                       Framework core
                              |
                  +-----------+-----------+
                  |           |           |
                  v           v           v
                 ORM      HTTP stack    Security
                  |           |           |
                  +-----------+-----------+
                              |
                              v
                  Application code / libraries
                              |
                              v
                    Drivers / native / agents

Separate build-time:
JDK -> Maven/Gradle -> plugins -> annotation processors -> artifact
```

Each layer can publish its own matrix. To decide on a JDK upgrade, never read only the framework core page while ignoring components on the critical path.

| Layer | Question to confirm | Useful information source |
|---|---|---|
| JVM/JDK | Are vendor, release, update level, OS/architecture used/supported by the product? | JDK vendor docs and runtime support policy |
| Framework core | Which framework version requires/supports the target JDK? | Framework reference guide and support matrix |
| Framework plugins | Do build plugins, starters, CLIs, and code generators share the release line? | Plugin docs and release notes |
| Application server | Can the server/container run the target JDK and framework version? | Server compatibility matrix |
| ORM, security, HTTP | Are integration modules and transitive libraries compatible? | BOM, release notes, issue tracker, compatibility docs |
| Build tool | Can the Gradle/Maven version run on the target JDK? | Build tool runtime/build matrix |
| Test tools | Do JUnit, mocking/bytecode, coverage, and agents support the target JDK? | Each tool's documentation |
| Driver/native | Are JDBC drivers, JNI, TLS providers, and native-image toolchains verified? | Vendor docs and OS/arch matrix |
| App artifact | Are class-file major and Java API targets correct? | Compiler configuration and artifact inspection |
| Infrastructure | Do base images, container runtimes, CA stores, and deployment pipelines support it? | CI/image/deployment documentation |

Do not confuse a system that "starts up" with an entire combination being supported. A bug in an ORM, bytecode proxy, or JDBC driver might only surface when handling a rare business flow.

## 3. Which documentation sources carry the highest authority?

### 3.1. Source priority order

When needing to prove a combination is supported, prioritize:

1. **Official reference documentation for the exact framework version.**
2. **Vendor support / compatibility matrix and lifecycle policy** where available.
3. **Release notes, migration guides, and known issues** of the exact release line.
4. **BOM/dependency management and plugin compatibility docs** for companion components.
5. **Corresponding JDK vendor, build tool, and application-server docs.**
6. **Official issue trackers** to clarify bugs or limits not yet updated in docs.
7. Community articles, Stack Overflow, blogs, operational anecdotes — useful for spotting clues, yet **never replace official commitments**.

If two sources differ, verify whether they refer to the same release line and the same type of "support." A marketing page claiming "Java 21 ready" may lack the precision of a compatibility table and migration guide.

### 3.2. Version-specific documentation, not the default "latest" page

Many websites route readers to documentation for the **newest version**, even when an application runs an older framework version.

Hypothetical example:

```text
Application currently uses: Framework Alpha 3.8
Default opened page: Framework Alpha 5.0 latest
Latest table: "Requires Java 21"
```

It would be wrong to conclude Alpha 3.8 requires Java 21 merely from reading Alpha 5.0's page. It is equally wrong to apply "Java 25 supported" from a new version back to an old branch.

Before recording Java requirements, verify:

- The URL/document selects the exact version.
- The release line or minor version matches.
- Whether the page applies to OSS, enterprise, or commercial editions.
- Whether release notes impose tighter limits than the overview page.
- Whether the document carries an update date or patch-release caveats.

### 3.3. Why check dates matter

A release line may be updated to support a newer JDK in a patch release, or stop receiving patches after end-of-life. The same statement "supports Java 21" must be timestamped:

```text
Checked on: 2026-11-12
Product line: Alpha 4.x
Exact release: Alpha 4.2.6
Claim: Java 21 is supported
Source: official versioned documentation
Support status: maintained / limited / EOL (verify separately)
```

This is an illustrative template for recording evidence, not factual info about Alpha. During a multi-month migration, **re-verify the support matrix before freezing the release**.

### 3.4. Distinguishing "not found in docs" from "unsupported"

If a JDK does not appear in a table, several explanations are possible:

- The JDK is too new and has not been tested by the publisher yet.
- The table lists only LTS releases, not every release.
- Documentation has not been updated yet.
- Support applies only to a specific edition or patch version.
- The framework may still run, yet the vendor has not committed to it.
- The framework genuinely does not support it; clear evidence or confirmation is needed.

Reporting rules should enforce three separate statuses: **Supported**, **Unsupported**, **Not verified**. Never extrapolate from silence in documentation.

## 4. Reading common phrasing in support matrices

| Phrase | Careful interpretation | Required action |
|---|---|---|
| `Minimum Java 17` | Minimum runtime/compile floor within the stated scope | Check whether newer JDKs appear in the supported/tested list |
| `Java 21 compatible` | Compatibility with Java 21 is stated, yet assurance level needs confirmation | Read scope, patch release, and limitations |
| `Tested on Java 17, 21` | Runtimes tested under some process | Distinguish tested from support SLA |
| `Certified on JDK vendor X` | Certification for a specific vendor/distribution | Check vendor/edition/OS/architecture |
| `Java 25 support added in 4.3.2` | Support begins at the stated patch | Do not apply to 4.3.0/4.2.x without evidence |
| `Runs on Java 17+` | Broad range claim | Look up exclusions, known issues, and lifecycle |
| `Requires Java 21 for build` | Build tooling requires JDK 21 | Do not infer that artifact runtime requires Java 21 |
| `Java 21 baseline` | Release line raised its baseline platform | Verify minimum runtime and bytecode output |
| `Not tested with Java 25` | No testing certification from this source yet | Mark Not verified and plan testing/vendor follow-up |
| `End of maintenance` | Maintenance ended or reduced per policy | Check security fix policy and migration path |

Key point: many statements use the word "support" while carrying **different entitlements**. OSS community support, vendor enterprise support, and distribution-bundled support may have differing terms.

## 5. Minimum runtime, build JDK, and target bytecode

### 5.1. Class-file major version

A JVM can only load class-file versions it supports. Common milestones:

| Java | Class-file major |
|---|---:|
| 8 | 52 |
| 11 | 55 |
| 17 | 61 |
| 21 | 65 |
| 25 | 69 |

If an artifact carries major 65, a Java 17 JVM cannot load that class even if a POM claims "Java 17 compatible."

To inspect a class inside a JAR:

```shell
javap -verbose -classpath framework-or-app.jar com.example.Main
```

A `major version: 61` line indicates the class-file version matching Java 17. However, inspecting one class is insufficient to prove all nested/shaded JARs or transitive dependencies match that level.

### 5.2. `--release` differs from `--source` and `--target`

With modern `javac`:

```shell
javac --release 17 -d build/classes src/com/example/App.java
```

`--release 17` restricts source features, bytecode, and Java SE platform APIs to match release 17 within compiler support.

Conversely, `--source 17 --target 17` does not fully protect against accidentally calling newer Java APIs when the compiler links against a newer JDK's platform libraries. Thus, when a framework still supports Java 17 while CI uses JDK 21, `--release 17` meaningfully enforces the application's own policy.

**However:** `--release` does not automatically check minimum Java versions of third-party JARs, code generators, agents, and native dependencies.

### 5.3. A framework can support running on JDK 21 while producing Java 17 libraries

There is no contradiction here. A framework built with a newer JDK can publish artifacts usable across multiple JDKs, and compatible applications can compile targeting Java 17.

Conversely, a build plugin requiring Java 21 while project outputs still target Java 17 can also be an intentional setup. Read each component's "Building," "Running," and "Supported JDKs" sections carefully.

## 6. Hypothetical matrix example: learning how to read rather than memorizing versions

Suppose an organization evaluates three framework lines:

| Framework release | Minimum Java | Documented tested JDKs | Maintenance status | Initial assessment |
|---|---:|---|---|---|
| Alpha 3.x | 11 | 11, 17 | Maintenance ending | Do not choose for long-term migration if support is ending soon |
| Alpha 4.x | 17 | 17, 21 | Active | Candidate when wanting to run Java 21 |
| Alpha 5.x | 21 | 21, 25 | Active | Candidate when ready to raise the runtime floor to Java 21 |

**All names and numbers in this table are hypothetical**; the purpose is learning how to reason. If an application still has a consumer running Java 17, upgrading to Alpha 5.x with a Java 21 minimum breaks that consumer contract. If the goal is running Java 25 while Alpha 4.x is only documented as tested up to 21, inspect patch notes and support evidence further before confirming.

### 6.1. Creating a decision table for a specific application

Example for `order-service`:

```text
Current:
  Framework: Alpha 3.4
  Runtime JDK: 17
  Build JDK: 17
  Deployment: Linux x86_64
  Database driver: D 2.x
  Target: JDK 21

Candidate:
  Framework: Alpha 4.2
  Runtime JDK: 21
  Build JDK: 21
  Database driver: D 3.x
```

The decision table should include columns for:

- Source URL/document version.
- Claim type: minimum, tested, officially supported, EOL.
- JDK vendor and OS/architecture.
- Support status of framework plugins and drivers.
- Known issues risk.
- Required test suite.
- Final status: supported / not verified / unsupported / blocked.

Do not simply write "framework OK," as it hides the verified scope.

### 6.2. Intersection of supported sets

If a production environment includes multiple components, selectable JDKs must lie in the **intersection** of sets supported by mandatory components.

Hypothetical example:

```text
Framework Alpha 4.x  : {17, 21}
Build tool B         : {17, 21, 25}
Application server C : {11, 17, 21}
JDBC driver D        : {17, 21}

Intersection         : {17, 21}
```

Wanting to pick Java 25 has no basis in the table above. Nor is computing the intersection enough on its own: data must share the same check date, OS/architecture, and patch release, while meeting each component's restrictions.

## 7. Spring ecosystem: reading versions layer by layer

### 7.1. Spring Framework and Spring Boot are not a single product

Within the Spring ecosystem, multiple version lines exist:

- Spring Framework core.
- Spring Boot.
- Spring Data.
- Spring Security.
- Spring Cloud release trains.
- Spring Integration/Batch and companion projects.
- Embedded servers, servlet/reactive stacks.
- Hibernate/JPA, logging, testing, and BOM-managed dependencies.

When looking up a Spring Boot version, verify:

1. The minimum Java/JDK published for **that Spring Boot version**.
2. Which Spring Framework and companion library versions are managed.
3. Maven/Gradle and **Spring Boot build plugin** requirements.
4. Embedded server and Jakarta/Servlet baselines.
5. Whether the Spring Cloud release train is compatible with the Boot release line if Spring Cloud is used.
6. Java vendor/runtime and native-image support if applicable.
7. Which patch releases resolve issues with the new JDK.

Do not infer from "Spring Framework runs on Java X" that every Spring Boot or Spring Cloud release supports Java X.

### 7.2. Example of recording evidence

```text
Component           : Spring Boot
Exact version       : <version from project>
Reference docs      : <versioned URL>
Minimum runtime JDK : <documented value>
Tested JDKs         : <documented list>
Build plugin version: <version in project>
Gradle/Maven support: <documented requirement>
Spring Cloud train  : <value if applicable>
Known issues        : <links to version-specific notes>
Decision            : supported / blocked / not verified
```

This is a template, not a pre-filled table of latest versions. When a team says "upgrade Spring" in a single bullet point, the odds of missing dependency alignment are very high.

### 7.3. Switching `javax.*` and `jakarta.*` is a separate axis

A framework migration may simultaneously move from old Java EE namespaces to new Jakarta EE namespaces. This is **not** a simple class-file version change.

Example old import:

```java
import javax.persistence.Entity;
```

A new Jakarta Persistence API may use:

```java
import jakarta.persistence.Entity;
```

If the framework release line requires Jakarta APIs, source code, JPA providers, servlet containers, and integration libraries must transition together. Running on a new JDK does not rename these packages automatically.

### 7.4. Embedded servers and cloud release trains

A Spring Boot version ships with a specific embedded server, while Spring Cloud maintains its own compatibility matrix against Boot lines. Consult **inter-version compatibility tables**, rather than independently picking the "latest" versions.

For applications deployed as WARs on external servers, consult that server/container's support matrix as well. A WAR built with a new Boot/Framework release may fail if the server supplies an older Servlet API, even if the JDK is supported.

## 8. Quarkus, Micronaut, and AOT/native frameworks

### 8.1. Frameworks with build-time augmentation/code generation steps

Modern frameworks perform substantial work at build time: annotation processing, bytecode generation, augmentation, or native-image preparation. Consequently, Java runtime requirements split into:

- JDK running the framework and JVM application.
- JDK building the application.
- GraalVM/Mandrel/native-image JDK/format and version to create native executables.
- Minimum Java for Maven/Gradle plugins.
- Minimum JDK for CLI and test tools.
- Extension support per framework version.

Do not read "supports Java 21" and deduce that every extension and native image setup is also certified.

### 8.2. Quarkus: platform BOM and extension matrix

When reading Quarkus documentation, verify exact platform and extension versions, as they are normally managed via a BOM or curated platform dependencies.

Questions to ask:

- Which Java version does the Quarkus release in use require?
- Do JVM mode and native mode share the same support matrix?
- Which JDK/Gradle/Maven versions do build tool plugins need?
- Which platform and OS/architecture does the native-image toolchain require?
- Are database, messaging, and security extensions on the same platform version?
- Are there migration notes regarding changed configs, namespaces, or APIs?

### 8.3. Micronaut: runtime and annotation processing

With Micronaut or frameworks heavily reliant on compile-time processing, confirm processor/plugin/build tool versions are compatible with the JDK/compiler. An application may run on a JDK while an older annotation processor fails when compiling with a newer `javac`.

Inspect separately:

- Micronaut Framework release line.
- Micronaut Gradle/Maven plugin.
- Annotation processors and generated code.
- Data/Serialization/Security modules if used.
- Native support and AOT features.
- Actual runtime JDKs tested by the framework.

### 8.4. JVM mode and native image are two distinct matrices

Hypothetical example:

| Mode | JDK used | Additional tools | What to check |
|---|---|---|---|
| JVM application | OpenJDK/Temurin/Oracle/... | Java launcher | Runtime JDK and dependencies |
| Native executable | GraalVM/Mandrel or compatible native-image toolchain | C compiler, libc, OS image | Native toolchain version, OS/architecture, reflection/resource config |
| Container JVM | JRE/JDK in base image | Container runtime | CPU architecture, CA store, libc, JVM flags |
| Container native | Native executable + runtime libraries | OS base image | ABI, dynamic libraries, and compatibility |

A framework line supporting JDK 21 **does not automatically prove** that Native Image builds of the same app run across every Linux distro.

## 9. Jakarta EE, servlet containers, and externally deployed applications

### 9.1. Container support is a mandatory condition

Enterprise applications may run on:

- Servlet containers.
- Full Jakarta EE application servers.
- Embedded servers.
- Custom runtimes packaged by the organization.

These components may publish different Java versions. When upgrading the JDK, check:

1. Does the current server version support the new JDK?
2. If the server needs upgrading, must the application change its Jakarta EE specification level?
3. Do server-provided Java/Jakarta APIs conflict with JARs bundled in the WAR/EAR?
4. Are providers such as JPA, CDI, transactions, and messaging compatible?
5. Does server documentation distinguish community support from commercial support?
6. Is the target environment's OS/architecture on the certification list?

### 9.2. Avoiding two incompatible API/provider versions

For example, an application might bundle one version of a servlet/JPA API inside the WAR while the server supplies another. Upgrading the JDK does not fix this error.

Establish dependency scopes (such as `provided` in Maven when the container supplies APIs), inspect the effective dependency graph, and test deployment on the actual server. Never run unit tests in an IDE and declare compatibility proven.

### 9.3. Server version and JDK must share a coordinated update plan

If an old server is EOL or uncertified on the target JDK, an intermediate step may be needed:

```text
Legacy JDK + Legacy server
          |
          v
Supported newer server on current JDK
          |
          v
Newer server + Target JDK
```

Alternatively, an organization may upgrade both in one release given sufficient integration tests and rollback plans. Optimal sequencing depends on dependencies and service constraints; no single prescription applies to every application server.

## 10. Framework release lines and support lifecycles

### 10.1. "It runs" does not solve maintenance

An old framework release might boot on Java 21 after adding a few flags, yet that release line has reached end of security maintenance. Such a migration solves immediate runtime execution while leaving long-term product risk.

Read the lifecycle policy:

- General availability (GA) and release date.
- Major/minor line support window.
- OSS maintenance vs. commercial support.
- Security-only maintenance phase.
- End of maintenance and End of Support (EOL/EOS).
- Support conditions for LTS lines.
- Requirements to stay on the latest patch release of a supported line.
- Rules for non-LTS JDK releases.

### 10.2. You may need to upgrade the framework before upgrading the JDK

If the current framework does not support the target JDK, a typical roadmap is:

```text
Old framework + current JDK
       |
       v
New framework already supporting current JDK
       |
       v
Functional and data testing
       |
       v
New framework + target JDK
       |
       v
Runtime/JVM testing and release
```

The benefit is isolating framework-upgrade errors from JDK-upgrade errors. However, this approach works only if an **overlapping support region** exists between the two framework lines and two JDK versions. If the new framework does not run on the old JDK, a coordinated simultaneous upgrade or parallel environment must be designed.

### 10.3. Do not pick "latest" without checking the release train

A new major release can:

- Raise minimum JDK requirements.
- Change Jakarta/Servlet baselines.
- Alter property names or autoconfiguration.
- Require newer build plugins.
- Change Hibernate, Netty, Jackson, or logging versions.
- Remove deprecated APIs.
- Force companion integrations to upgrade alongside it.

Pick a release **supported and compatible with the entire stack**, not merely the highest version number of a single artifact.

## 11. Inventorying the project before reading matrices

### 11.1. Minimum information

Build an inventory per application or deployable:

| Field | Example to record |
|---|---|
| Service name | `order-service` |
| Framework + exact version | Current framework release/patch |
| Java runtime | Vendor, version, update level |
| Java build | Maven/Gradle/compiler JDK |
| Packaging | JAR/WAR/EAR/container/native |
| Server/container | Embedded or external server version |
| Platform | OS, architecture, container base image |
| Build tool + plugins | Maven/Gradle and plugin versions |
| Critical dependencies | ORM, security, HTTP, JDBC, messaging, logging |
| Agents/native | Coverage, APM, JNI, TLS providers |
| Desired JDK | Target JDK and target release date |
| Support contract | OSS/commercial and expiry |
| Owner | Team responsible for verification/rollout |

### 11.2. Distinguishing declared versions from resolved versions

A POM may declare only a starter dependency while a framework BOM picks dozens of transitive dependencies. Readers must distinguish:

- Directly declared versions.
- Versions managed by a parent POM or BOM.
- Final resolved versions selected by dependency resolution.
- Actual versions packaged inside the fat JAR/container image.
- Versions of build plugins and their plugin dependencies.

A very common mistake is checking compatibility for the declared starter instead of what actually ships inside the artifact.

### 11.3. Commands to inspect actual tooling

Useful inventory commands:

```shell
java -version
javac -version
./mvnw -version
./gradlew --version
```

Run only commands for tools present in the repository. On Windows, wrappers are typically `mvnw.cmd` or `gradlew.bat`. Terminal `java -version` output does not guarantee the production runtime matches; inspect inside the actual container/VM/service context.

## 12. Inspecting Maven projects to cross-check framework requirements

### 12.1. Frameworks and dependencies are often managed via parent/BOM

Example POM structure:

```xml
<properties>
    <java.version>21</java.version>
</properties>

<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>com.example</groupId>
            <artifactId>platform-bom</artifactId>
            <version>5.2.0</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
```

`com.example:platform-bom` and the version above are illustrative. A BOM manages dependency versions yet does not automatically prove every module inside it supports Java 21. Cross-check framework, integration, and JDK requirements for the exact platform version.

### 12.2. Inspecting the effective POM

```shell
./mvnw help:effective-pom
```

The effective POM consolidates parent, dependency management, profiles, and inherited settings. It helps answer:

- What is the final Java compiler configuration?
- Which framework BOM is imported?
- Which plugin versions are used?
- Which profiles can alter requirements?
- Which modules override settings?

For multi-module builds, inspect key modules individually; do not infer from a parent POM that all child modules inherit identically.

### 12.3. Viewing the dependency tree

```shell
./mvnw dependency:tree
```

This reveals actual selected versions of ORM, HTTP, logging, security, and drivers. When dependency conflicts exist, understand Maven mediation and `dependencyManagement` before concluding a "framework version X + library version Y" pairing is valid.

### 12.4. Enforcing minimum JDK in Maven

The Maven Enforcer Plugin can fail builds running on a JDK outside policy bounds. Conceptual example:

```xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-enforcer-plugin</artifactId>
    <version>3.5.0</version>
    <executions>
        <execution>
            <id>enforce-build-jdk</id>
            <goals>
                <goal>enforce</goal>
            </goals>
            <configuration>
                <rules>
                    <requireJavaVersion>
                        <version>[21,22)</version>
                    </requireJavaVersion>
                </rules>
            </configuration>
        </execution>
    </executions>
</plugin>
```

Plugin version and range illustrate syntax only; select them from the real support matrix. The rule checks the **JDK executing Maven goals within configuration scope**, not every runtime where the artifact will later execute.

### 12.5. Compiler release differs from Maven runtime

A POM may specify:

```xml
<properties>
    <maven.compiler.release>17</maven.compiler.release>
</properties>
```

If the compiler supports `--release 17`, main code can target Java 17 even if the Maven process runs on a newer JDK. Yet a newer application framework or dependency JAR might require Java 21, causing Java 17 runtime failures. **Compiler target settings cannot downgrade the JDK required by framework binaries.**

## 13. Inspecting Gradle projects to cross-check framework requirements

### 13.1. Both Gradle version and framework plugin version matter

The Gradle version must be able to run on the daemon JDK. At the same time, framework plugins may impose their own Gradle version/JDK requirements.

```shell
./gradlew --version
./gradlew dependencies
```

`dependencies` can generate large reports across configurations; filter to relevant configurations in multi-project builds.

### 13.2. Gradle Java toolchains

Groovy DSL example:

```groovy
plugins {
    id 'java'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}
```

A toolchain declares the JDK used for compilation or integrated tasks. It is not a declaration that the framework in use officially supports Java 21, nor does it force custom tasks or plugins to use that toolchain.

If an application needs to build with JDK 21 while outputting Java 17 libraries:

```groovy
tasks.withType(JavaCompile).configureEach {
    options.release = 17
}
```

Check dependencies and run tests on Java 17 if that is the lowest committed runtime.

### 13.3. Viewing selected dependencies

```shell
./gradlew :app:dependencies --configuration runtimeClasspath
./gradlew :app:dependencyInsight --dependency example-core --configuration runtimeClasspath
```

`app` and `example-core` are placeholders. When a framework BOM manages versions, use reports to confirm final resolved versions and selection reasons rather than reading the version catalog alone.

### 13.4. Plugins requiring their own JDK or newer Gradle versions

A framework upgrade may require upgrading build plugins first. Read in parallel:

- Framework runtime support.
- Gradle framework-plugin compatibility.
- Gradle runtime JVM matrix.
- Java compiler toolchain support.
- Kotlin/Groovy/Scala compiler versions if used.
- Test plugin and instrumentation tool versions.

A single line stating "Java 21 supported" does not resolve these relationships.

## 14. Framework BOMs and dependency alignment

### 14.1. Why do BOMs matter when upgrading the JDK?

A framework typically publishes a BOM/dependency constraints tested across a library set. When independently bumping Hibernate, Netty, Jackson, or security libraries outside that set, the application may run on a combination the framework vendor has never validated.

Hypothetical example:

```text
Framework Alpha 4.2 BOM:
  core         4.2.x
  orm          6.y
  json         2.z
  http-server  11.w
```

Do not map these numbers to real frameworks. The takeaway is treating the version set as **a combination governed by the release line**.

### 14.2. Overriding dependencies is not strictly wrong, yet requires evidence

Valid reasons to override include:

- Fixing a critical CVE before the framework BOM updates.
- Needing a newer driver supporting the target database or JDK.
- Addressing a bug patched in a child library.
- Executing a phased migration.

Still, verify binary/API compatibility, run integration tests, and document the rationale. Never treat "latest dependency" as automatically compatible with the framework in use.

### 14.3. Release trains and linked versions

In ecosystems with release trains (e.g., extension/platform modules), a train aligns with a specific set of framework versions. Do not upgrade the core framework while keeping all old integration modules merely because the build has not reported errors yet.

Adopt the rule:

> Every release candidate must include a resolved version list cross-checked against the framework matrix and mandatory integrations.

## 15. Reading release notes and migration guides purposefully

### 15.1. Support matrices say "supported"; migration guides say "what to change"

A support table can confirm Java 21 runtime compatibility, yet cannot list every change across a framework major upgrade:

- Package/namespace changes.
- Changed properties and default configurations.
- Altered endpoint or serialization behavior.
- Removed deprecated APIs.
- Changed module access, reflection, and classloading.
- Tightened security defaults.
- Changed ORM schema/dialect behaviors.
- New embedded server and servlet baselines.
- New native-image reflection/resource configs.
- New test framework or startup lifecycles.

Therefore, once the target combination is confirmed as supported, read the **migration guide for the specific upgrade path from the current version to the target version**.

### 15.2. Reading across intermediate milestones

If an application sits on framework major 2 and aims for major 5, do not read only major 5 release notes. Cross-check breaking changes across 3, 4, and 5, including Java requirements that increased along the way.

Example workflow:

```text
Current release
      |
      v
Read next major migration guide
      |
      v
Identify source/API/config changes
      |
      v
Repeat for following release lines
      |
      v
Choose supported target patch version
```

### 15.3. Known issues can override matrix conclusions

A matrix states "Java 21 supported," yet the issue tracker lists a known bug impacting a critical application feature. Record that risk:

```text
Framework/JDK pair: officially supported
Feature: AOT native + specific database extension
Known issue: affects current patch release
Workaround: available / unavailable
Decision: blocked for our workload until patched
```

Overall support for a combination does not guarantee every specialized feature or configuration works. Production readiness conclusions must rest on the real workload.

## 16. OSS docs, commercial support, and JDK vendors

### 16.1. A single version may carry multiple support tiers

For example, a framework release line may:

- Be past OSS maintenance while still commercially supported.
- Be maintained by a distributor with custom patches.
- Receive extended support for selected platforms/JDKs.
- Receive security patches only, rejecting feature fixes.
- Require using a dedicated artifact repository or vendor build.

If your product relies on SLA guarantees, check entitlements and support contracts. Do not assume from community announcements that an organization qualifies for patches under commercial terms.

### 16.2. JDK vendors can affect certification

OpenJDK-based distributions share high Java SE compatibility, yet a vendor support matrix may certify only specific distributions, OSes, and architectures. Pay special attention to:

- Vendor and update train.
- Linux distribution/Windows Server version.
- CPU architecture, e.g., x86_64 and aarch64.
- FIPS/TLS/crypto provider configurations.
- Supported JVM flags or runtime options.
- Container runtime and native-image environments.

If development tests on one JDK vendor on macOS, that is not certification evidence for another vendor on Linux ARM64 in production.

## 17. Framework requirements differ from application release compatibility

### 17.1. Minimum framework Java is only one constraint

A framework supports Java 17 and 21, yet the application may inadvertently:

- Compile a module with `--release 21`.
- Use a library carrying class major 65.
- Attach a Java agent not supporting the target JVM.
- Rely on restricted internal JDK APIs.
- Use a native library lacking binaries for the target architecture.
- Contain code calling removed Java APIs.
- Experience altered serialization/certificate/TLS behavior.

The outcome is **framework compatible** yet **application incompatible**. Thus, the framework support matrix decides valid candidate targets, while acceptance tests decide whether your application is ready.

### 17.2. The same framework/JDK has multiple deployment configurations

Example:

| Runtime | Framework | Packaging | Additional risks |
|---|---|---|---|
| Java 21 | Alpha 4.x | Executable JAR | Embedded server, startup flags |
| Java 21 | Alpha 4.x | WAR | External server and Jakarta APIs |
| Java 21 | Alpha 4.x | Container | Base image, cert store, architecture |
| Java 21 | Alpha 4.x | Native binary | Native-image toolchain, reflection config |

This table is hypothetical. Passing tests in one row does not mean remaining rows receive identical support.

## 18. Designing a project verification matrix

A solid matrix has at least two layers: **vendor support evidence** and **application validation results**.

### 18.1. Layer 1: vendor support evidence

| ID | Component | Version | JDK candidate | Claim | Evidence | Status |
|---|---|---|---|---|---|---|
| F-01 | Framework core | Exact patch | 21 | Supported | Exact-version documentation | Verified |
| F-02 | Build plugin | Exact patch | 21 | Tested | Plugin docs | Verified |
| F-03 | Application server | Exact patch | 21 | Not found | No source yet | Not verified |
| F-04 | JDBC driver | Exact patch | 21 | Unsupported | Support matrix | Blocked |

Statuses in the table only illustrate how to document entries, not real-product confirmations.

### 18.2. Layer 2: test results

| ID | Scenario | Runtime | Result | Evidence |
|---|---|---|---|---|
| T-01 | Startup/healthcheck | Java 21 | Pass/Fail | CI log, test run |
| T-02 | API/serialization | Java 21 | Pass/Fail | Contract tests |
| T-03 | Database transaction | Java 21 | Pass/Fail | Integration tests |
| T-04 | Security/authentication | Java 21 | Pass/Fail | Security tests |
| T-05 | Load/performance | Java 21 | Pass/Fail | Benchmark |
| T-06 | Graceful shutdown | Java 21 | Pass/Fail | Runtime log |
| T-07 | Rollback compatibility | Java 17/21 | Pass/Fail | Release test |

Do not merge "vendor support confirmed" and "tests passed" into one Yes/No cell because they answer two separate questions.

### 18.3. Status labels and evidence tiers

A clear set of labels:

- **VERIFIED_SUPPORTED:** official source found for the exact version/scope.
- **VERIFIED_UNSUPPORTED:** official source explicitly states unsupported.
- **NOT_VERIFIED:** insufficient evidence available yet.
- **CONDITIONAL:** supported only when meeting specific patches, OSes, editions, or configs.
- **APPLICATION_TEST_PASS:** application passed organizational tests; independent of vendor support.
- **BLOCKED:** known barrier exists, requiring resolution prior to rollout.

Keep the two categories separate so an internal test pass is not mistaken for vendor certification.

## 19. Step-by-step framework matrix reading for a migration

### Step 1: Record the target

Example:

```text
Workload               : order-service
Current Java runtime   : 17
Target Java runtime    : 21
Framework currently    : <exact current version>
Deployment model       : JAR in Linux container
Required OS/arch       : Linux x86_64, Linux aarch64
Support needed until   : <business support horizon>
```

Do not pick a target framework version before knowing runtime, lifecycle, and platform requirements.

### Step 2: Check requirements of the current version

Determine whether the framework in use already supports the target JDK. If yes, a JDK-only upgrade may be feasible with minimal churn. If not, evaluate newer framework releases.

Even when matrices list support, check patch-specific known issues and mandatory integrations.

### Step 3: Shortlist candidate framework release lines

Create a summary:

```text
Candidate A: keep the current framework if supported
Candidate B: upgrade minor/patch within the current release line
Candidate C: upgrade major to a release line with long-term maintenance
```

Compare support windows, breaking changes, dependency BOMs, migration costs, and support horizons. Do not automatically pick the latest major version.

### Step 4: Verify support intersection across the stack

For each candidate, inspect:

- Framework core and plugins.
- Spring Cloud/extension train if used.
- Application server/embedded server.
- ORM, drivers, security, HTTP, messaging.
- Build tools and compiler toolchains.
- Test tools and Java agents.
- OS/architecture/native image.
- JDK distribution and patch level if specified by vendors.

### Step 5: Read migration guides and categorize changes

Separate into categories:

- Source/API changes.
- Build tool/plugin changes.
- Dependency upgrades.
- Configuration defaults.
- Jakarta namespaces.
- JVM/module access/bytecode.
- Data/protocol migrations.
- Deployment and observability changes.

Independent changes can be split into separate PRs to reduce risk.

### Step 6: Establish baselines and golden tests

Before changing the framework/JDK:

- Capture the resolved dependency graph.
- Record framework/BOM/plugin versions.
- Record bytecode target and artifact checksums.
- Save startup logs and JVM options.
- Run unit/integration tests on the current runtime.
- Capture contract/serialization fixtures for critical payloads.
- Record latency, memory, GC, and connection-pool metrics.

### Step 7: Upgrade under control

A sequence may be:

1. Upgrade build tools/plugins if needed.
2. Upgrade the framework to a release still runnable on the current JDK if possible.
3. Update sources/configs/namespaces.
4. Verify functionality and data.
5. Switch the JDK runtime to the target.
6. Execute the full CI/validation matrix.
7. Canary and monitor production.

If no incremental step exists due to framework Java floors, design a clear simultaneous upgrade plan with production-like staging.

### Step 8: Preserve final evidence

Decisions must include exact versions, source links, check dates, resolved graphs, CI logs, and risk-acceptance rationales. Never let "already tested Java 21" stand as the sole documentation for a release.

## 20. Practical example: choosing between keeping and upgrading a framework

Suppose an application currently runs:

```text
Framework Alpha 3.6
Java 17
Maven 3.x
Embedded Server S 9.x
Driver D 2.x
```

The goal is Java 21. After consulting docs, the team gathers **hypothetical** data:

| Component | Current version on Java 21 | Candidate version on Java 21 |
|---|---|---|
| Framework Alpha | Not verified | Supported in Alpha 4.2 |
| Server S | Unsupported | Supported in S 10.x |
| Driver D | Supported | Supported in D 3.x |
| Maven/plugins | Old plugins unverified | Newer plugins verified |
| Security module | Old patch EOL | New patch active |

The logical conclusion is not "Alpha 3.6 definitely fails," but that **the current combination lacks sufficient basis to be declared supported**. A sound candidate is upgrading framework/server/plugins along documented migration paths and then validating Java 21.

### 20.1. Hypothetical rollout plan

```text
Release 1:
  Update Maven/plugins
  Fix dependency conflicts
  Keep Java 17

Release 2:
  Upgrade Framework Alpha + Server S
  Adapt configuration/source
  Keep Java 17 if supported by new stack

Release 3:
  Switch production to Java 21
  Run compatibility and performance tests

Release 4:
  Remove temporary compatibility flags
  Close legacy support issues
```

If the new framework only supports Java 21, Release 2 and Release 3 may need merging. Support matrices reveal **feasible paths**, while release management determines acceptable risk.

### 20.2. Rollback scenario

If the new release modified database schemas or message formats, rolling back the JAR/framework to the prior version may fail to read newly written data. Therefore:

- Verify backward/forward schema compatibility.
- Use expand-then-contract when possible.
- Maintain migration scripts and database backups per policy.
- Enable producers to emit new values only after consumers are ready.
- Document version pairings per release.

Framework Java support matrices do not automatically cover business data compatibility; that is a separate risk.

## 21. JDK test matrix in CI

### 21.1. Separating compile and test JVMs

Example of an application supporting both Java 17 and 21:

```text
Compile:
  JDK 21 compiler
  --release 17

Test:
  Java 17 runtime
  Java 21 runtime

Package:
  JAR with compatible bytecode
  dependencies verified for minimum Java 17
```

If the target framework requires Java 21, the matrix above no longer fits framework application builds. Raise the minimum runtime or maintain a separate branch/artifact for Java 17 consumers.

### 21.2. Startup tests are only the first gate

A thorough matrix covers:

| Test category | Why it matters when upgrading JDK/framework? |
|---|---|
| Startup and healthcheck | Catches classloading/config failures early |
| HTTP contracts | Endpoints, validation, JSON behavior |
| Database/JPA | Query dialects, lazy loading, transactions |
| Security/TLS | Authentication, certificates, crypto defaults |
| Messaging | Serialization, converters, retries, schemas |
| Scheduling/async | Executor behavior, shutdown, context propagation |
| Reflection/proxies | Module encapsulation, instrumentation |
| Native/JNI | OS/architecture/ABI |
| Performance | Memory, latency, GC, thread usage |
| Packaging/deployment | WAR/JAR/container/native image |
| Rollback | Data and protocols between old/new versions |

Suites must exercise real product integrations; never copy a "framework demo" and claim the entire workload is verified.

### 21.3. Testing the exact final artifact

If builds produce a fat JAR, Docker image, or native binary, test that exact artifact. Passing Maven/Gradle `test` on an IDE classpath can differ in dependencies and runtime layout from production packaging.

Record:

- Artifact SHA-256/digest.
- Resolved framework/BOM versions.
- Runtime Java version and vendor.
- Container image digest if applicable.
- Test reports by OS/architecture.
- Known deviations and waivers.

## 22. Java runtime differences commonly exposed during framework upgrades

### 22.1. Reflection and strong encapsulation

Old frameworks and bytecode libraries may deeply access JDK internals. Upon upgrading the JDK, reflective access can be blocked under JPMS/strong encapsulation.

Symptom:

```text
java.lang.reflect.InaccessibleObjectException
```

Instead of spraying `--add-opens` and declaring support, verify whether a newer framework/agent supports the target JDK. Using module-opening flags should be a deliberate, minimal-scope measure with a removal plan.

### 22.2. Dependencies removed from the JDK

Certain APIs formerly inside older JDKs are no longer supplied the same way. Legacy code or frameworks may require replacement dependencies. When reading migration guides, separate **JDK removals** from **framework breaking changes** so you fix the right layer.

### 22.3. Bytecode libraries and proxies

ORMs, AOP, mocking, serialization, and framework internals may use ASM/Byte Buddy or class-file processing libraries. On newer JDKs, they must understand corresponding major class-file versions.

A framework release note stating "Java 21 support" might hold true only from the patch release that upgraded its bytecode library. That is why identifying exact patch versions—not just major lines—is essential.

### 22.4. TLS, cryptography, and certificates

Newer JDKs or frameworks can alter default enabled algorithms and protocols. Systems calling older servers sometimes fail only when establishing TLS connections, connecting to LDAP, or invoking external APIs.

Read JDK security release notes and test end-to-end in target environments; core framework support matrices do not guarantee compatibility with external endpoints.

### 22.5. Observability and production agents

Java agents for APM, profiling, tracing, and coverage manipulate bytecode or use JVM instrumentation. They maintain separate support matrices. A service may run smoothly without agents yet crash when deployed with `-javaagent`.

Consequently, enable production-like agents and JVM flags in staging, or explicitly document differences requiring validation.

## 23. Spotting misleading documentation

### 23.1. A generic statement without versions

```text
"Our framework works with modern Java."
```

Insufficient. Exact versions, JDK releases, conditions, and check dates are needed.

### 23.2. Applying "latest" info to the version in use

```text
Framework latest supports Java 25
Application is on framework 3.x
```

Inconclusive. Consult documentation for branch 3.x or an appropriate upgrade path.

### 23.3. Having only "minimum Java 17"

This does not guarantee Java 21/25 was tested. Require a supported/tested JDK table or vendor confirmation.

### 23.4. An individual issue comment saying "works for me"

Useful as a hint worth testing, yet never a support commitment. Additionally, OS, JDK vendor, dependency graph, and feature usage may differ.

### 23.5. A green compilation build on a new Java version

Compilation does not adequately test native runtimes, dynamic class loading, database dialects, TLS, serialization, or rollout compatibility. A real test matrix is required.

### 23.6. Relying on a BOM while overriding many modules

If an application overrides a large share of BOM-managed dependencies, official support scope may change. Document overrides explicitly and run targeted tests.

### 23.7. Confusing plugin minimum JDK with artifact minimum JDK

Build plugins may require Java 21 while artifacts target Java 17, or vice versa. Consult separate documentation for builders and runtimes.

### 23.8. Confusing "support ends on date X" with "binaries stop running on date X"

EOL refers to maintenance/support commitments, not the JVM intentionally halting execution on that date. Nonetheless, EOL introduces major security/operational risk and must influence migration decisions.

## 24. Questions to send vendors or framework maintainers

When documentation is unclear, ask targeted specifics rather than "does it support the new Java?":

1. Which **JDK releases and vendors** officially support framework release **X.Y.Z**?
2. Does support cover our production **OS/architecture**?
3. What is the minimum patch release adding support for the target JDK?
4. Does support cover **build plugins**, annotation processors, and CLIs?
5. Does the framework run on the target runtime when packaged as a WAR inside **server version A**?
6. Do ORM, security, messaging, and native-image extensions carry the same certification?
7. Are there known issues regarding the target JDK, and what are the corresponding workarounds/patches?
8. Until when does the release line receive security fixes?
9. Is there a migration guide from our running version to the candidate version?
10. Are any configurations/JVM flags excluded from support scope?

Archive the response and confirmation date alongside migration records. For commercial contracts, clarify vendor support escalation conditions.

## 25. Troubleshooting when the matrix and reality diverge

### 25.1. Framework claims Java 21 support, yet app throws `UnsupportedClassVersionError`

**Possible cause:** a module or dependency targeted a higher Java version than production runtime, or the actual runtime is not Java 21 as expected.

**Inspect:** `java -version` in the real environment, class-file major versions inside JARs and nested dependencies, Docker images/startup configs.

**Resolution:** select compatible dependencies/artifacts or upgrade runtime per policy; do not treat framework support as proof every JAR inside the app shares the same class major.

### 25.2. Build tool fails to run on the new JDK

**Cause:** older Gradle/Maven/plugin versions carry different runtime requirements.

**Inspect:** build tool support matrix and `./gradlew --version`/`./mvnw -version`.

**Resolution:** upgrade wrappers/plugins to supported versions, pin toolchains, and re-run CI builds.

### 25.3. Build succeeds yet ORM fails in integration tests

**Cause:** ORM version/dialect or JDBC driver is incompatible with the framework/server/database, or Jakarta API changes apply.

**Inspect:** resolved dependency tree, ORM/JPA release notes, database dialects, and server support matrix.

**Resolution:** adopt BOM-managed combinations or overrides proven by integration tests.

### 25.4. New framework requires `jakarta.*` yet app still has `javax.*`

**Cause:** incomplete Java EE/Jakarta EE migration, not merely a JDK mismatch.

**Inspect:** imports, WAR dependencies, container-provided APIs, transitive libraries, and migration guides.

**Resolution:** migrate namespaces/implementations per release line and run contract/integration tests.

### 25.5. New JDK fails only when enabling the APM agent

**Cause:** agent/bytecode transformer lacks support for target JDK class-file versions or JVM internals.

**Inspect:** agent compatibility matrix and deployed version.

**Resolution:** upgrade the agent and test with production-like observability settings.

### 25.6. Java 21 runs on a dev laptop yet crashes in an ARM64 container

**Cause:** differing OS/CPU, native libraries, libc, JDK distribution, or architecture-specific dependencies.

**Inspect:** image digests, architecture, framework/native extension matrices.

**Resolution:** choose base images and native artifacts supporting the exact target; test on the matching architecture.

### 25.7. Framework docs show "supported," yet security scanners report EOL

**Cause:** support may apply only to another edition, an outdated documentation page, or a release line past its maintenance window.

**Inspect:** latest lifecycle policy for the exact release line and support contract.

**Resolution:** adopt a maintained patch/branch or document approved exceptions/mitigations.

### 25.8. Target JDK not found in matrix

**Cause:** unverified or outside documented scope.

**Inspect:** patch release notes, official issue trackers, vendor confirmation.

**Resolution:** mark `NOT_VERIFIED`, do not self-declare support; consider upgrading the framework or adjusting target JDK if official support is mandatory.

## 26. Checklist for reading support matrices

### Documentation scope

- [ ] Identified exact framework version and release line.
- [ ] Reading version-matched documentation rather than the latest page by mistake.
- [ ] Recorded official source URL and verification date.
- [ ] Distinguished minimum, tested, certified, supported, and EOL statuses.
- [ ] Checked minimum patch release adding JDK support.
- [ ] Read migration guides and known issues along the upgrade path.

### Java and environment

- [ ] Separated build JDK, compiler toolchain, target bytecode, and runtime JDK.
- [ ] Recorded vendor, update level, OS, and architecture.
- [ ] Verified compilers/build tools support the target JDK.
- [ ] Cross-checked dependency class-file majors and minimum Java levels.
- [ ] Confirmed native-image requirements where applicable.
- [ ] Audited JVM flags, agents, security/TLS, and module access.

### Framework and ecosystem

- [ ] Core framework lies within an appropriate release line.
- [ ] Build plugins, BOMs, and release trains are aligned.
- [ ] Application server/embedded server carries matching support.
- [ ] ORM, security, HTTP, messaging, and JDBC drivers are verified.
- [ ] Jakarta/Servlet specification levels align with framework/server.
- [ ] Extensions and native libraries have separate matrices where needed.
- [ ] No critical dependency overrides remain untested.

### Migration decision

- [ ] Created table of candidate combinations and evidence status.
- [ ] Identified a combination supported across the product's support horizon.
- [ ] Categorized blockers and unverified items.
- [ ] Defined test matrix across real JDK/OS/architecture targets.
- [ ] Archived resolved dependency graphs and artifact checksums.
- [ ] Prepared canary, monitoring, and rollback plans.
- [ ] Release is never approved solely because "build succeeded."

## 27. Case-study exercises

### Exercise 1: Interpreting "Java 17 or later"

Hypothetical documentation:

```text
Framework Beta 3.5 requires Java 17 or later.
CI officially tests Java 17 and Java 21.
Support for Java 25 is under investigation.
```

Answer:

1. Which minimum Java version is confirmed?
2. What evidence exists for Java 21?
3. Can Java 25 be marked officially supported?
4. If the product requires vendor support, what further details must be checked?
5. If a build plugin requires Java 21 while runtime remains Java 17, is there a contradiction?

### Exercise 2: Selecting frameworks for a multi-component app

An application uses:

```text
Framework: F 2.x
Application server: S 8.x
JDBC driver: D 1.x
Gradle: G old release
Runtime: Java 17
Target: Java 21
```

After consulting exact docs, you discover F 2.x is unverified with Java 21, S 8.x does not support Java 21, while D 1.x supports it.

Build a decision table containing: supported / unsupported / not verified, evidence source, candidate version, and test/upgrade actions. Explain clearly why "driver supports Java 21" cannot be treated as the conclusion for the entire application.

### Exercise 3: Framework and BOM mismatch

A framework release line was vendor-tested with a library set in a BOM, yet the application overrode ORM and JSON to two newer versions. Present:

- What can still be inferred from the framework support matrix?
- Which areas fall outside the tested version set?
- Which dependency graphs should be collected?
- Which integration tests should be prioritized?
- When should you wait for a newer BOM or upgrade the framework line?

### Exercise 4: Build JDK differs from runtime JDK

An application builds with JDK 21, configured with `javac --release 17`, running on Java 17. The Gradle plugin requires newer Gradle running on JDK 21.

Draw a matrix separating:

```text
Gradle daemon JDK
Compiler toolchain
Source/bytecode/API target
Test runtime JDK
Production runtime JDK
Framework minimum runtime
```

Identify which conditions must be verified in Gradle, plugin, and framework docs.

### Exercise 5: Phased upgrade decision

A new framework requires Java 21, while the old framework runs Java 17 and is already EOL. The service faces a tight maintenance deadline.

Propose how to reduce risk when forced to upgrade framework and JDK almost simultaneously: staging environment, golden data, dependency graphs, feature flags, canary, rollback, and support confirmation.

## Conclusion

Reading framework Java requirements and support matrices is an **evidence-collection and cross-checking activity**, not looking up a single version line. "Minimum Java," "tested," "certified," "supported," and "end of support" carry distinct meanings; core framework documentation never replaces matrices for build plugins, application servers, drivers, native-image toolchains, and extensions.

In Java Advance Compatibility Migration, begin by capturing exact versions and workloads, reading exact release-line documentation, checking support lifecycles and patch-specific known issues, and then finding the **intersection of supported combinations** across the entire stack. Use Maven/Gradle to verify resolved versions, inspect bytecode/runtime constraints, and execute integration tests on real JDKs, OSes, and artifacts. Only when both **support evidence** and **application validation** pass requirements does a team have solid grounds to declare a framework–JDK pairing production-ready.
