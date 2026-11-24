# Null Values, Nested Collections, and Inner Beans in Spring XML

## 1. Context and Objectives

The Spring Core Container allows declaring not only simple beans of the form `<bean id="..." class="..."/>`, but also **null values**, **nested collection structures**, and **beans defined directly inside a property or constructor argument**. These techniques are helpful when integrating legacy Java libraries, configuring rule sets, or wiring object graphs in XML without adding Java configuration classes.

Example:

```xml
<bean id="notificationPlan" class="demo.NotificationPlan">
    <constructor-arg index="0"><null/></constructor-arg>
    <constructor-arg index="1">
        <map>
            <entry key="weekday">
                <list>
                    <value>email</value>
                    <value>sms</value>
                </list>
            </entry>
        </map>
    </constructor-arg>
    <constructor-arg index="2">
        <bean class="demo.Contact">
            <constructor-arg value="ops@example.test"/>
        </bean>
    </constructor-arg>
</bean>
```

This is a **structural illustration**, where `NotificationPlan` and `Contact` are two Java types that must be defined with compatible constructors. A complete, compilable/runnable version with Java 17 and Spring Framework 6.2 appears in the hands-on section.

### Learning Objectives

After this lesson, you will be able to:

1. Distinguish `<null/>` from an empty string, the literal string `"null"`, an unconfigured property, and XML `xsi:nil`.
2. Assign `null` via `<constructor-arg>`, `<property>`, inside `<list>`, `<map>`, and compatible collections.
3. Configure `<list>`, `<set>`, `<map>`, and `<props>` with nested elements; understand `<value>`, `<ref>`, `<bean>`, and `<null>`.
4. Explain how Spring uses generic types such as `Map<String, List<String>>` to assist data conversion during injection.
5. Understand inner beans: a bean defined directly inside another bean, **anonymous**, **not independently addressable by ID**, and created alongside the enclosing bean.
6. Distinguish an inner bean from a top-level bean + `ref`; understand interactions with scope and lifecycle.
7. Build a complete XML configuration with `null`, a map containing lists, a list containing lists, and an inner bean.
8. Diagnose XML errors related to structure/schema, nullability, type conversion, missing dependencies, and collection merging.

## 2. Three Layers to Distinguish

When Spring reads XML, data flows across three layers:

```text
XML resource
    |
    +--> <bean>          : bean definition
    +--> <constructor-arg> / <property> : injection point
    +--> <null/> / <list/> / <map/> ... : value metadata
    |
    v
BeanDefinition / PropertyValue / ConstructorArgumentValues
    |
    v
BeanFactory resolves dependencies + converts types
    |
    v
Java object and its data fields
```

During parsing, a `<list>` element is not necessarily an actual `ArrayList` yet; it can be represented as managed collection metadata. When the bean is instantiated, Spring resolves references, inner bean definitions, and nested values, and converts them to match the constructor parameter or setter type.

**Key point:** XML metadata declares the *input values of the object graph*, rather than changing the Java contract itself. If a Java constructor forbids `null`, XML `<null/>` does not make it valid.

## 3. `<null/>`: Genuine Java `null`

To pass a `null` value to a constructor:

```xml
<bean id="userProfile" class="com.example.UserProfile">
    <constructor-arg index="0">
        <null/>
    </constructor-arg>
</bean>
```

Assuming the class has constructor `UserProfile(String nickname)`, Spring passes the Java reference `null` as the first argument.

### 3.1. Four Very Different States

| XML or situation | Meaning |
| --- | --- |
| `<constructor-arg><null/></constructor-arg>` | Explicit Java `null`. |
| `<constructor-arg value=""/>` | Empty string `""`, not `null`. |
| `<constructor-arg value="null"/>` | Four-character string `n`, `u`, `l`, `l`, unless custom conversion logic says otherwise. |
| No constructor arg declared | Supplies no value at that position; Spring must choose a constructor and resolve remaining parameters via metadata/infrastructure. Does not mean auto-filling `null`. |

For setter/property injection, “omitting `<property>`” preserves the default value set by the constructor or field initializer; “declaring `<property><null/></property>`” explicitly requests writing `null` to the property.

### 3.2. Property Setter Receiving `null`

```java
package com.example;

public class MailSettings {
    private String replyTo = "noreply@example.test";

    public void setReplyTo(String replyTo) {
        this.replyTo = replyTo;
    }

    public String getReplyTo() {
        return replyTo;
    }
}
```

If XML does not configure `replyTo`, the field retains its default value. If you use:

```xml
<bean id="mailSettings" class="com.example.MailSettings">
    <property name="replyTo"><null/></property>
</bean>
```

Spring calls the setter with `null`. This **differs** from:

```xml
<property name="replyTo" value=""/>
```

because the latter specifies an empty string.

### 3.3. Primitive Types Do Not Accept `null`

```java
public final class RetrySettings {
    public RetrySettings(int attempts) {
    }
}
```

With constructor parameter `int attempts`, XML `<null/>` cannot produce a valid `int` value. Spring throws a bean-creation / mismatch error while resolving constructor arguments. If expressing “no value” is a valid requirement, consider `Integer` or a descriptive model like `Optional` in the Java layer, configured per the specific contract.

**Note on `Optional`:** do not assume `<null/>` automatically equals `Optional.empty()` for every constructor. Conversion, resolution, and factory/constructor signatures must be designed explicitly.

### 3.4. `null` and Validation

Annotations like `@NotNull` belong to the validation stack when a compatible provider and validation mechanism are present; they do not stop the XML parser from reading `<null/>`. A constructor checking `Objects.requireNonNull(...)` will throw an exception when Spring instantiates the bean unless other conversion or configuration applies.

Therefore, before passing `null` into an object, check:

- Is the Java parameter/field nullable by contract?
- Is a default set in the constructor?
- Is there fallback logic if `null` is passed?
- Does a validation or lifecycle callback enforce non-null?
- Should an error be caught at startup or at runtime?

## 4. `null` Inside Collections

Spring collection elements can contain `<null/>`:

```xml
<property name="fallbacks">
    <list>
        <value>primary</value>
        <null/>
        <value>secondary</value>
    </list>
</property>
```

This example sits inside a `<bean>` with a matching `fallbacks` property. If Java receives `List<String>`, the middle element is normally Java `null`. Some Java APIs disallow `null` in collections, so XML accepting the syntax does not mean the consumer accepts the semantics.

A `null` map value can be declared as:

```xml
<property name="thresholds">
    <map>
        <entry key="low" value="10"/>
        <entry key="unknown">
            <null/>
        </entry>
    </map>
</property>
```

This example requires a setter or constructor accepting a map with a nullable value type, such as `Map<String, Integer>`. `unknown` exists as **a map key with a `null` value**, unlike the key being absent from the map. In code, use `containsKey("unknown")` to distinguish the two cases.

### `null` in XML Is Not `xsi:nil` by Default

Do not take syntax from JAXB/XML Schema nillable elements and apply it mechanically to Spring Bean XML. In Spring's `beans` namespace, the explicit way to supply `null` in a value position is `<null/>`.

## 5. Basic Collection Elements

Spring XML can populate Java collections via:

| Element | Typical Java contract | Characteristics |
| --- | --- | --- |
| `<list>` | `List<T>` | Ordered; allows duplicate elements. |
| `<set>` | `Set<T>` | No duplicate elements by equality semantics; do not rely on order without a specific contract. |
| `<map>` | `Map<K,V>` | Key-value pairs; unique keys. |
| `<props>` | `java.util.Properties` | Property keys and values primarily as `String`. |
| `<array>` | Java array | Useful when an API requires an array; `<list>` can also be converted by Spring when compatible. |

**Note:** Collection types may be represented by Spring's internal managed metadata during parsing and converted into a suitable implementation at injection time; do not write logic relying on a concrete implementation like `LinkedHashMap` merely because you observed it in one run.

### 5.1. List

```xml
<property name="servers">
    <list>
        <value>primary.example.test</value>
        <value>backup.example.test</value>
        <value>backup.example.test</value>
    </list>
</property>
```

A `List<String>` Java property receives elements in order; duplicate strings can appear.

### 5.2. Set

```xml
<property name="regions">
    <set>
        <value>ap-southeast-1</value>
        <value>eu-west-1</value>
    </set>
</property>
```

If the Java property is `Set<String>`, business logic should not rely on positional indexing like `get(0)` (since `Set` has no index). In logs or tests, sort if deterministic output is required.

### 5.3. Map

```xml
<property name="timeouts">
    <map>
        <entry key="connect" value="500"/>
        <entry key="read" value="2000"/>
    </map>
</property>
```

If the setter accepts `Map<String,Integer>`, the conversion service/type conversion infrastructure can convert `"500"` and `"2000"` into `Integer`. If the numeric format is invalid, Spring reports an error during bean creation/injection.

### 5.4. Properties

```xml
<property name="mailSettings">
    <props>
        <prop key="mail.host">smtp.example.test</prop>
        <prop key="mail.protocol">smtp</prop>
    </props>
</property>
```

`<props>` binds to `java.util.Properties`. When you need nested objects or non-string values, use `<map>` instead of forcing everything into `Properties`.

### 5.5. Elements Allowed Inside Collections

Inside a list, set, or map value, Spring XML supports structures such as:

- `<value>`: literal value; converted on injection according to target type.
- `<ref bean="..."/>`: references a registered top-level bean or alias.
- `<bean class="...">`: creates an **inner bean** at that element position.
- `<null/>`: Java `null`.
- `<list>`, `<set>`, `<map>`, `<props>`: nested collection.
- `<idref bean="..."/>`: a validated **String bean name**, not an object reference.

Distinguish `<idref/>` from `<ref/>`: the former produces a string identifier, whereas the latter resolves the bean object.

## 6. Nested Collections: List in Map, Map in List

A notification routing application might require:

```java
Map<String, List<String>> channelsByDay;
```

XML:

```xml
<property name="channelsByDay">
    <map>
        <entry key="weekday">
            <list>
                <value>email</value>
                <value>sms</value>
            </list>
        </entry>
        <entry key="weekend">
            <list>
                <value>push</value>
            </list>
        </entry>
    </map>
</property>
```

Here, two `<list>` elements sit inside two `<entry>` elements of `<map>`. This is a **collection of collections**, not two bean definitions. Spring builds/resolves the nested values and converts them to the target type `Map<String,List<String>>`.

### 6.1. List Containing Lists

```xml
<property name="stages">
    <list>
        <list>
            <value>validate</value>
            <value>build</value>
        </list>
        <list>
            <value>deploy</value>
        </list>
    </list>
</property>
```

The Java target `List<List<String>>` has two elements: the first inner list contains `validate` and `build`; the second contains `deploy`. Distinguish this from a flat list of three strings.

### 6.2. Map Inside Map

```xml
<property name="routes">
    <map>
        <entry key="internal">
            <map>
                <entry key="primary" value="host-internal"/>
            </map>
        </entry>
        <entry key="external">
            <map>
                <entry key="primary" value="host-public"/>
            </map>
        </entry>
    </map>
</property>
```

A Java property of type `Map<String,Map<String,String>>` can receive this structure. If nesting becomes deep, consider a named configuration class with validation rather than hard-to-maintain multi-level XML.

### 6.3. Beans Inside Collections

```xml
<property name="handlers">
    <list>
        <bean class="com.example.EmailHandler"/>
        <ref bean="sharedSmsHandler"/>
    </list>
</property>
```

