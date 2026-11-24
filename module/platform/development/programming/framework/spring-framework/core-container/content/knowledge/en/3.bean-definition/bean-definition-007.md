# Distinguishing Bean Definition Inheritance from Java Class Inheritance

## 1. Two Kinds of "Inheritance" at Two Different Layers

In the Spring Core Container, **bean definition inheritance** refers to **a child bean definition inheriting configuration metadata from a parent bean definition**. This is an **IoC container configuration-reuse mechanism**: property values, constructor arguments, and certain initialization settings can be inherited and then supplemented or overridden.

By contrast, **Java class inheritance** is a type relationship understood by the compiler from the `extends` syntax (or `implements` for interfaces). It governs member reuse, subtyping, and reference assignment in Java's type system. **Spring does not create an `extends` relationship simply because XML has `parent="..."`.**

| Criterion | Bean definition inheritance | Java class inheritance |
| --- | --- | --- |
| What is inherited | **Metadata** for Spring to create/configure a bean | Members/behavior and **subtype relationship** of Java types |
| Common declaration | XML `<bean parent="template">...` or BeanDefinition parent name | `class Child extends Parent` |
| Who processes it | **Spring IoC container** when merging definitions | **Compiler/JVM** according to the Java language |
| Requires `extends` between the two bean classes? | **No** | Has `extends` for class inheritance |
| Must the parent definition create an object? | No; parent can be a template with `abstract="true"` | Java superclass does not have to be instantiated alone, though superclass constructors run when constructing a subclass |
| Does the child bean share an object with the parent bean? | **No**; inheriting configuration differs from injecting/sharing an instance | Two instances still have independent identity, even when belonging to classes in the same type hierarchy |
| What does the name "parent" mean? | **Bean name** of another definition | **Java superclass** identified by type name |

**The two independent relationships can appear together, separately, or not at all:** A Java subclass bean can be registered with a bean definition that has no `parent`; and two classes **unrelated by `extends`** can both inherit property metadata from one parent bean definition.

Goal of this lesson: read XML `parent`/`abstract` accurately, inspect merged configuration, distinguish `getBean` creating **objects** from `getBeanDefinition` returning **metadata**, and verify for yourself that a Java subclass does not inherit a bean definition.

## 2. Bean Definition Inheritance Works as a Configuration Template

A definition holds information for the container to create and configure a bean. In Spring XML, you can put shared properties into a **template bean definition**:

~~~xml
<bean id="sharedTemplate" abstract="true">
    <property name="endpoint" value="https://api.example.invalid/v1"/>
    <property name="retries" value="3"/>
</bean>
~~~

This is a **configuration definition**, not a Java object `SharedTemplate`. It intentionally omits `class` and is marked `abstract="true"`, because it serves only as a metadata source for child bean definitions.

Two child definitions reference it via `parent="sharedTemplate"`:

~~~xml
<bean id="emailSettings" parent="sharedTemplate"
      class="demo.EmailSettings">
    <property name="sender" value="learn@example.invalid"/>
</bean>

<bean id="smsSettings" parent="sharedTemplate"
      class="demo.SmsSettings">
    <property name="retries" value="5"/>
    <property name="provider" value="ExampleSMS"/>
</bean>
~~~

Spring interprets this as:

- `emailSettings` receives `endpoint` and `retries=3` from the template, plus `sender`.
- `smsSettings` receives the same `endpoint`, but **overrides `retries` to 5**, plus `provider`.
- The classes `EmailSettings` and `SmsSettings` **can have no Java inheritance relationship whatsoever**, as long as each class supports the properties applied to it.
- When the container creates a child bean, it processes the **merged bean definition**. The parent does not become a dependency/object injected into the child.

How this differs from the Java model: `parent="sharedTemplate"` points to a **bean definition name**, not a `class` or Java superclass. You can keep the Java classes unchanged while changing parent/template metadata, and vice versa.

### Why Is `abstract="true"` Required?

A parent definition used **solely as a template** should be marked abstract. When the parent **has no class**, `abstract="true"` is required so the container does not treat it as a bean to instantiate. Even when a template has a `class`, you should still set `abstract="true"` if you **do not intend for the container to create an instance of the parent**.

