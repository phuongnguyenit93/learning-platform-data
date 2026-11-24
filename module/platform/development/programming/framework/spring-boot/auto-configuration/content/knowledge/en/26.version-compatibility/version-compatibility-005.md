# Package, Module, and Dependency Changes When Upgrading Spring Boot Lines

## 1. Upgrading a Spring Boot line is a platform-wide change

A Spring Boot upgrade is not just changing a version number in `pom.xml` or `build.gradle`. Each Spring Boot line is tested against a specific set of Java, Spring Framework, Spring Data, Spring Security, third-party libraries, and build plugin versions. When upgrading lines, these pieces must remain mutually compatible.

Four groups of changes must be reviewed:

1. **Java and Jakarta EE:** minimum JDK version, Servlet/JPA/Validation APIs, and package namespaces.
2. **Packages and APIs:** classes moved, renamed, replaced, or removed; class name strings in metadata may also need updates.
3. **Modules and starters:** artifacts split smaller, renamed, or given dedicated test starters.
4. **Dependency management:** BOM, Maven coordinates, library versions, and build plugins must align with the target Boot line.

A project may compile after changing the version yet still fail at runtime due to old dependencies remaining on the classpath, auto-configuration not being discovered, or the container not meeting the new Servlet baseline. Therefore, an upgrade must be treated as a verified change across compilation, tests, packaging, and application startup.

## 2. Identify the source and target lines before editing the build

Spring Boot recommends upgrading the application to the latest maintenance release of the current line before moving to a new line. For example:

- From Boot 2.x to Boot 3.x: first upgrade to the latest 2.7.x release, resolve deprecation warnings, and inspect dependencies.
- From Boot 3.x to Boot 4.x: first upgrade to the latest 3.5.x release, address deprecated APIs/properties, and inspect dependencies.

If skipping multiple feature releases, read the release notes of all intermediate lines. Small changes in properties, auto-configuration, or dependencies can accumulate into hard-to-trace errors on the final jump.

### 2.1. Comparing key platform milestones

| Spring Boot line | Minimum Java | Underlying Spring Framework | Jakarta/Servlet |
|---|---:|---|---|
| Boot 2.7 | Java 8 | Spring Framework 5.3 | Java EE / `javax.*` APIs |
| Boot 3.0 | Java 17 | Spring Framework 6.0 | Jakarta EE 10; Servlet 6.0 |
| Boot 4.0 | Java 17 | Spring Framework 7.x | Jakarta EE 11; Servlet 6.1 |

This table highlights major milestones and does not replace the System Requirements of the exact maintenance release. Build tool versions, containers, Kotlin, GraalVM, and supporting libraries may have their own requirements. Check the target line documentation before changing the toolchain.

For example, Boot 4.0 requires Java 17 or higher and Spring Framework 7.x. The Boot 4.0 System Requirements documentation also specifies Maven 3.6.3 or higher and Gradle 8.14 or higher in the 8.x branch or Gradle 9.x. Re-verify the requirements of the exact Boot version being deployed.

### 2.2. Inventory dependencies before changing versions

Record the following components:

- Build JDK and production JDK.
- Spring Boot plugin, parent POM, or BOM.
- Spring Framework, Spring Data, Spring Security, and Spring Cloud.
- Starters in use and directly declared dependencies.
- Database drivers, HTTP clients, logging, JSON, metrics, and messaging.
- Build plugins, annotation processors, test engines, and deployment containers.
- In-house libraries that import internal classes or Spring Boot packages.

Distinguish dependencies managed by the BOM from dependencies with explicitly declared versions. A library outside the BOM, such as Spring Cloud or a vendor SDK, must have its own compatibility matrix checked. Do not assume it is compatible simply because the application uses a new Spring Boot version.

## 3. Boot 2 to Boot 3: migrating from Java EE to Jakarta EE

The most visible package change when upgrading from Boot 2 to Boot 3 is that Jakarta EE APIs moved from the `javax` namespace to `jakarta`. Boot 3 uses Spring Framework 6 and newer Jakarta EE versions.

Examples of imports that commonly change:

