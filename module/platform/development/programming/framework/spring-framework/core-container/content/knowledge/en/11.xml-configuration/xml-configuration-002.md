# Declaring Beans with `id`, `class`, and `alias` in Spring XML

## 1. Why Do You Need to Understand `id`, `class`, and `alias`?

In the Spring Core Container, XML is one way to declare **bean definitions** — metadata that instructs the container how to locate classes, create objects, inject dependencies, and manage scopes/lifecycles. Example:

```xml
<bean id="messageFormatter" class="com.example.MessageFormatter"/>
```

Four concepts must be distinguished:

- **`<bean>`**: a bean definition in XML.
- **`id`**: the explicit identifier name of the bean.
- **`class`**: the fully qualified Java class name used to instantiate the bean as configured (or the class containing a factory method).
- **`name` / `<alias/>`**: **alternative names** used to look up the same bean definition, not a request to create another bean.

Confusing these leads to `NoSuchBeanDefinitionException`, `ClassNotFoundException`, unresolved XML dependencies, or accidentally creating multiple objects when you only wanted multiple names.

### Learning Outcomes

After this lesson, you will be able to:

1. Write XML bean declarations using `id` and `class` properly.
2. Understand that `name` supports multiple bean identifiers and delimiter characters.
3. Register aliases outside the bean definition using `<alias name="..." alias="..."/>`.
4. Reference a bean by `id` or `alias` using `ref`; distinguish `value` from `ref`.
5. Explain why aliases do not increase the bean-definition count.
6. Distinguish **same definition** from **same instance** in singleton and prototype scopes.
7. Handle duplicate bean names, incorrect FQCNs, constructor arguments, and alias chains.
8. Run a Java 17+ example with Spring Framework 6.2.9, `beans.xml`, and `ClassPathXmlApplicationContext`, and accurately predict stdout.

## 2. Bean Definition and Bean Instance Are Two Layers

The XML file defines **how** to create beans. The container does not necessarily instantiate objects immediately when XML is parsed.

```text
beans.xml
  |
  |  <bean id="formatter"
  |        class="demo.MessageFormatter"/>
  v
XML BeanDefinitionReader
  |
  v
BeanDefinitionRegistry
  |
  | bean name, class, constructor args, scope, lifecycle...
  v
BeanFactory / ApplicationContext
  |
  | When bean creation is needed
  v
Java bean instance
```

With the default `singleton` scope, repeated lookups of **the same bean** within **the same context** return the same managed instance. With `prototype`, each normal lookup creates a new instance. An alias always points to the corresponding **bean definition**; it does not change the scope or the number of instances created.

One Java class can be declared as several distinct bean definitions. Conversely, one bean definition can have multiple names/aliases. Always be clear whether you are talking about **definition count**, **name count**, or **instance count**.

## 3. Standard XML Beans Namespace

A minimal Spring XML file:

**`src/main/resources/beans.xml`**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<beans xmlns="http://www.springframework.org/schema/beans"
       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
       xsi:schemaLocation="
           http://www.springframework.org/schema/beans
           https://www.springframework.org/schema/beans/spring-beans.xsd">

    <bean id="formatter"
          class="com.example.MessageFormatter"/>

</beans>
```

The `<beans>` element is the root of the configuration file, using the Spring Beans namespace. `xsi:schemaLocation` declares the namespace/schema pair so the XML parser understands the structure. These URLs belong to the schema, not to business endpoints or bean names.

`class="com.example.MessageFormatter"` requires that Java class to exist on the runtime classpath. The XML snippet may fail to instantiate if the class lacks a suitable constructor; constructor arguments must be supplied when needed.

### Starting an XML Context

```java
import org.springframework.context.support.ClassPathXmlApplicationContext;

try (ClassPathXmlApplicationContext context =
         new ClassPathXmlApplicationContext("beans.xml")) {
    Object bean = context.getBean("formatter");
}
```

Spring locates `beans.xml` on the classpath. In a standard Gradle project, place the file at `src/main/resources/beans.xml` so it is included on the runtime classpath. `try-with-resources` closes the context after use and triggers destruction callbacks for beans/scopes managed accordingly.

## 4. `id`: Primary Name of the Bean

```xml
<bean id="orderService" class="com.example.OrderService"/>
```

`orderService` is the bean name, **not the Java class name**. Once registered successfully, it can be looked up:

```java
Object service = context.getBean("orderService");
```

`id` provides **a single name**. By convention, use lower camel case: `orderService`, `customerRepository`, `paymentGateway`. Name beans after their role/contract rather than a specific implementation that may change in the future.

### Must `id` and `class` Be the Same?

No:

```xml
<bean id="billingGateway"
      class="com.example.adapters.CardPaymentGateway"/>
