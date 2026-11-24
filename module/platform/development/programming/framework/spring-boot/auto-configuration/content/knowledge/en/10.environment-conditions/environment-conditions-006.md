# `@ConditionalOnJava` and Accepted JVM Version Ranges

## 1. Purpose: Selecting Beans by the Running JVM

In Spring Boot Auto Configuration, sometimes an integration is only suitable when the application runs on a certain Java version. For example:

- An optimized adapter designed for **Java 21 and above**.
- A compatibility adapter for **Java before 21**.
- A configuration branch meant to activate only when the JVM falls within a verified version range.

Spring Boot's `@ConditionalOnJava` lets Spring decide whether to register a configuration class or a `@Bean` method based on **the JVM version actually running the application**.

~~~java
import org.springframework.boot.autoconfigure.condition.ConditionalOnJava;
import org.springframework.boot.system.JavaVersion;

@Bean
@ConditionalOnJava(JavaVersion.TWENTY_ONE)
MyAdapter java21Adapter() {
    return new MyAdapter();
}
~~~

This is an **illustrative snippet**: `MyAdapter` and the class containing the `@Bean` method must be defined by the project. With the configuration above, the `java21Adapter` bean definition is only considered for registration if the JVM is Java 21 or newer. If the application runs on Java 17 or Java 20, that bean method is not registered.

Two points to remember right from the start:

1. The annotation checks the **runtime JVM**, not the version number in `build.gradle`, `pom.xml`, the compiler `--release` option, or a property in `application.yml`.
2. The annotation **does not upgrade Java**, does not convert Java 21 bytecode into Java 17 bytecode, and cannot fix startup failures caused by an incompatible JVM version.

Within the scope of Spring Boot **3.3**, Java 17 is the minimum required to run the framework. Therefore all JVMs supported by this Spring Boot branch satisfy `JavaVersion.SEVENTEEN` or newer; the condition is most practically useful when comparing higher thresholds.

## 2. Syntax, `value` and `range` Attributes

API:

~~~java
org.springframework.boot.autoconfigure.condition.ConditionalOnJava
~~~

The annotation can be used on a **class** (`@Configuration` or `@AutoConfiguration`) and on a **method** (`@Bean`). It has two attributes:

| Attribute | Type | Meaning |
| --- | --- | --- |
| `value` | `org.springframework.boot.system.JavaVersion` | Reference Java version; **required**. |
| `range` | `ConditionalOnJava.Range` | Which side of the threshold is accepted; defaults to `EQUAL_OR_NEWER`. |

`Range` has exactly **two** constants to use in Spring Boot 3.3:

| `range` | Comparison on Java feature version | Boundary semantics |
| --- | --- | --- |
| `Range.EQUAL_OR_NEWER` | Current JVM **≥** `value` | Includes the threshold version; no upper bound. |
| `Range.OLDER_THAN` | Current JVM **<** `value` | **Excludes** the threshold version; no lower bound in the annotation itself. |

Example:

~~~java
@ConditionalOnJava(JavaVersion.TWENTY_ONE)
~~~

Completely equivalent to:

~~~java
@ConditionalOnJava(
    value = JavaVersion.TWENTY_ONE,
    range = ConditionalOnJava.Range.EQUAL_OR_NEWER
)
~~~

Both only match when **Java ≥ 21**.

Conversely:

~~~java
@ConditionalOnJava(
    value = JavaVersion.TWENTY_ONE,
    range = ConditionalOnJava.Range.OLDER_THAN
)
~~~

Only matches when **Java < 21**. On Spring Boot 3.3, the typical usable JVM group for this condition starts at Java 17 because the framework does not support older runtimes.

**Easy to confuse:** the name `OLDER_THAN` is a **strictly less-than** comparison, not less than or equal to. A Java 21 JVM **does not** match `OLDER_THAN(TWENTY_ONE)`.

## 3. JVM and Version Range Reference Table

Assuming the version in the table is the **JVM running the application**, not the JVM used to compile:

| Running JVM | `≥ 17` (default `SEVENTEEN`) | `≥ 21` (default `TWENTY_ONE`) | `< 21` (`OLDER_THAN TWENTY_ONE`) | `< 23` (`OLDER_THAN TWENTY_THREE`) |
| --- | :---: | :---: | :---: | :---: |
| Java 17 | Match | No | Match | Match |
| Java 18 | Match | No | Match | Match |
| Java 19 | Match | No | Match | Match |
| Java 20 | Match | No | Match | Match |
| Java 21 | Match | Match | No | Match |
| Java 22 | Match | Match | No | Match |
| Java 23 | Match | Match | No | No |

In Spring Boot 3.3, `JavaVersion` defines the constants `SEVENTEEN`, `EIGHTEEN`, `NINETEEN`, `TWENTY`, `TWENTY_ONE`, `TWENTY_TWO`, and `TWENTY_THREE`. Available enum constants depend on the **Spring Boot library** version, not on whether the developer's machine has that JDK installed.

When saying “accepts Java 17 through Java 20”, write the inequality clearly: **17 ≤ Java < 21**. In a Spring Boot 3.3 application, anything below Java 17 is already excluded by the framework, so a single `OLDER_THAN(TWENTY_ONE)` condition suffices to isolate the **17–20** branch. However, the annotation itself only expresses **Java < 21**; the **Java ≥ 17** constraint comes from Spring Boot 3.3's runtime requirement, not from a second attribute on the annotation.

## 4. One-Sided Ranges vs. Bounded Two-Sided Ranges

### 4.1. Lower bound: Java 21 and newer

~~~java
@Bean
@ConditionalOnJava(JavaVersion.TWENTY_ONE)
RuntimeAdapter modernAdapter() {
    return new ModernAdapter();
}
~~~

On Java 21, Java 22, Java 23: this bean can be registered. On Java 17–20: not registered. The `RuntimeAdapter`/`ModernAdapter` types in the snippet must be defined by the project.

### 4.2. Upper bound: before Java 21

~~~java
@Bean
@ConditionalOnJava(
    value = JavaVersion.TWENTY_ONE,
    range = ConditionalOnJava.Range.OLDER_THAN
)
RuntimeAdapter legacyAdapter() {
    return new LegacyAdapter();
}
~~~

On Java 17–20: the bean can be registered. On Java 21 and newer: not registered.

You can use this opposing pair of conditions to register **one of the two** adapters depending on the runtime JVM, provided both branches are defined, implemented, and packaged compatibly with the JVMs they must run on.

### 4.3. Two-sided range, e.g. `21 ≤ Java < 23`

There are **no** `min`, `max`, `between`, or `EQUAL` attributes in Spring Boot 3.3's `@ConditionalOnJava`. Each annotation usage describes only **one threshold** with one `range`; the annotation is not declared repeatable so you cannot place it twice directly on the same element to combine with AND.

When you genuinely need the range **21 ≤ Java < 23** (only Java 21 and 22), a clean solution is writing a custom `Condition` using the Java runtime version API:

File `src/main/java/com/example/demo/Java21To22Condition.java`:

~~~java
package com.example.demo;

import org.springframework.context.annotation.Condition;
import org.springframework.context.annotation.ConditionContext;
import org.springframework.core.type.AnnotatedTypeMetadata;

public final class Java21To22Condition implements Condition {

    @Override
    public boolean matches(
            ConditionContext context,
            AnnotatedTypeMetadata metadata
    ) {
        int feature = Runtime.version().feature();
        return feature >= 21 && feature < 23;
    }
}
~~~

Then place it on a configuration class or bean method:

~~~java
@Conditional(Java21To22Condition.class)
@Bean
AdvancedAdapter advancedAdapter() {
    return new AdvancedAdapter();
}
~~~

The snippet using `AdvancedAdapter` is an **integration illustration** since the business class must be defined by the project. The `Java21To22Condition` class above is a complete Java class; it requires Spring Context on the compile classpath. `Runtime.version().feature()` is an API from Java 9, suitable for Spring Boot 3.3's Java 17 baseline.