The first element is an **inner bean definition**, while the second is a **reference to another bean registered in the container**. If `handlers` accepts `List<Handler>`, both must be valid implementations. Never infer that every element in a list is automatically a managed top-level bean with an independent lookup name.

### 6.4. Nested Values Are Not Always Nested Beans

`<map><entry><list>...</list></entry></map>` creates nested *collection values* rather than a separate bean definition for each list. Only a `<bean>` placed inside `<property>` or `<constructor-arg>` is an **inner bean**. Do not call every nested XML element a bean.

## 7. Map Entries: `value`, `value-ref`, and Child Elements

These two forms have different meanings:

```xml
<entry key="clientName" value="httpClient"/>
```

stores the string **literal** `httpClient`.

```xml
<entry key="clientObject" value-ref="httpClient"/>
```

looks up the bean named `httpClient` to use its **object reference** as the value.

Nested form equivalent to `value-ref`:

```xml
<entry key="clientObject">
    <ref bean="httpClient"/>
</entry>
```

With `key-ref`, the key can also be a bean reference; use this when the key type is actually an object rather than a `String`. If the configuration only needs `String` keys, `key="..."` is simpler and clearer.

### `null` Value Entry in a Map

```xml
<entry key="disabled">
    <null/>
</entry>
```

Differs from omitting `disabled` from the map altogether. If business logic uses `get("disabled") == null`, both cases still need `containsKey` to tell them apart when necessary.

### Maps with Duplicate Keys

A map inherently holds one value per key by equality. Repeating a key in XML can trigger overwrite or validation behavior depending on the parser and data. Do not rely on entry order as an override policy; keep keys unique or merge collections under explicit rules.

## 8. Generic Types and Element Conversion

Spring leverages generic type information on constructors and setters when Java metadata provides it:

```java
public final class RetryPolicy {
    private final Map<String, Integer> attempts;

    public RetryPolicy(Map<String, Integer> attempts) {
        this.attempts = attempts;
    }
}
```

An XML config:

```xml
<bean id="retryPolicy" class="com.example.RetryPolicy">
    <constructor-arg>
        <map>
            <entry key="read" value="3"/>
            <entry key="write" value="5"/>
        </map>
    </constructor-arg>
</bean>
```

can convert string values to `Integer` thanks to the target constructor signature `Map<String,Integer>`. This type conversion capability is documented by Spring for strongly typed collections. If the string were `"many"`, `Integer` conversion would fail and bean creation would error out.

### Common Risks

- Java uses raw `Map` or `List`, losing generic type metadata.
- A nested list mixes `String` and bean objects even though the target is `List<String>`.
- Code assumes keys are always `String` when XML declares `key-ref`.
- A custom converter is not registered or produces unexpected conversion output.
- The Java field is `Map<String,List<Integer>>` while XML contains unparseable words.
- Consumers mutate a collection after injection without clear ownership or thread safety.

**Recommendation:** prefer specific generic types on constructors/setters, validate inputs early, and test bean creation with nested structures.

## 9. What Is an Inner Bean?

A bean placed directly inside a `<property>` or `<constructor-arg>` of another bean:

```xml
<bean id="mailDispatcher" class="com.example.MailDispatcher">
    <constructor-arg>
        <bean class="com.example.DeliveryContact">
            <constructor-arg value="ops@example.test"/>
        </bean>
    </constructor-arg>
</bean>
```

is an **inner bean**. It is appropriate when the collaborator:

- belongs solely to the enclosing bean;
- needs no public bean name;
- does not need to be reused independently by multiple consumers;
- has a lifecycle tied to creating the enclosing bean;
- makes the object graph easier to read for small configurations.

According to Spring documentation, inner beans are **anonymous**; even if you provide `id` or `name`, the container does not use them as standalone lookup identifiers. Any `scope` declared on an inner bean is also ignored so that the inner bean is created with its enclosing bean.

### 9.1. Why Is No `id` Needed?

```xml
<bean id="dispatcher" class="com.example.Dispatcher">
    <property name="contact">
        <bean class="com.example.Contact"/>
    </property>
</bean>
```

This is an inner bean created to inject into `dispatcher.contact`. It does not appear as a top-level bean named `contact` merely because the property has that name.

### 9.2. What If an Inner Bean Has an `id`?

```xml
<bean id="dispatcher" class="com.example.Dispatcher">
    <property name="contact">
        <bean id="embeddedContact" class="com.example.Contact"/>
    </property>
</bean>
```

In Spring XML, `embeddedContact` **does not become a public name usable with `getBean("embeddedContact")`** . The inner bean is still treated as an internal definition, not registered as a top-level lookup name.

**Do not write:** “Give the inner bean an ID and then `ref` it from another bean.” If multiple consumers need to share the same collaborator, use a **top-level bean + `ref`**.

### 9.3. Scope of an Inner Bean

Spring documentation explicitly states that inner beans are **always anonymous and always created with the outer bean**, and `scope` on an inner bean is ignored.

This means:

- An outer **singleton** is constructed once → its inner collaborator is normally created when the outer bean is built and held inside it.
- An outer **prototype** is created across multiple lookups → each outer instance typically receives a newly created inner collaborator alongside it.
- Putting `scope="singleton"` or `scope="prototype"` on an inner bean does not create an independent public scoped bean.

Certain custom scopes can have special destruction callback interactions; do not assume every inner bean across all custom scopes has identical destruction behavior to a top-level bean. Design resource ownership carefully and test the specific lifecycle.

## 10. Inner Bean vs. Top-Level `ref`: Comparison