With an abstract template:
- The container **retains the metadata** for children to reference;
- `containsBeanDefinition("sharedTemplate")` can return `true`;
- you **cannot** retrieve the template as a bean instance via `getBean("sharedTemplate")`;
- the template is not pre-instantiated like an ordinary singleton;
- `abstract="true"` **does not automatically make** a Java `abstract class`.

Conversely, `abstract class Base` in Java is a language constraint; an object must belong to a concrete subclass. The two uses of `abstract` operate at **two different layers of meaning**.

## 3. Java Class Inheritance: No Spring Needed, No Parent Bean Definition Needed

Look at plain Java:

~~~java
class EmailSettings {
    private int retries;

    public int getRetries() {
        return retries;
    }

    public void setRetries(int retries) {
        this.retries = retries;
    }
}

class UrgentEmailSettings extends EmailSettings {
    private String priority;

    public String getPriority() {
        return priority;
    }

    public void setPriority(String priority) {
        this.priority = priority;
    }
}
~~~

`UrgentEmailSettings extends EmailSettings` means an `UrgentEmailSettings` **is also** an `EmailSettings` in the type system. It inherits inheritable members such as `getRetries()`/`setRetries()`. Given an `UrgentEmailSettings` object, the expression `urgent instanceof EmailSettings` is true.

There is no XML `parent` in the Java example above. Spring **does not need** bean definition inheritance to instantiate a Java subclass:

~~~xml
<bean id="urgentEmail" class="demo.UrgentEmailSettings">
    <property name="retries" value="2"/>
    <property name="priority" value="HIGH"/>
</bean>
~~~

This is an **independent** bean definition using the Java subclass directly as its class. The `retries` property is set via the inherited Java setter. When inspecting raw metadata, `getParentName()` of `urgentEmail` will be `null`.

**Two counterexamples to prevent confusion:**

- `emailSettings` and `smsSettings` share parent **metadata**, yet `EmailSettings` does not extend `SmsSettings` or vice versa.
- `urgentEmail` uses the Java class `UrgentEmailSettings extends EmailSettings`, yet its definition has **no** `parent` metadata.

Java inheritance still follows Java's access control, constructors, overriding/overloading, and polymorphism rules. Those rules do not change simply because Spring uses reflection or injection.

## 4. What Gets Merged, and What Gets Overridden?

According to Spring Framework, a child definition can inherit **constructor argument values, bean properties, and method overrides** from a parent and override/supplement them. Certain container settings such as scope, init method, destroy method, or static factory method, when explicitly declared on the child, **replace** the parent's corresponding value.

| Attribute / Metadata | Basic behavior with parent/child definitions | Caution |
| --- | --- | --- |
| Bean class | If the child does not specify a class, it can use the parent's class; the child can specify a different class | The actual class must accept the merged properties/constructor args |
| Property values | Inherits names/properties from parent; child can override the same property and add new ones | If setter/type is incompatible, bean creation may fail |
| Constructor arguments | Can be inherited, added, or overridden via merge rules | Specify index/type/name clearly when multiple overloads exist |
| Method overrides | Can be merged from parent | Depends on the actual type and methods |
| Scope | Can be inherited or overridden per configuration | `prototype` does not mean Java subclass |
| Initialization/destroy method | Settings declared on child can override parent | Only meaningful when the method exists on the actual class |
| Static factory method setting | Child can replace the parent's setting | Requires matching factory/class and signature |
| Certain other flags | Not **every flag** on the parent is automatically inherited: lazy-init, autowire mode, depends-on, and other settings have their own rules | Check version-specific documentation/API; do not assume "copy everything verbatim" |

**Key point:** The container **does not run a "parent bean object's" constructor and then turn it into a child object**. It resolves metadata to know how to create a concrete object for the child bean definition. When the parent is purely an abstract template, **no parent instance exists** to be "inherited".

**Note on scope and lifecycle:** A child definition remains a registration with its own name and scope. If the child uses singleton, the container typically provides one instance per **child bean definition within one context**. Two child definitions inheriting from the same parent template do **not** get forced to share an object.

### Raw Bean Definition vs. Merged Bean Definition

Spring provides two views:

- `getBeanDefinition("smsSettings")`: inspects the **locally registered metadata** for the child bean, typically having `parentName="sharedTemplate"` and property `retries=5`, without the `endpoint` property in the child's own declaration.
- `getMergedBeanDefinition("smsSettings")`: inspects the **metadata after Spring combines** parent+child. At this point, the `endpoint` property from the template **is present** and `retries` reflects the child's overridden value.

These APIs are for **debugging container configuration**, not for routine use inside business services. Business code should receive dependencies via constructor/`@Bean` parameters and work with real objects.

## 5. A Java 17 + Maven Project Observing Both Kinds of Inheritance

This lesson runs on **Spring Framework 7.0.9**, using JDK **17+** and Maven **3.9+**. We intentionally use **Spring XML** because it illustrates `parent` and `abstract` visually. Spring XML remains a valid configuration choice in the Framework; it **does not** require Spring Boot, and there is no HTTP server here.

Project structure:

~~~text
bean-inheritance-demo/
├── pom.xml
└── src/
    └── main/
        ├── java/
        │   └── demo/
        │       ├── BeanInheritanceDemo.java
        │       ├── EmailSettings.java
        │       ├── SmsSettings.java
        │       └── UrgentEmailSettings.java
        └── resources/
            └── beans.xml
~~~

This is a **complete project**: all Java sources must reside under `src/main/java` in the proper package, and XML under `src/main/resources` so Maven places `beans.xml` on the runtime classpath.

### 5.1. `pom.xml`

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>bean-inheritance-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>7.0.9</version>
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
                <configuration>
                    <mainClass>demo.BeanInheritanceDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

`spring-context` brings along the core Spring artifacts needed to run `ClassPathXmlApplicationContext` and the bean factory. Maven Compiler Plugin runs `javac` with `--release 17`, and the Exec Plugin runs the `main` class with the full dependency classpath. Neither `spring-boot-starter` nor `@SpringBootApplication` is needed.

### 5.2. `src/main/resources/beans.xml`

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<beans xmlns="http://www.springframework.org/schema/beans"
       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
       xsi:schemaLocation="http://www.springframework.org/schema/beans
                           https://www.springframework.org/schema/beans/spring-beans.xsd">

    <!-- Holds shared metadata only; must not create a bean instance. -->
    <bean id="sharedTemplate" abstract="true">
        <property name="endpoint" value="https://api.example.invalid/v1"/>
        <property name="retries" value="3"/>
    </bean>

    <!-- No need to extend each other in Java to inherit metadata. -->
    <bean id="emailSettings" parent="sharedTemplate"
          class="demo.EmailSettings">
        <property name="sender" value="learn@example.invalid"/>
    </bean>

    <bean id="smsSettings" parent="sharedTemplate"
          class="demo.SmsSettings">
        <property name="retries" value="5"/>
        <property name="provider" value="ExampleSMS"/>
    </bean>

    <!-- Has Java extends, but NO parent bean definition. -->
    <bean id="urgentEmail" class="demo.UrgentEmailSettings">
        <property name="endpoint" value="https://urgent.example.invalid/v1"/>
        <property name="retries" value="2"/>
        <property name="sender" value="urgent@example.invalid"/>
        <property name="priority" value="HIGH"/>
    </bean>
</beans>
~~~

**How to read it:**
- The `sharedTemplate` template has no `class`, because **children supply concrete classes**. It must have `abstract="true"`.
- Both bean definitions `emailSettings` and `smsSettings` specify `parent="sharedTemplate"`: they share **metadata**, not a Java class or object.
- `smsSettings` overrides `retries=3` to `5` in the child metadata.
- `urgentEmail` uses a Java subclass but intentionally omits `parent="..."`. All properties in the example are declared **directly** on this bean.

**Note on URLs:** The `.invalid` domain is an illustrative address; no HTTP request is made. The `endpoint` property only stores a character string to verify inheritance/overriding.

### 5.3. `src/main/java/demo/EmailSettings.java`

~~~java
package demo;

public class EmailSettings {
    private String endpoint;
    private int retries;
    private String sender;

    public String getEndpoint() {
        return endpoint;
    }

    public void setEndpoint(String endpoint) {
        this.endpoint = endpoint;
    }

    public int getRetries() {
        return retries;
    }

    public void setRetries(int retries) {
        this.retries = retries;
    }

    public String getSender() {
        return sender;
    }

    public void setSender(String sender) {
        this.sender = sender;
    }
}
~~~

