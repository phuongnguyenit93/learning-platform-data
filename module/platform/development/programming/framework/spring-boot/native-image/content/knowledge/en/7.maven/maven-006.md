# The `nativeTest` profile and `spring-boot:process-test-aot`

When compiling **Spring Boot** to a **GraalVM Native Image**, testing on the JVM alone is not enough. Application code may run fine on the JVM yet fail in a native executable due to reflection, resources, proxies, or context initialization differences compared to JVM execution. To catch these issues early, Maven can run your test suite inside a **native test image**, supported by **Spring AOT** and **GraalVM Native Build Tools**.

In the **Maven** chapter of the **`SPRING_BOOT_NATIVE_IMAGE`** module, we will explore the `nativeTest` profile, the `spring-boot:process-test-aot` goal, and how they work together in the Maven lifecycle. This lesson aligns directly with the module's goals: building Spring Boot native via Spring AOT, verifying compatibility, identifying reflection/resource issues, and preparing to measure startup, memory, and native executable/container operations.

> **Scope note:** `nativeTest` is a **project-declared profile name** commonly seen in native-ready Spring Boot projects; it is not a built-in profile present in every Maven project. The examples below assume compatible versions of Spring Boot, GraalVM Native Build Tools, and JDK/GraalVM. Goal names and bindings may be adjusted depending on project configuration and plugin versions.

## 1. Learning objectives

After this lesson, you will be able to:

- Explain how a **native test** differs from standard tests run by Maven Surefire on the JVM.
- Distinguish the roles of **`spring-boot:process-test-aot`**, **`native:test`**, and the **`nativeTest`** profile.
- Configure Maven to process test contexts with Spring AOT before building and running a native test image.
- Run and interpret `./mvnw -PnativeTest test`; identify whether errors occur during Java compilation, Spring AOT, Native Image compilation, or test runtime.
- Choose the appropriate test type when evaluating compatibility before packaging a Spring Boot Native Image.

## 2. Why is separate testing on Native Image needed?

On the JVM, many libraries can load classes dynamically, access classes/members via reflection, and read classpath resources at runtime. GraalVM Native Image performs **reachability analysis** at build time; code and metadata that are not properly recognized may be omitted from the final executable.

For example:

~~~java
Class<?> type = Class.forName("com.example.payment.PaymentAdapter");
Object instance = type.getDeclaredConstructor().newInstance();
~~~

If Native Image cannot infer this dynamic access and the project lacks the corresponding **reachability metadata/Runtime Hints**, the native program can fail even though unit tests pass on the JVM. Similarly, a config file, template, or data file in `src/main/resources` may need to be declared so Native Image includes it in the binary.

With Spring Boot, **Spring AOT** analyzes Spring configuration and generates code/metadata to support building the native image. **Test AOT** additionally processes configurations that appear only in tests: Spring test contexts, test configurations, bean overrides, test profiles, and related needs.

Key differences:

| Execution method | Environment | What does it catch well? | Limitations |
|---|---|---|---|
| `./mvnw test` | JVM and Maven Surefire per default config | Java logic, most regular unit/integration tests | Does not prove code compatibility with AOT/Native Image analysis |
| `./mvnw -PnativeTest test` | Native test image, when profile is fully configured | Test contexts, reflection/resources, behavior when tests run in native | Longer build time; does not replace testing the final app binary |
| Running the native app binary and calling endpoints | Application's native executable | Startup, real wiring, deployment config, behavior, and runtime resources | Does not automatically run all JUnit assertions without an external test harness |

**A native test image is different from the application executable.** It typically contains test classes and components needed by JUnit Platform (or a supported test framework) to execute tests. Therefore, native tests can uncover compatibility issues, but passing them does not mean the production executable has been built, containerized, and fully verified.

## 3. Three components of the workflow

### 3.1. The `nativeTest` profile

A **Maven profile** is a conditional set of configurations in `pom.xml` or another supported Maven location. A profile can add plugins, executions, dependencies, or properties. Only when the profile is activated do those changes enter the build's effective POM.

The command:

~~~bash
./mvnw -PnativeTest test
~~~

means **activate the profile with id `nativeTest`** and execute the Maven lifecycle up to the `test` phase. Maven does not intrinsically know that the name `nativeTest` must run Native Image; that behavior exists only when the profile declares the appropriate plugins/executions.

