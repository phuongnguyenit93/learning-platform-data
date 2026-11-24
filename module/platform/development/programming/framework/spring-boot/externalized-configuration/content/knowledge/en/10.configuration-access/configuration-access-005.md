# Injecting Single Values with @Value on Constructors, Fields, and Methods

## 1. Why inject configuration values?

In a Spring Boot application, many values should not be hard-coded in Java code: displayed greetings, timeouts, retry counts, endpoint addresses, feature modes, or processing thresholds. These values can change across development, testing, and production environments.

For example, the application reads `src/main/resources/application.yml`:

```yaml
demo:
  greeting: "Hello from application.yml"
  retry-count: 3
  feature-enabled: true
  region: "ap-southeast"
```

Instead of writing:

```java
String greeting = "Hello from application.yml";
int retryCount = 3;
```

we want Spring to supply the values resolved from the configuration system into the bean.

**`@Value`**, from package `org.springframework.beans.factory.annotation`, is a way to ask Spring to **inject a value represented by an expression or placeholder** into a bean injection point.

Common syntax:

```java
@Value("${demo.greeting}")
```

Here `${demo.greeting}` is a **property placeholder**. When Spring processes the injection point, the placeholder is resolved against `Environment` and existing property sources.

There are three important practical locations:

1. **Constructor parameter:** the value is passed in when the object is created.
2. **Field:** Spring sets the value directly on a field of the bean.
3. **Method/parameter:** Spring invokes an injection method or setter and passes the required value.

This article focuses on **injecting single values** such as `String`, `int`, and `boolean`. When configuration is a multi-field group, consider `@ConfigurationProperties`.

## 2. @Value does not read a specific file on its own

`@Value("${demo.greeting}")` does not mean "read key `demo.greeting` specifically from `application.yml`". It asks Spring for the **effective value** of that property.

For example, `application.yml` contains:

```yaml
demo:
  greeting: "From YAML"
```

But when running:

```bash
java -jar app.jar --demo.greeting="From command line"
```

a bean created with:

```java
@Value("${demo.greeting}")
String greeting;
```

typically receives `From command line`, because command-line arguments have higher precedence than Config Data in standard Spring Boot configuration.

Similarly, an environment variable passed to the Java process:

```bash
DEMO_GREETING="From environment variable" java -jar app.jar
```

can supply the value for `demo.greeting` when no higher-precedence source overrides it.

Therefore, separate two questions:

- **Where is the value chosen from?** Decided by Spring's `Environment` mechanism and precedence order among property sources.
- **How is the value placed into the bean?** Performed by `@Value` and Spring's dependency injection mechanism.

The two mechanisms work together, but they are not synonymous.

## 3. Preparing the demo application

The examples use Spring Boot 3.x, Java 17 or later, and an application configured with `@SpringBootApplication`.

Configuration file:

```yaml
# src/main/resources/application.yml
demo:
  greeting: "Hello from the application"
  retry-count: 3
  feature-enabled: true
  region: "vn"
  max-items: 50
```

Startup class:

```java
package com.example.configdemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ConfigDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(ConfigDemoApplication.class, args);
    }
}
```

The following examples place components in package `com.example.configdemo` or subpackages so they are discovered by Spring component scan.

Remember: the standard `@Value` mechanism takes effect on **Spring-managed objects**. If you call `new MyClass()` yourself, you have created a plain Java object that does not go through Spring's value injection process.

## 4. Constructor injection: usually the preferred choice

### 4.1. Basic example

```java
package com.example.configdemo;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

@Component
public class GreetingService {

    private final String greeting;
    private final int retryCount;

    public GreetingService(
            @Value("${demo.greeting}") String greeting,
            @Value("${demo.retry-count:3}") int retryCount) {
        this.greeting = greeting;
        this.retryCount = retryCount;
    }

    public String getGreeting() {
        return greeting;
    }

    public int getRetryCount() {
        return retryCount;
    }
}
```

Meaning:

- `@Component` lets Spring recognize the class as a bean.
- `@Value("${demo.greeting}")` placed on a **constructor parameter** requests resolving property `demo.greeting`.
- `@Value("${demo.retry-count:3}")` placed on the `int` parameter; if the property is not found, uses default `3`.
- The constructor assigns values to `final` fields. Afterward, the object holds a fully initialized state.

Add an observer component:

