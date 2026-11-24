# Bean Names, Aliases, and Return Types of @Bean Methods in the Spring Core Container

## Lesson Objectives

In the Spring Core Container, a method marked with `@Bean` declares a **bean definition** backed by a Java factory method. Three aspects that are very easy to confuse are:

1. **Bean name:** the primary identifier by which the container registers and looks up the bean.
2. **Alias:** one or more additional names pointing to the **same bean definition**, not independent beans.
3. **Return type of the `@Bean` method:** type metadata that Spring can use to predict candidates, resolve dependencies, and work with generics, AOP/proxies, or infrastructure components.

This lesson clearly explains how to declare and use each aspect, focusing on Java configuration with `@Configuration` and `@Bean`. You will learn when to keep the default name, when to specify an explicit name, how to distinguish an alias from two separate factory methods, how to choose the right return type, how to diagnose `NoSuchBeanDefinitionException`/`NoUniqueBeanDefinitionException`, and practice with a plain Java 17 + Spring Framework project.

**Principle:** The bean name defines **what the bean is called**; aliases define **other names for the same bean**; the return type expresses **the kind of object the factory method promises to provide**. They interact during dependency resolution, but do not substitute for one another.

## 1. What Does a @Bean Method Register?

Minimal example:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
class AppConfig {

    @Bean
    PaymentGateway paymentGateway() {
        return new DemoPaymentGateway();
    }
}
```

This is an **illustrative snippet**, requiring application-defined types `PaymentGateway` and `DemoPaymentGateway`. When `AppConfig` is registered in an `ApplicationContext`:

- Spring reads `@Bean` metadata on the `paymentGateway()` method.
- A bean definition is created for that factory method.
- By default, the bean is named `paymentGateway` (matching the method name).
- The type exposed by the method is `PaymentGateway`.
- When creating the bean according to scope/lifecycle, Spring invokes the factory method and manages the returned object.

The bean is not the Java method itself; the bean is the **object managed by Spring** per the bean definition. If you call `new AppConfig().paymentGateway()` outside the container, the result is a regular Java object that does not automatically receive lifecycle callbacks, dependency injection, or Spring post-processors.

This differs from registering two bean definitions: one `@Bean` method with two aliases still defines **one bean**, whereas two separate `@Bean` methods normally define **two beans** even if their return types are identical.

## 2. The Default Bean Name Is the @Bean Method Name

When neither `name` nor `value` is declared:

```java
@Configuration(proxyBeanMethods = false)
class PaymentConfig {

    @Bean
    PaymentGateway paymentGateway() {
        return new DemoPaymentGateway();
    }
}
```

Spring sets the default **bean name** to `paymentGateway`, identical to the Java method name. It can be looked up by name:

```java
// Illustrative snippet inside a scope that already has context.
PaymentGateway gateway =
        context.getBean("paymentGateway", PaymentGateway.class);
```

Points to remember:

- The bean name `paymentGateway` serves as the **container identifier**, not the class name `DemoPaymentGateway`.
- Renaming the Java method `paymentGateway()` to `createGateway()` while keeping an unnamed `@Bean` **changes the default bean name** to `createGateway`.
- If other configuration code or a library looks up the bean using the string `"paymentGateway"`, renaming the method can cause runtime errors even though the source still compiles.
- Dependency injection by type `PaymentGateway` can still work if Spring resolves a single candidate; the name is not always referenced directly by consumers.

**Difference from component scanning:** An unnamed `@Component` class is usually named by `AnnotationBeanNameGenerator` based on its class name; an unnamed `@Bean` uses the **factory method name**. Both rules may produce the same string in some cases, yet the metadata source differs.

### When to keep the default name?

If internal configuration is simple, with no string-based lookup or public bean-name contract, a readable method name is usually sufficient. Choose names such as `httpClient`, `orderRepository`, and `notificationSender` to reflect the bean's role.

If the bean name is documented as an integration contract — for example, a bean intended for another module using `@Qualifier("billingGateway")` — consider declaring an explicit name so refactoring the method does not accidentally break the contract.

## 3. Explicit Naming with @Bean(name) or @Bean(value)

`@Bean` has two attributes `name` and `value`, which are **aliases for each other in annotation metadata**. Several equivalent ways to specify a name:

```java
// Illustrative variants; choose only one for a factory method:

@Bean(name = "billingGateway")
PaymentGateway gateway() {
    return new DemoPaymentGateway();
}

@Bean(value = "billingGateway")
PaymentGateway gateway() {
    return new DemoPaymentGateway();
}