| Criterion | Inner bean | Top-level bean + `ref` |
| --- | --- | --- |
| Placement | `<bean>` nested inside property/constructor arg | `<bean id="...">` directly under `<beans>` |
| Public name | None | Has `id`/`name`/aliases |
| Independent lookup | No | Yes |
| Shareable across multiple consumers | Not via the same public bean definition | Yes, when scope and wiring match |
| Scope | Bound to outer bean creation; internal scope flag is ignored | Follows the bean definition's own scope |
| Co-located with owner | Clear if collaborator is used in only one place | Clear if collaborator is a shared resource |
| Independently testable by bean name | No | Yes |
| Lifecycle | Created when outer is created; note custom destruction edge cases | Managed independently by BeanFactory per scope |

### When Is a Top-Level Bean Appropriate?

```xml
<bean id="sharedContact" class="com.example.Contact">
    <constructor-arg value="shared@example.test"/>
</bean>

<bean id="dispatcherA" class="com.example.Dispatcher">
    <constructor-arg ref="sharedContact"/>
</bean>

<bean id="dispatcherB" class="com.example.Dispatcher">
    <constructor-arg ref="sharedContact"/>
</bean>
```

Both consumers can receive the same `sharedContact` singleton. Replacing `ref` with separate inner `<bean>` elements in each consumer creates two distinct internal collaborator definitions.

### When Is an Inner Bean Appropriate?

A small formatter attached to a single parser, or a local strategy attached to one service without reuse needs, fits well as an inner bean. However, if an object holds a database connection pool, thread executor, SDK client with complex shutdown, or is shared across modules, a top-level bean with clear ownership is better.

## 11. Runnable Java 17+ Example: `null`, `Map<List>`, `List<List>`, and Inner Bean

This example **needs no Spring Boot**, uses no annotation configuration, and makes no network or database connections. It uses **Spring Framework 6.2.9** and **`ClassPathXmlApplicationContext`**.

We define:

- `ReleasePlan`: accepts nullable `String note`; `Map<String,List<String>> channels`; `List<List<String>> stages`; `Contact contact`.
- `Contact`: plain Java class containing an email.
- Bean `releasePlan` using XML constructor arguments and an inner `Contact`.
- Bean `sharedContact` at top level to contrast with the inner bean.
- `main` printing checks with deterministic stdout.

### 11.1. Project Structure

```text
spring-xml-values-demo/
├── settings.gradle
├── build.gradle
└── src/
    └── main/
        ├── java/
        │   └── demo/
        │       ├── Contact.java
        │       ├── ReleasePlan.java
        │       └── XmlValuesDemo.java
        └── resources/
            └── beans.xml
```

There are three public top-level Java classes, with filenames matching class names. XML lives at `src/main/resources/beans.xml` so Gradle puts it on the classpath.

### 11.2. Gradle

**`settings.gradle`**

```groovy
rootProject.name = 'spring-xml-values-demo'
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
    mainClass = 'demo.XmlValuesDemo'
}
```

Spring Context pulls in Spring Beans/Core and necessary dependencies. Java 17+ is compatible with Spring Framework 6.2. This is a **standalone project**, needing no wrapper if Gradle is already installed; if a wrapper exists, run the corresponding wrapper command.

### 11.3. `Contact.java`

**`src/main/java/demo/Contact.java`**

```java
package demo;

import java.util.Objects;

public final class Contact {
    private final String email;

    public Contact(String email) {
        this.email = Objects.requireNonNull(email);
    }

    public String email() {
        return email;
    }
}
```

The constructor requires a non-null email. XML provides a valid string.

### 11.4. `ReleasePlan.java`

**`src/main/java/demo/ReleasePlan.java`**

```java
package demo;

import java.util.List;
import java.util.Map;
import java.util.Objects;

public final class ReleasePlan {
    private final String note;
    private final Map<String, List<String>> channels;
    private final List<List<String>> stages;
    private final Contact contact;

    public ReleasePlan(
            String note,
            Map<String, List<String>> channels,
            List<List<String>> stages,
            Contact contact) {
        this.note = note; // nullable according to the example contract
        this.channels = Objects.requireNonNull(channels);
        this.stages = Objects.requireNonNull(stages);
        this.contact = Objects.requireNonNull(contact);
    }

    public String note() {
        return note;
    }

    public Map<String, List<String>> channels() {
        return channels;
    }

    public List<List<String>> stages() {
        return stages;
    }

    public Contact contact() {
        return contact;
    }
}
```

This structure is immutable in terms of **references** (`final` fields). It **does not guarantee deeply immutable collections**, because the passed-in `Map`/`List` instances may still be mutable. In production, make defensive and nested immutable copies if needed, though that does not change XML's ability to inject them.

### 11.5. Complete `beans.xml`

**`src/main/resources/beans.xml`**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<beans xmlns="http://www.springframework.org/schema/beans"
       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
       xsi:schemaLocation="
           http://www.springframework.org/schema/beans
           https://www.springframework.org/schema/beans/spring-beans.xsd">

    <!-- A top-level Contact that can be looked up by name. -->
    <bean id="sharedContact" class="demo.Contact">
        <constructor-arg value="shared@example.test"/>
    </bean>

    <bean id="releasePlan" class="demo.ReleasePlan">

        <!-- Constructor arg #0: Java null, not the string "null". -->
        <constructor-arg index="0">
            <null/>
        </constructor-arg>

        <!-- Constructor arg #1: Map<String, List<String>>. -->
        <constructor-arg index="1">
            <map>
                <entry key="weekday">
                    <list>
                        <value>email</value>
                        <value>sms</value>
                    </list>
                </entry>
                <entry key="weekend">
                    <list>
                        <value>push</value>
                    </list>
                </entry>
            </map>
        </constructor-arg>

        <!-- Constructor arg #2: List<List<String>>. -->
        <constructor-arg index="2">
            <list>
                <list>
                    <value>validate</value>
                    <value>build</value>
                </list>
                <list>
                    <value>deploy</value>
                </list>
            </list>
        </constructor-arg>

        <!-- Constructor arg #3: inner bean not addressable by ID. -->
        <constructor-arg index="3">
            <bean id="embeddedContact" class="demo.Contact">
                <constructor-arg value="ops@example.test"/>
            </bean>
        </constructor-arg>

    </bean>