### 5.4. `src/main/java/demo/SmsSettings.java`

~~~java
package demo;

public class SmsSettings {
    private String endpoint;
    private int retries;
    private String provider;

    public String getEndpoint() {
        return endpoint;
    }

    public void setEndpoint(String endpoint) {
        this.endpoint = endpoint;
    }

    public int getRetries() {
        return retries;
    }

    public void setRetries(int retries) {
        this.retries = retries;
    }

    public String getProvider() {
        return provider;
    }

    public void setProvider(String provider) {
        this.provider = provider;
    }
}
~~~

`SmsSettings` **does not extend** `EmailSettings`; the two classes simply happen to have setters/properties compatible with the metadata template. That is proof that bean definition inheritance does not create a Java type hierarchy.

### 5.5. `src/main/java/demo/UrgentEmailSettings.java`

~~~java
package demo;

public class UrgentEmailSettings extends EmailSettings {
    private String priority;

    public String getPriority() {
        return priority;
    }

    public void setPriority(String priority) {
        this.priority = priority;
    }
}
~~~

This class inherits `setEndpoint`, `setRetries`, and `setSender` from `EmailSettings` via **Java `extends`**, and adds the `priority` property. It does not need `parent` in XML for those Java setters to work.

### 5.6. `src/main/java/demo/BeanInheritanceDemo.java`

~~~java
package demo;

import org.springframework.beans.factory.config.BeanDefinition;
import org.springframework.context.support.ClassPathXmlApplicationContext;

public final class BeanInheritanceDemo {
    private BeanInheritanceDemo() {
    }

    public static void main(String[] args) {
        try (var context = new ClassPathXmlApplicationContext("beans.xml")) {
            var factory = context.getBeanFactory();

            BeanDefinition template =
                    factory.getBeanDefinition("sharedTemplate");
            BeanDefinition emailDefinition =
                    factory.getBeanDefinition("emailSettings");
            BeanDefinition smsDefinition =
                    factory.getBeanDefinition("smsSettings");
            BeanDefinition smsMerged =
                    factory.getMergedBeanDefinition("smsSettings");
            BeanDefinition urgentDefinition =
                    factory.getBeanDefinition("urgentEmail");

            EmailSettings email =
                    context.getBean("emailSettings", EmailSettings.class);
            SmsSettings sms =
                    context.getBean("smsSettings", SmsSettings.class);
            UrgentEmailSettings urgent =
                    context.getBean("urgentEmail", UrgentEmailSettings.class);

            System.out.println("template.registered="
                    + context.containsBeanDefinition("sharedTemplate"));
            System.out.println("template.abstract=" + template.isAbstract());
            System.out.println("email.parent=" + emailDefinition.getParentName());
            System.out.println("sms.parent=" + smsDefinition.getParentName());
            System.out.println("sms.raw.hasEndpoint="
                    + (smsDefinition.getPropertyValues()
                            .getPropertyValue("endpoint") != null));
            System.out.println("sms.merged.hasEndpoint="
                    + (smsMerged.getPropertyValues()
                            .getPropertyValue("endpoint") != null));

            System.out.println("email.endpoint=" + email.getEndpoint());
            System.out.println("email.retries=" + email.getRetries());
            System.out.println("email.sender=" + email.getSender());
            System.out.println("sms.endpoint=" + sms.getEndpoint());
            System.out.println("sms.retries=" + sms.getRetries());
            System.out.println("sms.provider=" + sms.getProvider());

            System.out.println("emailSms.javaInheritance="
                    + EmailSettings.class.isAssignableFrom(SmsSettings.class));
            System.out.println("urgent.javaExtendsEmail="
                    + (urgent instanceof EmailSettings));
            System.out.println("urgent.definitionParent="
                    + (urgentDefinition.getParentName() != null));
            System.out.println("urgent.priority=" + urgent.getPriority());
        }
    }
}
~~~

Relevant APIs:
- `getBeanDefinition("smsSettings")` gets the **raw definition** with `parentName`, where `endpoint` is not declared on the child.
- `getMergedBeanDefinition("smsSettings")` provides the **merged definition**, containing the `endpoint` property from the parent template.
- `getBean(...)` retrieves the **actual Java object** that has been instantiated and configured.
- `EmailSettings.class.isAssignableFrom(SmsSettings.class)` checks subtyping **in Java**; the result is completely distinct from parent metadata relationships.
- `urgent instanceof EmailSettings` is true due to **Java `extends`**, while `urgentEmail`'s raw bean definition has no parent.

