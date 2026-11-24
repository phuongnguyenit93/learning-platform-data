# Distinguishing JVM Testing with ApplicationContextRunner from Native Spring Boot Application Testing

## 1. Two distinct testing goals

When a Spring Boot library provides auto-configuration, we usually need to verify two groups of behaviors:

1. **Configuration decisions:** is the default bean created, does a custom bean make auto-configuration back off, and do property/classpath conditions match?
2. **Native execution capability:** can the Spring AOT-processed application start in a GraalVM Native Image, are required reflection/resource/proxy hints retained, and do application flows work in the native executable?

`ApplicationContextRunner` is well suited for the first group. It creates small Spring `ApplicationContext` instances on the JVM to test each condition combination. However, Spring Boot 3.3 explicitly notes that `ApplicationContextRunner` **does not work when running tests in a native image**.

Native testing uses a different mechanism: Spring TestContext Framework provides AOT support for JUnit 5 tests, such as `@SpringBootTest` and test slices. Native Build Tools process the context at build time, create a native test image, and run the JUnit TestEngine inside that image.

Therefore, the two test groups complement each other. Context runners catch auto-configuration logic errors quickly; native tests verify that the application and test contexts operate in the real native environment.

## 2. Map of testing layers

| Test type | Execution environment | Primary goal | When to use |
| --- | --- | --- | --- |
| Plain Java unit test | JVM | Class logic without Spring | Services, mappers, validators, algorithms |
| `ApplicationContextRunner` | JVM | Bean registration, conditions, user overrides, properties, and classpath | Developing auto-configuration |
| Regular `@SpringBootTest` | JVM | Booting a context close to the real application | Multi-bean integration testing |
| AOT mode on JVM | JVM using Spring AOT-generated code | Testing the AOT context and generated initialization code | Before paying native compilation time |
| Native test via `nativeTest` | GraalVM Native Image containing tests | Running Spring integration tests inside a native image | Verifying flows prone to differing from JVM |
| External smoke/integration test | Test process calling a running native executable | Testing the deployed artifact over HTTP or real protocols | Verifying the final native binary/container |

Do not treat every test containing the word "native" as the same kind. `nativeTest` builds a native image containing the test suite and JUnit engine; `nativeCompile` builds the application's native executable. A separate test process calling endpoints of the running executable is a third, black-box testing layer.

## 3. What problem does ApplicationContextRunner solve?

An auto-configuration can vary along several axes:
- Whether the application already declared a bean for the same contract.
- What values properties in `Environment` currently hold.
- Whether optional dependencies are on the classpath.
- Whether prerequisite beans were registered beforehand.
- Whether the context is non-web, servlet, or reactive.

`ApplicationContextRunner` creates an isolated context for each scenario. Common APIs:

| API | Purpose |
| --- | --- |
| `withConfiguration(AutoConfigurations.of(...))` | Loads the auto-configurations under test |
| `withUserConfiguration(...)` | Simulates configuration supplied by the application |
| `withPropertyValues(...)` | Injects properties into Environment |
| `withBean(...)` | Registers fixture/mock beans directly |
| `withClassLoader(new FilteredClassLoader(...))` | Simulates classes or packages absent from the classpath |
| `withInitializer(...)` | Attaches initializers or a Condition Evaluation Report listener |
| `run(context -> ...)` | Opens the context, runs assertions, and closes the context |

The runner does not need to boot a full `SpringApplication`, nor does it require a web server or database if the scenario does not need them. Each `run` creates a separate context, so properties and beans from one test never leak into another.

## 4. JVM example: testing default and custom beans with context runner

Suppose a library has `GreetingService` and an auto-configuration creating a default implementation if the application has not supplied its own bean.

~~~java
package com.example.demo;

import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

class GreetingAutoConfigurationContextRunnerTests {

    interface GreetingService {
        String message();
    }

    static final class DefaultGreetingService implements GreetingService {
        @Override
        public String message() {
            return "hello from library";
        }
    }

    static final class CustomGreetingService implements GreetingService {
        @Override
        public String message() {
            return "hello from application";
        }
    }

    @AutoConfiguration
    static class GreetingAutoConfiguration {

