# GraalVM Native Image and Library Version Support Conditions

GraalVM Native Image compiles a Java application into an executable targeting a specific operating system and CPU architecture. Native applications typically start faster and use less memory than JVM applications, but this compilation model requires determining most required code, classes, resources, reflection, and proxies ahead of time. Consequently, a library that runs well on the JVM is not guaranteed to work properly in a native image if it relies on runtime class loading or reflection without providing reachability metadata.

With Spring Boot, Spring AOT handles a large share of this work at build time. springdoc-openapi supports GraalVM native images starting from Spring Boot 3, but you must still choose the right springdoc line for your Spring Boot version, place configuration annotations properly, and test the actual native executable. Merely seeing a native build succeed is not enough to conclude that OpenAPI endpoints and Swagger UI work.

This lesson explains compatibility requirements, how Spring AOT and GraalVM process the application, key considerations when using springdoc, the native image build and test workflow, and how to measure performance to decide whether to deploy native.

## 1. How Does Native Image Differ from Running on the JVM?

JVM applications typically carry bytecode and run on the Java Virtual Machine. The JVM can load classes, create proxies, use reflection, and read classpath resources while the program executes. Native Image performs static analysis from entry points at build time and compiles the code deemed reachable into an executable.

| Criterion | Running on JVM | GraalVM Native Image |
| --- | --- | --- |
| Class loading | Can load classes at runtime from the classpath | Classpath is fixed at build time |
| Reflection | Can discover classes/members at runtime | Requires reachability metadata for dynamic access |
| Classpath resources | Can read resources present in JAR/classpath | Resources must be identified and included in the image |
| Dynamic proxies | Can create proxies at runtime | Proxies must be identified and generated at build time |
| Startup | May require initialization and JIT warm-up time | Typically starts faster |
| Throughput optimization | JIT can optimize based on live runtime behavior | Lacks conventional JVM JIT warm-up |
| Build | Usually faster | Native compilation is usually slower and heavier on CPU/RAM |
| Distribution | Requires a compatible Java runtime | Executable depends on OS/CPU and build environment |

Native Image relies on a closed-world assumption: required components must be known at build time. Code not identified as reachable can be stripped from the executable. This produces a leaner binary, while exposing reflection, resource, serialization, or proxy dependencies that the JVM handles dynamically.

## 2. Spring AOT Is Mandatory in Native Image

Spring Boot uses Ahead-of-Time processing to prepare the ApplicationContext before GraalVM compiles it. Spring AOT analyzes bean definitions, configuration conditions, and registered Spring components, then generates source code, bytecode, and runtime hints.

Generated files are typically located at:

| Build Tool | AOT Generated Sources | AOT Generated Resources |
| --- | --- | --- |
| Maven | target/spring-aot/main/sources | target/spring-aot/main/resources |
| Gradle | build/generated/aotSources | build/generated/aotResources |

Inside resources, Spring may generate metadata under META-INF/native-image. Hints generally describe:

- Reflection: classes, constructors, fields, or methods accessed dynamically.
- Resource: files to read from the classpath.
- Serialization: data types requiring dynamic serialization/deserialization.
- Proxy: interface or class proxies to pre-generate.
- JNI: Java elements accessed from native code.

Spring AOT handles many common cases automatically, such as controller request/response types. If a library or custom code uses dynamic mechanisms that Spring cannot infer, you must add runtime hints or reachability metadata. Do not add broad hints indiscriminately before encountering concrete errors, as overly wide metadata bloats image size and masks root causes.

## 3. Native Image Has a Closed-World Assumption

Some Spring configurations normally resolved at JVM runtime are resolved during AOT processing instead. This affects bean definitions:

- @Profile and profile-specific configurations have limitations because the bean graph is finalized at build time.
- @ConditionalOnProperty and .enabled properties can affect bean creation and thus need appropriate values at build time.
- You cannot expect to add classes to the classpath or instantiate an entirely new set of beans after the native executable is built.
- Configurations enabling/disabling controllers or OpenAPI endpoints must be accounted for in the AOT environment.

