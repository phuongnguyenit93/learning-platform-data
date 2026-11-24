# Default Configuration Detection When Not Explicitly Specified

When writing integration tests with Spring Test, you often need an `ApplicationContext` containing the beans required for the test. You can explicitly declare XML files or Java configuration classes in `@ContextConfiguration`. However, Spring Test also supports convention-based configuration detection when this annotation does not specify `locations` or `classes`.

This mechanism reduces repetitive configuration in simple test classes. Spring can look for a Java configuration class nested inside the test class or look for an XML file named after the test class. When no suitable configuration exists, or when multiple candidates exist that cannot be resolved unambiguously, context initialization fails. Therefore, you need to understand the naming conventions and limitations of default configuration detection so you know which configuration Spring is loading.

## 1. Explicit Configuration vs. Convention-Based Configuration

The Spring TestContext Framework needs to know how to create the `ApplicationContext` before running test methods. Configuration can be specified explicitly:

```java
@ExtendWith(SpringExtension.class)
@ContextConfiguration(classes = OrderTestConfig.class)
class OrderServiceTests {
    // Test methods
}
```

In this example, `classes` explicitly specifies the Java configuration class to use. If the application uses XML, you can specify `locations`:

```java
@ExtendWith(SpringExtension.class)
@ContextConfiguration(locations = "/test-context.xml")
class OrderServiceTests {
    // Test methods
}
```

When neither `classes` nor `locations` is supplied, Spring Test can apply default configuration detection. This is a convention-based mechanism, not Spring scanning the entire project and guessing which beans are needed. Spring searches for candidates according to specific rules of the `ContextLoader`.

For example, the annotation without configuration attributes:

```java
@ExtendWith(SpringExtension.class)
@ContextConfiguration
class OrderServiceTests {
    // Test methods
}
```

`@ContextConfiguration` must still be present to declare that the test uses the Spring TestContext Framework and requires loading a context. Adding only `@ExtendWith(SpringExtension.class)` without `@ContextConfiguration`, `@ContextHierarchy`, or an equivalent Spring configuration annotation does not provide a configuration source for the context.

## 2. Spring Test's Default Detection Mechanism

With Spring Test's default configuration, `@ContextConfiguration` can be used without declaring `classes` or `locations`. `DelegatingSmartContextLoader` performs default detection in sequence: it searches for `static` nested Java configuration classes annotated with `@Configuration`; if no suitable class is found, the loader falls back to the default XML resource convention. If multiple matching nested Java configuration classes exist, Spring does not pick one arbitrarily and instead raises an error so the test author specifies one explicitly.

The two common configuration forms are:

- **Java configuration class nested inside the test class:** Spring searches for `static` nested classes annotated with `@Configuration` first.
- **Default XML file:** if no Java configuration class is detected, the XML loader searches for a resource named after the fully qualified name of the test class with the `-context.xml` suffix.

With the default `DelegatingSmartContextLoader`, Spring supports both configuration styles in the sequence above. If you want predictable behavior in a project with multiple loader types or multiple configuration sources, specify `classes` or `locations` explicitly.

## 3. Detecting Nested Java Configuration Classes Inside a Test Class

### 3.1. Default Configuration Class Convention

If a test class has a `static` nested class annotated with `@Configuration`, Spring Test can detect that class as the default configuration when `@ContextConfiguration` does not specify `classes`.

Example:

```java
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.test.context.ContextConfiguration;
import org.springframework.test.context.junit.jupiter.SpringExtension;

import static org.junit.jupiter.api.Assertions.assertEquals;

@ExtendWith(SpringExtension.class)
@ContextConfiguration
class GreetingServiceTests {

    @Autowired
    private GreetingService greetingService;

    @Test
    void createsGreetingServiceFromDetectedConfiguration() {
        assertEquals("Hello, Lan", greetingService.greet("Lan"));
    }

    @Configuration
    static class TestConfig {

        @Bean
        GreetingService greetingService() {
            return new GreetingService();
        }
    }
}

class GreetingService {
    String greet(String name) {
        return "Hello, " + name;
    }
}
```

`TestConfig` is a `static` nested class annotated with `@Configuration`, so it can be detected as the default configuration. Spring creates the context from that configuration, registers the `GreetingService` bean, and injects the bean into the `greetingService` field of the test class.

### 3.2. Why Must the Configuration Class Be a Static Nested Class?

A default configuration class detected by convention is a `static` nested class. A non-static inner class requires an instance of the enclosing class to be instantiated. Spring Test does not use the test class instance as an enclosing object to instantiate this kind of configuration automatically.

Therefore, when placing configuration inside a test class, declare it as:

```java
@Configuration
static class TestConfig {
    // @Bean methods
}
```

