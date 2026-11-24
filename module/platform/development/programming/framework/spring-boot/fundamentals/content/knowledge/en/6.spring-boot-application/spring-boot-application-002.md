# `@SpringBootConfiguration` in Relation to `@Configuration`

In a Spring Boot application, the startup class is typically annotated with `@SpringBootApplication`:

```java
package com.example.shop;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ShopApplication {

    public static void main(String[] args) {
        SpringApplication.run(ShopApplication.class, args);
    }
}
```

When looking at this annotation, beginners often focus on component scanning and auto-configuration, yet inside it sits a foundational piece: **`@SpringBootConfiguration`**. This annotation is itself built upon **Spring Framework's `@Configuration`**.

That relationship explains why the `ShopApplication` class can declare `@Bean` methods, why Spring Boot recognizes which class is the root configuration of the application, and why certain tests need to locate a `@SpringBootConfiguration`.

This lesson belongs to the **`@SpringBootApplication`** chapter of **Spring Boot Fundamentals**. The focus is on properly understanding the role of `@SpringBootConfiguration` compared to `@Configuration`: what they share, what Spring Boot adds, and when to use each annotation.

## 1. The Big Picture: Three Annotation Layers

First, look at the meta-annotation relationship:

```text
@SpringBootApplication
    │
    ├── @SpringBootConfiguration
    │       │
    │       └── @Configuration
    │               │
    │               └── @Component (at the meta-annotation level)
    │
    ├── @EnableAutoConfiguration
    │
    └── @ComponentScan
```

The diagram shows only the components relevant to this lesson and does not list every metadata item or annotation alias.

In Spring, an annotation can be **annotated with another annotation**. When `@SpringBootApplication` is placed on a class, the annotations that compose it provide metadata for Spring to process.

Reading from the bottom up:

- **`@Configuration`**: marks a class as a source of Spring bean definitions, typically via `@Bean` methods.
- **`@SpringBootConfiguration`**: is a specialized variant of `@Configuration` for marking the **Spring Boot application configuration**.
- **`@SpringBootApplication`**: includes `@SpringBootConfiguration` plus other key capabilities, notably enabling auto-configuration and component scanning.

In other words, `@SpringBootConfiguration` **has the bean-configuring capability of `@Configuration`**, while carrying distinct identification semantics for Spring Boot. However, **using `@SpringBootConfiguration` alone does not automatically enable component scanning or auto-configuration** like `@SpringBootApplication` does.

### 1.1. Meta-Annotation Is Not Java Class Inheritance

This is an annotation composition relationship, not:

```java
class SpringBootConfiguration extends Configuration { ... }
```

Both `@SpringBootConfiguration` and `@Configuration` are annotation types. The relationship comes from one annotation having the other on its own declaration.

You can visualize the core declaration as:

```java
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@Configuration
public @interface SpringBootConfiguration {
    // Other attributes/metadata omitted.
}
```

This is **conceptual illustrative code**, not a full copy of Spring Boot's source. What matters is that `@Configuration` appears on the `@SpringBootConfiguration` definition; Spring has mechanisms to read composed metadata and process classes annotated at the higher level.

## 2. What Is `@Configuration`?

`@Configuration` belongs to **Spring Framework**, located in the package:

```java
import org.springframework.context.annotation.Configuration;
```

This annotation marks a class that contains Spring configuration declarations, usually `@Bean` methods returning objects to be managed inside the `ApplicationContext`.

Example:

```java
package com.example.shop.config;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class PricingConfiguration {

    @Bean
    public DiscountPolicy discountPolicy() {
        return new PercentageDiscountPolicy(10);
    }
}
```

Assume `DiscountPolicy` is an interface and `PercentageDiscountPolicy` is a matching implementation. When Spring processes `PricingConfiguration`, the `discountPolicy()` method supplies a bean definition to the container. Under the default scope, this bean is a **singleton within an ApplicationContext**.

The application can obtain the bean via dependency injection:

```java
package com.example.shop.service;

import com.example.shop.config.DiscountPolicy;
import org.springframework.stereotype.Service;

@Service
public class CheckoutService {

    private final DiscountPolicy discountPolicy;

    public CheckoutService(DiscountPolicy discountPolicy) {
        this.discountPolicy = discountPolicy;
    }
}
```

In this example, the Spring container creates and supplies the `DiscountPolicy` bean. `@Configuration` does not require the class to have a `main` method, and an application can have **multiple** `@Configuration` classes to separate groups of configuration.

### 2.1. `@Bean` and `@Configuration` Serve Two Different Roles