</beans>
```

There are **two top-level `<bean>` declarations**: `sharedContact` and `releasePlan`. `<bean id="embeddedContact">` is **nested inside** the constructor argument, so it is an anonymous inner bean; Spring does not register it as a top-level bean addressable by ID `embeddedContact`.

### 11.6. Main Class

**`src/main/java/demo/XmlValuesDemo.java`**

```java
package demo;

import org.springframework.context.support.ClassPathXmlApplicationContext;

public final class XmlValuesDemo {
    public static void main(String[] args) {
        try (ClassPathXmlApplicationContext context =
                     new ClassPathXmlApplicationContext("beans.xml")) {

            ReleasePlan plan =
                    context.getBean("releasePlan", ReleasePlan.class);
            Contact shared =
                    context.getBean("sharedContact", Contact.class);

            System.out.println("note-null="
                    + (plan.note() == null));

            System.out.println("weekday-channels="
                    + String.join(",", plan.channels().get("weekday")));

            System.out.println("weekend-channels="
                    + String.join(",", plan.channels().get("weekend")));

            System.out.println("stages-count="
                    + plan.stages().size());

            System.out.println("stage-order="
                    + plan.stages().get(0).get(1) + ">"
                    + plan.stages().get(1).get(0));

            System.out.println("inner-email="
                    + plan.contact().email());

            System.out.println("inner-lookup-visible="
                    + context.containsBean("embeddedContact"));

            System.out.println("inner-is-shared="
                    + (plan.contact() == shared));

            System.out.println("release-plan-singleton="
                    + (plan == context.getBean(ReleasePlan.class)));

            System.out.println("top-level-definitions="
                    + context.getBeanDefinitionCount());
        }
    }
}
```

### 11.7. Compile and Run

From the `spring-xml-values-demo` directory:

```bash
gradle run --quiet
```

If the project has a Gradle Wrapper:

```bash
./gradlew run --quiet
```

On Windows, use `gradlew.bat run --quiet`. You cannot compile `XmlValuesDemo.java` alone with `javac` without putting Spring libraries on the compile classpath and compiling the other source files; Gradle handles both classpath setup and resource copying.

### 11.8. Program Stdout

```text
note-null=true
weekday-channels=email,sms
weekend-channels=push
stages-count=2
stage-order=build>deploy
inner-email=ops@example.test
inner-lookup-visible=false
inner-is-shared=false
release-plan-singleton=true
top-level-definitions=2
```

These are the lines produced by the `System.out.println` calls in the example. Any other Gradle or runtime logs are outside this output.

### 11.9. Output Interpretation

- **`note-null=true`:** constructor argument 0 receives Java `null` because XML uses `<null/>`.
- **`weekday-channels=email,sms`:** key `weekday` holds a two-element list in the declared order.
- **`weekend-channels=push`:** key `weekend` holds a single-element list.
- **`stages-count=2`:** the outer list has two inner lists.
- **`stage-order=build>deploy`:** the first list is `[validate, build]` and the second is `[deploy]`, so index 1 of list 0 is `build` and index 0 of list 1 is `deploy`.
- **`inner-email=ops@example.test`:** Spring instantiated the inner `Contact` with its constructor argument.
- **`inner-lookup-visible=false`:** the `embeddedContact` name placed on the inner bean does not become a lookup-visible top-level bean ID.
- **`inner-is-shared=false`:** the top-level `sharedContact` and the inner collaborator are two distinct objects.
- **`release-plan-singleton=true`:** `releasePlan` uses the default singleton scope and was looked up twice in the same context.
- **`top-level-definitions=2`:** the pure XML context has exactly two top-level beans; the inner bean does not count as a top-level bean definition.

**Key verification point:** an inner bean can be validly instantiated and injected by Spring **even though it is not exposed as an independent bean name**.

## 12. Inner Beans Combined with Nested Collections

Inner beans do not appear only directly under `<property>` or `<constructor-arg>`; they can also sit inside collections passed as properties or arguments.

Example policy list:

```xml
<bean id="policyEngine" class="com.example.PolicyEngine">
    <constructor-arg>
        <list>
            <bean class="com.example.MinValuePolicy">
                <constructor-arg value="10"/>
            </bean>
            <bean class="com.example.MaxValuePolicy">
                <constructor-arg value="100"/>
            </bean>
        </list>
    </constructor-arg>
</bean>
```

This is an illustrative architectural snippet requiring the real classes and a constructor accepting `List<Policy>`. Each `<bean>` inside the list is an inner bean; the policies have no top-level names for other consumers to look up independently.

If a policy needs to be shared across multiple engines, define a top-level policy bean:

```xml
<bean id="sharedPolicy" class="com.example.SharedPolicy"/>

<bean id="policyEngine" class="com.example.PolicyEngine">
    <constructor-arg>
        <list>
            <ref bean="sharedPolicy"/>
        </list>
    </constructor-arg>
</bean>
```

`<ref>` links to the registered bean according to its scope; nesting `<bean>` at the usage site creates an inner definition.

### When Is a Nested Collection Too Deep?

If XML has so many layers of `<map>` and `<list>` that validation rules become unreadable, consider:

- a clearly named settings class instead of maps of maps;
- a Java configuration factory method returning a typed object;
- configuration properties mapping/binding per the stack in use;
- splitting XML resources along module boundaries;
- tests verifying structure and business invariants.

Nested collections are helpful for structured data, not for turning XML into a complex programming language.

## 13. Collection Merging in XML Bean Inheritance

Spring XML supports **merging** compatible collections when using parent/child bean definitions.

Example where property `rules` is `List<String>`:

```xml
<bean id="basePolicy"
      abstract="true"
      class="com.example.RuleConfig">
    <property name="rules">
        <list>
            <value>audit</value>
            <value>validate</value>
        </list>
    </property>
