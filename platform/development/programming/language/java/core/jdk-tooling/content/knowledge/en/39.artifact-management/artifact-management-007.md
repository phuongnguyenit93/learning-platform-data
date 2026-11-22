# Gradle Repository Publishing: Publishing Java Artifacts to a Repository

## 1. What is repository publishing?

Repository publishing is the step of uploading built artifacts to a repository so that other projects, CI pipelines, or users can declare dependencies and download them by stable coordinates.

For Java libraries, the artifact is typically a JAR containing classes and resources. When publishing, the build also generates metadata describing the group, artifact, version, dependencies, license, developers, and usage variants. The repository can be a Maven repository, an Ivy repository, or Maven Local on a developer's machine.

Three activities should be distinguished:

- **Build:** compile sources, run verification tasks, and produce artifacts in the build directory.
- **Publish:** upload artifacts along with their metadata to the configured repository.
- **Resolve dependency:** a consuming project reads metadata from the repository, selects the appropriate variant, and downloads the artifact into its cache.

A JAR file sitting in `build/libs` does not automatically become a usable dependency from a repository. It needs to be published with appropriate coordinates and metadata.

## 2. Maven coordinates and repository layout

Maven identifies an artifact using three main components:

```text
groupId:artifactId:version
```

Example:

```text
com.example:greeter:1.2.0
```

| Component | Meaning | Example |
|---|---|---|
| groupId | Group or namespace of the library | com.example |
| artifactId | Name of the published module | greeter |
| version | Artifact version | 1.2.0 |

Gradle maps commonly used values:

- project.group → groupId.
- MavenPublication.artifactId → artifactId.
- project.version → version.

If no separate artifactId is assigned, Gradle usually uses the project name. You should explicitly set group and version in the build script to avoid publishing with unintended coordinates.

A Maven repository uses groupId to construct the directory path. Dots in groupId become forward slashes:

```text
com.example:greeter:1.2.0
→ com/example/greeter/1.2.0/
    greeter-1.2.0.jar
    greeter-1.2.0.pom
    greeter-1.2.0.module
    greeter-1.2.0-sources.jar
    greeter-1.2.0-javadoc.jar
```

The POM describes dependencies according to the Maven model. The `.module` file is Gradle Module Metadata, which can describe richer variants and attributes. Not every repository enables or serves all metadata types under the same policy; check the actual repository.

## 3. Gradle publishing plugins and publication model

Gradle has two commonly used built-in publishing plugins:

| Plugin | Publication | Repository |
|---|---|---|
| maven-publish | MavenPublication | Maven repository |
| ivy-publish | IvyPublication | Ivy repository |

To publish a Java library to a Maven repository:

```groovy
plugins {
    id 'java-library'
    id 'maven-publish'
}
```

The Java Plugin or Java Library Plugin provides the Java component. The Maven Publish Plugin creates the publication and the corresponding publish tasks.

A publication describes the artifacts to be published. A repository is the destination receiving the artifacts. Multiple publications or multiple repositories can be declared, but they must be managed carefully to avoid publishing the wrong version or to the wrong environment.

## 4. Publishing a Java component with from components.java

The most common way to publish a Java library is to take the component provided by the Java Plugin:

```groovy
publishing {
    publications {
        mavenJava(MavenPublication) {
            from components.java
        }
    }
}
```

`from components.java` brings the outputs and metadata of the Java component into the publication. Gradle knows the main artifact, dependencies, and variants created by the Java plugin.

Prefer publishing a component rather than manually creating a publication containing only a JAR file. If you only add the JAR manually, dependency metadata may be missing or fail to accurately reflect how consumers need to compile and run the library.

With the Java Library Plugin, the component can represent API dependencies and implementation dependencies separately. This is especially useful when the library is used by many other projects.

## 5. How the Java Plugin and Java Library Plugin affect metadata

Both `java` and `java-library` support compiling, packaging, and publishing a Java component. The Java Library Plugin adds clearer API conventions:

- `api`: a dependency that is part of the API consumers need to see at compile time.
- `implementation`: an internal dependency; it does not need to be exposed on the consumer's compile classpath, though it may be needed at runtime.

Example:

```groovy
plugins {
    id 'java-library'
}

dependencies {
    api 'org.example:public-api:2.0'
    implementation 'org.example:internal-helper:1.4'
}
```

When publishing a Maven POM, Gradle maps dependencies to the appropriate scopes. With Gradle Module Metadata, dependencies are attached to the corresponding variants such as apiElements and runtimeElements.