```java
package com.example.configdemo;

import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.stereotype.Component;

@Component
public class GreetingPrinter implements ApplicationRunner {

    private final GreetingService service;

    public GreetingPrinter(GreetingService service) {
        this.service = service;
    }

    @Override
    public void run(ApplicationArguments args) {
        System.out.println(service.getGreeting());
        System.out.println("retryCount = " + service.getRetryCount());
    }
}
```

When run with the given configuration, the program can print:

```text
Hello from the application
retryCount = 3
```

If run with:

```bash
java -jar app.jar --demo.greeting="Hello from CLI" --demo.retry-count=7
```

the values injected into the newly created bean correspond to the effective configuration:

```text
Hello from CLI
retryCount = 7
```

### 4.2. Why is constructor injection worth preferring?

Constructor injection has practical advantages:

- **Valid object immediately upon creation:** required dependencies and values are passed during construction.
- **Fields can be `final`:** clearly expresses that data is not reassigned after the constructor.
- **Easy unit testing:** you can instantiate `new GreetingService("Test", 2)` directly without starting a Spring context.
- **Visible dependencies:** readers of the constructor immediately know what values the bean requires.

Plain Java/JUnit test example:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;

import org.junit.jupiter.api.Test;

class GreetingServiceTest {

    @Test
    void constructorReceivesValues() {
        GreetingService service = new GreetingService("In test", 4);

        assertEquals("In test", service.getGreeting());
        assertEquals(4, service.getRetryCount());
    }
}
```

When instantiating directly with `new` in this test, Spring does **not** resolve placeholders. You explicitly pass the values into the constructor, and that itself is a testing advantage.

### 4.3. Do you need @Autowired on the constructor?

For a bean with a **single constructor**, modern Spring can use that constructor to inject dependencies without needing `@Autowired` on the constructor.

In the `GreetingService` example, the parameters have `@Value`, while the constructor needs no extra annotation.

If a class has multiple constructors, which constructor Spring selects must be designed explicitly; `@Autowired` can be placed on the appropriate constructor. Avoid creating multiple competing constructors without a consistent selection rule.

## 5. Injecting directly into fields with @Value

### 5.1. Field injection example

```java
package com.example.configdemo;

import jakarta.annotation.PostConstruct;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

@Component
public class FieldConfigPrinter {

    @Value("${demo.greeting:Hello}")
    private String greeting;

    @Value("${demo.retry-count:3}")
    private int retryCount;

    @PostConstruct
    public void printConfiguration() {
        System.out.println("Field greeting = " + greeting);
        System.out.println("Field retryCount = " + retryCount);
    }
}
```

Spring creates the bean and then processes field injection points. When the method annotated with `@PostConstruct` is invoked under normal bean lifecycle, the injected values have already been set.

Notable points:

- No need to write a constructor accepting `greeting` and `retryCount`.
- `@Value` attaches directly to the field receiving the data.
- Can inject into `private` fields because Spring performs injection via reflection/framework bean processing.
- This is not an assignment that runs when Java executes `new` outside Spring.

### 5.2. Why does field injection have limitations?

Code like:

```java
@Value("${demo.greeting}")
private String greeting;
```

is concise, yet hides configuration dependencies inside the class. If you instantiate:

```java
FieldConfigPrinter printer = new FieldConfigPrinter();
```

Spring injects nothing into the object you created yourself. The `greeting` field may remain `null` and `retryCount` may be `0` per Java's default values.

Common limitations:

1. Hard to instantiate the object in unit tests without Spring or reflection.
2. Hard to represent required dependencies using `final` fields with post-construction field injection.
3. Easy to accidentally use a field too early, such as inside the bean's own constructor.
4. A class can accumulate many configuration fields without a clear initialization contract.

Field injection still appears in short examples, small apps, or existing codebases, but constructor injection is usually easier to maintain for required dependencies.

### 5.3. Do not read a @Value field inside the constructor if it is field-injected

Problematic example:

```java
@Component
public class BadFieldExample {

    @Value("${demo.greeting}")
    private String greeting;

    public BadFieldExample() {
        // At this point, field injection may not have happened yet.
        System.out.println(greeting);
    }
}
```

The value of `greeting` when the constructor runs has generally not been injected yet. Do not view this as "Spring failed to read application.yml"; this is a **timing issue in the bean creation lifecycle**.

If the value is needed to build initial state, inject it via constructor:

```java
@Component
public class GoodConstructorExample {

    private final String greeting;