| Before (Boot 2 / Java EE) | After (Boot 3 / Jakarta EE) |
|---|---|
| `javax.servlet.Filter` | `jakarta.servlet.Filter` |
| `javax.persistence.Entity` | `jakarta.persistence.Entity` |
| `javax.validation.Valid` | `jakarta.validation.Valid` |
| `javax.transaction.Transactional` | `jakarta.transaction.Transactional` |
| `javax.annotation.PostConstruct` | `jakarta.annotation.PostConstruct` |

Servlet API example:

~~~java
// Before: Boot 2.x
import javax.servlet.Filter;
import javax.servlet.ServletRequest;
import javax.servlet.ServletResponse;

// After: Boot 3.x
import jakarta.servlet.Filter;
import jakarta.servlet.ServletRequest;
import jakarta.servlet.ServletResponse;
~~~

Do not blindly replace every string starting with `javax.`. Several Java SE packages stay unchanged, such as:

- `javax.sql.DataSource`
- `javax.crypto.*`
- `javax.net.*`
- `javax.xml.*`
- `javax.annotation.processing.*`

Determine whether a package belongs to Jakarta EE or Java SE before changing imports. Mistakenly changing `javax.sql.DataSource` to `jakarta.sql.DataSource` will prevent the code from compiling because that package does not exist.

### 3.1. Aligning Jakarta dependencies

If using Spring Boot starters and the BOM, many Jakarta dependencies are managed according to the Boot line. If declaring APIs manually, verify both Maven coordinates and versions.

Servlet API example:

~~~xml
<!-- Jakarta Servlet API for Boot 3 applications -->
<dependency>
    <groupId>jakarta.servlet</groupId>
    <artifactId>jakarta.servlet-api</artifactId>
    <scope>provided</scope>
</dependency>
~~~

Do not keep both the old `javax.servlet:javax.servlet-api` and the new `jakarta.servlet:jakarta.servlet-api` on the same runtime just to mask compile errors. The two namespaces define different types and are not interchangeable.

Integration libraries must also support Jakarta. If an SDK, filter, validation provider, or persistence library only provides `javax.*` classes, upgrade it to a Jakarta-compatible version or replace that library.


## 4. Boot 3: reviewing auto-configuration, packages, and legacy dependencies

### 4.1. Registering auto-configuration via the imports file

Spring Boot 2.7 introduced the file:

~~~text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

From Spring Boot 3.0 onward, registering auto-configuration via the `org.springframework.boot.autoconfigure.EnableAutoConfiguration` key in `spring.factories` was removed. Move the auto-configuration list to `AutoConfiguration.imports`.

Example file contents:

~~~text
com.example.audit.autoconfigure.AuditAutoConfiguration
com.example.audit.autoconfigure.AuditMetricsAutoConfiguration
~~~

Each line is the fully qualified name of one class. Other `spring.factories` entries, such as extension points other than `EnableAutoConfiguration`, are not removed because of this change. Read the proper key and documentation for each corresponding extension point before moving anything.

If a library must support both Boot 2.7 and Boot 3 during a transition period, Boot 2.7 understands both mechanisms and deduplicates classes declared in both places. For new libraries supporting only Boot 3 and higher, use the imports file as the primary registration mechanism.

### 4.2. Tracking renamed or relocated classes

Do not update imports only in source code. Class names can also appear in:

- `AutoConfiguration.imports` and metadata files.
- `spring.factories`.
- `@AutoConfiguration(before = ...)` or `after = ...`.
- `exclude` / `excludeName` on `@EnableAutoConfiguration`.
- `@Import`, reflection, class names in configuration, and tests.
- `META-INF/spring/...AutoConfiguration.replacements` if a library maintains auto-configuration name compatibility.

An example from the Boot 3 migration guide: `ReactiveElasticsearchRestClientAutoConfiguration` was renamed to `ReactiveElasticsearchClientAutoConfiguration` and moved from package `org.springframework.boot.autoconfigure.data.elasticsearch` to `org.springframework.boot.autoconfigure.elasticsearch`. When an application excludes or orders configuration using the old class, both the imports and the corresponding metadata references must be updated.

### 4.3. Checking changed dependency coordinates

Some dependencies change groupId or artifactId when upgrading lines. Examples from migrating to Boot 3:

| Before | After |
|---|---|
| `mysql:mysql-connector-java` | `com.mysql:mysql-connector-j` |
| `org.apache.httpcomponents:httpclient` | `org.apache.httpcomponents.client5:httpclient5` |

