# Checking Multiple Classes Simultaneously and Designing Conditions per Feature Group in Spring Boot

## 1. The Problem: A Starter with Multiple Optional Integrations

Suppose your library provides **multiple independent features**: text encoding, data compression, and integration with a third-party vendor codec. Each feature requires different Java classes or SDKs on the classpath. If an application only installs the dependency for encoding, the other features should not cause startup failures; if only the external codec integration's dependency is missing, encoding and compression must still work.

Spring Boot solves this problem through **classpath conditions**, primarily `@ConditionalOnClass` and `@ConditionalOnMissingClass`, combined with separate nested `@Configuration` classes for each group.

Four core principles:

1. **A single `@ConditionalOnClass` checks multiple classes with AND logic.** Every listed class name must be present for the condition to match.
2. **Multiple feature groups should be checked independently.** Do not place all optional SDK classes on the parent auto-configuration class if one group can be absent while the others must still operate.
3. **Detecting a class does not mean creating a bean.** `@ConditionalOnClass` only inspects the classpath; beans also depend on `@ConditionalOnBean`, `@ConditionalOnMissingBean`, properties, and other conditions.
4. **Avoid referencing optional classes too early.** When a factory method uses types from a potentially missing dependency, isolate it inside a nested configuration guarded by a **class-level** condition, rather than placing the condition only on the `@Bean` method.

Learning target: know when to use `value` or `name` arrays; distinguish AND from OR; create multiple independent feature groups; determine behavior when optional dependencies are missing; and design auto-configuration structures that are easy to diagnose and extend.

## 2. Syntax for Checking Multiple Classes: All Must Be Present

The annotation `org.springframework.boot.autoconfigure.condition.ConditionalOnClass` has two key attributes:

```java
// Illustrative code: placed on a @Configuration or @AutoConfiguration class.
@ConditionalOnClass({
        java.util.Base64.class,
        java.nio.charset.StandardCharsets.class
})
```

This is shorthand for `value = {...}`. Both classes in the array **must** be present on the classpath. Java 17 always includes these classes, so this example matches in a standard Java 17 environment.

Using string names:

```java
@ConditionalOnClass(name = {
        "java.util.Base64",
        "com.vendor.codec.FastCodec"
})
```

Here both `java.util.Base64` **and** `com.vendor.codec.FastCodec` must be present. If `FastCodec` is not in the application, the condition is **false** — even though `Base64` is available.

### 2.1. AND Truth Table

Consider `@ConditionalOnClass(name = {"com.acme.A", "com.acme.B"})`:

| Class A present? | Class B present? | Result |
| --- | --- | --- |
| Yes | Yes | Match |
| Yes | No | No match |
| No | Yes | No match |
| No | No | No match |

With three classes A, B, C, the condition matches **only when all three are present**.

Do not interpret “checking multiple classes” as “at least any one class is present”. If you want **OR**, organize separate configurations or use a composite condition designed for OR; a multi-element `@ConditionalOnClass` does not turn itself into OR.

### 2.2. Combining `value` and `name`

The `@ConditionalOnClass` Javadoc states:
- `Class<?>[] value()`: classes that must be present.
- `String[] name()`: fully qualified names of classes that must be present.

When both are specified together, their presence requirements are combined in an **all-required** sense. Practically: every class literal and every class name is a necessary condition.

```java
@ConditionalOnClass(
        value = java.util.Base64.class,
        name = {"com.vendor.codec.FastCodec", "com.vendor.codec.CodecConfig"}
)
```

This is an illustrative annotation snippet, not a standalone Java class. Why `name` is useful: vendor classes **may not exist on the compile classpath** of this module, since the annotation only holds strings. If `FastCodec.class` is used in source, the module still needs that class on its **compile classpath**, even though it might not be on the runtime classpath.

### 2.3. `@ConditionalOnMissingClass` Checks the Opposite

`@ConditionalOnMissingClass` takes class names as strings:

```java
@ConditionalOnMissingClass("com.vendor.codec.FastCodec")
```

It matches when the specified class is **not** on the classpath. When listing multiple class names, distinguish it from OR: all specified classes must be **simultaneously absent** for the condition to match.

Combine this condition with `@ConditionalOnClass` if you need to switch between an SDK-present branch and an SDK-absent branch, but do so only when business requirements genuinely call for it. More commonly, there is an independent core configuration and a vendor configuration that only appears when the SDK is present.