    public GoodConstructorExample(
            @Value("${demo.greeting}") String greeting) {
        this.greeting = greeting;
        System.out.println(this.greeting);
    }
}
```

When choosing field injection, use the value after Spring finishes property injection, such as in `@PostConstruct` or business methods invoked after bean initialization.

## 6. Injecting into methods and setters

Besides constructors and fields, Spring can supply configuration values via **injection methods**.

### 6.1. Method accepting parameters with @Value

Example of a method accepting two configuration values:

```java
package com.example.configdemo;

import jakarta.annotation.PostConstruct;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

@Component
public class MethodConfigPrinter {

    private String region;
    private boolean featureEnabled;

    @Autowired
    public void configure(
            @Value("${demo.region:local}") String region,
            @Value("${demo.feature-enabled:false}") boolean featureEnabled) {
        this.region = region;
        this.featureEnabled = featureEnabled;
    }

    @PostConstruct
    public void printConfiguration() {
        System.out.println("region = " + region);
        System.out.println("featureEnabled = " + featureEnabled);
    }
}
```

Here:

- `@Autowired` on the method asks Spring to invoke that method as an injection point.
- `@Value` on **each parameter** specifies the corresponding configuration value to resolve.
- Spring calls `configure(...)` while populating the bean, after object instantiation and before standard initialization callbacks.
- This method is not called again whenever an external configuration value changes.

With the initial YAML configuration, expected output:

```text
region = vn
featureEnabled = true
```

### 6.2. Single-parameter setter with @Value

For a setter taking a single parameter, you can write:

```java
package com.example.configdemo;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

@Component
public class BannerSettings {

    private String banner;

    @Value("${demo.greeting:Hello}")
    public void setBanner(String banner) {
        this.banner = banner;
    }

    public String getBanner() {
        return banner;
    }
}
```

`@Value` on a method is a form of injection declaration processed by Spring for container-managed beans. This injection point suits a single value attached to a setter.

Another expression style, often clearer when a method takes multiple parameters, is `@Autowired` on the method and `@Value` on each parameter as in `MethodConfigPrinter`.

Do not confuse **method injection** with manually calling a method that has `@Value`-annotated parameters. If you write:

```java
settings.setBanner("Manual assignment");
```

that is just an ordinary Java method call, not Spring reading configuration at call time.

### 6.3. When should you choose setter/method injection?

Setter/method injection is useful when a value is optional or when an existing class structure needs a configuration step after object instantiation. A single method can handle multiple related parameters in one call.

However, fields assigned after the constructor are not yet ready when the constructor runs. If the class must always have the value from the moment of instantiation, constructor injection is usually the clearer choice.

Furthermore, Spring calling a setter during bean creation **does not mean** that setter acts as an automatic runtime configuration change listener.

## 7. Comparison table of the three injection sites

| Criterion | Constructor | Field | Method/setter |
| --- | --- | --- | --- |
| Where `@Value` is placed | Constructor parameter | On field | On method or injection method parameters |
| When data is received | When bean is created | After creation, during injection step | After creation, when Spring calls injection method |
| Can use `final` fields? | Yes | Incompatible with post-creation field injection | Incompatible if assigned after constructor |
| Convenience for plain Java unit tests | Very good | Worse | Can call setter manually |
| Are dependencies visible at construction? | Yes | No | Not at constructor time |
| Suitable example | Required values | Short code, simple examples | Optional configuration or multiple parameters |
| Auto-updates when property changes? | No | No | No |

This table applies to normal configuration injection into Spring singleton beans. Specialized mechanisms such as refresh scope, bean recreation, or querying `Environment` at use time have different lifecycles and are not default behaviors of `@Value`.

## 8. Property placeholder: `${...}` syntax

The most common syntax in this article is:

```java
@Value("${demo.greeting}")
```

It asks Spring to resolve the key `demo.greeting` from `Environment`.

### 8.1. Default values

Syntax:

```java
@Value("${demo.greeting:Hello}")
private String greeting;
```

The part after the colon inside the placeholder is the **fallback value** when the property is not found.

Example with an integer:

```java
@Value("${demo.retry-count:3}")
private int retryCount;
```

If `demo.retry-count` has no provider, Spring can convert the fallback string `3` to `int`.

With a Boolean:

```java
@Value("${demo.feature-enabled:false}")
private boolean featureEnabled;
```

If the key is not found, `false` is used.

### 8.2. Missing property without a default

Example:

```java
@Component
public class RequiredConfig {

