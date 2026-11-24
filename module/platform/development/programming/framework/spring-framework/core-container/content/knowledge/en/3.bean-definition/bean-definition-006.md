# Configuration Values and References Between Beans — Spring Framework Core Container

## 1. Objective: Values and References Are Not the Same Concept

When creating a bean in Spring, sometimes you need to pass **configuration data** such as a channel name, URL, retry count, notification prefix, or timeout. Other times, you need to wire that bean to **another bean** managed by Spring. Both needs can appear together in a constructor, factory method, or setter, yet they must be clearly distinguished:

- **Configuration value:** String, numeric, boolean, enum, URI, or suitable value-object data. It can be a literal or retrieved from `Environment`/property sources.
- **Bean reference:** instructs Spring to retrieve a **bean object** by name or resolve a type-compatible dependency to pass to the current bean.
- **Bean name:** string identifier for a bean in the registry. The name string itself **does not automatically become an object reference** if passed merely as a String property.
- **BeanDefinition:** metadata describing how Spring creates and configures a bean, which can hold **literal values** and **`RuntimeBeanReference`** entries before the actual objects are assembled.

After this lesson, you will be able to:

1. Distinguish values, references, bean names, bean definitions, and managed objects.
2. Use `@Bean`, constructor injection, and `Environment.getRequiredProperty(...)`.
3. Register definitions using `BeanDefinitionBuilder.addPropertyValue(...)` and `addPropertyReference(...)`.
4. Inspect `RuntimeBeanReference` metadata before verifying the actual injected object.
5. Understand the roles of `@Value`, `@PropertySource`, constructor arguments, property conversion, and property source ordering.
6. Handle errors involving missing keys, missing beans, wrong setters/types, and multiple candidates.
7. Run a standalone **Java 17+** Spring Framework program, verifying Maven/`javac`/`java` and stdout.

**Scope:** focuses on how the Spring Core Container supplies **configuration values** and **bean-to-bean references**. No Spring Boot, MVC, database, or distributed configuration system is required.

## 2. A Small Graph with Two Types of Edges

A notification application has two components:

- `MessageGateway` needs the **value** `notify.channel = MAIL`.
- `NotificationService` needs the `MessageGateway` **bean object** and the **value** `notify.prefix = Xin chao`.
- `ManualSender` needs the value `label = manual` along with a reference to the `messageGateway` bean.

~~~mermaid
flowchart LR
    E1["Environment: notify.channel=MAIL"] -->|"String value"| G["Bean: messageGateway"]
    E2["Environment: notify.prefix=Xin chao"] -->|"String value"| N["Bean: notificationService"]
    G -->|"Bean object"| N
    V["BeanDefinition: label=manual"] -->|"Literal"| M["Bean: manualSender"]
    G -->|"Bean reference"| M
~~~

| Input | What Spring/Java Does | Result |
| --- | --- | --- |
| Literal string `"manual"` | Assigns to a `String`-typed property | A value, not a bean |
| `Environment.getRequiredProperty("notify.prefix")` | Looks up key in property sources | String `"Xin chao"` |
| `MessageGateway gateway` parameter on `@Bean` | Resolves matching bean candidate | Managed `MessageGateway` object |
| `addPropertyReference("gateway", "messageGateway")` | Looks up registry, resolves reference | Bean object to pass to setter |
| `RuntimeBeanReference.getBeanName()` | Reads metadata | Target bean name, not the object itself |

**Semantic note:** both `"MAIL"` and `"messageGateway"` can be written as strings in configuration, yet the first string is business/configuration data, while the second serves as a **reference address** when passed into the `addPropertyReference` API.

## 3. Passing Values and Bean Objects via `@Bean` Factory Methods

JavaConfig can be written as:

~~~java
@Configuration(proxyBeanMethods = false)
class AppConfig {
    @Bean
    MessageGateway messageGateway(Environment environment) {
        return new MessageGateway(
                environment.getRequiredProperty("notify.channel"));
    }