Do not rely on a non-`static` nested class as a default configuration. If the configuration needs to live outside the test class, create a top-level configuration class and declare it explicitly with `@ContextConfiguration(classes = ...)`.

### 3.3. Multiple Nested Configuration Classes

Default detection works well when Spring can identify a single unambiguous default configuration. If the test class contains multiple `static` nested classes annotated with `@Configuration`, Spring cannot automatically know which class is intended. In that case, explicitly declare the class to use:

```java
@ExtendWith(SpringExtension.class)
@ContextConfiguration(classes = OrderServiceTests.OrderConfig.class)
class OrderServiceTests {

    @Configuration
    static class OrderConfig {
        // Order test beans
    }

    @Configuration
    static class PaymentConfig {
        // Payment test beans
    }
}
```

If the test needs both configurations, pass both classes in the desired order:

```java
@ContextConfiguration(classes = {
        OrderServiceTests.OrderConfig.class,
        OrderServiceTests.PaymentConfig.class
})
```

Explicit specification tells readers where the context is assembled from and avoids relying on automatic detection rules.

## 4. Detecting Default XML Files

### 4.1. Resource Naming Convention

When using an XML-based context loader without specifying `locations`, Spring can look up an XML file based on the fully qualified name of the test class. For the test class:

```java
package com.example.orders;

class OrderRepositoryTests {
}
```

the convention-based default resource is:

```text
classpath:com/example/orders/OrderRepositoryTests-context.xml
```

The package name is converted into a directory path, the test class name is preserved, and the `-context.xml` suffix is appended. The file must reside on the test classpath, typically under `src/test/resources`.

Example project layout:

```text
src
├── test
│   ├── java
│   │   └── com/example/orders/OrderRepositoryTests.java
│   └── resources
│       └── com/example/orders/OrderRepositoryTests-context.xml
```

The test class can declare:

```java
@ExtendWith(SpringExtension.class)
@ContextConfiguration
class OrderRepositoryTests {
    // Spring Test loads the convention-based XML resource.
}
```

The XML context loader loads the convention-based file if the resource exists and the active loader supports that detection mechanism. You can explicitly declare the resource if you want to rename the file or place it in a different location:

```java
@ContextConfiguration(locations = "classpath:/spring/order-test-context.xml")
```

### 4.2. XML File Example

A minimal XML file can register beans:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<beans xmlns="http://www.springframework.org/schema/beans"
       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
       xsi:schemaLocation="
           http://www.springframework.org/schema/beans
           https://www.springframework.org/schema/beans/spring-beans.xsd">

    <bean id="greetingService" class="com.example.orders.GreetingService"/>
</beans>
```

If the resource is placed at the default path, the test can use `@Autowired` to receive beans just like with explicitly specified XML configuration. Convention detection only helps Spring locate the resource; the XML content must still be valid and capable of instantiating the required beans.

## 5. Choosing Explicit Configuration When Needed

Default detection suits small test classes with a stable structure. When there are multiple configurations, multiple profiles, multiple modules, or a need for exact context control, specify configuration explicitly.

### 5.1. Specifying Java Configuration Classes

```java
@ExtendWith(SpringExtension.class)
@ContextConfiguration(classes = {
        OrderTestConfig.class,
        SharedTestConfig.class
})
class OrderServiceTests {
}
```

### 5.2. Specifying One or More XML Files

```java
@ExtendWith(SpringExtension.class)
@ContextConfiguration(locations = {
        "classpath:/spring/application-test.xml",
        "classpath:/spring/order-test.xml"
})
class OrderServiceTests {
}
```

### 5.3. Combining XML and Java Configuration

If you need to combine XML and Java sources, you can use `@ImportResource` in a Java configuration class or declare appropriate sources according to the active context loader. Example:

```java
@Configuration
@ImportResource("classpath:/spring/legacy-order-context.xml")
static class OrderTestConfig {
    // Java @Bean methods can be declared here.
}
```

Then specify `OrderTestConfig.class` in `@ContextConfiguration`. This makes Java configuration clearly the entry point, with XML imported as part of the context.

Avoid declaring both `classes` and `locations` arbitrarily without considering the `ContextLoader` type. Smart loaders may choose a loader based on the declared metadata type; if you need to combine both formats, use an explicit import mechanism or a loader that supports that case.

## 6. Distinguishing Spring Test Default Detection from Spring Boot

A common misconception is assuming `@ContextConfiguration` and `@SpringBootTest` use the same configuration detection rules. They belong to two different bootstrapping mechanisms.

### 6.1. Plain Spring Test

With `@ContextConfiguration` without `classes` or `locations`, Spring Test uses the context loader's convention: a `static` nested `@Configuration` class or a default XML resource based on the test class name.

### 6.2. Spring Boot Test

With `@SpringBootTest` without `classes`, Spring Boot searches for a root configuration class annotated with `@SpringBootConfiguration` in the test's package or parent packages. In a typical application, this annotation is provided indirectly by `@SpringBootApplication`.

Example:

```java
package com.example.orders;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest
class OrderApplicationTests {