@Bean("billingGateway")
PaymentGateway gateway() {
    return new DemoPaymentGateway();
}
```

Do **not** put all three identical `gateway()` methods into the same class; they are syntactically equivalent alternatives. All three declare the bean name `billingGateway` even though the method name is `gateway`.

If an explicit name is declared, do not assume the old method name still works in `getBean(...)`. Given:

```java
@Bean("billingGateway")
PaymentGateway createGateway() {
    return new DemoPaymentGateway();
}
```

the primary name is `billingGateway`. Spring does **not automatically** add `createGateway` as an alias. If you need to support it as a secondary name, declare it in the name array or register an alias intentionally.

**Syntax note:** `@Bean(name = ...)` accepts `String[]`, so a single string is accepted by Java as a single-element array in annotation syntax. `@Bean("billingGateway")` is shorthand via the `value` attribute.

### @Bean(name) differs from @AliasFor

`@Bean.name` and `@Bean.value` are defined as aliases **between two annotation attributes** via Spring's `@AliasFor`. By contrast, `@Bean(name = {"main", "legacy"})` creates a **bean name and a bean-name alias in the BeanFactory**.

These two uses of the word "alias" operate at **two different levels**:

| Kind of alias | Example | Meaning |
| --- | --- | --- |
| Annotation attribute alias | `@Bean.name` and `@Bean.value` | Two attributes expressing the same configuration metadata |
| Bean name alias | `@Bean(name = {"main", "legacy"})` | Two lookup strings for the same bean definition/instance per scope |

Do not think that declaring both `name` and `value` creates two independent beans or serves as two distinct name lists.

## 4. Aliases in the @Bean(name = {...}) Array

When a `@Bean` method declares multiple name strings:

```java
@Bean(name = {"paymentGateway", "legacyGateway", "checkoutGateway"})
PaymentGateway paymentGatewayFactory() {
    return new DemoPaymentGateway();
}
```

Spring uses the **first element** as the primary name `paymentGateway`; the remaining strings are aliases `legacyGateway` and `checkoutGateway` for the **same bean**.

Example within a singleton container:

```java
// Illustration in code that already has context.
Object a = context.getBean("paymentGateway");
Object b = context.getBean("legacyGateway");
Object c = context.getBean("checkoutGateway");

System.out.println(a == b && b == c);
```

If the bean uses the default singleton scope and those names are declared as above, the output is:

```text
true
```

That does not mean Spring created three instances and merged them. All names resolve to the same bean definition, and singleton resolution yields the same reference.

### When to use aliases?

- **Backward compatibility:** an older module looks up `legacyGateway`, while a newer module switches to `paymentGateway`.
- **Dual naming for the same role:** one bean needs to be exposed under two deliberate API naming conventions.
- **Configuration migration:** renaming the primary name while still supporting the old name during a transition period.

Be cautious: the more aliases you have, the harder it is to tell which name is canonical; do not use aliases to mask genuine ambiguity between two different implementations.

### Aliases do not create extra beans of the same type

Suppose:

```java
@Bean(name = {"mainGateway", "oldMainGateway"})
PaymentGateway gateway() {
    return new DemoPaymentGateway();
}
```

When injecting a `PaymentGateway`, only **one bean definition** is declared by this method. The number of aliases does not give the container "two candidates of the same type". Meanwhile:

```java
@Bean("firstGateway")
PaymentGateway firstGateway() {
    return new DemoPaymentGateway();
}

@Bean("secondGateway")
PaymentGateway secondGateway() {
    return new DemoPaymentGateway();
}
```

are **two separate bean definitions**, which can produce two distinct singletons; injecting `PaymentGateway` without a qualifier can become ambiguous unless a selection rule exists.

### Bean names are unique within a BeanFactory

Primary names and aliases can collide with other names/aliases. A container cannot effectively use the same name for two different bean definitions without an override policy or valid alias registration. Depending on container type, version, and settings, duplicate names may be rejected or follow override rules; **do not** rely on `@Bean` method order assuming the last bean wins.

Use unique, business-meaningful names and test scenarios where multiple modules register beans with overlapping names.

## 5. Bean Names Differ from By-Type Bean Selection

When Spring injects a dependency:

```java
@Bean
CheckoutService checkoutService(PaymentGateway gateway) {
    return new CheckoutService(gateway);
}
```

Spring resolves `PaymentGateway` by **type and candidate selection rules**. The parameter name `gateway` is not a command that must always find a bean named `gateway`; the name can act as a fallback hint in certain candidate-selection situations, but it does not replace `@Qualifier` when a specific bean must be identified clearly.

### When only one bean matches the type

If only one autowirable `PaymentGateway` exists, Spring normally injects that bean regardless of whether the parameter is named `gateway` or `paymentClient`.

### When multiple beans share the same type

```java
@Configuration(proxyBeanMethods = false)
class MultiGatewayConfig {

    @Bean("fastGateway")
    PaymentGateway fastGateway() {
        return new FastPaymentGateway();
    }

    @Bean("safeGateway")
    PaymentGateway safeGateway() {
        return new SafePaymentGateway();
    }

    @Bean
    CheckoutService checkoutService(
            @Qualifier("safeGateway") PaymentGateway gateway) {
        return new CheckoutService(gateway);
    }
}
```

This is an **illustrative snippet requiring the corresponding application classes**. `@Qualifier("safeGateway")` makes the injection point require a candidate matching that qualifier/name; the Java method name `checkoutService` names the consumer bean, not the gateway.

You can mark `@Primary` on one bean as the preferred candidate when selecting a single bean by type. However, `@Primary` does not rename the bean or create an alias.

### Do not overuse parameter names

Spring has certain candidate-selection mechanisms based on a bean name matching a dependency name, depending on parameter/field name metadata and other conditions. That sometimes helps autowiring when multiple beans exist, yet it is fragile under refactoring. When selection carries business meaning, use an **explicit `@Qualifier`**, a narrower interface, or a dedicated registry.

### Looking up by name and type together

```java
PaymentGateway gateway =
        context.getBean("safeGateway", PaymentGateway.class);
