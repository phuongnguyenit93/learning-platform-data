# Verifying Compatibility Across Spring Boot, Spring Data REST, Spring HATEOAS, and Jackson

A Spring Data REST application does not depend on a single library. The pipeline that exports repositories as REST APIs flows through Spring Boot, Spring Framework, Spring Data REST, Spring HATEOAS, and a JSON library such as Jackson. These components are coupled through APIs, auto-configuration, message converters, and transitive dependencies.

Therefore, compatibility checks must cover the entire dependency graph and live runtime responses. Seeing a Gradle/Maven build succeed is not sufficient to conclude that HAL representations, serialization, or Spring Data REST endpoints work properly.

## 1. Understanding Component Roles and Relationships

| Component | Role | What to Check |
|---|---|---|
| Spring Boot | Manages application config, starters, and dependency versions | Boot version, Java baseline, BOM, and auto-configuration |
| Spring Framework | Container foundation, MVC, converters, and transactions | Version matching the Spring Boot release line |
| Spring Data REST | Exports Spring Data repositories as REST resources via WebMVC | REST module compatible with the Spring Data release train and Boot |
| Spring HATEOAS | Builds hypermedia, HAL links, EntityModel, and CollectionModel | HATEOAS APIs and HAL serializers compatible with Spring Data REST |
| Jackson | Serializes/deserializes JSON representations | Version, packages, mappers, modules, and custom serializers |

The response flow can be visualized as follows:

~~~text
Spring Boot
    |
    +-- Spring Framework / Spring MVC
    |
    +-- Spring Data REST
    |       |
    |       +-- Spring Data repository
    |       |
    |       +-- Spring HATEOAS / HAL
    |
    +-- JSON integration
            |
            +-- Jackson
                    |
                    +-- JSON serialization/deserialization
~~~

Spring Data REST exports repositories as REST resources via Spring WebMVC. HATEOAS supplies the hypermedia and representation abstractions used by the REST API. Jackson handles converting objects to JSON and reading JSON into objects according to application configuration.

A compatibility error at any layer can prevent the application from starting, cause requests to fail, or alter JSON/HAL responses unexpectedly.

## 2. Choosing Spring Boot as the Starting Point

When using Spring Boot, choose a specific Boot version first. Then rely on the dependency management provided by that version to select the versions of Spring Framework, Spring Data REST, Spring HATEOAS, and Jackson.

Spring Boot publishes the spring-boot-dependencies BOM. This BOM declares dependency versions selected and tested together for a Boot release. When a dependency is managed by the BOM, the application typically only declares group/artifact without specifying a separate version.

Principles:

1. Lock down the Spring Boot release line and patch version in use.
2. Consult the managed dependency versions table for that exact Boot release line.
3. Let the BOM manage Spring and Jackson dependencies if they are already in the BOM.
4. Override a version only when there is a clear, verified, and tested compatibility reason.
5. Do not randomly mix the latest versions of individual libraries.

No "latest" pair of versions is automatically compatible with every application. A newer Spring Data REST release may require Spring Framework or Spring HATEOAS APIs newer than what an older Boot release manages.

### Why Shouldn't You Pick Individual Versions Manually?

Suppose a project uses Spring Boot 3.x but manually declares a Spring HATEOAS version from a newer line. The build may still resolve dependencies, yet at runtime you may encounter:

- NoSuchMethodError: compiled code calls a method that does not exist in the class loaded at runtime.
- NoClassDefFoundError or ClassNotFoundException: a class required by a component is absent from the runtime classpath.
- ClassCastException: incompatible types or class loaders.
- Bean initialization or auto-configuration failures.
- HAL links, JSON fields, or content negotiation differing from the contract clients rely on.

These errors do not necessarily appear at compile time. They may only surface when the application context starts or when a specific endpoint is called.

## 3. Using the Spring Boot BOM in Gradle

With Gradle Groovy DSL, the Spring Boot plugin can integrate dependency management:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-rest'

    // Only add when the application directly builds hypermedia
    // representations beyond what Spring Data REST provides.
    implementation 'org.springframework.boot:spring-boot-starter-hateoas'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

The versions in this example illustrate declarations for a project on the Boot 3.3 line. Use the patch version and plugin version chosen by your organization; do not copy example versions verbatim into a different Boot project.

When the dependency management plugin is applied, Spring Boot imports the corresponding BOM automatically. Therefore, you do not need to declare explicit versions for spring-data-rest-webmvc, spring-hateoas, or Jackson when the BOM already manages them.