</bean>

<bean id="prodPolicy" parent="basePolicy">
    <property name="rules">
        <list merge="true">
            <value>enforce</value>
        </list>
    </property>
</bean>
```

This snippet requires a public `RuleConfig` class with `setRules(List<String>)` or a compatible property. `basePolicy` is marked abstract as a template definition; `prodPolicy` inherits its metadata and merges the list.

With `merge="true"` on the **child list**, the merged list in order is:

```text
audit
validate
enforce
```

Important point: merging must be enabled **on the child collection** in the inheriting bean definition. Putting the merge flag on the parent list does not produce the desired effect. You cannot merge collections of incompatible types, such as a parent `<map>` and a child `<list>`.

### Map, Set, and Props Merging

- **List:** keeps parent elements first, then appends child elements.
- **Map:** child keys can override parent keys.
- **Set:** merges elements under set semantics.
- **Properties:** child entries can override parent keys.

Do not design logic relying on iteration order of `Map`, `Set`, or `Properties` unless a contract guarantees it. Collection merging is a metadata inheritance mechanism, not Spring automatically merging arbitrary collections injected from unrelated beans.

### Do Not Confuse Merging with Nested Collections

`<list><list>...</list></list>` is a **list nested inside a list**. `<list merge="true">` in a child bean definition **merges parent and child collection metadata**. These are two separate mechanisms that can appear together without being synonymous.

## 14. `null` in a `Map` and Distinguishing Absent Keys

Example configuration map:

```xml
<property name="featureLimits">
    <map>
        <entry key="basic" value="10"/>
        <entry key="premium">
            <null/>
        </entry>
    </map>
</property>
```

Java code:

```java
Map<String, Integer> limits = settings.getFeatureLimits();

boolean premiumExplicitlyPresent =
        limits.containsKey("premium"); // true

Integer premium = limits.get("premium"); // null
Integer trial = limits.get("trial");     // null
```

This snippet is illustrative, assuming `settings` has an accessor returning `Map<String,Integer>`. Both `get()` calls return `null`, yet `premium` is a present key with a `null` value, whereas `trial` is an absent key. If the app uses `null` to mean “unlimited,” write clear validation and comments.

**Never try to force Java primitive `int` to hold `null`.** With map value type `Integer`, `null` can be valid by contract.

## 15. `null` vs. Empty Collections

The same `recipients` property has at least three distinct states:

**Unconfigured:**

```xml
<bean id="mailer" class="com.example.Mailer"/>
```

The Java property retains whatever default the constructor or field initializer establishes; Spring does not automatically infer an empty list.

**Configured as `null`:**

```xml
<bean id="mailer" class="com.example.Mailer">
    <property name="recipients"><null/></property>
</bean>
```

The setter receives Java `null` if the type permits it.

**Configured as an empty list:**

```xml
<bean id="mailer" class="com.example.Mailer">
    <property name="recipients"><list/></property>
</bean>
```

The setter receives an empty list instead of `null`. This is usually preferable if consumers iterate directly over `recipients`, though it must match the class contract.

**Common mistake:** `<list/>` is not `<null/>`; an empty collection object is not absence. In unit and integration tests, assert the exact state the business logic requires.

## 16. Bean Names, Aliases, and Inner Beans

### 16.1. Top-Level `id` and Alias

```xml
<bean id="supportContact" class="com.example.Contact"/>
<alias name="supportContact" alias="emergencyContact"/>
```

This is a top-level bean definition with an alias. Both names can be used via `<ref bean="..."/>` in the same context.

### 16.2. Inner Beans Do Not Appear as Aliases

```xml
<bean id="releasePlan" class="com.example.ReleasePlan">
    <property name="contact">
        <bean id="localContact" class="com.example.Contact"/>
    </property>