## 3. `@ConditionalOnClass` Is Not a Complete Dependency Check

Merely having `com.vendor.codec.FastCodec` present does not guarantee:

- the class version has the methods/signatures your code needs;
- transitive dependencies of the SDK are all present and compatible;
- a `FastCodec` bean has been registered;
- configuration properties for the SDK are valid;
- no `LinkageError` or other initialization failure occurs at execution time;
- the application actually enabled the feature via properties.

This is a **condition on class discoverability**, not a runtime integration health check.

Example where a class is on the classpath yet no bean is registered:

```java
@ConditionalOnClass(name = "com.vendor.codec.FastCodec")
```

This condition **can match**, yet when injecting `FastCodec` into a factory method if the context lacks a matching bean, DI still fails. If you actually need a **bean**, combine the appropriate `@ConditionalOnBean`; if you want to provide a default yourself, you can use `@ConditionalOnMissingBean`.

And if you want to toggle via configuration, add `@ConditionalOnProperty`. Each condition type answers a different question.

| Condition | Actual question |
| --- | --- |
| `@ConditionalOnClass` | Are one or more required Java classes on the classpath? |
| `@ConditionalOnMissingClass` | Are the required classes absent from the classpath? |
| `@ConditionalOnBean` | Have the needed beans been detected at the time the condition is evaluated? |
| `@ConditionalOnMissingBean` | Is a matching bean missing so auto-config can provide a default? |
| `@ConditionalOnProperty` | Does the property satisfy the enabled/disabled or specified value? |
| `@ConditionalOnResource` | Can the required resource be found? |

In Spring Boot, conditional annotations appearing together on a class or method generally act as **AND across requirements**: the configuration is only applied when all required conditions match.

## 4. Designing Multiple Feature Groups: Avoid One Overly Broad Condition

### 4.1. Error-Prone Design: One “Lock Gate” for All Integrations

Suppose an auto-configuration provides all three features:

```java
@AutoConfiguration
@ConditionalOnClass(name = {
        "java.util.Base64",
        "java.util.zip.GZIPOutputStream",
        "com.vendor.codec.FastCodec"
})
class EverythingAutoConfiguration {
    // Configures Base64, GZIP, and vendor codec...
}
```

This is illustrative code, not independently runnable.

The problem is that if the application **does not install the vendor SDK** (a completely valid setup), **the entire auto-configuration class fails to match**. Consequently, Base64 and GZIP also get no beans, even though those two features have nothing to do with the SDK.

The parent condition imposes a **global AND** constraint. It fits if *all three groups must always travel together*; it does not fit if these are **three independent optional features**.

### 4.2. Right Design: Multiple Nested Configurations Under One Auto-Config

```java
@AutoConfiguration
public class FeaturesAutoConfiguration {

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnClass(name = {"java.util.Base64",
                                "java.nio.charset.StandardCharsets"})
    static class TextEncodingConfiguration {
        // @Bean methods for encoding feature
    }

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnClass(name = {"java.util.zip.GZIPOutputStream",
                                "java.io.ByteArrayOutputStream"})
    static class GzipConfiguration {
        // @Bean methods for compression feature
    }

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnClass(name = {"java.util.Base64",
                                "com.vendor.codec.FastCodec"})
    static class VendorConfiguration {
        // @Bean methods for vendor feature
    }
}
```

This is an **illustrative skeleton**, without imports or bean methods.

Now:
- The Text group matches if **both Base64 and StandardCharsets** are on the classpath.
- The GZIP group matches if **both GZIPOutputStream and ByteArrayOutputStream** are on the classpath.
- The vendor group matches if **both Base64 and FastCodec** are on the classpath.
- Missing FastCodec **does not disqualify Text/GZIP**.

If a Text bean needs an extra toggle property or needs to back off for a user bean, you can place conditions on the corresponding group or method **without affecting other groups**.

### 4.3. When Should a Condition Sit on the Parent?

Place a classpath condition on the **parent `@AutoConfiguration`** when it reflects a **dependency genuinely shared and required by every group**.

For example, if every feature requires `com.acme.core.CoreRuntime`:

```java
@AutoConfiguration
@ConditionalOnClass(name = "com.acme.core.CoreRuntime")
public class FeaturesAutoConfiguration {
    // Nested groups still have their own conditions.
}
```

When `CoreRuntime` is absent, none of the groups can operate, so a parent gate is sensible. If only the vendor group needs `FastCodec`, place that condition on the nested vendor group, **not on the parent**.