Gradle native BOM support can be used instead of the dependency management plugin:

~~~groovy
plugins {
    id 'java'
}

dependencies {
    implementation platform(
        'org.springframework.boot:spring-boot-dependencies:3.3.13'
    )

    implementation 'org.springframework.boot:spring-boot-starter-data-rest'
    implementation 'org.springframework.boot:spring-boot-starter-hateoas'
}
~~~

Pick one consistent dependency management strategy for the project. If the build already imports the Boot BOM at the root or in a convention plugin, do not import a different BOM version in a subproject.

Spring Data REST already brings in the dependencies needed for repository exporting. Only declare the HATEOAS starter separately when application code directly uses HATEOAS APIs or needs separate integration configuration; avoid adding dependencies merely because you see their names in the dependency tree.

## 4. Using the Spring Boot BOM in Maven

When using spring-boot-starter-parent, dependency management is inherited from the parent:

~~~xml
<parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.3.13</version>
    <relativePath/>
</parent>

<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-data-rest</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-hateoas</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

If you cannot use the Boot parent, import spring-boot-dependencies under dependencyManagement:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-dependencies</artifactId>
            <version>3.3.13</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

After importing the BOM, managed dependencies can omit versions. If there are multiple BOMs or dependency management blocks in other parents, check precedence rules and the effective POM to see the final resolved version.

## 5. Checking Actual Versions in the Dependency Graph

Build files only show declared dependencies. The dependency graph reveals which versions actually resolve after considering BOMs, constraints, transitive dependencies, resolution strategies, and overrides.

### With Gradle

Inspect the full runtime classpath:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
~~~

Inspect where a specific dependency resolves from:

~~~bash
./gradlew dependencyInsight --dependency spring-data-rest-webmvc --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-hateoas --configuration runtimeClasspath
./gradlew dependencyInsight --dependency jackson-databind --configuration runtimeClasspath
~~~

On Windows you can use gradlew.bat instead of ./gradlew.

dependencyInsight output helps identify:

- The final selected version.
- Which dependency pulls the library into the graph.
- Which versions were rejected or conflicted.
- Which constraint, platform, or rule determined the version.

For Jackson 3, also search for artifacts under the tools.jackson group; do not check only com.fasterxml.jackson.core:jackson-databind.

### With Maven

Inspect the dependency tree:

~~~bash
mvn dependency:tree -Dverbose
~~~

You can filter output to the dependency groups you want to inspect:

~~~bash
mvn dependency:tree -Dincludes=org.springframework.data:*,org.springframework.hateoas:*,com.fasterxml.jackson.core:*,tools.jackson.core:*
~~~

Check the effective POM when the project has parents or multiple BOMs:

~~~bash
mvn help:effective-pom
~~~

Do not look solely at versions inside pom.xml. Resolved versions can come from parent POMs, BOM imports, or higher-level dependency management.

### Creating an Inventory Table

After inspecting the dependency tree, record at minimum:

| Artifact | Expected Version | Runtime Version | Management Source |
|---|---|---|---|
| Spring Boot | Per project baseline | Per dependency graph | Boot plugin / BOM |
| Spring Framework | Per Boot BOM | Per dependency graph | Boot BOM |
| Spring Data REST | Per Boot BOM | Per dependency graph | Boot BOM |
| Spring HATEOAS | Per Boot BOM | Per dependency graph | Boot BOM |
| Jackson core/databind | Per Boot's Jackson line | Per dependency graph | Boot BOM or migration config |

If the runtime version differs from the managed version, determine which dependency caused the difference and why. Do not ignore it just because the build succeeds.

## 6. Understanding Jackson Differences Between Spring Boot 3 and Spring Boot 4

This is a critical upgrade point because the change goes beyond version numbers. Spring Boot 4 switches to Jackson 3 as the default JSON library; Spring Boot 3 uses Jackson 2 by default.

| Item | Spring Boot 3.x | Spring Boot 4.x |
|---|---|---|
| Default JSON mapper | Jackson 2 | Jackson 3 |
| Primary mapper | ObjectMapper | JsonMapper |
| Core/databind packages | com.fasterxml.jackson.* | tools.jackson.* |
| Annotation package | com.fasterxml.jackson.annotation | Still uses com.fasterxml.jackson.annotation |
| Auto-configuration | Jackson 2 | Jackson 3 |
| Jackson configuration | spring.jackson.* | New Jackson 3 properties, e.g., spring.jackson.* and corresponding JSON properties per Boot 4 docs |
| Component annotations | @JsonComponent, @JsonMixin | @JacksonComponent, @JacksonMixin |

