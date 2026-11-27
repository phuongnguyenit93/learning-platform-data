# Mapping Java, Spring Boot, Release Trains, and Commons Versions

## 1. Why Build a Version Matrix?

Spring Cloud is released in release trains. Each train bundles a set of modules such as Spring Cloud Commons, Config, LoadBalancer, OpenFeign, Gateway, and Bus. Modules can have their own version numbers, while the release train BOM selects a set of versions that have been tested together.

When upgrading an application, you need to cross-check at least four axes:

1. **Java:** the JDK used to compile and run the application.
2. **Spring Boot:** the foundation that manages dependencies, auto-configuration, and lifecycle.
3. **Spring Cloud release train:** the Spring Cloud version set compatible with the Spring Boot generation.
4. **Spring Cloud Commons:** the specific artifact version containing common abstractions such as DiscoveryClient, ServiceRegistry, LoadBalancerClient, and RefreshScope.

These version numbers do not follow the same numbering scheme. For example, the Spring Cloud 2025.1.4 release train manages Spring Cloud Commons 5.0.4; it does not mean Commons has to carry the number 2025.1.4. The Spring Cloud BOM is what ties the modules in a train together.

This lesson belongs to the **Upgrades** chapter of the **SPRING_CLOUD_CORE** module. The module helps learners understand the core foundations of Spring Cloud in distributed systems, especially Spring Cloud Commons, Context, external configuration, and Spring Boot compatibility; learners also explore refresh scope, discovery, service registry, service-to-service communication, and testing and operating common abstractions.

After this lesson, learners can:

- Read the compatibility table across Java, Spring Boot, and Spring Cloud.
- Choose a release train based on the Spring Boot version in use.
- Look up the Spring Cloud Commons version managed by the BOM.
- Distinguish between GA releases, preview releases, and release trains that have reached end of OSS support.
- Configure Maven or Gradle using the Spring Cloud BOM.
- Verify the actual resolved dependency versions.
- Plan an upgrade when Java, Boot, or Cloud is no longer in the support matrix.

## 2. How to Read the Four Version Axes

### 2.1. Java Is the Baseline for Spring Boot

Spring Boot defines the minimum JDK and the compatible JDK range for each release line. For modern lines:

- Spring Boot 2.x has a Java 8 baseline.
- Spring Boot 3.x requires Java 17 or higher.
- Spring Boot 4.x requires Java 17 or higher.

Java 17 is the shared baseline for Boot 3 and Boot 4, but that does not mean every third-party dependency in an application supports every newer JDK. Check the requirements of drivers, agents, SDKs, and integration libraries.

The table in this lesson lists the **minimum JDK** to make environment selection straightforward. The maximum supported Java version can vary by Spring Boot minor/patch release; for example, Boot 3.5.16 and Boot 4.1.2 have different maximum Java limits. Do not infer that limit from the major version alone.

### 2.2. Spring Boot Determines the Compatible Release Train

Spring Cloud publishes a mapping table between release trains and Spring Boot generations. This is the starting point when selecting dependencies:

- Boot 4.0.x and Boot 4.1.x use Spring Cloud 2025.1.x; support for Boot 4.1.x starts in Spring Cloud 2025.1.2.
- Boot 3.5.x corresponds to Spring Cloud 2025.0.x.
- Boot 3.4.x corresponds to Spring Cloud 2024.0.x.
- Boot 3.2.x/3.3.x correspond to Spring Cloud 2023.0.x; Boot 3.3.x is supported starting from 2023.0.2.
- Boot 3.0.x/3.1.x correspond to Spring Cloud 2022.0.x; Boot 3.1.x is supported starting from 2022.0.3.
- Boot 2.6.x/2.7.x correspond to Spring Cloud 2021.0.x; Boot 2.7.x is supported starting from 2021.0.3.

Do not pick a release train merely because the version numbers look close. Use the official Spring Cloud mapping.

### 2.3. Commons Is Managed by the Release Train BOM

Spring Cloud Commons has its own versioning. The train BOM manages the Commons version alongside the other modules, for example:

| Spring Cloud release train | Spring Cloud Commons |
| --- | --- |
| 2025.1.x | 5.0.x |
| 2025.0.x | 4.3.x |
| 2024.0.x | 4.2.x |
| 2023.0.x | 4.1.x |
| 2022.0.x | 4.0.x |
| 2021.0.x | 3.1.x |
| 2020.0.x | 3.0.x |
| Hoxton | 2.2.x |
| Greenwich | 2.1.x |
| Finchley | 2.0.x |

The rows in the table show the **series** of the Commons module. The specific patch version is selected by the release train BOM; do not manually grab a patch version from another train and force it into the application.

## 3. Version Matrix as of 2026-11-18

| Spring Cloud train | Compatible Spring Boot | Minimum Java | Spring Cloud Commons | Status at time of lookup |
| --- | --- | --- | --- | --- |
| 2026.0.0-RC2 (Paddington) | 4.2.0-RC2 | 17 | 5.1.0-RC2 | Preview, not yet GA |
| 2025.1.4 (Oakwood) | 4.0.x; 4.1.x from 2025.1.2 | 17 | 5.0.4 | GA, latest stable train |
| 2025.0.3 (Northfields) | 3.5.15; belongs to Boot 3.5.x line | 17 | 4.3.3 | Final OSS release; OSS support ended 2026-06-30 |
| 2024.0.3 (Moorgate) | 3.4.12 | 17 | 4.2.4 | End of OSS support |
| 2023.0.6 (Leyton) | 3.3.13 | 17 | 4.1.6 | End of OSS support |
| 2022.0.5 (Kilburn) | 3.0.13; train supports 3.0.x/3.1.x | 17 | 4.0.5 | End of OSS support |
| 2021.0.x (Jubilee) | 2.6.x/2.7.x | 8 | 3.1.x | End of OSS support |
| 2020.0.x (Ilford) | 2.4.x/2.5.x | 8 | 3.0.x | End of OSS support |
| Hoxton | 2.2.x/2.3.x | 8 | 2.2.x | End of OSS support |
| Greenwich | 2.1.x | 8 | 2.1.x | End of OSS support |
| Finchley | 2.0.x | 8 | 2.0.x | End of OSS support |

### 3.1. Recommended Line for New Applications

As of 2026-11-18:

- **Latest GA:** Spring Cloud 2025.1.4, Spring Cloud Commons 5.0.4.
- **Latest stable Spring Boot:** Boot 4.1.2; train 2025.1.x supports Boot 4.1.x starting from 2025.1.2.
- **Minimum JDK:** Java 17 for Boot 4.x.
- **Next preview:** Spring Cloud 2026.0.0-RC2, Boot 4.2.0-RC2, Commons 5.1.0-RC2; use only for compatibility testing and upgrade preparation.

If you are starting a new Spring Cloud application, using Boot 4.1.x with Cloud 2025.1.x is the latest GA option in the verified matrix. You can use Boot 4.0.x with this train if the system needs to stay on the Boot 4.0 minor line.

### 3.2. Note on Spring Cloud 2025.0.x

Spring Cloud 2025.0.3 is the final OSS release of the 2025.0.x train. Spring announced that OSS support for this train ended on 2026-06-30. Therefore, even though Boot 3.5.x still has stable Spring Boot releases, you should not assume Spring Cloud 2025.0.x continues to receive OSS updates after its end-of-support date.

If the application still requires Boot 3.5.x, evaluate commercial support and plan the migration to Boot 4.x/Cloud 2025.1.x. Do not upgrade Commons alone to 5.x in an attempt to stay on Boot 3.5; that mixes two dependency generations.

### 3.3. Distinguishing GA and Preview

2026.0.0-RC2 is a release candidate. It was published against Boot 4.2.0-RC2 and Commons 5.1.0-RC2. These versions may change before GA; do not put them into production just because the version number is newer.

When documenting or creating a release manifest, preserve the `-M`, `-RC`, or `-SNAPSHOT` suffix. Do not strip the suffix to make a preview release look like a stable release.

## 4. Example of Selecting Versions for an Application

Suppose an application uses Java 17 and needs Spring Cloud LoadBalancer along with Commons abstractions. How to choose:

1. Choose Spring Boot 4.1.2.
2. Check the compatibility table: Boot 4.1.x uses Cloud 2025.1.x starting from 2025.1.2.
3. Choose the current GA train patch, Cloud 2025.1.4.
4. Let the BOM select Commons 5.0.4.
5. Do not declare individual versions for each Spring Cloud starter or Commons.

