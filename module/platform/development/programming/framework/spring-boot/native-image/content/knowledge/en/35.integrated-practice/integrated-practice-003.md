# Reproducing a Reflection Error and Adding Minimal RuntimeHints

## 1. Practice Objectives

In this practice, you will create a Spring Boot scenario that works properly on the JVM but fails when running as a GraalVM Native Image. The root cause is that the application instantiates an object through reflection: the class name and constructor are only accessed at runtime, so reachability analysis cannot always infer which metadata to retain.

After reproducing the error, you will use Spring AOT RuntimeHints to register the exact constructor invoked. The goal is to understand the evidence-based investigation and remediation workflow:

1. Create a reproducible reflection code path.
2. Run the same test on the JVM to confirm expected behavior.
3. Build and run the native executable to observe the failure.
4. Read the exception and identify the class/member missing metadata.
5. Add RuntimeHints with minimal scope.
6. Verify the hints and re-run the native test.
7. Confirm that other functionality continues to work.

The example uses Java reflection to illustrate the mechanism clearly. In real applications, prefer mechanisms where Spring/the framework or library already provides hints before writing a custom registrar.

## 2. Context: Creating a Plugin by Class Name

Suppose a service has a data converter selected via configuration. The application receives the class name from configuration and creates an instance using reflection.

Create the interface:

```java
package com.example.demo.plugin;

public interface PayloadFormatter {
    String format(String value);
}
```

Create an implementation with a no-arg constructor:

```java
package com.example.demo.plugin;

public class UppercaseFormatter implements PayloadFormatter {

    public UppercaseFormatter() {
    }

    @Override
    public String format(String value) {
        return value.toUpperCase();
    }
}
```

Create a factory that invokes reflection:

```java
package com.example.demo.plugin;

public class FormatterFactory {

    public PayloadFormatter create(String className) {
        try {
            Class<?> type = Class.forName(className);
            Object instance = type.getDeclaredConstructor().newInstance();
            return (PayloadFormatter) instance;
        } catch (ReflectiveOperationException ex) {
            throw new IllegalStateException(
                "Cannot create formatter: " + className, ex
            );
        }
    }
}
```

The class name is just an example. In production systems, do not accept arbitrary class names from external requests because that can introduce security risks. Use an allowlist or a controlled registry.

## 3. Wire the Factory into Spring Boot

Create a service that uses the factory:

```java
package com.example.demo;

import com.example.demo.plugin.FormatterFactory;
import com.example.demo.plugin.PayloadFormatter;
import org.springframework.stereotype.Service;

@Service
public class FormattingService {

    private final FormatterFactory factory;

    public FormattingService() {
        this.factory = new FormatterFactory();
    }

    public String format(String className, String value) {
        PayloadFormatter formatter = factory.create(className);
        return formatter.format(value);
    }
}
```

Create an endpoint to test the behavior over HTTP:

```java
package com.example.demo;

import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/format")
public class FormattingController {

    private final FormattingService service;

    public FormattingController(FormattingService service) {
        this.service = service;
    }

    @GetMapping
    public String format(
            @RequestParam String formatter,
            @RequestParam String value) {
        return service.format(formatter, value);
    }
}
```

Example request:

```http
GET /format?formatter=com.example.demo.plugin.UppercaseFormatter&value=hello
```

The expected result is the string `HELLO`.

## 4. Write a Test Confirming Behavior on the JVM

Test the factory or service before building native:

```java
package com.example.demo;

import com.example.demo.plugin.UppercaseFormatter;
import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;

class FormattingServiceTest {

    private final FormattingService service = new FormattingService();

    @Test
    void createsFormatterThroughReflection() {
        String result = service.format(
            UppercaseFormatter.class.getName(),
            "hello"
        );

        assertThat(result).isEqualTo("HELLO");
    }
}
```

Run the test using your project's build tool, for example Gradle:

```bash
./gradlew test
```

Or Maven:

```bash
./mvnw test
```

This test proves the code path works on the JVM. It does not prove that Native Image has sufficient reflection metadata.

## 5. Build and Reproduce the Error on Native Image