- `@Configuration` goes on the **configuration class**, telling Spring that this class supplies bean definitions.
- `@Bean` goes on a **factory method**, telling Spring that the object returned by the method should be registered and managed as a bean.

Example:

```java
@Configuration
public class TimeConfiguration {

    @Bean
    public java.time.Clock applicationClock() {
        return java.time.Clock.systemUTC();
    }
}
```

When code has a constructor:

```java
public ReportService(Clock applicationClock) {
    this.applicationClock = applicationClock;
}
```

Spring can inject `Clock` if that bean has been placed in the same `ApplicationContext`.

The `@Configuration` annotation by itself **does not execute arbitrary Java code** simply because the class exists on the classpath. The configuration class must be discovered or registered by Spring: via component scanning, `@Import`, being specified as a source when creating the context, or an equivalent configuration registration mechanism.

### 2.2. `@Configuration` Is Also a Type of Component

`@Configuration` is meta-annotated with `@Component`. Consequently, in an application with appropriate component scanning, Spring can find configuration classes as candidate components.

Example:

```text
com.example.shop
├── ShopApplication.java              (@SpringBootApplication)
├── config/
│   └── PricingConfiguration.java     (@Configuration)
└── service/
    └── CheckoutService.java          (@Service)
```

When `ShopApplication` is in package `com.example.shop`, the default component scan enabled by `@SpringBootApplication` normally covers `com.example.shop` and its subpackages. In that case, `PricingConfiguration` is found and its `@Bean` methods are processed.

What to distinguish:

- `@Configuration` is a **candidate discovered by scanning**.
- `@ComponentScan` is the annotation that **enables/specifies package scanning**.
- These two annotations do not have the same function.

Therefore, if a class only has `@Configuration` but sits outside the scan range and is neither imported nor registered in another way, the `@Bean` objects inside it may not be created in the application context.

## 3. What Is `@SpringBootConfiguration`?

`@SpringBootConfiguration` belongs to **Spring Boot**, located in the package:

```java
import org.springframework.boot.SpringBootConfiguration;
```

It is a specialized annotation meaning: **this class provides Spring Boot application-level configuration**.

In terms of defining beans, it behaves like `@Configuration` because it is meta-annotated with `@Configuration`. The addition is an **identification marker**: Spring Boot components, especially in testing support, can search for a configuration class annotated with `@SpringBootConfiguration` as the starting point for the application.

One way to picture it:

```text
@Configuration
    └── "This is a Spring bean configuration class."

@SpringBootConfiguration
    ├── "This is a Spring bean configuration class."
    └── "This is the Spring Boot application configuration class."
```

That second meaning is why Spring Boot provides this annotation even though Spring Framework already has `@Configuration`.

### 3.1. Example of Direct Usage

You can declare:

```java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.context.annotation.Bean;

@SpringBootConfiguration
public class DemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }

    @Bean
    public java.time.Clock applicationClock() {
        return java.time.Clock.systemUTC();
    }
}
```

The configuration above can supply the `Clock` bean to the Spring context. However, it **does not by default provide the capabilities users typically expect when seeing `@SpringBootApplication`**, such as scanning `@Service` classes in subpackages or enabling auto-configuration for web or data.

If you simply replace:

```java
@SpringBootApplication
```

with:

```java
@SpringBootConfiguration
```

in an existing web application, controllers will likely not be discovered, `DataSource` will not be auto-configured, or the web server will not be set up as before. That is because two crucial pieces were removed: `@ComponentScan` and `@EnableAutoConfiguration`.

### 3.2. Not Every `@Configuration` Needs to Be Changed to `@SpringBootConfiguration`

In an application, there are usually multiple configuration classes:

```text
com.example.shop
├── ShopApplication.java            (@SpringBootApplication)
└── config/
    ├── SecurityConfiguration.java  (@Configuration)
    ├── CacheConfiguration.java     (@Configuration)
    └── SchedulingConfiguration.java (@Configuration)
```

`SecurityConfiguration`, `CacheConfiguration`, and `SchedulingConfiguration` are feature/component configurations. They **do not need** `@SpringBootConfiguration` to register `@Bean` definitions.

Usually, the `@SpringBootConfiguration` marker appears once, indirectly through the `@SpringBootApplication` class representing the primary application configuration. This also helps Spring Boot test bootstrapping identify one clear root configuration point.

### 3.3. What `@SpringBootConfiguration` Does Not Add on Its Own

`@SpringBootConfiguration` by itself:

- Is not a launch instruction: the JVM still needs `main` or another bootstrap entry.
- Does not automatically enable `@ComponentScan`.
- Does not automatically activate `@EnableAutoConfiguration`.
- Does not automatically create web controllers, a web server, repositories, or database connections.
- Does not replace Spring Boot starter dependencies.
- Does not require all beans to live in the same class.
- Does not automatically make beans in other packages appear if they have not been discovered or registered.

The primary difference from `@Configuration` is **Boot-specific identification metadata**, not a new dependency injection system.

## 4. How Does `@SpringBootApplication` Combine Capabilities?

A typical main class:

```java
package com.example.shop;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ShopApplication {

    public static void main(String[] args) {
        SpringApplication.run(ShopApplication.class, args);
    }
}
```

`@SpringBootApplication` is a composite annotation whose three key parts are:

| Component | Contribution |
|---|---|
| `@SpringBootConfiguration` | Marks this as the Boot application configuration; carries the functionality of `@Configuration` |
| `@EnableAutoConfiguration` | Asks Spring Boot to evaluate auto-configurations based on classpath, properties, beans, and conditions |
| `@ComponentScan` | Allows finding components in scanned packages: `@Component`, `@Service`, `@Repository`, `@Controller`, `@Configuration`, etc. |

A class with `@SpringBootApplication` therefore **simultaneously plays the role of a Spring configuration class** and serves as a convenient entry point to start the Boot application.

You can declare `@Bean` right on the main class:

```java
@SpringBootApplication
public class ShopApplication {

    public static void main(String[] args) {
        SpringApplication.run(ShopApplication.class, args);
    }

    @Bean
    public Clock applicationClock() {
        return Clock.systemUTC();
    }
}
```

This example requires importing `org.springframework.context.annotation.Bean` and `java.time.Clock`. The `Clock` bean is registered because `@SpringBootApplication` carries `@SpringBootConfiguration` and therefore carries the semantics of `@Configuration`.

However, if the number of custom beans grows large, it is better to extract them into `@Configuration` classes grouped by functionality rather than placing every `@Bean` method in the main class.

### 4.1. Placing the Main Class in the Root Package

Recommended structure:

```text
com.example.shop
├── ShopApplication.java            (@SpringBootApplication)
├── controller/
│   └── ProductController.java      (@RestController)
├── service/
│   └── ProductService.java         (@Service)
└── config/
    └── PricingConfiguration.java   (@Configuration)
```

By default, component scanning from `@SpringBootApplication` starts from the package containing the application class and its subpackages. Placing `ShopApplication` in `com.example.shop` enables discovering controllers, services, and configuration components beneath it.

If you place main in:

```text
com.example.shop.boot.ShopApplication
```

while the controller resides in:

```text
com.example.shop.controller.ProductController
```

then the controller is in a **sibling package**, not beneath `com.example.shop.boot`. Default component scanning may miss it. In that case, you can either relocate the main class or configure the scan scope explicitly.

Note: **this is the role of `@ComponentScan` inside `@SpringBootApplication`**, not a separate behavior provided by `@SpringBootConfiguration`.

### 4.2. Auto-Configuration Is Not a Function of `@SpringBootConfiguration`

Spring Boot auto-configuration typically relies on starter dependencies and conditions, such as the presence or absence of certain classes, presence or absence of user-declared beans, or property values.

When the appropriate Spring MVC dependencies are on the classpath, auto-configuration can set up the foundational beans needed for a web application, depending on the environment and configuration.

If an application is annotated only with `@SpringBootConfiguration`, do not assume it automatically configures a web server simply because it is launched with `SpringApplication.run(...)`. For core configuration, choosing the configuration source and enabling auto-configuration are two separate concerns.

### 4.3. Manually Combining the Three Annotations: When Is It Needed?

In learning scenarios or when fine-grained control is needed, you can declare each part explicitly:

```java
package com.example.shop;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.context.annotation.ComponentScan;

@SpringBootConfiguration
@EnableAutoConfiguration
@ComponentScan(basePackages = "com.example.shop")
public class ShopApplication {

    public static void main(String[] args) {
        SpringApplication.run(ShopApplication.class, args);
    }
}
```

This illustrates the core roles corresponding to `@SpringBootApplication`. However, the real `@SpringBootApplication` also carries certain defaults, scan filters, and attribute aliases; therefore **you should not treat this minimal combination as identical in every implementation detail** to `@SpringBootApplication`.

For typical projects, `@SpringBootApplication` is clearer and easier to maintain. Split the annotations only when there is a practical reason and you understand what is being customized.