```

This method requires a bean with the **name** `safeGateway` and a **compatible type** `PaymentGateway`. If the name exists but the bean cannot be cast to the requested type, Spring reports a type error; knowing the right name does not turn an object into an arbitrary type.

## 6. The @Bean Return Type Is Important Metadata

A factory method declares a **Java return type**, for example:

```java
@Bean
PaymentGateway paymentGateway() {
    return new DemoPaymentGateway();
}
```

The actual bean is a `DemoPaymentGateway` instance, yet the declared type is **`PaymentGateway`**. Spring uses metadata about the `@Bean` method to predict the bean type at many stages **before the instance is instantiated**.

This has consequences:

- Injection points expecting `PaymentGateway` match the return type metadata.
- An injection point requiring `DemoPaymentGateway` may **not be recognized by Spring** during type prediction if the factory method only declares `PaymentGateway` and the instance has not yet been created.
- Once the bean is created, the container may learn more about its runtime type, yet early dependency resolution should not depend on a bean happening to be instantiated beforehand.
- Scope, proxying, factory objects, and generic metadata also affect how Spring sees types; do not equate the Java runtime class with the exposed bean type at every stage.

### Choosing an interface or concrete class return type?

| Declaration | Advantage | Caveat |
| --- | --- | --- |
| `PaymentGateway paymentGateway()` | Clean interface, encourages consumers to depend on abstraction | Does not advertise the concrete type in the method signature for early type matching |
| `DemoPaymentGateway paymentGateway()` | Spring has more specific metadata before creating the bean | Consumers do not have to inject by concrete class; avoid tight coupling |
| `Object paymentGateway()` | Very broad, little information | Makes it hard for the container to predict candidates; almost never appropriate |
| `Collection<Handler> handlers()` | Declares a single bean of a collection type | **One collection bean**, distinct from "multiple `Handler` beans" injected as a list |
| `FactoryBean<Product> productFactory()` | Declares a `FactoryBean` supplying products | Spring has a contract distinguishing **factory** and **product**; requires understanding `&name` syntax |

**Recommendation:** Declare a **return type specific enough for required injection points to resolve reliably**. This is not a rule that every factory method must return a concrete class; if the whole application depends only on `PaymentGateway`, returning that interface is completely sound. If you expect Spring to find the bean by a specific subtype **before creation**, consider declaring the subtype on the method or adjusting the injection design.

### Avoid casting everywhere

If a factory method returns `PaymentGateway` while the object is `DemoPaymentGateway`, casting in a consumer to call concrete-type methods increases coupling. It is usually better to extend the right interface contract or create a narrow capability interface instead of forcing multiple consumers to depend on the implementation.

## 7. Complete Java 17 + Spring Framework Example: Names, Aliases, Return Types

The following example runs with Java 17 and Maven using plain Spring Framework; no Spring Boot is required.

Verification goals:

1. An unnamed `@Bean` uses the **method name**.
2. `@Bean(name = {"mailClient", "legacyMailClient"})` registers **one bean and one alias**.
3. When a bean name is specified explicitly, the factory method name **does not automatically become an alias**.
4. A factory method can declare a concrete return type `SmtpClient` or an interface return type `DeliveryClient`.
5. `@Primary` selects the preferred bean for single-bean injection without renaming it and without removing other beans from collections.
6. `@Qualifier("smsClient")` selects an exact bean when two candidates implement the interface.

### 7.1. Create the project structure

```text
bean-name-return-type/
├── pom.xml
└── src/main/java/demo/BeanIdentityDemo.java
```

Create `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>bean-name-return-type</artifactId>
    <version>1.0-SNAPSHOT</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.18</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
            </plugin>
        </plugins>
    </build>
</project>
```

### 7.2. Java source code

Create `src/main/java/demo/BeanIdentityDemo.java`:

```java
package demo;

import java.util.Arrays;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Primary;

public class BeanIdentityDemo {

    interface DeliveryClient {
        String channel();
    }

    static final class SmtpClient implements DeliveryClient {
        @Override
        public String channel() {
            return "mail";
        }
    }

    static final class SmsClient implements DeliveryClient {
        @Override
        public String channel() {
            return "sms";
        }
    }

    static final class OrderNotifier {
        private final DeliveryClient client;

        OrderNotifier(DeliveryClient client) {
            this.client = client;
        }