These are representative examples, not a complete list. Do not keep old coordinates just because a transitive dependency still pulls them onto the classpath. Inspect the dependency tree and vendor documentation to confirm the direct dependencies the application should declare.

### 4.4. Handling renamed or removed properties

Properties may change prefixes, be renamed, or be removed between feature releases. For example, in Boot 3, some Redis settings moved from `spring.redis.*` to `spring.data.redis.*`; some Cassandra settings moved from `spring.data.cassandra.*` to `spring.cassandra.*`.

Spring Boot provides the `spring-boot-properties-migrator` module to analyze the environment, print warnings, and temporarily migrate certain properties when running the application.

Maven:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-properties-migrator</artifactId>
    <scope>runtime</scope>
</dependency>
~~~

Gradle:

~~~groovy
runtimeOnly 'org.springframework.boot:spring-boot-properties-migrator'
~~~

Run the application in a test or staging environment, read the warnings, update the actual configuration files, and then remove the migrator from dependencies. The migrator is a transitional tool, not a long-term compatibility layer. Properties added late to the Environment, such as via `@PropertySource`, may not be fully handled by the migrator.

## 5. Boot 4: smaller modules and module-scoped packages

Spring Boot 4.0 has a much more modular design. Instead of a few large JARs containing many integrations, Boot publishes many smaller technology-focused modules. Each module follows a dedicated root package convention:

- Module: `spring-boot-<technology>`.
- Root package: `org.springframework.boot.<technology>`.
- Starter: `spring-boot-starter-<technology>`.

For example, GraphQL support resides in module `spring-boot-graphql`, root package `org.springframework.boot.graphql`, and starter `spring-boot-starter-graphql`.

This affects both dependencies and Java imports. If an application uses only official starters, most dependencies transition with the starter. If an application declares Boot modules directly or imports specific Boot classes, each module/package must be audited and updated.

### 5.1. Renamed starters

Some old starters still exist in Boot 4 but are deprecated so users migrate to the new names:

| Old starter | New starter |
|---|---|
| `spring-boot-starter-web` | `spring-boot-starter-webmvc` |
| `spring-boot-starter-web-services` | `spring-boot-starter-webservices` |
| `spring-boot-starter-oauth2-client` | `spring-boot-starter-security-oauth2-client` |
| `spring-boot-starter-oauth2-resource-server` | `spring-boot-starter-security-oauth2-resource-server` |
| `spring-boot-starter-oauth2-authorization-server` | `spring-boot-starter-security-oauth2-authorization-server` |

Do not rely on an old starter still resolving to conclude it remains a good choice. Update to replacement names from the migration guide and track deprecated starters slated for removal in later releases.

### 5.2. Separating runtime and test dependencies

Boot 4 standardizes starters by technology and provides accompanying test starters. Examples:

| Purpose | Dependency |
|---|---|
| Spring MVC runtime | `spring-boot-starter-webmvc` |
| Spring MVC test support | `spring-boot-starter-webmvc-test` |
| JDBC runtime | `spring-boot-starter-jdbc` |
| JDBC test support | `spring-boot-starter-jdbc-test` |
| Spring Security runtime | `spring-boot-starter-security` |
| Spring Security test support | `spring-boot-starter-security-test` |

Inspect `testImplementation` / Maven `test` scope separately. When test infrastructure is modularized, an old test dependency may no longer transitively pull in all test utility classes the application previously used indirectly.

### 5.3. Relocated packages in Boot 4

Some important examples from the migration guide:

| API | Old package | New package |
|---|---|---|
| `BootstrapRegistry` | `org.springframework.boot` | `org.springframework.boot.bootstrap` |
| `EnvironmentPostProcessor` | `org.springframework.boot.env` | `org.springframework.boot` |
| `EntityScan` | legacy auto-config package | `org.springframework.boot.persistence.autoconfigure.EntityScan` |
| `TestRestTemplate` | legacy test package | `org.springframework.boot.resttestclient.TestRestTemplate` |

If using `EnvironmentPostProcessor` or `BootstrapRegistry`, update both source code and the class name registered in `spring.factories`. For `TestRestTemplate`, the migration guide specifies the new test dependency `spring-boot-resttestclient`.

Example imports after upgrading to Boot 4:

~~~java
import org.springframework.boot.bootstrap.BootstrapRegistry;
import org.springframework.boot.EnvironmentPostProcessor;
import org.springframework.boot.persistence.autoconfigure.EntityScan;
import org.springframework.boot.resttestclient.TestRestTemplate;
~~~

Do not copy a package table verbatim from an old blog post. Every class should be cross-checked against the API docs or migration guide of the exact target Boot line because packages can change across modules and releases.

### 5.4. Migration from Jackson 2 to Jackson 3

Boot 4 uses Jackson 3 as its default JSON library. Jackson 3 moves most groupIds/packages from `com.fasterxml.jackson` to `tools.jackson`; `jackson-annotations` alone continues to use groupId `com.fasterxml.jackson.core` and package `com.fasterxml.jackson.annotation`.

Some API changes:

| Jackson 2 / Boot 3 | Jackson 3 / Boot 4 |
|---|---|
| `com.fasterxml.jackson.databind.ObjectMapper` | `tools.jackson.databind.ObjectMapper` |
| `Jackson2ObjectMapperBuilderCustomizer` | `JsonMapperBuilderCustomizer` |
| `@JsonComponent` | `@JacksonComponent` |
| `@JsonMixin` | `@JacksonMixin` |

Several JSON properties also moved from `spring.jackson.read.*` / `spring.jackson.write.*` to `spring.jackson.json.read.*` / `spring.jackson.json.write.*`.

If immediate migration is not yet possible, Boot 4 offers the `spring-boot-jackson2` compatibility module, though this module is marked deprecated and should only be used as a transitional measure. Do not include both Jackson 2 and Jackson 3 in the default configuration without clearly understanding which mapper each integration uses.


## 6. Aligning BOM, Spring Framework, and build plugins

Spring Boot publishes the `spring-boot-dependencies` BOM containing dependency versions integrated and tested together for that Boot line. Use the BOM so Spring modules, Spring Data, and third-party libraries are managed in sync.

Principles when upgrading:

- Update the Spring Boot parent, plugin, and BOM to the same line.
- Remove explicit version declarations for dependencies already managed by the BOM.
- Do not force Spring Framework, Spring Data, Jackson, Hibernate, or logging onto arbitrary versions without compatibility testing.
- If a dependency override is necessary, document the reason, check the compatibility matrix, and add corresponding tests.
- Spring Cloud and other portfolio release trains must use versions compatible with the target Boot line.

### 6.1. Maven: using parent or importing BOM

If the project can inherit the Spring Boot parent:

~~~xml
<parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>4.0.0</version>
    <relativePath/>
</parent>

<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-webmvc</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-webmvc-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

`4.0.0` is an illustrative version for syntax. When performing an actual migration, use the maintenance release approved by the organization and use that same version for the Spring Boot Maven plugin.

If the company has a custom parent POM, import the BOM inside `dependencyManagement`:

~~~xml
<properties>
    <spring-boot.version>4.0.0</spring-boot.version>
</properties>

<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-dependencies</artifactId>
            <version>4.0.0</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

Then declare dependencies without repeating versions when managed by the BOM. At the same time, update `spring-boot-maven-plugin` to the same version line. If the old plugin still runs while the new BOM is imported, the build can produce artifacts with inconsistent loader or packaging behavior.

### 6.2. Gradle: aligning plugin and BOM

Groovy DSL example:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '4.0.0'
}

