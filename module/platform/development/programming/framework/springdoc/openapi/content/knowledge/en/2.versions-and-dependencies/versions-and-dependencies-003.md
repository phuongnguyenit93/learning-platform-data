# Springdoc v1, v2, and v3 Branches and Their Corresponding Spring Boot Generations

springdoc-openapi has three major branches used for three different Spring Boot generations. The branch selection rule is:

- Spring Boot 1.x and 2.x: springdoc-openapi v1.
- Spring Boot 3.x: springdoc-openapi v2.
- Spring Boot 4.x: springdoc-openapi v3.

This is a compatibility relationship between the library and the Spring Boot platform, not the OpenAPI specification version. For example, springdoc 3.2.0 can still generate a document with the openapi field set to 3.1.0. The number 3.2.0 is the Java library version; the value in the openapi field is the specification version that the document follows.

Choosing the right major is only the first step. Each minor line of Spring Boot has specific springdoc versions built and tested by the project. Do not take the latest springdoc version and attach it to any arbitrary Spring Boot version of the same major.

## 1. Branch Selection Rule

| Spring Boot Generation | springdoc Branch | Primary Documentation |
|---|---|---|
| Boot 1.x and 2.x | v1.x | springdoc.org/v1 |
| Boot 3.x | v2.x | springdoc.org/v2 |
| Boot 4.x | v3.x | springdoc.org |

A quick mnemonic: Boot 2 uses springdoc 1, Boot 3 uses springdoc 2, Boot 4 uses springdoc 3. Do not apply this number pairing to the OpenAPI Specification.

Springdoc automatically analyzes Spring applications, controllers, configuration, data types, and annotations to generate OpenAPI JSON/YAML; UI starters also provide an interactive interface. The majors are separated along platform changes in Spring Boot, Spring Framework, Java, and Jakarta EE.

## 2. Detailed Compatibility Matrix

### Spring Boot 1.x and 2.x: springdoc v1

v1 is the branch for Spring Boot 1 and 2. The last published open-source version for this generation is 1.8.0. The project also notes a separate extended support offering for organizations needing support beyond the open-source lifecycle.

Minimum baselines published by the v1 documentation:

| Spring Boot | Minimum recorded springdoc version |
|---|---|
| 2.7.x | 1.6.11+ |
| 2.6.x | 1.6.0+ |
| 2.5.x | 1.5.9+ |
| 2.4.x | 1.5.0+ |
| 2.3.x | 1.4.0+ |
| 2.2.x | 1.2.1+ |
| 2.0.x | 1.0.0+ |
| 1.5.x | 1.6.11+ at the highest compatibility baseline listed alongside Boot 2.7.x |

For Boot 2.7 applications using v1, 1.8.0 is the final open-source choice of this branch. Do not use v1 for Boot 3 just because the application still compiles some classes; Boot 3 moved to the Jakarta namespace and springdoc v2 is the branch built for that platform.

### Spring Boot 3.x: springdoc v2

v2 is designed for Spring Boot 3, Spring Framework 6, and Java 17 or higher. The detailed matrix published by the v2 documentation:

| Spring Boot | Built springdoc range |
|---|---|
| 3.5.x | 2.8.x to 2.10.x |
| 3.4.x | 2.7.x to 2.8.x |
| 3.3.x | 2.6.x |
| 3.2.x | 2.3.x to 2.5.x |
| 3.1.x | 2.2.x |
| 3.0.x | 2.0.x to 2.1.x |

As of 20-11-2026, the v2 documentation lists 2.10.0 as the latest stable version of the branch. However, that does not mean 2.10.0 is the right choice for every Boot 3.x release. For example, the matrix only lists Boot 3.5.x with the range 2.8.x–2.10.x; Boot 3.2.x is confirmed with 2.3.x–2.5.x.

### Spring Boot 4.x: springdoc v3

v3 is the branch for Spring Boot 4 and Spring Framework 7. Current official matrix:

| Spring Boot | Built springdoc range |
|---|---|
| 4.1.x | 3.1.x to 3.2.x |
| 4.0.x | 3.0.x |

As of 20-11-2026, 3.2.0 is the latest stable version published in springdoc documentation. This version is built on Spring Boot 4.1.2 and the matrix confirms the Boot 4.1.x line.