For example, if an OpenAPI endpoint is only created when springdoc.api-docs.enabled=true, the value used during the AOT build must permit that bean to exist in the native image. Changing the property when running the executable cannot resurrect a bean excluded from the image at build time.

Across multiple deployment environments, distinguish configuration values changeable at runtime from conditions governing the bean graph. Values like host, port, or credentials can usually be supplied via environment at runtime; bean existence and conditional branches must be verified against the AOT constraints of the Spring Boot version in use.

## 4. Spring Boot and springdoc-openapi Compatibility Matrix

You must choose the right springdoc major version matching your Spring Boot major version. Do not simply bump springdoc to the latest version while ignoring the compatibility matrix.

| Spring Boot | Compatible springdoc Line | Notes |
| --- | --- | --- |
| 4.1.x | 3.1.x to 3.2.x | Per current springdoc compatibility matrix |
| 4.0.x | 3.0.x | Use springdoc 3.x |
| 3.x | 2.x | See springdoc v2 documentation for Boot 3 |
| 2.x and 1.x | 1.8.0 is the final open-source line | Legacy line, open-source support ended |

The detailed matrix is updated with releases. Before upgrading, check springdoc's FAQ/README and pick a version built/tested with your project's exact Spring Boot line. Do not infer that every 3.x release is compatible with every 4.x release.

For example, current springdoc documentation lists Boot 4.1.x with springdoc 3.1.x–3.2.x and Boot 4.0.x with springdoc 3.0.x. For Boot 3.x, use the springdoc 2.x branch and v2 documentation. If still on Boot 2.x, consider upgrading the platform because springdoc 1.8.0 is a legacy line without ongoing open-source support.

## 5. springdoc Native Image Support Starts with Spring Boot 3

The springdoc FAQ notes that native support was introduced alongside Spring Boot 3. For Boot 3 or Boot 4 applications, native builds follow Spring AOT and GraalVM Native Build Tools in the modern Spring Boot ecosystem.

Do not confuse current native guides with the standalone Spring Native project used prior to Boot 3. Use the Native Image support built into Spring Boot, Spring AOT, and the native build plugin compatible with your Boot version.

The springdoc FAQ also highlights a specific case: if @OpenAPIDefinition or @SecurityScheme is placed on an annotation-only class with no implementation or Spring configuration role, that class may be stripped during native compilation. Place these annotations on a @Configuration class so Spring detects it and AOT processes it properly.

## 6. Placing OpenAPI Annotations on a Configuration Class

Example configuring metadata and a bearer security scheme:

~~~java
import io.swagger.v3.oas.annotations.OpenAPIDefinition;
import io.swagger.v3.oas.annotations.info.Info;
import io.swagger.v3.oas.annotations.security.SecurityScheme;
import io.swagger.v3.oas.annotations.enums.SecuritySchemeType;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@OpenAPIDefinition(
    info = @Info(
        title = "Order API",
        version = "1.0.0",
        description = "Order management API"
    )
)
@SecurityScheme(
    name = "bearerAuth",
    type = SecuritySchemeType.HTTP,
    scheme = "bearer",
    bearerFormat = "JWT"
)
class OpenApiConfiguration {
}
~~~

This class is a Spring configuration bean. OpenAPI annotations are attached to a Spring component that can be discovered in the ApplicationContext and processed during AOT.

If the annotated class lies outside component scanning, the native build cannot discover it automatically. Verify the configuration class's package, scan configuration, and test the ApplicationContext with the same configuration used to build the native image.

## 7. Choosing the Right Starter for Web MVC, WebFlux, and Swagger UI

springdoc provides separate starters for API descriptions and documentation UI:

| Application | OpenAPI Endpoint Only | Swagger UI Needed |
| --- | --- | --- |
| Spring MVC | springdoc-openapi-starter-webmvc-api | springdoc-openapi-starter-webmvc-ui |
| Spring WebFlux | springdoc-openapi-starter-webflux-api | springdoc-openapi-starter-webflux-ui |

If you only need OpenAPI JSON/YAML in CI or to supply specs to a gateway, the API starter may suffice. If an interactive interface is needed, use the UI starter matching your web stack.

Do not mix Web MVC and WebFlux starters arbitrarily. Use the exact web stack your application runs and avoid pulling multiple versions of swagger-core or swagger-annotations through transitive dependencies.

## 8. Aligning Dependencies and Avoiding Version Conflicts

When a native build fails, the cause may come from incompatible libraries, not just GraalVM. Check:

- Spring Boot version and Spring Framework version.
- springdoc starter version.
- Resolved swagger-core and swagger-annotations versions.
- Jackson modules and custom serializers.
- Native Build Tools plugin version.
- GraalVM JDK version and Java toolchain.
- Whether third-party libraries include reachability metadata.

Run dependency insight/tree to spot multiple versions of swagger-core, Jackson, or Spring Framework coexisting. Use an appropriate BOM/dependency management setup and avoid forcing a transitive dependency to another version without checking the compatibility matrix.

Gradle example:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
~~~

Maven example:

~~~bash
./mvnw dependency:tree
~~~

After changing dependencies, re-run JVM tests, AOT processing, and the native build. A passing JVM build does not prove the new dependency's metadata is complete.

## 9. Building Native Images with Maven

The Spring Boot Maven plugin provides AOT processing. If the project uses spring-boot-starter-parent, the native profile can configure process-aot, Native Build Tools, and image building.

The POM needs the Spring Boot Maven plugin and Native Build Tools Maven plugin in the application module:

~~~xml
<build>
  <plugins>
    <plugin>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-maven-plugin</artifactId>
    </plugin>
    <plugin>
      <groupId>org.graalvm.buildtools</groupId>
      <artifactId>native-maven-plugin</artifactId>
    </plugin>
  </plugins>
</build>
~~~

With the native profile provided by the Spring Boot parent, you can start with:

~~~bash
./mvnw -Pnative package
~~~

If the project manages plugin executions manually or does not use the Spring Boot parent, configure process-aot and native goals according to the Spring Boot/Native Build Tools documentation for your exact version. The native profile does not automatically add missing plugins in a custom POM.

Another option is using Cloud Native Buildpacks to produce a container image containing the native executable. This build method requires a Docker daemon and compatible builder; in return, the pipeline may not need GraalVM installed directly on the build runner.

## 10. Building Native Images with Gradle

With Gradle, add the Native Build Tools plugin alongside the Spring Boot plugin:

~~~kotlin
plugins {
    java
    id("org.springframework.boot") version "4.1.2"
    id("org.graalvm.buildtools.native") version "1.1.14"
}
~~~

The example above illustrates plugin structure. Replace versions with the compatible Spring Boot, Gradle, and Native Build Tools combination in your project. Do not treat sample version numbers as defaults for all projects.

Once the plugin is configured, the main task typically used is:

~~~bash
./gradlew nativeCompile
~~~

After the build finishes, run the executable via nativeRun if provided by the plugin or run the binary directly in build/native/nativeCompile. Paths and filenames depend on the project name, OS, and binary configuration.

The Native Build Tools Gradle plugin requires a GraalVM JDK with native-image. You can select a toolchain or configure GRAALVM_HOME per the plugin documentation. Check native-image --version before running the build.

## 11. Using the Right GraalVM and Native Build Tools Versions

Native builds depend on more than a standard Java version. Check:

1. Minimum Java version required by your Spring Boot version.
2. GraalVM Native Image version supported by Spring Boot.
3. Compatible Native Build Tools plugin version.
4. Supported Gradle/Maven version.
5. OS and CPU architecture used to build the binary.