</bean>
```

`localContact` does not become a public alias or top-level definition just because it has an `id` attribute. You cannot expect `context.getBean("localContact")` to work. If it should be shared, move it to top level.

### 16.3. XML Resources and Context Boundaries

Loading two XML resources into one `ClassPathXmlApplicationContext` lets top-level bean definitions and aliases reference one another within that context's registry. Inner beans remain tied to their enclosing definitions.

Creating two separate contexts does not make an inner bean from context A visible in context B. Parent-child context hierarchies also do not turn an inner bean into a publicly addressable bean.

## 17. Lifecycle and Resources of Inner Beans

### 17.1. Are Inner Beans Created at XML Parse Time?

Not by default. The parser creates and records metadata. The inner bean instance is created when the outer bean is resolved/instantiated along the dependency graph; for an eager outer singleton, this normally happens during `refresh()`.

### 17.2. Does a `scope` Attribute on an Inner Bean Control Lookups?

No. The scope flag on an inner bean is ignored by Spring: the inner bean is created **with its enclosing bean**. An inner bean has no public bean name to pass to `getBean()` repeatedly, so it has no independent lookup semantics like a top-level prototype.

### 17.3. What About Initialization and Destruction Callbacks?

Spring can still run initialization and post-processing steps for container-created inner beans. However, do not assume every inner collaborator's destruction lifecycle behaves identically to an independent top-level singleton: documentation notes corner cases where custom scopes can receive destruction callbacks, whereas standard inner beans follow the outer bean's scope.

For resources requiring `close()`, thread pools, sockets, connection pools, or SDK clients, using a **top-level named bean** with an explicit init/destroy contract is much easier to govern. Do not assume inline declaration magically solves resource ownership.

### 17.4. What If the Outer Bean Is Prototype?

Each request for an outer prototype typically creates a new outer instance along with its inner dependencies. If you want multiple outer prototypes to share the same singleton collaborator, use a top-level singleton + `<ref>` instead of repeating an inner `<bean>`.

## 18. Common Pitfalls

### Pitfall 1 — Using the Literal `"null"` Instead of `null`

```xml
<constructor-arg value="null"/>
```

is the string `"null"` in typical cases. To pass Java `null`, use `<constructor-arg><null/></constructor-arg>`.

### Pitfall 2 — Passing `null` to a Primitive

`int`, `boolean`, and `long` cannot hold Java `null`. If optionality is valid, design wrapper types and validation intentionally.

### Pitfall 3 — Using `<value/>` to Represent an Empty Collection

`<value/>` is value metadata, not an empty list. Use `<list/>` when you want an empty `List`.

### Pitfall 4 — Confusing `ref` with `value`

`<ref bean="sharedClient"/>` is a managed dependency, whereas `<value>sharedClient</value>` is a string literal. This applies inside nested `<list>`/`<map>` as well.

### Pitfall 5 — Nested Collection Incompatible with Java Generic Type

The constructor expects `Map<String,List<Integer>>` while XML provides the words `email` and `sms`, causing a conversion failure when Spring creates the bean.

### Pitfall 6 — Mixing Element Types Unintentionally

A `List<String>` containing `<bean class="..."/>` may fail to convert cleanly to `String`. If a list needs heterogeneous objects, design a clear interface/record or matching target type.

### Pitfall 7 — Looking Up an Inner Bean via `getBean("id")`

An inner bean's ID is ignored as a standalone lookup name. Promote it to a top-level `<bean id>` and use `<ref>` if lookup by name is genuinely needed.

### Pitfall 8 — Trying to Set `scope="singleton"` to Share an Inner Bean

The scope on an inner bean does not behave like a top-level bean's scope. When a resource must be shared, a top-level singleton and `ref` is the proper design.

### Pitfall 9 — Thinking an Inner Bean Is the Same as a Nested Collection

`<list><list>...</list></list>` merely describes nested data without creating a bean definition per list. Only a nested `<bean>` is an inner bean.

### Pitfall 10 — Using an Inner Bean for Resources Needing Clear Ownership

A DB pool or client with complex shutdown should have top-level configuration and lifecycle management. Do not hide critical resources inside a constructor argument just to make XML shorter.

### Pitfall 11 — Placing Collection `merge` on the Parent

`merge="true"` must be placed on the inherited child collection. Setting the flag on the parent does not perform the intended merge.

### Pitfall 12 — Merging Incompatible Collection Types

A parent `<map>` and a child `<list merge="true">` cannot be merged via collection inheritance.

### Pitfall 13 — Assuming `Map`/`Set` Preserve Insertion Order Like `List`

`List` is ordered; `Map` and `Set` carry no general ordering guarantee for business contracts in their base abstractions. Use an explicitly ordered structure if required.

### Pitfall 14 — Failing to Distinguish a `null` Value from an Absent Key

`map.get(key)==null` does not tell you whether the key exists. Use `containsKey` if the semantics require distinguishing them.

### Pitfall 15 — Reading Only XML Without Checking Java Constructors

Valid XML parsing does not guarantee BeanFactory can construct the bean. Java parameter types, constructor overloads, null constraints, and validation can fail startup.

### Pitfall 16 — Wrong Namespace/Schema or Misplaced Nested Elements

`<null/>`, `<entry>`, `<list>`, and `<bean>` must appear in structures permitted by the Spring Beans XML schema. When the parser reports a validation error, check nesting before modifying Java code.

### Pitfall 17 — Expecting Configured Collections to Always Be Immutable

`final List` only fixes the reference. If immutable configuration is required, make deep defensive copies or use immutable records by design.

### Pitfall 18 — Overusing Deeply Nested XML Layers

Once XML turns into a map of maps of lists of maps, reading and testing it becomes costly. Consider Java configuration or typed properties with explicit schemas and validation.

## 19. Quick Verification Tests

### Testing `null`

After creating the context:

```java
ReleasePlan plan = context.getBean(ReleasePlan.class);
if (plan.note() != null) {
    throw new AssertionError("note must be null");
}
```

This snippet goes in the demo project where `context` is available. It verifies the **Java value**, not merely that XML contained `<null/>`.

### Testing Nested Collections

```java
if (!plan.channels().get("weekday")
        .equals(java.util.List.of("email", "sms"))) {
    throw new AssertionError("weekday channels");
}

if (!plan.stages().get(0).get(1).equals("build")) {
    throw new AssertionError("stage order");
}
```

Verify shapes across **multiple nesting levels**, rather than asserting only collection sizes.

### Testing Inner Beans

```java
if (context.containsBean("embeddedContact")) {
    throw new AssertionError("inner bean must not be top-level");
}

if (plan.contact() == context.getBean("sharedContact")) {
    throw new AssertionError("inner should be separate from shared contact");
}
```

These checks rely on the demo's XML. Deliberately placing `id="embeddedContact"` on the inner definition demonstrates that this ID does not become a public bean name.

### Testing Context Startup

If XML passes `null` to a non-null constructor, provides a wrongly typed nested value, or uses invalid schema nesting, an integration test loading `ClassPathXmlApplicationContext("beans.xml")` catches it early at startup.

## 20. Applied Exercises

### Exercise 1 — Distinguishing `null` from Empty String

Change:

```xml
<constructor-arg index="0"><null/></constructor-arg>
```

to:

```xml
<constructor-arg index="0" value=""/>
```

Prediction: `plan.note() == null` becomes `false`; `plan.note().isEmpty()` becomes `true`. Explain why this is a value change rather than an XML parsing issue.

### Exercise 2 — Map Containing a List with a `null` Element

Add:

```xml
<entry key="maintenance">
    <list>
        <value>email</value>
        <null/>
    </list>