Spring Boot 4.2.0 has appeared in the stable list of Spring Boot documentation, but the current springdoc matrix does not yet list the Boot 4.2.x line. Therefore, springdoc 3.2.0 cannot yet be considered a combination confirmed by springdoc for Boot 4.2.x. If a project wants to use this pair, check newer release notes or a newer matrix and run your own integration tests before finalizing for production.

### How to Read the Matrix

A row like Boot 3.5.x with springdoc 2.8.x–2.10.x means the project built the springdoc versions in that range against the corresponding Boot branch. It is not a claim that every arbitrary patch dependency combination is compatible.

When choosing a version:

1. Identify the exact Spring Boot major and minor.
2. Find the corresponding row in the springdoc matrix.
3. Choose a springdoc version within the published range.
4. Check the Java runtime and Spring Framework managed by Boot.
5. Inspect the dependency tree after resolution.
6. Run tests to start the application, download OpenAPI JSON/YAML, and check Swagger UI if used.

If a Boot version does not yet appear in the matrix, do not infer compatibility from the fact that Maven or Gradle can download the artifact.

## 3. Why Does springdoc Separate Majors by Spring Boot?

springdoc is not just a JSON file generator. The library integrates deeply with Spring:

- Auto-configuration and bean creation conditions.
- Spring MVC or Spring WebFlux.
- Controller mappings and functional endpoints.
- Message converters, codecs, and serialization.
- Bean Validation.
- Spring Security.
- Spring Data, HATEOAS, and Actuator.
- Swagger Core, Swagger UI, and auxiliary modules.

When Spring Boot bumps a major version, the underlying platforms also change. springdoc needs a matching branch to compile, start up, and read metadata accurately from the new runtime.

### Three Platform Generations

| Platform | Spring Boot | Spring Framework | Important Namespace |
|---|---|---|---|
| Legacy generation | 1.x/2.x | 4.x/5.x depending on Boot line | Java EE with javax |
| Boot 3 generation | 3.x | 6.x | Jakarta EE with jakarta |
| Boot 4 generation | 4.x | 7.x | Next-gen Jakarta EE and corresponding platform APIs |

Spring Boot 3 migrated managed Java EE APIs to Jakarta EE 10, including changing packages from javax to jakarta. Spring Boot 4 continues building on Spring Framework 7 and newer Jakarta generations. These changes explain why springdoc needs separate major branches.

## 4. Java and Platform Requirements to Check

Do not only look at the springdoc version. Check the Java and Spring Framework versions required by Spring Boot:

| Platform | Platform Requirement to Remember |
|---|---|
| Spring Boot 2.x | Java requirement depends on minor line; older lines can run on Java 8 |
| Spring Boot 3.x | Java 17 or higher; Spring Framework 6 |
| Spring Boot 4.x | Java 17 or higher; Spring Framework 7 |

Spring Boot 3.0 raised the baseline to Java 17 and moved to Jakarta EE 10. Spring Boot 4.0 also requires at least Java 17 and Spring Framework 7.0. Third-party libraries may require a higher Java version, so check the documentation of each starter and plugin.

For example, an old Boot 2 application still running Java 8 cannot simply swap its dependency to springdoc v2. You must upgrade the Boot/Java platform first, then choose the corresponding springdoc branch.

## 5. Choosing a Starter by Web Stack and UI Needs

Modern majors use starter artifact groups. Two independent factors must be chosen:

1. Does the application use Spring MVC or Spring WebFlux?
2. Do you only need OpenAPI endpoints or also the Swagger UI interface?

| Need | Spring MVC | Spring WebFlux |
|---|---|---|
| Generate OpenAPI JSON/YAML only | springdoc-openapi-starter-webmvc-api | springdoc-openapi-starter-webflux-api |
| Generate docs and include Swagger UI | springdoc-openapi-starter-webmvc-ui | springdoc-openapi-starter-webflux-ui |

In v1, artifact names had older forms like springdoc-openapi-ui or springdoc-openapi-webflux-ui. From v2 onward, the core modules were renamed to starter names. The v3 branch continues using the starter group corresponding to Boot 4.

Default endpoint examples remain familiar:

~~~text
/v3/api-docs
/v3/api-docs.yaml
/swagger-ui.html
~~~

Paths can be customized via springdoc configuration. Keeping familiar endpoints does not mean dependencies, packages, or auto-configuration are identical across majors.