For example, Spring Boot 4.1.2 documentation lists GraalVM Community 25 and Native Build Tools 1.1.14 in its native image requirements. These numbers can change in patch releases or newer Boot lines; always consult the System Requirements for the exact version being deployed.

Do not rely merely on a developer machine having a recent GraalVM installed. A GraalVM that is too new or too old relative to Spring Boot/Native Build Tools can cause build failures, alter reachability behavior, or make CI non-reproducible.

## 12. Understanding Library Reachability Metadata

GraalVM performs static analysis to determine which code is called directly. Dynamic operations such as reflection, reading resources by name, serialization, or proxy creation may not be fully inferred. Reachability metadata supplies the information Native Image needs to retain those elements.

Metadata can come from:

- Spring AOT generated hints.
- Metadata bundled with libraries under META-INF/native-image.
- The GraalVM Reachability Metadata Repository downloaded by Native Build Tools.
- RuntimeHints registered by the application itself.
- JSON metadata added by the development team after diagnosing real errors.

JSON files can describe reflection, resources, serialization, JNI, and proxies. Do not copy a massive reflect-config.json from another project because classes, members, and dependency versions may differ.

## 13. Checking Libraries Missing Reachability Metadata

Native Build Tools provides a command listing dependencies missing metadata in the repository:

~~~bash
./gradlew listLibrariesMissingMetadata
~~~

With Maven:

~~~bash
./mvnw native:list-libraries-missing-metadata
~~~

This output helps identify libraries needing further inspection. Lacking metadata in the repository does not automatically mean a library cannot run; the code might not invoke that dynamic feature, or Spring AOT may have generated alternative hints. Conversely, having metadata does not prove every application code path is covered.

Verify runtime behavior using the native executable and test real functionality, especially features using reflection, custom serializers, plugins, classpath scanning, or dynamic resources.

## 14. Adding Reflection Hints for Types Requiring Binding

Spring AOT normally infers hints for controller request/response types. If a type is used via reflection or dynamic binding that AOT misses, additional hints can be registered.

Example:

~~~java
import org.springframework.aot.hint.annotation.RegisterReflectionForBinding;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@RegisterReflectionForBinding({
    CreateOrderRequest.class,
    OrderResponse.class
})
class ApiNativeBindingHints {
}
~~~

Register only the types actually needed. This annotation is useful when a type is bound/serialized dynamically and static paths are insufficient for Spring AOT to infer it. Do not add hints for every DTO out of habit if Spring already generates the metadata.

If resources or proxies are missing rather than reflection, use the corresponding RuntimeHints API. Read the native image error messages to determine the exact hint type needed.

## 15. Adding RuntimeHints When Libraries Need Resources or Proxies

Spring Framework provides RuntimeHintsRegistrar to register reflection, resources, serialization, and proxies. Example illustrating registration of a specific resource:

~~~java
import org.springframework.aot.hint.RuntimeHints;
import org.springframework.aot.hint.RuntimeHintsRegistrar;

public class ApiDocumentationHints implements RuntimeHintsRegistrar {

    @Override
    public void registerHints(
            RuntimeHints hints,
            ClassLoader classLoader) {

        hints.resources().registerPattern(
            "META-INF/example-api/banner.txt"
        );
    }
}
~~~

Register the registrar via @ImportRuntimeHints on a configuration class or the corresponding Spring Framework mechanism. The example above illustrates a resource hint; replace the pattern with the exact resource the application actually reads.

Do not register all of META-INF or the entire classpath when only one file is missing. Overly broad hints inflate the native image and mask unexpected library resource dependencies.

## 16. Special Considerations for OpenAPI Annotations and Swagger UI

When using springdoc in a native image, check the following components individually:

- Configuration classes carrying @OpenAPIDefinition and @SecurityScheme must be discovered by Spring, so annotate them with @Configuration.
- Controllers and functional routes must exist in the bean graph at AOT time.
- DTOs, enums, generic wrappers, and custom serializers must be reflected accurately in schemas and responses.
- If Swagger UI is needed, static resources from the UI starter must be present in the native image.
- If only JSON/YAML is needed, use the API starter to drop unnecessary UI assets.
- GroupedOpenApi beans and OpenAPI customizers must be registered during AOT processing.
- Conditions such as springdoc.api-docs.enabled, packages-to-scan, and paths-to-match must be accurate at build time.

A native executable may start successfully yet lack OpenAPI endpoints, miss groups, or fail to render Swagger UI. Therefore, test each endpoint after launching the binary.

## 17. Distinguishing OpenAPI Endpoints from Swagger UI

springdoc typically exposes:

| Endpoint | Content |
| --- | --- |
| /v3/api-docs | OpenAPI JSON |
| /v3/api-docs.yaml | OpenAPI YAML |
| /swagger-ui.html | Swagger UI entry point under default configuration |

If the application only uses the API starter, Swagger UI will not necessarily exist. If using the UI starter, check HTML, JavaScript, CSS, and the OpenAPI config fetched by the UI.

A native image build does not automatically turn the OpenAPI document into a static file at build time. springdoc still builds the document from Spring mappings and metadata when the native application runs. If you need a static JSON/YAML file to publish in a pipeline, use a dedicated documentation export step in the build; do not assume native compilation already exported the spec.

## 18. Verifying the Native Executable After Building

Run the binary in a production-like environment:

~~~bash
./build/native/nativeCompile/application
~~~

Executable name and path depend on the Gradle project and OS. With Maven, the binary typically resides in target after native plugin execution or inside an image built with Buildpacks.

Fetch OpenAPI JSON:

~~~bash
curl --fail --silent --show-error \
  http://localhost:8080/v3/api-docs \
  --output openapi-native.json
~~~

Fetch YAML:

~~~bash
curl --fail --silent --show-error \
  http://localhost:8080/v3/api-docs.yaml \
  --output openapi-native.yaml
~~~

Validate the JSON file:

~~~bash
jq -e '.openapi and .paths and (.paths | length > 0)' openapi-native.json
~~~

If Swagger UI is included, open /swagger-ui.html and verify the browser loads swagger-config, OpenAPI JSON, and static assets. If using OAuth2 or bearer security, verify security schemes in the document and authentication flows in a test environment.

## 19. Do Not Stop at Checking Whether the Native Build Succeeded

A successful build only confirms GraalVM produced an executable. A verification suite must exercise real execution paths:

1. ApplicationContext starts in native mode.
2. Key controllers return the right status and media type.
3. OpenAPI JSON/YAML endpoints return 200 and parse cleanly.
4. All expected paths/methods appear in the document.
5. Request DTOs and response DTOs serialize properly.
6. Validation and error responses work.
7. Security schemes, OAuth2, groups, and customizers work.
8. Swagger UI assets load if the UI starter is used.
9. Routes using reflection or custom converters are actually invoked.
10. The native executable runs in the target container/OS.

Check both actual responses and the OpenAPI document. A schema might be generated properly while the Jackson serializer in the native runtime still lacks metadata for a rarely hit data branch.

## 20. Using the Tracing Agent When Metadata Is Missing

The GraalVM Native Image Tracing Agent can observe reflection, resource, and proxy usage while the application runs on the JVM. The agent emits configuration suggestions based on executed paths.

You can run the application or tests with the agent and then exercise real workflows such as:

- Calling endpoints that create and read data.
- Opening OpenAPI JSON/YAML.
- Opening Swagger UI if enabled.
- Triggering error handlers and validation.
- Using security schemes, custom converters, and grouped docs.

After stopping the application, the agent writes metadata into the configured output directory. Review the generated files, remove test-infrastructure metadata unnecessary at runtime, and move required entries into source resources per GraalVM guidelines.