Good design makes **condition boundaries match real feature/dependency boundaries**.

### 4.4. When Only One of Two SDKs Is Needed: OR, Not AND

Some problems mean *either SDK A or SDK B works*. Writing a single array `@ConditionalOnClass(name={"sdk.A","sdk.B"})` would **misrepresent the intent** because it requires both.

A more maintainable design:

```java
@AutoConfiguration
public class StorageAutoConfiguration {

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnClass(name = "com.vendor.alpha.AlphaClient")
    static class AlphaStorageConfiguration {
        // Alpha integration
    }

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnClass(name = "com.vendor.beta.BetaClient")
    static class BetaStorageConfiguration {
        // Beta integration
    }
}
```

This is a **non-runnable skeleton**. It allows **two branches to exist independently**, equivalent to OR at the level of “at least one branch is considered”.

However, if **both SDK A and B** are present, **both nested configurations can match**. When only **a single bean** may be created, you must define precedence, back-off conditions, auto-config ordering, or a provider selection property. Merely splitting groups does not by itself resolve bean conflicts.

Spring Boot has tools like `AnyNestedCondition` for complex OR combinations, but avoid custom conditions when two independent nested configurations express the requirement more clearly.

## 5. Optional Classes and Premature Class Loading Issues

A dependency may exist on the compile classpath yet be absent at runtime. Spring Boot documentation allows:

```java
@AutoConfiguration
@ConditionalOnClass(value = com.vendor.codec.FastCodec.class)
public class VendorAutoConfiguration {
}
```

The code can only **compile when FastCodec is present at compile time**. When `@ConditionalOnClass` is attached **directly to the configuration class**, Spring Boot can read annotation metadata via ASM so a class literal for an optional dependency can be checked safely in supported cases.

However, there are **two pitfalls**:

### 5.1. Class Literals Inside Composed Annotations

If you define your own composite annotation:

```java
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@ConditionalOnClass(name = "com.vendor.codec.FastCodec")
public @interface ConditionalOnFastCodec {
}
```

This is an illustrative snippet (imports needed). **Use `name`**, not `value=FastCodec.class`, because Spring Boot's Javadoc emphasizes that the safety of class literals when analyzing direct annotations **is not guaranteed in the same way for custom meta-annotations**.

### 5.2. Optional Return Types in `@Bean` Methods

Consider this configuration:

```java
@AutoConfiguration
public class VendorAutoConfiguration {

    @Bean
    @ConditionalOnClass(name = "com.vendor.codec.FastCodec")
    FastCodec fastCodec() {
        return new FastCodec();
    }
}
```

This is **illustrative code** that only compiles if the `FastCodec` type actually exists in compile dependencies. Checking `@ConditionalOnClass` at the method level **can arrive too late**: the JVM or Spring may already have to inspect the method signature and referenced classes before the condition excluding the method is applied. A runtime without the SDK may hit a missing-class error.

The isolation pattern recommended by Spring Boot is a nested configuration:

```java
@AutoConfiguration
public class VendorAutoConfiguration {

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnClass(name = {
            "com.vendor.codec.FastCodec",
            "com.vendor.codec.FastCodecOptions"
    })
    static class VendorCodecConfiguration {

        @Bean
        @ConditionalOnMissingBean(FastCodec.class)
        FastCodec fastCodec() {
            return new FastCodec();
        }
    }
}
```

**The example above is not yet a runnable project**: it needs imports and compile dependencies providing the two vendor classes. What matters is that the condition sits at the **nested configuration class level**, letting Spring evaluate the group before inspecting factory method signatures. When a module has no vendor compile dependencies at all, you should also avoid mentioning `FastCodec` as a Java type in that module's source.

Similarly, do not place classes from an optional SDK in a **field type, constructor signature, or superclass of the parent auto-config** if you want the parent to load safely when the SDK is missing. Isolate integration code in a nested group or separate module.

## 6. Complete Example (Java 17 + Spring Boot 3.3.13): Three Independent Groups

The following Maven project demonstrates **checking multiple classes with `name`**, one group continuing to work when another group's SDK is absent, and a user bean replacing the default. The project intentionally **does not depend on** `com.vendor.codec.FastCodec`, proving the vendor branch fails to match without throwing `ClassNotFoundException`.