    @Bean
    NotificationService notificationService(
            MessageGateway gateway, Environment environment) {
        String prefix =
                environment.getRequiredProperty("notify.prefix");
        return new NotificationService(gateway, prefix);
    }
}
~~~

**This is an illustrative snippet**, without imports or type definitions. The complete Java file is in Section 5.

- The `Environment` parameter is a capability Spring can supply when calling a factory method; you use it to read data from property sources.
- The `MessageGateway gateway` parameter is an **object dependency**, requiring a matching bean instance in the container.
- `NotificationService` receives both `gateway` (object) and `prefix` (String) via its constructor; it does not need to know property keys directly or call the container.
- `@Configuration(proxyBeanMethods = false)` is appropriate when `@Bean` methods do not call each other directly. If you manually call `messageGateway(env)` inside another method, that is a plain Java call and may create an object outside the intended singleton bean.

### Must Every Value Come from `Environment`?

No. A simple configuration can contain:

~~~java
@Bean
MessageGateway messageGateway() {
    return new MessageGateway("MAIL");
}
~~~

The string `"MAIL"` is a valid literal value. However, if the channel differs across environments, using `Environment` or an external configuration source avoids editing factory code for each deployment.

A plain value like `"MAIL"` does not need to be registered as its own separate bean unless you have a **value object/managed contract** that genuinely adds value.

## 4. `BeanDefinitionBuilder`: Distinguishing Property Value from Property Reference

The same idea can be expressed programmatically via metadata:

~~~java
BeanDefinition senderDefinition = BeanDefinitionBuilder
        .genericBeanDefinition(ManualSender.class)
        .addPropertyValue("label", "manual")
        .addPropertyReference("gateway", "messageGateway")
        .getBeanDefinition();

context.registerBeanDefinition("manualSender", senderDefinition);
~~~

**Snippet**, requiring `ManualSender` with a no-argument constructor and two matching setters. It is not a standalone Java file yet.

The two builder methods are not equivalent:

- `addPropertyValue("label", "manual")` stores a literal so the container assigns the value to the `setLabel(String)` setter.
- `addPropertyReference("gateway", "messageGateway")` stores a **reference to a bean**; when creating `manualSender`, Spring resolves the bean by name and passes the object into the `setGateway(MessageGateway)` setter.

A common mistake:

~~~java
.addPropertyValue("gateway", "messageGateway")
~~~

This is **not** the right way to ask Spring to inject the managed `MessageGateway`. It supplies a String literal to a property expecting an object of type `MessageGateway`; the standard conversion system does not automatically turn an arbitrary bean name into the desired reference. Use `addPropertyReference(...)`.

### `RuntimeBeanReference` Is Metadata, Not the Bean Object

It can be read back:

~~~java
BeanDefinition definition =
        context.getBeanFactory().getBeanDefinition("manualSender");
PropertyValue reference =
        definition.getPropertyValues().getPropertyValue("gateway");

RuntimeBeanReference ref =
        (RuntimeBeanReference) reference.getValue();
System.out.println(ref.getBeanName()); // messageGateway
~~~

This is an illustrative snippet requiring imports for `PropertyValue` and `RuntimeBeanReference`; the complete example later includes those imports.

When Spring **has not yet assigned properties**, the definition can hold `RuntimeBeanReference` metadata. After instance creation, `manualSender.gateway()` must be a real **object**. To verify wiring thoroughly, inspect both the definition and runtime identity/behavior.

### Setter Injection Differs from Constructor Injection

The builder code here intentionally uses setters to clearly demonstrate `addPropertyValue` and `addPropertyReference`. Setter injection fits when configurable properties have a clear configuration contract; however, **constructor injection is usually preferable for required dependencies**, because the created instance already has its required collaborators. You can also specify constructor args in the builder:

~~~java
BeanDefinition definition = BeanDefinitionBuilder
        .genericBeanDefinition(AlertWorker.class)
        .addConstructorArgValue("batch")
        .addConstructorArgReference("messageGateway")
        .getBeanDefinition();
~~~