dependencies {
    implementation platform('org.springframework.boot:spring-boot-dependencies:4.0.0')

    implementation 'org.springframework.boot:spring-boot-starter-webmvc'
    testImplementation 'org.springframework.boot:spring-boot-starter-webmvc-test'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

This is an illustrative configuration for Boot 4.0. In a real project, verify the Gradle Wrapper version supported by the target Boot line and use the same version for both the plugin and the BOM. If the project uses Kotlin DSL or internal convention plugins, update the version catalog and convention plugins rather than editing only a single submodule.

### 6.3. Do not keep multiple versions of the same platform

After changing the BOM, run dependency insight to find version conflicts. For instance, a direct dependency declaring Spring Framework 6 while Boot 4 manages Spring Framework 7 can cause the classpath to contain Spring modules from mismatched baselines.

Maven:

~~~bash
mvn help:effective-pom
mvn dependency:tree -Dverbose
~~~

Gradle:

~~~bash
./gradlew dependencies
./gradlew dependencyInsight --dependency spring-core --configuration runtimeClasspath
~~~

Inspect the compile classpath, runtime classpath, and test runtime classpath. An old dependency appearing only in tests can make test compilation fail even when the production application runs.

## 7. Building custom libraries/starters for multiple Boot lines

If a team develops an auto-configuration library or starter, Spring Boot's packages and modules are part of the compile-time API the library depends on. An artifact built with Boot 3 is not naturally compatible with Boot 4 just because the user changes the dependency version.

The Boot 4 migration guide strongly recommends against supporting Boot 3 and Boot 4 in the same artifact due to modularization and package changes.

A manageable way to organize is publishing separate artifacts per line:

~~~text
northstar-spring-boot-3-autoconfigure
northstar-spring-boot-3-starter
northstar-spring-boot-4-autoconfigure
northstar-spring-boot-4-starter
~~~

The names above are examples from a hypothetical vendor. Keep the vendor's namespace first; do not name third-party artifacts starting with `spring-boot`.

A multi-module repository or separate release branches can be used, but each artifact must:

- Compile against the proper Spring Boot BOM and APIs of the supported line.
- Have its own dependency graph, not pulling Boot 3 classes into a Boot 4 artifact.
- Have a test suite running on the corresponding Boot version.
- Package the correct auto-configuration imports and metadata.
- Clearly publish version compatibility, Java baseline, and migration path.
- Be able to release security patches independently per line if the organization needs parallel support.

If business logic needs to be shared, extract code that does not depend on Spring Boot into a core module. The Boot 3 and Boot 4 adapters can share the core API, while each adapter compiles against the exact packages, modules, and auto-configuration API of its respective line.

### 7.1. Checking starter metadata after migration

After building the JAR, verify:

- `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports` contains the exact class names of the target Boot line.
- `spring.factories` files contain only valid keys and class names.
- Class names in ordering, exclusions, replacements, and reflection no longer have old packages.
- Configuration metadata generated from `@ConfigurationProperties` classes is accurate.
- No duplicate classes or transitive dependencies pull both Boot 3 and Boot 4 into the same runtime.

A test using `ApplicationContextRunner` may register the auto-configuration class directly, so it is not enough to prove resources in the JAR are packaged properly. Add a consumer smoke test that depends only on the published or locally installed starter artifact to verify discovery through the artifact.


## 8. Step-by-step upgrade workflow

A repeatable workflow helps catch failures at the exact layer of change.

### Step 1: Lock the current baseline

- Upgrade to the latest maintenance release of the current Boot line.
- Run the full test suite and save results as a baseline.
- Record the dependency tree, JDK version, Maven/Gradle Wrapper, and production container.
- Enable compiler warnings or deprecation checks to find APIs marked for removal.

Do not start with bulk import replacements if the current application does not yet build green. If pre-existing failures exist, triage them first so legacy issues are not confused with migration issues.

### Step 2: Clean up deprecations before moving majors

Replace classes, methods, and properties deprecated in the current line. Boot 3 removed many APIs deprecated in Boot 2; Boot 4 continues removing APIs deprecated in Boot 3.

Read the migration guide and release notes for each line. A method still existing in the last release of an old line does not mean it remains in the next major.

### Step 3: Upgrade JDK and build tools

Update the JDK/toolchain beforehand or in a controlled build change. Check:

- Local JDK, CI, Docker base images, and production runtime.
- Maven Wrapper or Gradle Wrapper.
- Compiler release/source compatibility.
- Annotation processors, Kotlin plugin, and executable JAR packaging plugins.
- Servlet container or application server if deploying a WAR.

Example Java toolchain configuration in Gradle:

~~~groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}
~~~

Java 17 is the baseline for Boot 3 and Boot 4. However, third-party dependencies or build tools may require a higher Java version.

### Step 4: Switch Spring Boot parent/plugin/BOM in one pass

Update the single place managing the version whenever possible. Verify every submodule inherits the new BOM, including test, integration test, build logic, and code generation modules.

Ensure the Boot plugin, BOM, dependency management plugin, and related plugins no longer mix versions from two lines.

### Step 5: Update packages and metadata