## 6. Dependency Examples for Each Generation

### Boot 2.7 with springdoc v1

Maven example for a Spring MVC application:

~~~xml
<dependency>
    <groupId>org.springdoc</groupId>
    <artifactId>springdoc-openapi-ui</artifactId>
    <version>1.8.0</version>
</dependency>
~~~

If using WebFlux, v1 has a separate artifact springdoc-openapi-webflux-ui. Verify the exact artifact for the web stack.

### Boot 3.5 with springdoc v2

Maven example:

~~~xml
<dependency>
    <groupId>org.springdoc</groupId>
    <artifactId>springdoc-openapi-starter-webmvc-ui</artifactId>
    <version>2.10.0</version>
</dependency>
~~~

If the application uses WebFlux, replace the artifact with springdoc-openapi-starter-webflux-ui. If you only need JSON/YAML for CI, use the corresponding webmvc-api or webflux-api starter so Swagger UI is not packaged.

### Boot 4.1 with springdoc v3

Maven example:

~~~xml
<dependency>
    <groupId>org.springdoc</groupId>
    <artifactId>springdoc-openapi-starter-webmvc-ui</artifactId>
    <version>3.2.0</version>
</dependency>
~~~

For WebFlux, use springdoc-openapi-starter-webflux-ui. For API-only, use the starter-webmvc-api or starter-webflux-api artifact.

The versions in these examples illustrate pairs listed in the published matrix at the time of writing. Update according to the latest matrix when starting a project or upgrading.

## 7. Key Migration Differences from v1 to v2

Changing majors from v1 to v2 is not just editing a version number. Official migration documentation explicitly states that modules were renamed and several packages/classes moved locations.

### Artifact Renames

| v1 Artifact | v2 Artifact |
|---|---|
| springdoc-openapi-common | springdoc-openapi-starter-common |
| springdoc-openapi-webmvc-core | springdoc-openapi-starter-webmvc-api |
| springdoc-openapi-webflux-core | springdoc-openapi-starter-webflux-api |
| springdoc-openapi-ui | springdoc-openapi-starter-webmvc-ui |
| springdoc-openapi-webflux-ui | springdoc-openapi-starter-webflux-ui |
| springdoc-openapi-data-rest | Integrated via starter-common |
| springdoc-openapi-hateoas | Integrated via starter-common |
| springdoc-openapi-security | Integrated via starter-common |
| springdoc-openapi-kotlin | Integrated via starter-common |
| springdoc-openapi-groovy | Integrated via starter-common |
| springdoc-openapi-javadoc | Integrated via starter-common |

Do not keep both v1 and v2 artifacts in the same application. Remove old modules that were replaced before adding new starters, then inspect the dependency tree to avoid duplicate classes or two auto-configurations running at once.

### Package and Class Renames

| Old Name | New Name |
|---|---|
| org.springdoc.core.SpringDocUtils | org.springdoc.core.utils.SpringDocUtils |
| org.springdoc.api.annotations.ParameterObject | org.springdoc.core.annotations.ParameterObject |
| org.springdoc.core.GroupedOpenApi | org.springdoc.core.models.GroupedOpenApi |
| org.springdoc.core.customizers.OpenApiCustomiser | org.springdoc.core.customizers.OpenApiCustomizer |
| org.springdoc.core.Constants | org.springdoc.core.utils.Constants |
| org.springdoc.core.SwaggerUiConfigParameters | org.springdoc.core.properties.SwaggerUiConfigParameters |

Notably, the OpenApiCustomiser class spelling changed to OpenApiCustomizer. Imports in customizers, configuration classes, and tests must be updated together.

### Switching from javax to jakarta

Spring Boot 3 migrated from the Java EE namespace to the Jakarta EE namespace. For example:

~~~java
// Before upgrading to Spring Boot 3
import javax.validation.Valid;
import javax.validation.constraints.NotBlank;
import javax.servlet.http.HttpServletRequest;

// After upgrading to Spring Boot 3
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.servlet.http.HttpServletRequest;
~~~

This is a Spring Boot/Jakarta platform change, not a rename done specifically by springdoc. DTOs, controllers, filters, and integration libraries all need the matching namespace.

## 8. Upgrading from v2 to v3 When Moving to Spring Boot 4

