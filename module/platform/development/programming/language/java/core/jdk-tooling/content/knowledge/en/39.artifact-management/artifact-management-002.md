# Module Artifacts in Java: Building, Publishing, and Consuming

## Objectives

After this lesson, you will be able to explain module artifacts; distinguish a build module from a Java Platform Module System (JPMS) module; understand artifact coordinates and repository layout; create separate artifacts for each module in Maven multi-module and Gradle multi-project builds; manage dependencies between modules; distinguish build output, local install, and remote publication; publish JAR, POM, sources, Javadoc, and metadata; manage releases/SNAPSHOTs; verify artifacts before release; and troubleshoot issues when a module fails to produce or publish an artifact or when a consumer cannot resolve it.

## 1. What Is a Module Artifact?

In a Java project split into multiple modules, each module has its own responsibility and can produce one or more **artifacts** for use by other modules or external applications.

For example:

~~~text
shop-platform/
├── domain/
├── persistence/
└── application/
~~~

- `domain` contains models and business rules.
- `persistence` implements data access and depends on `domain`.
- `application` assembles components into an application and depends on `domain` and `persistence`.

After building, each module can produce an artifact:

~~~text
domain-1.0.0.jar
persistence-1.0.0.jar
application-1.0.0.jar
~~~

An artifact can be a JAR, WAR, EAR, ZIP, POM, or a file in a custom format. An aggregator-style module might only produce a POM and no JAR.

Within the scope of **artifact management**, a module artifact is the identifiable and distributable output of a module in a build. Artifacts are stored in a repository so that consumers can declare dependencies using stable coordinates.

### A Module Can Produce Multiple Artifacts

A Java library module can produce:

- A main JAR containing production classes and resources.
- A sources JAR for IDEs and developers to view source code.
- A Javadoc JAR for API reference.
- A test JAR or test fixtures if the project explicitly publishes test utilities.
- Secondary artifacts with specific classifiers or extensions.
- POM and metadata describing dependencies/publications.
- SBOM, checksums, signatures, and provenance accompanying a release.

An artifact does not have to be a JAR. A frontend module can produce a ZIP of static assets; a deployment module can produce a WAR; a native module can produce OS/architecture-specific binaries.

## 2. Distinguishing Build Modules and Java Modules (JPMS)

The word “module” has two common meanings in the Java ecosystem. It is important to distinguish them to avoid misconfiguration.

| Concept | Meaning | Example |
|---|---|---|
| Build module | A project/subproject built separately by Maven or Gradle within the same build | Maven module `domain`, Gradle project `:domain` |
| JPMS module | A module unit of the Java Platform Module System, with a module descriptor and dependency/encapsulation rules | `com.example.domain` |
| Artifact | An identifiable and distributable output file | `com.example:domain:1.0.0` |
| Repository | A place storing artifacts and metadata for consumers to download | Internal Maven repository |

A Gradle subproject or Maven module can produce a JAR without `module-info.class`. It is still a build module and still produces a valid artifact.

Conversely, a JPMS module can be packaged as a modular JAR. The module name in JPMS is neither the Maven `artifactId` nor necessarily the Gradle project name.

For example:

- Maven coordinates: `com.acme.platform:domain:1.0.0`.
- JPMS module name: `com.acme.platform.domain`.
- File: `domain-1.0.0.jar`.

These three values are related by naming convention but serve different purposes.

## 3. Artifact Coordinates Identify Module Output

An artifact is not just an arbitrarily named file. Build repositories use coordinates to identify an artifact and its version.

In Maven, the common fields are:

| Field | Role |
|---|---|
| `groupId` | Group/organization owning the artifact |
| `artifactId` | Name of the artifact/module |
| `version` | Version |
| `classifier` | Distinguishes secondary artifacts sharing the same base coordinates |
| `extension` | File extension, commonly `jar`, `pom`, `zip` |

The three fields `groupId:artifactId:version` are commonly called GAV. When describing an artifact in full, classifier and extension are also included (GAVCE).

For example:

~~~text
groupId    = com.acme.platform
artifactId = domain
version    = 1.0.0
classifier = sources
extension  = jar
~~~

Main artifact coordinates:

~~~text
com.acme.platform:domain:1.0.0
~~~

The sources artifact of the same version has full coordinates:

~~~text
com.acme.platform:domain:1.0.0:jar:sources
~~~

Classifier is an optional field. It is useful when a module publishes multiple files under the same version, such as `sources`, `javadoc`, or `tests`.

Do not use classifiers to hide incompatible API versions. If two artifacts represent different development lines or contracts, design clear `artifactId`s/versions instead.

### Maven Repository Layout

Given:

~~~text
groupId    = com.acme.platform
artifactId = domain
version    = 1.0.0
~~~

A Maven repository typically stores:

~~~text
com/
└── acme/
    └── platform/
        └── domain/
            └── 1.0.0/
                ├── domain-1.0.0.jar
                ├── domain-1.0.0.pom
                ├── domain-1.0.0-sources.jar
                └── domain-1.0.0-javadoc.jar
~~~

Each artifact can have its own checksums/signatures and repository metadata. The POM describes the project's identity and dependency metadata.

GAV coordinates are interpreted within the scope of a repository. Two different repositories may contain the same GAV with different bytes. This is why repository policies, checksum verification, and release immutability are necessary.

## 4. Artifact Lifecycle: Building, Local Install, and Remote Publish

A module artifact typically goes through the following stages:

~~~text
Module source
       |
       v
Compile + test
       |
       v
Package artifact
       |
       v
Local build output
       |
       +----> Consume directly in the same build
       |
       +----> Install to local repository
       |
       +----> Publish to remote repository
                    |
                    v
              Consumer resolves
                    |
                    v
              Compile / run
~~~

Three operations are often confused:

| Operation | Storage Location | Purpose |
|---|---|---|
| Build/package | Module's output directory | Create files for inspection or use in the current build |
| Install | Developer/agent's local repository | Allow other builds on the same machine to resolve the artifact |
| Publish/deploy | Remote repository | Share the artifact with the team, CI, or consumers |

Maven examples:

- `mvn package` creates the artifact in the `target` directory.
- `mvn install` installs the artifact and POM into the local repository, typically `~/.m2/repository`.
- `mvn deploy` uploads the artifact, POM, and attached artifacts to the configured remote repository.

Gradle examples:

- `./gradlew :domain:jar` creates the JAR in the project's output directory.
- `./gradlew :domain:publishToMavenLocal` publishes the publication to the local Maven repository.
- `./gradlew :domain:publish` executes publish tasks to the configured remote repositories.

The local repository is not an official distribution channel. A build that succeeds using an old artifact in the local repository does not prove that the current module produces the right artifact. When investigating issues, distinguish between a newly built artifact and an older artifact that was previously installed.

## 5. How Maven Multi-Module Projects Produce Artifacts

Maven supports grouping multiple projects into a single build using a parent/aggregator POM. This orchestration mechanism is called the **Maven Reactor**.

The Reactor:

1. Collects the declared modules.
2. Determines dependency relationships.
3. Orders modules into a valid build order.
4. Executes the lifecycle/goals for the selected modules.

If `application` depends on `domain`, the Reactor builds `domain` before it is needed by `application`.

### Aggregation and Inheritance

These two features are often placed in the same root POM, but they have different meanings:

- **Aggregation:** `<modules>` groups projects so the Maven Reactor builds them together in one run.
- **Inheritance:** `<parent>` allows child POMs to inherit properties, dependency management, plugin management, and shared configuration.

A POM can act as both an aggregator and a parent, but these are not the same mechanism. A child can inherit from a parent without being built by an aggregator; an aggregator can also include modules that do not directly inherit from it.

Only actual dependencies in a module create dependency relationships for the Reactor to order. Declaring coordinates in `dependencyManagement` or `pluginManagement` does not automatically create a dependency or build order.

### Project Structure

~~~text
shop-platform/
├── pom.xml
├── domain/
│   ├── pom.xml
│   └── src/main/java/
└── application/
    ├── pom.xml
    └── src/main/java/
~~~

### Parent/Aggregator POM

Root `pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.acme.platform</groupId>
    <artifactId>shop-platform</artifactId>
    <version>1.0.0</version>
    <packaging>pom</packaging>

    <modules>
        <module>domain</module>
        <module>application</module>
    </modules>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencyManagement>
        <dependencies>
            <dependency>
                <groupId>com.acme.platform</groupId>
                <artifactId>domain</artifactId>
                <version>1.0.0</version>
            </dependency>
        </dependencies>
    </dependencyManagement>
</project>
~~~

`packaging` is `pom` because the root POM is used to manage/aggregate modules. It does not produce `shop-platform-1.0.0.jar`.

`<modules>` declares the module directories. `dependencyManagement` manages dependency versions, but does not automatically make a module a dependency; consumer modules must still declare the actual dependency.

### Domain Module POM

File `domain/pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>com.acme.platform</groupId>
        <artifactId>shop-platform</artifactId>
        <version>1.0.0</version>
        <relativePath>../pom.xml</relativePath>
    </parent>

    <artifactId>domain</artifactId>
    <packaging>jar</packaging>
</project>
~~~

Maven inherits `groupId`, version, and properties from the parent. This module has `jar` packaging, so the lifecycle produces `domain-1.0.0.jar`.

### Application Module POM