This example intentionally inspects bean factory APIs for teaching purposes. In normal business code, avoid scattering `BeanDefinition` inspection or `getBean()` calls across services; prefer dependency injection and explicit configuration.

## 6. Running Maven and Verifying Stdout

Run inside the `bean-inheritance-demo` directory containing `pom.xml`:

~~~bash
java -version
javac -version
mvn -version
mvn -q clean compile exec:java
~~~

Commands `java -version`/`mvn -version` display machine-dependent information and **have no fixed standard stdout**. The final Maven command compiles Java via `javac` using the Compiler Plugin and runs the main class with Spring libraries on the classpath.

**16 lines of stdout printed by the program** (excluding Maven/logging backend messages):

~~~text
template.registered=true
template.abstract=true
email.parent=sharedTemplate
sms.parent=sharedTemplate
sms.raw.hasEndpoint=false
sms.merged.hasEndpoint=true
email.endpoint=https://api.example.invalid/v1
email.retries=3
email.sender=learn@example.invalid
sms.endpoint=https://api.example.invalid/v1
sms.retries=5
sms.provider=ExampleSMS
emailSms.javaInheritance=false
urgent.javaExtendsEmail=true
urgent.definitionParent=false
urgent.priority=HIGH
~~~

### Reading the Evidence by Group

1. `template.registered=true`, `template.abstract=true`: the template exists as metadata; it is not a bean object to retrieve with `getBean("sharedTemplate")`.
2. `email.parent` and `sms.parent`: both definitions point to **the same parent name**.
3. `sms.raw.hasEndpoint=false` yet `sms.merged.hasEndpoint=true`: the `endpoint` property is **merged from the template**, even though the child XML did not re-declare it.
4. Email gets `retries=3`, SMS gets `retries=5`: **both inherit metadata yet override independently**.
5. `emailSms.javaInheritance=false`: `EmailSettings` and `SmsSettings` have no class inheritance relationship even though their definitions share a parent.
6. `urgent.javaExtendsEmail=true` alongside `urgent.definitionParent=false`: Java inheritance exists **without** needing bean definition inheritance.

Note: `emailSettings` and `smsSettings` can be pre-instantiated during context refresh if they are non-lazy singletons. These are **two separate registrations**, with no shared "parent instance". `getBeanDefinition` and `getMergedBeanDefinition` operate on metadata, not on querying a Java superclass.

## 7. Java `extends` vs. XML `parent`: Common Cases

| Scenario | Java `extends` relationship? | Bean definition `parent`? | Result |
| --- | --- | --- | --- |
| `EmailSettings` and `SmsSettings` in the demo | No | Both point to `sharedTemplate` | Two independent classes inheriting shared configuration values |
| `UrgentEmailSettings extends EmailSettings`, bean `urgentEmail` | Yes | No | Java subtype; independent bean definition |
| Child bean class is the same Java class as a class-bearing template | No separate subtype relationship needed | Yes | Metadata can be reused when classes are compatible |
| Child bean class is a Java subclass of the template's class | Yes | Yes | Both relationships exist, yet they remain **two distinct mechanisms** |
| A class uses `extends`, with no Spring bean registered | Yes | No | Java inheritance works, **no Spring bean exists** |
| A child definition overrides `class` to one not accepting parent properties | Does not require `extends` | Yes, but incompatible metadata | Bean creation may fail due to setter/constructor mismatch |

**Do not write:** "The child bean class must extend the parent bean class." The true requirement is that **the class used to create the child bean must be compatible with the merged metadata**. If the template requires `setEndpoint(String)`, the child class needs a way to accept the `endpoint` property. It can do so via its own setter, an inherited Java setter, or another container-supported configuration mechanism.

### Parent Bean Definition Is Not a Parent `ApplicationContext`

Spring also has the concept of a **parent application context** in a hierarchy of contexts. That is a **relationship between two containers**, completely different from `parent="sharedTemplate"` in XML. Do not see the word `parent` and assume both mechanisms share the same bean lookup or scope management behavior.