Configuration:
- The Text group requires two standard Java classes: `Base64` and `StandardCharsets`. This group creates a default `TextCodec` bean when no application bean exists.
- The GZIP group requires `GZIPOutputStream` and `ByteArrayOutputStream`. This group creates a marker bean `gzipFeatureMarker` as proof of registration.
- The Vendor group requires `Base64` **and** `com.vendor.codec.FastCodec`. Because the SDK is not installed, the `vendorFeatureMarker` marker does not appear.
- User config can add a custom `TextCodec` via `--demo.custom-codec=true`; in that situation the default bean backs off while the GZIP/Vendor groups remain independent.

> Note on example scope: `gzipFeatureMarker` and `vendorFeatureMarker` are **illustrative beans** for observing condition outcomes, not a complete compression implementation or SDK integration. In a real system, each group creates the necessary services/adapters rather than just a marker.

### 6.1. Directory Structure

```text
grouped-classpath-demo/
├── pom.xml
└── src/main/
    ├── java/com/example/
    │   ├── api/TextCodec.java
    │   ├── app/
    │   │   ├── DemoApplication.java
    │   │   └── UserCodecConfiguration.java
    │   └── autoconfig/
    │       └── FeatureAutoConfiguration.java
    └── resources/
        ├── application.properties
        └── META-INF/spring/
            └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

`DemoApplication` sits in package `com.example.app`; `FeatureAutoConfiguration` sits in `com.example.autoconfig`. Thus the feature auto-configuration **is outside the app's default component scan** and is discovered by Spring Boot through the imports file.

### 6.2. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>grouped-classpath-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>
    </dependencies>
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

### 6.3. `src/main/java/com/example/api/TextCodec.java`

```java
package com.example.api;

@FunctionalInterface
public interface TextCodec {
    String encode(String input);
}
```

This is the **public API/SPI**; the app can inject the interface or supply its own implementation bean. An interface by itself creates no bean.

### 6.4. `src/main/java/com/example/autoconfig/FeatureAutoConfiguration.java`

```java
package com.example.autoconfig;

import java.nio.charset.StandardCharsets;
import java.util.Base64;

import com.example.api.TextCodec;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@AutoConfiguration
public class FeatureAutoConfiguration {

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnClass(name = {
            "java.util.Base64",
            "java.nio.charset.StandardCharsets"
    })
    @ConditionalOnProperty(
            prefix = "demo",
            name = "text-enabled",
            havingValue = "true",
            matchIfMissing = true)
    public static class TextConfiguration {

        @Bean
        @ConditionalOnMissingBean(TextCodec.class)
        TextCodec textCodec() {
            return input -> Base64.getEncoder().encodeToString(
                    input.getBytes(StandardCharsets.UTF_8));
        }
    }

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnClass(name = {
            "java.util.zip.GZIPOutputStream",
            "java.io.ByteArrayOutputStream"
    })
    public static class GzipConfiguration {

        @Bean
        String gzipFeatureMarker() {
            return "GZIP_AVAILABLE";
        }
    }

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnClass(name = {
            "java.util.Base64",
            "com.vendor.codec.FastCodec"
    })
    public static class VendorConfiguration {

        @Bean
        String vendorFeatureMarker() {
            return "VENDOR_AVAILABLE";
        }
    }
}
```

**Design analysis:**

1. Parent `FeatureAutoConfiguration` **has no** condition requiring `FastCodec`. Thus SDK absence does not disable the entire parent.
2. Each nested class is annotated with `@Configuration(proxyBeanMethods=false)`. Whichever group matches has its `@Bean` methods considered for registration; other groups may not match.
3. The Text group checks **two classes** and also has its own property gate. Classpath match does not guarantee the group runs if `demo.text-enabled=false`.
4. `@ConditionalOnMissingBean(TextCodec.class)` checks for a user bean so the default backs off; this is **not** a classpath condition.
5. The Vendor group only mentions `FastCodec` as a **String name**. The project can compile without the vendor class. It declares no Java fields or method return types involving the vendor.
6. GZIP/Vendor markers use `String` for demonstration. In large systems, give beans clear names and avoid relying on String beans as business contracts; real services should have their own domain types.
7. To implement real FastCodec support, the SDK must be in compile dependencies of an appropriate integration module and bean methods isolated under a nested class with suitable conditions.

**Specifically:** merely naming a class in `@ConditionalOnClass` **does not** cause Boot to download dependencies from Maven or automatically create a bean of that type. The annotation only inspects what the runtime environment provides.

### 6.5. `src/main/java/com/example/app/UserCodecConfiguration.java`

```java
package com.example.app;

