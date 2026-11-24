# Choosing value or name When Referencing Optional Classes — @ConditionalOnClass in Spring Boot

> **Module:** Spring Boot — auto-configuration. **Group:** Classpath conditions. **Objective:** Know when to write `@ConditionalOnClass(value = SomeClient.class)` and when to write `@ConditionalOnClass(name = "com.vendor.SomeClient")`; understand why referencing `Class<?>` is sometimes safe even when the dependency is absent at runtime, which cases require using a string name, and how to isolate `@Bean` methods whose signatures contain optional types. Examples use Java 17, Maven, and Spring Boot 3.5.7.

## 1. Key Takeaways

`@ConditionalOnClass` is a Spring Boot condition that checks **whether the specified class is present on the classpath/class loader in use** before applying a piece of configuration.

It has two important attributes:

```java
Class<?>[] value() default {};
String[] name() default {};
```

These are two abbreviated **annotation attribute signatures**, not a standalone Java file.

- `value` accepts `Class<?>` literals: e.g. `@ConditionalOnClass(value = VendorClient.class)`, or shorthand `@ConditionalOnClass(VendorClient.class)`.
- `name` accepts strings of **fully-qualified class names**: e.g. `@ConditionalOnClass(name = "dev.lesson.vendor.VendorClient")`.
- When specifying multiple classes in `value`, multiple names in `name`, or both, the condition requires **all** requested classes to be present. It does not treat elements as OR.
- Both are used to **check class existence**, not to check for a bean, not to automatically create an instance, and not to guarantee that the SDK can connect to an external service.
- This condition can appear on a configuration class or an `@Bean` method, but the safety level for **optional classes absent at runtime** differs; you cannot rely solely on `value` vs. `name` syntax to solve every linkage error.

**Quick selection rules:**

1. **Used directly on a configuration class**, where the type is present at compile time but may be absent at runtime: `value = SomeClient.class` is fine; Spring Boot reads annotation metadata via ASM before having to load the configuration class.
2. **Cannot or do not want a compile-time dependency on that type**: use `name = "package.SomeClient"`.
3. **Writing a custom composed/meta-annotation** containing `@ConditionalOnClass`: **must use `name`** instead of `value`, per Spring Boot's documentation and Javadoc.
4. **`@Bean` method returning or accepting parameters of an optional SDK type**: place the method inside a **nested `@Configuration(proxyBeanMethods = false)`** annotated with the condition at the **class level**. Switching `value` to `name` directly on the method **is not** a complete cure for the risk of the JVM resolving the signature too early.

## 2. Classpath Checking Mechanism and Why value Is Sometimes Safe

Direct class example:

```java
@AutoConfiguration
@ConditionalOnClass(VendorClient.class)
public class VendorAutoConfiguration {
    // Specific @Bean methods will be placed in a separate configuration when needed.
}
```

This is an **illustrative snippet missing imports and resource files**. At compile time, the Java compiler must find `VendorClient` to emit bytecode containing the annotation. However, the runtime of an application using this library might **not have** the JAR defining `VendorClient`.

Spring Boot reads configuration class metadata using ASM. When `@ConditionalOnClass` is placed **directly on that class**, Boot can see the class name represented in bytecode without forcing the JVM to resolve `VendorClient.class` the way application code directly referencing a class literal would. Thus `value` **is a supported choice** in this position, even when the dependency only appears when building the library.

That does not make arbitrary code referencing `VendorClient` safe. For example:

```java
public final class VendorConnector {
    private final VendorClient client;

    public VendorConnector(VendorClient client) {
        this.client = client;
    }
}
```

If a code path must load or introspect `VendorConnector` while `VendorClient` is absent, resolving the reference can trigger `NoClassDefFoundError` or a linkage error. Spring Boot only promises the safe mechanism **when directly reading annotation metadata in supported situations**, not excluding every class load performed by the JVM.

### When does value work well?

- The class is available on the compile classpath of the **auto-configuration module**.
- Spring Boot reads the condition directly on a **configuration class**.
- APIs that may be absent are isolated in child configuration classes, untouched by other code before condition filtering.
- You want IDE/refactoring support to catch class renames and the compiler to check names/types at build time.

### When does name work well?

- You only have the **fully-qualified name** of the integration class and do not want to pull the SDK onto the compile classpath.
- You want to keep the auto-config module free of a direct dependency on the JAR containing the target type just to check presence.
- Writing a **composed annotation**, because Spring Boot's rule requires a string name.
- You want to check the presence of a class from an optional module without creating a Java import or literal type reference in the annotation source.

Remember: using `name` in a condition **is not enough to compile code that actually calls SDK constructors/methods**. If a method body or signature mentions the SDK class, the module containing that code still needs the type on its compile classpath or must use appropriate reflection/abstraction.