### 3.2. The `spring-boot:process-test-aot` goal

This goal belongs to the **Spring Boot Maven Plugin** (`org.springframework.boot:spring-boot-maven-plugin`). Its job is to process **Spring test contexts** using AOT: analyzing the Spring contexts required by tests, generating context initialization support code, and preparing the necessary information for the AOT/native pipeline.

It **does not compile the native executable itself** and **does not run JUnit tests itself**. It prepares the Spring side so Native Image can build and run tests properly.

### 3.3. The `native:test` goal

The `test` goal of the **GraalVM Native Build Tools Maven Plugin** (`org.graalvm.buildtools:native-maven-plugin`), commonly called `native:test`, performs the Native Image side of the work: using compiled tests and required configuration to build a **native test executable**, then executing tests with that executable.

Do not confuse the two goals that both contain the word "test":

- `spring-boot:process-test-aot`: processes **test code and Spring test contexts**.
- `native:test`: **compiles/runs tests with Native Image**.
- Maven lifecycle phase `test`: the stage in the Maven lifecycle where test goals are bound according to configuration.

## 4. How the steps connect in the Maven lifecycle

With a properly configured native test profile, the conceptual flow is:

~~~mermaid
flowchart TB
    A["mvn -PnativeTest test"] --> B["Activate nativeTest profile"]
    B --> C["Compile main/test classes per Maven lifecycle"]
    C --> D["spring-boot:process-test-aot"]
    D --> E["Generated test AOT code and metadata"]
    E --> F["GraalVM native-maven-plugin: test"]
    F --> G["Native Image analyzes and compiles test executable"]
    G --> H["Run tests in native environment"]
    H --> I["Pass/fail results and reports"]
~~~

Relevant Maven phases:

| Phase / goal | Role |
|---|---|
| `compile` and preparatory phases | Compiles application code and executes project setup tasks |
| `test-compile` | Compiles test classes and test sources |
| `process-test-classes` | A suitable point to run `process-test-aot` after test classes exist |
| `test` | Runs tests; the profile can bind `native:test` here |

**Ordering matters greatly:** Spring AOT must see prepared test classes and contexts. Do not place `process-test-aot` in an overly early phase, or invoke this goal standalone on a `target` directory lacking compiled test classes and expect the same outcome as a full lifecycle.

In plugin versions that define a default phase for `process-test-aot`, Maven can bind the goal automatically to the appropriate phase even when `<phase>` is omitted from the execution. The example below declares `process-test-classes` explicitly so the sequence is clear to learners. When using a POM generated by Spring Initializr or your project tooling, preserve the active binding mechanism and check the effective POM before adding executions.

## 5. Sample `nativeTest` profile configuration in `pom.xml`

The example focuses on a **Spring Boot Maven** project that already manages versions for Spring Boot Maven Plugin and GraalVM Native Build Tools. If your project does not manage plugin versions yet, declare compatible versions via `<version>` or `<pluginManagement>`.

~~~xml
<profiles>
    <profile>
        <id>nativeTest</id>
        <build>
            <plugins>
                <plugin>
                    <groupId>org.springframework.boot</groupId>
                    <artifactId>spring-boot-maven-plugin</artifactId>
                    <executions>
                        <execution>
                            <id>process-test-aot</id>
                            <phase>process-test-classes</phase>
                            <goals>
                                <goal>process-test-aot</goal>
                            </goals>
                        </execution>
                    </executions>
                </plugin>

                <plugin>
                    <groupId>org.graalvm.buildtools</groupId>
                    <artifactId>native-maven-plugin</artifactId>
                    <extensions>true</extensions>
                    <executions>
                        <execution>
                            <id>test-native</id>
                            <phase>test</phase>
                            <goals>
                                <goal>test</goal>
                            </goals>
                        </execution>
                    </executions>
                </plugin>
            </plugins>
        </build>
    </profile>
</profiles>
~~~

Meaning of each part:

1. **`<id>nativeTest</id>`**: enables activation via `-PnativeTest`. This name is a project convention; Maven does not provide built-in profile contents for it.
2. **`spring-boot-maven-plugin`**: invokes `process-test-aot` when the lifecycle reaches `process-test-classes`, i.e., after test code has been compiled.
3. **`native-maven-plugin`**: provides the `test` goal to build and run the native test image when Maven reaches the `test` phase.
4. **`<extensions>true</extensions>`**: enables the plugin as a Maven extension under this configuration. Plugin lifecycle/test handling behavior can vary across releases; cross-check the effective POM and execution logs.