The tracing agent only records executed code paths. It does not automatically discover every possible branch. If a group endpoint, DTO variant, or rare error was never triggered, metadata for that branch may be missing.

## 21. Running Tests in Native Mode

Native Build Tools supports compiling and running tests in a native image. With Gradle, the typical task is:

~~~bash
./gradlew nativeTest
~~~

With Maven, Native Build Tools provides a native test goal and requires a compatible JUnit Platform setup. Configure test dependencies, Surefire, and Native Build Tools according to your version's documentation.

There is no need to move the entire test suite to native mode immediately. A practical roadmap:

- Run unit tests on the JVM for fast feedback.
- Run integration tests on the JVM to verify business logic and external systems.
- Run a focused suite of smoke/critical tests on the native image.
- Expand native tests for code paths heavy on reflection or custom serialization.

Native tests catch discrepancies that appear only after AOT/native compilation. Yet JVM tests remain valuable for checking logic and business behavior at lower cost.

## 22. Troubleshooting Common Native Errors

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| Native build reports missing reflection registration | Missing reflection hint for dynamically accessed class/member | Check the class in the error, inspect AOT hints, and register the exact type |
| OpenAPI endpoint returns 404 | API docs bean not created during AOT build or endpoint disabled | Check component scan and springdoc.api-docs.enabled at build time |
| @OpenAPIDefinition disappears | Annotation sits on a class not discovered by Spring | Move the annotation onto a @Configuration class |
| Security scheme does not appear | Config class not scanned or annotation holder stripped | Inspect OpenApiConfiguration and the native document |
| DTO has missing fields in JSON | Insufficient reflection/binding/serializer metadata or differing Jackson config | Check native responses, custom serializers, and binding hints |
| Swagger UI returns 404 for assets | UI starter or resources omitted from image | Check starter and dependency resource hints |
| OpenAPI group disappears | GroupedOpenApi bean not created in AOT context | Check bean conditions, profiles, and build-time configuration |
| Runs on JVM but fails in native | A code path uses reflection/resources/proxies lacking metadata | Use tracing agent and native tests |
| Native image build fails due to toolchain | Incompatible GraalVM, Java, Boot, or Native Build Tools | Cross-check System Requirements for the exact Boot version |
| Binary runs on build machine but fails elsewhere | Binary depends on OS, architecture, or native libraries | Build for the right target and verify runtime dependencies |
| Build is very slow or runs out of RAM | Native compilation is CPU/RAM intensive, too much parallelism | Limit parallel builds and allocate adequate CI resources |

## 23. Native Image Is Not Always Faster Than the JVM

Native Image generally excels in startup time and memory footprint, especially for frequently restarted or short-lived applications. However, JVM applications with a JIT compiler can reach very high throughput after warm-up. A native executable does not have the same runtime profile-guided JIT optimization.

For a long-running API server, measure:

- Time from process start to readiness.
- First-time OpenAPI document load time.
- Latency p50, p95, and p99 of business endpoints.
- Throughput under steady load.
- RSS/working set after warm-up.
- CPU usage and garbage collection behavior.
- Container image and executable sizes.
- Native image build time.

Do not conclude native is superior based solely on startup time. For long-lived services, throughput and tail latency may matter more than a few hundred milliseconds at startup.

## 24. Benchmarking JVM and Native Fairly

When comparing the two build modes:

1. Use the same source code, dependencies, configuration, and data.
2. Use the same CPU, memory limits, and network.
3. Measure JVM after warm-up and native once steady state is reached.
4. Run the same workload and concurrency.
5. Run multiple iterations and record variance.
6. Measure both cold start and steady state.
7. Separate image build time from runtime performance.
8. Verify functionality and responses before comparing performance.

With springdoc, measure /v3/api-docs separately if that endpoint is called frequently. Generating the document consumes CPU and allocations; fast native startup does not mean OpenAPI document generation is free.