## 3. Comparing value and name

| Criterion | `value = VendorClient.class` | `name = "dev.lesson.vendor.VendorClient"` |
| --- | --- | --- |
| Declaration form | Class literal | Fully-qualified name string |
| Must SDK be present when compiling the referencing source? | **Yes** | **No**, if that code only contains the condition string |
| IDE package/class refactoring | Usually updated and checked by compiler | Easily becomes a stale string; requires testing |
| Used directly on `@Configuration` class | **Safe via Boot-supported ASM mechanism** | Yes |
| Used inside a custom meta-annotation | **Not recommended; not safely supported like direct annotation** | **Must use `name`** |
| SDK missing at runtime | Condition does not match if metadata is processed via standard path | Condition does not match |
| Prevents `@Bean` signature error mentioning absent SDK | Not guaranteed by itself | Not guaranteed by itself |
| Checks SDK version/API compatibility | No | No |
| Creates bean or instance from SDK | No | No |

### Valid Syntax

```java
@ConditionalOnClass(VendorClient.class)
```

```java
@ConditionalOnClass(value = VendorClient.class)
```

```java
@ConditionalOnClass(name = "dev.lesson.vendor.VendorClient")
```

```java
@ConditionalOnClass(
    value = { VendorClient.class, VendorMetrics.class },
    name = "com.example.optional.HealthApi"
)
```

These are **annotation snippets**, not complete Java classes. In the last example, `VendorClient` and `VendorMetrics` require the compile classpath, and all three classes must exist for the condition to match.

## 4. When name Is Mandatory: Custom Composed Annotations

Suppose we want to standardize an internal annotation:

```java
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@Documented
@ConditionalOnClass(name = "dev.lesson.vendor.VendorClient")
public @interface ConditionalOnVendorClient {
}
```

This is a complete annotation structure, though it needs Java/Spring imports; the project example below provides the full file.

`@ConditionalOnVendorClient` is a **meta-annotation wrapper**: an annotation you define containing `@ConditionalOnClass`, which you then place on a configuration class:

```java
@Configuration(proxyBeanMethods = false)
@ConditionalOnVendorClient
static class VendorMarkerConfiguration {
    // ...
}
```

Spring Boot documentation/Javadoc states clearly that if `@ConditionalOnClass` is used as a **meta-annotation**, the class must be referenced via the `name` attribute. Do not turn the wrapper into:

```java
@ConditionalOnClass(VendorClient.class)
public @interface ConditionalOnVendorClient {
}
```

Although that code may compile when the SDK is available, it **does not have equivalent safety guarantees to a direct class-level annotation** when the SDK is excluded from the runtime classpath.

**Design rationale:** Because composition causes metadata to be read along different paths, the ASM-based handling of `Class<?>` literals for direct annotations cannot be assumed to behave identically. A class name string avoids forcing an optional type to be resolved at the meta-annotation site.

### Testing Rules

- For direct annotations, test both runtimes with and without the SDK.
- For composed annotations, test SDK absence by actually removing the class from the classloader, not merely setting a property to false.
- Try renaming the package or upgrading the SDK to catch whether the `name` string is still accurate.
- If the annotation wrapper is public across multiple modules, document the class name being checked and the refactoring risk.

## 5. Another Issue: @ConditionalOnClass on an @Bean Method

An easily mistaken pattern:

```java
@AutoConfiguration
public class RiskyVendorAutoConfiguration {

    @Bean
    @ConditionalOnClass(name = "dev.lesson.vendor.VendorClient")
    public VendorClient vendorClient() {
        return new VendorClient();
    }
}
```

This is a **risk-analysis fragment**, not a recommended configuration to run. The danger lies not in the string name, but in the **return type `VendorClient`** in the method signature of a class being processed by Spring. When Spring/the JVM must load or introspect the enclosing class to create bean definitions, `VendorClient` may be resolved **before the method condition can protect it**.

The durable approach is to isolate it:

```java
@AutoConfiguration
public class VendorAutoConfiguration {

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnClass(name = "dev.lesson.vendor.VendorClient")
    static class VendorPresentConfiguration {

        @Bean
        VendorClient vendorClient() {
            return new VendorClient();
        }
    }
}
```

This is also just a fragment because it lacks imports and the SDK class. Still, the key structure is:

1. The outer auto-configuration can be discovered and have its metadata read even when the SDK is missing.
2. The nested configuration is **filtered at the class level** before Spring needs to process methods with SDK signatures.
3. Only when the SDK exists are the `@Bean` methods in the nested configuration processed to create beans.
4. `proxyBeanMethods=false` is a common choice to avoid proxy interception between bean methods.