Choose `api` when public types of the library depend on types from that dependency, or when consumers must have the dependency to compile code calling the API. Use `implementation` for implementation details to keep the API clean and avoid exposing unnecessary dependencies.

Do not declare every dependency as api just to work around consumer compile errors; first inspect the public API and which dependencies genuinely need to be exposed.

## 6. Maven POM and Gradle Module Metadata

A Maven publication typically produces at least:

- The main JAR.
- The POM XML.
- Gradle Module Metadata with the `.module` extension if enabled.
- Sources/Javadoc JARs if the publication includes those artifacts.
- Checksum sidecars generated by the repository or Gradle.

The POM XML contains groupId, artifactId, version, name, description, URL, license, developers, SCM, and dependency scopes.

Gradle Module Metadata can describe:

- API and runtime variants.
- Java target compatibility.
- Usage and library elements.
- Dependency constraints.
- Sources and Javadoc variants.
- Artifact files along with checksums.

Common Java variants are apiElements, runtimeElements, sourcesElements, and javadocElements.

When Gradle reads a repository with properly published Gradle Module Metadata, Gradle typically prefers this metadata to select variants. Maven clients read the POM according to the Maven model. Therefore, both should be checked when a library serves both Maven and Gradle consumers.

Do not arbitrarily delete the `.module` file or the marker metadata in the POM. Doing so can cause Gradle consumers to lose variant information provided by the publisher.

## 7. Adding metadata to the POM

Metadata helps users identify the library and gives repositories sufficient information to manage the artifact.

```groovy
publishing {
    publications {
        mavenJava(MavenPublication) {
            from components.java

            pom {
                name = 'Greeter Library'
                description = 'A reusable greeting library.'
                url = 'https://example.org/greeter'

                licenses {
                    license {
                        name = 'Apache License, Version 2.0'
                        url = 'https://www.apache.org/licenses/LICENSE-2.0.txt'
                        distribution = 'repo'
                    }
                }

                developers {
                    developer {
                        id = 'example-maintainers'
                        name = 'Example Maintainers'
                    }
                }

                scm {
                    connection = 'scm:git:https://example.org/greeter.git'
                    url = 'https://example.org/greeter'
                }
            }
        }
    }
}
```

Replace the example values with the library's actual information before publishing. The license must match the actual license of the source and binary. Do not declare an inaccurate license, developer, SCM, or URL just to make the POM look complete.

Use the typed pom DSL for standard fields. Only manipulate XML directly via withXml when you need extension fields not supported by the DSL and you understand the impact on consumers.

## 8. Sources JAR and Javadoc JAR

Public libraries should generally publish source and API documentation so that IDEs and users can inspect them.

Enable both artifacts via the Java extension:

```groovy
java {
    withSourcesJar()
    withJavadocJar()
}
```

When the publication is derived from components.java, Gradle automatically attaches the sources JAR and Javadoc JAR to the publication. There is no need to manually create separate publications for each file.

Example artifacts:

```text
greeter-1.2.0.jar
greeter-1.2.0-sources.jar
greeter-1.2.0-javadoc.jar
```

The sources JAR typically contains the sources from the main source set. The Javadoc JAR contains API documentation generated from Javadoc comments and public classes.

Before publishing, verify that the Javadoc task runs cleanly. Add @param, @return, and @throws tags for public APIs to make the documentation useful and avoid warnings. If the project has multiple source sets or variants, explicitly check which artifacts are included in the publication.

## 9. Adding custom artifacts

A publication can contain additional artifacts such as schemas, API specifications, distribution archives, or special documentation.

Configuration example:

```groovy
publishing {
    publications {
        mavenJava(MavenPublication) {
            from components.java

            artifact(tasks.apiDocsZip) {
                classifier = 'api-docs'
                extension = 'zip'
            }
        }
    }
}
```

The apiDocsZip task must actually produce an output file and have its task dependency wired to the publication. The classifier distinguishes the secondary artifact from the main JAR; the extension indicates the file format.

Do not publish the same file twice with the same classifier and extension. Before adding an artifact, check whether it genuinely needs to be downloaded via Maven coordinates or should be distributed through a separate channel.

## 10. Declaring the target Maven repository

Repositories are configured inside publishing.repositories:

```groovy
publishing {
    repositories {
        maven {
            name = 'test'
            url = layout.buildDirectory.dir('test-maven-repo')
        }
    }
}
```

