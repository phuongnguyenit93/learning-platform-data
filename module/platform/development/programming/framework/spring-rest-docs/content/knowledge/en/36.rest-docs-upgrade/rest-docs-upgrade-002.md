# Aligning Compatible Spring Boot and Spring Framework Versions

## 1. Why Align Versions?

Spring REST Docs produces verifiable REST API documentation from HTTP tests using MockMvc, WebTestClient, or REST Assured. Tests generate snippets for requests, responses, payloads, headers, parameters, and multipart parts; Asciidoctor/Markdown assembles the snippets into documentation.

When upgrading, you cannot simply change the Spring REST Docs version and assume the entire build is compatible. Related components include the Java runtime, Spring Boot, Spring Framework, Spring Test, the REST Docs integration, the Asciidoctor plugin/AsciidoctorJ, and the Gradle/Maven wrapper.

The goal is to determine the actually resolved versions, compare them against the target release requirements, and then upgrade in a controlled manner.

## 2. Spring Boot – Spring Framework Relationship

Spring Boot provides dependency management to select Spring Framework versions tested together with the release train. When using the Spring Boot parent POM or BOM, you normally do not need to declare separate versions for modules such as spring-core, spring-context, spring-webmvc, or spring-test.

| Spring Boot generation | Typical paired Spring Framework generation |
| --- | --- |
| Boot 2.x | Framework 5.x |
| Boot 3.x | Framework 6.x |
| Boot 4.x | Framework 7.x |

This table only describes major generation relationships. Do not infer specific patch/minor versions; inspect the BOM of the exact Spring Boot release. Minor/patch versions within the same generation may vary across release trains.

If you manually override a Framework module, the project can create an untested combination with Boot, such as mismatched spring-webmvc and spring-test versions or a spring-core from a different generation.

**Principle:** choose a Spring Boot release compatible with your Java version and product requirements; let the BOM manage Spring Framework unless there is a clear, verified technical reason to override it.

## 3. Compatibility Dimensions to Check

| Component | What to Verify |
| --- | --- |
| Java runtime/toolchain | Whether Boot, Framework, REST Docs, and build plugins support this Java version |
| Spring Boot | Release train, BOM, and plugin version |
| Spring Framework | Whether modules resolved by the BOM share the same generation and a consistent version set |
| Spring REST Docs | Whether the release supports the Spring Framework/test stack in use |
| Spring Test | Compatibility with Framework and the test integration |
| Test client | MockMvc, WebTestClient, or REST Assured integration matching the application |
| Asciidoctor plugin | Compatibility with AsciidoctorJ and Java |
| AsciidoctorJ | Version required by the Spring REST Docs extension |
| Gradle/Maven | Wrapper and plugin versions meeting Boot/plugin requirements |

Some changes may compile successfully but fail during tests or when Asciidoctor builds HTML. Verification should cover dependency resolution, compile/test, snippet generation, and documentation packaging.

## 4. Using the Spring Boot BOM as the Source of Versions

### 4.1. Maven with Spring Boot Parent

Maven example using the Spring Boot parent:

```xml
<parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.x.y</version>
    <relativePath/>
</parent>

<properties>
    <java.version>17</java.version>
    <spring-restdocs.version>4.x.y</spring-restdocs.version>
</properties>

<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.restdocs</groupId>
        <artifactId>spring-restdocs-mockmvc</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
```

Versions 3.x.y and 4.x.y are placeholders, not a guaranteed compatible pair. Choose REST Docs according to that release's documentation and the project's Java/Framework stack. The Boot parent/BOM typically manages starter and Spring Framework versions; do not pin individual modules without an explicit reason.

### 4.2. Maven Without the Boot Parent

If the project uses a custom parent POM, import the Boot BOM inside dependencyManagement:

```xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-dependencies</artifactId>
            <version>3.x.y</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
```