File `application/pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>com.acme.platform</groupId>
        <artifactId>shop-platform</artifactId>
        <version>1.0.0</version>
        <relativePath>../pom.xml</relativePath>
    </parent>

    <artifactId>application</artifactId>
    <packaging>jar</packaging>

    <dependencies>
        <dependency>
            <groupId>com.acme.platform</groupId>
            <artifactId>domain</artifactId>
        </dependency>
    </dependencies>
</project>
~~~

The version of the `domain` dependency is taken from the parent's `dependencyManagement`. Because this is an actual dependency, the Reactor can order `domain` before `application`.

### Running the Maven Reactor

From the root directory:

~~~bash
./mvnw clean verify
~~~

Maven builds the declared modules in dependency order. Once the build succeeds, verify:

~~~text
domain/target/domain-1.0.0.jar
application/target/application-1.0.0.jar
~~~

Build only the `application` module and the modules it depends on:

~~~bash
./mvnw -pl application -am verify
~~~

`-pl` selects the project; `-am` (also make) instructs Maven to also build dependency modules in the Reactor.

Select a module by artifactId:

~~~bash
./mvnw -pl :domain package
~~~

If the selected module depends on other modules in the reactor, use `-am` to build the required dependency modules.

Other options:

- `-amd`: build the selected module and modules that depend on it.
- `-rf`: resume the Reactor from a specified module after fixing an error.
- `-fae`: continue building other modules and report all failures at the end.
- `-N`: do not recurse into child modules.

The order of `<modules>` in the POM is used when there are no specific dependency relationships dictating another order. Do not rely on declaration order to mask missing dependencies.

## 6. Installing and Deploying Individual Modules in Maven

### Installing to the Local Repository

Run from the root:

~~~bash
./mvnw clean install
~~~

Maven runs the lifecycle up to `install` for each module. The artifacts and POMs are installed into the local repository for other builds on the same machine to use.

Example path:

~~~text
~/.m2/repository/com/acme/platform/domain/1.0.0/
~~~

Installing is useful when testing a separate consumer project or when projects are not built in the same Reactor. In a normal multi-module build, the Reactor can wire module dependencies directly without needing to install first.

### Deploying to a Remote Repository

A POM or parent POM can declare:

~~~xml
<distributionManagement>
    <repository>
        <id>internal-releases</id>
        <url>https://repo.example.com/releases</url>
    </repository>

    <snapshotRepository>
        <id>internal-snapshots</id>
        <url>https://repo.example.com/snapshots</url>
    </snapshotRepository>
</distributionManagement>
~~~

`id` must match the server entry in Maven `settings.xml`. Credentials should be supplied from a CI secret store or an equivalent security mechanism—never hardcode passwords in the POM or commit them to the repository.

Publish:

~~~bash
./mvnw clean deploy
~~~

The Maven Deploy Plugin deploys the artifact, POM, and attached artifacts. In a multi-module build, each module can deploy its publication according to the lifecycle.

### Deploying Only One Module

~~~bash
./mvnw -pl domain -am deploy
~~~

This command selects `domain` along with the modules it depends on. Omit `-am` if you have confirmed the module has no dependency modules that need to be built in the reactor.

### Releases and SNAPSHOTs

Maven typically distinguishes:

- Release version: for example `1.0.0`.
- Snapshot version: for example `1.1.0-SNAPSHOT`.

A snapshot represents a development build that can be updated prior to release. A Maven repository can store snapshots using timestamped versions and metadata pointing to the current snapshot.

Release artifacts should be treated as immutable: never overwrite the same release coordinates with different bytes. If the contents change, release a new version. This policy ensures consumers and caches do not resolve the same GAV and receive different contents.

## 7. How Gradle Multi-Project Builds Produce Artifacts

Gradle uses a root project and subprojects declared in `settings.gradle` or `settings.gradle.kts`.

### Project Structure

~~~text
shop-platform/
├── settings.gradle
├── build.gradle
├── domain/
│   └── build.gradle
└── application/
    └── build.gradle
~~~

### Declaring Subprojects

File `settings.gradle`:

~~~groovy
rootProject.name = 'shop-platform'

include 'domain', 'application'
~~~

The Gradle project paths for the two modules are `:domain` and `:application`.

### Domain Module

File `domain/build.gradle`:

~~~groovy
plugins {
    id 'java-library'
    id 'maven-publish'
}

group = 'com.acme.platform'
version = '1.0.0'

java {
    withSourcesJar()
    withJavadocJar()
}

publishing {
    publications {
        mavenJava(MavenPublication) {
            from components.java
        }
    }

    repositories {
        maven {
            name = 'localBuildRepo'
            url = layout.buildDirectory.dir('repo')
        }
    }
}
~~~

The Java Library plugin creates a Java component. `withSourcesJar()` and `withJavadocJar()` configure secondary artifacts for sources and Javadoc.

The Maven Publish plugin uses the component to determine which artifacts and dependency metadata to publish. The file-based repository in this example is for illustration only; production setups typically use an internal HTTPS repository or repository manager.

### Application Module

File `application/build.gradle`:

~~~groovy
plugins {
    id 'application'
}

group = 'com.acme.platform'
version = '1.0.0'

dependencies {
    implementation project(':domain')
}
~~~

`project(':domain')` is a project dependency. Gradle knows `application` needs the output of `domain`, so it creates task dependencies and places the appropriate outputs and transitive dependencies on the classpath.

This is a dependency between subprojects within the same build. It is not a published Maven coordinate.

### Building a Module Artifact

Build the domain JAR:

~~~bash
./gradlew :domain:jar
~~~

Default artifact:

~~~text
domain/build/libs/domain-1.0.0.jar
~~~

Run a full project build:

~~~bash
./gradlew build
~~~

List projects:

~~~bash
./gradlew projects
~~~

View module tasks:

~~~bash
./gradlew :domain:tasks --all
~~~

A fully qualified task name consists of the project path and task name. For example, `:domain:jar` specifies the exact module to build, avoiding confusion with the `jar` task of other modules.

## 8. Publishing Modules with the Gradle Maven Publish Plugin

Gradle can publish a Java component as a Maven publication.

In the `domain/build.gradle` example, the publication is named `mavenJava` and the repository is named `localBuildRepo`. Gradle generates publish tasks based on the publication/repository names:

~~~bash
./gradlew :domain:generatePomFileForMavenJavaPublication
./gradlew :domain:publishMavenJavaPublicationToLocalBuildRepoRepository
~~~

Publish all configured publications in the project:

~~~bash
./gradlew :domain:publish
~~~

Publish to the local Maven repository:

~~~bash
./gradlew :domain:publishToMavenLocal
~~~

`publishToMavenLocal` places the artifact and metadata into the local Maven cache. It is not a remote release.

### Publication Identity

A Gradle `MavenPublication` has the following identity fields:

- `groupId`
- `artifactId`
- `version`

By default, these are taken from `project.group`, `project.name`, and `project.version`. They can be overridden individually in the publication if naming policies require something different from the project name.

For example:

~~~groovy
publishing {
    publications {
        mavenJava(MavenPublication) {
            from components.java
            groupId = 'com.acme.platform'
            artifactId = 'domain'
            version = '1.0.0'
        }
    }
}
~~~

Ensure that consumer dependency declarations match the actual publication coordinates. Renaming a project or overriding `artifactId` can make published coordinates differ from the directory name.

### Publishing to a Remote Repository

You can replace the file repository with an HTTPS repository:

~~~groovy
publishing {
    repositories {
        maven {
            name = 'internalReleases'
            url = uri('https://repo.example.com/releases')
            credentials(PasswordCredentials)
        }
    }
}
~~~

Gradle can obtain credentials from Gradle properties or environment variables according to your pipeline's security mechanism. Never commit real usernames/passwords into build scripts. Configure the appropriate credentials before invoking a remote publish task.

Specific publish task:

~~~bash
./gradlew :domain:publishMavenJavaPublicationToInternalReleasesRepository
~~~

The task name is derived from the publication name and repository name. Run `./gradlew :domain:tasks --all` to confirm the actual task name after configuration.

## 9. Project Dependencies vs. Published Artifact Dependencies

There are two ways for one module to use code from another module.

### Project Dependency Within the Same Gradle Build

~~~groovy
dependencies {
    implementation project(':domain')
}
~~~

Gradle knows the producer project, task graph, and variants. It can consume the output of a project dependency without needing to publish a JAR to a repository first.

### External Module Dependency

Once the artifact has been published:

~~~groovy
dependencies {
    implementation 'com.acme.platform:domain:1.0.0'
}
~~~

The consumer resolves the coordinates from the configured repository.

### Maven Dependency Within the Same Reactor

~~~xml
<dependency>
    <groupId>com.acme.platform</groupId>
    <artifactId>domain</artifactId>
    <version>1.0.0</version>
</dependency>
~~~

If both `domain` and `application` are in the Maven Reactor and the dependency is declared properly, Maven builds the dependency module first. If building the consumer separately outside the Reactor, the dependency must already be available in the local or remote repository.

### Comparison

| Criterion | Project dependency | Published artifact dependency |
|---|---|---|
| Scope | Same build | Can span different repositories/builds |
| Identifier | Project path | Artifact coordinates |
| Build order | Build tool constructs task graph/reactor automatically | Consumer resolves an already-existing artifact |
| Metadata | Build model/variants within the build | POM and/or Gradle Module Metadata |
| Best suited for | Modules developed together | Modules shared across multiple projects/teams |

You do not need to publish every time you want to test a module dependency within the same Gradle build or Maven Reactor. Publishing is required when external consumers outside the build need to fetch the artifact through a repository.

## 10. Inter-Module Dependencies and API Boundaries

A module artifact should accurately expose only the API that consumers are allowed to use.

With the Gradle Java Library plugin:

- `api` declares dependencies required on the consumer's compile classpath because the module's public API exposes types from those dependencies.
- `implementation` keeps dependencies internal on the implementation/runtime side when consumers do not need those dependencies to compile against the public API.

For example:

~~~groovy
plugins {
    id 'java-library'
}

dependencies {
    api 'org.example:public-contract:2.0.0'
    implementation 'org.example:internal-engine:3.1.0'
}
~~~

Overusing `api` enlarges the consumer's dependency graph and can cause implementation changes to affect many modules. Use `implementation` when a dependency is strictly internal to the module.

Maven uses dependency scopes such as `compile`, `provided`, `runtime`, `test`, and `system` to describe how dependencies are used and propagated via the POM. Maven does not have an `api`/`implementation` pair like the Gradle Java Library plugin; when published, the POM expresses dependencies and scopes according to the Maven model.

### Avoiding Dependency Cycles

If `domain` depends on `application` while `application` also depends on `domain`, the build graph has a cycle or the module architecture is inverted.

How to handle this:

1. Extract shared contracts into a smaller module.
2. Have implementations depend on the contract.
3. Avoid letting lower-level modules depend on orchestration modules.
4. Inspect the dependency graph rather than relying solely on directory order.
5. Split modules when responsibility boundaries are stable.

## 11. POM, Gradle Module Metadata, and Publication Metadata

An artifact JAR contains classes/resources. Consumers also need metadata to know how to resolve the artifact and its dependencies.

### Maven POM

A POM publication can describe:

- `groupId`, `artifactId`, `version`.
- Packaging/type.
- Dependencies and scopes.
- Parent/BOM or dependency management as configured.
- Name, description, URL, licenses, developers, and SCM metadata.
- Relocation when coordinates change.

If only a JAR file is uploaded without an appropriate POM, Maven consumers may lack dependency metadata and not know which additional artifacts the library requires.

### Gradle Module Metadata

Gradle can publish a `.module` file alongside the Maven POM. This metadata describes component variants, capabilities, and attributes in greater detail than a Maven POM.

For example, a single component can have:

- An API variant.
- A Runtime variant.
- A Sources variant.
- A Javadoc variant.
- Platform/attribute-specific variants.

Gradle consumers can use this metadata to select the appropriate variant. Maven consumers rely primarily on the POM and artifact conventions.

### Metadata Must Match the Artifact

If a POM declares wrong dependency versions, or Gradle metadata points to a nonexistent artifact/variant, the JAR might download, but consumers will still fail at resolution or runtime.

After publishing, verify the generated POM and `.module` files, confirm that identity/version and dependency lists are correct, and ensure artifact URLs are actually downloadable.

## 12. Main Artifacts, Attached Artifacts, and Classifiers

A module typically has one main artifact and may have secondary artifacts.

For example:

~~~text
domain-1.0.0.jar
domain-1.0.0.pom
domain-1.0.0-sources.jar
domain-1.0.0-javadoc.jar
domain-1.0.0-tests.jar
~~~

Purpose:

| Artifact | Purpose |
|---|---|
| Main JAR | Production classes/resources |
| POM | Metadata for Maven dependency resolution |
| Sources JAR | Source code for IDE/developer reference |
| Javadoc JAR | API documentation |
| Tests JAR | Test utilities if the module explicitly exports them |
| SBOM | List of components/dependencies |
| Signature/checksum | Integrity/authenticity verification |

Maven can attach secondary artifacts with classifiers. For example, the Sources and Javadoc plugins typically generate artifacts with their corresponding classifiers.

The Gradle Java plugin supports `withSourcesJar()` and `withJavadocJar()`. When a publication is created from `components.java`, these artifacts can be included in the publication according to plugin configuration.

Do not publish test outputs or internal content not meant for consumers just because files were generated in the build directory. Select publications explicitly and review their contents before release.

## 13. Versioning and Compatibility Between Module Artifacts

A module version is part of the contract with consumers.

For example:

~~~text
com.acme.platform:domain:1.0.0
com.acme.platform:persistence:1.0.0
com.acme.platform:application:1.0.0
~~~

A multi-module release can use a shared version to indicate that the modules are released in sync. Modules can also be versioned independently if they have separate release lifecycles.

### SemVer and API Compatibility

With Semantic Versioning:

- MAJOR: incompatible API changes.
- MINOR: backward-compatible feature additions.
- PATCH: backward-compatible bug fixes.

This is a versioning policy, not an automatic behavior of Maven/Gradle. Build tools do not automatically verify that a module actually adheres to SemVer.

If `application` requires a specific version of `domain`, manage dependency versions centrally using a Maven BOM/parent or a Gradle version catalog/platform when appropriate.

### Synchronized Releases

Use a shared version when:

- Modules are always released together.
- Internal APIs change in lockstep.
- Consumers need a set of modules tested together for compatibility.

### Independent Releases

Use independent versions when:

- Modules have separate consumers and release schedules.
- API boundaries are stable.
- Changing one module does not force other modules to release.
- The team has a clear compatibility testing process.

Do not version independently just to reduce build counts if dependency compatibility is not yet under control.

## 14. SNAPSHOTs and Release Repositories

Snapshots are suitable for development integration. Release repositories are for released versions.

A common policy:

| Type | Example | Policy |
|---|---|---|
| Snapshot | `1.2.0-SNAPSHOT` | Can be updated during development |
| Release | `1.2.0` | Immutable, never overwritten |
| Candidate | `1.2.0-rc.1` | Pre-release according to team policy |

Maven `distributionManagement` can declare separate repositories for releases and snapshots. Gradle publishing can likewise declare corresponding target repositories.

Never point a release version to an artifact that changes over time. If you need to fix a released artifact, create a new version and update consumers.

### Snapshot Caches and Stale Artifacts

Consumers may cache snapshot metadata or artifacts. If a snapshot is updated but the consumer still uses an old cached copy, behavior may differ from expectations.

When debugging, check:

- Snapshot metadata in the repository.
- The local repository cache.
- The timestamp when the artifact was published.
- Dependency refresh policies.
- Whether the build is resolving from the right repository.

Gradle can refresh dependencies:

~~~bash
./gradlew --refresh-dependencies
~~~

Maven can update snapshots according to its update policy or using the corresponding update flags. Clear caches only after understanding the root cause; avoid using the local cache as proof that a release artifact is valid.

## 15. Publishing and Resolving Artifacts in CI/CD

A module release pipeline typically includes these steps:

1. Check out a specific source revision.
2. Build and test the modules to be released.
3. Verify dependencies and versions.
4. Produce the main artifact and attached artifacts.
5. Inspect POM/Gradle metadata.
6. Compute checksums and sign artifacts if required by policy.
7. Publish to a staging/release repository.
8. Verify that the artifact can be resolved from the target repository.
9. Promote or release according to repository workflow.
10. Store manifests, SBOMs, and provenance.

### Do Not Publish When Build/Tests Fail

Publish tasks must depend on mandatory quality gates. In Maven, invoke the appropriate lifecycle up to `deploy` after tests and verification pass. In Gradle, the publish pipeline should depend on build/verification tasks according to project policy.

Do not run a standalone publish task if it does not ensure that build/tests have executed. A publish task might simply upload whatever output already exists.

### Staging Before Release

If the repository supports staging:

- Publish to a staging repository.
- Resolve the artifact from staging using a consumer test.
- Verify coordinates, POM, checksums, and signatures.
- Promote staging to release once validation passes.

Staging reduces the risk of pushing a broken artifact to an immutable release repository.

### Credentials

- Use the CI secret store.
- Grant the minimum deploy permissions required.
- Separate read credentials from publish credentials.
- Do not log tokens/passwords.
- Do not commit `settings.xml` containing secrets or Gradle properties containing credentials.
- Rotate credentials according to policy.

## 16. Inspecting Artifacts After Creation

Do not trust the build's exit code alone. Verify the actual files.

### Checking Files and Sizes

Linux/macOS:

~~~bash
find domain/target -maxdepth 1 -type f -print
ls -lh domain/target/domain-1.0.0.jar
~~~

Gradle:

~~~bash
find domain/build/libs -maxdepth 1 -type f -print
ls -lh domain/build/libs/domain-1.0.0.jar
~~~

Windows PowerShell:

~~~powershell
Get-ChildItem domain\target -File
Get-Item domain\target\domain-1.0.0.jar | Select-Object Name, Length
~~~

### Listing JAR Contents

~~~bash
jar --list --file domain-1.0.0.jar
~~~

Verify:

- Expected packages/classes are present.
- Required resources are present.
- No unintended local files, secrets, or test-only outputs are included.
- The manifest has the right metadata.
- The module descriptor is present if the project uses JPMS.

### Inspecting the Manifest

~~~bash
unzip -p domain-1.0.0.jar META-INF/MANIFEST.MF
~~~

If `unzip` is unavailable, you can use `jar --extract` in a temporary directory and read the manifest file.

### Computing Checksums

Linux:

~~~bash
sha256sum domain-1.0.0.jar
~~~

Windows PowerShell:

~~~powershell
Get-FileHash domain-1.0.0.jar -Algorithm SHA256
~~~

Checksums are used to compare bytes. They do not by themselves prove a trusted publisher; signatures or provenance are required depending on security requirements.

## 17. Testing Module Artifacts with an Independent Consumer

An artifact is only valuable if a consumer can resolve and use it.

Create a minimal consumer project, configure the right repository and dependency coordinates, and run:

~~~bash
./mvnw clean verify
~~~

or:

~~~bash
./gradlew clean test
~~~

A consumer test should verify:

- The artifact resolves from the target repository.
- POM/Gradle metadata is downloaded.
- Transitive dependencies are complete.
- Public classes/APIs compile.
- The runtime classpath has all required dependencies.
- The correct version is selected.
- It does not depend on files in the producer's workspace.
- It does not accidentally pick up an old artifact from the local cache.

To test remote publication, use a clean workspace or a fresh repository cache. If the consumer only passes after the producer runs `install` on the same machine, the consumer may be pulling the artifact from the local repository instead of the remote repository.

## 18. JPMS Modular JARs as a Special Case

The Java Platform Module System (JPMS) was introduced in Java 9. A modular JAR contains a compiled module descriptor at `module-info.class`.

Source descriptor:

~~~java
module com.acme.platform.domain {
    exports com.acme.platform.domain;
}
~~~

The source file typically resides at:

~~~text
src/main/java/module-info.java
~~~

When compiled, the descriptor becomes:

~~~text
module-info.class
~~~

In a modular JAR, `module-info.class` is located at the root of the archive (or in a version-specific location for multi-release JARs).

### What Does the Descriptor Control?

| Directive | Meaning |
|---|---|
| `requires` | This module needs another module |
| `exports` | Package is exposed publicly to other modules |
| `opens` | Package is opened for reflection |
| `uses` | Module uses a service |
| `provides ... with ...` | Module provides an implementation for a service |

For example:

~~~java
module com.acme.platform.application {
    requires com.acme.platform.domain;
}
~~~

The module descriptor defines module relationships at compile time and runtime. Maven coordinates are still used to locate the artifact file in a repository. The JPMS module name is used on the module path to resolve the module graph.

### JARs Without `module-info`

A JAR without a module descriptor can still be placed on the module path as an automatic module. Its module name can be taken from the `Automatic-Module-Name` manifest attribute or derived from the JAR filename.

For public libraries, declaring a stable `Automatic-Module-Name` helps JPMS consumers use a consistent module name before the project transitions to a true modular JAR.

Do not rely long-term on a name derived from the filename, because renaming the artifact can change the module name.

### Classpath and Module Path

- The classpath uses the traditional class-loading model.
- The module path allows the JVM to resolve module descriptors, read `requires`, and enforce encapsulation.
- A modular JAR placed on the classpath is treated like a non-modular JAR.

Do not confuse a “module artifact” with a “JAR containing `module-info`”. A build module can publish a non-modular JAR; a JPMS module can be packaged in a JAR artifact and published under normal GAV coordinates.

### Inspecting the Module Descriptor

~~~bash
jar --describe-module --file domain-1.0.0.jar
~~~

This command displays the module name and descriptor recognized by the JDK. If the JAR has no descriptor, the output may describe an automatic module.

You can inspect module dependencies with `jdeps`:

~~~bash
jdeps --check com.acme.platform.domain --module-path libs
~~~

Replace the module name and module path with your project's actual values. `jdeps` helps analyze dependencies at the class/module level; it does not replace integration tests.

## 19. Multi-Release JARs and Platform-Specific Artifacts

A module sometimes needs to distribute different code depending on the Java runtime version or OS/architecture.

### Multi-Release JARs

A multi-release JAR contains base classes along with alternative implementations per Java release under:

~~~text
META-INF/versions/9/
META-INF/versions/17/
~~~

The manifest must include the attribute:

~~~text
Multi-Release: true
~~~

A single JAR file can supply classes matching the runtime version. This represents multiple implementations inside one artifact, not multiple Maven/Gradle build modules.

### Platform-Specific Artifacts

A library with native components can publish separate artifacts by classifier or distinct coordinates:

~~~text
native-engine-1.0.0-linux-x86_64.jar
native-engine-1.0.0-windows-x86_64.jar
native-engine-1.0.0-macos-aarch64.jar
~~~

Choose a consistent convention so consumers know which platform to resolve. In Gradle, variant attributes can model platform selection more cleanly than plain classifiers.

Do not use arbitrary classifiers if metadata does not describe how consumers should pick the right artifact. Always test on each supported OS/architecture.

## 20. Managing Artifact Coordinate Changes

Once published, artifact coordinates become a contract with consumers. Changing `groupId` or `artifactId` can break resolution for existing dependencies.

When changing coordinates:

1. Choose the new coordinates and version policy.
2. Publish the new artifact.
3. If using a Maven repository, consider a relocation POM at the old coordinates.
4. Update consumers.
5. Document migration notes and the support window for the old coordinates.
6. Do not delete old artifacts if consumers still need to resolve them.

Maven relocation allows a POM at the old coordinates to point to the new coordinates. It helps repository browsers and build tools inform users that the artifact has moved.

Do not change `artifactId` just to rename a directory without a consumer migration plan.

## 21. Artifact Integrity and Supply-Chain Metadata

Artifacts shared via repositories need appropriate verification mechanisms.

Types of evidence:

| Evidence | Purpose |
|---|---|
| SHA-256/SHA-512 | Detect altered bytes |
| Signature | Verify the artifact was signed by a trusted key |
| POM/Gradle metadata | Describe identity, dependencies, and variants |
| SBOM | List components/dependencies contained in the artifact |
| Provenance/attestation | Record the source, workflow, and environment that produced the artifact |

Checksums published alongside an artifact help detect file corruption during download. To verify the publisher's identity, consumers need checksums/signatures obtained from a trusted source.

If signing artifacts, manage private keys in a CI secret/HSM or signing service. Never place private keys in the repository or build output.

Never modify an artifact after it has been signed or published. If bytes need to change, release a new version and regenerate checksums/signatures/attestations.

## 22. Common Issues and How to Fix Them

### Module Builds Successfully but No JAR Is Produced

**Cause:** The module uses `pom` packaging, the `package` phase has not run, or the artifact-producing task was not invoked.

**Fix:** Check packaging, build tasks, and output directories. In Maven, run `package`; in Gradle, run `:module:jar` or the corresponding task.

### Maven Reports Missing Dependency Module in the Same Repository

**Cause:** The module is not declared in the Reactor, dependency coordinates are wrong, or the consumer is built separately before the artifact is installed/published.

**Fix:** Check root `<modules>`, dependency GAV, and Reactor order; run from the root or use `-pl ... -am`; if building an independent consumer, install/publish the artifact first.

### Maven Reactor Builds in the Wrong Order or Skips a Module

**Cause:** Inter-module dependencies are not actually declared; entries exist only in `dependencyManagement` or `pluginManagement`.

**Fix:** Declare actual dependencies/plugins/extensions in the module that uses them; inspect the Reactor summary and use `-pl` and `-am`.

### Gradle Reports Project Path Does Not Exist

**Cause:** Missing `include` in settings, wrong project name, or wrong project path.

**Fix:** Run `./gradlew projects`; check `settings.gradle(.kts)`; use the full path such as `:domain`.

### Gradle Consumer Picks Up the Wrong Module Output

**Cause:** Using custom file dependencies or task-to-task dependencies instead of project dependencies/the variant model.

**Fix:** Use `implementation project(':domain')` or proper outgoing artifacts/variants; avoid hardcoding paths into `build/libs`.

### Local Artifact Differs from Remote Artifact

**Cause:** The local repository holds a stale artifact, the wrong version/repository was published, or an artifact was overwritten.

**Fix:** Compare SHA-256 hashes, coordinates, repository URLs, and metadata; use a clean consumer workspace; enforce an immutable release policy.

### Consumer Resolves the JAR but Misses Dependencies

**Cause:** The POM has no dependencies, the Gradle publication used the wrong component, or the artifact was uploaded manually without metadata.

**Fix:** Inspect the effective POM/Gradle Module Metadata; check the dependency tree; publish from the right component and test with an independent consumer.

### Sources/Javadoc JAR Does Not Appear

**Cause:** Source/Javadoc tasks are not configured, or the publication does not attach secondary artifacts.

**Fix:** In Maven, configure the Sources/Javadoc Plugins; in Gradle, use `withSourcesJar()` and `withJavadocJar()`; verify the publication file list before publishing.

### Publish Task Not Found

**Cause:** The Maven Publish Plugin is not applied, publications/repositories are not declared, or the task name is different.

**Fix:** Check plugins and the `publishing` block; run `./gradlew :module:tasks --all`; use the task name generated by Gradle.

### Maven Deploy Fails with 401/403

**Cause:** Server ID mismatch, wrong/expired credentials, or account lacks deploy permissions.

**Fix:** Match the `distributionManagement` ID with `settings.xml`; supply credentials from a secret store; verify repository permissions and URL. Never put passwords in the POM.

### Release Version Already Exists

**Cause:** The repository disallows overwriting releases, or the pipeline is attempting to republish the same GAV.

**Fix:** Verify the already-released artifact; if the bytes match, no republish is needed; if changes are required, bump the version and release a new version.

### Snapshot Resolves an Old Version

**Cause:** Local cache or snapshot metadata has not been refreshed.

**Fix:** Check metadata and the target repository; refresh dependencies; confirm the publish completed before the consumer resolves.

### JPMS Reports Module Not Found

**Cause:** The JAR is not on the module path, the module name differs from expectations, `module-info.class` is missing, or a dependency module is absent.

**Fix:** Use `jar --describe-module`; check `module-info.java`; verify the module path and `requires` names.

### JPMS Reports Package Is Not Exported/Opened

**Cause:** The module descriptor does not export the package to consumers, or a framework needs reflection without appropriate `opens`.

**Fix:** Export only public APIs; declare targeted `opens` when reflection is truly needed; do not arbitrarily open the entire module.

### Platform-Specific Artifact Selected Incorrectly

**Cause:** Classifier/variant does not match OS/architecture, or metadata does not declare selection criteria.

**Fix:** Check classifier/variant attributes and platform detection; test resolution on each supported platform.

## 23. Module Artifact Management Workflow

### When Developing a Module

1. Define the module's responsibility and public API.
2. Establish group/artifact/version conventions.
3. Declare dependencies according to module boundaries.
4. Build and test the module independently.
5. Inspect JAR contents, manifest, and metadata.
6. Check transitive dependencies and API exposure.
7. If using JPMS, verify the module descriptor separately.

### When Releasing

1. Finalize the release version.
2. Run build/tests from a clean checkout.
3. Produce the main artifact and required secondary artifacts.
4. Inspect POM/Gradle Module Metadata.
5. Compute checksums and sign artifacts per policy.
6. Publish to a staging/release repository.
7. Use an independent consumer project to resolve and test.
8. Promote the release and archive provenance/SBOM.
9. Never overwrite published release coordinates.

### When a Consumer Encounters an Error

1. Confirm dependency coordinates.
2. Confirm repository URL and credentials/read permissions.
3. Inspect POM/Gradle metadata.
4. Inspect the dependency graph and variant selection.
5. Check versions/caches.
6. Download the artifact and compare checksums.
7. Check the JPMS module name if using the module path.
8. Reproduce with a clean consumer build.

## 24. Pre-Publish Checklist for Module Artifacts

### Identity and Contents

- [ ] `groupId`, `artifactId`, and version follow conventions.
- [ ] Packaging/extension is appropriate.
- [ ] Main artifact contains required classes/resources.
- [ ] No secrets, local files, or unintended test outputs are included.
- [ ] Classifiers are used properly for secondary artifacts.
- [ ] JPMS descriptor is valid if the module is a modular JAR.

### Build and Dependencies

- [ ] Module is included in Maven Reactor/Gradle settings.
- [ ] Inter-module dependencies are properly declared.
- [ ] No unintended dependency cycles exist.
- [ ] Public API and transitive dependencies have been reviewed.
- [ ] Unit/integration tests pass.
- [ ] Dependency versions are managed consistently.

### Publication

- [ ] POM or Gradle Module Metadata is accurate.
- [ ] Sources/Javadoc are published if required by policy.
- [ ] Release and snapshot repositories are separated.
- [ ] Credentials are sourced from a secret store.
- [ ] Release versions are not overwritten.
- [ ] Checksums/signatures/provenance are generated per policy.

### Consumer Verification

- [ ] Artifact resolves from the target repository.
- [ ] Consumer compiles and passes tests.
- [ ] Transitive dependencies are complete.
- [ ] Artifact version/hash is correct.
- [ ] No reliance on a stale local repository.
- [ ] Migration/relocation is announced if coordinates changed.

## 25. Official References

- [Maven Artifacts](https://maven.apache.org/repositories/artifacts.html) — artifact coordinates, GAVCE, classifier, extension, and repository identity.
- [Guide to Working with Multiple Modules — Maven](https://maven.apache.org/guides/mini/guide-multiple-modules.html) — Maven Reactor, module collection, dependency order, and project selection.
- [Maven Install Plugin](https://maven.apache.org/plugins/maven-install-plugin/) — installing artifacts and POMs to the local repository.
- [Maven Deploy Plugin](https://maven.apache.org/plugins/maven-deploy-plugin/) — deploying artifacts, POMs, and attached artifacts to remote repositories.
- [Multi-Project Builds — Gradle](https://docs.gradle.org/current/userguide/multi_project_builds.html) — root project, subprojects, and inter-project dependencies.
- [The Maven Publish Plugin — Gradle](https://docs.gradle.org/current/userguide/publishing_maven.html) — publications, POMs, repositories, and publish tasks.
- [Publishing a Project as a Module — Gradle](https://docs.gradle.org/current/userguide/publishing_setup.html) — artifacts, Gradle Module Metadata, POMs, checksums, and signatures.
- [JAR File Specification — Java SE](https://docs.oracle.com/en/java/javase/26/docs/specs/jar/jar.html) — modular JARs, module descriptors, automatic modules, and multi-release JARs.
- [Introduction to Modules in Java — dev.java](https://dev.java/learn/modules/intro/) — module declarations, module path, and modular JARs.

A module artifact is the identifiable and distributable output of a build module. Manage identity, dependency metadata, versioning, repositories, and integrity alongside the JAR/ZIP file itself. Maven Reactor and Gradle multi-project builds help modules coordinate within the same build; publication enables external consumers to resolve artifacts through a repository. If a project uses JPMS, treat the module descriptor and module path as a separate layer alongside artifact coordinates.