In a direct nested class condition, you can use `value = VendorClient.class` if the module compiles with the SDK, or `name="..."` as needed. The runnable example below uses **direct `value`** for one nested configuration and **`name` inside a composed annotation** for another nested configuration, allowing you to observe both forms.

## 6. Runnable Example: Optional SDK Present or Excluded from Runtime

We will use a three-module Maven reactor:

- `vendor-sdk`: small JAR containing `VendorClient` as a simulated SDK.
- `sample-autoconfigure`: JAR containing auto-configuration, with a compile dependency on `vendor-sdk` **marked `optional=true`**. Because it is optional, the dependency **does not transitively propagate** to the application module.
- `app`: Spring Boot application depending on `sample-autoconfigure`. By default it **does not pull `vendor-sdk`** into runtime. Only the Maven `with-sdk` profile adds `vendor-sdk` directly to `app`.

This lets us build the **same source** and run two different outcomes: SDK absent and SDK present.

### 6.1. Directory Structure

```text
optional-class-demo/
├── pom.xml
├── vendor-sdk/
│   ├── pom.xml
│   └── src/main/java/dev/lesson/vendor/
│       └── VendorClient.java
├── sample-autoconfigure/
│   ├── pom.xml
│   └── src/
│       ├── main/
│       │   ├── java/dev/lesson/autoconfig/
│       │   │   ├── FeaturePort.java
│       │   │   ├── ConditionalOnVendorClient.java
│       │   │   └── VendorAutoConfiguration.java
│       │   └── resources/META-INF/spring/
│       │       └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
│       └── test/java/dev/lesson/autoconfig/
│           └── VendorAutoConfigurationTest.java
└── app/
    ├── pom.xml
    └── src/main/java/dev/lesson/app/
        └── DemoApplication.java
```

The application is in `dev.lesson.app`, while auto-configuration is in `dev.lesson.autoconfig`, so the application's default component scan **does not scan** the auto-configuration class. Its activation depends on the imports file.

### 6.2. Parent POM

File `optional-class-demo/pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.7</version>
        <relativePath/>
    </parent>
    <groupId>dev.lesson</groupId>
    <artifactId>optional-class-demo</artifactId>
    <version>1.0.0</version>
    <packaging>pom</packaging>
    <modules>
        <module>vendor-sdk</module>
        <module>sample-autoconfigure</module>
        <module>app</module>
    </modules>
    <properties>
        <java.version>17</java.version>
    </properties>
</project>
```

### 6.3. Module vendor-sdk

`vendor-sdk/pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>dev.lesson</groupId>
        <artifactId>optional-class-demo</artifactId>
        <version>1.0.0</version>
        <relativePath>../pom.xml</relativePath>
    </parent>
    <artifactId>vendor-sdk</artifactId>
</project>
```

`vendor-sdk/src/main/java/dev/lesson/vendor/VendorClient.java`:

```java
package dev.lesson.vendor;

public final class VendorClient {
    public String version() {
        return "vendor-1";
    }
}
```

This is a mock SDK, requiring no internet connection or external system.

### 6.4. Module sample-autoconfigure and Optional Dependency

`sample-autoconfigure/pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>dev.lesson</groupId>
        <artifactId>optional-class-demo</artifactId>
        <version>1.0.0</version>
        <relativePath>../pom.xml</relativePath>
    </parent>
    <artifactId>sample-autoconfigure</artifactId>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-autoconfigure</artifactId>
        </dependency>
        <dependency>
            <groupId>dev.lesson</groupId>
            <artifactId>vendor-sdk</artifactId>
            <version>1.0.0</version>
            <optional>true</optional>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
</project>
```

Note: `optional=true` does not remove the dependency from the compile/runtime classpath **of the `sample-autoconfigure` module itself**. It controls **transitivity to other modules** that depend on `sample-autoconfigure`. Therefore tests written in the auto-configuration module have the SDK by default, yet an app depending on the auto-configuration can still run without the SDK.

### 6.5. Public Contract Independent of the SDK

`sample-autoconfigure/src/main/java/dev/lesson/autoconfig/FeaturePort.java`:

```java
package dev.lesson.autoconfig;

@FunctionalInterface
public interface FeaturePort {
    String message();
}
```

This interface resides in the auto-config JAR so the app can use it without directly importing optional SDK classes.

### 6.6. Composed Annotation Requiring name

`sample-autoconfigure/src/main/java/dev/lesson/autoconfig/ConditionalOnVendorClient.java`:

```java
package dev.lesson.autoconfig;

import java.lang.annotation.Documented;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;

@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@Documented
@ConditionalOnClass(name = "dev.lesson.vendor.VendorClient")
public @interface ConditionalOnVendorClient {
}
```