    @Test
    void contextLoads() {
    }
}
```

If `OrderApplication` has `@SpringBootApplication` and sits in `com.example.orders` or an appropriate parent package, Spring Boot can detect that class as the application configuration. This mechanism does not rely on the filename `OrderApplicationTests-context.xml`.

If there are multiple configuration sources or you want to use a specific application class, declare:

```java
@SpringBootTest(classes = OrderApplication.class)
class OrderApplicationTests {
}
```

If Spring Boot cannot find `@SpringBootConfiguration`, the test usually fails with an error stating it could not find a Spring Boot configuration. In that case, check the test package, the application class location, and the `classes` configuration.

### 6.3. Comparison Table

| Mechanism | Default Configuration Searched | How to Specify Explicitly |
|---|---|---|
| Spring Test `@ContextConfiguration` | Nested `static @Configuration` or convention-based XML resource of the context loader | `classes` or `locations` |
| `@SpringJUnitConfig` | Inherits `@ContextConfiguration` mechanism and integrates JUnit Jupiter | `classes` or `locations` |
| `@SpringBootTest` | `@SpringBootConfiguration` class, typically the class with `@SpringBootApplication` | `classes` |

Do not rename the test class to fix a failure finding `@SpringBootConfiguration`, because Spring Boot does not use Spring Test's XML naming convention for that lookup. Identify which annotation is bootstrapping the context before fixing the configuration.

## 7. Using @SpringJUnitConfig with Default Configuration

`@SpringJUnitConfig` is a composed annotation combining `@ExtendWith(SpringExtension.class)` and `@ContextConfiguration`. Therefore, it can also use `@ContextConfiguration`'s default detection mechanism.

Example:

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringJUnitConfig
class PriceCalculatorTests {

    @Autowired
    private PriceCalculator calculator;

    @Test
    void calculatesTotal() {
        assertEquals(120, calculator.total(100, 20));
    }

    @Configuration
    static class TestConfig {
        @Bean
        PriceCalculator priceCalculator() {
            return new PriceCalculator();
        }
    }
}

class PriceCalculator {
    int total(int amount, int fee) {
        return amount + fee;
    }
}
```

Here `@SpringJUnitConfig` replaces the pair `@ExtendWith(SpringExtension.class)` and `@ContextConfiguration`. The nested `TestConfig` remains a detectable default Java configuration.

If you want to write it even more concisely, you can pass `classes` directly to `@SpringJUnitConfig(PriceCalculatorConfig.class)`. The explicit style fits when configuration is shared across multiple test classes or resides outside the test class.

## 8. Default Configuration and Inheritance Between Test Classes

Spring Test supports inheriting configuration from a parent test class when configuration annotations allow inheritance. This is often useful when multiple tests share a common baseline configuration.

Example:

```java
@ExtendWith(SpringExtension.class)
@ContextConfiguration(classes = SharedTestConfig.class)
abstract class BaseIntegrationTests {
}

class OrderServiceTests extends BaseIntegrationTests {
    // Uses the inherited context configuration.
}
```

`@ContextConfiguration` allows inheriting configuration from the superclass by default via the `inheritLocations` attribute. For Java class configuration, this attribute also controls inheritance of component classes. If a subclass declares its own configuration, Spring can merge metadata according to inheritance rules; if you want to completely replace the inherited configuration, set `inheritLocations = false` and explicitly declare the subclass's configuration source.

Example of a subclass using its own configuration:

```java
@ContextConfiguration(
        classes = OrderServiceTests.OrderConfig.class,
        inheritLocations = false
)
class OrderServiceTests extends BaseIntegrationTests {

    @Configuration
    static class OrderConfig {
        // Configuration specific to order tests
    }
}
```

When using inheritance, distinguish configuration from the superclass from default detection on the test class itself. A test class can receive configuration via inherited metadata without needing to re-detect it on its own. If the resulting context is confusing, inspect the entire superclass chain and configuration annotations, not just the subclass.

## 9. When No Default Configuration Is Found

Default detection does not guarantee that Spring can always create a context. Common situations include:

- The test class has no `static` nested class annotated with `@Configuration` and no convention-based XML resource.
- The XML file exists but is in the wrong package or has the wrong suffix.
- Multiple nested configuration classes exist, preventing Spring from choosing a single default configuration.
- The test uses a custom context loader or a loader that supports only one configuration type.
- Configuration is found, but a required bean or resource fails to initialize.