This is a local repository inside the build directory, suitable for testing. When publishing succeeds, Gradle creates the Maven layout by groupId, artifactId, and version.

Remote repositories typically use HTTPS:

```groovy
publishing {
    repositories {
        maven {
            name = 'internalReleases'
            url = uri('https://repo.example.org/releases')
        }
    }
}
```

The URL must point to the publish endpoint of a repository manager, such as Nexus, Artifactory, or your organization's Maven repository service. The dependency download endpoint may differ from the upload endpoint; use the exact URL provided by your repository administrator.

A repository can be a release or snapshot repository. Do not point a production publication to a local build directory or test endpoint just because the publish task succeeds.

## 11. Managing credentials and secrets

Never write usernames, passwords, access tokens, or private keys directly in build.gradle, the POM, or the repository.

Gradle supports PasswordCredentials:

```groovy
publishing {
    repositories {
        maven {
            name = 'internalReleases'
            url = uri('https://repo.example.org/releases')
            credentials(PasswordCredentials)
        }
    }
}
```

For a repository named internalReleases, Gradle can read the following project properties:

```properties
internalReleasesUsername=publisher
internalReleasesPassword=secret-value
```

You can place these values in a gradle.properties file in Gradle User Home without committing them to the source repository. In CI, inject them from a secret store and map them to project properties via environment variables:

```text
ORG_GRADLE_PROJECT_internalReleasesUsername
ORG_GRADLE_PROJECT_internalReleasesPassword
```

Restrict the permissions of the publishing account to the specific repository and artifact types it needs to publish. Use dedicated tokens for CI, rotate them when needed, and avoid printing credentials in logs. Always require HTTPS for remote repositories to protect credentials in transit.


## 12. Release and snapshot versions

Maven distinguishes between release versions and snapshot versions.

| Type | Example | Usage |
|---|---|---|
| Release | 1.2.0 | Stable release |
| Snapshot | 1.3.0-SNAPSHOT | Development build that can be updated |

A snapshot repository typically manages metadata to identify the latest snapshot build, which may map a SNAPSHOT version to timestamped snapshot files. A release repository usually enforces an immutable version policy: an already published release should not be overwritten with a different binary.

You can select the endpoint based on the version:

```groovy
def snapshotBuild = project.version.toString().endsWith('-SNAPSHOT')
def targetUrl = snapshotBuild
    ? 'https://repo.example.org/snapshots'
    : 'https://repo.example.org/releases'

publishing {
    repositories {
        maven {
            name = 'internal'
            url = uri(targetUrl)
            credentials(PasswordCredentials)
        }
    }
}
```

Set the version properly before publishing. Do not reuse the same release version for a different binary; increment the version when the published content changes. Clean up old snapshots according to your repository manager's retention policy to prevent repository bloat.

## 13. Common publishing tasks

The Maven Publish Plugin generates tasks based on the publication and repository names.

| Task | Purpose |
|---|---|
| generatePomFileForMavenJavaPublication | Generates the POM |
| generateMetadataFileForMavenJavaPublication | Generates Gradle Module Metadata |
| publishMavenJavaPublicationToTestRepository | Publishes the mavenJava publication to the test repository |
| publish | Runs publish tasks to all configured repositories |
| publishToMavenLocal | Publishes Maven publications to the local Maven cache |

The exact task names depend on the publication and repository names. For example, a publication named mavenJava and a repository named internalReleases will generate tasks corresponding to those two names.

Run:

```bash
./gradlew tasks --all
./gradlew generatePomFileForMavenJavaPublication
./gradlew publishToMavenLocal
./gradlew publish
```

publishToMavenLocal writes to the local Maven repository on the development machine, typically `~/.m2/repository`. It does not upload artifacts to a remote repository and does not replace an official release publish.

The publish task should not be treated as an automated testing step. Run check and verify the artifacts before running publish to a shared repository.

## 14. Inspecting the publication before uploading

After generating the publication, inspect its contents before releasing:

1. Verify groupId, artifactId, and version.
2. Open the POM to confirm metadata, license, SCM, and dependency scopes.
3. Inspect the `.module` file to review variants and artifact files.
4. List the JAR contents using jar --list.
5. Inspect the sources and Javadoc JARs.
6. Compute SHA-256 and compare against the checksum sidecar if provided by the repository.
7. Ensure there are no artifacts with duplicate classifiers or wrong versions.
8. Try resolving the dependency from a separate consumer project.