## 5. Comparison Table of the Three Annotations

| Criterion | `@Configuration` | `@SpringBootConfiguration` | `@SpringBootApplication` |
|---|---|---|---|
| Framework | Spring Framework | Spring Boot | Spring Boot |
| Acts as a `@Bean` definition source | Yes | Yes, via `@Configuration` | Yes, via `@SpringBootConfiguration` |
| Carries Boot application config marker | No | Yes | Yes |
| Automatically enables component scanning | No | No | Yes |
| Automatically enables auto-configuration | No | No | Yes |
| Can be used for secondary config classes | Common | Usually unnecessary | Usually discouraged |
| Typically used on the Boot app main class | Only with custom bootstrap configuration | Possible, in special cases | Most common |
| Recognized by Spring Boot test bootstrap as root Boot config | Not just for having `@Configuration` | Yes | Yes |
| Supports configuring `proxyBeanMethods` | Yes | Yes, forwarded to `@Configuration` | Yes, forwarded via `@SpringBootConfiguration` |

A way to remember:

```text
@Configuration
    = defines bean configuration

@SpringBootConfiguration
    = @Configuration + Boot application config marker

@SpringBootApplication
    = Boot config marker + auto-configuration + component scanning
```

Do not read the table as "the annotation further to the right is always better." Each annotation has its own scope of use. A `@Configuration` class dedicated to caching, security, or mapping remains completely appropriate inside an application that uses `@SpringBootApplication`.

## 6. `proxyBeanMethods` Connects the Annotations

An important detail that is often overlooked is the **`proxyBeanMethods`** attribute.

Because `@SpringBootConfiguration` is built on `@Configuration`, it also allows controlling proxy behavior for `@Bean` methods. `@SpringBootApplication` exposes this attribute as well to apply it to the underlying configuration part.

In common Spring Boot versions, the default for `proxyBeanMethods` is `true`. When enabled on a full configuration class, Spring can proxy the configuration class so that direct calls between `@Bean` methods honor the container-managed bean lifecycle and scope.

### 6.1. Example of a Dependency Between Two Beans

Suppose there are two simple Java classes:

```java
public class MailClient {
    public void send(String message) {
        System.out.println(message);
    }
}
```

```java
public class ReportService {
    private final MailClient mailClient;

    public ReportService(MailClient mailClient) {
        this.mailClient = mailClient;
    }
}
```

Configuration:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class ReportingConfiguration {

    @Bean
    public MailClient mailClient() {
        return new MailClient();
    }

    @Bean
    public ReportService reportService() {
        return new ReportService(mailClient());
    }
}
```

In the default `@Configuration` case with `proxyBeanMethods = true`, Spring uses a configuration class enhancement mechanism so that when `reportService()` calls `mailClient()`, the call can be intercepted and return the container-managed `MailClient` bean, respecting bean scope and semantics.

If you change it to:

```java
@Configuration(proxyBeanMethods = false)
```

then the `mailClient()` call inside `reportService()` is a direct Java method call, which can create a **new `MailClient` object**, separate from the singleton instance Spring registered for the `mailClient` bean. This is a difference in identity and lifecycle, not merely performance.

### 6.2. Writing Configurations Without Direct Inter-`@Bean` Calls

A usually clearer pattern is letting Spring inject the bean via a method parameter:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class ReportingConfiguration {

    @Bean
    public MailClient mailClient() {
        return new MailClient();
    }

    @Bean
    public ReportService reportService(MailClient mailClient) {
        return new ReportService(mailClient);
    }
}
```

When creating `ReportService`, Spring resolves the `MailClient` parameter from the container. This approach does not rely on directly calling the `mailClient()` method on the configuration object.

This pattern fits well when `@Bean` definitions are independent or relate to one another through Spring's dependency injection. In that case, `proxyBeanMethods = false` can reduce the need to proxy the configuration class.

**`proxyBeanMethods = false` does not disable `@Bean`, does not disable dependency injection, and does not turn the configuration class into an unmanaged Java class.** It primarily affects intercepting inter-method `@Bean` calls on the configuration instance.

### 6.3. This Attribute on `@SpringBootConfiguration` and `@SpringBootApplication`

You can write:

```java
@SpringBootConfiguration(proxyBeanMethods = false)
public class ApplicationConfiguration {
    // Independent @Beans or ones receiving dependencies via parameters.
}
```

Or on the common main class:

```java
@SpringBootApplication(proxyBeanMethods = false)
public class ShopApplication {

    public static void main(String[] args) {
        SpringApplication.run(ShopApplication.class, args);
    }
}
```