The custom condition returns `true` for runtime 21 or 22, and `false` for 17–20, 23 and newer. When another range is needed, use an inequality with controlled bounds and test boundary values.

**Do not** try to place two `@ConditionalOnJava` annotations on the same method/class as two identical annotations; this API version does not support that declaration style.

## 5. Class-Level vs. Method-Level: Scope of Impact

An annotation on a `@Bean` method conditions **only that method's bean definition**:

~~~java
@AutoConfiguration
class JvmAdaptersAutoConfiguration {

    @Bean
    @ConditionalOnJava(JavaVersion.TWENTY_ONE)
    RuntimeMarker modernMarker() {
        return new RuntimeMarker("modern");
    }

    @Bean
    @ConditionalOnJava(
        value = JavaVersion.TWENTY_ONE,
        range = ConditionalOnJava.Range.OLDER_THAN
    )
    RuntimeMarker legacyMarker() {
        return new RuntimeMarker("legacy");
    }
}
~~~

This snippet illustrates two branches; `RuntimeMarker` must be defined. From a bean registration perspective: JVMs before 21 receive `legacyMarker`; JVMs 21 and newer receive `modernMarker`.

An annotation at the class level conditions the entire configuration:

~~~java
@AutoConfiguration
@ConditionalOnJava(JavaVersion.TWENTY_ONE)
class ModernOnlyAutoConfiguration {

    @Bean
    RuntimeMarker modernMarker() {
        return new RuntimeMarker("modern");
    }
}
~~~

If the JVM is Java 17, Spring skips that configuration, meaning the `modernMarker` bean inside is not registered through this configuration either. The snippets in section 5 only describe how to organize code; a test example with all required classes is in section 6.

The condition is evaluated when Spring **processes configurations and registers beans**. It does not monitor the running JVM over time to change beans after the context has started. A single JVM cannot switch itself from Java 17 to Java 21 mid-lifecycle in the same process; changing the JDK and restarting the application is required for the condition to be re-evaluated against the new runtime.

## 6. Java 17+ Example Testable with `ApplicationContextRunner`

The following example directly tests the branch matching the JVM running the test. In a Spring Boot 3.3 project with `spring-boot-starter-test`, create the file:

`src/test/java/com/example/demo/ConditionalOnJavaTest.java`

~~~java
package com.example.demo;

import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.autoconfigure.condition.ConditionalOnJava;
import org.springframework.boot.autoconfigure.condition.ConditionalOnJava.Range;
import org.springframework.boot.system.JavaVersion;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;

import static org.assertj.core.api.Assertions.assertThat;

class ConditionalOnJavaTest {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withConfiguration(
                            AutoConfigurations.of(JvmAutoConfiguration.class));

    @AutoConfiguration
    static class JvmAutoConfiguration {

        @Bean("java17OrNewer")
        @ConditionalOnJava(JavaVersion.SEVENTEEN)
        String java17OrNewer() {
            return "supported";
        }

        @Bean("beforeJava21")
        @ConditionalOnJava(
                value = JavaVersion.TWENTY_ONE,
                range = Range.OLDER_THAN
        )
        String beforeJava21() {
            return "legacy";
        }

        @Bean("fromJava21")
        @ConditionalOnJava(JavaVersion.TWENTY_ONE)
        String fromJava21() {
            return "modern";
        }
    }

    @AutoConfiguration
    @ConditionalOnJava(JavaVersion.TWENTY_ONE)
    static class Java21Configuration {

        @Bean("classLevelBean")
        String classLevelBean() {
            return "java21-plus";
        }
    }

    @Test
    void methodLevelConditionsMatchActualRuntime() {
        boolean atLeast21 = Runtime.version().feature() >= 21;

        runner.run(context -> {
            assertThat(context.containsBean("java17OrNewer")).isTrue();
            assertThat(context.containsBean("beforeJava21"))
                    .isEqualTo(!atLeast21);
            assertThat(context.containsBean("fromJava21"))
                    .isEqualTo(atLeast21);
        });
    }