import com.example.api.TextCodec;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class UserCodecConfiguration {

    @Bean
    @ConditionalOnProperty(
            prefix = "demo",
            name = "custom-codec",
            havingValue = "true")
    TextCodec customTextCodec() {
        return input -> "CUSTOM:" + input;
    }
}
```

Because it resides under `com.example.app`, this bean is evaluated as part of application configuration. When the property is enabled, a user-declared `TextCodec` bean exists; the default in auto-configuration must back off per the condition on `textCodec()`.

### 6.6. `src/main/java/com/example/app/DemoApplication.java`

```java
package com.example.app;

import com.example.api.TextCodec;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ApplicationContext;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class DemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }

    @Bean
    ApplicationRunner report(ApplicationContext context) {
        return args -> {
            boolean codecExists = !context.getBeansOfType(TextCodec.class).isEmpty();
            String text = codecExists
                    ? context.getBean(TextCodec.class).encode("Hi")
                    : "none";

            System.out.println("CODEC_PRESENT=" + codecExists);
            System.out.println("TEXT_RESULT=" + text);
            System.out.println("DEFAULT_TEXT_BEAN="
                    + context.containsBean("textCodec"));
            System.out.println("USER_TEXT_BEAN="
                    + context.containsBean("customTextCodec"));
            System.out.println("GZIP_GROUP_BEAN="
                    + context.containsBean("gzipFeatureMarker"));
            System.out.println("VENDOR_GROUP_BEAN="
                    + context.containsBean("vendorFeatureMarker"));
        };
    }
}
```

The runner does not require injecting `TextCodec`, so it still runs when the Text group is disabled and there is no user codec. When exactly one `TextCodec` exists, `getBean(TextCodec.class)` returns it, illustrating both default and custom beans. In complex apps with multiple beans of the same interface, resolve them via `@Qualifier` / `@Primary` or select by name/`ObjectProvider` rather than implicitly assuming a single candidate.

### 6.7. `src/main/resources/application.properties`

```properties
spring.main.banner-mode=off
spring.main.web-application-type=none
logging.level.root=OFF
demo.text-enabled=true
demo.custom-codec=false
```

`demo.text-enabled` independently controls the Text group, while `demo.custom-codec` controls the user bean to test back-off. Both properties are **demo application conventions**, not general built-in Spring Boot settings.

### 6.8. `src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`

```text
com.example.autoconfig.FeatureAutoConfiguration
```

This is the **sole** primary auto-configuration candidate. The nested `@Configuration` classes inside are analyzed by Spring through the parent configuration class's structure; you do not need and should not list the three nested groups as three separate auto-config candidates if they are merely child configurations of the parent.

### 6.9. Build and Run — Case A: Default Features

In the directory containing `pom.xml`, with JDK 17+ and Maven:

```bash
mvn -q -DskipTests package
java -jar target/grouped-classpath-demo-1.0.0.jar
```

Lines printed by `ApplicationRunner` (excluding tool/environment logs):

```text
CODEC_PRESENT=true
TEXT_RESULT=SGk=
DEFAULT_TEXT_BEAN=true
USER_TEXT_BEAN=false
GZIP_GROUP_BEAN=true
VENDOR_GROUP_BEAN=false
```

Interpretation:

- `Base64` and `StandardCharsets` are available; the Text group is accepted, its property is enabled, and no other `TextCodec` bean exists.
- The string `"Hi"` has UTF-8 bytes `48 69` (hex), corresponding to Base64 `"SGk="`.
- The GZIP group requires two standard Java classes, both present on Java 17, so its marker appears.
- The Vendor group requires **both** Base64 and FastCodec, but the project lacks the SDK; the condition does not match and the marker is absent.
- The application starts normally, proving a missing optional SDK must not cause other groups to fail.

### 6.10. Case B: Disabling Only the Text Group

```bash
java -jar target/grouped-classpath-demo-1.0.0.jar --demo.text-enabled=false
```

Runner output lines:

```text
CODEC_PRESENT=false
TEXT_RESULT=none
DEFAULT_TEXT_BEAN=false
USER_TEXT_BEAN=false
GZIP_GROUP_BEAN=true
VENDOR_GROUP_BEAN=false
```

Even though **both classes in the Text group are present**, `@ConditionalOnProperty` prevents the group from applying. GZIP still runs and Vendor remains excluded. This proves classpath presence is **one of several conditions**.

### 6.11. Case C: User Replaces Default Codec

```bash
java -jar target/grouped-classpath-demo-1.0.0.jar --demo.custom-codec=true
```

Stdout:

```text
CODEC_PRESENT=true
TEXT_RESULT=CUSTOM:Hi
DEFAULT_TEXT_BEAN=false
USER_TEXT_BEAN=true
GZIP_GROUP_BEAN=true
VENDOR_GROUP_BEAN=false
```

Mechanism:
1. The app registers the `customTextCodec` bean of type `TextCodec` per the property.
2. The Text group still matches on classpath and `demo.text-enabled=true`.
3. Auto-config's `textCodec()` factory **is not registered** because `@ConditionalOnMissingBean(TextCodec.class)` sees the user bean.
4. The runner obtains the user-supplied `TextCodec`; GZIP/Vendor are unaffected.

If both `--demo.text-enabled=false --demo.custom-codec=true` are passed, the Text group is disabled yet the user codec **still exists**: `CODEC_PRESENT=true` and `TEXT_RESULT=CUSTOM:Hi`, while `DEFAULT_TEXT_BEAN=false`. Because user config is independent of the nested Text group, this behavior is intentional.

## 7. Organizing Conditions per Group in a Real Starter

A starter often has more complex integrations than the demo:

```text
feature-autoconfigure/
├── CoreAutoConfiguration.java
├── DatabaseAutoConfiguration.java
├── MessagingAutoConfiguration.java
└── MetricsAutoConfiguration.java
```

Or a parent auto-config with separate nested `@Configuration` classes. Choose the separation granularity based on size, toggleability, and library versions; both approaches can be valid.

### 7.1. Splitting by True “Dependency Closure”

For each feature, list the **required class set**:

| Group | Minimal classpath | Other conditions | Bean created |
| --- | --- | --- | --- |
| TextCodec | Base64, StandardCharsets | Property enabled, no user TextCodec yet | TextCodec |
| GZIP | GZIPOutputStream, ByteArrayOutputStream | May need properties, resources, or other beans | Compressor / demo marker |
| Vendor | SDK API, SDK configuration type | Credentials, properties, client bean, compatible version | VendorAdapter |
| Metrics | MeterRegistry, corresponding integration API | MeterRegistry bean present, metrics property | MetricsBinder |

This is a design table, **not a claim** that a single class is always sufficient to run a real integration. For JDBC, messaging, or network clients, additional classes, native libraries, authentication, or resources may be required; class conditions cannot replace all those checks.

### 7.2. Independent Groups: Put Conditions at the Narrowest Sensible Scope

If only Bean A needs `com.vendor.api.OptionalExtension`, do not apply that condition to a parent containing Beans B/C. Place the condition on a nested group or matching `@Bean`. However, if a factory method has return/parameter types involving an absent class, use a **nested class-level guard** to avoid premature class loading.

If two beans in the same group always belong together, placing the condition at the group class level reduces duplication and ensures they are enabled/disabled together.

### 7.3. Interdependent Groups: Define Relationships Explicitly

If adapter B needs core bean A:

- Check B's own required classpath.
- Use `@ConditionalOnBean(CoreService.class)` at the appropriate evaluation stage if bean A must exist.
- Place `@AutoConfiguration(after = CoreAutoConfiguration.class)` on **two top-level auto-configs** when B depends on A's definitions.
- Do not confuse bean definition ordering with bean instantiation order; DI determines instance dependencies.

If B only needs class A on the classpath and constructs bean A via its own factory, `@ConditionalOnBean` may be inappropriate. Review the actual design before combining conditions.

### 7.4. Multiple Alternative Providers: Do Not Accidentally Create Two Defaults

If providers A and B each have independent nested groups and both SDKs A/B are present, both groups can match. When they create the same `Client` interface, you must design:
- a property choosing the preferred provider;
- `@ConditionalOnMissingBean(Client.class)` and explicit ordering;
- or two named beans with qualifiers for the application to choose intentionally.

**Do not** rely on the accidental order in which Spring parses two nested classes to decide which provider wins. If this is a critical decision, declare a clear public rule and test with both SDKs present.

### 7.5. Separating Compile/Runtime Optional Dependencies

There are three classpaths to understand:

1. **Compile classpath of the auto-config module:** where the compiler must see Java types directly imported/referenced in source.
2. **Runtime classpath of the application:** where Spring Boot actually checks `@ConditionalOnClass` and loads services.
3. **Test classpath:** may include SDK mocks, extras, or dependencies causing conditions to match differently than in production.

A condition using `name="com.vendor.FastCodec"` does not require the compiler to know that type. Yet if a method returns `FastCodec`, the module **still must** have a valid compile dependency; and you must isolate that code when the runtime classpath lacks the SDK.

## 8. Diagnosing When Features Are Skipped or Startup Fails

### 8.1. Condition Evaluation Report

Run the application with:

```bash
java -jar target/grouped-classpath-demo-1.0.0.jar --debug --logging.level.root=DEBUG
```

In the *Condition Evaluation Report*, look for nested groups such as `TextConfiguration`, `GzipConfiguration`, and `VendorConfiguration`. When FastCodec is missing, the class condition can report that this class was not found; that is the valid outcome for an optional integration.

If using Actuator, `/actuator/conditions` is also useful when the dependency and exposure are properly configured; do not expose it publicly indiscriminately. Do not treat log names or report formatting as fixed across every Spring Boot version.

### 8.2. Questions to Check in Order

1. Is the parent auto-config class in `AutoConfiguration.imports` and inside the JAR?
2. Was the parent excluded by classpath/property/exclusion before nested groups were considered?
3. Which **exact classes** does the missing group require? Do FQCNs match the package/version?
4. Is the class genuinely on the **runtime** classpath, or only on compile/test classpath?
5. Are there `ClassNotFoundException` or `NoClassDefFoundError` errors caused by code referencing optional types before conditions are evaluated?
6. Did the classpath condition match, yet `@ConditionalOnProperty` or `@ConditionalOnMissingBean` excluded the bean?
7. Did two provider groups both match and create duplicate bean types/names?
8. Are there SDK version conflicts, missing transitive dependencies, or incompatible method signatures?

### 8.3. Common Failure Table

| Symptom | Likely explanation | Resolution |
| --- | --- | --- |
| Class A present yet `@ConditionalOnClass({A,B})` is false | Class B missing, due to AND | Add the right dependency or split feature groups |
| Missing vendor SDK makes core features disappear | SDK condition placed on parent | Move SDK gate down to nested vendor group |
| Wrote `@ConditionalOnClass` on `@Bean` yet got `NoClassDefFoundError` | JVM may process method signature before condition | Isolate factory in nested config with class-level guard |
| Compile error because `OptionalSdk.class` does not exist | `value` is a Java class literal needing compile dependency | Use `name` when only string-based presence check is needed |
| Class present yet bean missing | Bean conditions/properties do not match | Inspect full condition stack and bean definitions |
| Both SDK A and B present so two providers created | OR expressed via two groups without selection strategy | Add selection property, precedence, and back-off |
| Condition uses misspelled class string | Compiler does not validate FQCN strings | Test context startup with SDK present and absent |
| Missing class referenced in composed annotation causes error | Class literals in meta-annotations are not as safe as direct annotations | Use `@ConditionalOnClass(name=...)` in custom composed annotations |
| Bean created manually yet default still appears | Missing-bean condition checks wrong type/name or evaluation order | Review conditions, type metadata, and auto-config ordering |
| Matches in local test, fails to match in production | Test classpath has different dependencies than runtime | Test a classpath matrix or use `FilteredClassLoader` in tests |
| Property enabled yet group still absent | Group's classpath condition is false | True property cannot substitute for a missing class |
| SDK class exists yet method call fails | `@ConditionalOnClass` does not verify method compatibility | Align versions, run integration tests, inspect dependency tree |

## 9. Testing a Classpath Matrix Instead of a Single Package

A library with multiple optional integrations should test at least:

| Classpath | Core/Text | GZIP | Vendor |
| --- | --- | --- | --- |
| Base dependencies only | Works | Works if JDK classes exist | No |
| Full vendor SDK present | Works | Works | Eligible if other conditions match |
| Only one of two required SDK classes present | Works | Works | No (AND) |
| SDK present, vendor property disabled | Works | Works | Not registered when property gate fails |
| User-provided bean replaces default | Backs off per contract | Unaffected | Unaffected |

In Spring Boot tests, `ApplicationContextRunner` lets you launch lightweight contexts and check auto-config/bean conditions. You can use `FilteredClassLoader` to **hide certain classes from the test context classloader**, simulating missing dependencies, and assert whether beans exist.

This is a **testing technique**, not a guarantee that `FilteredClassLoader` can remove every reference if the JVM has already loaded classes directly beforehand. Isolating integrations and configuring class-level guards remains essential. When you need to test with the real vendor SDK, add the appropriate test dependency or run a separate integration test module.

Assertions should prove **context-visible outcomes**:
- when classes A and B are present, the feature bean is registered if other conditions match;
- when any single required class is missing, only that feature group goes unregistered;
- independent groups remain intact;
- user beans cause defaults to back off;
- when both provider SDKs are present, the bean selection strategy is consistent.

## 10. Knowledge Self-Check

**Question 1.** Given `@ConditionalOnClass(name={"com.acme.A","com.acme.B","com.acme.C"})`, if A and C are present but B is absent, does the configuration match?

**Answer:** No. This is **AND**; all three classes must be present.

**Question 2.** To run feature X if A **or** B is present, should you write `@ConditionalOnClass({A.class,B.class})`?

**Answer:** No. That array requires A **and** B. Create separate nested configurations for A/B or a composite OR condition if a shared bean is needed.

**Question 3.** Why shouldn't a missing vendor SDK block the core Text group?

**Answer:** Because the vendor SDK is only a dependency of the vendor group. Placing the condition on the parent turns the SDK into a mandatory requirement for all features. Place conditions at the boundary of the group using the SDK.

**Question 4.** In the demo, `com.vendor.codec.FastCodec` is absent yet `GZIP_GROUP_BEAN` is true. Why?

**Answer:** GZIP has its own classpath conditions depending only on two standard Java classes, independent of FastCodec. The vendor group is excluded independently.

**Question 5.** In the demo, does `--demo.text-enabled=false` remove `Base64` from Java?

**Answer:** No. The class remains on the classpath; the property condition merely prevents the text group from being applied.

**Question 6.** In the demo, does `--demo.custom-codec=true` cause the Text group to fail its classpath condition?

**Answer:** No. The classpath still matches, but `@ConditionalOnMissingBean(TextCodec.class)` makes the **default factory** back off in favor of the user bean.

**Question 7.** Why is a condition placed directly on an `@Bean` method with a return type from an optional SDK risky?

**Answer:** The method signature can be processed by the JVM/Spring before the method condition can protect it. Isolate the method inside a nested `@Configuration` checked for classpath presence at the **class level**.

**Question 8.** When a custom composed annotation uses `@ConditionalOnClass` to check an optional SDK, should you choose `value` or `name`?

**Answer:** Choose `name` with an FQCN string. Spring Boot explicitly notes that class literals do not have the same processing guarantees when placed inside a meta-annotation.

**Question 9.** If the SDK class is in the JAR yet the app fails due to a missing method, can `@ConditionalOnClass` protect against that?

**Answer:** Not guaranteed. The condition only checks **class** presence; ABI, method signatures, dependency versions, and runtime errors must be verified separately.

**Question 10.** Why is testing once with all dependencies present insufficient?

**Answer:** Because when deploying an application to production, some optional dependencies may be omitted or have different versions. You must test classpath combinations, especially missing individual classes in AND groups and cases where both providers are present simultaneously.

## 11. Reference Documentation

- [Spring Boot 3.3.13 — ConditionalOnClass Javadoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnClass.html): `value`/`name` list classes that **must be present**, with warnings about method signatures and meta-annotations.
- [Spring Boot — Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/reference/features/developing-auto-configuration.html): class conditions, nested `@Configuration` to isolate optional dependencies, bean conditions, and the `AutoConfiguration.imports` resource.
- [Spring Boot 3.3 — ConditionalOnMissingClass](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnMissingClass.html): counterpart condition requiring class absence.
- [Spring Boot — Testing Auto-configuration](https://docs.spring.io/spring-boot/reference/features/developing-auto-configuration.html#features.developing-auto-configuration.testing): `ApplicationContextRunner`, `FilteredClassLoader`, and testing bean conditions.

**Takeaway:** `@ConditionalOnClass` with multiple classes is **AND** logic. When features are independent, split conditions per **nested configuration/feature group**, avoiding a “global AND” at the parent. Use `name` when referencing optional classes purely by string, guard methods carrying optional types with **class-level** conditions, and verify classpath, property, and bean conditions separately to design auto-configuration accurately.