        String notifyOrder(String orderId) {
            return client.channel() + ":" + orderId;
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class AppConfig {

        @Bean(name = {"mailClient", "legacyMailClient"})
        @Primary
        SmtpClient createMailClient() {
            return new SmtpClient();
        }

        @Bean("smsClient")
        DeliveryClient createSmsClient() {
            return new SmsClient();
        }

        @Bean
        OrderNotifier orderNotifier(
                @Qualifier("smsClient") DeliveryClient client) {
            return new OrderNotifier(client);
        }
    }

    public static void main(String[] args) {
        try (var context =
                     new AnnotationConfigApplicationContext(AppConfig.class)) {

            SmtpClient byMainName =
                    context.getBean("mailClient", SmtpClient.class);
            SmtpClient byAlias =
                    context.getBean("legacyMailClient", SmtpClient.class);
            SmtpClient byConcreteType =
                    context.getBean(SmtpClient.class);
            DeliveryClient byInterfaceType =
                    context.getBean(DeliveryClient.class);

            System.out.println("defaultName=" +
                    context.containsBean("orderNotifier"));
            System.out.println("methodNameIsBean=" +
                    context.containsBean("createMailClient"));
            System.out.println("aliasSame=" +
                    (byMainName == byAlias));
            System.out.println("concreteSame=" +
                    (byMainName == byConcreteType));
            System.out.println("primaryIsMail=" +
                    (byMainName == byInterfaceType));

            OrderNotifier notifier =
                    context.getBean(OrderNotifier.class);
            System.out.println("notifier=" +
                    notifier.notifyOrder("A42"));

            String[] names =
                    context.getBeanNamesForType(DeliveryClient.class);
            Arrays.sort(names);
            System.out.println("deliveryBeans=" +
                    Arrays.toString(names));
        }
    }
}
```

### 7.3. Compile and run

From the directory containing `pom.xml`, install JDK 17+ and Maven and run:

```bash
mvn -q compile exec:java -Dexec.mainClass=demo.BeanIdentityDemo
```

Output **printed by the program**, excluding Maven/Spring logs if the environment configures logging differently:

```text
defaultName=true
methodNameIsBean=false
aliasSame=true
concreteSame=true
primaryIsMail=true
notifier=sms:A42
deliveryBeans=[mailClient, smsClient]
```

### 7.4. Explanation of each result

**`defaultName=true`:** The `orderNotifier(...)` method has an unnamed `@Bean`, so the bean defaults to `orderNotifier`.

**`methodNameIsBean=false`:** `createMailClient()` declares explicit name `mailClient` and alias `legacyMailClient`. The method name `createMailClient` is **not** automatically registered as an extra bean name.

**`aliasSame=true`:** `mailClient` and `legacyMailClient` both point to the singleton bean definition of `SmtpClient`, so they return the same instance.

**`concreteSame=true`:** `createMailClient()` declares the return type `SmtpClient`. Spring recognizes and supplies this bean when looked up by concrete type `SmtpClient.class`. Lookups by type and primary name match within a singleton context.

**`primaryIsMail=true`:** Two beans implement `DeliveryClient`: `mailClient` and `smsClient`. `@Primary` on the mail factory method lets Spring pick mail when looking up an unqualified `DeliveryClient`. `@Primary` does not rename `mailClient` and does not discard `smsClient`.

**`notifier=sms:A42`:** The `orderNotifier` factory method takes a parameter marked `@Qualifier("smsClient")`. Even though mail is primary, the qualifier selects `smsClient` to construct `OrderNotifier`; the result is `sms:A42`.

**`deliveryBeans=[mailClient, smsClient]`:** `getBeanNamesForType(DeliveryClient.class)` returns the **primary bean names** of matching beans and does not list `legacyMailClient` as a separate bean. `Arrays.sort` guarantees output order by name rather than relying on bean registration order.

### 7.5. Self-verifying aliases with BeanFactory

Inside `main` of the example, you can add:

```java
// Addition inside the try block that already has the context variable:
boolean isAlias =
        context.getBeanFactory().isAlias("legacyMailClient");
System.out.println("recognizedAlias=" + isAlias);
```

Additional output:

```text
recognizedAlias=true
```

`isAlias` checks whether that name is registered as an alias of another bean name. Remember that `context.getBean("legacyMailClient")` and `context.getBean("mailClient")` being equal by reference for a singleton bean does not mean they are two bean definitions.

## 8. When Do Interface and Concrete Return Types Differ?

Consider two factory styles:

```java
@Bean("mailA")
DeliveryClient mailA() {
    return new SmtpClient();
}

@Bean("mailB")
SmtpClient mailB() {
    return new SmtpClient();
}
```

This is an illustrative snippet; **do not place these two beans alongside the existing beans in the main example without updating injection** because adding candidates can affect bean selection.

**At Java runtime**, both objects may be `SmtpClient` instances. Yet the metadata when the container reads the factory methods differs:

- `mailA()` declares `DeliveryClient`.
- `mailB()` declares `SmtpClient`.

If Spring needs to predict which bean can be injected into `SmtpClient` **before instantiation**, `mailB` is the clearer candidate because its method signature declares the concrete type. Do not expect `mailA` to be found as `SmtpClient` at every initialization point, even though the factory ultimately returns that subtype.

### Avoid assuming "Spring will inspect the return statement"

Spring does not always execute the factory method upfront just to learn the actual return type. Doing so could break lazy initialization, create resources prematurely, or create dependency cycles. In type prediction, the method signature is an important metadata source. Treat the method declaration as the **bean's contract**, not merely Java syntax for the compiler.

### Balancing abstraction and metadata

When consumers only need `DeliveryClient`, returning the interface is good design. When a bean provides specific features of `SmtpClient` and Spring must inject that subtype, you can:

1. Declare the concrete return type `SmtpClient` in the factory method.
2. Define a narrower meaningful interface instead of depending on a concrete class.
3. Use an explicit qualifier or bean name if the goal is selecting an implementation by role, **not** accessing concrete-class-specific methods.

Declaring a concrete return type does not force all consumers to inject the concrete type: they can still depend on `DeliveryClient`.

## 9. Return Types and Generic Types in Dependency Matching

Spring can use **generic type metadata** as a candidate filter condition. That is another reason to avoid raw types or `Object` in `@Bean` method signatures.

Example:

```java
// Illustrative snippets; must be placed inside a suitable @Configuration.
interface Codec<T> {
    T decode(byte[] input);
}

@Bean
Codec<String> stringCodec() {
    return bytes ->
            new String(bytes, java.nio.charset.StandardCharsets.UTF_8);
}

@Bean
Codec<byte[]> binaryCodec() {
    return byte[]::clone;
}
```

Both beans share the raw `Codec` interface, yet return type metadata distinguishes `Codec<String>` from `Codec<byte[]>`. A consumer declaring:

```java
// Illustrative snippet in another bean's constructor:
CodecRegistry(Codec<String> stringCodec) {
    this.stringCodec = stringCodec;
}
```

can use generics as a resolution criterion for `Codec<String>` when Spring preserves the corresponding type metadata.

### Why avoid returning raw Codec?

If you write:

```java
// Counter-example with poor metadata:
@Bean
@SuppressWarnings("rawtypes")
Codec codec() {
    return bytes -> "decoded";
}
```

the method does not declare the generic type argument. Spring has less information when selecting candidates for injection points expecting `Codec<String>` or `Codec<byte[]>`. Raw types also reduce Java type safety. Declare complete generic types whenever a BeanFactory must distinguish beans sharing a raw type.

### Factory method returning a Collection vs. collection injection

The following two declarations serve different purposes:

```java
@Bean
java.util.List<String> supportedChannels() {
    return java.util.List.of("mail", "sms");
}
```

This is **one bean** of type `List<String>`, created by a single factory method.

Conversely, a constructor taking:

```java
// Illustrative snippet in a Spring-managed bean:
Router(java.util.List<DeliveryClient> clients) {
    this.clients = clients;
}
```

normally asks Spring to aggregate **multiple `DeliveryClient` beans** into a collection on injection. Do not assume a factory method returning `List<DeliveryClient>` and Spring aggregating multiple `DeliveryClient` beans behave identically in every injection context; one is a collection bean, while the other is a set of candidate beans.

## 10. FactoryBean<T> Return Type Is a Special Case

Spring provides the `org.springframework.beans.factory.FactoryBean<T>` abstraction so a factory bean object is responsible for supplying a **product bean**. This is **not** the same concept as a regular `@Bean` method, even though both names contain "factory".

Conceptual example:

```java
// Illustration: ProductFactory is an application-written FactoryBean<Product>.
@Bean("product")
FactoryBean<Product> productFactory() {
    return new ProductFactory();
}
```

Things to know when using `FactoryBean<T>`:

- Looking up `context.getBean("product")` normally retrieves the **product** created/supplied by the `FactoryBean`.
- Looking up `context.getBean("&product")` retrieves the **FactoryBean object itself** (the `&` prefix is Spring's dereference convention).
- The generic `FactoryBean<Product>` and information from `getObjectType()` strongly affect **product type prediction**; if not declared properly, autowiring by product type may be hard to resolve before factory/product creation.
- `FactoryBean` has its own contract for `getObject()`, `getObjectType()`, and `isSingleton()`; do not deduce that products are newly created solely from the factory bean's scope without checking those methods.

This is an advanced API illustration, not a standalone program. When a custom `FactoryBean` is unnecessary, a simple `@Bean Product product()` is usually easier to understand. Do not add a `FactoryBean` merely to rename a bean or create an alias.

## 11. Return Type and Proxy/AOP/Lazy Resolution

A bean can be wrapped by Spring in a proxy when transactions, AOP, or certain scopes are enabled. Thus, **the runtime class obtained from the container may differ from the concrete class directly created by the factory method**. For example, a JDK dynamic proxy typically implements interfaces without extending the actual class. That is why constructor injection using a **stable interface** is usually more resilient than unnecessary concrete-class casts.

Distinguish between:

- **Declared return type** on the `@Bean` method.
- **Target class/instance** created by the factory method.
- **Exposed type** of the bean after Spring post-processes/proxies it at usage time.

When an injection point requires a concrete class while the bean is proxied by interface, bean lookup/casting may fail to match. Choose an interface as the primary contract or adjust the proxy strategy intentionally rather than relying on implementation details.

### @Lazy does not fix poor type metadata

`@Lazy` can defer singleton initialization, yet it does not restore generic/concrete type metadata lost because a factory method declared `Object` or a raw interface. On the contrary, a clear declared return type is even more important when Spring must choose candidates **before creating** a lazy object.

### @Primary and @Qualifier do not "fix" return types either

If a factory method declares `Object`, adding `@Primary` does not turn it into `PaymentGateway` in terms of Java type signature. `@Qualifier` filters candidates that Spring already considers eligible; if type metadata cannot be determined properly from the factory method, a qualifier has no magic to guarantee early subtype injection will succeed.

## 12. Role of Bean Names When Using @Qualifier

`@Qualifier` is commonly used on constructor parameters, fields, or `@Bean` method parameters. When a qualifier string matches a bean name, Spring can select the bean by that name.

```java
@Bean
NotificationService notificationService(
        @Qualifier("mailClient") DeliveryClient client) {
    return new NotificationService(client);
}
```

This snippet illustrates a `NotificationService` class that must be defined. It requests a `DeliveryClient` bean matching `mailClient`; it does not require the factory method's own name to be `mailClient`.

### Aliases can be used for lookup just like a valid bean name

```java
context.getBean("legacyMailClient");
```

retrieves the bean registered under primary name `mailClient` if `legacyMailClient` is an alias. During autowiring, matching qualifiers against names/aliases is also subject to Spring's candidate selection rules. **Prefer the stable primary name in new qualifiers** and use aliases for compatibility when needed, rather than spreading many nicknames across every consumer.

### @Primary does not turn an alias into a second bean

In `BeanIdentityDemo`, `@Primary` was placed on the method declaring `mailClient`. It attaches priority metadata to the **bean definition**, rather than picking the primary name alone while ignoring aliases; looking up `legacyMailClient` still points to that same bean.

## 13. Avoid Confusing @Bean Name with Spring BeanDefinition Identity

A bean definition holds metadata such as bean name, aliases, scope, qualifiers, and factory method. When `@Bean` creates a singleton, the BeanFactory also holds the corresponding singleton object.

You can visualize it as:

```text
BeanDefinition "mailClient"
    ├── factoryMethod = AppConfig.createMailClient()
    ├── exposedType = SmtpClient
    ├── primary = true
    └── aliases:
        └── "legacyMailClient"
                 |
                 v
         BeanFactory resolves
                 |
                 v
         same managed singleton
```

Contrast with:

```text
BeanDefinition "mailClient" ---> SmtpClient instance A
BeanDefinition "smsClient"  ---> SmsClient instance B
```

Two separate bean definitions may implement the same `DeliveryClient` interface, yet they have independent identities, scopes, lifecycles, and qualifiers. To test an **alias**, compare reference equality and/or call `isAlias`; to test **two independent beans**, inspect bean names by type and verify the respective definitions.

### Singleton identity is scoped to a single container

Two different contexts registering `@Bean("mailClient")` normally hold **independent singletons**:

```java
// Illustrative snippet with AppConfig already defined:
try (var a = new AnnotationConfigApplicationContext(AppConfig.class);
     var b = new AnnotationConfigApplicationContext(AppConfig.class)) {
    System.out.println(
            a.getBean("mailClient") == b.getBean("mailClient"));
}
```

Expected output:

```text
false
```

Because each `ApplicationContext` maintains its own singleton registry. A bean name identifies an object **within container scope**, and does not automatically make the instance a JVM-global singleton.

## 14. Naming When @Bean Has Same-Named Methods or Inheritance

### Avoid unintentional factory method overloading

Java permits overloading:

```java
// Illustrative counter-example; do not place in the main runnable program:
@Bean
Client client() { return new Client(); }

@Bean
Client client(Settings settings) { return new Client(settings); }
```

These are multiple factory methods with the **same Java name**, leading to ambiguity or violating bean-name/factory-overload contracts. Modern Spring Framework enforces rules/checks on the uniqueness of `@Bean` methods in full configuration; declaring overloads requires great care and may not be accepted under default configurations.

**Recommendation:** Use **distinct method names**, and if you need a specific bean name, use `@Bean("name")`. Do not rely on overloading to select a factory method by parameter set at runtime if you want clear Java configuration.

### Inheritance and method overriding

If configuration classes inherit `@Bean` methods or override methods, how Spring handles them depends on method/class metadata, full/lite mode, and overriding rules. Do not rely on complex inheritance to create aliases or replace beans implicitly. With multi-module configuration, `@Import` and uniquely named factory methods are usually much easier to understand and test.

### Renaming a method changes a public bean-name contract

A project has:

```java
@Bean
Client oldClient() { return new Client(); }
```

If renamed to `createClient()`, the default bean name changes. If consumers inject using `@Qualifier("oldClient")` or call `getBean("oldClient")`, they must be updated or the old name retained via `@Bean("oldClient")` / a compatibility alias.

Do not assume renaming a factory method is always a refactor with zero runtime impact.

## 15. @Bean Names and Return Types in Multi-Module Configuration

One configuration module can be imported into another:

```java
@Configuration(proxyBeanMethods = false)
class ClientConfig {