    @Test
    void classLevelConditionGatesWholeConfiguration() {
        boolean atLeast21 = Runtime.version().feature() >= 21;

        new ApplicationContextRunner()
                .withConfiguration(
                        AutoConfigurations.of(Java21Configuration.class))
                .run(context ->
                        assertThat(context.containsBean("classLevelBean"))
                                .isEqualTo(atLeast21));
    }

    @Test
    void environmentPropertyDoesNotImpersonateJvmVersion() {
        boolean atLeast21 = Runtime.version().feature() >= 21;

        runner.withPropertyValues("java.version=999")
                .run(context -> {
                    assertThat(context.containsBean("beforeJava21"))
                            .isEqualTo(!atLeast21);
                    assertThat(context.containsBean("fromJava21"))
                            .isEqualTo(atLeast21);
                });
    }
}
~~~

Run in a project that has the Spring Boot Gradle plugin, JUnit 5, and `spring-boot-starter-test`:

~~~bash
./gradlew test --tests "com.example.demo.ConditionalOnJavaTest"
~~~

On Windows:

~~~powershell
.\gradlew.bat test --tests "com.example.demo.ConditionalOnJavaTest"
~~~

**Expected result: 3 tests PASS** on both Java 17 and Java 21 when the project is configured to use the right test JDK. The difference is which beans are created:

| JVM executing test | `java17OrNewer` | `beforeJava21` | `fromJava21` | `classLevelBean` in separate context |
| --- | --- | --- | --- | --- |
| Java 17 | Yes | Yes | No | No |
| Java 21 | Yes | No | Yes | Yes |
| Java 22 | Yes | No | Yes | Yes |

The third test deliberately adds `java.version=999` **to the Spring Environment**. This is not a way to change the JVM; the condition still evaluates the real runtime version. This proves you cannot use `withPropertyValues(...)` to simulate Java 21 when the test actually runs on Java 17.

The assertions verify context state and **do not produce fixed stdout**. The example uses simple `String` beans to isolate `@ConditionalOnJava` behavior from business logic.

### Testing boundaries properly

To test both sides of the Java 21 threshold, you must **run the test under two real JVMs**, such as Java 17 and Java 21. `ApplicationContextRunner` has no parameter to switch the Java runtime within the same process. If using a Gradle Java toolchain for the `test` task or a separate IDE/CI test JVM setting, verify the JDK actually launching the tests; the Java running the Gradle daemon is not guaranteed to match the Java running every `Test` task.

A direct runtime check while the application is running:

~~~java
System.out.println(Runtime.version().feature());
~~~

For example, a process actually running on Java 21 will print:

~~~text
21
~~~

Note that this is **runtime-dependent output**, not a fixed result across all environments.

## 7. Distinguishing Runtime JVM, Compile Target, and Compatibility

| Aspect | Example | Does `@ConditionalOnJava` check it directly? |
| --- | --- | --- |
| Java running the application or tests | Spring Boot process actually running on JDK 21 | **Yes.** |
| Java used to compile source | `javac` from JDK 21 | No, unless the runtime itself is also Java 21. |
| Bytecode target | `javac --release 17` | No. You can run bytecode 17 on JVM 21 and the condition still sees runtime 21. |
| Spring property | `app.java-version=21` in `application.yml` | No. |
| Maven/Gradle dependency | Using a library requiring Java 21 | Does not automatically guarantee the library can load on Java 17. |
| Class appearing on classpath | `@ConditionalOnClass` can check it | A separate concern, does not replace the version condition. |

**Very important limitation:** an application compiled completely into Java 21 class files can be rejected by JVM 17 **before** the condition has a chance to exclude the bean. `@ConditionalOnJava` is not a “shield” guaranteeing an older JVM can read newer bytecode or avoid touching a nonexistent API. To support older JVMs, you must ensure the parts that must load have compatible bytecode, choose compatible packaging (such as splitting modules/artifacts per runtime and proper class-loading design), and verify with tests on every supported JVM.

Conversely, if you only use JDK 21 to **build** an application with `--release 17` and then run it with JVM 17, the condition sees **Java 17**. If you run that exact same artifact with JVM 21, the condition sees **Java 21**.