### Bean Definition Inheritance Does Not Mean Java Property Inheritance

When a child definition inherits a property `retries=3`, it receives a **configuration value** that the container will apply to the child object. Its Java class **does not automatically gain a `retries` field**: the class must still declare/support that property. If `SmsSettings` lacks `setRetries` or a corresponding binding mechanism, do not expect XML to inject a field into bytecode.

## 8. One More Example Without XML to Clarify the Boundary

Java class inheritance works entirely on its own in a program with no Spring at all:

~~~java
// Standalone Java file: PureJavaInheritance.java
public class PureJavaInheritance {
    static class BasePolicy {
        int retries() {
            return 3;
        }
    }

    static class UrgentPolicy extends BasePolicy {
        @Override
        int retries() {
            return 5;
        }
    }

    public static void main(String[] args) {
        BasePolicy ordinary = new BasePolicy();
        BasePolicy urgent = new UrgentPolicy();

        System.out.println("ordinary=" + ordinary.retries());
        System.out.println("urgent=" + urgent.retries());
        System.out.println("isSubclass=" + (urgent instanceof BasePolicy));
    }
}
~~~

**Java 17+ run commands without Maven or Spring** (from the directory containing the file):

~~~bash
javac PureJavaInheritance.java
java PureJavaInheritance
~~~

**Exact stdout:**

~~~text
ordinary=3
urgent=5
isSubclass=true
~~~

Here Java `extends` and **dynamic method dispatch** explain the entire result. There is no `ApplicationContext`, `BeanDefinition`, `parent="..."`, XML, or container. If you want to use `UrgentPolicy` as a Spring bean, you **must still register it** via an appropriate mechanism.

**Connecting the two examples:** Java inheritance primarily serves type/behavior relationships; Spring bean definition inheritance primarily serves metadata reuse when creating one or more beans. Avoid treating either mechanism as if it performs both roles automatically.

## 9. Common Mistakes When Configuring Bean Definition Inheritance

| Symptom or False Assumption | Cause / Correct Understanding |
| --- | --- |
| `getBean("sharedTemplate")` throws an error | The template has `abstract="true"`; it is not a bean to instantiate |
| Forgetting `abstract="true"` on a classless template | The context may try to process a bean lacking a class/factory, causing bootstrap failure |
| Child specifies `parent="sharedTemplate"` but the name does not exist | Parent bean definition was not registered or the referenced name is wrong |
| Child changes class but lacks a setter for an inherited property | Merged metadata is incompatible with the instantiated Java class |
| Thinking `parent="..."` creates a Java `extends` | XML does not modify the type hierarchy or bytecode |
| Thinking Java `extends` automatically copies bean properties from another Spring definition | Java inherits members, whereas Spring metadata must be declared/merged separately |
| Thinking two children with the same parent share an instance | They have separate bean definitions/scopes |
| Reading raw `getBeanDefinition`, seeing a missing property, and assuming config is broken | Inspect the **merged definition** or instance; the child may inherit the property from the parent |
| Assuming all flags like `lazy-init` inherit verbatim | Each metadata group has its own merge/override rules |
| Using `abstract="true"` yet expecting `getBean` on the template to work | Abstract templates are designed for inheritance, not to be used as an instance |
| Confusing parent definition with parent context | One is a metadata relationship; the other is a hierarchy between IoC containers |
| Overusing multi-level XML inheritance | Hard to read and predict overrides; consider simpler ways to express configuration |

**When debugging:** check the parent name, XML registration, `getParentName()`, raw/merged data, actual class and compatible setters, scope/lazy settings, and the full exception cause chain. Avoid changing multiple things at once or enabling bean-definition overriding just to mask errors.

### When to Use It, and When Not To

Bean definition inheritance is useful when many beans share **genuinely identical configuration**, especially in XML systems with repetitive metadata. However, it creates an implicit configuration coupling: changing the template can affect all children, so documentation and tests are essential.

In modern Java configuration projects, configuration can be reused via factory methods, parameterization, and component composition instead of forcing an XML inheritance model everywhere. `@Bean` methods in Java configuration **do not automatically** acquire `parent` metadata merely because the Java config class uses `extends`. Choose the clearest mechanism for your team and system requirements.

## 10. Prediction Exercises Before Running