The attribute on `@SpringBootApplication` forwards to the root configuration part of the composite annotation. When this configuration declares no `@Bean` methods that need to call one another, turning off proxying can be appropriate.

Setting `proxyBeanMethods = false` on the **main class** does not mean every other `@Configuration` class in the project automatically switches to `false`. Each configuration class should be understood by its own declaration and how Spring processes it.

Do not flip this flag out of habit without knowing whether the configuration has calls between `@Bean` methods.

## 7. Why Does Spring Boot Test Need to Recognize `@SpringBootConfiguration`?

This is the most important practical difference between `@SpringBootConfiguration` and `@Configuration`.

When writing an integration test like:

```java
package com.example.shop.service;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest
class ProductServiceIntegrationTest {

    @Test
    void contextLoads() {
        // If the context fails to start, this test fails.
    }
}
```

and **not** passing an explicit configuration class to `@SpringBootTest`, Spring Boot's test bootstrap mechanism can search upward through the test's package hierarchy to locate a class marked with `@SpringBootConfiguration`. A `@SpringBootApplication` class also satisfies this because it carries this marker.

Example of a sensible layout:

```text
src/main/java/
└── com/example/shop/
    └── ShopApplication.java        (@SpringBootApplication)

src/test/java/
└── com/example/shop/
    └── service/
        └── ProductServiceIntegrationTest.java (@SpringBootTest)
```

A test placed in `com.example.shop.service` can search up to the parent package `com.example.shop` and pick up `ShopApplication` as the root Boot configuration.

### 7.1. What If There Is Only `@Configuration`?

Suppose the main class is designed with a custom bootstrap:

```java
@Configuration
public class CustomApplicationConfig {
    // ...
}
```

If the test simply writes:

```java
@SpringBootTest
class CustomIntegrationTest {
}
```

then merely having `@Configuration` in the project is **not enough** to guarantee Spring Boot automatically identifies it as the root configuration through its `@SpringBootConfiguration` search mechanism.

In that case, you can:

- Explicitly provide the configuration class the test needs, such as `@SpringBootTest(classes = CustomApplicationConfig.class)`, if that fits the desired bootstrap setup.
- Use a main class with `@SpringBootApplication` in the appropriate package structure.
- Use `@SpringBootConfiguration` when you are genuinely defining a dedicated root configuration for a Boot application.

Example of specifying the test source:

```java
package com.example.shop.service;

import com.example.shop.config.CustomApplicationConfig;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest(classes = CustomApplicationConfig.class)
class CustomIntegrationTest {

    @Test
    void contextLoads() {
    }
}
```

This does not mean that simply writing `classes` automatically brings in all auto-configurations or components. The context contents still depend on the annotations and configuration of the selected class.

### 7.2. Common Error: Unable to Find a Spring Boot Configuration

A test bootstrap error can look similar to:

```text
Unable to find a @SpringBootConfiguration.
You need to use @ContextConfiguration or @SpringBootTest(classes=...)
with your test.
```

Possible causes include:

- The test resides in a package outside the branch of the main class.
- The application only has `@Configuration`, with no discoverable `@SpringBootConfiguration` source.
- The project/module layout prevents the application configuration from being on the test classpath.
- The test needs an isolated context but has not specified a configuration source.

The fix is to determine which configuration the test should use, not to attach `@SpringBootConfiguration` to every `@Configuration` class "so Spring can find it."

### 7.3. Why Avoid Having Multiple Root Markers?

If multiple classes are annotated with `@SpringBootConfiguration` within the scope that test bootstrapping treats as candidates, locating the root configuration can become ambiguous or fail reporting that multiple configurations were found.

Layout to avoid in a simple application:

```text
com.example.shop
├── ShopApplication.java       (@SpringBootApplication)
└── config/
    └── CacheConfiguration.java (@SpringBootConfiguration)  <-- unnecessary
```

`CacheConfiguration` only needs `@Configuration`. It can be discovered via component scan or registered appropriately. There is no typical benefit to using `@SpringBootConfiguration` for every secondary configuration.

In systems with multiple applications, multiple modules, or complex test suites, multiple valid Boot applications may exist. In such cases, organize package layouts and test bootstrapping carefully or specify `classes` explicitly, rather than assuming the entire repository may only ever have one marker.

### 7.4. Distinguishing `@TestConfiguration` from the Root Configuration Marker

Spring Boot also provides `@TestConfiguration` to create supplemental configuration specifically for tests. Example:

```java
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;

@TestConfiguration(proxyBeanMethods = false)
public class FixedClockTestConfiguration {

    @Bean
    public Clock fixedClock() {
        return Clock.fixed(
            Instant.parse("2030-01-01T00:00:00Z"),
            ZoneOffset.UTC
        );
    }
}
```

This class can be imported into a test when needed:

```java
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Import;

@SpringBootTest
@Import(FixedClockTestConfiguration.class)
class ClockIntegrationTest {

    @Test
    void contextLoads() {
    }
}
```

`@TestConfiguration` serves to supplement beans or customize the context in tests. It **does not replace `@SpringBootConfiguration`'s role of identifying the main application configuration**. If the context already has another `Clock` bean, the test also needs to resolve the multiple-beans-of-same-type issue, e.g., with a qualifier or `@Primary` as appropriate; do not assume adding a new bean always overrides the existing one.

## 8. A Complete Example: Main Class and Secondary Configuration Class

Let's look at how a small Spring Boot project can be organized:

```text
src/main/java/com/example/shop/
├── ShopApplication.java
├── config/
│   └── GreetingConfiguration.java
├── service/
│   ├── GreetingFormatter.java
│   ├── DefaultGreetingFormatter.java
│   └── GreetingService.java
└── web/
    └── GreetingController.java
```

### 8.1. Root Configuration Class

`ShopApplication.java`:

```java
package com.example.shop;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ShopApplication {

    public static void main(String[] args) {
        SpringApplication.run(ShopApplication.class, args);
    }
}
```

This class acts as the `@SpringBootConfiguration` source via `@SpringBootApplication`, while also enabling component scanning and auto-configuration.

### 8.2. Defining the Types to Use

`service/GreetingFormatter.java`:

```java
package com.example.shop.service;

public interface GreetingFormatter {
    String format(String name);
}
```

`service/DefaultGreetingFormatter.java`:

```java
package com.example.shop.service;

public class DefaultGreetingFormatter implements GreetingFormatter {

    private final String prefix;

    public DefaultGreetingFormatter(String prefix) {
        this.prefix = prefix;
    }

    @Override
    public String format(String name) {
        return prefix + ", " + name + "!";
    }
}
```

These are ordinary Java types; they do not automatically become Spring beans simply by being on the classpath.

### 8.3. Configuring Secondary Beans with `@Configuration`

`config/GreetingConfiguration.java`:

```java
package com.example.shop.config;

import com.example.shop.service.DefaultGreetingFormatter;
import com.example.shop.service.GreetingFormatter;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class GreetingConfiguration {

    @Bean
    public GreetingFormatter greetingFormatter() {
        return new DefaultGreetingFormatter("Hello");
    }
}
```

No `@SpringBootConfiguration` is needed for this class. `@Configuration` is sufficient to mark the source providing the `GreetingFormatter` bean.

### 8.4. Service Receiving the Dependency via Constructor

`service/GreetingService.java`:

```java
package com.example.shop.service;

import org.springframework.stereotype.Service;

@Service
public class GreetingService {

    private final GreetingFormatter formatter;

    public GreetingService(GreetingFormatter formatter) {
        this.formatter = formatter;
    }

    public String greet(String name) {
        return formatter.format(name);
    }
}
```

### 8.5. Controller Using the Service

`web/GreetingController.java`:

```java
package com.example.shop.web;

import com.example.shop.service.GreetingService;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class GreetingController {

    private final GreetingService greetingService;

    public GreetingController(GreetingService greetingService) {
        this.greetingService = greetingService;
    }

    @GetMapping("/greeting")
    public String greeting(
            @RequestParam(defaultValue = "Spring Boot") String name
    ) {
        return greetingService.greet(name);
    }
}
```

With a project that has `spring-boot-starter-web` and the application running on the default port, you can call:

```text
GET http://localhost:8080/greeting?name=Lan
```

Result:

```text
Hello, Lan!
```

Application formation flow:

```text
ShopApplication (@SpringBootApplication)
    │
    ├── @SpringBootConfiguration
    │       └── identifies the Spring Boot root configuration
    │
    ├── @ComponentScan
    │       ├── discovers GreetingConfiguration (@Configuration)
    │       ├── discovers GreetingService (@Service)
    │       └── discovers GreetingController (@RestController)
    │
    ├── @EnableAutoConfiguration
    │       └── configures web foundation based on dependencies/conditions
    │
    └── GreetingConfiguration
            └── @Bean GreetingFormatter
                    │
                    ▼
            GreetingService
                    │
                    ▼
            GreetingController
```