This is a **composed annotation**. If you replace `name` with `value = VendorClient.class` directly in your custom composed annotation declaration, you violate the safety rule Spring Boot specifies for meta-annotations. Because the class name is a string, keep tests to catch wrong names after refactoring.

### 6.7. Auto-Configuration with Direct value, Indirect name, and Fallback

`sample-autoconfigure/src/main/java/dev/lesson/autoconfig/VendorAutoConfiguration.java`:

```java
package dev.lesson.autoconfig;

import dev.lesson.vendor.VendorClient;

import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingClass;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@AutoConfiguration
public class VendorAutoConfiguration {

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnClass(value = VendorClient.class)
    static class SdkPresentConfiguration {

        @Bean
        @ConditionalOnMissingBean(VendorClient.class)
        public VendorClient vendorClient() {
            return new VendorClient();
        }

        @Bean
        @ConditionalOnMissingBean(FeaturePort.class)
        public FeaturePort sdkFeaturePort(VendorClient client) {
            return () -> "sdk:" + client.version();
        }
    }

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnVendorClient
    static class ComposedAnnotationConfiguration {

        @Bean
        public String vendorMarker() {
            return "sdk-visible";
        }
    }

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnMissingClass("dev.lesson.vendor.VendorClient")
    static class SdkAbsentConfiguration {

        @Bean
        @ConditionalOnMissingBean(FeaturePort.class)
        public FeaturePort fallbackFeaturePort() {
            return () -> "fallback";
        }
    }
}
```

**Reading the design across the three nested classes:**

1. `SdkPresentConfiguration` uses `value = VendorClient.class` **directly at the configuration class level**, the case safely supported by Boot via ASM. Inside, it declares `@Bean` methods with SDK return types/parameters.
2. `ComposedAnnotationConfiguration` applies the custom `@ConditionalOnVendorClient`, which uses **`name`** internally. It only creates the `vendorMarker` bean when the SDK is present.
3. `SdkAbsentConfiguration` uses `@ConditionalOnMissingClass`, which accepts **a string class name**, to provide the fallback when the SDK is absent.

`SdkPresentConfiguration` and `SdkAbsentConfiguration` have opposite classpath conditions, so under normal conditions only one side registers `FeaturePort`. Both still have `@ConditionalOnMissingBean(FeaturePort.class)` to respect an application-provided bean if one exists.

**Why not put `@ConditionalOnClass` on the outer `VendorAutoConfiguration`?** Because the outer class contains **the fallback as well**. If the outer class were only entered when the SDK existed, the fallback could not run when the SDK is absent. The condition is placed precisely on the feature branch depending on the SDK.

**Why can `VendorClient.class` and its import still appear in the outer source?** At compile time, the `vendor-sdk` dependency is present. When the SDK is absent at runtime, the class literal sits on the nested configuration's annotation, while methods using the optional type are isolated inside the nested configuration. This is the Spring Boot recommended pattern for optional dependencies, not a blanket guarantee for arbitrary code referencing the SDK in the outer class.

### 6.8. Auto-Configuration Registration File

Create `sample-autoconfigure/src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`:

```text
dev.lesson.autoconfig.VendorAutoConfiguration
```

The file only lists the **outer auto-configuration class**. Nested configurations are discovered via that class's structure when Spring processes configuration. There is no need to add them as top-level candidates in the imports file.

### 6.9. Module app and Maven Profile to Enable the SDK

`app/pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>dev.lesson</groupId>
        <artifactId>optional-class-demo</artifactId>
        <version>1.0.0</version>
        <relativePath>../pom.xml</relativePath>
    </parent>
    <artifactId>app</artifactId>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>
        <dependency>
            <groupId>dev.lesson</groupId>
            <artifactId>sample-autoconfigure</artifactId>
            <version>1.0.0</version>
        </dependency>
    </dependencies>
    <profiles>
        <profile>
            <id>with-sdk</id>
            <dependencies>
                <dependency>
                    <groupId>dev.lesson</groupId>
                    <artifactId>vendor-sdk</artifactId>
                    <version>1.0.0</version>
                </dependency>
            </dependencies>
        </profile>
    </profiles>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

The profile lives in **app**, so running `-Pwith-sdk` adds `vendor-sdk` as a **direct dependency** of the application. No source code or imports file needs to be modified.

### 6.10. Application Observing the Classpath State

`app/src/main/java/dev/lesson/app/DemoApplication.java`:

```java
package dev.lesson.app;

import dev.lesson.autoconfig.FeaturePort;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;

@SpringBootApplication
public class DemoApplication {