Build the native executable using the project's configuration. For example, with the Spring Boot Gradle plugin with native support:

```bash
./gradlew clean nativeCompile
```

With Maven, use the goal/package configuration corresponding to the project's Spring Boot Maven Plugin and Native Build Tools. Goal names and how the native profile is enabled depend on the version; verify the actual task/goal rather than mechanically applying a single command to every project.

Run the generated executable:

```bash
./build/native/nativeCompile/api-app
```

Then call the endpoint:

```bash
curl "http://localhost:8080/format?formatter=com.example.demo.plugin.UppercaseFormatter&value=hello"
```

If the native build lacks metadata for the dynamically invoked class/constructor, the runtime may report errors related to reflection, constructors, or class reachability. The exact exception depends on the GraalVM version and build configuration. Save the full stack trace, not just the last line.

Some Native Image versions may infer additional metadata from code or dependency metadata. If the example still runs, check the build output and test a dynamically accessed member/class in a way that analysis genuinely cannot infer; do not intentionally add broad hints just to force an artificial error.

## 6. Read the Error and Identify the Actually Missing Metadata

When the native executable fails, record:

- The class passed to Class.forName.
- The constructor or method called via reflection.
- The member's access level.
- The exception type and cause.
- The Native Image/GraalVM version.
- Build arguments and loaded metadata.
- The exact test input reproducing the failure.

Distinguish the following cases:

| Error | Investigation Direction |
|---|---|
| Class not reachable / not found | Is the class on the application runtime classpath and included in the image? |
| Constructor not permitted for reflection | Register the exact constructor/access needed |
| Method/field reflection fails | Identify the specific method/field and access rights |
| ClassCastException | Implementation does not implement the interface or classloader/type mismatch |
| ClassNotFoundException on JVM | Missing dependency/classpath or wrong class name, not merely a missing hint |
| Bean does not exist | Check Spring AOT bean graph/conditions; RuntimeHints do not create beans |

RuntimeHints only describe metadata for runtime operations that need support. They do not add missing dependencies, create Spring beans excluded by conditions, or fix invalid cast logic.

## 7. Register the Constructor Using RuntimeHints

Create a registrar in the application:

```java
package com.example.demo;

import com.example.demo.plugin.UppercaseFormatter;
import org.springframework.aot.hint.MemberCategory;
import org.springframework.aot.hint.RuntimeHints;
import org.springframework.aot.hint.RuntimeHintsRegistrar;

public class FormatterRuntimeHints implements RuntimeHintsRegistrar {

    @Override
    public void registerHints(RuntimeHints hints, ClassLoader classLoader) {
        hints.reflection().registerType(
            UppercaseFormatter.class,
            MemberCategory.INVOKE_DECLARED_CONSTRUCTORS
        );
    }
}
```

Register the registrar using an annotation:

```java
package com.example.demo;

import org.springframework.context.annotation.ImportRuntimeHints;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@ImportRuntimeHints(FormatterRuntimeHints.class)
public class NativeHintsConfiguration {
}
```

The registrar declares the constructor invoked via reflection. It does not expose all methods/fields of the class and does not register every class in the package.

The API may vary by Spring Framework version. Use the exact package and methods of the Spring Boot/Spring Framework version managed by your project.

## 8. Why Must Hints Be Minimal?

An overly broad hint can cause Native Image to retain more metadata or code than necessary. This increases binary size, build time, and the surface area that must be audited.

In this example, the dynamic operation calls a no-arg constructor. Therefore, registering declared constructors is an appropriate illustrative scope. If code only calls a public constructor, consider a narrower category matching the API/version and actual access pattern.

Do not register public methods, fields, or all declared members if no code path requires them. Also do not register an entire package when only one implementation is used.

If the application has multiple valid formatters, register each type in the allowlist or design a static registry so the compiler sees the implementations directly.

## 9. Verify RuntimeHints with RuntimeHintsPredicates

Spring provides test support to verify that a registrar registers the expected metadata. Example:

```java
package com.example.demo;

import com.example.demo.plugin.UppercaseFormatter;
import org.junit.jupiter.api.Test;
import org.springframework.aot.hint.RuntimeHints;
import org.springframework.aot.hint.predicate.RuntimeHintsPredicates;

import static org.assertj.core.api.Assertions.assertThat;

class FormatterRuntimeHintsTest {

    @Test
    void registersConstructorInvocationHint() {
        RuntimeHints hints = new RuntimeHints();
        new FormatterRuntimeHints().registerHints(
            hints,
            getClass().getClassLoader()
        );

        assertThat(
            RuntimeHintsPredicates.reflection()
                .onType(UppercaseFormatter.class)
                .withMemberCategory(
                    MemberCategory.INVOKE_DECLARED_CONSTRUCTORS
                )
                .test(hints)
        ).isTrue();
    }
}
```

Import MemberCategory in the test:

```java
import org.springframework.aot.hint.MemberCategory;
```

Predicate tests confirm that the registrar declares the expected hint. They do not prove every runtime path works; the native executable must still be tested.

## 10. Re-Run AOT and the Native Image Build

After adding the registrar:

1. Run unit tests and the RuntimeHints test.
2. Run Spring AOT processing.
3. Rebuild the native executable from a clean state if needed to eliminate stale output.
4. Confirm the compiler finishes and did not skip the registrar.
5. Run the new executable.
6. Call the exact endpoint/request fixture that previously failed.
7. Run additional tests for other valid formatters.

Gradle example:

```bash
./gradlew clean test nativeCompile
```

Build output paths and tasks depend on the Spring Boot/Native Build Tools configuration. Use the newly produced executable from the exact commit, and do not accidentally run a stale binary.

## 11. Verify via Native Integration Test

If the project supports native test execution, create an integration test that runs the native application or use the plugin's native test task. Another option is launching the executable in CI and calling HTTP endpoints from a test script.

Smoke test example:

```bash
./build/native/nativeCompile/api-app &
APP_PID=$!
trap 'kill "$APP_PID" 2>/dev/null || true' EXIT

for attempt in $(seq 1 30); do
  if curl --fail --silent http://localhost:8080/actuator/health; then
    break
  fi
  sleep 1
done

curl --fail   "http://localhost:8080/format?formatter=com.example.demo.plugin.UppercaseFormatter&value=hello"
```

The example requires an appropriate health endpoint, the right port, and shell/CI-appropriate process cleanup. In a real pipeline, verify readiness status explicitly and fail on timeout; do not let the loop finish and still report pass when the app is not ready.

## 12. Testing Multiple Implementations and Allowlists

If there are two implementations, add the second type:

```java
public class LowercaseFormatter implements PayloadFormatter {
    public LowercaseFormatter() {
    }

    @Override
    public String format(String value) {
        return value.toLowerCase();
    }
}
```

If both are selected by runtime configuration, register constructors for both valid types:

```java
hints.reflection().registerType(
    UppercaseFormatter.class,
    MemberCategory.INVOKE_DECLARED_CONSTRUCTORS
);
hints.reflection().registerType(
    LowercaseFormatter.class,
    MemberCategory.INVOKE_DECLARED_CONSTRUCTORS
);
```

This list should come from trusted configuration or a registry. Do not accept an arbitrary class name from a query parameter or request body for unconstrained instantiation. A registry map from business keys to suppliers is usually safer and easier for reachability analysis than reflection.

## 13. When Should Reflection Be Replaced with a Static Registry?

If the number of implementations is small and known at compile time, a static registry can be simpler:

```java
@Component
public class FormatterRegistry {

    private final Map<String, PayloadFormatter> formatters;

    public FormatterRegistry() {
        this.formatters = Map.of(
            "upper", new UppercaseFormatter(),
            "lower", new LowercaseFormatter()
        );
    }

    public PayloadFormatter get(String name) {
        PayloadFormatter formatter = formatters.get(name);
        if (formatter == null) {
            throw new IllegalArgumentException(
                "Unsupported formatter: " + name
            );
        }
        return formatter;
    }
}
```