## 8. Common Pitfalls and How to Debug

1. **Setting `@ConditionalOnJava(JavaVersion.TWENTY_ONE)` and expecting exactly Java 21.** Default is **≥ 21**; Java 22 or 23 also match. If an exact narrow range is required, use a condition with both bounds and test the boundaries.
2. **Confusing `OLDER_THAN` with `≤`.** `OLDER_THAN(TWENTY_ONE)` excludes Java 21; it only accepts values strictly below 21.
3. **Leaving `value` blank.** The `value` attribute is required; unlike some other condition annotations, there is no default JVM threshold.
4. **Using `application.properties` to “change the Java version”.** `@ConditionalOnJava` inspects the real JVM. Changing a Spring property does not replace running with a different JDK.
5. **Confusing the JDK of the IDE, Gradle, and container app.** If the machine has JDK 21 while the Docker container runs JRE 17, the condition sees Java 17; check `java -version` *inside* the container and `Runtime.version().feature()` of that exact process.
6. **Assuming Java-21-only code can compile/run on Java 17.** Newer source/APIs or a higher bytecode target can still prevent the application from starting; compatibility must be designed from build, packaging, and class loading.
7. **Choosing constants outside the `JavaVersion` enum defined by the Spring Boot library in use.** Do not assume `TWENTY_FOUR` or `TWENTY_FIVE` exists in Spring Boot 3.3; check the Javadoc of the Spring Boot version you are using before typing the enum name.
8. **Confusing a registration condition with “runtime is ready”.** A condition only decides whether to place a bean/configuration into the context. It does not verify that a library works properly, a service is connected, or a feature is enabled by business properties.
9. **Using a JVM condition instead of a classpath check.** If a feature also needs an optional library, consider `@ConditionalOnClass` or an appropriate configuration split; a sufficiently new JVM does not guarantee the dependency exists.

When a bean is unexpectedly skipped, enable `--debug` or `debug=true` in Spring Boot to view the Condition Evaluation Report; look for the auto-configuration, the Java condition, and the match/did-not-match reason. You can inspect the report via Actuator `/actuator/conditions` if the endpoint is enabled/exposed per project configuration. Cross-check against the actual running version, then add tests for boundary thresholds.

## 9. Knowledge Self-Check

1. The JVM is Java 21; does `@ConditionalOnJava(JavaVersion.TWENTY_ONE)` match? **Yes**, because the lower bound includes Java 21 itself.
2. The JVM is Java 21; does `@ConditionalOnJava(value = JavaVersion.TWENTY_ONE, range = Range.OLDER_THAN)` match? **No**, because the upper bound excludes the threshold 21 itself.
3. The JVM is Java 20; does `@ConditionalOnJava(JavaVersion.TWENTY_ONE)` match? **No**.
4. The application is compiled with JDK 21 using `--release 17` but run with JRE 17; which version does the condition observe? **17**.
5. Using `@ConditionalOnJava` alone, can you express `21 ≤ JVM < 23` exactly? **No**; one annotation has one single-sided threshold. You must build an appropriate range condition.
6. A Spring Boot 3.3 module requires “Java 17 up to before 21”. Why can `OLDER_THAN(TWENTY_ONE)` suffice in this environment? Because **Spring Boot 3.3 already has a Java 17 minimum requirement**, and the annotation adds the **Java < 21** condition.

## Official Documentation

- [Spring Boot 3.3 — `@ConditionalOnJava` JavaDoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnJava.html): required `value`, default `range`, and lower-inclusive/upper-exclusive semantics.
- [Spring Boot 3.3 — `ConditionalOnJava.Range` JavaDoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnJava.Range.html): `EQUAL_OR_NEWER` and `OLDER_THAN`.
- [Spring Boot 3.3 — `JavaVersion` JavaDoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/system/JavaVersion.html): enum thresholds and runtime version API.
- [Spring Boot 3.3 — Testing Auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html): `ApplicationContextRunner` and condition verification guidance.