    public static void main(String[] args) {
        try (ConfigurableApplicationContext context =
                 SpringApplication.run(DemoApplication.class, args)) {

            FeaturePort port = context.getBean(FeaturePort.class);

            System.out.println("feature.message=" + port.message());
            System.out.println(
                "vendor.client.bean=" + context.containsBean("vendorClient")
            );
            System.out.println(
                "composed.marker.bean=" + context.containsBean("vendorMarker")
            );
        }
    }
}
```

The application **does not import `VendorClient`**. It only depends on `FeaturePort`, which is always available. This makes sense when the SDK is a genuinely optional integration.

### 6.11. Running When the SDK Is Absent

In the root directory `optional-class-demo/`, requiring Java 17 and Maven:

```bash
mvn -q clean package
java -jar app/target/app-1.0.0.jar
```

When Maven builds with the default profile, `sample-autoconfigure` still compiles with the SDK; however, `app` **does not pull that optional dependency** into its runtime JAR. Ignoring startup logs, the three lines printed by the code are:

```text
feature.message=fallback
vendor.client.bean=false
composed.marker.bean=false
```

Reasons:

- `SdkPresentConfiguration` does not match the direct `value` condition because `VendorClient` is not on the app's runtime classpath.
- `@ConditionalOnVendorClient` does not match because the name `dev.lesson.vendor.VendorClient` cannot be found.
- `@ConditionalOnMissingClass` matches, creating `fallbackFeaturePort`.

This demonstrates that **just because a library has code referencing an SDK at compile time does not mean the application must carry that SDK at runtime**, provided the code is structured and guarded by conditions properly.

### 6.12. Running When the SDK Is Present

Rebuild the same project with the profile enabled:

```bash
mvn -q -Pwith-sdk clean package
java -jar app/target/app-1.0.0.jar
```

Now `app` contains the `vendor-sdk` dependency directly. The three lines printed by the application (ignoring startup logs):

```text
feature.message=sdk:vendor-1
vendor.client.bean=true
composed.marker.bean=true
```

At this point, both the condition using direct `value` and the `name` condition inside the composed annotation match. The fallback branch is excluded because `@ConditionalOnMissingClass` no longer matches.

**Note when running the two variants back-to-back:** `clean package` must be executed again when switching profiles; otherwise you might run an executable JAR packaged under the previous profile. Both outputs are the expected results when dependencies match the example structure, excluding Spring Boot logs.

## 7. Testing Two Classpaths with FilteredClassLoader

Because the auto-config project has the SDK on its compile/test classpath, we use `FilteredClassLoader` to simulate the SDK not being visible in a context. This approach fits when the test classpath needs the SDK to compile the code, yet production consumers might not carry the SDK.

File `sample-autoconfigure/src/test/java/dev/lesson/autoconfig/VendorAutoConfigurationTest.java`:

```java
package dev.lesson.autoconfig;

import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.test.context.FilteredClassLoader;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

class VendorAutoConfigurationTest {

    private final ApplicationContextRunner runner =
        new ApplicationContextRunner().withConfiguration(
            AutoConfigurations.of(VendorAutoConfiguration.class)
        );

    @Test
    void sdkPresentAllowsDirectValueAndComposedName() {
        runner.run(context -> {
            assertThat(context).hasSingleBean(FeaturePort.class);
            assertThat(context.getBean(FeaturePort.class).message())
                .isEqualTo("sdk:vendor-1");
            assertThat(context).hasBean("vendorClient");
            assertThat(context).hasBean("vendorMarker");
            assertThat(context).doesNotHaveBean("fallbackFeaturePort");
        });
    }

    @Test
    void sdkAbsentAllowsFallbackWithoutLinkageError() {
        runner.withClassLoader(
            new FilteredClassLoader("dev.lesson.vendor")
        ).run(context -> {
            assertThat(context).hasSingleBean(FeaturePort.class);
            assertThat(context.getBean(FeaturePort.class).message())
                .isEqualTo("fallback");
            assertThat(context).doesNotHaveBean("vendorClient");
            assertThat(context).doesNotHaveBean("vendorMarker");
        });
    }

    @Test
    void userPortMakesSdkDefaultBackOff() {
        runner.withUserConfiguration(UserPortConfiguration.class)
            .run(context -> {
                assertThat(context).hasSingleBean(FeaturePort.class);
                assertThat(context.getBean(FeaturePort.class).message())
                    .isEqualTo("from-user");
                assertThat(context).doesNotHaveBean("sdkFeaturePort");
                assertThat(context).hasBean("vendorMarker");
            });
    }