</entry>
```

Verify `plan.channels().get("maintenance").size()==2` and index 1 is `null`. Note that `String.join` has its own semantics with `null` elements; do not extrapolate from the original demo's output when `null` elements are present.

### Exercise 3 — Replacing an Inner Bean with a Top-Level `ref`

Change constructor arg #3 of `releasePlan` to:

```xml
<constructor-arg index="3">
    <ref bean="sharedContact"/>
</constructor-arg>
```

Predict that `inner-is-shared` in the demo changes to `true` because `releasePlan` receives the top-level singleton `sharedContact` instead of creating an inner `Contact`.

### Exercise 4 — Adding a `Map` Layer Inside a `List`

Extend the Java model to accept `List<Map<String,String>>`, and configure a `<list>` containing multiple `<map>` elements. Assert keys/values in each map and explain how it differs from the existing `Map<String,List<String>>`.

### Exercise 5 — Experimenting with Collection Merging

Create an abstract parent bean definition with property `List<String> rules`, and a child with `<list merge="true">`. Verify parent items precede child items. Move `merge="true"` to the parent and compare results to see the semantics.

### Exercise 6 — Invalid Instantiation

Change `ReleasePlan` constructor parameter `note` from `String` to primitive `int` while keeping `<null/>`. Predict the bean creation failure and discuss how to design an optional numeric value safely.

## 21. Review Questions with Answers

**Q1.** How does `<null/>` differ from `value=""`?

**Answer:** `<null/>` produces Java `null`; `value=""` passes an empty string for a `String` target.

**Q2.** Which Java type matches XML `<map><entry key="x"><list>...</list></entry></map>`?

**Answer:** `Map<String,List<T>>` when element types match and conversion succeeds.

**Q3.** Does `<list><list>...</list></list>` create inner beans?

**Answer:** No. It creates nested collections. An inner bean requires a nested `<bean>` element.

**Q4.** Can an inner bean be retrieved via `getBean("embeddedContact")` if it has an `id`?

**Answer:** No. An inner bean's `id`/`name` does not become a public bean identifier.

**Q5.** Does a `scope` attribute on an inner bean control independent singleton/prototype lookups?

**Answer:** No. An inner bean is created with its enclosing bean and its internal scope flag is ignored.

**Q6.** How does referencing a top-level bean `sharedContact` twice via `ref` differ from declaring two inner beans?

**Answer:** If `sharedContact` is singleton, both references typically resolve to the same managed instance. Two separate inner definitions create collaborator instances per enclosing object.

**Q7.** Where is list `merge` placed?

**Answer:** On the child collection in the inheriting bean definition, not on the parent.

**Q8.** Can a parent map and a child list be merged?

**Answer:** No. Merging requires compatible collection types.

**Q9.** Is `<entry key="unknown"><null/></entry>` different from omitting that key?

**Answer:** Yes. In the first case `containsKey("unknown")` is `true` while `get` returns `null`; in the second case the key is absent.

**Q10.** Can Spring use Java generic types to convert string values into `Integer` inside collections?

**Answer:** Yes, when injection point metadata is clear and type conversion supports it. Malformed data still causes an error.

**Q11.** Are `<ref bean="sharedClient"/>` and `<value>sharedClient</value>` equivalent?

**Answer:** No. `ref` retrieves the bean object; `value` is a string literal.

**Q12.** If an outer singleton is created once, is the inner bean necessarily registered as a top-level singleton?

**Answer:** No. An inner bean is an anonymous definition created when the outer bean is built; it has no independent public bean ID.

**Q13.** Is a `final List` always immutable?

**Answer:** No. `final` only fixes the reference; list contents can still be modified if the implementation is mutable. Use defensive copies when needed.

**Q14.** Should you use an inner bean for a connection pool shared across the entire system?

**Answer:** Usually not. Use a top-level managed resource bean with clear lifecycle/ownership and inject it via `ref`.

## 22. Official Documentation

- [Spring Framework 6.2 — Dependencies and Configuration in Detail](https://docs.spring.io/spring-framework/reference/6.2/core/beans/dependencies/factory-properties-detailed.html): explains `<null/>`, inner beans, collections, nested values, collection merging, and strongly typed collections.
- [Spring Framework — Bean Overview](https://docs.spring.io/spring-framework/reference/core/beans/definition.html): `BeanDefinition`, bean metadata, and scopes.
- [Spring Framework — Bean Scopes](https://docs.spring.io/spring-framework/reference/core/beans/factory-scopes.html): singleton, prototype, and resource lifecycle.
- [Spring Framework — Dependencies](https://docs.spring.io/spring-framework/reference/core/beans/dependencies.html): constructor/property injection and reference semantics.
- [Spring Framework 6.2 Javadoc — ClassPathXmlApplicationContext](https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/context/support/ClassPathXmlApplicationContext.html): XML context bootstrap.
- [Spring Framework 6.2 Javadoc — BeanDefinition](https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/beans/factory/config/BeanDefinition.html): bean definition metadata.
- [Spring Framework — Type Conversion](https://docs.spring.io/spring-framework/reference/core/validation/convert.html): type conversion when binding/injecting values.

**Conclusion:** Spring XML describes not only bean names and classes, but also the **object value graph**. `<null/>` is genuine Java `null`, nested `<list>`/`<map>` express collection structures, and a nested `<bean>` creates an anonymous collaborator bound to its enclosing bean. To configure reliably, always check **Java constructor/setter types**, distinguish **inner beans from top-level `ref`**, and test **values, collection shapes, scopes, and lifecycles**.