Useful commands:

```bash
jar --list --file build/libs/greeter-1.2.0.jar
jar --validate --file build/libs/greeter-1.2.0.jar
sha256sum build/libs/greeter-1.2.0.jar
```

On Windows PowerShell:

```powershell
Get-FileHash -Algorithm SHA256 ./build/libs/greeter-1.2.0.jar
```

Validate the POM with an XML parser and the `.module` file with a JSON parser. The mere existence of a file does not mean the metadata is valid or that the dependency can be resolved by consumers.

## 15. Testing a consumer from a local repository

A reliable way to test is to create a separate project that only knows the dependency coordinates and the published repository.

Example:

```groovy
plugins {
    id 'application'
}

repositories {
    maven {
        url = uri('../greeter-library/build/test-maven-repo')
    }
}

dependencies {
    implementation 'com.example:greeter:1.2.0'
}

application {
    mainClass = 'consumer.Main'
}
```

Consumer source:

```java
package consumer;

import com.example.greeter.Greeter;

public class Main {
    public static void main(String[] args) {
        System.out.println(Greeter.greet("Repository"));
    }
}
```

Run the consumer:

```bash
./gradlew clean run
```

Expected stdout:

```text
Hello, Repository!
```

The consumer project must resolve the artifact from the published local repository rather than pulling classes directly from the source project. This confirms that the coordinates, POM/Gradle metadata, and JAR are usable outside the producer module.

To test the Maven POM compatibility path, configure metadataSources on the Gradle consumer:

```groovy
repositories {
    maven {
        url = uri('../greeter-library/build/test-maven-repo')
        metadataSources {
            mavenPom()
            artifact()
        }
    }
}
```

This configuration instructs the consumer to use the POM and artifact. Testing both the default Gradle Module Metadata path and the POM-only path helps catch metadata differences between different types of consumers.

## 16. Local repository, Maven Local, and test repository

There are three common approaches during development:

- Repository in the build directory: easy to delete, isolated per project, and suitable for testing publications.
- Maven Local: uses the publishToMavenLocal task; artifacts are saved to the developer's local Maven cache.
- Remote repository: a shared repository for the team or pipeline.

Do not rely on Maven Local to prove that an artifact has been properly published to a remote repository. The local cache may hold an older version, causing a consumer to resolve the artifact even if the new publish failed.

When testing, prefer a dedicated repository in the build directory and an independent consumer project. When verifying a remote repository, use the actual URL and confirm that the downloaded artifact's checksum matches the built artifact.

If you need to delete an old local version, identify the exact coordinates and directory before deleting; avoid wiping the entire Maven cache as that forces all projects to re-download dependencies.

## 17. Dependency metadata and version mapping

A publication must accurately describe dependencies according to how the library is resolved.

With java-library:

- api dependencies may be needed on the consumer's compile classpath.
- implementation dependencies are only needed internally when compiling the producer, but may be needed at runtime.
- runtimeOnly dependencies are only needed at runtime.
- compileOnly dependencies should not automatically be treated as runtime dependencies.

Gradle Module Metadata preserves detailed variants. A Maven POM uses scopes such as compile, runtime, and other Maven scopes. Because the two systems have different models, inspect the generated POM when the library has complex dependencies.

If versions are resolved dynamically or you need to publish the resolved versions from a configuration, consider MavenPublication's versionMapping. Only add it when the project has a clear reason and you have verified the resulting POM; do not use it as a default configuration for every library.

## 18. Ivy publishing

If your organization's repository uses Ivy, apply the ivy-publish plugin and create an IvyPublication:

```groovy
plugins {
    id 'java-library'
    id 'ivy-publish'
}

publishing {
    publications {
        ivyJava(IvyPublication) {
            from components.java
        }
    }

    repositories {
        ivy {
            name = 'internalIvy'
            url = uri('https://repo.example.org/ivy')
        }
    }
}
```

An Ivy publication generates descriptors according to the Ivy model and uses the repository layout supported by the repository. Consumers must declare an appropriate Ivy repository to resolve it.

Do not mix MavenPublication and IvyPublication just to get an extra metadata file. Choose the publication type based on the actual repository and consumers.

## 19. Multi-project builds and multiple publications

In a multi-project build, each subproject can publish its own artifact with its own coordinates. Set group and version in a centralized place if the modules belong to the same release train, then specify artifactId for a module when the project name is not suitable.