- From Boot 2 to 3, migrate Jakarta APIs from `javax` to `jakarta` and review corresponding dependencies.
- From Boot 3 to 4, update packages split by module, such as `BootstrapRegistry`, `EnvironmentPostProcessor`, `EntityScan`, and `TestRestTemplate`.
- Update `spring.factories` if an extension point class name changed.
- Update `AutoConfiguration.imports`, exclusions, ordering, and reflection strings.
- Check test sources, generated sources, annotation processors, and configuration files.

Do not change package names in source code while forgetting class names stored as strings in metadata files.

### Step 6: Migrate starters and test dependencies

Cross-check dependencies against the starter/module table of the target Boot line. Replace deprecated starters with new starters; add corresponding test starters when tests use separated test support classes.

If upgrading to Boot 4 and needing an intermediate step to get a large application starting quickly, `spring-boot-starter-classic` and `spring-boot-starter-test-classic` can be used. Classic starters provide a broad module set close to the previous generation, allowing packages and dependencies to be migrated gradually. This is only a bridge; once migration completes, move to specific starters/modules for a smaller, clearer classpath.

### Step 7: Migrate properties and configuration behavior

Use the properties migrator when properties are renamed, then update the original configuration files. Compare files:

- `application.properties` and `application.yml`.
- Profile-specific configurations.
- Environment variables and command-line arguments.
- Config servers, Kubernetes ConfigMaps/Secrets, and secret managers.
- Values loaded via `@PropertySource` or custom EnvironmentPostProcessors.

Verify actual bound values, not just property names in source. A property can keep its name while changing its default or interpretation.

### Step 8: Run tests and verify artifacts

Run in order:

1. Compile main sources and test sources.
2. Unit tests and slice tests.
3. Integration tests with databases, brokers, caches, and mocked external services.
4. Package JAR/WAR and inspect contents.
5. Start the application using the newly packaged artifact.
6. Smoke test endpoints, health, metrics, security, database migrations, and graceful shutdown.
7. Test the image/container in a production-like environment.

For starter libraries, add a consumer sample depending only on the published/installed starter artifact. This test confirms transitive dependencies, packages, and auto-configuration discovery behave as they do for real users.

## 9. Tools to help find and fix changes

### 9.1. Finding legacy imports and dependency coordinates

Ripgrep can be used to scan sources and build files:

~~~bash
rg -n "javax\\.(servlet|persistence|validation|transaction|annotation)" src
rg -n "spring-boot-starter-web|spring-boot-starter-oauth2" pom.xml build.gradle settings.gradle
rg -n "spring\\.redis|spring\\.data\\.cassandra|spring\\.data\\.mongodb" src/main/resources
~~~

Search results are a review checklist, not an automated replacement list. In particular, do not replace all `javax.*` occurrences because many Java SE packages still belong to the JDK.

### 9.2. Using OpenRewrite or IDE migration

OpenRewrite has recipes supporting certain Spring Boot and Jakarta migrations. IDEs can also assist with package renames and import fixes. These tools reduce repetitive edits, but results still require review:

- Recipes may be unaware of the organization's internal dependencies.
- Some changes require updating Maven/Gradle coordinates alongside source code.
- Reflection, string-based class names, and resource files may not be updated automatically.
- An API with changed semantics may need redesigning rather than just renaming.

Run recipes on a separate branch, review the diff, then compile and test. Do not treat a recipe finishing as proof that the migration is complete.

### 9.3. Inspecting dependencies and JARs

Maven:

~~~bash
mvn help:effective-pom
mvn dependency:tree -Dverbose
mvn clean verify
jar tf target/application.jar
~~~

Gradle:

~~~bash
./gradlew dependencies
./gradlew dependencyInsight --dependency spring-core --configuration runtimeClasspath
./gradlew clean check bootJar
~~~

Check that:

- No incompatible legacy dependencies remain.
- No two versions of Spring Framework or critical platform libraries exist.
- Test dependencies are not pulled into runtime.
- Auto-configuration and metadata resources are present in the JAR.
- Classes referenced in the imports file actually exist in the artifact.

## 10. Common mistakes