Both v2 and v3 use starter names following the springdoc-openapi-starter-* pattern. When moving from v2 to v3, the focus is migrating the Boot 3/Spring Framework 6 platform to Boot 4/Spring Framework 7, then picking the springdoc v3 version confirmed for the new Boot minor line.

There is no full artifact/package rename table from v2 to v3 similar to the v1-to-v2 documentation. Therefore, do not invent an undocumented package rename list. Instead:

1. Read the Spring Boot 4 migration guide and release notes.
2. Upgrade the Java toolchain and Spring Boot plugin.
3. Update dependency management for Boot 4.
4. Switch springdoc to v3 within the published compatible range.
5. Verify the MVC/WebFlux starter and integration modules.
6. Recompile customizers, configurations, and tests using springdoc APIs.
7. Check changes in Spring Framework 7, Jakarta APIs, serialization, and security.
8. Regenerate the OpenAPI document and compare it with the baseline.

The starter names webmvc-ui, webflux-ui, webmvc-api, and webflux-api continue to be used in v3 documentation. However, you must take a v3 version appropriate for the Boot 4 minor line, not a v2 version just because the artifact names look identical.

## 9. What Does Not Change Across Majors

Upgrading the library major does not mean redesigning the entire API contract. The following concepts keep the same role:

- Controller mappings are read to produce paths and operations.
- Swagger/OpenAPI annotations describe operations, parameters, schemas, responses, and security.
- The OpenAPI document can be exported as JSON or YAML.
- Swagger UI reads the document to render and test requests.
- GroupedOpenApi is used to split documentation into groups.
- OpenApiCustomizer is used to modify the generated document.

What must be distinguished is that springdoc's Java API and integration layer can change across majors, while the HTTP contract consumed by clients can remain unchanged.

## 10. Managing Versions Consistently in Maven

Declare only one springdoc starter matching the web stack. For auxiliary modules, use the same version as the starter or the dependency management provided by the project.

Example setting the version in a property:

~~~xml
<properties>
    <springdoc.version>2.10.0</springdoc.version>
</properties>

<dependencies>
    <dependency>
        <groupId>org.springdoc</groupId>
        <artifactId>springdoc-openapi-starter-webmvc-ui</artifactId>
        <version>${springdoc.version}</version>
    </dependency>
</dependencies>
~~~

Update both the property and dependency version according to the Boot matrix in use. Do not leave webmvc-ui on one version while starter-common or an auxiliary module is on a different version.

If the project manages versions centrally through a Maven BOM or internal parent POM, keep the springdoc version in one place and inspect the dependency tree after resolution.

## 11. Managing Versions Consistently in Gradle

Declare the version in one place, such as a version catalog:

~~~toml
[versions]
springdoc = "2.10.0"

[libraries]
springdoc-webmvc-ui = { module = "org.springdoc:springdoc-openapi-starter-webmvc-ui", version.ref = "springdoc" }
~~~

Then use the alias in the build:

~~~kotlin
dependencies {
    implementation(libs.springdoc.webmvc.ui)
}
~~~

For Boot 4, change the version catalog to a springdoc v3 version in the compatibility matrix. If multiple apps with different Boot majors live in one repository, each app may need its own version catalog or dependency constraint.

## 12. Avoiding Mixed Majors and Overriding Transitive Dependencies

Common mistakes when upgrading versions:

- A springdoc v1 module left behind while v2/v3 starters were added.
- Using springdoc 2.x with Spring Boot 4 or springdoc 3.x with Spring Boot 3.
- Pulling in a different version of swagger-core or swagger-annotations than the one managed by springdoc.
- Having both WebMVC UI and WebFlux UI in one app without an explicit reason.
- Adding a standalone swagger-ui WebJar and accidentally overriding assets provided by the springdoc starter.
- Using a snapshot or prerelease version for production without control.

Inspect the dependency tree:

~~~bash
# Maven
mvn dependency:tree -Dincludes=org.springdoc,io.swagger.core.v3,org.webjars

# Gradle
./gradlew dependencyInsight --dependency springdoc --configuration runtimeClasspath
./gradlew dependencyInsight --dependency swagger-core --configuration runtimeClasspath
./gradlew dependencyInsight --dependency swagger-annotations --configuration runtimeClasspath
~~~

If you see two springdoc majors or multiple swagger-core versions, trace which dependency brings them in. Fix the dependency declaration or apply targeted exclusions; do not add a global override before knowing which module needs that version.

