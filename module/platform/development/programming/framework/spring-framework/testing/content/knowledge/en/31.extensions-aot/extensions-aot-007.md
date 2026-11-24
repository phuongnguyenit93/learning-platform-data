# AOT Processing for Spring Integration Tests

Spring normally creates the application context when an application or test starts running. During that process, the framework reads configuration, discovers beans, resolves dependencies, and prepares required components. For large applications, this startup step can take significant time; when compiling to a native image, certain reflective operations and resource accesses must also be declared ahead of time so GraalVM can package them properly.

Ahead-of-Time (AOT) processing shifts part of the context preparation work to build time. Spring analyzes configuration, generates initialization code, and registers runtime hints for necessary operations. Spring Boot supports AOT for both the application and test contexts, making it possible to verify integration configurations in AOT mode and prepare tests to run in an appropriate native environment.

In integration testing, it is important to distinguish three related but distinct activities:

- **Application AOT:** processes the application's configuration to generate initialization code and runtime hints.
- **Test context AOT:** processes application contexts created from test configuration, such as the context of `@SpringBootTest` or a test slice.
- **Native test execution:** compiles and runs tests inside a native executable. This is an additional verification step, not synonymous with merely running AOT processing on the JVM.

## 1. What Problem Does AOT Processing Solve?

In standard startup, Spring builds the `ApplicationContext` at runtime. Main steps may include:

1. Reading application configuration and property sources.
2. Discovering configuration classes, components, and bean definitions.
3. Resolving dependencies between beans.
4. Registering bean post-processors, proxies, and infrastructure components.
5. Instantiating beans and completing context refresh.

With AOT, Spring performs part of the analysis at build time and generates Java code representing context initialization. When running the application, the runtime can use the generated code to create the context with less dynamic discovery work.

This process is especially important for GraalVM Native Image. Native Image analyzes the program under a closed-world model: classes, methods, resources, and proxies needed at runtime must be identified during the native build. Operations that appear only via reflection or dynamic resource access may require runtime hints.

AOT processing helps Spring supply the necessary metadata instead of relying entirely on dynamic discovery once the application is running.

## 2. How Do Application AOT and Test AOT Differ?

Spring Boot provides two main AOT flows:

| Flow | Input | Primary Output | Purpose |
| --- | --- | --- | --- |
| Application AOT | Production application configuration | Context initialization code and runtime hints for the application | Prepare the application to run with AOT or native image |
| Test AOT | Context configuration declared by tests | Initialization code and hints for test application contexts | Prepare integration test contexts for AOT/native test execution |

Application AOT is typically invoked via Gradle's `processAot` task or the Spring Boot Maven Plugin's `process-aot` goal. Test AOT uses the corresponding `processTestAot` task or `process-test-aot` goal in supported plugin versions.

For example, an application with production configuration and a test slice:

```text
Application configuration
        |
        +--> Application AOT processing
        |         |
        |         +--> Generated application context initializer
        |         +--> Application runtime hints
        |
Test classes and test configuration
        |
        +--> Test AOT processing
                  |
                  +--> Generated test context initializer
                  +--> Test runtime hints
```

Test AOT does not regenerate the assertion logic inside individual test methods. It prepares the context that tests need to use. Test methods are still executed by the test engine such as JUnit; the difference lies in how the test context is initialized in AOT mode.

## 3. How Does Test Context AOT Work?

The Spring TestContext Framework manages contexts for integration tests. When using `@SpringBootTest`, `@WebMvcTest`, `@DataJpaTest`, or `@ContextConfiguration`, the framework determines test metadata and creates the corresponding context.

In the normal flow, the context is loaded from configuration when the test runs. In the AOT flow, Spring analyzes the test context at build time and generates initializer code for that configuration. When tests run in AOT mode, Spring uses the generated initializer instead of performing the full context analysis in the standard way.

Overall flow:

```text
Build time
----------
Test classes + Spring test metadata
              |
              v
      TestContext AOT processor
              |
              +--> Analyze test context configuration
              +--> Generate context initializer code
              +--> Register runtime hints
              |
              v
      Generated test AOT artifacts

Test runtime
------------
JUnit discovers test class
              |
              v
      Spring TestContext Framework
              |
              v
      Generated context initializer
              |
              v
      ApplicationContext for test
              |
              v
      Execute test methods
```

This helps verify that the test's context can be prepared using the generated artifacts. For native testing, it also brings test configuration and required hints into the native executable build process.