    @Bean("billingClient")
    PaymentClient paymentClient() {
        return new HttpPaymentClient();
    }
}

@Configuration(proxyBeanMethods = false)
@Import(ClientConfig.class)
class CheckoutConfig {

    @Bean
    CheckoutService checkoutService(
            @Qualifier("billingClient") PaymentClient paymentClient) {
        return new CheckoutService(paymentClient);
    }
}
```

These are illustrative classes requiring `PaymentClient`, `HttpPaymentClient`, and `CheckoutService`. `@Import` pulls the configuration class into the context, while the `PaymentClient paymentClient` parameter is resolved by Spring by type and qualifier. You **do not** need to call `new ClientConfig().paymentClient()` manually.

In multi-module projects, bean naming becomes part of module design if external modules must reference it. In that case:

- Prefer meaningful names and avoid collisions with other modules, e.g., `billingClient` instead of an overly generic `client`.
- Announce primary-name changes; consider compatibility aliases during migration.
- Expose a stable return type like `PaymentClient` if consumers only need the interface.
- Do not let internal framework code implicitly depend on the concrete type of a bean declared with a broad interface return type without tests.

## 16. Common Errors and How to Diagnose Them

| Symptom | Possible Cause | Fix |
| --- | --- | --- |
| `getBean("oldName")` fails after refactoring | `@Bean` method was renamed without keeping an explicit name | Add `@Bean("oldName")` or declare a migration alias |
| `containsBean("factoryMethodName")` returns `false` | `@Bean(name=...)` set another name; method name is not an alias automatically | Look up the declared primary bean name/alias |
| Two beans of the same interface when expecting one via alias | **Two** separate `@Bean` methods were written | Use one method with a name array when only one bean is needed |
| Thinking two beans exist because `name={"a","b"}` | `b` is only an alias of `a` | Check `getBeanNamesForType`/`isAlias` |
| `NoUniqueBeanDefinitionException` | Multiple bean definitions of the same type without a winner | Use `@Qualifier`, `@Primary`, or design a collection |
| `NoSuchBeanDefinitionException` by subtype | Factory return type is only a broad interface, subtype not yet predicted; or bean not registered | Declare concrete return type when needed, check registration/scan and bean scope |
| `BeanNotOfRequiredTypeException` | Lookup by name succeeded yet requested type does not match | Use the right interface/exposed type or adjust proxy/config |
| Bean name collision | Two methods/modules try to claim the same primary name or alias | Choose unique names; check BeanFactory and override policy |
| `@Primary` does not help select the desired subtype | Primary only selects among type-compatible candidates | Fix return type/generic metadata or injection type |
| Alias cannot be retrieved | Alias not declared properly, name collision, or config not loaded | Check `@Bean(name={...})`, context, and bean definitions |
| Incorrect/ambiguous generic injection | Factory method returns raw type or lacks generic metadata | Declare `Codec<String>` instead of `Codec` |
| FactoryBean does not return expected object | Confusing product with FactoryBean object or wrong `getObjectType()` | Distinguish `name` vs. `&name` and verify FactoryBean contract |
| Bean type changes after enabling AOP | Proxy exposes a type other than the concrete class | Inject by interface or configure proxy strategy appropriately |
| Factory method called with `new` outside Spring | Object is not managed by Spring | Retrieve bean from context or constructor-inject in a managed bean |

### Systematic debugging workflow

1. **Identify the primary bean name:** does the method have `@Bean(name/value)`? If not, it uses the method name.
2. **Check aliases:** are the second and subsequent strings in `name={...}` registered?
3. **Count bean definitions:** one factory method or multiple factory methods of the same type?
4. **Inspect declared return type:** interface, concrete class, generic, or raw type?
5. **Inspect the injection point:** does it want one bean or many; are `@Qualifier`/`@Primary` present?
6. **Inspect lifecycle:** has the singleton been created yet; do `@Lazy`/scope/proxy affect type prediction?
7. **Check context:** was the configuration class registered, `@Import`ed, or found by component scan?
8. **Read the root cause** in the exception chain: missing name, missing type, multiple candidates, bean creation, or type mismatch?

### Do not fix errors by renaming randomly

When hitting `NoUniqueBeanDefinitionException`, renaming `firstGateway` to `preferredGateway` does not necessarily solve having two beans of the same type. You must specify **how to pick a candidate** with qualifier/primary or adjust the dependency to receive a collection if appropriate.

Likewise, adding an alias to a bean does not give it a different subtype. Bean name resolution and Java type compatibility are two separate checks.

## 17. Testing Behaviors That Must Stay Stable

An important configuration should be tested with a small Spring ApplicationContext rather than only invoking the Java factory method with `new`.

In `BeanIdentityDemo`, the following checks belong **inside the `try` block that already has `context`**, not as a standalone program:

```java
if (!context.containsBean("mailClient")) {
    throw new AssertionError("Missing primary bean name");
}
if (!context.containsBean("legacyMailClient")) {
    throw new AssertionError("Missing alias");
}
if (context.containsBean("createMailClient")) {
    throw new AssertionError("Unexpected method-name alias");
}
if (context.getBean("mailClient") !=
        context.getBean("legacyMailClient")) {
    throw new AssertionError("Alias must reference same singleton");
}
if (context.getBean(DeliveryClient.class) !=
        context.getBean(SmtpClient.class)) {
    throw new AssertionError("Primary selection is incorrect");
}
```

If all conditions hold, the assertions print no extra stdout lines. If any fail, they throw `AssertionError` with a specific message. An integration test suite can run similar assertions via JUnit/AssertJ and also test missing-bean or ambiguity scenarios.

### Testing renames and migrations

If another library expects the bean name `legacyMailClient`, a test looking up by alias catches regressions when someone accidentally removes the alias. When you want to retire the old name, update the test intentionally alongside the consumer migration plan rather than leaving unused aliases indefinitely.

### Testing bean type prediction

If an injection point requires `SmtpClient` and you change the factory method's return type from `SmtpClient` to `DeliveryClient`, create a context in an integration test with that dependency to detect whether Spring stops resolving the subtype before bean creation. That test is more valuable than checking `getBean("mailClient").getClass()` after the context has already started.

## 18. Exercises and Guided Answers

### Exercise 1 — Default bean name

```java
@Bean
ReportService reportService() {
    return new ReportService();
}
```

What is the default bean name?

**Answer:** `reportService`. It is the method name, provided no explicit name metadata or special registration strategy overrides the identifier.

### Exercise 2 — Explicit name differs from method name

```java
@Bean("mainAudit")
AuditSink createAuditSink() {
    return new StdoutAuditSink();
}
```

Can you call `getBean("createAuditSink")` by default?

**Answer:** No. The primary bean name is `mainAudit`. `createAuditSink` is only the Java factory method name and does not automatically become a bean name or alias.

### Exercise 3 — One bean or two beans?

```java
@Bean(name={"mainAudit","legacyAudit"})
AuditSink auditSink() {
    return new StdoutAuditSink();
}
```

How many bean definitions does this method contribute? Does `legacyAudit` create an extra singleton?

**Answer:** One bean definition; `legacyAudit` is an alias of `mainAudit`, not a second bean. With the default singleton scope, looking up either name returns the same reference.

### Exercise 4 — Two implementations and qualifiers

A context has `@Bean("smsClient") DeliveryClient sms()` and `@Bean("mailClient") DeliveryClient mail()`. A service must always pick SMS. Is renaming `sms()` to `buildSms()` enough to select SMS?

**Answer:** No. The explicit bean names remain `smsClient` and `mailClient`; selection must be specified via `@Qualifier("smsClient")`, or another rule that genuinely expresses the business requirement.

### Exercise 5 — Interface vs. concrete return type

Two `@Bean` methods both return an `SmtpClient` instance, yet one declares `DeliveryClient` and the other declares `SmtpClient`. When Spring needs to find a candidate of type `SmtpClient` before creating the bean, which method resolves more reliably?

**Answer:** The method declaring return type `SmtpClient` provides explicit subtype metadata, so it is better suited for early type prediction. The method declaring `DeliveryClient` does not advertise the subtype in its signature, even though the runtime object created may be an `SmtpClient`.

### Exercise 6 — Return types and generics

Why is `Codec<String> stringCodec()` better than raw `Codec stringCodec()` when multiple codecs exist in the container?

**Answer:** Spring gets generic metadata to select the bean for a `Codec<String>` injection point; the Java compiler also enforces stronger type checking.

### Exercise 7 — FactoryBean and the & prefix

A bean named `product` is created by `FactoryBean<Product>`. Do `getBean("product")` and `getBean("&product")` serve the same purpose?

**Answer:** No. A regular lookup retrieves the product supplied by the FactoryBean; the `&`-prefixed name dereferences to the factory object itself. This behavior is specific to Spring's `FactoryBean`, not every `@Bean` method.

### Exercise 8 — Safe renaming

A project wants to rename bean `oldGateway` to `billingGateway` while older consumers still use the old name. Configuration suggestion?

```java
@Bean(name = {"billingGateway", "oldGateway"})
PaymentGateway gateway() {
    return new DemoPaymentGateway();
}
```

**Answer:** `billingGateway` is the new primary name, and `oldGateway` is a compatibility alias. Plan to update consumers rather than keeping unused aliases indefinitely.

### Exercise 9 — Collection bean trap

A `@Bean List<Handler> handlers()` returns a list of handlers. Is that equivalent to creating N `Handler` beans using N independent `@Bean` methods?

**Answer:** No. A factory method returning a list registers **one collection bean**; N methods register **N `Handler` beans**. Collection injection rules can also be affected by available candidates, so define clearly what you want Spring to manage.

### Exercise 10 — Reading error logs at the right layer

A consumer needs `@Qualifier("billingGateway") PaymentGateway`, yet Spring reports no matching bean. What do you check?

**Answer:** First verify the configuration was loaded, whether bean name/alias `billingGateway` exists, whether the return type matches `PaymentGateway`, and whether the bean is excluded from autowire candidates. If the bean exists yet fails during creation, read the root exception instead of just adding aliases. If multiple candidates exist and the qualifier is insufficient to distinguish them, check selection metadata.

## 19. Design and Review Checklist

- [ ] The primary bean name is either the **default method name** or an explicitly declared name.
- [ ] When using `@Bean(name={"a","b"})`, `b` is understood to be an alias, **not a second bean**.
- [ ] Do not accidentally rely on the factory method name when another explicit name has been set.
- [ ] Bean names/aliases do not collide with other modules.
- [ ] When multiple beans share a type, injection points have clear qualifiers/primary or collection contracts.
- [ ] Return types carry enough information for Spring to resolve required dependencies.
- [ ] Generic return types are declared completely rather than as raw types.
- [ ] Do not confuse declared type, runtime object class, and exposed proxy type.
- [ ] When using `FactoryBean<T>`, distinguish product and factory via `name` / `&name`.
- [ ] Integration tests cover public names, aliases, bean identity, and type matching.
- [ ] Renaming a `@Bean` method is evaluated as a runtime contract change when relying on the default name.

## Summary

In Spring Java configuration, **`@Bean` defaults the bean name to the method name**. `@Bean(name = ...)` or `@Bean(value = ...)` lets you specify an explicit name; when an array of names is provided, **the first element is the primary bean name** and the rest are **aliases of the same bean**. Aliases do not increase the count of bean definitions and do not create extra instances per scope.

**The return type is the factory method's type metadata contract**: it affects how Spring predicts bean types, selects candidates, and matches generics before objects are created. Returning an interface is good design when consumers depend on abstractions; returning a concrete class helps when Spring must predict a subtype for accurate injection. Do not declare an overly broad return type just to make the code compile.

Evaluate three questions independently: **what is the bean's name, how many independent beans exist, and under what type is the bean exposed?** Answering them clearly prevents autowiring ambiguity, post-refactor naming errors, and subtle type-matching bugs.

## Official References

- [Spring Framework — Using the @Bean Annotation (6.2)](https://docs.spring.io/spring-framework/reference/6.2/core/beans/java/bean-annotation.html): naming, aliases, return types, injection, and lifecycle.
- [Spring Framework — @Bean Javadoc](https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/context/annotation/Bean.html): `name`, `value`, aliases, and factory method attributes.
- [Spring Framework — Fine-tuning Annotation-based Autowiring with Qualifiers](https://docs.spring.io/spring-framework/reference/6.2/core/beans/annotation-config/autowired-qualifiers.html): `@Qualifier` and candidate selection.
- [Spring Framework — Fine-tuning Annotation-based Autowiring with @Primary](https://docs.spring.io/spring-framework/reference/6.2/core/beans/annotation-config/autowired-primary.html): primary selection when multiple candidates exist.
- [Spring Framework — Using Generics as Autowiring Qualifiers](https://docs.spring.io/spring-framework/reference/6.2/core/beans/annotation-config/generics-as-qualifiers.html): generic types in injection.
- [Spring Framework — Customizing Instantiation Logic with FactoryBean](https://docs.spring.io/spring-framework/reference/6.2/core/beans/factory-extension.html): `FactoryBean` contract, product type, and lifecycle.