1. **Changing only the Spring Boot version.** Parent/plugin/BOM, Java, packages, dependencies, and test support must all be reviewed together.
2. **Replacing every `javax` with `jakarta`.** Only Jakarta EE APIs changed namespaces; Java SE packages like `javax.sql` remain unchanged.
3. **Keeping legacy Java EE dependencies alongside Jakarta APIs.** The two namespaces are type-incompatible and can cause classpath or runtime errors.
4. **Forgetting `AutoConfiguration.imports` when upgrading to Boot 3.** The `EnableAutoConfiguration` key in `spring.factories` is no longer the way to register auto-configuration.
5. **Updating imports while forgetting metadata.** Ordering, exclusions, reflection, and `spring.factories` may still reference old class names.
6. **Keeping deprecated starters in Boot 4.** Switch to new starters such as `spring-boot-starter-webmvc` and starters with the `security` prefix.
7. **Failing to separate test dependencies.** A test may miss MockMvc, RestTestClient, JDBC test support, or other test classes even when runtime dependencies are right.
8. **Pinning a standalone Spring Framework version alongside the Boot BOM.** This can create an incompatible set of modules.
9. **Upgrading Spring Cloud or out-of-BOM SDKs without checking matrices.** Dependencies outside the BOM have their own compatibility cycles.
10. **Leaving the properties migrator in production long-term.** Use it to find and fix properties, then remove it from the build.
11. **Using classic starters as the final solution.** They are a transitional bridge; afterward, replace them with specific starters/modules.
12. **Checking only compilation.** Runtime errors can surface in the servlet container, security filters, JSON mapper, database driver, or auto-configuration.
13. **A custom artifact trying to support both Boot 3 and Boot 4.** Packages and module APIs differ; splitting artifacts by line keeps compatibility under control.
14. **Not reading release notes of intermediate lines.** Minor property and dependency changes can be missed when jumping across multiple releases.

## 11. Checklist before marking migration complete

| Item | Pass criteria |
|---|---|
| Baseline | Source line upgraded to latest maintenance release and deprecations resolved |
| Java | Build, CI, and runtime JDKs meet the target line baseline |
| Build tools | Supported Maven/Gradle Wrapper and plugins |
| BOM | Boot parent/plugin/BOM aligned; no arbitrary framework overrides |
| Jakarta | Jakarta imports and dependencies accurate; no mass-replace of Java SE `javax.*` |
| Packages | Imports, reflection, metadata, and class names updated |
| Auto-configuration | Imports file, `spring.factories`, ordering, and exclusions valid |
| Starters | Runtime starters and test starters match the target line |
| Dependencies | Dependency tree free of version conflicts or legacy artifacts |
| Properties | Renamed/changed-default properties updated; migrator removed |
| Tests | Unit, slice, integration, and consumer smoke tests all pass |
| Packaging | JAR/WAR contains proper classes, resources, and metadata |
| Runtime | Application starts and passes smoke tests in a production-like environment |
| Documentation | Version matrix, Java baseline, and migration notes updated |

## 12. Takeaways

- Boot 2 to Boot 3 is a major transition to Java 17, Spring Framework 6, and Jakarta EE; Jakarta APIs moved from `javax.*` to `jakarta.*`.
- Boot 3 removed auto-configuration registration via the `EnableAutoConfiguration` key in `spring.factories`; use `AutoConfiguration.imports`.
- Boot 4 continues requiring Java 17, moves to Spring Framework 7/Jakarta EE 11, and modularizes packages, modules, and starters.
- Boot 4 renames several starters, separates test starters, and moves packages of many APIs; both source code and metadata must be updated.
- Use the target Boot line's BOM to align dependencies; check Spring Cloud and out-of-BOM libraries separately.
- The properties migrator and classic starters are transitional tools; remove them once migration completes.
- For starter libraries, maintaining separate artifacts for Boot 3 and Boot 4 is safer than cramming both APIs into one artifact.
- Only declare completion after building, testing, packaging, and starting the actual artifact all succeed.

### Official documentation

- Spring Boot 3.0 Migration Guide — Java 17, Spring Framework 6, Jakarta EE, imports file, and dependency changes: https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-3.0-Migration-Guide
- Spring Boot 4.0 Migration Guide — module/package changes, starter/test starter, Jackson 3, and package migration: https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-4.0-Migration-Guide
- Spring Boot 4.0 System Requirements — Java, Spring Framework, and build tools: https://docs.spring.io/spring-boot/4.0/system-requirements.html
- Upgrading Spring Boot — upgrade guide by line: https://docs.spring.io/spring-boot/3.4/upgrading.html
- Spring Boot Build Systems — dependency management and BOM: https://docs.spring.io/spring-boot/3.5/reference/using/build-systems.html