**This is an example showing the required structure, not an instruction to copy blindly into every project.** If `pom.xml` already has a `nativeTest` profile and these plugins, adding duplicate executions can cause AOT or native tests to run repeatedly. Inspect your existing configuration first.

### Can this be written under an existing plugin configuration?

Yes. In Maven, a plugin can be declared in the shared `<build><plugins>` block while a profile adds executions or conditional configuration. Maven merges plugin configurations according to effective POM rules. What matters is inspecting the **final resolved configuration when the profile is active**, not just where you inserted an XML block.

In multi-module projects, do not mechanically put native test executions in every module. Only modules with tests requiring native verification and suitable Spring Boot/Native Build Tools configuration should execute this pipeline.

## 6. Example Spring Boot test processed by test AOT

Suppose the application has a service:

~~~java
package com.example.demo;

import org.springframework.stereotype.Service;

@Service
public class GreetingService {
    public String greet(String name) {
        return "Hello, " + name;
    }
}
~~~

Write a test using a Spring context:

~~~java
package com.example.demo;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest
class GreetingServiceNativeTests {

    @Autowired
    GreetingService greetingService;

    @Test
    void shouldInjectAndCallService() {
        assertThat(greetingService.greet("Native"))
                .isEqualTo("Hello, Native");
    }
}
~~~

The test assumes the project has `spring-boot-starter-test` in `test` scope and a Spring Boot application class (`@SpringBootApplication`) in an appropriate package so `@SpringBootTest` can locate the configuration.

With `./mvnw test`, the test normally runs on the JVM per Maven configuration. With `./mvnw -PnativeTest test` and the profile configured, the corresponding Spring test context can be **analyzed at build time** and used for native test execution. Building the native test executable is handled by GraalVM Native Build Tools.

### Why not use only a plain Java unit test?

A unit test such as:

~~~java
@Test
void returnsMessage() {
    assertThat(new GreetingService().greet("Native"))
            .isEqualTo("Hello, Native");
}
~~~

is still useful and can run inside a native test image when supported. However, it does not verify Spring context initialization, dependency injection, or Spring configuration processing during AOT. Therefore, a native test suite should include at least a few tests exercising a **real Spring context** alongside pure Java unit tests.

Conversely, not every test needs `@SpringBootTest`; spinning up large contexts for all tests increases build time and the amount of AOT configuration to process. Choose a level of testing proportionate to your goal.

## 7. Run guide: JVM first, native second

### Step 1: verify the build environment

In the Maven project's terminal:

~~~bash
java -version
native-image --version
./mvnw -version
~~~

These three commands show Java on `PATH`, the Native Image tool, and the JDK Maven uses. They do **not necessarily** point to the same JDK if the machine has multiple installations or Maven/plugins configure a separate toolchain.

To compile native directly on the host, the machine needs a **GraalVM JDK with Native Image**, appropriate Maven plugins, and the native compiler/linker tools required by the OS (such as the C/C++ toolchain on Linux/macOS or Visual Studio C++ Build Tools on Windows).

### Step 2: run JVM tests first

~~~bash
./mvnw test
~~~

If the test suite still fails on the JVM, fix functional, dependency, or Spring configuration issues before investigating Native Image differences. Native test builds normally take significantly more time and resources than JVM tests.

### Step 3: activate the native test profile

~~~bash
./mvnw -PnativeTest test
~~~

When the profile is configured properly, observe this sequence:

1. Maven compiles application and test code.
2. Spring Boot plugin runs test AOT processing.
3. GraalVM Native Build Tools builds and runs the native test executable.
4. Maven collects pass/fail results.

A native test image bundles tests and required components, so artifact size and compile time can be larger than expected from the number of tests alone. Tests running in a native executable **do not necessarily complete faster overall than on the JVM**, because AOT compilation time is part of the build cost.

### Step 4: on error, inspect stack traces/logs

~~~bash
./mvnw -PnativeTest test -e
~~~

If you need to inspect plugin configurations and detailed native commands:

~~~bash
./mvnw -PnativeTest test -X
~~~