    public RequiredConfig(
            @Value("${demo.required-token}") String token) {
        // ...
    }
}
```

If `demo.required-token` is absent and no special configuration changes placeholder handling, Spring Boot will normally be unable to create this bean and startup can fail with an unresolved placeholder error.

That is helpful for required configuration: the application should fail early when essential input is missing.

For sensitive values like tokens, avoid printing received values to logs or displaying them in error messages.

### 8.3. Empty default

```java
@Value("${demo.optional-note:}")
private String note;
```

If the key does not exist, the default can be an empty string.

However, **an empty string differs from a completely non-existent property**. If a configuration source supplies `demo.optional-note=""`, the result can be the empty string from that source itself. Do not assume every empty value automatically triggers the default after the colon.

For inputs that must be checked as non-empty, add appropriate validation or business checks.

### 8.4. Do not use placeholders as arbitrary file lookups

`@Value("${demo.greeting}")` specifies a **property key**. It does not open files on its own, parse arbitrary JSON, or fetch secrets from an external service. Those capabilities only exist when the corresponding configuration source is integrated into Spring `Environment` or custom logic resolves the data.

## 9. Type conversion during value injection

One advantage of `@Value` is that Spring has a type conversion mechanism for single values.

Example:

```yaml
demo:
  retry-count: 5
  feature-enabled: false
  threshold: 0.75
```

Fields receiving Java types:

```java
@Value("${demo.retry-count:3}")
private int retryCount;

@Value("${demo.feature-enabled:true}")
private boolean featureEnabled;

@Value("${demo.threshold:0.5}")
private double threshold;
```

When the properties resolve and convert successfully, the results are:

```text
retryCount = 5
featureEnabled = false
threshold = 0.75
```

If a value is invalid for the target type, Spring can report an error during bean creation. For instance, `demo.retry-count=abc` cannot be converted directly to `int` under normal rules.

Do not treat `@Value` as a mechanism for ignoring data errors. For configuration requiring strict constraints—positive numbers, valid durations, allowed value sets—add validation, or use `@ConfigurationProperties` with Bean Validation for a group of properties.

### 9.1. Canonical property names and relaxed binding

Spring Boot recommends writing keys in `@Value` in canonical **lowercase, kebab-case** form, for example:

```java
@Value("${demo.retry-count}")
private int retryCount;
```

Consistent spelling helps Spring Boot leverage property lookups from multiple configuration formats. Do not assume `@Value` has all the list, map, and nested-structure binding capabilities of `@ConfigurationProperties`; the two mechanisms have different scopes and utilities.

For example, an environment variable passed to the JVM:

```bash
DEMO_RETRYCOUNT=8 java -jar app.jar
```

is a familiar representation when converting property name `demo.retry-count` into canonical environment variable form. For `demo.greeting`, `DEMO_GREETING` is more straightforward. Use canonical names in placeholders and verify in `Environment` if an environment variable is not mapping as predicted.

## 10. @Value also supports SpEL expressions

In addition to `${...}` placeholders, Spring `@Value` can also use **Spring Expression Language (SpEL)** with `#{...}` syntax.

Example:

```java
@Value("#{2 * 3}")
private int computedValue;
```

The evaluated value is `6`.

Or:

```java
@Value("#{systemProperties['user.home']}")
private String userHome;
```

This expression reads the Java system property `user.home` via SpEL.

Comparison:

| Syntax | Meaning |
| --- | --- |
| `@Value("${demo.greeting}")` | Look up property from the configuration environment |
| `@Value("${demo.greeting:Hello}")` | Look up property, with a fallback value |
| `@Value("#{2 * 3}")` | Evaluate SpEL expression |
| `@Value("Static content")` | Inject literal string |

There is no need to use SpEL when you just want to read a simple property. Placeholders are easier to read and closer to the intent of Externalized Configuration.

Also distinguish the symbols: `${...}` is a placeholder, while `#{...}` is a SpEL expression. They are not the same mechanism.

## 11. Which sources do @Value values come from?

In a Spring Boot application, a key such as `demo.greeting` can be supplied by:

- `application.yml`, `application.properties` files;
- profile-specific documents;
- external configuration files outside the JAR;
- data loaded via `spring.config.import`;
- process environment variables;
- Java system properties;
- command-line arguments;
- other configuration sources added by the framework or application.

Example:

```yaml
# application.yml
demo:
  greeting: "from-yaml"
```

Run:

```bash
DEMO_GREETING=from-env java -jar app.jar
```