## 4. Which Types of Tests Benefit from Test AOT?

Test AOT is most useful for tests that require a Spring application context, especially when you want to verify that the application or configuration layers can run in a native environment.

| Test Type | Example | Value of Test AOT |
| --- | --- | --- |
| Full integration test | `@SpringBootTest` | Verifies that a broad integration context can be AOT-processed |
| MVC slice | `@WebMvcTest` | Prepares the context containing controllers and MVC infrastructure |
| JPA slice | `@DataJpaTest` | Prepares the test's persistence context |
| JSON slice | `@JsonTest` | Verifies mapper/serializer configuration in an AOT context |
| Custom Spring context | `@ContextConfiguration` | Verifies that test configuration sources can be AOT-processed if involved components support it |

Not every test needs Test AOT. Pure Java unit tests that do not create a Spring context generally gain no benefit from generating context initializers. Prioritize tests that represent real Spring configurations and integrations with risks around reflection, resource loading, proxies, or native runtime.

## 5. Enabling AOT Processing for Application and Tests

AOT tasks/goals are provided by Spring Boot plugins. Exact names and integration capabilities depend on the project's Spring Boot Gradle Plugin or Maven Plugin version.

### With Gradle

Example build using the Spring Boot Gradle Plugin:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.4.0'
}

dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
```

Commonly used AOT tasks:

```bash
./gradlew processAot
./gradlew processTestAot
```

- `processAot` processes the application's application context.
- `processTestAot` processes contexts declared in tests.

If the project integrates GraalVM Native Build Tools, the native plugin provides tasks related to compiling or running native executables. Check the tasks available in your plugin version, for example:

```bash
./gradlew tasks --all
```

Do not confuse `processTestAot` with a task that runs tests. It prepares AOT artifacts; test or native test tasks are what execute test methods.

### With Maven

The Spring Boot Maven Plugin provides AOT goals in supported versions:

```bash
./mvnw spring-boot:process-aot
./mvnw spring-boot:process-test-aot
```

The first goal processes application configuration; the second goal processes test contexts. If the project uses Maven profiles or a separate native plugin, check the current build configuration to identify the goals for compiling and running native tests.

### Checking the Plugin Version

Do not upgrade `spring-boot-maven-plugin` or the Gradle plugin independently of the Spring Boot version your application uses. The plugin should align with the project's Spring Boot line and dependency management. If the `processTestAot` task or `process-test-aot` goal does not exist, check your plugin version and corresponding documentation before manually adding custom tasks.

## 6. Integration Test Example with `@SpringBootTest`

Suppose the application has a service and a controller:

```java
@Service
public class GreetingService {

    public String greet(String name) {
        return "Hello, " + name;
    }
}

@RestController
public class GreetingController {

    private final GreetingService greetingService;

    public GreetingController(GreetingService greetingService) {
        this.greetingService = greetingService;
    }

    @GetMapping("/greetings/{name}")
    public Map<String, String> greet(@PathVariable String name) {
        return Collections.singletonMap("message", greetingService.greet(name));
    }
}
```

Integration test:

```java
@SpringBootTest
@AutoConfigureMockMvc
class GreetingIntegrationTest {

    @Autowired
    private MockMvc mockMvc;