Maven `-X` logs are extremely verbose; enable them only when diagnosing root causes, and review before sharing since they may expose paths, arguments, or environment settings.

### Step 5: confirm the right profile is active

If the project has Maven Help Plugin available or can resolve it, check:

~~~bash
./mvnw help:active-profiles -PnativeTest
./mvnw help:effective-pom -PnativeTest
~~~

In the effective POM, look for executions of `spring-boot-maven-plugin` and `native-maven-plugin`. If they are missing, the profile is likely undefined or configured in another module. This step is especially helpful in projects with parent POMs or multiple submodules.

## 8. Is calling `spring-boot:process-test-aot` directly enough?

No. The command:

~~~bash
./mvnw spring-boot:process-test-aot
~~~

only asks Maven to run the **Spring AOT test processing goal**. It is not equivalent to `./mvnw -PnativeTest test`, because it does not compile Native Image or execute native tests by default.

Moreover, this goal requires inputs such as **compiled test classes and test context metadata**. If invoked directly before the project runs preparatory phases, the goal may miss required data or produce results inconsistent with the official pipeline.

A partial check, depending on the Spring Boot/plugin version:

~~~bash
./mvnw test-compile spring-boot:process-test-aot
~~~

This runs `test-compile` before calling the goal, but **still does not run `native:test`**. It helps separate AOT errors from Native Image errors when troubleshooting. To run the full configured pipeline, prefer:

~~~bash
./mvnw -PnativeTest test
~~~

### How does `process-aot` differ from `process-test-aot`?

| Goal | Primary inputs | Intended output |
|---|---|---|
| `spring-boot:process-aot` | Application configuration, bean definitions, and runtime behavior for `main` | AOT code/metadata for the application |
| `spring-boot:process-test-aot` | Test configurations and Spring test contexts for `test` | AOT code/metadata enabling native tests to start Spring contexts properly |
| `native:compile` or plugin native build goal | Compiled app code and metadata | Application native executable |
| `native:test` | Test classes, test framework, and required metadata | Native test executable and test execution results |

In particular, **do not substitute `process-aot` for `process-test-aot` and expect test contexts to be processed automatically**. Test-specific details (test configurations, test profiles, context customizers) differ from the main application configuration.

## 9. Output locations and reading results

In a Maven/Spring Boot workflow, generated AOT code and metadata usually appear under the **`target`** directory tree, such as the Spring AOT output area. Exact paths vary by Spring Boot version and plugin settings, so check the **`process-test-aot` goal logs** rather than relying on a hardcoded directory path.

Once Maven completes, verify:

- **AOT test processing** actually ran; logs must show the corresponding Spring Boot goal.
- **The native test image** was built with GraalVM; look for native compiler output rather than only seeing Maven Surefire running on the JVM.
- **Test assertions** executed with clear pass/fail outcomes.
- Test reports inside Maven's output directory contain expected data; report location and format depend on plugins and project setup.

Never claim "native tests passed" merely because Maven exited with code 0 if the profile never invoked the native plugin. That might have been just a JVM test run or zero tests selected.

## 10. Potential incompatibilities with test AOT

### 10.1. Spring test contexts altered entirely at runtime

Spring AOT needs to **analyze** context configuration ahead of time. A test that creates or mutates bean definitions in ways only discoverable at runtime can be hard to handle once the native test image is compiled. This does not mean all Spring test features are forbidden; check how they interact with AOT in your Spring version.

For instance, if a test selects a configuration or implementation via a dynamic class name string, verify whether Native Image has the required metadata and code.

### 10.2. Mocks, spies, and dynamic proxies

Tests using Mockito or runtime proxy/subclass generation may encounter limitations in a native environment depending on library versions and instantiation techniques. Mock/spy mechanisms are particularly sensitive if they rely on runtime bytecode generation or dynamic class loading.

Do not rush to delete every mock. Instead, classify which tests are pure JVM unit tests, which need a real Spring context, and which genuinely add value inside a native test image. If a test requires unsupported dynamic behavior, consider a simple test implementation or testing at another layer.

### 10.3. Missing reflection or resources

If a test uses:

~~~java
getClass().getResourceAsStream("/fixtures/sample.json");
~~~

or instantiates objects via reflection, passing on the JVM does not guarantee the resource/class is included in Native Image. When a native error occurs, distinguish:

- Is the resource in the right place on the Maven test classpath?
- Did Spring AOT/Runtime Hints or reachability metadata declare the required dynamic accesses?
- Does the resource name/path differ when running the test image?

Calls like `RuntimeHints.resources().registerPattern(...)` or appropriate reflection registrations may be necessary, but base them strictly on actual errors and code rather than adding broad metadata indiscriminately.

### 10.4. Test technologies requiring JVM process hooks

Tests relying on Java agents, instrumentation, the attach API, or full JVM JIT/classloader capabilities may not work inside a native executable. A native test image is not a JVM with full dynamic bytecode modification capabilities.

### 10.5. Missing OS or external resources

Native Image requires a compatible compiler/linker. Integration tests may also need databases, brokers, Docker, or external services depending on how the project writes tests. A "cannot connect to database" failure after the image builds successfully is not automatically an AOT bug.

## 11. Troubleshooting errors by stage

| Stage | Symptom | How to investigate |
|---|---|---|
| Maven profile | `-PnativeTest` still does not invoke the native plugin | Verify profile existence, effective POM, and active module |
| Java/test compile | `Compilation failure` or invalid test code | Check JDK compiler, `maven-compiler-plugin`, dependencies, and Java release |
| Spring test AOT | `process-test-aot` fails analyzing context/test configuration | Read Spring AOT exception and test config; isolate the failing context |
| Native image analysis | Unrecognized reflection/resource or unsafe class initialization detected | Inspect Native Image diagnostics, add metadata or adjust initialization |
| Native compilation/linking | Missing `native-image`, C/C++ compiler/linker, or OS libraries | Verify GraalVM JDK, PATH/toolchain, and OS requirements |
| Native test runtime | Assertion failure, context startup failure, missing runtime resource | Distinguish logic bugs from native behavior; inspect stack traces and test logs |
| Reporting | Build succeeds but no native tests ran | Confirm test goal ran, test suite matched filters, and executed test count |

### Scenario A: `process-test-aot` succeeds, but `native:test` fails

This is completely possible. Spring AOT handles only the Spring side, whereas Native Image must analyze and compile the entire code graph and test framework. Inspect the **first Native Image error message**: missing metadata, build-time retained objects, an unsupported feature, or a native linker error?

**Do not blindly add another Spring Boot goal** if the failure happens during the Native Image stage.

### Scenario B: `native:test` finishes building, but a `@SpringBootTest` fails

Inspect the context and test-specific configuration. If the test fails only in native mode, compare how it uses reflection, resources, mocks/proxies, profiles, and environment-dependent settings. Context initialization may be generated by AOT code, so mutating contexts dynamically at runtime may not behave like on the JVM.

### Scenario C: calling `spring-boot:process-test-aot` and concluding native tests ran

That conclusion is wrong: the AOT goal does not build or run the test executable. Check `native:test` or a pipeline binding an equivalent goal to the lifecycle.

### Scenario D: `./mvnw -PnativeTest test` passes suspiciously fast

Native test compilation can be faster when cached, but if there are no native compiler logs or test execution counts, inspect the effective POM, test reports, and profile activation. The profile might lack a native execution, or all tests might have been skipped or undiscovered.

## 12. Native tests vs. testing the production native executable

Native tests are highly valuable because they execute JUnit tests under Native Image and verify Spring test context compatibility. Even so, your release workflow must still test the **final application executable**:

1. Build the native application with the project's profile/goal (e.g., `./mvnw -Pnative native:compile`, if the POM defines the `native` profile properly).
2. Start the executable on the target OS/architecture.
3. Verify real endpoints, data, database migrations, environment variables, secrets/configuration, resources, and serialization.
4. If containerized, run the image under an operational configuration matching deployment.
5. Measure startup and memory on both JVM and native builds under identical workloads/infrastructure.

**The native test image is not a deployable artifact.** Passing native tests is a strong compatibility signal, but it does not replace smoke tests, integration tests against the production executable, and container verification.

### Separating `native` and `nativeTest` profiles

Many projects follow the convention:

| Profile | Purpose | Example command |
|---|---|---|
| `native` | Build the application's native executable | `./mvnw -Pnative native:compile` |
| `nativeTest` | Build/run the native test image | `./mvnw -PnativeTest test` |