The value of `demo.greeting` is typically `from-env` if no higher-precedence source overrides it.

Run:

```bash
DEMO_GREETING=from-env java -jar app.jar --demo.greeting=from-cli
```

The value injected via `@Value("${demo.greeting}")` is `from-cli` in the normal case.

The main point is: **Spring injects the result after resolving source precedence**, rather than literally injecting "the first value seen in a file" or choosing based on where the annotation appears in the class.

## 12. When is @Value resolved in the bean lifecycle?

Picture two bean styles.

**Constructor injection:**

```text
Spring prepares to create bean
        |
        +-- resolves ${demo.greeting}
        |
        +-- invokes constructor(greeting)
        |
        +-- object has final field assigned
        |
        +-- continues bean initialization steps
```

**Field/method injection:**

```text
Spring invokes constructor
        |
        +-- Java object is created
        |
        +-- Spring processes @Value on field/method
        |
        +-- Spring invokes applicable initialization callbacks
        |
        +-- bean is ready for application use
```

That is why you **should not read a field injected with `@Value` inside the same object's constructor**.

For `@PostConstruct` in a normally configured Spring bean, field/method injection points have already been processed. Thus, it is a place where injected values can be observed if you need to demonstrate lifecycle order.

However, do not rely on the injection order of multiple independent fields or methods to implement order-dependent business logic. If you need to establish state from multiple values, group them into a constructor or a single method with explicit parameters.

### 12.1. @Value does not refresh values automatically

Suppose a bean is created at 9 a.m. with:

```text
demo.greeting = Hello
```

At 10 a.m. you edit the configuration file to:

```text
demo.greeting = Hi
```

A regular singleton bean that already received `Hello` via `@Value` **does not automatically change** just because the file on disk was edited. The application normally needs a restart to pick up the new value through the bean creation lifecycle.

If the application has a specialized dynamic configuration mechanism, you must design a refresh workflow or query properties on demand; that is not a default feature of `@Value`.

## 13. @Value on @Bean factory method parameters

Besides `@Component`, Spring can also resolve `@Value` in parameters of a `@Configuration` bean factory method.

Example:

```java
package com.example.configdemo;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class WorkerConfiguration {

    @Bean
    public WorkPolicy workPolicy(
            @Value("${demo.retry-count:3}") int retryCount,
            @Value("${demo.feature-enabled:false}") boolean enabled) {
        return new WorkPolicy(retryCount, enabled);
    }
}

class WorkPolicy {

    private final int retryCount;
    private final boolean enabled;

    WorkPolicy(int retryCount, boolean enabled) {
        this.retryCount = retryCount;
        this.enabled = enabled;
    }

    public int getRetryCount() {
        return retryCount;
    }

    public boolean isEnabled() {
        return enabled;
    }
}
```

Here, `@Value` is placed on the **factory method parameters**, and `@Bean` asks Spring to call the method to create the `WorkPolicy` object.

This is useful when the constructed class is outside your code control or when you want to keep object construction in a configuration class.

It differs from annotating a business method called multiple times. Spring resolves parameters when the container invokes the factory method to create the bean, not automatically every time someone calls an ordinary Java method.

## 14. @Value only works when the object is managed by Spring

A common pitfall:

```java
public class PlainService {

    @Value("${demo.greeting}")
    private String greeting;

    public String greeting() {
        return greeting;
    }
}
```

And:

```java
PlainService service = new PlainService();
System.out.println(service.greeting());
```

In this situation, the result can be `null`: you instantiated the object yourself, so it never passed through Spring's annotation injection step.

To have it managed, you can declare `@Component` and ensure component scan discovers the class:

```java
@Component
public class PlainService {

    @Value("${demo.greeting}")
    private String greeting;

    public String greeting() {
        return greeting;
    }
}
```

Then retrieve the bean via dependency injection:

```java
@Component
public class PlainServiceRunner implements ApplicationRunner {

    private final PlainService service;

    public PlainServiceRunner(PlainService service) {
        this.service = service;
    }

    @Override
    public void run(ApplicationArguments args) {
        System.out.println(service.greeting());
    }
}
```

Or create the bean via `@Bean` in a `@Configuration` class. The core point is not the annotation name on the class, but **whether the object is created by the Spring container and processed through the bean lifecycle**.

## 15. Do not use @Value on static fields

Example to avoid:

```java
@Component
public class StaticConfiguration {

    @Value("${demo.greeting}")
    private static String greeting;
}
```