    @Test
    void loadsApplicationContextAndReturnsGreeting() throws Exception {
        mockMvc.perform(get("/greetings/{name}", "Lan"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.message").value("Hello, Lan"));
    }
}
```

This test initializes the Boot application context and exercises Spring MVC via `MockMvc`. When AOT test processing runs, Spring prepares a context initializer for that test configuration. When the test runs in AOT mode, the context can be created from the generated artifact.

`MockMvc` still uses simulated Servlet requests/responses. If you need to verify an embedded server or network stack, include tests using `@SpringBootTest(webEnvironment = RANDOM_PORT)` and an HTTP client. Test AOT does not turn `MockMvc` into a real HTTP server.

## 7. Test Slices and AOT

Test slices also create an application context, so they can participate in the Test AOT flow when supported by the Spring Boot version and components in the context.

MVC slice example:

```java
@WebMvcTest(GreetingController.class)
class GreetingControllerSliceTest {

    @Autowired
    private MockMvc mockMvc;

    @MockitoBean
    private GreetingService greetingService;

    @Test
    void mapsGreetingRequest() throws Exception {
        given(greetingService.greet("Lan")).willReturn("Hello, Lan");

        mockMvc.perform(get("/greetings/Lan"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.message").value("Hello, Lan"));
    }
}
```

Test slices keep scope smaller than a full context. AOT processing of a slice helps verify that the MVC test configuration and related beans can be prepared in AOT mode. If the slice uses custom test configuration or test context customizers, those components must also be compatible with the AOT mechanism.

In older Spring Framework/Spring Boot versions, the mock bean annotation may be `@MockBean` instead of `@MockitoBean`. The example using `@MockitoBean` requires Spring Framework 6.2 or later.

## 8. Runtime Hints and Native Image in Integration Tests

Native Image cannot automatically retain every class and resource an application might access dynamically. If code uses reflection, resource loading, serialization, or dynamic proxies, the native image may need metadata to know which components must be preserved.

Spring AOT generates runtime hints for many cases the framework can analyze. When an application has libraries or custom code using dynamic reflection/resources, developers may need to register hints.

An example `RuntimeHintsRegistrar`:

```java
public class GreetingRuntimeHints implements RuntimeHintsRegistrar {

    @Override
    public void registerHints(RuntimeHints hints, ClassLoader classLoader) {
        hints.resources().registerPattern("greetings/*.json");
        hints.reflection().registerType(
                GreetingPayload.class,
                MemberCategory.INVOKE_PUBLIC_CONSTRUCTORS,
                MemberCategory.INVOKE_PUBLIC_METHODS);
    }
}
```

Registering the registrar with `@ImportRuntimeHints`:

```java
@Configuration
@ImportRuntimeHints(GreetingRuntimeHints.class)
public class GreetingConfiguration {
}
```

When integration tests run on a standard JVM, missing runtime hints may not cause failures because the JVM permits flexible reflection and resource access. When running a native executable, missing hints can cause the test or application to fail. Therefore, native integration tests are a useful way to uncover undeclared runtime assumptions.

### Verifying Hints with `RuntimeHintsPredicates`

Spring provides an API to verify registered hints:

```java
class GreetingRuntimeHintsTest {

    @Test
    void registersGreetingPayloadReflectionHints() {
        RuntimeHints hints = new RuntimeHints();
        new GreetingRuntimeHints().registerHints(hints, getClass().getClassLoader());

        assertThat(RuntimeHintsPredicates.reflection()
                .onType(GreetingPayload.class))
                .accepts(hints);
    }
}
```

This is a unit test for metadata registration, not a complete native integration test. It verifies that the registrar declares the expected hint. Native image tests are still necessary to verify the final result in a closed-world environment.

## 9. Limitations and Prerequisites of Test AOT

AOT processing takes place at build time, so a test context needs a configuration stable enough for analysis and code generation. Certain situations may require special handling:

- Configuration depending on environment variables or system properties that vary between build and test runtime.
- Bean definitions created by dynamic logic that the AOT engine cannot infer.
- `ContextCustomizer`, `ContextCustomizerFactory`, or custom test extensions that do not support AOT.
- Configuration relying on resources only available in the test runtime environment, not during the build.
- Tests requiring external services to start during context processing itself.
- Code using reflection, resources, or proxies without the required runtime hints.

With Testcontainers or `@DynamicPropertySource`, pay close attention to when values are produced. AOT processing may need to load the test context at build time; if that requires a container or external service, the build environment must provide them or the test must be designed not to depend on an unstable runtime value during code generation.

Do not assume every integration test can be AOT-processed without modification. Run the Test AOT task on CI or the corresponding build environment to catch incompatible customizers, context configurations, or external dependencies.

### Using `@DisabledInAotMode` When a Test Is Unsuitable

Spring Test provides `@DisabledInAotMode` in supported versions to mark a test class or method that should not run when AOT mode is enabled.

Example:

```java
@SpringBootTest
@DisabledInAotMode("This test depends on runtime-only context mutation")
class RuntimeOnlyConfigurationTest {

    @Test
    void verifiesRuntimeSpecificBehavior() {
        // Test only suitable for a context initialized via standard runtime.
    }
}
```

This annotation is intended for cases with a clear technical reason preventing the test from running in AOT mode. Do not use it to hide AOT errors in tests representing production configuration; tests important for native compatibility still need to be run and fixed to be compatible.

## 10. Test AOT on the JVM vs. Native Test Execution

These two environments provide different levels of verification:

| Execution Mode | What Is Verified | Limitations |
| --- | --- | --- |
| Regular test on JVM | Application logic and context created via standard runtime path | Does not verify generated AOT contexts |
| Test in AOT mode on JVM | Context can be initialized using AOT artifacts | Still runs on JVM, does not test all native image constraints |
| Native integration test | Context, runtime hints, and test code work in a native executable | Slower build, requires GraalVM/native toolchain and appropriate resources |

Do not treat a regular test run as proof of native compatibility. Conversely, native tests typically cost more in build and execution time, so you can select a representative set of integration tests to execute in the native pipeline.

A pipeline can be organized in layers:

```text
Pull request
   |
   +--> Unit tests on JVM
   |
   +--> Integration tests on JVM
   |
   +--> Test AOT processing
             |
             +--> AOT-mode tests on JVM (if configured)
             |
             +--> Native test build/run (per native pipeline)
```

Steps can run at different stages depending on build duration and the criticality of native deployment.

## 11. Organizing Integration Tests for AOT Compatibility

Several practices make test contexts easier to AOT-process:

1. Prefer explicit Spring configuration via `@Configuration`, `@Import`, `@TestConfiguration`, and standard Boot annotations.
2. Keep bean definitions determinable at build time; avoid arbitrarily mutating bean configuration after the context has refreshed.
3. Separate tests depending on dynamic environments from tests verifying core application configuration.
4. Declare runtime hints for custom reflection, resources, and proxies when needed.
5. Ensure test infrastructure such as databases, containers, or mock servers is available during AOT processing if the context requires them.
6. Run both regular tests and AOT tests; the two execution paths can uncover different issues.
7. Select a representative group of native integration tests covering critical application paths.

There is no need to turn every unit test into an AOT test. Focus on integration contexts and components likely to encounter issues in a native runtime.

## 12. Diagnosing Common Errors

### Task `processTestAot` Does Not Exist

Check the Spring Boot plugin version and how the plugin is applied. AOT tasks depend on the Boot release line; do not manually define a task with the same name when the plugin does not yet support it.

### Test Context Cannot Be Processed at Build Time

Read the AOT error to identify the problematic bean definition, context customizer, or property source. Check whether the context depends on external services, environment variables, or values available only at runtime.

### Native Image Is Missing a Class or Resource

Check runtime hints for reflection, serialization, resources, and proxies. Use `RuntimeHintsPredicates` to verify the registrar registers the needed hint; then run native tests to verify the final artifact.

### Test Passes on JVM but Fails in Native Executable

The JVM permits many dynamic behaviors that native image cannot infer automatically. Check reflection, resource paths, serialization, dynamic proxies, JNI, and libraries without native support yet. Add hints or switch to a suitable implementation approach.

### Testcontainers Test Fails During AOT Processing

Determine whether the container is being started during build-time context loading, and whether Docker/runtime is available in the build environment. Configure the pipeline to supply required dependencies or separate unsuitable tests from AOT mode with clear justification.

### AOT Context Starts but Test Behavior Is Wrong

AOT processing verifies how the context is prepared, not that all business rules are correct. You still need assertions for endpoints, repositories, transactions, message handling, and the integration behaviors the test targets.

## 13. Workflow for Rolling Out AOT for Integration Tests

You can roll it out in these steps:

1. Define the goal: speeding up context startup, validating generated contexts, or verifying native compatibility.
2. Check versions of Spring Boot, Spring Framework, build plugins, and GraalVM Native Build Tools.
3. Run regular integration tests to establish a baseline.
4. Run application AOT if production configuration needs verification.
5. Run Test AOT to process contexts declared in the test suite.
6. Fix incompatible configurations or customizers; add runtime hints where needed.
7. Run tests in AOT mode on the JVM if the pipeline supports it.
8. Select representative tests to build and run as a native executable.
9. Monitor build times, native image size, context startup errors, and integration test results in CI.

Keep the Test AOT step frequent enough in the pipeline to catch regressions in test configuration, especially when adding libraries, custom bean factory logic, or changing how resources are loaded.

## 14. Conclusion

AOT processing for Spring integration tests prepares test application contexts at build time, generating initializer code and runtime hints so contexts can be initialized in AOT mode and compatible native environments. `processAot` processes the application context; `processTestAot` processes contexts declared in tests. Native test execution is an additional step to verify the program inside a native executable.

Use Test AOT for integration tests representing important Spring configurations, keep test contexts stable, and declare runtime hints for dynamic behavior when needed. Run regular tests to verify logic, Test AOT to verify generated contexts, and native integration tests to catch closed-world runtime differences. These three verification levels complement one another when an application needs AOT or GraalVM Native Image support.