A project can have multiple publications if there are genuinely multiple variants or formats to publish. Ensure each publication has distinct coordinates and classifiers, and do not create two publications that write the same file at the same version.

When publishing multiple modules with dependencies between them, check the release order and repository metadata so that consumers do not download a new module while missing its corresponding dependencies.

## 20. CI pipelines and release workflows

A release workflow may consist of:

1. Check out the exact commit and verify a clean working tree.
2. Use the Gradle Wrapper and a pinned JDK/toolchain.
3. Resolve dependencies with lockfiles and verification metadata.
4. Run clean, test, and check.
5. Build the JAR, sources JAR, and Javadoc JAR.
6. Inspect the POM, Gradle Module Metadata, and checksums.
7. Publish to a staging or test repository.
8. Use a consumer project to resolve and run the artifact.
9. Sign the artifacts if required by the release policy.
10. Promote or publish the release using granted CI permissions.
11. Record coordinates, checksums, commit, and build logs.

Arbitrary pull requests should not be allowed to publish directly to a release repository. Use dedicated CI permissions, approvals, or staging promotion according to your organization's policy. Snapshots can be published automatically in development pipelines; releases should be tied to a tag/version and a verification workflow.

If a publish partially fails, check the repository state before rerunning. Some repositories do not allow overwriting an existing release; blind retries can create inconsistent artifacts or cause the pipeline to fail repeatedly.

For released artifacts, use a clean and trusted CI environment. If the repository requires signatures, you can use the Signing Plugin to sign publications after building and verification are complete:

```groovy
plugins {
    id 'signing'
}

signing {
    sign publishing.publications.mavenJava
}
```

The private key and signing passphrase must be supplied from the CI secret store; never commit keys to the repository. Caching is useful for regular builds when configured properly; reproducibility tests should actively exclude stale state that could obscure the origin of results.

## 21. Common errors and troubleshooting

| Symptom | Common cause | Solution |
|---|---|---|
| No publish tasks available | maven-publish or ivy-publish is not applied | Check plugins in the build script |
| No publications found | publications block is not declared | Create a MavenPublication/IvyPublication |
| Artifact missing dependency metadata | JAR file published manually | Use from components.java |
| POM has wrong group/version | Project coordinates are not configured properly | Check group, artifactId, and version |
| Consumer cannot resolve artifact | Wrong repository URL or coordinates | Check layout and metadata |
| Consumer compile error for missing public type | Required dependency is declared as implementation | Review API dependencies and use api where appropriate |
| Consumer missing class at runtime | Missing runtime dependency or wrong scope | Check runtimeElements and POM scopes |
| Sources/Javadoc JAR missing | Artifact tasks are not enabled | Use withSourcesJar and withJavadocJar |
| Javadoc task fails | Invalid Javadoc comments or configuration | Fix warnings/errors and check the toolchain |
| HTTP 401/403 | Missing credentials or insufficient permissions | Check secrets, account, and repository permissions |
| HTTP 404 when publishing | URL points to the wrong endpoint | Use the correct deployment endpoint |
| HTTP 409 or version conflict | Release version already exists or is immutable | Increment the version or follow the repository workflow |
| Snapshot not updating as expected | Stale cache or snapshot metadata | Check repository metadata and refresh dependencies |
| Gradle selects an unintended variant | Incompatible metadata variant attributes | Inspect `.module`, Java target, and consumer attributes |
| Maven consumer does not see Gradle variants | Maven only reads the POM | Ensure the POM has the appropriate dependency scopes |
| Artifact in Maven Local differs from remote | Local cache holds an older version | Check checksums in the actual repository |
| Publish succeeds but CI did not run tests | publish does not automatically replace check | Run check before publish in the pipeline |

## 22. Complete example: publishing a library and using it from a consumer

The producer project has the following structure:

```text
greeter-library/
├── settings.gradle
├── build.gradle
└── src/
    └── main/
        └── java/
            └── com/
                └── example/
                    └── greeter/
                        └── Greeter.java
```

File settings.gradle:

```groovy
rootProject.name = 'greeter'
```

File build.gradle:

```groovy
plugins {
    id 'java-library'
    id 'maven-publish'
}

group = 'com.example'
version = '1.2.0'

java {
    withSourcesJar()
    withJavadocJar()
}

tasks.withType(JavaCompile).configureEach {
    options.release = 17
}

publishing {
    publications {
        mavenJava(MavenPublication) {
            from components.java

            pom {
                name = 'Greeter Library'
                description = 'A small reusable greeting library.'
                url = 'https://example.org/greeter'
            }
        }
    }

    repositories {
        maven {
            name = 'test'
            url = layout.buildDirectory.dir('test-maven-repo')
        }
    }
}
```

File src/main/java/com/example/greeter/Greeter.java:

```java
package com.example.greeter;

/** A small reusable greeting library. */
public final class Greeter {
    private Greeter() {
    }

    /**
     * Returns a greeting for the supplied name.
     * @param name recipient name; must not be blank
     * @return a greeting containing the recipient name
     * @throws IllegalArgumentException if the name is null or blank
     */
    public static String greet(String name) {
        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException("name must not be blank");
        }
        return "Hello, " + name + "!";
    }
}
```

Publish to the project's local repository:

```bash
./gradlew clean publish
```

The artifacts are placed under:

```text
build/test-maven-repo/com/example/greeter/1.2.0/
```

Key files:

```text
greeter-1.2.0.jar
greeter-1.2.0.pom
greeter-1.2.0.module
greeter-1.2.0-sources.jar
greeter-1.2.0-javadoc.jar
```

Consumer configuration:

```groovy
plugins {
    id 'application'
}

repositories {
    maven {
        url = uri('../greeter-library/build/test-maven-repo')
    }
}

dependencies {
    implementation 'com.example:greeter:1.2.0'
}

application {
    mainClass = 'consumer.Main'
}
```

File src/main/java/consumer/Main.java:

```java
package consumer;

import com.example.greeter.Greeter;

public class Main {
    public static void main(String[] args) {
        System.out.println(Greeter.greet("Repository"));
    }
}
```

Run the consumer:

```bash
./gradlew clean run
```

Exact stdout:

```text
Hello, Repository!
```

In testing on Gradle 9.2.1 and OpenJDK Zulu 24.0.2, the producer published the main JAR, sources JAR, Javadoc JAR, POM, and Gradle Module Metadata into an isolated repository. The POM XML and module JSON were parsed successfully; the JAR passed jar --validate and the SHA-256 sidecar checksums matched. The consumer resolved the dependency and printed Hello, Repository! when using default metadata, and also ran successfully when forced to use POM metadata.

## 23. Summary

Repository publishing turns build outputs into dependencies that other projects can resolve by stable coordinates.

Key points to remember:

- Use maven-publish for Maven repositories and ivy-publish for Ivy repositories.
- Prefer from components.java so the publication carries artifacts and dependency metadata.
- Set group, artifactId, and version explicitly.
- Use java-library to distinguish api and implementation dependencies.
- Verify both the Maven POM and Gradle Module Metadata.
- Enable withSourcesJar and withJavadocJar for libraries that need to distribute source/documentation.
- Use a local repository in the build directory to test publications before uploading.
- Never store credentials in source; inject them via Gradle properties or CI secrets.
- Keep release versions immutable; use snapshot versions for development builds.
- Run check, verify checksums, and test resolving from a consumer before releasing.
- Distinguish publishToMavenLocal from publishing to a remote repository.

**Official references:**

- [Gradle User Manual — Maven Publish Plugin](https://docs.gradle.org/current/userguide/publishing_maven.html)
- [Gradle DSL — MavenPublication](https://docs.gradle.org/current/dsl/org.gradle.api.publish.maven.MavenPublication.html)
- [Gradle DSL — MavenArtifactRepository](https://docs.gradle.org/current/dsl/org.gradle.api.artifacts.repositories.MavenArtifactRepository.html)
- [Gradle User Manual — Ivy Publish Plugin](https://docs.gradle.org/current/userguide/publishing_ivy.html)
- [Gradle User Manual — Java Library Plugin](https://docs.gradle.org/current/userguide/java_library_plugin.html)
- [Gradle User Manual — Publishing Java Libraries](https://docs.gradle.org/current/userguide/publishing_setup.html)
- [Gradle User Manual — Dependency Verification](https://docs.gradle.org/current/userguide/dependency_verification.html)
- [Apache Maven — POM Reference](https://maven.apache.org/pom.html)
- [Apache Maven — Introduction to Repositories](https://maven.apache.org/guides/introduction/introduction-to-repositories.html)
- [Gradle — Gradle Module Metadata](https://docs.gradle.org/current/userguide/publishing_gradle_module_metadata.html)