A static registry lets the compiler see constructor calls directly and avoids reflection metadata for this code path. However, if the application genuinely requires dynamic plugin discovery, keep reflection and register metadata properly. Choose the architecture based on extensibility, security, and deployment requirements.

## 14. Using the Native Image Tracing Agent When Needed

The tracing agent can observe a JVM run and record a subset of dynamic operations such as reflection, resources, proxies, or serialization. Agent data can help discover missing hints, but only covers code paths executed during the observation run.

General workflow:

1. Run the JVM application with the tracing agent according to your GraalVM version's documentation.
2. Execute representative test scenarios.
3. Collect the generated agent metadata.
4. Review and prune unnecessary metadata.
5. Migrate to metadata/hints mechanisms suitable for Spring and your dependencies.
6. Build native and re-test.

Do not blindly ship agent output to production. The agent can generate excess metadata and miss rarely executed branches.

## 15. Common Errors When Adding RuntimeHints

| Symptom | Cause | Resolution |
|---|---|---|
| Registrar is not applied | Configuration containing the annotation was not discovered | Check component/config import and AOT output |
| Hint exists but native still fails | Registered wrong type/member or stale binary | Read stack trace, clean build, and verify executable |
| Constructor hint is insufficient | Code also calls methods/fields via reflection | Identify actual members and register minimally |
| Class missing from image | Missing dependency or classpath entry | Fix dependency/application module |
| Bean does not exist | Profile/condition excluded the bean during AOT | Fix build-time profile/property |
| Resource not found | Missing resource hint or resource not in artifact | Check resource path/pattern |
| JVM test passes but native fails | Test did not run in native or metadata is missing | Add native regression test |
| Hint is too broad | Registered entire type/package unnecessarily | Narrow type and member categories |

## 16. Extension Exercises

Perform the following exercises on the project:

1. Add a second formatter and register only that implementation's constructor.
2. Try changing the constructor to private; verify the required access category and consider redesigning.
3. Convert class names into registry keys and compare native metadata/build size.
4. Add a method invoked via reflection, reproduce the error, and register only that method.
5. Add a resource template selected by runtime name and register a narrow resource pattern.
6. Run the tracing agent with test scenarios and review the generated metadata.
7. Remove the newly added hint and re-run the native test to verify the test actually catches regressions.
8. Add the native smoke test to CI and archive logs on failure.

For each change, save the request/test fixture, the stack trace before the fix, the RuntimeHints diff, and the result after the fix.

## 17. Practice Completion Checklist

- A class is instantiated via reflection in a clear code path.
- JVM tests confirm the expected behavior.
- The native executable is built and tested to reproduce the failure.
- The exception is analyzed down to the specific class/member.
- Dependencies/classpath are checked and distinguished from bean graph issues.
- `RuntimeHintsRegistrar` registers the exact minimal type/member.
- The registrar is imported/registered into the Spring AOT context.
- The RuntimeHints predicate test passes.
- The new Native Image build completes.
- Native regression/smoke tests pass against the original fixture.
- Reflection is not registered more broadly than needed.
- Implementation selection input is constrained by an allowlist/registry.
- Logs and artifact identity are archived for build reproducibility.

## 18. Self-Check Questions

1. Why can code using Class.forName run on the JVM yet fail in Native Image?
2. How does reachability analysis relate to reflection metadata?
3. What is `RuntimeHintsRegistrar` used to declare?
4. Why does registering a constructor not imply registering all methods and fields?
5. What do `RuntimeHintsPredicates` verify and what do they not prove?
6. How do you distinguish a missing reflection hint from a missing dependency or bean?
7. When is a static registry more appropriate than reflection?
8. Why cannot the tracing agent guarantee coverage of all branches?
9. After fixing hints, why are a clean native build and testing the exact new executable required?
10. Why should arbitrary class names not be accepted from a request to instantiate objects?

**Remember:** reproduce the error with a specific test, identify the exact dynamically accessed class/member, and register the narrowest RuntimeHints that satisfy the code path. Verify the registrar, rebuild the native executable, and run regression tests on the exact new binary before accepting the change.