The BOM manages dependencies listed within it. Plugin versions and dependencies outside the BOM still need to be managed separately.

### 4.3. Gradle

Groovy DSL example:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.x.y'
    id 'io.spring.dependency-management' version '1.x.y'
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.restdocs:spring-restdocs-mockmvc:4.x.y'
}
```

Combining the Boot plugin with the dependency management plugin lets you use the corresponding BOM. If using Gradle native platforms/BOMs, configure the platform explicitly and avoid mixing multiple override mechanisms at the same time. Replace placeholders with versions supported by your build environment.

## 5. Inspecting Resolved Versions in Maven

Do not read only pom.xml; dependencies can arrive via starters, transitive dependencies, parent POMs, or profiles.

```bash
./mvnw help:effective-pom -Doutput=target/effective-pom.xml
./mvnw dependency:tree -Dincludes=org.springframework
./mvnw dependency:tree -Dincludes=org.springframework.restdocs
```

The effective POM displays the configuration after inheriting from the parent, importing BOMs, and applying profiles. The dependency tree shows the selected versions and dependency paths.

Check:

- Do spring-core, spring-context, spring-webmvc, and spring-test belong to the same release train?
- Do versions come from the Boot BOM or project overrides?
- Is the REST Docs integration properly in test scope?
- Is an older dependency being pulled in by another library?

Successful Maven resolution does not prove the combination is supported by Spring Boot; compare against the BOM and release notes.

## 6. Inspecting Resolved Versions in Gradle

```bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencies --configuration testRuntimeClasspath
./gradlew dependencyInsight --dependency spring-core --configuration testRuntimeClasspath
./gradlew dependencyInsight --dependency spring-test --configuration testRuntimeClasspath
./gradlew dependencyInsight --dependency spring-webmvc --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-restdocs --configuration testRuntimeClasspath
```

Read the output to see which version was selected, which dependency requested it, and which rules affected resolution. If you see force, strictly, constraints, or resolution rules, verify they are intentional and still necessary.

Do not use force merely to make the dependency tree look uniform. It is better to fix the version source in the BOM/platform or dependency management.

## 7. Aligning REST Docs with the Test Stack

| Test client | Integration |
| --- | --- |
| MockMvc | spring-restdocs-mockmvc |
| WebTestClient | spring-restdocs-webtestclient |
| REST Assured | spring-restdocs-restassured |

Choose the integration matching your actual test client. Do not mix core/extension artifacts from different releases.

Maven example:

```xml
<dependency>
    <groupId>org.springframework.restdocs</groupId>
    <artifactId>spring-restdocs-mockmvc</artifactId>
    <version>4.x.y</version>
    <scope>test</scope>
</dependency>
```

The REST Docs version must be compatible with Spring Framework and Spring Test. When crossing Boot generations, read migration/release notes to check API changes, the Java baseline, and test framework requirements.

## 8. Aligning the Asciidoctor Plugin and AsciidoctorJ

REST Docs tests may pass while the HTML step fails if the plugin or extension is incompatible. Distinguish between the Asciidoctor Maven/Gradle plugin (build integration), AsciidoctorJ (runtime processing AsciiDoc), and spring-restdocs-asciidoctor (extension providing REST Docs attributes/macros).

Maven plugin dependencies example:

```xml
<plugin>
    <groupId>org.asciidoctor</groupId>
    <artifactId>asciidoctor-maven-plugin</artifactId>
    <version>3.2.0</version>
    <dependencies>
        <dependency>
            <groupId>org.asciidoctor</groupId>
            <artifactId>asciidoctorj</artifactId>
            <version>3.0.0</version>
        </dependency>
        <dependency>
            <groupId>org.springframework.restdocs</groupId>
            <artifactId>spring-restdocs-asciidoctor</artifactId>
            <version>4.x.y</version>
        </dependency>
    </dependencies>