    @Configuration(proxyBeanMethods = false)
    static class UserPortConfiguration {
        @Bean
        FeaturePort userFeaturePort() {
            return () -> "from-user";
        }
    }
}
```

Run from root:

```bash
mvn -q test
```

Expect **3 passing tests** in the `sample-autoconfigure` module when using the sources above:

1. SDK present: both direct `value` and composed `name` match.
2. SDK hidden: fallback is created, SDK-using classes are excluded before causing linkage errors.
3. User already provided `FeaturePort`: auto-configuration backs off for the default interface bean.

**Limitation of this test:** `FilteredClassLoader` tests classloader visibility; it does not completely replace verifying a production executable JAR. Hence, the two `java -jar` commands in section 6 remain valuable as real packaging smoke tests.

The test class is in `dev.lesson.autoconfig` whereas the application's main class is in `dev.lesson.app`, so `UserPortConfiguration` nested inside the test class is not picked up by the demo app's default component scan. The runner also only passes that configuration in the third test.

## 8. Should You Use name for Every Potentially Absent Class?

**No.** This is a common misconception.

Spring Boot intentionally supports `@ConditionalOnClass(value = OptionalSdk.class)` when the annotation is placed **directly** on a configuration class and metadata is read via ASM. Converting every `value` to `name` can sacrifice the compiler/IDE's ability to catch renames without delivering any corresponding safety benefit in already-supported cases.

However, three situations call for using `name`:

- **Meta-annotations:** explicit rule—use `name`.
- **No SDK in compile dependencies:** referencing only the string name does not require the Java compiler to know that class.
- **Wanting to reduce coupling in metadata:** avoiding literal type references on the class needing the condition; tests will guard the string.

Conversely, if a method body **actually** writes `new OptionalSdk()`, a string `name` does not allow the module to compile without the SDK. Do not conflate “reducing compile-time dependency for the condition” with “reducing compile-time dependency for all code”.

## 9. Avoiding NoClassDefFoundError and Unintended Linkage

### 9.1. Conditions Do Not Guard Every Code Path

Risky example:

```java
@AutoConfiguration
@ConditionalOnClass(name = "com.vendor.Client")
public class RiskyAutoConfiguration {

    private final com.vendor.Client eagerClient =
        new com.vendor.Client();
}
```

**This is an illustration, not meant to be run.** The condition can cause the configuration class to be skipped along the standard auto-configuration path, yet **another place** could still directly instantiate/load `RiskyAutoConfiguration`. Using conditions does not replace designing proper isolation for optional dependencies.

The durable pattern is usually an outer config that does not mention the SDK in method signatures or fields, and nested configs with class-level conditions containing all `@Bean` methods that use the SDK.

### 9.2. @ConditionalOnClass Only Checks Presence, Not API Compatibility

When `VendorClient.class` is on the classpath, the condition matches. However:

- API methods may have been removed or changed across SDK versions.
- A transitive dependency needed by the SDK at initialization might be missing.
- Drivers/native libraries, credentials, or external services might be unavailable.
- The class may exist yet be incompatible with the current JVM/platform.

Therefore do not infer from `@ConditionalOnClass` that the integration is guaranteed to run successfully. For complex optional APIs/versions, you need explicit dependency management, compatibility tests, and proper fail-fast/diagnostic strategies. Avoid catching broad `NoClassDefFoundError` and silently continuing in a broken state.

### 9.3. Hidden Type References in Other Annotations

Even when the outer auto-configuration only uses `name`, an unguarded `@Import(SomeSdkConfiguration.class)` or a class signature referencing the SDK can force Spring/the JVM to load missing classes. Examine the **entire dependency graph of the configuration**, not just a single condition line.

### 9.4. Optional SDKs in Maven

Maven's `optional=true` on an auto-config module's dependency means that dependency does not transitively propagate to consumers, not that it is excluded from compiling the producer module. A comparable goal in Gradle can use `compileOnly` with appropriate runtime dependency arrangement, though Gradle's syntax/variant resolution differs from Maven; do not assume both packaging systems behave identically.

## 10. Confusions Around value/name to Avoid

`@ConditionalOnClass` is not the only annotation with attributes of those names.

| Annotation | `value` | `name` | Question it answers |
| --- | --- | --- | --- |
| `@ConditionalOnClass` | `Class<?>[]` | `String[]` | Are the required **classes** present? |
| `@ConditionalOnMissingClass` | No class literal `value` | `String[] value` | Are the specified classes **absent**? |
| `@ConditionalOnBean` | Bean type (class literal) | Bean **name** | Is a matching bean known at evaluation time? |
| `@ConditionalOnMissingBean` | Bean type (class literal) | Bean **name** | Is a matching bean missing at evaluation time? |
| `@ConditionalOnProperty` | Alias for `name` property | Property name | Does the Environment have the right key/value? |

**Important:** `name` on `@ConditionalOnClass` means the **fully-qualified Java class name**; `name` on `@ConditionalOnBean` means the **Spring bean name**; and `name` on `@ConditionalOnProperty` means the **configuration property name**. Same attribute name `name`, different meaning depending on the annotation.

`@ConditionalOnMissingClass` in Spring Boot 3.5 uses class name strings in `value` (e.g. `@ConditionalOnMissingClass("dev.lesson.vendor.VendorClient")`), not `value = VendorClient.class`. This condition is designed to express class absence without requiring a compile-time type reference.

## 11. Using value/name with Multiple Optional SDKs and AND/OR Logic

### 11.1. AND: All Classes Must Be Present

```java
@Configuration(proxyBeanMethods = false)
@ConditionalOnClass(name = {
    "com.vendor.Client",
    "com.vendor.Metrics"
})
class ClientMetricsConfiguration {
}
```

The class is only applied when **both** types can be found by the classloader. If only `Client` is present and `Metrics` is missing, the condition does not match.

Equivalent form when a compile dependency exists:

```java
@ConditionalOnClass(value = {
    Client.class,
    Metrics.class
})
```

This is a **fragment**, without imports.

### 11.2. OR: At Least One SDK Is Present

**Do not** pass two names in the same `@ConditionalOnClass` expecting OR. You can split them into **two separate configuration classes**, each annotated with the condition for its respective SDK, and design bean back-off so they do not conflict.

Conceptual example:

```java
@Configuration(proxyBeanMethods = false)
@ConditionalOnClass(name = "com.vendor.alpha.Client")
class AlphaIntegrationConfiguration {
    // ...
}