        @Bean
        @ConditionalOnMissingBean(GreetingService.class)
        DefaultGreetingService greetingService() {
            return new DefaultGreetingService();
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class UserGreetingConfiguration {

        @Bean
        CustomGreetingService customGreetingService() {
            return new CustomGreetingService();
        }
    }

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withConfiguration(
                            AutoConfigurations.of(GreetingAutoConfiguration.class));

    @Test
    void createsDefaultWhenApplicationHasNoCustomBean() {
        runner.run(context -> {
            assertThat(context).hasNotFailed();
            assertThat(context).hasSingleBean(GreetingService.class);
            assertThat(context).hasSingleBean(DefaultGreetingService.class);
            assertThat(context.getBean(GreetingService.class).message())
                    .isEqualTo("hello from library");
        });
    }

    @Test
    void backsOffWhenApplicationProvidesCustomBean() {
        runner.withUserConfiguration(UserGreetingConfiguration.class)
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).hasSingleBean(GreetingService.class);
                    assertThat(context).hasSingleBean(CustomGreetingService.class);
                    assertThat(context).doesNotHaveBean(DefaultGreetingService.class);
                    assertThat(context.getBean(GreetingService.class).message())
                            .isEqualTo("hello from application");
                });
    }
}
~~~

Run tests on the JVM:

~~~bash
./gradlew test --tests "*GreetingAutoConfigurationContextRunnerTests"
~~~

Or Maven:

~~~bash
./mvnw -Dtest=GreetingAutoConfigurationContextRunnerTests test
~~~

Both tests verify the two key branches of auto-configuration. The runner can be extended to test property conditions, missing dependencies, multiple candidates, `@Primary`, or `FilteredClassLoader`.

**Important limitation:** this is a JVM test. Spring Boot 3.3 explicitly states that `ApplicationContextRunner` does not work when running tests in a native image. Do not include test classes using the runner in a native test suite expecting them to work like on the JVM.

If a build runs the entire test suite via Native Build Tools, exclude context-runner tests from the native run, for example by marking the class/method with Native Build Tools' `@DisabledInNativeImage` or configuring a separate test list. Those tests still run normally in the JVM `test` task.

## 5. What does `@SpringBootTest` on the JVM verify?

`@SpringBootTest` uses `SpringApplication` to create the test context, so it can include far more application configuration than a context runner. It is suited when you need to test integration across controllers, services, configuration, security, serialization, or auto-configurations working together.

Example of a regular JVM test:

~~~java
@SpringBootTest
class ApplicationContextIntegrationTests {

    @Autowired
    GreetingService greetingService;

    @Test
    void applicationProvidesGreetingService() {
        assertThat(greetingService.message()).isNotBlank();
    }
}
~~~

This test verifies that the application context can start and inject the service. However, it still runs on a standard JVM. It does not yet prove that:
- Spring AOT generates valid initialization code.
- GraalVM retains all required classes/resources/proxies.
- The native executable can start.
- APIs or libraries whose behavior differs in native image still work.

`@SpringBootTest` on the JVM and `@SpringBootTest` running inside a native test image can share test concepts, yet their build pipelines and runtimes are different.

## 6. AOT mode running on the JVM: an intermediate check

Spring AOT analyzes the application at build time and generates optimized code for initializing `ApplicationContext`. You can run the application on the JVM while instructing Spring to use the generated AOT code via a system property:

~~~bash
java -Dspring.aot.enabled=true -jar target/my-application.jar
~~~

The prerequisite is that the artifact must contain AOT output. With Maven, Spring Boot 3.3 can activate the `native` profile to run `process-aot`; with Gradle, apply the GraalVM Native Image plugin so Spring Boot configures the AOT tasks.

Maven example with Spring Boot parent:

~~~bash
./mvnw -Pnative package
java -Dspring.aot.enabled=true -jar target/my-application.jar
~~~

This is still a JVM process. It tests AOT initialization code and catches certain issues early before compiling a native image. It does **not** test GraalVM reachability, the native executable, or native image runtime limitations.

If the application has not enabled an AOT build properly or the JAR does not contain generated assets, setting `spring.aot.enabled=true` will not turn a normal JAR into an AOT artifact. Verify build output and confirm the `processAot` task ran.

## 7. How do native tests work?

Spring Framework supports AOT for JUnit 5 tests using the TestContext Framework. Native Build Tools and Spring Boot coordinate along this general flow:

1. Analyze tests to determine which `ApplicationContext` instances they require.
2. Run AOT processing for each test context and generate corresponding initializers/assets.
3. Feed generated assets into GraalVM Native Image compilation.
4. Package the JUnit `TestEngine` together with the discovered test list into a native test image.
5. Launch the image; the JUnit engine executes the tests and reports results.

Thus, tests using `@SpringBootTest` and Spring test slices can run inside a native image through the TestContext Framework's AOT support.