When no candidate is found, Spring typically throws an exception during context bootstrapping, before any test method runs. The error message usually indicates that default configuration classes could not be detected or the default resource could not be found. If the resource was found but its content is invalid, errors may appear as XML parse errors, bean creation errors, or `Failed to load ApplicationContext`.

### 9.1. Troubleshooting by Symptom

| Symptom | What to Check | Resolution |
|---|---|---|
| No default configuration class detected | Whether a `static` nested class with `@Configuration` exists | Add a valid configuration or declare `classes` explicitly |
| XML resource not found | Package, test class name, `-context.xml` suffix, location on test classpath | Place the resource following convention or specify `locations` |
| Multiple nested `@Configuration` classes | Whether the test class has multiple default candidates | Select a class or list of classes via `classes` |
| `@SpringBootConfiguration` not found | Whether the test package is under the application's package | Put the test in the right package or pass `classes` to `@SpringBootTest` |
| Configuration found but initialization failed | Beans, profiles, properties, datasources, resources, and root cause in stack trace | Fix the failing configuration or dependency; do not randomly rename the test class |

### 9.2. Using Explicit Configuration to Reduce Ambiguity

When a test is part of a large suite, explicit configuration is often easier to maintain:

```java
@SpringJUnitConfig(classes = {
        SharedTestConfig.class,
        OrderFeatureTestConfig.class
})
class OrderFeatureTests {
}
```

In return, the test class has additional metadata to maintain. Choosing between default detection and explicit configuration should be based on stability, reusability, and clarity of the configuration.

## 10. How Detected Configuration Affects the Context Cache

The Spring TestContext Framework can cache `ApplicationContext` instances so test classes using the same configuration do not have to reinitialize the context repeatedly. The detected configuration becomes part of the metadata used to determine which context to load and cache.

This has several practical consequences:

- Multiple test classes sharing the same Java configuration class or the same XML resource can reuse the context if related metadata is compatible.
- Default XML files are named per test class, so different test classes may inadvertently use separate contexts even when the XML contents are similar.
- Explicit configuration sharing a single class can make context reuse intent clearer.
- If a test dirties the context, `@DirtiesContext` can tell Spring to evict the context from the cache; this annotation should be used when a test genuinely mutates context state.

Default detection only determines which configuration source to use; it does not mean every test method always creates a new `ApplicationContext`. Context reuse is governed by Spring Test's caching mechanism and configuration metadata.

## 11. Workflow to Identify Which Configuration Spring Is Using

When a test initializes a context unexpectedly, you can check step by step:

1. **Identify the bootstrap annotation.** Does the test use `@ContextConfiguration`, `@SpringJUnitConfig`, or `@SpringBootTest`?
2. **Check configuration attributes.** Are `classes`, `locations`, `value`, or a custom context loader passed?
3. **If not explicitly declared, check default conventions.** For Spring Test, look for a `static` nested `@Configuration` class and an XML resource matching the test class name.
4. **Check inherited configuration.** See whether a superclass has `@ContextConfiguration` and whether inheritance attributes are enabled.
5. **Read the root exception.** Distinguish a failure to locate configuration from finding configuration but failing to instantiate beans.
6. **Specify explicitly when needed.** Use `classes` or `locations` to remove ambiguity and make the test's configuration source clear.

For example, if `OrderServiceTests` uses `@ContextConfiguration` without a nested configuration class, check the resource `com/example/orders/OrderServiceTests-context.xml` on the test classpath. If the test actually uses `@SpringBootTest`, look for a `@SpringBootConfiguration` class in an appropriate package or specify the application class via `classes`.

## 12. Notes for Applying This in Projects

- Use default detection for simple tests where the default configuration has a single unambiguous candidate and resource names follow convention.
- Use a `static` nested Java configuration class inside the test when the configuration serves only that test.
- Use top-level test configuration and declare `classes` when multiple tests need to reuse the configuration.
- Use `locations` when testing XML configuration or when you need to pinpoint exact resource files.
- Distinguish Spring Test's rules from Spring Boot's `@SpringBootConfiguration` lookup rules.
- Do not rely on default detection if the test class has multiple configuration sources or requires a complex context hierarchy; declare metadata explicitly.

Default configuration detection helps Spring Test reduce repetitive declarations, but it only works according to specific conventions. With `@ContextConfiguration`, Spring can detect a `static` nested `@Configuration` class or an XML resource named after the test class. With `@SpringBootTest`, Spring Boot searches for a `@SpringBootConfiguration` class, usually the class annotated with `@SpringBootApplication`. When convention cannot identify a single configuration, specify `classes` or `locations` explicitly so the context is created exactly as the test expects.