## 13. Verifying the Application After Switching Branches

After upgrading dependencies, verify at a minimum:

1. Application context starts without errors.
2. No NoSuchMethodError, ClassNotFoundException, or NoClassDefFoundError related to springdoc/swagger-core.
3. /v3/api-docs returns valid JSON.
4. /v3/api-docs.yaml returns valid YAML if the YAML endpoint is enabled.
5. Swagger UI loads the right document if using the UI starter.
6. GroupedOpenApi still generates all groups.
7. OperationIds, paths, parameters, and schemas have not disappeared.
8. Security schemes and response codes remain accurate.
9. The OpenAPI document is validated and semantically diffed against the baseline.
10. Runtime tests for critical requests/responses still PASS.

Do not rely only on the Swagger UI page opening. The UI can load HTML successfully while the JSON document fails or misses operations.

## 14. Checking Changes That Can Alter the Document After Upgrades

Even when the HTTP API does not change, the generated schema can change due to upgrades in Spring Boot, swagger-core, Jackson, validation, or springdoc.

Review:

- Required and nullable flags of properties.
- Numeric types, date/time types, and formats.
- Enums and schema component names.
- Generic wrappers, Page, Pageable, and HATEOAS models.
- Request parameters inferred from method parameter names.
- Response codes from @ResponseStatus and @ControllerAdvice.
- Security requirements at root and operation levels.
- Server URL behind proxy/context path.
- OpenAPI version in the openapi field.

Some issues with parameters not being generated can be related to Spring Boot 3.2 changing parameter name discovery. Springdoc documentation recommends enabling the -parameters compiler option in Maven:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-compiler-plugin</artifactId>
    <configuration>
        <parameters>true</parameters>
    </configuration>
</plugin>
~~~

If the document changes, compare JSON/YAML and determine whether the change came from controllers, DTOs, Spring Boot, springdoc, or swagger-core before updating the baseline.

## 15. Upgrade Roadmap from v1 to v2

For Boot 2 applications:

1. Finalize the target Boot minor and Java runtime.
2. Upgrade the application platform to Spring Boot 3 and Java 17 following the migration guide.
3. Migrate Java EE imports from javax to jakarta for Jakarta EE APIs.
4. Remove springdoc v1 artifacts.
5. Add the v2 starter matching MVC or WebFlux.
6. Migrate springdoc packages/classes per the migration table.
7. Update tests and OpenAPI configuration.
8. Build, start up, fetch JSON/YAML, and check Swagger UI.
9. Review semantic diff and runtime contract tests.
10. Release only when both the dependency graph and API contract pass.

Do not upgrade springdoc v1 to v2 while staying on Boot 2. If you cannot upgrade to Boot 3 yet, keep the appropriate v1 branch and plan the platform migration separately.

## 16. Upgrade Roadmap from v2 to v3

For Boot 3 applications:

1. Identify the target Boot 4 minor line.
2. Check Java 17+ and Spring Framework 7 requirements.
3. Read the Spring Boot 4 migration guide for the application.
4. Update dependency management and build plugins.
5. Replace springdoc v2 with a v3 version confirmed for that Boot minor.
6. Keep the matching webmvc or webflux starter.
7. Recompile customizers and springdoc integration code.
8. Check configuration, auto-configuration, and security.
9. Generate OpenAPI JSON/YAML, validate, and run semantic diff.
10. Run integration tests on the Boot 4 runtime.

If the Boot minor is not yet in the springdoc matrix, wait for a supporting release or perform a dedicated tested compatibility evaluation. Do not label it production-ready just because the build succeeds.

## 17. Choosing a Branch by Scenario

| Scenario | Selection Approach |
|---|---|
| Legacy app running on Boot 2.7 | Use springdoc v1 within the supported range; 1.8.0 is the last OSS release |
| Project upgrading Boot 2 to Boot 3 | Switch to springdoc v2 after handling Jakarta and Java 17 |
| New project on Boot 3.5 | Choose springdoc 2.8.x–2.10.x per matrix; 2.10.0 is the latest stable at time of writing |
| Project on Boot 4.0 | Choose springdoc 3.0.x |
| Project on Boot 4.1 | Choose springdoc 3.1.x–3.2.x |
| Project on Boot 4.2.0 | Current matrix has not confirmed yet; check newer springdoc releases before finalizing |
| App only needs OpenAPI for CI | Choose API-only starter, no UI starter needed |
| App needs Swagger UI | Choose UI starter matching MVC/WebFlux |