Difference from context runner:
- `ApplicationContextRunner` creates contexts dynamically inside the test body via the `run` callback; Spring Boot does not support this in native image tests.
- `@SpringBootTest` declares test contexts in a model that Spring TestContext Framework can discover and AOT-process at build time.
- The native test image contains the test engine and generated context initializers, rather than relying on constructing arbitrary contexts at runtime.

## 8. Example application test running inside a native image

Suppose the application has an endpoint:

~~~java
@RestController
class ProbeController {

    @GetMapping("/probe")
    String probe() {
        return "native-ready";
    }
}
~~~

Integration test:

~~~java
package com.example.demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class NativeApplicationTests {

    @Autowired
    TestRestTemplate http;

    @Test
    void httpEndpointWorksInTheNativeTestImage() {
        ResponseEntity<String> response =
                http.getForEntity("/probe", String.class);

        assertThat(response.getStatusCode()).isEqualTo(HttpStatus.OK);
        assertThat(response.getBody()).isEqualTo("native-ready");
    }
}
~~~

This test uses the Spring TestContext Framework and starts a web context on a random port. When run via the native test task, the context and test are AOT-processed and executed inside the native test image.

Example prerequisites:
- The application has `spring-boot-starter-web` and `spring-boot-starter-test`.
- `ProbeController` is registered via component scanning or imported explicitly.
- Native Build Tools, GraalVM, and the native compilation toolchain are installed properly.
- The test context does not depend on dynamic configurations that AOT cannot determine at build time.

This is an integration test example. It checks the endpoint and HTTP response inside the native test image, not an example of `ApplicationContextRunner`.

## 9. Gradle configuration and run commands

With Gradle Groovy DSL, add the Spring Boot plugin and the GraalVM Native Image plugin. Example versions compatible with Spring Boot 3.3.13:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'org.graalvm.buildtools.native' version '0.10.6'
}

dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

When the GraalVM Native Image plugin is applied, the Spring Boot Gradle plugin configures AOT tasks for the application and tests.

Primary commands:

~~~bash
# Fast JVM tests, including ApplicationContextRunner
./gradlew test

# Run supported tests inside the native test image
./gradlew nativeTest

# Compile the application's native executable
./gradlew nativeCompile
~~~

`nativeTest` and `nativeCompile` are two different tasks. The first builds/runs an image containing tests; the second builds the application executable for deployment.

GraalVM Native Image requires a toolchain matching the target OS and architecture. Native builds are typically much slower than JVM tests; therefore, keep `test` as the fast feedback loop and run `nativeTest` in CI or on an appropriate schedule.

## 10. Maven configuration and run commands

When using `spring-boot-starter-parent` 3.3.13, the parent provides a `nativeTest` profile configuring AOT executions for tests. The application module must declare the Spring Boot Maven plugin and the Native Build Tools Maven plugin:

~~~xml
<parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.3.13</version>
    <relativePath/>
</parent>

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

Commands:

~~~bash
# Regular JVM tests
./mvnw test

# Run test AOT processing and execute tests in a native image
./mvnw -PnativeTest test

# Compile the application's native executable
./mvnw -Pnative native:compile
~~~

If not using `spring-boot-starter-parent`, configure equivalent executions for the Spring Boot Maven plugin's `process-test-aot` goal and the Native Build Tools Maven plugin's `test` goal. Simply adding the native plugin without enabling the test AOT workflow does not mean Maven runs tests inside a native image.

## 11. Native test image vs. deployable native executable

The following two artifacts are often confused:

**Native test image**
- Contains test classes and JUnit TestEngine.
- Built to run the test suite in native mode.
- Uses Gradle's `nativeTest` or Maven's `nativeTest` profile.
- Goal is to verify test contexts and behavior in the native runtime.

**Application native executable**
- Contains application code, generated AOT assets, and required reachability hints.
- Does not contain the project's JUnit test suite.
- Built using `nativeCompile` or `native:compile`.
- Goal is the actual deployable artifact.

You can verify the executable after building via an external smoke test:

~~~bash
# Start the native executable in the first terminal
./build/native/nativeCompile/my-application
~~~

Second terminal calls the endpoint:

~~~bash
curl -i http://localhost:8080/probe
~~~

Expected result is HTTP 200 and body `native-ready`. This command tests the running native executable; it is not the `nativeTest` command.

For container images, you can run the native container and send HTTP requests from an external test process or pipeline. That additionally verifies container configuration, port mappings, environment variables, filesystem, and startup commands.

## 12. AOT/native differences that must be tested

Native Image uses static analysis under a closed-world assumption. GraalVM cannot automatically discover every dynamic behavior an application may perform. Notable differences:

### 12.1. Bean graph is decided at build time

During `processAot`, `BeanFactory` is prepared and conditions are evaluated. Therefore, the environment configuration used at build time can decide which beans exist in the native image.

For example, `@ConditionalOnProperty` or `@Profile` used to create beans cannot be treated as arbitrary runtime toggles to add/remove beans after the image is built. Supply the right properties/profiles to the AOT build and test the corresponding configuration.

### 12.2. Reflection, resources, and proxies

Native image can eliminate code not proven reachable. If the application uses reflection, dynamic resource loading by name, serialization, or dynamic proxies, appropriate hints are required.

Spring AOT automatically generates many hints for supported cases. For special cases, you may need to register `RuntimeHints` or additional GraalVM metadata.

### 12.3. Fixed classpath

A native executable is built from the classpath at build time. You cannot add new libraries to the runtime classpath as when running on a standard JVM.

A classpath condition is already resolved during AOT processing; you cannot expect adding a JAR after the build to make a new auto-configuration appear.

### 12.4. Libraries and test frameworks

A library that runs fine on the JVM does not necessarily support native. Tools relying on bytecode instrumentation, dynamic class loading, reflection, or proxies need dedicated testing. Do not assume every mock framework or test extension is compatible just because JVM tests pass.

## 13. Recommended test matrix for an auto-configuration library

| Area | JVM context runner | AOT on JVM | Native test / native executable |
| --- | --- | --- | --- |
| Default bean registered | Very suitable | Can additionally test AOT context | Smoke/integration test if it affects runtime |
| User bean makes default back off | Very suitable | Verify selected build-time configuration | Test context with `@SpringBootTest` if needed |
| `@ConditionalOnProperty` | Test many values quickly | Verify values used during AOT build | Verify image is built with the right config |
| `@ConditionalOnClass` | Use `FilteredClassLoader` | Verify generated context for present dependencies | Verify native image has right dependencies/hints |
| Bean wiring and HTTP | Only when a small context suffices | Test AOT initialization | Native `@SpringBootTest` or black-box HTTP |
| Reflection/resource/proxy hints | `RuntimeHints` unit tests can help | Inspect AOT code and generated hints | Native test/executable is stronger runtime proof |
| Startup and container config | Not the primary goal | Does not replace deploy testing | Run executable/container and smoke test |

This matrix avoids two extremes: running only context runners and assuming native is fine, or running native image for every test when most logic can be verified quickly on the JVM.

## 14. Balanced CI workflow

A practical pipeline can be split into tiers:

~~~mermaid
flowchart TD
    A["Every code change"] --> B["Unit tests + ApplicationContextRunner on JVM"]
    B --> C["Spring integration tests on JVM"]
    C --> D["AOT processing and running app on JVM"]
    D --> E["Native test image: @SpringBootTest / test slices"]
    E --> F["Build native executable"]
    F --> G["Smoke test executable or container"]
~~~

A sensible allocation:
- Run unit tests and context runners on every pull request because they are fast.
- Run Spring integration tests on the JVM in every build.
- Run AOT mode on the JVM to catch generated initialization errors before native compilation.
- Run a curated set of native tests in CI; can run nightly if compilation takes long.
- Run smoke tests on the native executable/container before release.

Not every CI branch needs to compile a native image. Prioritize testing code paths where real differences exist between JVM and native, such as reflection, resource access, serialization, proxies, optional classpaths, and build-time configuration.

## 15. Common errors and diagnostics

| Symptom | Cause | Resolution |
| --- | --- | --- |
| `ApplicationContextRunner` fails in `nativeTest` | Runner is not supported when running tests in a native image | Keep runner tests on JVM; exclude from native suite or use `@DisabledInNativeImage` |
| JVM tests pass yet native tests fail during AOT build | Test context or configuration has parts unanalyzable at build time | Check TestContext configuration, dynamic bean registration, and build-time properties |
| Native app lacks property-enabled bean | Condition was evaluated during AOT build with a different Environment than runtime | Set right property/profile in AOT build environment and rebuild image |
| Native executable reports missing resource | Resource was not detected by reachability analysis | Register resource hint and re-verify native image |
| Reflection works on JVM yet fails in native | Missing reflection hint or unsupported API | Use Spring RuntimeHints/GraalVM metadata and write a native regression test |
| Proxied bean behaves wrongly in native | Proxy type/interface was not recognized or has AOT limits | Check proxy strategy, generated hints, and native test case |
| `nativeTest` finds no tests | Tests are not in JUnit 5/TestContext pipeline or build plugin is unconfigured | Check dependencies, plugins, profiles, and task reports |
| Native tests take too long | Compiling the native test image is expensive | Keep most tests on JVM; put only critical native scenarios in the suite |
| Native executable runs yet endpoint errors | Checked only startup, not HTTP/integration flow | Send requests from an external process and assert status/body |
| AOT JVM test uses a different context than production | Build-time properties/profiles differ from release configuration | Align AOT build Environment with target deployment profile |