Application matrix:

| Component | Selected version |
| --- | --- |
| Java toolchain/runtime | 17 |
| Spring Boot | 4.1.2 |
| Spring Cloud release train BOM | 2025.1.4 |
| Spring Cloud Commons | 5.0.4, managed by the BOM |
| Spring Cloud LoadBalancer | Version managed by BOM 2025.1.4 |

## 5. Configuring Maven with the Spring Cloud BOM

Example POM using the Spring Boot parent and importing the Spring Cloud release train BOM:

```xml
<parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>4.1.2</version>
    <relativePath/>
</parent>

<properties>
    <java.version>17</java.version>
    <spring-cloud.version>2025.1.4</spring-cloud.version>
</properties>

<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.cloud</groupId>
            <artifactId>spring-cloud-dependencies</artifactId>
            <version>${spring-cloud.version}</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>

<dependencies>
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-loadbalancer</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-commons</artifactId>
    </dependency>
</dependencies>
```

In this POM:

- The Spring Boot parent manages dependencies in the Boot ecosystem.
- `spring-cloud-dependencies` manages Spring Cloud modules according to train 2025.1.4.
- Spring Cloud dependencies do not need individual version declarations.
- `spring-cloud-commons` is usually already present transitively via starters. Only declare it directly when the application source code actually uses Commons APIs at compile time; otherwise, the corresponding starter is enough.

If the project does not use the Spring Boot parent, you can still import `spring-cloud-dependencies` in `dependencyManagement` alongside the Boot BOM or your existing dependency management mechanism. Do not import a Cloud BOM from a different train just to pull in a single module.

## 6. Configuring Gradle with the Spring Cloud BOM

Example using Gradle Groovy DSL with the dependency management plugin:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '4.1.2'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

ext {
    set('springCloudVersion', '2025.1.4')
}

dependencyManagement {
    imports {
        mavenBom "org.springframework.cloud:spring-cloud-dependencies:${springCloudVersion}"
    }
}

dependencies {
    implementation 'org.springframework.cloud:spring-cloud-starter-loadbalancer'
    implementation 'org.springframework.cloud:spring-cloud-commons'
}
```

You can use Gradle's native platform/BOM dependency management instead of the plugin. Either way, the goal remains having a single release train BOM manage the Spring Cloud modules.

## 7. Verifying the Actual Resolved Versions

Do not just read the versions in the build file. Dependencies can be overridden by:

- Another imported BOM.
- A version declared directly on a dependency.
- A Gradle dependency constraint or resolution strategy.
- A transitive dependency from another library.
- An organization's parent POM or convention plugin.

### 7.1. Maven

View the Commons dependency tree:

```bash
mvn dependency:tree -Dincludes=org.springframework.cloud:spring-cloud-commons
```

View the merged POM:

```bash
mvn help:effective-pom
```

In the output, confirm that `spring-cloud-commons` resolves to 5.0.4 when using Cloud 2025.1.4.

### 7.2. Gradle

View the selected dependency and why it was chosen:

```bash
./gradlew dependencyInsight --dependency spring-cloud-commons --configuration runtimeClasspath
```

If you want to view the full runtime graph:

```bash
./gradlew dependencies --configuration runtimeClasspath
```

Check the JVM used by the build tool:

```bash
java -version
mvn -version
./gradlew --version
```

`java -version` in the shell is not necessarily the JVM used by the IDE or the Gradle daemon. You need to cross-check the toolchain, the build tool's JVM, and the runtime in the container/deployment.

## 8. Spring Cloud Compatibility Verifier

Spring Cloud Commons includes a Compatibility Verifier to detect certain Spring Boot combinations that are not in the train's compatibility list. It can be enabled with:

```yaml
spring:
  cloud:
    compatibility-verifier:
      enabled: true