A `static` field belongs to the class, not to a specific bean instance. Directly injecting `@Value` on a static field is not supported by Spring like instance field injection; it typically results in the value not being assigned as intended.

If a static API is strictly required for compatibility with legacy code, consider refactoring to pass beans or values through managed objects, instead of expecting Spring to automatically populate a static field.

Do not work around this with a trick that copies the value into a static field inside `@PostConstruct` unless design changes are truly impossible; that creates global state and makes lifecycles and testing hard to reason about.

## 16. When to use @Value vs. @ConfigurationProperties?

`@Value` works very well for **a few single values**:

```java
@Component
public class RetryService {
    private final int maxRetries;

    public RetryService(
            @Value("${demo.retry-count:3}") int maxRetries) {
        this.maxRetries = maxRetries;
    }
}
```

But if configuration has many related keys:

```yaml
client:
  endpoint: "https://api.example.invalid"
  connection-timeout: 5s
  read-timeout: 15s
  retry-count: 3
  retry-enabled: true
```

then scattering many `@Value` annotations across multiple classes becomes hard to manage.

Spring Boot provides `@ConfigurationProperties` to bind **a structured group of properties** into a configuration object, offering richer type support, name binding, metadata, and more convenient validation.

Comparison:

| Criterion | `@Value` | `@ConfigurationProperties` |
| --- | --- | --- |
| Primary need | One or a few single values | A group of related configuration properties |
| Placement | Field, parameter, method | Configuration class/bean |
| Placeholders | Yes | Configured via binder mechanism |
| SpEL | Yes | Not the target mechanism |
| Binding nested structures | Inconvenient | Designed for this purpose |
| Multi-property validation | Requires extra setup | Easy to combine with Bean Validation |
| Configuration centralization | Easily scattered if overused | Better for configuration groups |

Not every application needs to convert all `@Value` usages to `@ConfigurationProperties`. Choose the mechanism based on configuration complexity and scale.

## 17. Testing @Value injection

### 17.1. Unit testing constructor injection without Spring

From the `GreetingService` class created above:

```java
@Test
void canConstructWithoutSpring() {
    GreetingService service = new GreetingService("Hello test", 6);

    assertEquals("Hello test", service.getGreeting());
    assertEquals(6, service.getRetryCount());
}
```

This test verifies **object logic** and how values are used after construction; it does not test the placeholder mechanism.

### 17.2. Integration testing with a Spring Boot context

If you want to verify that Spring actually resolves `@Value` from property sources, use a context-creating test:

```java
package com.example.configdemo;

import static org.junit.jupiter.api.Assertions.assertEquals;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest(properties = {
        "demo.greeting=Hello integration test",
        "demo.retry-count=9"
})
class GreetingServiceIntegrationTest {

    @Autowired
    private GreetingService greetingService;

    @Test
    void valuesComeFromSpringEnvironment() {
        assertEquals("Hello integration test",
                greetingService.getGreeting());
        assertEquals(9, greetingService.getRetryCount());
    }
}
```

Here:

- `@SpringBootTest` starts a Spring context for testing.
- The `properties` array supplies values specific to the test environment.
- Spring creates the `GreetingService` bean and resolves `@Value` parameters.
- The test verifies the injected results for the specific case.

Depending on project structure, you may need to specify the main application class on `@SpringBootTest` if Spring Boot cannot automatically locate the appropriate startup configuration. The sample code sits in the same package as `ConfigDemoApplication`.

### 17.3. Why is field injection harder to test?

If you use:

```java
@Value("${demo.greeting}")
private String greeting;
```

then a unit test instantiating the object with `new` undergoes no injection. You must create a Spring context, use test helper mechanisms, or change the design. With constructor injection, you can pass `"Hello test"` directly into the object, making tests simpler.

## 18. A complete configuration with all three injection styles

For a practical comparison, suppose `application.yml` has:

```yaml
demo:
  greeting: "Hello"
  retry-count: 4
  region: "local"
  feature-enabled: true
```

**Bean A — constructor:**

```java
@Component
public class ConstructorExample {

    private final String greeting;

    public ConstructorExample(
            @Value("${demo.greeting}") String greeting) {
        this.greeting = greeting;
    }

    public String value() {
        return greeting;
    }
}
```

**Bean B — field:**

```java
@Component
public class FieldExample {

    @Value("${demo.retry-count:3}")
    private int retryCount;

    public int value() {
        return retryCount;
    }
}
```