### Investigation checklist

1. Confirm whether the error occurs in JVM tests, AOT processing, native test image, or native executable.
2. Check which conditions and profiles were evaluated at build time.
3. Verify generated AOT classes/resources exist in the artifact.
4. Check reflection/resource/proxy/serialization hints.
5. Read logs from `processAot`, `processTestAot`, and the native-image compiler.
6. Reproduce with a small JVM test before escalating native complexity.
7. Run native smoke tests on the exact target OS/architecture and near-production configuration.

## 16. Principles for choosing tools

- Use `ApplicationContextRunner` to quickly verify auto-configuration logic on the JVM: defaults, back-off, properties, classpath, and dependency conditions.
- Use `@SpringBootTest` on the JVM to test application integration with SpringApplication and real beans.
- Use AOT mode on the JVM to verify generated initialization code before native compilation.
- Use `@SpringBootTest` or test slices run through `nativeTest` for scenarios that need to prove TestContext works in a native image.
- Use an external test process to call the native executable/container and verify deployment protocols.
- Keep native-incompatible tests, such as those using `ApplicationContextRunner`, out of the native suite.
- Do not treat the native test image as the production native executable; run a dedicated smoke test on the deployable artifact.
- Document profiles/properties used during AOT builds because bean-creation conditions are decided at build time.
- Expand the native suite only for specific native risks; keep the JVM feedback loop fast and easy to run in the IDE.

## 17. Knowledge self-check

1. Which type of test is `ApplicationContextRunner` best suited for? **Testing auto-configuration, bean conditions, and Environment on the JVM.**
2. Can `ApplicationContextRunner` run inside native image tests? **No; Spring Boot 3.3 explicitly states the runner does not work in native image tests.**
3. Which tests can be processed by Spring TestContext AOT to run natively? **JUnit 5 integration tests using the TestContext Framework, such as `@SpringBootTest` and test slices.**
4. What kind of artifact does `nativeTest` produce? **A native image containing the tests and JUnit TestEngine to run the test suite.**
5. What does `nativeCompile` produce? **The application's native executable.**
6. Does `spring.aot.enabled=true` turn the JVM into a native image? **No; it instructs the JVM to use the generated AOT initialization code.**
7. Why must property conditions be checked at build time? **The bean graph is prepared and conditions are evaluated during AOT processing.**
8. Can native image automatically retain every class invoked via reflection? **No; appropriate reachability hints are needed for reflection/resources/proxies when Spring cannot infer them.**
9. Why keep most tests on the JVM? **Fast feedback loop, strong IDE support, and high native image build cost.**
10. After `nativeCompile` succeeds, what testing is still needed? **Running the executable/container and smoke/integration testing critical flows.**

## Official References

- [Spring Boot 3.3 — Testing your Auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html): how to use `ApplicationContextRunner`, context customizations, and the note that the runner does not work in native image tests.
- [Spring Boot 3.3 — Testing GraalVM Native Images](https://docs.spring.io/spring-boot/3.3/how-to/native-image/testing-native-applications.html): strategy for keeping most tests on JVM, AOT mode on JVM, and native testing with Native Build Tools.
- [Spring Boot 3.3.13 — Maven Ahead-of-Time Processing](https://docs.spring.io/spring-boot/3.3/maven-plugin/aot.html): `process-aot`, `process-test-aot`, build-time BeanFactory, and the nativeTest profile.
- [Spring Boot 3.3 — Gradle Plugin Ahead-of-Time Processing](https://docs.spring.io/spring-boot/3.3/gradle-plugin/aot.html): `processAot`, `processTestAot`, `nativeTest`, and `nativeCompile` tasks.
- [Spring Boot 3.3 — Introducing GraalVM Native Images](https://docs.spring.io/spring-boot/3.3/reference/packaging/native-image/introducing-graalvm-native-images.html): closed-world, fixed classpath, AOT, and native limitations.
- [Spring Boot 3.3.13 — System Requirements](https://docs.spring.io/spring-boot/3.3/system-requirements.html): compatible Java, GraalVM, and Native Build Tools.