This is a **non-standalone illustrative snippet**: `AlertWorker` is not defined, and it requires a compatible constructor such as `AlertWorker(String mode, MessageGateway gateway)`. Semantically, `addConstructorArgValue` passes a literal; `addConstructorArgReference` requires resolving a bean object.

## 5. Runnable Java 17+ Project with `@Bean` and `BeanDefinitionBuilder`

Uses **Spring Framework 6.2.19**, JDK 17+, and Maven. The version is pinned for the example, **not claimed to be the latest Spring release**. No Spring Boot, web server, or database is required.

~~~text
bean-values-references-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── BeanValuesReferencesDemo.java
~~~

### 5.1. `pom.xml`

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>bean-values-references-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.19</version>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.14.1</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.1</version>
                <configuration>
                    <mainClass>demo.BeanValuesReferencesDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

The `spring-context` module pulls in the relevant Spring dependencies. When running `javac` directly, the classpath must include all those JARs; you cannot simply pass the Java source file to the compiler and expect it to locate Spring automatically.

### 5.2. `BeanValuesReferencesDemo.java`

Create `src/main/java/demo/BeanValuesReferencesDemo.java`:

~~~java
package demo;

import java.util.Map;
import java.util.Objects;

import org.springframework.beans.PropertyValue;
import org.springframework.beans.factory.config.BeanDefinition;
import org.springframework.beans.factory.config.RuntimeBeanReference;
import org.springframework.beans.factory.support.BeanDefinitionBuilder;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.Environment;
import org.springframework.core.env.MapPropertySource;

public final class BeanValuesReferencesDemo {
    private BeanValuesReferencesDemo() {}

    public static final class MessageGateway {
        private final String channel;

        public MessageGateway(String channel) {
            this.channel = Objects.requireNonNull(channel);
        }

        public String channel() {
            return channel;
        }
    }

    public static final class NotificationService {
        private final MessageGateway gateway;
        private final String prefix;

        public NotificationService(MessageGateway gateway, String prefix) {
            this.gateway = Objects.requireNonNull(gateway);
            this.prefix = Objects.requireNonNull(prefix);
        }

        public MessageGateway gateway() {
            return gateway;
        }

        public String notification(String name) {
            return prefix + " " + name + " (" + gateway.channel() + ")";
        }
    }

    public static final class ManualSender {
        private String label;
        private MessageGateway gateway;

        public ManualSender() {}

        public void setLabel(String label) {
            this.label = Objects.requireNonNull(label);
        }

        public void setGateway(MessageGateway gateway) {
            this.gateway = Objects.requireNonNull(gateway);
        }

        public MessageGateway gateway() {
            return gateway;
        }