```

In current Commons versions, the verifier is configured via `spring.cloud.compatibility-verifier.enabled`; property metadata lists the default as `false`. Therefore, if you want to use it as a startup check, you must enable it explicitly.

The verifier is an additional safeguard. It does not replace the official compatibility table, the BOM, or checking the dependency tree. Do not edit `compatible-boot-versions` to hide an unsupported combination. If you must use a custom combination, ensure you have integration tests, a risk assessment, and an explicit support decision.

## 9. Common Mistakes When Building a Matrix

| Symptom | Cause | Resolution |
| --- | --- | --- |
| Boot starts up, but Spring Cloud reports incompatibility | Selected a release train that does not support the Boot generation in use | Check the mapping table, choose the right train, and enable the Compatibility Verifier. |
| NoSuchMethodError or NoClassDefFoundError in Commons | Forced a Commons module from a different series than the BOM or mixed multiple trains | Remove version overrides, use a single Cloud BOM, and inspect the dependency tree. |
| Commons 4.x paired with Boot 4.x | Pulled the Commons version from a Boot 3.x train | Use Cloud 2025.1.x and Commons 5.0.x for Boot 4.x. |
| Commons 5.x paired with Boot 3.5.x | Forced Commons to a new major version while keeping the old train | Do not mix majors; pick the train matching Boot or upgrade Boot. |
| Using Cloud 2025.0.x for Boot 4.0.x | Confused 2025.0 with 2025.1 | Boot 4.0/4.1 uses 2025.1.x; 2025.0.x is for Boot 3.5.x. |
| Using 2026.0.0-RC2 in production | Mistook a release candidate for GA | Wait for GA or use RC only in a controlled evaluation environment. |
| Build runs on newer Java, but deployment fails | Build JVM and container runtime differ, or a supporting library does not support it yet | Check runtime JDK, toolchain, and third-party dependency requirements. |
| Dependency tree shows an unexpected Commons patch | Overridden by another BOM, direct version, or resolution rule | Inspect effective POM/dependencyInsight and remove unnecessary overrides. |
| Release train is out of OSS support | Continued using an old train because the application still builds | Plan an upgrade or confirm commercial support coverage. |

## 10. Checklist for Building the Matrix Before Upgrading

1. Record the current Java runtime, Java toolchain, and Spring Boot version.
2. Look up the release train compatible with the Boot generation in the Spring Cloud table.
3. Check whether the train is still under OSS support or only commercial support.
4. Select the latest patch release in the corresponding train.
5. Look up the `spring-cloud-commons` version in the train reference/BOM.
6. Import only the appropriate `spring-cloud-dependencies` BOM.
7. Remove individual versions from Spring Cloud modules if managed by the BOM.
8. Run `dependency:tree` or `dependencyInsight` to confirm the actual resolved versions.
9. Enable the Compatibility Verifier in testing/startup validation environments.
10. Run tests for discovery, registration, load balancing, refresh scope, and service calls.
11. Check third-party integrations such as Eureka, Consul, Kubernetes, Feign, and brokers.
12. Record Boot, Cloud train, Commons version, Java runtime, and lookup date in the release manifest.

## 11. Reference Upgrade Paths

### 11.1. From Boot 2.7 / Cloud 2021.0 to Boot 3.x

Boot 2.7 uses Java 8 or higher, and Cloud 2021.0 uses Commons 3.1.x. When moving to Boot 3.x, you need Java 17 and Cloud release train 2022.0 or later depending on the Boot minor version:

- Boot 3.0/3.1: Cloud 2022.0.x, Commons 4.0.x.
- Boot 3.2/3.3: Cloud 2023.0.x, Commons 4.1.x.
- Boot 3.4: Cloud 2024.0.x, Commons 4.2.x.
- Boot 3.5: Cloud 2025.0.x, Commons 4.3.x.

Trains 2021.0 and 2022.0 are currently out of OSS support. If the system still uses them, plan an upgrade path across supported Boot/Cloud milestones instead of upgrading Commons alone.

### 11.2. From Boot 3.5 / Cloud 2025.0 to Boot 4.x / Cloud 2025.1

This is a major upgrade of Spring Boot and Spring Framework. Path:

1. Verify Java 17 or higher and upgrade the build tool as required by Boot 4.
2. Read the migration guides for Spring Boot 4 and the Spring Cloud modules in use.
3. Upgrade Boot to the 4.0.x or 4.1.x line.
4. Switch the Cloud BOM to 2025.1.x.
5. Let the BOM manage Commons 5.0.x.
6. Address removed or changed APIs/packages in Spring Framework 7, Boot 4, and the Spring Cloud modules.
7. Run integration tests for configuration, discovery, registry, load balancer, HTTP client, and observability.
8. Roll out a canary deployment before upgrading all services.

Do not upgrade Commons 4.3 to 5.0 independently while keeping Cloud 2025.0 modules. The release train BOM must be upgraded together.

## 12. Release Trains and Support Lifecycle

A Spring Cloud release train is a collection of independent projects, each of which can have its own release schedule. Spring Cloud publishes a BOM to manage a curated set of versions. Therefore:

- A train may still have artifacts on Maven Central after OSS support ends.
- The existence of a version does not mean it still receives bug fixes or CVE patches.
- A train's support status depends on the lifecycle of its component projects and the Spring Boot version it supports.
- Spring Cloud 2025.0.3 is an example: artifacts can still be downloaded, but OSS support ended on 2026-06-30.

The Spring Cloud support policy states that major versions are supported for at least three years and minor versions for at least twelve months under the OSS policy; a release train does not have a separate support schedule independent of its component projects. When planning an upgrade, check both Spring Cloud Supported Versions and the Spring Boot lifecycle, rather than only checking whether Maven Central still hosts the artifacts.

## 13. Self-Check Questions

1. Why are Java, Spring Boot, Spring Cloud release train, and Spring Cloud Commons four distinct version axes?
2. Which Spring Boot lines is Spring Cloud 2025.1.4 compatible with?
3. Why does Cloud 2025.1.4 manage Commons 5.0.4 instead of Commons 2025.1.4?
4. What is the minimum Java version required by Boot 3.x and Boot 4.x?
5. Why should 2026.0.0-RC2 not be treated as GA?
6. What is the OSS support status of Cloud 2025.0.3 after 2026-06-30?
7. Why should you import the `spring-cloud-dependencies` BOM instead of setting versions for each module?
8. Which Maven or Gradle commands can verify the actual Commons version?
9. Is the Compatibility Verifier enabled by default in Commons 5.0.4?
10. Which areas should be tested after a major Boot/Cloud upgrade?

## 14. Official References

- [Spring Cloud — Release Train / Spring Boot Compatibility](https://spring.io/projects/spring-cloud/)
- [Spring Cloud Supported Versions and Project Mapping](https://github.com/spring-cloud/spring-cloud-release/wiki/Supported-Versions)
- [Spring Cloud Release 2025.1.4 — Project Versions](https://docs.spring.io/spring-cloud-release/reference/index.html)
- [Spring Cloud Release 2025.0.3 — Project Versions](https://docs.spring.io/spring-cloud-release/reference/2025.0/index.html)
- [Spring Cloud Release 2024.0.3 — Project Versions](https://docs.spring.io/spring-cloud-release/reference/2024.0/index.html)
- [Spring Cloud Release 2023.0.6 — Project Versions](https://docs.spring.io/spring-cloud-release/reference/2023.0/index.html)
- [Spring Cloud Release 2026.0.0-RC2 — Preview Project Versions](https://docs.spring.io/spring-cloud-release/reference/2026.0/index.html)
- [Spring Boot 4.1 System Requirements](https://docs.spring.io/spring-boot/system-requirements.html)
- [Spring Boot 4.0 System Requirements](https://docs.spring.io/spring-boot/4.0/system-requirements.html)
- [Spring Boot 3.5 System Requirements](https://docs.spring.io/spring-boot/3.5/system-requirements.html)
- [Spring Boot 2.7.18 System Requirements](https://docs.spring.io/spring-boot/docs/2.7.18/reference/html/getting-started.html#system-requirements)
- [Spring Cloud Commons 5.0.4 Configuration Properties](https://docs.spring.io/spring-cloud-commons/reference/configprops.html)
- [Spring Cloud 2025.0.3 — Final OSS Release Announcement](https://spring.io/blog/2026/06/11/spring-cloud-2025-0-3-aka-northfields-has-been-released/)
- [Spring Cloud 2026.0.0-RC2 Announcement](https://spring.io/blog/2026/11/05/spring-cloud-2026-0-0-rc2-has-been-released/)

A version matrix is a snapshot at the time of lookup. Before each release, re-verify the latest release train, the Spring Boot compatibility table, the Commons project version, and the OSS support status.