In this example, the **root configuration** and **secondary configuration** both participate in building the context, yet do not share the same responsibility. This is a key reason to keep `@SpringBootApplication` on the main class while keeping feature/business configurations on `@Configuration`.

## 9. Common Misconceptions

### 9.1. "`@SpringBootConfiguration` Is a Drop-In Replacement for `@SpringBootApplication`"

Incorrect. `@SpringBootConfiguration` only provides the configuration role and marker. It does not include component scanning or auto-configuration unless you declare them separately.

When changing the main class annotation from `@SpringBootApplication` to `@SpringBootConfiguration`, the context may fail to discover controllers or services as before.

### 9.2. "Any Class with `@Configuration` Is a Boot Root Configuration"

Incorrect. `@Configuration` is a general Spring mechanism. Meanwhile, Boot test bootstrapping can use `@SpringBootConfiguration` as a marker to find the root configuration when tests do not specify explicit classes.

In a typical application, secondary `@Configuration` classes do not need to act as this marker.

### 9.3. "`@Configuration` Automatically Scans Every Package"

Incorrect. `@Configuration` tells Spring how to process a configuration class that has already been registered. `@ComponentScan` or another registration mechanism determines which classes are discovered.

A configuration outside the scan scope will not appear automatically just because it carries the `@Configuration` annotation.

### 9.4. "`@Bean` Can Only Be Used When `@SpringBootConfiguration` Is Present"

Incorrect. `@Bean` works across many appropriately processed Spring configuration forms. `@Configuration` is the most common way to group factory methods; `@SpringBootConfiguration` inherits that capability rather than inventing new `@Bean` syntax.

### 9.5. "`proxyBeanMethods = false` Stops Spring from Managing Beans"

Incorrect. Spring still registers beans from `@Bean`. The primary difference is that the configuration does not use a proxy to intercept direct calls between `@Bean` methods. Needed beans can be passed via method parameters or constructor injection.

### 9.6. "Adding `@SpringBootConfiguration` to Every Config Makes Tests Pass"

Do not do this. If tests cannot locate the root configuration, check the packages, classpath, and test annotations. Creating multiple root markers can make identifying the primary application ambiguous.

## 10. Diagnosing Related Errors

| Symptom | What to check | Reason |
|---|---|---|
| `@SpringBootTest` reports it cannot find `@SpringBootConfiguration` | Test and main class packages, or `@SpringBootTest(classes = ...)` | Test bootstrap needs to identify the root Boot configuration |
| Test reports multiple Boot configurations found | Multiple classes annotated with `@SpringBootConfiguration` within search range | Root marker is ambiguous |
| Application startup is missing `@Service` or `@Controller` | Main class location and component scan scope | `@SpringBootConfiguration` does not scan packages on its own |
| Missing bean from a `@Configuration` class | Has the class been scanned, imported, or registered? | Being annotated on the classpath does not mean the class is in the context |
| `@Bean` exists but fails due to missing dependency | Constructor/bean method parameters, config conditions | Bean source was recognized, but dependencies were not satisfied |
| Two different instances created when calling `@Bean` directly | `proxyBeanMethods` and calls between methods | `false` lets direct Java calls instantiate a new object |
| Multiple beans of the same type cause ambiguous injection | `@Qualifier`, `@Primary`, names, and active configurations | Not a `@SpringBootConfiguration` marker issue |
| Web app fails to start as web after switching to `@SpringBootConfiguration` | Annotations dropped when replacing `@SpringBootApplication` | Missing required component scan/auto-configuration |

### 10.1. When a Bean Is Missing, Ask in Order

Suppose you see a log like:

```text
Parameter 0 of constructor in GreetingService
required a bean of type GreetingFormatter that could not be found.
```

Analyze:

1. Is `GreetingConfiguration` in a scanned package?
2. Does that class actually have `@Configuration` and is it registered in the context?
3. Is the `@Bean` method creating `GreetingFormatter` valid and active?
4. Is there a conditional annotation or profile preventing the bean from being created?
5. Does the main class still have `@SpringBootApplication`, or was it replaced with a narrower marker?

Do not try to solve this by turning every `@Configuration` into `@SpringBootConfiguration`: that does not replace configuration discovery or bean wiring.

### 10.2. When Tests Fail, Ask in Order

If `@SpringBootTest` cannot locate the application configuration:

1. Is the test inside the package branch of the `@SpringBootApplication` class?
2. Is the main class present on the test classpath?
3. Was `@SpringBootApplication` accidentally replaced with plain `@Configuration`?
4. Is the test meant to use the main application context or a custom context?
5. If using a custom context, have `classes` or appropriate test configuration mechanisms been supplied?