        public String send(String name) {
            return label + ":" + gateway.channel() + ":" + name;
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class AppConfig {
        @Bean
        public MessageGateway messageGateway(Environment env) {
            return new MessageGateway(
                    env.getRequiredProperty("notify.channel"));
        }

        @Bean
        public NotificationService notificationService(
                MessageGateway gateway, Environment env) {
            return new NotificationService(gateway,
                    env.getRequiredProperty("notify.prefix"));
        }
    }

    public static void main(String[] args) {
        AnnotationConfigApplicationContext context =
                new AnnotationConfigApplicationContext();

        try (context) {
            context.getEnvironment().getPropertySources().addFirst(
                    new MapPropertySource("lessonProperties",
                            Map.<String, Object>of(
                                    "notify.channel", "MAIL",
                                    "notify.prefix", "Xin chao")));

            context.register(AppConfig.class);

            BeanDefinition senderDefinition = BeanDefinitionBuilder
                    .genericBeanDefinition(ManualSender.class)
                    .addPropertyValue("label", "manual")
                    .addPropertyReference("gateway", "messageGateway")
                    .getBeanDefinition();

            context.registerBeanDefinition("manualSender", senderDefinition);
            context.refresh();

            MessageGateway gateway = context.getBean(MessageGateway.class);
            NotificationService service =
                    context.getBean(NotificationService.class);
            ManualSender manual = context.getBean(ManualSender.class);

            BeanDefinition stored =
                    context.getBeanFactory()
                            .getBeanDefinition("manualSender");
            PropertyValue label =
                    stored.getPropertyValues().getPropertyValue("label");
            PropertyValue gatewayReference =
                    stored.getPropertyValues().getPropertyValue("gateway");
            RuntimeBeanReference ref =
                    (RuntimeBeanReference) gatewayReference.getValue();

            System.out.println("propertyPrefix=" +
                    context.getEnvironment().getProperty("notify.prefix"));
            System.out.println("gatewayChannel=" + gateway.channel());
            System.out.println("literalValue=" + label.getValue());
            System.out.println("referenceBean=" + ref.getBeanName());
            System.out.println("sameGateway=" +
                    (service.gateway() == gateway
                     && manual.gateway() == gateway));
            System.out.println("notification=" +
                    service.notification("Lan"));
            System.out.println("manualSend=" + manual.send("Lan"));
            System.out.println("senderSingleton=" +
                    (manual == context.getBean(ManualSender.class)));
        }
    }
}
~~~

**Self-containment of the example:** one public top-level class matching the filename, with suitable nested types. `Map.<String, Object>of(...)` creates a property source with the appropriate map type; supported in Java 17. Bean definitions and the property source are registered **before `refresh()`**.

`MessageGateway` is configured from the value `"MAIL"`; `NotificationService` takes one reference and one value; `ManualSender` receives a literal via `setLabel` and a bean object via `setGateway`. The program compares metadata and runtime so these two layers are not confused.

### 5.3. Running with Maven

In the `bean-values-references-demo` directory:

~~~bash
java -version
javac -version
mvn -version
mvn -q clean compile exec:java
~~~

**Exact eight lines of stdout printed by `main` upon a successful run:**

~~~text
propertyPrefix=Xin chao
gatewayChannel=MAIL
literalValue=manual
referenceBean=messageGateway
sameGateway=true
notification=Xin chao Lan (MAIL)
manualSend=manual:MAIL:Lan
senderSingleton=true
~~~

JDK/Maven version lines and Maven logs may appear depending on the machine and are **not** part of the eight lines printed by the demo code. The example does not rely on randomness, clocks, or iteration order to determine its output.

### 5.4. Compiling and Running Directly with `javac`/`java`

Generate the dependency classpath using Maven:

~~~bash
mvn -q dependency:build-classpath -Dmdep.outputFile=classpath.txt
~~~

**Linux/macOS (bash/zsh):**

~~~bash
mkdir -p out
javac --release 17 -encoding UTF-8 \
  -cp "$(cat classpath.txt)" \
  -d out src/main/java/demo/BeanValuesReferencesDemo.java
java -cp "out:$(cat classpath.txt)" demo.BeanValuesReferencesDemo
~~~

**Windows PowerShell:**

~~~powershell
$deps = (Get-Content -Raw classpath.txt).Trim()
New-Item -ItemType Directory -Force out | Out-Null
javac --release 17 -encoding UTF-8 -cp "$deps" -d out src/main/java/demo/BeanValuesReferencesDemo.java
java -cp "out;$deps" demo.BeanValuesReferencesDemo
~~~

The classpath separator is `:` on Unix and `;` on Windows. Running `javac` without the Spring JARs causes compilation errors such as `package org.springframework... does not exist`, not proof of bad bean configuration.

## 6. Interpreting the Eight Output Lines

| Output | Conclusion |
| --- | --- |
| `propertyPrefix=Xin chao` | `Environment` supplied the String from the property source |
| `gatewayChannel=MAIL` | The Gateway bean was created with the `notify.channel` value |
| `literalValue=manual` | BeanDefinition stores the literal property value |
| `referenceBean=messageGateway` | BeanDefinition stores the target bean name via `RuntimeBeanReference` |
| `sameGateway=true` | Both consumers are wired to the **exact same singleton bean object** |
| `notification=Xin chao Lan (MAIL)` | Service combines a data value and a bean collaborator |
| `manualSend=manual:MAIL:Lan` | Setters for the value and reference were applied |
| `senderSingleton=true` | Same bean name/type in one context yields the same singleton instance |

Looking only at `referenceBean=messageGateway` only tells you **which bean the metadata points to**; `sameGateway=true` verifies the collaborator object at runtime. BeanDefinition is not synonymous with bean instance.

## 7. `Environment`, Property Sources, and Precedence Order

Spring `Environment` aggregates multiple property sources such as system properties, environment variables, or property sources registered by the application. **Which source wins on key collisions** is part of configuration policy.

In the program, the code:

~~~java
context.getEnvironment().getPropertySources().addFirst(
        new MapPropertySource("lessonProperties",
                Map.<String, Object>of(
                        "notify.channel", "MAIL",
                        "notify.prefix", "Xin chao")));
~~~

places the demo data at the front of the list, so even if the machine has matching keys in another source, the two in-memory values still take precedence. This is a **decision for reproducibility**, not a recommendation that real applications should always override all deployment settings.

### Externalizing Properties to a File

Another application could use `src/main/resources/app.properties`:

~~~properties
notify.channel=MAIL
notify.prefix=Xin chao
~~~

And register the resource:

~~~java
@Configuration
@PropertySource("classpath:app.properties")
class AppConfig {
    // Necessary @Bean factory methods.
}
~~~

**This is an illustration, not a second version of the runnable file.** To run it, you must create the properties file and write the complete config. `@PropertySource` requires an existing resource; the annotation alone does not conjure data out of thin air.

### `@Value` Instead of `Environment` at Certain Injection Points

Another way to express it:

~~~java
@Bean
NotificationService notificationService(
        MessageGateway gateway,
        @Value("${notify.prefix}") String prefix) {
    return new NotificationService(gateway, prefix);
}
~~~

This snippet only illustrates syntax and requires a context configured for placeholder resolution. `@Value` can inject values from property placeholders or expressions according to the Spring environment. In the runnable lesson, `Environment.getRequiredProperty` is used so that **a missing required key fails clearly**, without depending on how unresolved placeholders might be handled under different configurations.

There is no need to turn every property into a `@Bean String` just to use it in a factory method.

## 8. Bean Reference by Name vs. Injection by Type

There are two different configuration styles:

- `@Bean NotificationService notificationService(MessageGateway gateway, ...)`: requests a candidate by **type** and autowiring rules.
- `addPropertyReference("gateway", "messageGateway")`: the reference is specified **by bean name** in metadata.

When **two beans share the same type**, such as `messageGatewayA` and `messageGatewayB`, single-valued type-based injection cannot choose one candidate on its own. Spring provides mechanisms:

- `@Qualifier("messageGatewayA")` when the injection point requires a specific bean.
- `@Primary` when a default candidate is needed for a clear reason.
- Bean name at the composition root, such as `context.getBean("messageGatewayA", MessageGateway.class)`.
- Collection injection or `ObjectProvider<MessageGateway>` when multiple candidates or flexible retrieval are genuinely needed.

Do not interpret "two beans of the same type" as a Java error; the issue is that **the injection point needs one object that Spring cannot disambiguate yet**.

If metadata references a non-existent bean, Spring will fail when creating the object that needs that reference. It **does not fall back to using the bean name String as a value**.

## 9. Value Conversion and Configuration Data Validation

Not every configuration value remains a String in the final object. For example:

~~~java
int retries =
        environment.getRequiredProperty("notify.retries", Integer.class);
~~~

This is a valid snippet in a method with an `Environment environment` variable and that key provided. Spring can convert numeric string values into `Integer` via appropriate conversion; if the key is missing or cannot be converted, an exception is typically thrown. **Successful conversion does not prove the data is valid for business rules.**

Important rules:

- **Required value:** fail fast when missing; do not silently fall back to defaults that mask deployment errors.
- **Optional value:** only use a default when the contract permits missing configuration.
- **Validation:** verify timeout > 0, non-blank channel name, valid address, retry count within bounds; throw clear exceptions at the configuration boundary.
- **Type clarity:** a String property holding a bean name does not automatically become a reference; use the proper API.
- **Secrets:** avoid writing tokens/passwords into real READMEs, source code, or stdout. Use an appropriately managed secrets configuration source.
- **Runtime changes:** updating a property source after singletons have already been created does not automatically re-inject or rebuild those objects; an intentional dynamic reconfiguration mechanism is needed if runtime changes are desired.

With `BeanDefinitionBuilder.addPropertyValue`, Spring can also apply type conversion when setting properties; however, do not expect it to infer a dependency object from a bean name string when the programmer did not create a reference.

## 10. Scope and Lifecycle Related to References

| Case | Typical Behavior |
| --- | --- |
| Default singleton Gateway | Service and ManualSender in the demo receive the same object |
| Prototype Gateway | Each time the container creates/supplies a prototype on request, it can be a different instance |
| Prototype injected directly into singleton | Normally resolved **once when the singleton is created**, not creating a new object on every method call |
| Lazy bean | Bean creation can be deferred; dependency logic still applies |
| Reference to an alias | Alias resolves to the named target bean; does not create a new definition |
| Bean created with `new` outside container | Does not automatically receive Spring DI/lifecycle |
| Closed context | Do not use the context as a source for retrieving new beans |

If the service genuinely wants a fresh Gateway on every call, design a provider/lookup according to the appropriate scope, **do not merely change Gateway to prototype and store the reference permanently inside a singleton**.

A constructor/factory dependency cycle A→B→A indicates an architectural problem; switching a reference from type-based to a String bean name does not resolve the cycle.

## 11. Common Errors

| Error / Symptom | Likely Cause | How to Check |
| --- | --- | --- |
| `getRequiredProperty(...)` fails | Missing required key or property source not loaded | Check key, source precedence, profile |
| Property in wrong format | Cannot convert to setter/constructor type | Check type/converter and validation |
| `NoSuchBeanDefinitionException` | Bean name in reference not registered | Check `messageGateway` and registration |
| `UnsatisfiedDependencyException` | Factory/constructor needs a bean Spring cannot supply | Check type, qualifier, scan, config |
| `NoUniqueBeanDefinitionException` | Multiple candidates of same type, no unique selection | Use qualifier/primary or fix wiring |
| `NotWritablePropertyException` | Programmatic property lacks matching setter name/type | Check JavaBean getter/setter and public visibility |
| Passing `addPropertyValue("gateway","messageGateway")` | Confused name string with bean reference | Use `addPropertyReference` |
| Setter appears not to run | Instance not yet created, lazy bean, or wrong property name | Retrieve bean/read creation errors, check setters |
| `@Value` does not resolve property as intended | Missing property source or placeholder configurer | Check Environment and placeholder resolution |
| Programmatic registration after refresh | Metadata not processed at the intended time | Register before `refresh()` |
| New runtime value has no effect | Singleton already created with old value | Use a supported reconfiguration mechanism |
| `package org.springframework... does not exist` | Maven/`javac` classpath lacks Spring | Check pom and classpath |
| Mutable singleton bean exhibits race conditions | Multiple callers share one instance | Design thread-safety/appropriate scope |

How to debug: separate the **configuration layer (metadata)** from the **object layer (runtime)**. Ask *is this property a value or a reference?*, verify the exact key/bean name, check types/setters, trace `Caused by`, and compare against actual runtime objects.

## 12. Targeted Testing

**Unit test without Spring:** instantiate Gateway and NotificationService via constructor:

~~~java
MessageGateway gateway = new MessageGateway("TEST");
NotificationService service = new NotificationService(gateway, "Hello");
System.out.println(service.notification("An")); // Hello An (TEST)
~~~

This is a snippet inside a method/class with access to the nested types, not a standalone file. It tests Java logic without verifying bean registration.

**Configuration integration test:** build the Context like the main example, then:

- Assert that the label literal and gateway `RuntimeBeanReference` metadata are correct.
- Verify `service.gateway() == context.getBean(MessageGateway.class)`.
- Verify `manual.gateway()` is also the expected object.
- Test missing `notify.prefix` or missing `messageGateway` bean in a **separate test configuration**; do not break the happy-path demo and compare against the old stdout.
- Test property conversion/validation for required keys.

Do not use Java `assert` as a mandatory runtime guarantee because it is disabled by default without `-ea`. Use exceptions or test assertions that actually execute.

## 13. Self-Check Questions

**1.** Why is `addPropertyValue("gateway", "messageGateway")` not the same as `addPropertyReference("gateway", "messageGateway")`?

**Answer:** One only supplies a literal String, while the other instructs the container to resolve a managed bean by name and inject the object.

**2.** Why is the `MessageGateway gateway` parameter of `@Bean notificationService(...)` a bean reference even though it lacks the word `ref`?

**Answer:** Spring resolves factory method parameters according to type/autowiring rules and supplies the matching bean object.

**3.** What does `RuntimeBeanReference.getBeanName()` return, and how does it differ from the real object?

**Answer:** It returns the target bean name, here `"messageGateway"`. After `ManualSender` is created, its field holds the `MessageGateway` object, not the name string.

**4.** Does the `notify.prefix` value need to become a `String` bean?

**Answer:** No. The factory method can read the value directly from `Environment` and pass it into the constructor; create a separate value object/bean only when there is a design reason.

**5.** Why does the example use `MapPropertySource.addFirst`?

**Answer:** So the in-memory data has high priority, keeping output reproducible even if the machine defines a property with the same name. Real applications should design precedence policies per environment.

**6.** If Gateway is changed to prototype, is `sameGateway=true` still guaranteed?

**Answer:** No. Scope governs how instances are allocated; separate injections/lookups can receive different instances.

**7.** Why not call the `messageGateway(...)` factory method directly from `notificationService(...)` when `proxyBeanMethods=false` is set?

**Answer:** That is a plain Java call and can create an object other than the expected managed bean; use parameters so Spring resolves it.

## 14. Application Checklist

- [ ] Determine whether each input is a **value** or a **bean reference**.
- [ ] Name beans and properties clearly, without confusing bean names with data.
- [ ] Use Environment/PropertySource for appropriate externalized values.
- [ ] Use `getRequiredProperty` for required settings and perform domain validation.
- [ ] Use `@Bean` method parameters for managed collaborators.
- [ ] Use `addPropertyValue` for literals and `addPropertyReference` for bean objects.
- [ ] Ensure setters/constructors accept the right types and beans are registered.
- [ ] Register programmatic definitions before context refresh.
- [ ] Inspect `RuntimeBeanReference` in metadata and object identity after wiring.
- [ ] Handle missing beans or multiple beans with intentional registration and qualifiers/primary.
- [ ] Evaluate singleton/prototype/lazy scopes and their impact on identity.
- [ ] Run Java 17+ and match the **exact eight lines of stdout**.
- [ ] Provide the full Spring classpath for `javac`/`java`.
- [ ] Do not log secrets, do not use defaults to hide missing config, and do not ignore wiring errors.

**Remember:** a configuration value answers **"what data should be passed into the bean?"**, whereas a bean reference answers **"which managed object should this bean be wired to?"**. BeanDefinition stores both kinds of information distinctly; the container converts values and resolves references when creating objects. Seeing the **metadata ↔ instance** boundary clearly keeps Spring configuration explicit, safe, and testable.

### Official References

- [Spring Dependency Injection: Properties and Collaborators](https://docs.spring.io/spring-framework/reference/core/beans/dependencies/factory-collaborators.html)
- [Spring Environment Abstraction](https://docs.spring.io/spring-framework/reference/core/beans/environment.html)
- [Spring Java-based Container Configuration](https://docs.spring.io/spring-framework/reference/core/beans/java.html)
- [Spring BeanDefinition API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/beans/factory/config/BeanDefinition.html)