If the OpenAPI endpoint is mostly used during development or by an internal portal, you may not need to optimize it like high-traffic business endpoints. Choose benchmark workloads reflecting real system behavior.

## 25. When Should You Choose Native Image?

| Scenario | Worth Trying Native Image? | Reason |
| --- | --- | --- |
| Serverless or scale-to-zero | Yes | Startup and memory footprint can cut cold-start costs |
| Short-lived workers | Yes | Startup accounts for a large share of runtime |
| Many-replica API service with tight memory limits | Yes, benchmark required | Can lower per-replica memory |
| Continuously running high-throughput API server | Benchmark carefully | JVM JIT may deliver higher throughput |
| Project relies heavily on runtime plugins/classpath scanning | Evaluate carefully | Closed-world may require many hints or redesign |
| Critical library lacks native support | Not ready for production | High risk of runtime failures and maintenance cost |
| CI lacks CPU/RAM for native compilation | May be unsuitable | Native builds carry significant resource costs |

For springdoc, native image works well when the project uses the right dependency matrix, OpenAPI config is recognized by Spring, and documentation endpoints are verified on the real binary. If Swagger UI is unnecessary in production, you can package only the API docs starter or export the specification in the build pipeline.

## 26. Pre-Release Checklist for Native Images with springdoc

- [ ] Spring Boot and springdoc versions match the compatibility matrix.
- [ ] GraalVM JDK, Java toolchain, and Native Build Tools align with Spring Boot.
- [ ] Spring AOT processing succeeds with the proper build-time configuration.
- [ ] Required controllers, RouterFunctions, GroupedOpenApi, and customizers are discovered.
- [ ] @OpenAPIDefinition and @SecurityScheme reside on a @Configuration class.
- [ ] DTOs, Jackson modules, and custom serializers work in the native runtime.
- [ ] Library reachability metadata has been checked.
- [ ] RuntimeHints are added only for reflection/resources/proxies truly needed.
- [ ] /v3/api-docs and /v3/api-docs.yaml return valid documents.
- [ ] Swagger UI and static assets work if packaged.
- [ ] Security schemes, OAuth2, validation, and error responses have been smoke tested.
- [ ] Native executable runs on the target OS/architecture.
- [ ] Startup, memory, throughput, latency, and build time have been measured.
- [ ] Runtime benefits have been weighed against native build and metadata maintenance costs.

Native Image delivers its clearest benefits when startup and memory are decisive factors. With Spring Boot and springdoc, good outcomes hinge on three things: picking the right version pair, letting Spring AOT discover full OpenAPI configuration, and testing endpoints on the real native executable. Base decisions on measurements and runtime tests rather than merely seeing native compilation succeed.

## References

- [springdoc-openapi – FAQ: GraalVM support and compatibility matrix](https://springdoc.org/faq.html)
- [springdoc-openapi – Introduction and GraalVM support](https://springdoc.org/)
- [springdoc-openapi v2 – Documentation for Spring Boot 3.x](https://springdoc.org/v2/)
- [Spring Boot – Introducing GraalVM Native Images](https://docs.spring.io/spring-boot/reference/packaging/native-image/introducing-graalvm-native-images.html)
- [Spring Boot – Ahead-of-Time Processing](https://docs.spring.io/spring-boot/maven-plugin/aot.html)
- [Spring Boot – Advanced Native Images Topics](https://docs.spring.io/spring-boot/reference/packaging/native-image/advanced-topics.html)
- [Spring Boot – System Requirements](https://docs.spring.io/spring-boot/system-requirements.html)
- [GraalVM – Reachability Metadata](https://www.graalvm.org/latest/reference-manual/native-image/metadata/)
- [GraalVM Native Build Tools – Gradle Plugin](https://graalvm.github.io/native-build-tools/latest/gradle-plugin)
- [GraalVM Native Build Tools – Maven Plugin](https://graalvm.github.io/native-build-tools/latest/maven-plugin)