This is a **POM convention**, not automatic functionality triggered by profile names. A project may choose different names or combine configurations as long as goals and lifecycle phases are explicit.

In CI, it is common to run JVM unit tests first for fast feedback, then run native tests when compatibility verification is needed, followed by building/deploying the native application and running smoke tests. Pipeline depth depends on project size and build budget.

## 13. Notes for multi-module Maven projects

In multi-module Maven builds, a parent POM may manage plugins, yet not every module contains a Spring Boot application or Spring context tests. If placing `nativeTest` in the parent:

- Identify which modules contain tests that need native execution.
- Check whether plugin executions are inherited or only declared in `pluginManagement`.
- Do not assume every module includes `spring-boot-maven-plugin` and identical AOT test configuration.
- When troubleshooting, run against the appropriate module or use `-pl` with matching Maven reactor flags.

Example (replace `app-service` with the actual artifact/module):

~~~bash
./mvnw -pl app-service -am -PnativeTest test
~~~

This command may cause Maven to run the `test` phase across dependent reactor modules as well. If only the application module is configured for native tests, check how the whole reactor behaves and which test goals apply before putting this command in CI. Avoid applying a native test profile across every module if unnecessary build scope can be avoided.

## 14. Practice exercises

**Exercise 1 — Profile check:** A project runs `./mvnw -PnativeTest test` and succeeds. How do you verify tests actually ran on Native Image?

**Suggested answer:** check the effective POM and logs to confirm `process-test-aot` and `native:test` executed; look for the native test image compilation step, executed test count, and test reports. A Maven exit code of 0 alone is insufficient.

**Exercise 2 — Wrong goal purpose:** A team runs `./mvnw spring-boot:process-test-aot` and considers native testing complete. What step is missing?

**Suggested answer:** compiling and executing the native tests via GraalVM Native Build Tools, typically the `native:test` goal in a configured lifecycle.

**Exercise 3 — Resource error:** A test opens `/fixtures/sample.json`, passes on the JVM, and fails in native. Name three places to inspect.

**Suggested answer:** verify the file and test classpath; check reachability/resource metadata/Runtime Hints; inspect the access path and native test image runtime logs.

**Exercise 4 — Real native binary:** `nativeTest` passes, but the production executable crashes reading a different environment variable than at build time. Is there a contradiction?

**Suggested answer:** no. The native test image and the application executable are separate artifacts; they can have different initialization configs, environments, and workloads. Verify runtime behavior on the production executable directly.

**Exercise 5 — AOT diagnosis:** Maven reports an error from `spring-boot:process-test-aot` while initializing a Spring test context. Should you immediately replace the Native Image JDK?

**Suggested answer:** there is no evidence yet that changing the JDK is needed. Read the test context/AOT exception first, isolate the failing test, and review the Spring configuration. Only check JDK/GraalVM versions if logs indicate a compatibility or toolchain issue.

## 15. Project adoption checklist

- [ ] POM defines the `nativeTest` profile rather than passing an undefined profile name.
- [ ] Spring Boot Maven Plugin has a `process-test-aot` execution in an appropriate phase after `test-compile`.
- [ ] GraalVM Native Build Tools has the `test` goal wired into the pipeline to build/run the native test image.
- [ ] Versions of Java, Spring Boot, GraalVM Native Image, and Maven plugins are compatible.
- [ ] GraalVM includes the `native-image` executable and full OS C/C++/linker toolchain.
- [ ] Baseline JVM tests pass before running expensive native builds.
- [ ] Representative `@SpringBootTest` tests verify real Spring test contexts.
- [ ] Reflection/resource issues and mock/proxy mechanisms are investigated in the native environment.
- [ ] Logs and reports confirm the native test image executed with clear test counts.
- [ ] Dedicated smoke/integration tests cover the final production executable/container.
- [ ] Startup, memory, and compatibility are measured/evaluated on the deployed app, not inferred from test image results.

**Key takeaway:** the **`nativeTest`** profile orchestrates the pipeline via Maven; **`spring-boot:process-test-aot`** prepares AOT code and metadata for Spring test contexts; and GraalVM Native Build Tools' **`native:test`** builds and runs the native test image. Together they help uncover compatibility issues before releasing a Spring Boot Native Image application, though native test results must still be complemented by testing the real production executable and container.