@Configuration(proxyBeanMethods = false)
@ConditionalOnClass(name = "com.vendor.beta.Client")
class BetaIntegrationConfiguration {
    // ...
}
```

The two fragments only illustrate splitting branches; if both SDKs are present, both classes may apply. If they register the same bean type, you must specify precedence/conditions/ordering. For complex logic, you can write a `Condition` or use appropriate nested condition structures, while testing all cases thoroughly.

## 12. Diagnosing When Conditional Classes Do Not Work

### Issue A — Class Is Declared Correctly, but Condition Does Not Match

Inspect the exact **runtime classpath**, not just the auto-config module's compile classpath. In Maven, `optional=true` or `scope=provided`/`test` can prevent the JAR from reaching the app runtime as you assumed.

In the demo, run at root:

```bash
jar tf app/target/app-1.0.0.jar
```

Check whether `BOOT-INF/lib/vendor-sdk-1.0.0.jar` appears in the entry list. With the `with-sdk` profile, this entry is expected to be present. Without the profile, it is expected to be absent.

### Issue B — Only Added @ConditionalOnClass to a Method with an SDK Return Type

Even when using `name`, a JVM/Spring code path can still resolve the method signature early. Move the method into a **nested configuration class** with a class-level condition and test with the dependency actually missing.

### Issue C — Composed Annotation Uses value

Use `@ConditionalOnClass(name = "...")` inside your custom composed annotation. Do not rely on tests always having the SDK so the `value` approach “appears to work”.

### Issue D — name Has Wrong Package After Refactoring

String names are not checked by the Java compiler. Use an integration test with the SDK present to verify the condition genuinely matches and the bean appears; IDE renames can miss strings.

### Issue E — Confusing “Class Exists” with “Bean Exists”

`@ConditionalOnClass` does not guarantee a bean of that class is registered. If you need a bean, use `@ConditionalOnBean` under the right conditions and pay attention to bean definition registration order; the two condition types answer **two different questions**.

### Issue F — Auto-Configuration Is Not in imports

A class annotated with `@AutoConfiguration` that is not listed in `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports` will not be automatically found by Spring Boot via standard auto-configuration discovery. Do not fix this by opening `@ComponentScan` to the autoconfigure package.

### Issue G — Adding Multiple Names While Expecting OR

In `@ConditionalOnClass(name={"A","B"})`, **both A and B** must be present to match. If you want either one, split the configurations or write matching condition logic.

### Issue H — Class Is Present, but API Is Incompatible

The classpath condition can still match. Check dependency versions, method signatures, transitive dependencies, linkage failures, and run integration tests in the right runtime environment; a presence condition is not a “health check”.

### Issue I — SDK Is Absent, Yet the App Still Tries to Call SDK Methods

Check whether another `@Configuration`/`@Component` class is being scanned/imported; a condition on one auto-configuration does not block all code in the project. Isolate optional dependencies into separate modules and nested configs.

### Condition Evaluation Report

You can run the app with:

```bash
java -jar app/target/app-1.0.0.jar --debug
```

Spring Boot's report helps inspect matched/unmatched classpath conditions. When reading the log, distinguish which nested config a source belongs to and which condition applies to that source.

## 13. Production Design Checklist

1. **Identify the optional class** by its fully qualified name and containing artifact. Never write only a simple name without a package.
2. **Choose the right annotation placement:** direct class-level, custom meta-annotation, or method-level? This step matters more than “preferring value or name”.
3. **Direct class-level:** use `value` when the compile classpath has the type and you want type safety/refactoring support.
4. **Meta-annotations:** always use `name` for `@ConditionalOnClass`.
5. **No compile dependency:** use a string `name`, provided code elsewhere does not directly use the SDK type without a compile dependency.
6. **SDK types in @Bean signatures:** isolate the method inside a nested `@Configuration` with a class-level condition.
7. **Do not place classpath conditions too broadly:** if a fallback is needed, the outer auto-configuration should not be disabled just because the primary SDK is absent.
8. **Bean fallback/back-off:** use `@ConditionalOnMissingBean` on the public contract where appropriate; avoid unintentionally registering two implementations.
9. **Maven optional:** verify the runtime JAR actually contains or omits the dependency, rather than only seeing the library build succeed.
10. **Test both states thoroughly:** class present and absent, ideally combining `FilteredClassLoader` with executable-JAR smoke tests.
11. **Test meta-annotations:** because string names lack compiler rename checking, maintain tests both with and without the SDK.
12. **Observe root causes:** use the Condition Evaluation Report and classpath dependency tree instead of guessing from `NoClassDefFoundError`.
13. **Do not confuse presence with functionality:** to ensure SDK compatibility, run integration tests against the real SDK version.
14. **Do not open component scanning:** auto-configurations are loaded via imports, without needing to scan library packages.

## 14. Self-Check Questions

1. Directly on a configuration class, can `@ConditionalOnClass(VendorClient.class)` be safe when the SDK is missing at runtime? **Yes**, because Boot reads annotation metadata with ASM via a supported path.
2. When creating a custom annotation `@ConditionalOnVendorClient` meta-annotated with `@ConditionalOnClass`, should you use `value` or `name`? **Must use `name`.**
3. Without the SDK on the compile classpath, you want to check a class with a condition without calling its API directly: what do you use? **`@ConditionalOnClass(name = "fully.qualified.ClassName")`.**
4. Does merely changing method-level `@ConditionalOnClass(value=Sdk.class)` to `name="..."` solve every error where a method return type contains the SDK? **No**; you need a nested configuration guarded at the class level.
5. Is `@ConditionalOnClass(name={"A","B"})` AND or OR? **AND**.
6. Does `@ConditionalOnClass` prove a Spring bean for the SDK already exists? **No**; it checks the classpath.
7. Why does `optional=true` in the auto-config POM not mean the SDK is missing when testing that module? **Because `optional` mainly prevents transitivity to consumers, while the producer module still sees the SDK.**
8. In the example, which implementation will `app` use when `with-sdk` is disabled? **Fallback**.
9. With `with-sdk`, which condition creates the marker? **The custom composed annotation using `name`**.
10. If the vendor SDK exists yet a method was removed in a new version, does the classpath condition report an error upfront? **Not guaranteed**; it does not check full API compatibility.
11. Why shouldn't the outer auto-configuration carry the SDK-present condition? **Because the outer class also owns the fallback branch that must run when the SDK is missing.**
12. Do `FilteredClassLoader` tests replace executable JAR verification? **Not completely**; you should also test actual packaging.
13. Does `@ConditionalOnMissingClass` have `Class<?>[] value` like `@ConditionalOnClass`? **No**; it uses class name strings.
14. If `VendorClient` is inside a JAR yet the application classloader cannot see it, can `@ConditionalOnClass` fail to match? **Yes**; check visibility under the actual class loader.

## Official Documentation

- [Spring Boot — Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/reference/features/developing-auto-configuration.html): explicitly documents direct class-level `value`, meta-annotation `name`, and nested configurations for methods using optional types.
- [Spring Boot 3.5 — ConditionalOnClass Javadoc](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnClass.html): official details on `value()`/`name()`, ASM, and `@Bean` method caveats.
- [Spring Boot 3.5 — ConditionalOnMissingClass Javadoc](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnMissingClass.html): syntax for checking class absence.
- [Spring Boot — Auto-configuration](https://docs.spring.io/spring-boot/reference/using/auto-configuration.html): conditions, exclusions, default configurations, and the Condition Evaluation Report.
- [Spring Boot — Testing Auto-configuration](https://docs.spring.io/spring-boot/reference/features/developing-auto-configuration.html#features.developing-auto-configuration.testing): `ApplicationContextRunner` and `FilteredClassLoader`.
- [Maven — Optional Dependencies](https://maven.apache.org/guides/introduction/introduction-to-optional-and-excludes-dependencies.html): how `optional=true` alters transitive dependencies.