**Bean C — method:**

```java
@Component
public class MethodExample {

    private String region;
    private boolean enabled;

    @Autowired
    public void configure(
            @Value("${demo.region:unknown}") String region,
            @Value("${demo.feature-enabled:false}") boolean enabled) {
        this.region = region;
        this.enabled = enabled;
    }

    public String region() {
        return region;
    }

    public boolean enabled() {
        return enabled;
    }
}
```

Required imports for these compact examples:

```java
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;
```

Create a runner:

```java
@Component
public class ThreeWaysRunner implements ApplicationRunner {

    private final ConstructorExample constructorExample;
    private final FieldExample fieldExample;
    private final MethodExample methodExample;

    public ThreeWaysRunner(
            ConstructorExample constructorExample,
            FieldExample fieldExample,
            MethodExample methodExample) {
        this.constructorExample = constructorExample;
        this.fieldExample = fieldExample;
        this.methodExample = methodExample;
    }

    @Override
    public void run(ApplicationArguments args) {
        System.out.println(constructorExample.value());
        System.out.println(fieldExample.value());
        System.out.println(methodExample.region());
        System.out.println(methodExample.enabled());
    }
}
```

With imports:

```java
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.stereotype.Component;
```

If the classes are placed where component scan detects them and no other source overrides them, illustrative output is:

```text
Hello
4
local
true
```

Three different writing styles, yet **all resolve properties from Spring Environment**. Which injection style you pick depends on class design intent and bean lifecycle.

## 19. Common mistakes

### 19.1. Forgetting to declare the bean

Putting `@Value` on a field of a class instantiated manually with `new` does not cause Spring to inject it. Let Spring manage the object or use a constructor taking explicit values.

### 19.2. Writing invalid placeholder syntax

Incorrect:

```java
@Value("demo.greeting")
private String greeting;
```

This is the literal string `demo.greeting`, not a property lookup request.

Correct:

```java
@Value("${demo.greeting}")
private String greeting;
```

With default:

```java
@Value("${demo.greeting:Hello}")
private String greeting;
```

### 19.3. Mixing up property names and values

If the YAML file specifies:

```yaml
demo:
  retry-count: 5
```

but Java requests `${demo.max-retries}`, those are two different keys. Ensure the referenced property name is exact, preferring canonical kebab-case.

### 19.4. Missing a required property

`@Value("${demo.required}")` has no default. If no source supplies a value, bean creation can fail. Do not fix this by adding a dummy default if the property is genuinely required; it is better to supply the needed configuration and surface a clear setup error.

### 19.5. Failing to convert types

If using:

```java
@Value("${demo.retry-count}")
private int retryCount;
```

while configuration contains:

```yaml
demo:
  retry-count: "many"
```

then `"many"` is not a valid integer. Fix the input or change the expected data type.

### 19.6. Reading a field before Spring injects it

With field injection, the constructor runs before the field injection step. If constructor logic depends on the property, switch to constructor injection.

### 19.7. Assuming @Value refreshes configuration automatically

Editing a YAML file while the application is running does not update `@Value` fields on default singleton beans. Restart or design an explicit dynamic configuration solution if needed.

### 19.8. Assuming @Value only reads application.yml

Actual values can come from command-line arguments, system properties, environment variables, profile-specific documents, or other Config Data. Inspect `Environment` when results do not match predictions.

### 19.9. Assuming @Value on an arbitrary method runs on every invocation

Spring processes method injection points during the bean lifecycle. The annotation does not turn an ordinary Java method into a function that re-queries properties every time a caller invokes it.

### 19.10. Using @Value for too many related keys

A class with dozens of `@Value` annotations for HTTP configuration, timeouts, connections, retries, and security is usually hard to read and hard to change. As the number of properties grows, consider creating a corresponding `@ConfigurationProperties` object.

## 20. Diagnosing when injected values do not match expectations

### Step 1: confirm the bean is managed by Spring

Check that the class has `@Component` or is registered via `@Bean`, and lies within component scan scope. If the object is created manually, injection will not occur.

### Step 2: check @Value syntax

Example:

```java
@Value("${demo.greeting:Hello}")
```

Must have `${...}` if you want a placeholder. If you need a SpEL expression, use `#{...}`.

### Step 3: check whether the property exists

Use `Environment` to observe the effective value:

```java
@Component
public class ValueInspector implements ApplicationRunner {

    private final Environment environment;

    public ValueInspector(Environment environment) {
        this.environment = environment;
    }

    @Override
    public void run(ApplicationArguments args) {
        System.out.println(environment.getProperty("demo.greeting"));
    }
}
```

Corresponding imports:

```java
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;
```

If `Environment#getProperty` has no value and `@Value` has a default, the bean receives the default per placeholder syntax. If `@Value` has no default, bean creation can fail.

### Step 4: check higher-precedence sources

Check whether `--demo.greeting=...` appears in the launch command or IDE Run Configuration. Check Java system properties, environment variables, and profile-specific files.

### Step 5: check lifecycle ordering

If a value is null inside the constructor of a bean using field injection, that is a sign the field is being read too early. Use constructor injection or move the logic after the injection step.

### Step 6: check data types

If the bean fails to create due to type conversion, verify whether the actual value has the right format for `int`, `boolean`, or another type. For numeric values, avoid strings like `"three"` when expecting `int`.

### Step 7: avoid exposing sensitive information

Only use non-sensitive demo keys for logging. Never print passwords, tokens, or private information just to debug source ordering.

## 21. Reinforcement exercises

### Exercise A: determine injected values

Given:

```yaml
demo:
  greeting: "From YAML"
  retry-count: 2
```

And:

```java
@Component
public class DemoSettings {

    private final String greeting;
    private final int retryCount;

    public DemoSettings(
            @Value("${demo.greeting:Default}") String greeting,
            @Value("${demo.retry-count:3}") int retryCount) {
        this.greeting = greeting;
        this.retryCount = retryCount;
    }

    public String getGreeting() {
        return greeting;
    }

    public int getRetryCount() {
        return retryCount;
    }
}
```

Question: with only the YAML above, what do `getGreeting()` and `getRetryCount()` return?

Answer:

```text
From YAML
2
```

Defaults `Default` and `3` are not used because YAML already provides the properties.

### Exercise B: command-line override

Using the same configuration, launch:

```bash
java -jar app.jar --demo.greeting=FromCLI --demo.retry-count=8
```

Answer:

```text
FromCLI
8
```

Application arguments have higher precedence than Config Data in the example.

### Exercise C: field injection and new

Consider:

```java
@Component
class FeatureFlag {

    @Value("${demo.feature-enabled:true}")
    private boolean enabled;

    boolean isEnabled() {
        return enabled;
    }
}
```

If you call `new FeatureFlag().isEnabled()` outside Spring, is the result guaranteed to be `true`?

**No.** The object is not injected by Spring; Java's default initial value for a boolean field is `false`. The placeholder fallback `true` only takes effect when Spring's injection mechanism processes the injection point.

### Exercise D: distinguishing field and constructor

Why should the following snippet not be used?

```java
@Component
class EarlyRead {

    @Value("${demo.greeting}")
    private String greeting;

    EarlyRead() {
        System.out.println("Greeting = " + greeting);
    }
}
```

Because field injection occurs after Java invokes the constructor. If you need the value right inside the constructor, pass it via a parameter annotated with `@Value`.

### Exercise E: fixing an injection method

Start with:

```java
@Component
class RegionSettings {

    private String region;
    private int maxItems;
}
```

Write a `configure(...)` method so Spring injects `demo.region` (default `local`) and `demo.max-items` (default `50`).

One way:

```java
@Autowired
public void configure(
        @Value("${demo.region:local}") String region,
        @Value("${demo.max-items:50}") int maxItems) {
    this.region = region;
    this.maxItems = maxItems;
}
```

This snippet places `@Autowired` on the method and `@Value` on the parameters.

## 22. Key takeaways

- `@Value` injects **single values** resolved from Spring `Environment` or expressions into a bean injection point.
- **Constructor injection** receives values when the object is created, fits required values and `final` fields, and is usually the preferred choice.
- **Field injection** is concise yet depends on Spring processing the bean after construction, making testing and state control harder.
- **Method/setter injection** lets Spring call an injection method after object creation; you can place `@Autowired` on the method and `@Value` on its parameters.
- `${key}` is a placeholder; `${key:default}` adds a fallback value; `#{...}` is a SpEL expression.
- Injection does not automatically apply to objects instantiated with `new` outside Spring, and is unsuitable for static fields.
- Injected values can come from any effective property source, not necessarily `application.yml`.
- `@Value` does not automatically refresh values when configuration sources change while the application is running.
- For large, nested, or validation-requiring configuration groups, consider `@ConfigurationProperties`.