</plugin>
```

This is a configuration example, not a mandatory version set for every release. Consult the Getting Started guide of the exact REST Docs version to choose compatible Maven plugin/AsciidoctorJ versions.

## 9. Pre-Upgrade Verification Matrix

| Component | Current | Target | Verification Source |
| --- | --- | --- | --- |
| Java | Toolchain/runtime | Version supported by the Boot release | Boot system requirements |
| Spring Boot | Effective POM/plugin version | Target Boot release | Boot release notes/BOM |
| Spring Framework | Dependency tree | Version managed by the Boot BOM | Boot BOM |
| Spring REST Docs | Dependency tree | Compatible release | REST Docs release notes |
| Spring Test | Dependency tree | Version on the same Framework train | Boot BOM |
| Asciidoctor plugin | POM/Gradle plugin | Version supporting AsciidoctorJ | Plugin documentation |
| AsciidoctorJ | Plugin dependency | Version supported by the REST Docs extension | REST Docs Getting Started |
| Maven/Gradle | Wrapper version | Version supported by Boot/plugins | Build tool requirements |

Do not fill in target versions by guessing. For each version, record the verification source and the resolved result after making changes.

## 10. Controlled Upgrade Process

1. **Record the baseline:** current Java, Boot, dependency tree, wrapper, and test results.
2. **Choose the Boot release:** verify the Java baseline, support window, and migration notes.
3. **Let Boot manage Framework:** remove unnecessary overrides.
4. **Choose the REST Docs release:** check Framework/Spring Test and integration requirements.
5. **Choose Asciidoctor plugin/J:** follow the documentation for the exact REST Docs release.
6. **Upgrade wrapper/plugins:** verify Gradle/Maven versions meet requirements.
7. **Resolve dependencies:** run effective POM/dependency tree or Gradle dependencyInsight.
8. **Run tests:** compile and run REST Docs tests to generate snippets.
9. **Build documentation:** run Asciidoctor and inspect HTML.
10. **Package:** build the JAR/WAR and verify docs inside the archive.
11. **Smoke test:** run the application, request the docs URL and an asset.
12. **Document the matrix:** update actual versions and verification sources.

Upgrade closely related groups together; avoid changing Java, Boot, REST Docs, Asciidoctor, and the build tool all at once unless necessary. Checking the dependency tree and verifying each step separately helps isolate root causes.

## 11. Full-Pipeline Verification Commands

Maven:

```bash
./mvnw -version
./mvnw help:effective-pom -Doutput=target/effective-pom.xml
./mvnw dependency:tree -Dincludes=org.springframework,org.springframework.restdocs
./mvnw clean test
./mvnw prepare-package
./mvnw package
```

Gradle:

```bash
./gradlew --version
./gradlew dependencies --configuration testRuntimeClasspath
./gradlew dependencyInsight --dependency spring-core --configuration testRuntimeClasspath
./gradlew clean test asciidoctor
./gradlew bootJar
```

Inspect the archive:

```bash
jar tf target/application.jar
jar tf build/libs/application.jar
```

If docs are embedded, look for BOOT-INF/classes/static/docs/index.html and assets. If docs are a separate artifact, inspect the ZIP along with version metadata/source revision.

## 12. Common Errors

| Symptom | Cause | Resolution |
| --- | --- | --- |
| NoSuchMethodError in Spring | Mismatched Framework module versions or old library | Inspect dependency tree, remove overrides, and use the BOM |
| ClassNotFoundException in tests | Missing integration/test dependency or wrong scope | Add the right REST Docs integration in test scope |
| MockMvc tests fail after Boot upgrade | Changes in Spring Test/MVC API or configuration | Read migration notes, update test setup |
| WebTestClient integration error | Wrong integration or WebFlux/test stack version | Check REST Docs release and dependency tree |
| REST Assured test runtime error | Mismatched REST Docs integration version | Check integration artifact and transitive dependencies |
| Asciidoctor fails to load extension | Missing or wrong plugin dependency version | Check spring-restdocs-asciidoctor on the plugin classpath |
| AsciidoctorJ reports incompatible API | Plugin and AsciidoctorJ outside compatibility range | Use versions specified in Getting Started |
| Maven resolves unexpected version | Parent/BOM/profile/nearest dependency effect | Inspect effective POM and dependency tree |
| Gradle selects unexpected version | Constraint, force, or transitive dependency | Use dependencyInsight |
| Works locally but fails in CI | Different JDK/wrapper/cache/profile | Pin toolchain/wrapper, run clean build, and compare resolution |

## 13. Hands-On Exercise

A service is currently using Spring Boot and Spring REST Docs. Prepare an upgrade:

1. Record the Java, Boot, Framework, REST Docs, AsciidoctorJ, and build tool versions.
2. Run Maven effective POM/dependency tree or Gradle dependencies/dependencyInsight.
3. Identify which Framework versions come from the Boot BOM and whether any overrides exist.
4. Look up the Java/Framework requirements of the target Boot release.
5. Look up a REST Docs release compatible with the target Framework/Spring Test.
6. Choose the Asciidoctor plugin and AsciidoctorJ per the REST Docs guide.
7. Change versions at the centralized management source without pinning individual Framework modules.
8. Run REST Docs tests and verify snippets.
9. Run Asciidoctor and inspect the HTML.
10. Package the JAR and verify docs/assets inside the archive.
11. Start the application and test the docs URL.
12. Save the compatibility matrix along with the source revision.

**Completion criteria:** explain how the Boot BOM manages Framework; determine actual versions using dependency tools; align Java, Framework, REST Docs, and Asciidoctor; upgrade without introducing dependency drift; verify tests, HTML, and packaging.

## 14. Self-Check Questions

**1. Why shouldn't you pin versions of individual Spring Framework modules?**

The Spring Boot BOM manages a set of versions tested together within the release train. Pinning individually can produce an inconsistent combination of modules.

**2. Does Boot 3.x always use the same Spring Framework patch version?**

No. You must inspect the BOM of the exact Boot release; do not infer patch/minor versions from the major generation.

**3. Which Maven command shows configuration after inheriting parent/BOM?**

help:effective-pom.

**4. Which Gradle command explains why spring-core is resolved to its current version?**

dependencyInsight --dependency spring-core --configuration testRuntimeClasspath.

**5. Why check Spring REST Docs and AsciidoctorJ together?**

The REST Docs extension runs on the Asciidoctor classpath; an incompatible plugin and AsciidoctorJ can make document generation fail even when tests generate snippets successfully.

**6. Does a successful dependency tree resolution prove the combination is supported?**

No. You must cross-check the BOM, release notes, and official compatibility requirements.

**7. Which checks prove the upgrade is complete?**

REST Docs tests generate snippets, Asciidoctor produces HTML, the package contains docs/assets, and the application serves the correct URL.

## References

- [Spring Boot — Dependency Versions](https://docs.spring.io/spring-boot/appendix/dependency-versions/index.html): dependency versions managed by each Boot release.
- [Spring Boot — Managing Dependencies](https://docs.spring.io/spring-boot/reference/using/build-systems.html): using parent/BOM and dependency management.
- [Spring REST Docs — Getting Started](https://docs.spring.io/spring-restdocs/tutorial/getting-started/index.html): dependencies, test integrations, and Asciidoctor configuration per release.
- [Spring Framework — Overview and Requirements](https://docs.spring.io/spring-framework/reference/overview.html): Framework requirements and foundational details.
- [Maven Dependency Plugin](https://maven.apache.org/plugins/maven-dependency-plugin/): dependency tree and dependency analysis tools.
- [Gradle — Viewing and Debugging Dependencies](https://docs.gradle.org/current/userguide/viewing_debugging_dependencies.html): dependencies and dependencyInsight.