```

The bean name is `billingGateway`, and the Java type declared by `class` is `CardPaymentGateway`. Consumers can continue referencing `id="billingGateway"` even if you swap the implementation to another class with a compatible contract.

### Must `id` Be Unique?

Bean names must be managed without conflicts inside the container. Having two XML files both declare `id="billingGateway"` can cause bean-definition overriding or an error depending on configuration and environment. **Do not rely on XML load order to silently pick one definition.**

In modern Spring XML, `id` has type `xsd:string`, without the old `xsd:ID` restrictions. Still, that is no reason to put arbitrary delimiters or hard-to-read characters in bean names. Stable, clear names reduce mistakes in `ref` and monitoring.

## 5. `class`: Source for Creating the Java Object

In most XML bean declarations, `class` is the **fully qualified class name**:

```xml
<bean id="paymentClient"
      class="com.example.integration.PaymentClient"/>
```

The class must be on the classpath. When using constructor-based instantiation, Spring selects and invokes the appropriate constructor. For a class that only has a constructor accepting `String endpoint`, an argument must be provided:

```xml
<bean id="paymentClient"
      class="com.example.integration.PaymentClient">
    <constructor-arg value="https://api.example.test"/>
</bean>
```

This is an illustrative snippet requiring a `PaymentClient` class with a matching constructor. The endpoint is only an example string; in production, URLs and credentials typically come from configuration or a secret manager rather than hardcoding sensitive values in source.

### Common `class`-Related Errors

- Missing package name or typo in the FQCN.
- Class resides in a JAR not yet on the runtime classpath.
- Class is an interface or abstract class yet declared as a bean to be instantiated via constructor.
- Constructor has required parameters, but `<constructor-arg>` is omitted.
- Overloaded constructors are not disambiguated by type, index, or name.
- Class has another unresolved dependency.
- Java module system restricts reflective access to the required constructor.

### One Class, Multiple Bean Definitions

```xml
<bean id="clientA" class="com.example.Client"/>
<bean id="clientB" class="com.example.Client"/>
```

These two lines create **two bean definitions**, which can result in two independent singleton instances. Do not call them aliases. Use two definitions only when you need two separate configurations, ownerships, or scopes.

### When `class` Is a Factory Class

```xml
<bean id="client"
      class="com.example.ClientFactory"
      factory-method="create"/>
```

If `ClientFactory.create()` is a valid static factory method, Spring invokes it to obtain the target bean. In that case, `class` specifies the **factory class**, not necessarily the runtime class of the final object. There are also instance factory methods via `factory-bean`/`factory-method` and the `FactoryBean<T>` interface.

Therefore, the rule “`class` always equals `context.getBean(name).getClass()`” is not accurate in all situations, especially when factories or proxies are involved.

## 6. `name`: Multiple Identifiers on the Same `<bean>`

`name` is an XML attribute supporting one or more names:

```xml
<bean id="formatter"
      name="textFormatter, preferredFormatter"
      class="com.example.MessageFormatter"/>
```

Here:

- `formatter` is the `id`.
- `textFormatter` and `preferredFormatter` are valid aliases.
- They **do not** create additional `MessageFormatter` objects or `BeanDefinition` entries.

Spring accepts multiple names in `name` separated by **commas**, **semicolons**, or **whitespace**. Example:

```xml
<bean id="formatter"
      name="textFormatter; preferredFormatter backupFormatter"
      class="com.example.MessageFormatter"/>
```

This line defines three alternative names for the `formatter` bean. Choose commas or whichever convention is clearest for your team, and avoid unnecessarily long alias lists.

### Using Only `name`, Without `id`

```xml
<bean name="reportService, legacyReportService"
      class="com.example.ReportService"/>