Make each change on a clean copy, restoring the original XML/source between exercises to compare stdout:

1. Change `sharedTemplate.retries` from `3` to `8`. Predict `email.retries=8` while `sms.retries=5` keeps its override.
2. Add property `enabled=true` to the template **without** adding a matching setter to `EmailSettings` and `SmsSettings`. Explain why bean creation fails rather than the Java classes generating fields.
3. Remove `parent="sharedTemplate"` from `emailSettings`. Predict `email.endpoint` and `email.retries` when they are not declared separately (Java defaults).
4. Remove `abstract="true"` from the classless template. Observe the configuration error when the context tries to process the template.
5. Make `SmsSettings` a Java subclass of `EmailSettings` while keeping the XML unchanged. State which part of the outcome reflects Java subtyping and which still reflects metadata merging.
6. Add `parent="sharedTemplate"` to `urgentEmail` and remove duplicate properties. Predict both inheritance mechanisms working together, while XML parent still is not a Java superclass.
7. Change `smsSettings` to `prototype` scope and call `getBean` twice; distinguish **instance count** from shared template metadata.
8. Use `getMergedBeanDefinition("smsSettings")` to observe the overridden `retries` value compared to the raw definition.
9. Create another child using `parent="sharedTemplate"` whose class lacks `setEndpoint`. Predict the exception when applying the inherited property.
10. Change `UrgentEmailSettings extends EmailSettings` into a non-extending class that declares the same setters; predict how `instanceof EmailSettings` changes while the definition's parent metadata (none) remains unchanged.

### Lesson Completion Checklist

- [ ] State clearly that **bean definition inheritance = configuration metadata inheritance**, whereas Java inheritance = member inheritance/subtype relationship.
- [ ] Explain XML `parent`, `abstract="true"`, property overrides, and raw vs. merged definitions.
- [ ] Show why two classes that do not `extend` each other can still inherit from the same bean template.
- [ ] Show that a Java subclass can be a Spring bean **without** a parent bean definition.
- [ ] Know that an abstract parent template **cannot** be retrieved as a bean instance.
- [ ] Know that Spring does not automatically add Java setters/fields when inheriting property metadata.
- [ ] Distinguish `getBeanDefinition`, `getMergedBeanDefinition`, and `getBean`.
- [ ] Run both the Spring Maven demo (16 lines of stdout) and plain Java (3 lines of stdout) on Java 17+.

## 11. Summary and Reference Documentation

**One sentence to remember:** Bean definition inheritance reuses **"configuration recipes"**; Java class inheritance reuses **"program types and behavior"**. They can be combined, yet **they do not replace each other**.

- XML `parent="sharedTemplate"` inherits property values and applicable metadata to create **child beans**.
- `abstract="true"` on a template marks a definition **not to be instantiated on its own**; it does not mean the bean class is a Java `abstract class`.
- `class UrgentEmailSettings extends EmailSettings` is a **Java subtype** relationship and does not require a parent bean definition.
- A child can override configuration values **without** overriding any Java method; conversely, overriding a Java method does not automatically alter XML properties.
- Use `getMergedBeanDefinition` when you need to inspect post-merge metadata, rather than mistaking raw child metadata for the final configuration.

Official documentation:
- [Spring Framework – Bean Definition Inheritance](https://docs.spring.io/spring-framework/reference/core/beans/child-bean-definitions.html)
- [Spring Framework – Bean Overview](https://docs.spring.io/spring-framework/reference/core/beans/definition.html)
- [Spring Framework – XML-based Metadata](https://docs.spring.io/spring-framework/reference/core/beans/basics.html)
- [Spring – Bean Scopes](https://docs.spring.io/spring-framework/reference/core/beans/factory-scopes.html)
- [Spring – Java-based Container Configuration](https://docs.spring.io/spring-framework/reference/core/beans/java.html)
- [Java Language Specification – Classes](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html)
- [Spring Framework 7.0 Release Notes](https://github.com/spring-projects/spring-framework/wiki/Spring-Framework-7.0-Release-Notes)

**Conclusion:** Whenever you see `parent` in a Spring configuration, ask whether it is a **parent bean definition** or a **Java superclass**. Only by separating those two relationships properly can you accurately predict how Spring merges configuration, creates beans, applies setters, and distinguishes metadata from actual objects.