For a normal integration test, a clean package layout is usually the simplest solution. For tests needing special bootstrapping, declaring explicit configuration makes the test intent clearer.

## 11. Practice Exercises: Observing the Differences

You can practice with a simple Spring Boot application that has the `spring-boot-starter-web` dependency.

### Experiment A — `@SpringBootApplication` Can Contain `@Bean`

Keep the main class with `@SpringBootApplication`, and add:

```java
@Bean
public Clock clock() {
    return Clock.systemUTC();
}
```

Create a service receiving `Clock` via constructor. Observe that Spring injects the bean without needing a separate `@Configuration` on the main class. Explanation: `@SpringBootApplication` carries `@SpringBootConfiguration`, which is built on `@Configuration`.

### Experiment B — Extracting `@Configuration` into a Secondary Class

Move `@Bean Clock` to `TimeConfiguration`:

```java
@Configuration(proxyBeanMethods = false)
public class TimeConfiguration {

    @Bean
    public Clock clock() {
        return Clock.systemUTC();
    }
}
```

Place this class in a subpackage of the main class's package. The application can still inject `Clock` when component scan detects `TimeConfiguration`.

Next, move the config class outside the scan range without `@Import`. This change helps demonstrate that `@Configuration` does not find its way into the context on its own.

### Experiment C — Using `@SpringBootConfiguration` Alone

In a separate test project, create a main class with only:

```java
@SpringBootConfiguration
public class MinimalApplication {

    public static void main(String[] args) {
        SpringApplication.run(MinimalApplication.class, args);
    }

    @Bean
    public ApplicationRunner runner() {
        return args -> System.out.println("Root configuration loaded");
    }
}
```

Remember to import `SpringApplication`, `SpringBootConfiguration`, `ApplicationRunner`, and `Bean`. `ApplicationRunner` is invoked by Spring Boot after the context has been initialized successfully.

Compare this with a main class using `@SpringBootApplication`. Observe that directly declared beans are still processed, but a configuration with only the `@SpringBootConfiguration` marker does not activate the full component scan and auto-configuration of the composite annotation.

### Experiment D — Finding Root Configuration in Integration Tests

Create a `@SpringBootTest` test in the same package branch as the `@SpringBootApplication` main class. Then try placing the test in a different package branch and specifying `@SpringBootTest(classes = ShopApplication.class)` as needed.

Through this, you can see that the `@SpringBootConfiguration` marker serves an additional role in identifying the application configuration source during Boot test bootstrapping, rather than being just an alias syntax for `@Configuration`.

### Experiment E — Changing How Beans Are Wired

In a `@Configuration` class, create two `@Bean` methods where the second method calls the first method directly. Observe the implications when `proxyBeanMethods` is enabled versus disabled. Then switch to receiving the dependent bean via a method parameter:

```java
@Bean
public ReportService reportService(MailClient mailClient) {
    return new ReportService(mailClient);
}
```

This expresses dependencies explicitly and usually does not require a proxy to coordinate direct calls between `@Bean` methods.

## 12. Guidelines for Applying in Spring Boot Projects

When structuring an application, keep responsibilities clearly divided:

- **Use `@SpringBootApplication` on the main class** when you want standard Spring Boot bootstrapping, including the root configuration marker, auto-configuration, and component scanning.
- **Use `@Configuration` classes** for bean configuration grouped by module or specific responsibility; they are valid Spring configurations and can be split across multiple classes.
- **Use `@SpringBootConfiguration` directly** when you need control over bootstrap components or want to mark the Boot root configuration without pulling in all features bundled by `@SpringBootApplication`.
- **Use `@TestConfiguration`** for supplemental test configurations, not as a replacement for the Boot root configuration marker.
- **Use `@Bean`** on factory methods to register objects into the container; whether the configuration class uses proxying is a separate concern.

Think of each annotation as answering one question:

```text
@Configuration
    "Where are the bean definitions of this group declared?"

@SpringBootConfiguration
    "Which class is the Spring Boot application configuration source?"

@SpringBootApplication
    "Which class is the convenient bootstrap entry point combining
     application configuration, scanning, and auto-configuration?"
```

Once you understand that division, you will not confuse **bean registration**, **package scanning**, **enabling auto-configuration**, and **identifying root configuration for Spring Boot tests** as a single behavior. `@SpringBootConfiguration` is the bridge between Spring Framework's `@Configuration` and Spring Boot's `@SpringBootApplication`.