```

Spring can take the primary name and aliases from `name`. Having both `id` and `name` is not mandatory. However, if a bean plays a public role in the system, specifying an explicit `id` is usually easier to read.

### Neither `id` Nor `name`

```xml
<bean class="com.example.Helper"/>
```

The container can **auto-generate a bean name**. That is valid in some configurations, but you should not build cross-module integration contracts on auto-generated names: they are hard to remember and may depend on metadata or load order. If using `ref` or string-name lookup, an explicit identifier is far more maintainable.

## 7. `<alias/>`: Defining Names Outside the Bean Definition

Another XML file can declare:

```xml
<alias name="formatter" alias="externalFormatter"/>
```

The meaning of the two attributes on this element **differs from `name` on `<bean>`**:

- `name="formatter"` is **the name of the target bean being aliased**.
- `alias="externalFormatter"` is **the alternative name being registered**.

Once both elements are loaded into the same context:

```xml
<bean id="formatter" class="com.example.MessageFormatter"/>
<alias name="formatter" alias="externalFormatter"/>
```

`context.getBean("externalFormatter")` resolves to **the exact same bean definition** as `context.getBean("formatter")`.

### An Alias Is Not a New Bean

```text
Primary name: "formatter" --------------------+
                                              |
Alias from name: "textFormatter" -------------+--> BeanDefinition formatter
                                              |         |
Alias from <alias>: "externalFormatter" ------+         v
                                                     target bean
```

The names are different keys for looking up a single registration. An alias is not a class alias, Java inheritance, wrapper, proxy, HTTP redirect, or bean copy.

### When Is `<alias/>` More Valuable Than `name`?

When a bean lives in module A, and module B wants to refer to it by its own name **without modifying module A's XML file**.

**`core-beans.xml`:**

```xml
<bean id="coreFormatter" class="com.example.Formatter"/>
```

**`report-aliases.xml`:**

```xml
<alias name="coreFormatter" alias="reportFormatter"/>
```

Load **both** into the same `ApplicationContext`, and reporting code can use `reportFormatter`. These snippets assume `Formatter` has an appropriate no-arg constructor; in the complete example below, the actual class has a constructor requiring an argument and XML supplies it.

### Alias Chains and Cycles

```xml
<bean id="mainClient" class="com.example.Client"/>
<alias name="mainClient" alias="oldClient"/>
<alias name="oldClient" alias="reportClient"/>
```

Spring's alias registry can resolve alias chains to a canonical name. However, multi-level aliases complicate debugging, and alias cycles or conflicts may be rejected. It is better to maintain one canonical name and direct aliases with clear intent.

## 8. Complete Java 17+ Example with Spring Framework 6.2.9

This demo uses pure `beans.xml` XML. It includes:

- A `MessageFormatter` bean registered with `id="formatter"`.
- Two aliases declared via `name`.
- One alias registered via `<alias/>`.
- A `GreetingClient` that constructor-injects the formatter **via an alias**.
- A Java program verifying definition count, aliases, reference identity, and greeting output.

No `@ComponentScan`, Spring Boot, or web server is required.

### 8.1. Structure

```text
xml-bean-naming-demo/
├── settings.gradle
├── build.gradle
└── src/
    └── main/
        ├── java/
        │   └── demo/
        │       ├── MessageFormatter.java
        │       ├── GreetingClient.java
        │       └── XmlBeanNamingDemo.java
        └── resources/
            └── beans.xml