## 18. Troubleshooting by Symptom

| Symptom | Common Cause | Resolution |
|---|---|---|
| Cannot resolve starter | Wrong artifact name or version line | Cross-check starter by major and web stack |
| Boot 3 reports missing javax/jakarta class | Legacy Java EE library remaining or Jakarta migration incomplete | Check imports and dependency tree |
| Boot 3 fails with springdoc v1 | Wrong major used | Switch to springdoc v2 |
| Boot 4 fails with springdoc v2 | Using branch not meant for Boot 4 | Switch to v3 within the matrix |
| NoSuchMethodError in swagger-core | Transitive dependency overridden | Use version managed by springdoc and check dependency tree |
| Old GroupedOpenApi class not found | Package moved when going from v1 to v2 | Update import to org.springdoc.core.models |
| Customizer fails to compile | OpenApiCustomiser renamed to OpenApiCustomizer | Update class name and package |
| Swagger UI opens but document fails | API docs endpoint or serializer affected | Call /v3/api-docs directly and inspect response/logs |
| Parameters disappear after Boot 3.2 upgrade | Parameter name metadata not retained | Enable -parameters compiler option |
| Document has different required/nullable | Schema inference or dependency version changed | Review schema diff and check runtime payload |
| Both MVC and WebFlux starters appear | Dependency graph mismatches stack | Pick one web stack and corresponding starter |

## 19. Checklist Before Finalizing Version

- [ ] Exact Spring Boot major and minor identified.
- [ ] Corresponding springdoc major selected.
- [ ] springdoc minor/patch falls within published matrix.
- [ ] Java runtime meets Spring Boot requirements.
- [ ] Spring Framework and Jakarta APIs match baseline.
- [ ] Only one springdoc major in the dependency graph.
- [ ] Starter matches MVC or WebFlux.
- [ ] UI starter used only when Swagger UI is actually needed.
- [ ] Module/package renames handled if upgrading from v1 to v2.
- [ ] javax updated to jakarta when upgrading the Boot 3 platform.
- [ ] Migration guide read when upgrading to Boot 4.
- [ ] No unintended overrides of swagger-core/annotations.
- [ ] OpenAPI JSON/YAML loads and is valid.
- [ ] Swagger UI renders the right document.
- [ ] Operations, schemas, security, and server URL verified.
- [ ] Semantic diff and runtime contract tests PASS.

## 20. Official References

- [springdoc-openapi v1](https://springdoc.org/v1/): 1.8.0 branch, Boot 1.x/2.x, and compatibility matrix.
- [springdoc-openapi v2](https://springdoc.org/v2/): 2.10.0 branch, Boot 3.x, and compatibility matrix.
- [springdoc-openapi v3](https://springdoc.org/): 3.2.0 branch, Boot 4.x, and compatibility matrix.
- [Migrating from springdoc-openapi v1](https://springdoc.org/v2/migrating-from-springdoc-v1.html): module, package, and class renames when moving to v2.
- [Spring Boot 3.0 Migration Guide](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-3.0-Migration-Guide): Java 17, Spring Framework 6, and Jakarta EE.
- [Spring Boot 4.0 System Requirements](https://docs.spring.io/spring-boot/4.0/system-requirements.html): Java 17, Spring Framework 7, and build tools.
- [Spring Boot Wiki](https://github.com/spring-projects/spring-boot/wiki): migration guides and release notes by Boot generation.
- [springdoc-openapi Releases](https://github.com/springdoc/springdoc-openapi/releases): changes per release across v1/v2/v3.

## Conclusion

Choose springdoc by the Spring Boot generation: v1 for Boot 1/2, v2 for Boot 3, and v3 for Boot 4. Then cross-check the minor line in the official matrix, because not every patch of the same major was built against every Boot minor. When upgrading v1 to v2, handle module/package renames and the Jakarta transition with Boot 3; when upgrading v2 to v3, perform the Boot 4 migration and re-verify the dependency graph, auto-configuration, schemas, and Swagger UI. The springdoc library version is not the OpenAPI version written into the document, and successful dependency resolution does not replace compatibility testing.