Key changes when moving to Boot 4:

- The group ID and package of most of Jackson 2 move from com.fasterxml.jackson to tools.jackson.
- A notable exception is Jackson annotations, which continue using the com.fasterxml.jackson.core and com.fasterxml.jackson.annotation group/package.
- ObjectMapper in the Jackson 2 ecosystem is replaced by JsonMapper in the Jackson 3 integration.
- Several serializer/deserializer classes and customizers are renamed.
- @JsonComponent and @JsonMixin are renamed to @JacksonComponent and @JacksonMixin.
- Some JSON properties move to new namespaces.

Boot 4 still provides a Jackson 2 compatibility module for transition periods, but it is marked deprecated and should not be treated as a long-term solution. If a third-party library does not yet support Jackson 3, verify its requirements and upgrade plan before deciding to retain Jackson 2.

Do not arbitrarily mix classes from both Jackson generations in the same API. For example, a method accepting com.fasterxml.jackson.databind.ObjectMapper cannot be directly replaced with tools.jackson.databind.json.JsonMapper merely by changing dependency versions; this is a package and type change requiring code updates.

## 7. Verifying Spring Data REST and Spring HATEOAS

Spring Data REST exports repository resources via Spring WebMVC. Hypermedia responses typically use HAL and representation types from Spring HATEOAS.

When upgrading versions, verify that:

- The application context starts with the current auto-configuration.
- Repositories are exported under the expected base path and collection/item resources.
- HAL responses still include _links, _embedded, and the relations clients need.
- Content negotiation still returns representations matching the Accept header.
- Pagination and sorting preserve expected metadata, links, and query parameters.
- Projections, excerpts, and association links still serialize properly.
- Custom controllers, assemblers, EntityModel, CollectionModel, and RepresentationModel still compile and function.
- Jackson modules, mixins, and custom serializers are still registered with the mapper actually in use.

Example smoke test request:

~~~http
GET /api/products
Accept: application/hal+json
~~~

Responses should be verified against the actual contract, for example:

~~~json
{
  "_embedded": {
    "products": [
      {
        "id": 1,
        "name": "Keyboard"
      }
    ]
  },
  "_links": {
    "self": {
      "href": "http://localhost:8080/api/products"
    }
  }
}
~~~

The example above is a simplified illustrative representation. Actual content, relation names, and links depend on the repository, configuration, and entity model.

Spring Boot provides auto-configuration for Spring HATEOAS in suitable applications. If enabling @EnableHypermediaSupport manually, carefully review its impact on auto-configuration and mapper customization. In modern Spring Boot configurations, avoid adding this annotation out of habit if auto-configuration already meets requirements.

Note that the HATEOAS starter targets Spring MVC; do not combine it with WebFlux as if both stacks share the same configuration model. For WebFlux, use the appropriate HATEOAS dependency according to Boot's documentation.

## 8. Common Compatibility Errors

| Symptom | Possible Cause | How to Check |
|---|---|---|
| NoSuchMethodError in Spring Data or HATEOAS | Spring modules from different generations or versions | dependencyInsight / dependency:tree |
| ClassNotFoundException with Jackson | Code imports a Jackson package from a different generation | Check imports and runtime classpath |
| App fails to start due to mapper bean | Incompatible auto-configuration or customizer | Read condition evaluation report and inspect mapper beans |
| Response is no longer HAL as expected | Content negotiation, media type, or HATEOAS config changed | Test with Accept: application/hal+json |
| Custom serializer is not invoked | Module/annotation registration or a different mapper is active | Check active mapper and run serialization tests |
| JSON date/time format changed | Jackson module or properties changed | Contract tests for date/time |
| Fields unexpectedly appear or disappear | Visibility, mixin, naming strategy, or annotation changes | Snapshot/JSON path tests |
| Links or relations changed | HATEOAS model, assembler, or configuration changed | Check HAL links and relation names |
| Fails only at runtime while compile succeeds | Transitive dependency conflict | Inspect runtimeClasspath, not just compileClasspath |

Do not fix errors by randomly adding a latest Jackson or HATEOAS version. First locate which dependency introduces the conflicting version, determine which BOM applies, and compare against Boot's official dependency management.

## 9. Safe Upgrade Process

Upgrades should proceed step by step so you can pinpoint which change causes an error:

1. Record the baseline: current Java, Spring Boot, Spring Framework, Spring Data REST, HATEOAS, and Jackson versions.
2. Select target Boot: identify the target Boot release line and its JDK requirements.
3. Read migration guides: review upgrade guides for each relevant major/minor version change.
4. Compare BOMs: compare managed dependency versions between baseline and target; identify libraries changing generations.
5. Remove unnecessary version overrides: let the BOM manage Spring and Jackson dependencies whenever possible.
6. Re-resolve dependencies: run dependency tree/insight to detect conflicts and forced versions.
7. Apply code migrations: address deprecated/removed APIs, package changes, and mapper changes—especially when moving from Jackson 2 to Jackson 3.
8. Build and test: run compile, unit tests, integration tests, and application context checks.
9. Verify API contracts: exercise repository endpoints, HAL, pagination, associations, projections, and custom JSON types.
10. Trial deployment: inspect logs, error rates, and responses in a production-like environment before rollout.

Do not upgrade Boot, Spring Data REST, HATEOAS, and Jackson as four independent changes in one pass without reason. Upgrading Boot first typically gives you a pre-tested set of dependencies together; handle libraries outside the BOM separately afterward.

## 10. Minimum Post-Upgrade Test Suite

A compatibility test suite should include these groups:

**Startup and dependencies**

- Application context starts successfully.
- No missing beans or unexpectedly duplicated mapper beans.
- Runtime dependency tree contains no unintended Spring/Jackson version overrides.

**Spring Data REST**

- Collection GET returns expected resources.
- Item GET, POST, PUT/PATCH, and DELETE operate per configuration.
- Search/finder resources are exported correctly.
- Association links can be read and updated.
- Pagination, sorting, and projections remain accurate.

**Spring HATEOAS/HAL**

- Responses have the expected media type.
- _links and _embedded exist with the right relations.
- Self, next/prev, and association links are valid.
- Custom assemblers build representations without errors.

**Jackson**

- Serialize and deserialize key entities/DTOs.
- Dates, times, enums, UUIDs, numbers, and nulls preserve expected formats.
- Custom serializers/deserializers and mixins remain registered.
- Entity relationships do not cause unintended serialization cycles.
- Sensitive fields remain hidden per the API contract.

**Client compatibility**

- Compare JSON/HAL responses against the current contract.
- Test clients using proper Accept and Content-Type headers.
- If the API changes representations, assess impact on legacy clients before release.

You can use @SpringBootTest to verify auto-configuration and MockMvc or HTTP integration tests to verify endpoints. Direct mapper serialization tests cannot replace HTTP tests because the request pipeline also involves content negotiation, message converters, and Spring Data REST representation processing.

## 11. Compatibility Sign-Off Checklist

- [ ] Spring Boot version and Java baseline locked.
- [ ] Spring Framework belongs to the Boot-managed generation.
- [ ] Spring Data REST pulled from the right BOM/release train.
- [ ] Spring HATEOAS pulled from the right BOM without arbitrary overrides.
- [ ] Jackson groups/packages match the Boot major version in use.
- [ ] No unintended dual mappers or dual Jackson generations in use.
- [ ] Runtime dependency tree inspected, not just declared files.
- [ ] Application context starts cleanly.
- [ ] Repository REST endpoints operate over HTTP.
- [ ] HAL links, embedded resources, and content negotiation verified.
- [ ] Jackson custom modules, mixins, and date/time serialization tested.
- [ ] Client API contracts verified after upgrade.
- [ ] Migration guides and release notes reviewed for the target major/minor version.

## 12. Official Reference Sources

Do not use a static version table from a blog post or old answer to decide dependencies. Check the exact patch version of Spring Boot you selected:

- Spring Boot — Managed Dependency Versions: https://docs.spring.io/spring-boot/appendix/dependency-versions/
- Spring Boot — Gradle Dependency Management: https://docs.spring.io/spring-boot/gradle-plugin/managing-dependencies.html
- Spring Data REST Reference: https://docs.spring.io/spring-data/rest/reference/
- Spring Boot 3.3 — JSON and Jackson: https://docs.spring.io/spring-boot/3.3/reference/features/json.html
- Spring Boot 4.0 — JSON and Jackson: https://docs.spring.io/spring-boot/4.0/reference/features/json.html
- Spring Boot 4.0 Migration Guide: https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-4.0-Migration-Guide
- Spring Boot Supported Versions: https://github.com/spring-projects/spring-boot/wiki/Supported-Versions