```

### 8.2. Gradle Setup

**`settings.gradle`**

```groovy
rootProject.name = 'xml-bean-naming-demo'
```

**`build.gradle`**

```groovy
plugins {
    id 'java'
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-context:6.2.9'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

application {
    mainClass = 'demo.XmlBeanNamingDemo'
}
```

`spring-context` brings in the transitive dependencies needed for `ClassPathXmlApplicationContext`, the XML `BeanDefinitionReader`, and the bean container. With Java 17+ and a toolchain-compatible Gradle, the program compiles and runs without installing Spring Boot.

### 8.3. MessageFormatter

**`src/main/java/demo/MessageFormatter.java`**

```java
package demo;

import java.util.Objects;

public final class MessageFormatter {
    private final String prefix;

    public MessageFormatter(String prefix) {
        this.prefix = Objects.requireNonNull(prefix);
    }

    public String format(String name) {
        return prefix + ", " + name + "!";
    }
}
```

This is a plain POJO with no Spring annotations. The class has a constructor accepting `String`, so XML must supply the constructor argument.

### 8.4. GreetingClient

**`src/main/java/demo/GreetingClient.java`**

```java
package demo;

import java.util.Objects;

public final class GreetingClient {
    private final MessageFormatter formatter;

    public GreetingClient(MessageFormatter formatter) {
        this.formatter = Objects.requireNonNull(formatter);
    }

    public MessageFormatter formatter() {
        return formatter;
    }

    public String greet(String name) {
        return formatter.format(name);
    }
}
```

`GreetingClient` only knows the Java dependency `MessageFormatter`. It does not know whether that bean is called `formatter` or `externalFormatter` in XML.

### 8.5. XML Declarations

**`src/main/resources/beans.xml`**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<beans xmlns="http://www.springframework.org/schema/beans"
       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
       xsi:schemaLocation="
           http://www.springframework.org/schema/beans
           https://www.springframework.org/schema/beans/spring-beans.xsd">

    <!-- One bean definition, multiple lookup names. -->
    <bean id="formatter"
          name="textFormatter, preferredFormatter"
          class="demo.MessageFormatter">
        <constructor-arg value="Hello"/>
    </bean>

    <!-- Adds a name, NOT another bean definition. -->
    <alias name="formatter" alias="externalFormatter"/>

    <!-- Uses an alias to inject the same managed dependency. -->
    <bean id="greetingClient" class="demo.GreetingClient">
        <constructor-arg ref="externalFormatter"/>
    </bean>

</beans>
```

There are exactly two `<bean>` elements: `formatter` and `greetingClient`. `name` and `<alias/>` only add names for `formatter`.

### 8.6. Main Class

**`src/main/java/demo/XmlBeanNamingDemo.java`**

```java
package demo;

import java.util.Arrays;
import java.util.HashSet;
import java.util.Set;

import org.springframework.context.support.ClassPathXmlApplicationContext;

public final class XmlBeanNamingDemo {
    public static void main(String[] args) {
        try (ClassPathXmlApplicationContext context =
                     new ClassPathXmlApplicationContext("beans.xml")) {

            MessageFormatter primary =
                    context.getBean("formatter", MessageFormatter.class);
            MessageFormatter viaName =
                    context.getBean("textFormatter", MessageFormatter.class);
            MessageFormatter viaSecondName =
                    context.getBean("preferredFormatter", MessageFormatter.class);
            MessageFormatter viaAlias =
                    context.getBean("externalFormatter", MessageFormatter.class);

            Set<String> aliases = new HashSet<>(
                    Arrays.asList(context.getAliases("formatter"))
            );

            GreetingClient client =
                    context.getBean("greetingClient", GreetingClient.class);

            System.out.println("bean-definitions="
                    + context.getBeanDefinitionCount());
            System.out.println("id-exists="
                    + context.containsBean("formatter"));
            System.out.println("alias-exists="
                    + context.containsBean("externalFormatter"));

            System.out.println("name-alias-registered="
                    + aliases.contains("textFormatter"));
            System.out.println("second-name-alias-registered="
                    + aliases.contains("preferredFormatter"));
            System.out.println("alias-element-registered="
                    + aliases.contains("externalFormatter"));

            System.out.println("all-names-same-instance="
                    + (primary == viaName
                    && primary == viaSecondName
                    && primary == viaAlias));

            System.out.println("alias-is-definition="
                    + context.containsBeanDefinition("externalFormatter"));
            System.out.println("client-uses-managed-bean="
                    + (client.formatter() == primary));
            System.out.println("greeting=" + client.greet("Spring"));
        }
    }
}
```

### 8.7. Running

From the `xml-bean-naming-demo` directory:

```bash
gradle run --quiet
```

If you have the Gradle Wrapper, use `./gradlew run --quiet` on Linux/macOS or `gradlew.bat run --quiet` on Windows.

Running `javac XmlBeanNamingDemo.java` alone is not sufficient because all three Java files must be compiled with Spring dependencies on the classpath. Gradle puts both the compiled classes and `src/main/resources/beans.xml` onto the runtime classpath.

### 8.8. Program Stdout

```text
bean-definitions=2
id-exists=true
alias-exists=true
name-alias-registered=true
second-name-alias-registered=true
alias-element-registered=true
all-names-same-instance=true
alias-is-definition=false
client-uses-managed-bean=true
greeting=Hello, Spring!
```

Any Gradle or logging framework output, if present, is not part of the ten lines printed by `System.out.println`.

### 8.9. Output Analysis

**`bean-definitions=2`:** There are only two bean definitions, because `<alias/>` does not register an additional definition.

**`id-exists=true`:** `formatter` is registered from `id`.

**`alias-exists=true`:** `externalFormatter` is recognized by the registry as an alias.

**`name-alias-registered=true` and `second-name-alias-registered=true`:** `textFormatter` and `preferredFormatter` come from `name`.

**`alias-element-registered=true`:** `<alias name="formatter" alias="externalFormatter"/>` creates an additional alias outside the bean definition.

**`all-names-same-instance=true`:** The default scope is singleton; looking up all four names returns the same object.

**`alias-is-definition=false`:** `containsBeanDefinition("externalFormatter")` finds no definition bearing the alias name. This differs from `containsBean("externalFormatter")`, which returns true due to alias resolution.

**`client-uses-managed-bean=true`:** `<constructor-arg ref="externalFormatter"/>` supplies the managed instance to `GreetingClient`. Using an alias does not hinder constructor injection.

**`greeting=Hello, Spring!`:** The value `Hello` comes from the XML constructor argument; the Java method concatenates it with `Spring` and adds an exclamation mark.

## 9. An Alternative Name Does Not Mean an Alternative Instance

One bean can be referred to by multiple aliases while still having only **one definition**:

```xml
<bean id="primaryClient" class="com.example.Client"/>
<alias name="primaryClient" alias="legacyClient"/>
<alias name="primaryClient" alias="reportClient"/>
```

Diagram:

```text
"primaryClient" ------+
"legacyClient" -------+--> bean definition: primaryClient
"reportClient" -------+                  |
                                         v
                              singleton instance (if singleton)
```

Conversely:

```xml
<bean id="primaryClient" class="com.example.Client"/>
<bean id="legacyClient" class="com.example.Client"/>
<bean id="reportClient" class="com.example.Client"/>
```

is **three bean definitions** and can produce three managed singleton instances. Do not copy bean definitions just to keep old names when what you need is an alias.

## 10. Aliases and Scope: Singleton vs. Prototype

With singleton:

```xml
<bean id="client"
      name="clientAlias"
      class="com.example.Client"
      scope="singleton"/>
```

calling `getBean("client")` and `getBean("clientAlias")` in the same context normally returns the same instance.

With prototype:

```xml
<bean id="requestBuilder"
      name="builderAlias"
      class="com.example.RequestBuilder"
      scope="prototype"/>

<alias name="requestBuilder" alias="externalBuilder"/>
```

All names point to **one prototype definition**; however, each normal lookup creates a new prototype. Thus:

```java
Object first = context.getBean("requestBuilder");
Object second = context.getBean("externalBuilder");
System.out.println(first == second);  // typically false
```

Aliases do not “force singleton” and do not hold references to created objects. They simply resolve the name before the BeanFactory applies the target definition's scope.

### Prototype Injected into a Singleton

If a singleton service receives a prototype bean via `ref` in its constructor, that prototype instance is created when the singleton is built and the reference is normally held for the singleton's lifetime. It is not replaced with a new prototype on each service method call. If you want dynamic prototype lookup, use `ObjectProvider<T>`/`Provider<T>` or an appropriate mechanism rather than relying on aliases.

## 11. Referencing via `ref`: `name` and `value` Are Very Different

### Constructor Injection

```xml
<bean id="repository" class="com.example.Repository"/>
<alias name="repository" alias="primaryRepository"/>

<bean id="service" class="com.example.Service">
    <constructor-arg ref="primaryRepository"/>
</bean>
```

`Service` must have a matching constructor accepting `Repository`. Spring resolves the `primaryRepository` alias and passes the bean object into the constructor.

### Nested `<ref/>` Form

```xml
<bean id="service" class="com.example.Service">
    <constructor-arg>
        <ref bean="primaryRepository"/>
    </constructor-arg>
</bean>
```

Has the equivalent lookup effect in the use case above.

### Property/Setter Injection

```xml
<bean id="service" class="com.example.Service">
    <property name="repository" ref="primaryRepository"/>
</bean>
```

Here `name="repository"` is the **JavaBean property** name matching `Service`'s setter; `ref="primaryRepository"` is the dependency bean name. Do not confuse `property@name` with `bean@name`.

### Use `value` When You Want a Literal

```xml
<constructor-arg value="primaryRepository"/>
```

passes the **string** `primaryRepository` rather than looking up a bean. If the constructor expects `Repository`, this can cause a conversion or constructor-matching error. Change it to `ref` when an object dependency is required.

## 12. Registering Aliases Across Multiple XML Files

A legacy project may have module A define a bean while module B assigns its own name:

**`shared.xml`**

```xml
<beans xmlns="http://www.springframework.org/schema/beans">
    <bean id="sharedFormatter"
          class="com.example.MessageFormatter"/>
</beans>
```

**`reporting.xml`**

```xml
<beans xmlns="http://www.springframework.org/schema/beans">
    <alias name="sharedFormatter" alias="reportFormatter"/>
</beans>
```

These two snippets only illustrate splitting sources; the `MessageFormatter` class needs a compatible constructor in a real project. Load both files into **the same context**, for example:

```java
try (ClassPathXmlApplicationContext context =
         new ClassPathXmlApplicationContext(
                 "shared.xml", "reporting.xml")) {
    Object formatter = context.getBean("reportFormatter");
}
```

Do not create two independent `ClassPathXmlApplicationContext` instances and expect aliases from one context to be automatically visible in the other.

### XML Import

A root file can also load child XML files:

```xml
<beans xmlns="http://www.springframework.org/schema/beans">
    <import resource="shared.xml"/>
    <alias name="sharedFormatter" alias="reportFormatter"/>
</beans>
```

In a real project, add the full namespace and `schemaLocation` as in the main demo. The key point is that bean definitions and aliases are loaded into the same registry.

### Combining Java Configuration with XML

If Java `@Configuration` serves as the composition root, you can use Spring `@ImportResource("classpath:shared.xml")`. This imports XML metadata into the same context; it does **not** create a second XML context. Aliases in the XML continue to work in that bean registry.

## 13. XML Names vs. Java `@Bean` Names

| Mechanism | Meaning |
| --- | --- |
| `<bean id="client" class="..."/>` | XML bean definition named `client`. |
| `<bean id="client" name="legacyClient" class="..."/>` | XML bean named `client` with alias `legacyClient`. |
| `<alias name="client" alias="externalClient"/>` | Adds an alias outside the bean element. |
| `@Bean("client")` | Java configuration method providing a bean named `client`. |
| `@Bean({"client", "legacyClient"})` | Java bean with a primary name and an alias. |
| `@Component("client")` | Scanned component with an explicit name. |

Spring manages bean names and aliases in its registry; different **declaration sources** do not inherently produce different bean types. However, the same name can be registered from multiple sources and collide.

Do not assume that because a bean has an alias in XML, a Java `@Bean` with the same name will automatically merge with that XML bean. If two sources register **two definitions**, Spring applies name-conflict/overriding rules. Assign one clear owner for each bean.

## 14. APIs for Inspecting Beans and Aliases When Debugging

### `getBean(name)`

```java
Object target = context.getBean("externalFormatter");
```

Looks up a bean by name or alias. For a normal singleton, an alias returns the same instance as the canonical name.

### `getBean(name, type)`

```java
MessageFormatter target =
        context.getBean("externalFormatter", MessageFormatter.class);
```

Looks up by name/alias while requiring a compatible type. If the bean does not exist, `NoSuchBeanDefinitionException` can occur; if the type does not match, `BeanNotOfRequiredTypeException` can occur.

### `containsBean(name)`

```java
boolean present = context.containsBean("externalFormatter");
```

Checks whether a name or alias can resolve to a bean.

### `containsBeanDefinition(name)`

```java
boolean ownDefinition =
        context.containsBeanDefinition("externalFormatter");
```

Checks whether a definition **directly** bears that name in the current registry. For a normal alias, the result is false even though `containsBean` returns true. In a parent-child hierarchy, the two methods also differ in lookup scope.

### `getAliases(name)`

```java
String[] aliases = context.getAliases("formatter");
```

Lists alternative names for a canonical bean. Do not rely on the element order of the returned array as a contract; if deterministic output is needed in tests, sort it.

### `getBeanDefinitionNames` and `getBeanDefinitionCount`

```java
String[] names = context.getBeanDefinitionNames();
int count = context.getBeanDefinitionCount();
```

These inspect **bean definitions**, not treating aliases as new definitions. In the pure XML demo, there are exactly two top-level `<bean>` elements, so the count is 2.

## 15. Common Pitfalls

### Pitfall 1 — Swapping `id` and `class`

```xml
<bean id="demo.MessageFormatter" class="formatter"/>
```

Bean name and Java class name are reversed. Fix `class` to the real FQCN and `id` to a logical bean name.

### Pitfall 2 — Using Two Definitions When You Only Want Two Names

Two `<bean>` elements with the same class can produce two instances. If you genuinely just want an old name alongside a new name, use `<alias/>` or `name`.

### Pitfall 3 — Alias Conflict

Defining an alias `reportService` while another bean already has the name `reportService` causes ambiguity/conflict. Audit names across the whole context, including XML imports, Java config, and scanned beans.

### Pitfall 4 — Alias Pointing to an Absent Target

An aliases file is loaded, but the target bean was not loaded or was excluded by a profile/condition. An alias does not create the target definition. Check the loaded sources and actual bean registrations.

### Pitfall 5 — Duplicate Bean Definition Names

Two XML files both declaring `id="client"` can cause an error or silent overriding depending on configuration. Do not treat file order as a stable API to pick implementations.

### Pitfall 6 — Typo in `ref`

`<constructor-arg ref="externalFormater"/>` misspelled relative to `externalFormatter` prevents Spring from resolving the dependency. Catch this early with an integration test that starts the context.

### Pitfall 7 — Using `value` Instead of `ref`

`value="client"` is a literal; `ref="client"` looks up a bean. Distinguish them according to the Java parameter type.

### Pitfall 8 — Constructor Mismatch

If a class only has `MessageFormatter(String)`, `<bean class="demo.MessageFormatter"/>` lacks the information needed to instantiate it. Declare `<constructor-arg value="..."/>`.

### Pitfall 9 — Wrong Fully Qualified Class Name

The package/class name in XML differs from the Java file, or the JAR is missing from the classpath. Verify the build output and runtime classpath.

### Pitfall 10 — Thinking an Alias Changes Bean Scope

An alias does not turn a prototype into a singleton or extend its lifetime. Two prototype lookups via two aliases can return two different objects.

### Pitfall 11 — Thinking a Bean Without `id` Does Not Exist

XML can use `name` or an auto-generated name. However, for beans referenced via `ref`, an explicit identifier makes the configuration clearer.

### Pitfall 12 — Thinking `getAliases` Returns Bean Definitions

Aliases are alternative names, not independent registrations. Use `getBeanDefinitionNames` for definitions and `getAliases` for names.

### Pitfall 13 — Using an Alias to Hide Two Different Resources

If `readDatabase` and `writeDatabase` have separate connection pools, do not alias them to the same pool just to avoid configuring another bean. An alias is only valid when both names genuinely represent **the same dependency**.

### Pitfall 14 — Loading an Alias in a Separate Context

An alias existing in context A does not make context B automatically find that bean. Configure composition or parent-child relationships as intended; do not build a second context inside a factory method.

### Pitfall 15 — Confusing `FactoryBean` with an Alias

The `&` prefix in `&factoryName` requests the **FactoryBean instance** rather than its product; it is not a regular alias.

### Pitfall 16 — Using Names Containing Sensitive Data

Bean names frequently appear in logs, error messages, and monitoring. Never put API tokens, passwords, or credentials in `id` or `alias`.

## 16. Testing XML Definitions and Naming

Test bean names not only by string lookup, but also by reference identity and definition count.

- Verify `containsBean("formatter")` and `containsBean("externalFormatter")`.
- Verify all aliases appear in `getAliases("formatter")`.
- Verify `getBeanDefinitionCount()` does not increase merely from adding `<alias/>`.
- For singletons, compare references with `==` between lookups by `id` and by `alias`.
- For prototypes, assert that two lookups return valid distinct instances per scope, rather than forcing identity.
- Verify constructor injection via `ref` through the consumer's behavior.
- Test that the context fails when a target bean or class is missing so XML mistakes are caught early.

### Migration Testing Scenario

When renaming bean `oldClient` to `primaryClient`, you can keep:

```xml
<bean id="primaryClient" class="com.example.Client"/>
<alias name="primaryClient" alias="oldClient"/>
```

In integration tests, verify that both names resolve to the same managed bean (when singleton). When removing the old alias, tests should fail only in modules still using the old name, exposing dependencies that need migration.

## 17. Self-Check Exercises

**Exercise 1.** Given the XML:

```xml
<bean id="primary" name="secondary,tertiary"
      class="demo.Client"/>
<alias name="primary" alias="legacy"/>
```

How many bean definitions are there? How many lookup names?

**Answer:** One definition, four names: `primary`, `secondary`, `tertiary`, `legacy`.

**Exercise 2.** If you add:

```xml
<bean id="another" class="demo.Client"/>
```

Is `another` an alias of `primary`?

**Answer:** No. This is a second definition even though it uses the same Java class.

**Exercise 3.** Does `<alias name="primary" alias="legacy"/>` cause the constructor of bean `primary` to run an extra time?

**Answer:** No. An alias only registers an alternative name.

**Exercise 4.** With prototype scope, is `getBean("primary") == getBean("legacy")` always true?

**Answer:** No. Each prototype lookup normally creates a new instance.

**Exercise 5.** XML has `<constructor-arg value="legacy"/>`, and the constructor requires `Client`. Is this valid?

**Answer:** No. You must use `ref="legacy"` to look up the bean object.

**Exercise 6.** `<property name="client" ref="legacy"/>`: do both `name` attributes mean the same thing?

**Answer:** No. `property@name` selects the JavaBean property; bean `id`/`alias` names the dependency resolved by `ref`.

**Exercise 7.** Can Spring create a bean when neither `id` nor `name` is declared?

**Answer:** Yes, it can auto-generate a name in some situations. However, explicit names are recommended for beans referenced publicly.

**Exercise 8.** Why can `containsBean("legacy")` be true while `containsBeanDefinition("legacy")` is false?

**Answer:** Because `legacy` is only an alias; there is no direct bean definition with that name.

**Exercise 9.** Is `class` always the runtime class of a bean returned from a factory method?

**Answer:** No. If `factory-method`, `FactoryBean`, or a proxy is used, the declared class may be the factory class or differ from the runtime bean type.

**Exercise 10.** Should you alias `readClient` to `writeClient` if the two clients have different policies?

**Answer:** No, unless they truly represent the same resource and contract. An alias is inappropriate for equating two dependencies that must remain distinct.

## 18. Official Documentation

- [Spring Framework 6.2 — Bean Overview and Naming Beans](https://docs.spring.io/spring-framework/reference/6.2/core/beans/definition.html): meanings of `id`, `name`, aliases, `class`, and naming conventions.
- [Spring Framework 6.2 — Dependency Injection](https://docs.spring.io/spring-framework/reference/6.2/core/beans/dependencies.html): `value`, `ref`, constructors, properties.
- [Spring Framework 6.2 — Bean Scopes](https://docs.spring.io/spring-framework/reference/6.2/core/beans/factory-scopes.html): singleton and prototype.
- [Spring Framework 6.2 — Using the @Bean Annotation](https://docs.spring.io/spring-framework/reference/6.2/core/beans/java/bean-annotation.html): naming and aliasing in Java configuration for comparison.
- [Spring Framework 6.2 API — ClassPathXmlApplicationContext](https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/context/support/ClassPathXmlApplicationContext.html): creating a context from classpath XML.
- [Spring Framework 6.2 API — BeanFactory](https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/beans/factory/BeanFactory.html): lookup by name/type and `getAliases`.
- [Spring Framework 6.2 API — AliasRegistry](https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/core/AliasRegistry.html): alias registration and canonical names.

**Key takeaway:** `id` is the identifier name, `class` specifies the Java type or factory used to create the bean, and `name` and `<alias/>` provide alternative lookup names. **An alias does not create a new bean definition or object**; the actual number of objects is governed by scope and lifecycle. As XML configuration grows, keep a clear canonical name, add aliases only with clear intent, and test lookup and identity before renaming beans.
