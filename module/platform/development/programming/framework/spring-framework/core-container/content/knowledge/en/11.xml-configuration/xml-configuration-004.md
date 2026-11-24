# Providing Properties via `<property>`, `value`, and `ref` in Spring XML

## 1. Why Does XML Need to Distinguish Values from Bean References?

In the Spring IoC Container, an XML bean definition describes how to create an object, which properties to configure, and which beans the object depends on. When using JavaBeans-style setter injection, the `<property>` element is the direct way to set a property after Spring creates the object.

The two most important forms:

```xml
<bean id="mailService" class="demo.MailService">
    <property name="senderName" value="System"/>
    <property name="repository" ref="mailRepository"/>
</bean>

<bean id="mailRepository" class="demo.InMemoryMailRepository"/>
```

This is an **illustrative snippet**, not runnable on its own without the two corresponding Java classes. It expresses two distinct actions:

- `value="System"`: passes a **text value** into property `senderName`, which Spring converts if the target requires a type other than `String`.
- `ref="mailRepository"`: looks up a **registered bean** named `mailRepository`, then passes a **reference to that object** into property `repository`.

When `MailService` defines `setSenderName(String)` and `setRepository(MailRepository)`, Spring invokes both setters after creating the service. If `mailRepository` is a singleton, the service is wired to that exact managed singleton, not a copy constructed from the string `"mailRepository"`.

Lesson objectives:

1. Understand `<bean>`/`<property>` syntax and the JavaBean property contract.
2. Use `value` for `String`, numbers, booleans, enums, and types with compatible converters/editors.
3. Use `ref` to wire beans together; understand bean names, aliases, scopes, and dependency initialization.
4. Know attribute forms, nested elements `<value/>`, `<ref/>`, `<idref/>`, `<null/>`, and inner beans.
5. Supply collections `<list/>`, `<set/>`, `<map/>`, and `<props/>` with values and bean references.
6. Compare `p:property`/`p:property-ref` with traditional `<property>` syntax.
7. Distinguish bean-creation-time injection, property placeholders, and Spring Expression Language.
8. Diagnose setter, type conversion, bean reference, schema, and circular dependency errors.
9. Run a complete Java 17+ example with Spring Framework 6.2 and XML, verifying results and identity.

## 2. Reading a `<property>` Element from the Inside Out

Configuration:

```xml
<bean id="reportService" class="demo.ReportService">
    <property name="title" value="Monthly"/>
</bean>
```

Meaning of each part:

| Part | Interpretation |
| --- | --- |
| `bean` | Declares a bean definition in the Spring XML beans namespace |
| `id="reportService"` | Name used to look up or `ref` the bean |
| `class="demo.ReportService"` | Class Spring loads and instantiates per the bean definition |
| `property` | A property on the newly created object to be configured |
| `name="title"` | JavaBean property name: typically corresponds to `setTitle(...)` |
| `value="Monthly"` | Literal value to be converted to the target property type if needed |

This configuration resembles the Java operations:

```java
ReportService service = new ReportService();
service.setTitle("Monthly");
```

The two snippets above are conceptual illustrations only. In practice, Spring also manages bean definitions, scopes, lifecycle callbacks, bean post-processors, and appropriate proxying. **Do not** treat XML property injection as a simple macro replacing every Spring mechanism with `new`.

### 2.1. A JavaBean Property Need Not Be a Public Field

Example class:

```java
package demo;

public class ReportService {
    private String title;

    public void setTitle(String title) {
        this.title = title;
    }

    public String getTitle() {
        return title;
    }
}
```

The setter `setTitle(String)` establishes a writable property named `title`, even though field `title` is `private`. Spring normally sets properties through the JavaBeans property descriptor / setter. Simply having a field named `title` without a suitable setter **is not sufficient** for a standard `<property name="title">`.

Having a `private` field does not make Spring injection impossible in general: annotation field injection and certain custom binding mechanisms behave differently. However, in **standard Spring XML `<property>` setter injection**, the first thing to verify is a **writable property**.

### 2.2. Distinguishing Constructor Injection and Setter Injection

Both approaches can express a dependency relationship, but at different times:

```xml
<!-- Constructor injection -->
<bean id="serviceA" class="demo.ServiceA">
    <constructor-arg ref="repository"/>
</bean>

<!-- Setter/property injection -->
<bean id="serviceB" class="demo.ServiceB">
    <property name="repository" ref="repository"/>
</bean>
```

With constructor injection, Spring must resolve the argument before invoking `ServiceA`'s constructor. With property injection, Spring constructs `ServiceB` first, then populates the `repository` property.

**Design:** Core dependencies without which an object cannot be valid usually fit constructor injection; setter injection fits auxiliary configuration, replaceable dependencies, or library classes designed around JavaBeans setters. Choosing between them depends on the actual class API and bean lifecycle, not a dogma that “all setters are bad.”

### 2.3. Does Spring XML Require `@Autowired`?

No. Bean definitions and property values in XML can be applied by Spring without any Spring annotations on the class.

```java
public class Sender {
    private String signature;
    public void setSignature(String signature) {
        this.signature = signature;
    }
}
```

Alongside:

```xml
<bean id="sender" class="demo.Sender">
    <property name="signature" value="Team"/>
</bean>
```

Given the right package and classpath, the bean is configured via the XML setter. Annotation processing infrastructure is only needed if the application **also uses** `@Autowired`, `@Value`, `@PostConstruct`, and related annotations. Component scanning does not need to be enabled to register a class already declared explicitly in XML.

## 3. `value`: Passing a Literal and Converting Its Type

Common shorthand form:

```xml
<property name="displayName" value="Catalog"/>
<property name="retryLimit" value="3"/>
<property name="active" value="true"/>
```

With corresponding setters:

```java
public void setDisplayName(String displayName) { ... }
public void setRetryLimit(int retryLimit) { ... }
public void setActive(boolean active) { ... }
```

These are **illustrative fragments**; the Java method bodies `...` represent omitted implementation, not a complete program. On a real bean class, Spring reads `"3"` as text and uses its type conversion infrastructure to assign an `int`, and reads `"true"` to assign a `boolean`.

You do not need to declare a type in each `value` attribute if Spring can infer it from the writable property and matching converter/editor. However, a text literal **is not an arbitrary Java expression**. `value="1+2"` assigns the string `1+2` to a `String`; it does not automatically evaluate to the number 3 just because it looks like arithmetic.

### 3.1. Semantics of XML Quotes

Example:

```xml
<property name="name" value="System"/>
```

The quotes here belong to **XML attribute syntax**, not to the `String` value passed to the setter. The setter receives `System`, without surrounding `"` characters.

### 3.2. Type Conversion and Conversion Errors

A Java `int retryLimit` property receiving `value="3"` usually works. However:

```xml
<property name="retryLimit" value="three"/>
```

can trigger a `TypeMismatchException` / `ConversionFailedException` inside a `BeanCreationException` chain or equivalent exception when Spring sets the property. **XSD does not inspect** that `retryLimit` is a Java `int` on that class; value verification occurs at the binding/bean-creation layer.

Common types:

| Target property type | Sample literal | Result |
| --- | --- | --- |
| `String` | `value="hello"` | String `hello` |
| `int`/`Integer` | `value="42"` | Integer 42 when conversion is valid |
| `boolean`/`Boolean` | `value="true"` | Boolean true |
| `long`/`Long` | `value="5000"` | Long integer |
| `double`/`Double` | `value="2.5"` | Floating-point number via converter/editor |
| `Duration`/`Path`/custom types | String depending on conversion service | Works only when proper conversion support exists |
| Enum `Mode` | `value="FAST"` | Can convert to enum constant `FAST` via appropriate mechanism |
| `Class<?>` | `value="java.lang.String"` | Can load class when supported by type converter/editor |

**Do not assume every type converts automatically.** For domain-specific types, a `ConversionService`, `Converter`, `PropertyEditor`, or factory method may be required. Test the real case instead of guessing solely from the literal.

### 3.3. Nested `<value/>` Form

Instead of an attribute:

```xml
<property name="displayName" value="Catalog"/>
```

you can use a sub-element:

```xml
<property name="displayName">
    <value>Catalog</value>
</property>
```

Both forms express a literal value. The nested form is convenient for XML element content, clear formatting, or explicit typing hints. Example:

```xml
<property name="retryLimit">
    <value type="int">3</value>
</property>
```

`type="int"` is a type hint/declaration on `<value>` per the schema; it will not make the string `three` valid for an `int` setter.

### 3.4. Empty String Differs from `null`

For a `String` property:

```xml
<property name="note" value=""/>
```

passes an **empty string** `""`, whereas:

```xml
<property name="note">
    <null/>
</property>
```

passes **Java `null`**. These two states can make the application behave differently:

```java
"".isEmpty()      // true
note == null     // true if note is set to null
```

These Java lines are illustrative only. A setter accepting a primitive such as `int` cannot normally receive Java `null`; nullability applies to wrapper/reference types and the property's contract.

### 3.5. XML Escaping Is Not Spring Conversion

Inside an XML attribute, `&` must be written as `&amp;` and `<` as `&lt;`. Example:

```xml
<property name="displayName" value="Sales &amp; Operations"/>
```

Spring receives `Sales & Operations` after the XML parser resolves the entity. Writing `value="Sales & Operations"` makes the file not well-formed; the error happens **before** setter injection is even considered.

## 4. `ref`: Injecting Another Bean Object

Example:

```xml
<bean id="repository" class="demo.InMemoryRepository"/>

<bean id="service" class="demo.CatalogService">
    <property name="repository" ref="repository"/>
</bean>
```

With the Java API:

```java
public void setRepository(Repository repository) {
    this.repository = repository;
}
```

These are illustrative snippets requiring the corresponding class/interface. `ref="repository"` is the **registered bean name**; Spring resolves that name and injects a reference to the corresponding instance.

Do not confuse with:

```xml
<property name="repository" value="repository"/>
```

This line specifies the literal string `"repository"`. It **does not** look up a bean named `repository`. If the setter expects `Repository`, type conversion does not by default convert a string bean name into a managed dependency like `ref` does.

### 4.1. Beans Do Not Need to Be in the Same XML File

`ref` resolves against the **bean registry/hierarchy**, without requiring both bean definitions to sit side by side in the same file. Spring can load multiple XML resources into the same context or use a parent context; `ref` can point to a bean in the same container or a visible bean in a parent.

Example:

```xml
<import resource="repository-context.xml"/>

<bean id="service" class="demo.CatalogService">
    <property name="repository" ref="repository"/>
</bean>
```

This illustrative snippet must reside inside a valid `<beans>` root. `repository-context.xml` can supply the `repository` definition. Spring must read and process both resources appropriately; merely writing `ref` does not automatically search arbitrary JARs or files.

### 4.2. Bean Name and Alias

```xml
<bean id="repository" class="demo.InMemoryRepository"/>
<alias name="repository" alias="catalogStore"/>

<bean id="service" class="demo.CatalogService">
    <property name="repository" ref="catalogStore"/>
</bean>
```

With the alias `catalogStore`, `ref` can reference the bean's alias; it still resolves to the same definition/managed instance without creating a new repository.

### 4.3. Nested `<ref bean="..."/>` Form

These two are semantically equivalent:

```xml
<property name="repository" ref="repository"/>
```

and:

```xml
<property name="repository">
    <ref bean="repository"/>
</property>
```

The second form is helpful when writing nested configuration consistently alongside `<list>`, `<map>`, or nested beans. You may also encounter:

```xml
<property name="repository">
    <ref parent="repository"/>
</property>
```

`<ref parent="repository"/>` has a special meaning: it selects the definition named `repository` from the **parent BeanFactory/ApplicationContext**, useful when a child context defines a bean with the same name shadowing the parent bean. This is an advanced case; do not use `parent` instead of `bean` out of habit.

The XML snippets above are not standalone files; they require a `<beans>` root and actual bean definitions.

### 4.4. When References Are Resolved

When Spring creates bean `service` with a writable property `repository` configured with `ref="repository"`:

1. BeanFactory locates the definition of `service`.
2. Creates the `service` instance via the appropriate constructor or factory method.
3. While populating properties, BeanFactory needs an instance of `repository`.
4. If the dependency has not been created yet and must be resolved eagerly, Spring creates/prepares `repository` according to its scope and lifecycle.
5. Spring invokes `setRepository(managedRepository)`.
6. The bean proceeds through init callbacks and post-processors per Spring's lifecycle.

Therefore, `ref` represents a dependency edge in the bean graph. A bean marked `lazy-init="true"` may still be instantiated early if an eager bean depends on it via `ref`.

### 4.5. Scope and Reference Identity

If `repository` is a default singleton, all consumers injected with that bean typically share the managed reference. If `repository` is a prototype, each time the container resolves the prototype dependency it creates an instance per scope; a singleton service that already received a prototype via its setter **does not receive a fresh prototype on every business method call**.

If the dependency is an AOP proxy or scoped proxy, the reference the service receives may be the proxy supplied by the BeanFactory, rather than the raw object returned by the constructor. `ref` carries container semantics, quite different from calling `new Repository()` inside a setter.

### 4.6. Missing Reference vs. Missing Setter

With:

```xml
<property name="repository" ref="doesNotExist"/>
```

Spring may report `NoSuchBeanDefinitionException` inside a `BeanCreationException` / `BeanDefinitionStoreException` depending on the phase. However, if the bean exists yet `CatalogService` lacks a writable property `repository`, that is an **invalid property name** error (such as `NotWritablePropertyException`), not a missing bean.

Proper debugging means reading the **root cause** and identifying whether the bean name or property name failed.

## 5. `<idref>`: Passing a Bean Name as a String, Not an Instance

Spring provides the element:

```xml
<property name="repositoryBeanName">
    <idref bean="repository"/>
</property>
```

Meaning: property `repositoryBeanName` receives the string `"repository"`, **not** a `Repository` object. Spring can validate that the referenced bean name exists when processing the definition, reducing typos compared to:

```xml
<property name="repositoryBeanName" value="repository"/>
```

In the second example, `value` merely supplies a string without expressing an `idref` that validates the bean name's existence. `idref` is useful for infrastructure that accepts a **bean name as a String**, such as when another component later looks up that name by contract.

| Syntax | What does the setter receive? | Does it resolve the object as a dependency? |
| --- | --- | --- |
| `value="repository"` | String literal `"repository"` | No |
| `ref="repository"` | Bean object/proxy named `repository` | Yes |
| `<ref bean="repository"/>` | Bean object/proxy named `repository` | Yes |
| `<idref bean="repository"/>` | String `"repository"`, with appropriate name validation | Does not pass the object into the property |
| `<value>repository</value>` | String literal `"repository"` | No |

**Do not write `<idref>` instead of `ref` when you need to inject a dependency object.** The names look similar, but their semantics are completely different.

## 6. Configuring Collections with `value`, `ref`, and Nested Elements

A property does not have to be a scalar or a single bean. Spring XML supports `<list>`, `<set>`, `<map>`, and `<props>` under `<property>`.

### 6.1. `<list>` Containing Multiple Values

```xml
<bean id="reportService" class="demo.ReportService">
    <property name="regions">
        <list>
            <value>north</value>
            <value>south</value>
        </list>
    </property>
</bean>
```

If the Java setter is `setRegions(List<String>)`, Spring creates a list and passes it into the bean. The order `north`, `south` is significant because `List` preserves element order.

Do not confuse this with **collection injection by type** like `@Autowired List<SomeInterface>`: here the collection elements are **explicitly declared in XML**, not automatically gathered from all beans of that type just because the property type is `List`.

### 6.2. `<list>` Containing Bean References

```xml
<bean id="smsChannel" class="demo.SmsChannel"/>
<bean id="mailChannel" class="demo.MailChannel"/>

<bean id="dispatcher" class="demo.Dispatcher">
    <property name="channels">
        <list>
            <ref bean="smsChannel"/>
            <ref bean="mailChannel"/>
        </list>
    </property>
</bean>
```

This illustrative XML requires `SmsChannel`, `MailChannel`, `Dispatcher`, and a matching `setChannels(List<...>)` setter. The list entries are **bean references**, not the strings `"smsChannel"` and `"mailChannel"`.

### 6.3. `<map>`: Values or Bean References

```xml
<property name="regionLabels">
    <map>
        <entry key="north" value="N"/>
        <entry key="south" value="S"/>
    </map>
</property>
```

Here the map keys and values are literals. If you need to reference a bean in the map:

```xml
<property name="handlers">
    <map>
        <entry key="main" value-ref="mainHandler"/>
    </map>
</property>
```

`value-ref` on `<entry>` denotes a bean reference. It differs from `value="mainHandler"`, which is a string literal. Certain configurations also allow `key-ref` when the map key itself is a bean object.

### 6.4. `<set>` and `<props>`

```xml
<property name="roles">
    <set>
        <value>reader</value>
        <value>writer</value>
    </set>
</property>

<property name="codes">
    <props>
        <prop key="north">N</prop>
        <prop key="south">S</prop>
    </props>
</property>
```

`<set>` expresses a set of elements; `<props>` fits `java.util.Properties` and string key/value pairs. Both are **XML fragments** requiring a bean class with matching setters.

For maps and sets, do not build business logic around iteration order unless a specific contract guarantees it. When order matters, use a `List` or an ordered domain structure.

### 6.5. Type Conversion in Generic Collections

If a setter accepts `List<Integer>`, Spring can convert `<value>1</value>` and `<value>2</value>` into `Integer` using generic type information and compatible conversion infrastructure.

```xml
<property name="levels">
    <list value-type="java.lang.Integer">
        <value>1</value>
        <value>2</value>
    </list>
</property>
```

`value-type` on `<list>` specifies the intended element type per the Spring XML schema. However, if the class lacks a setter or no converter supports a custom type, declaring generics/`value-type` cannot fix every runtime error on its own.

### 6.6. Collection Merging Is a Separate Topic

When using **parent-child bean definitions** via `parent="..."` in XML, Spring allows compatible collection metadata from the child to merge with the parent if `merge="true"` is configured properly. This is **merging bean definition values**, not an arbitrary runtime `List.addAll`.

Do not add `merge="true"` casually expecting it to merge collections across two unrelated singleton beans. Understand parent/child bean definition relationships and the rules for each collection type.

## 7. Inner Beans: Creating a Private Collaborator for One Property

Sometimes a collaborator does not need an independent name in the registry:

```xml
<bean id="service" class="demo.CatalogService">
    <property name="formatter">
        <bean class="demo.SimpleFormatter">
            <property name="prefix" value="SVC: "/>
        </bean>
    </property>
</bean>
```

Spring treats a `<bean>` nested inside `<property>` as an **inner bean**. Characteristics:

- Typically has no public bean name for standalone lookup from `ApplicationContext`.
- Its instance has a lifecycle/ownership relationship with the enclosing bean per inner bean semantics.
- Do not use an inner bean when multiple consumers need to share the same managed named singleton.
- When there is only one consumer and the collaborator is purely internal, this configuration is concise.

An inner bean does not mean **every call to a service method constructs a new formatter**. Bean construction still happens when Spring builds the enclosing bean and populates its properties, not automatically on each business method invocation.

### 7.1. Inner Bean vs. `ref`

Two distinct wiring styles:

```xml
<!-- References a named bean that can be shared. -->
<property name="formatter" ref="sharedFormatter"/>
```

and:

```xml
<!-- Defines a private object inside the consumer. -->
<property name="formatter">
    <bean class="demo.SimpleFormatter"/>
</property>
```

The first obtains a managed reference to `sharedFormatter`. The second creates an inner bean definition; it does not register a top-level `sharedFormatter` bean.

### 7.2. Inner Beans and Scopes

Spring documentation notes that an inner bean normally shares the lifecycle context of its enclosing bean; even if you specify a different scope on an inner definition, understand Spring's actual rules before relying on it. For reusable dependencies or nontrivial scopes (request/session), named beans and scoped proxies are clearer.

## 8. The `p` Namespace: Shorthand for `<property>`

In Spring XML, you can choose the explicit form:

```xml
<bean id="service" class="demo.CatalogService">
    <property name="label" value="Catalog"/>
    <property name="repository" ref="repository"/>
</bean>
```

Or use the `p` namespace:

```xml
<bean id="service" class="demo.CatalogService"
      p:label="Catalog"
      p:repository-ref="repository"/>
```

Declare it on the `<beans>` root:

```xml
xmlns:p="http://www.springframework.org/schema/p"
```

**The `p` namespace has no separate XSD**. It is supported directly by the Spring bean XML parser; do not invent a `spring-p.xsd` in `xsi:schemaLocation`.

### 8.1. Rules for `value` and `ref`

| Full form | `p` form |
| --- | --- |
| `<property name="title" value="Hello"/>` | `p:title="Hello"` |
| `<property name="repository" ref="repository"/>` | `p:repository-ref="repository"` |
| `<property name="enabled" value="true"/>` | `p:enabled="true"` |
| `<property name="timeout" value="30"/>` | `p:timeout="30"` |

`p:repository="repository"` is **not** equivalent to `p:repository-ref="repository"` when the property expects a `Repository` object. The `-ref` suffix is what tells the container to look up a bean.

### 8.2. Limitations of Shorthand

`p` is convenient for scalar properties and short references. For lists, maps, inner beans, or long configurations, nested `<property>` elements are easier to read.

A JavaBean property name that itself ends with `Ref` (such as `accountRef`) can clash confusingly with the `-ref` suffix convention in the p-namespace, making full XML syntax safer for complex names. Do not mix too many styles in a single file if it hurts team maintainability.

## 9. Property Placeholders `${...}` and SpEL `#{...}`

These are two extension mechanisms applied to values, not to be confused with `ref`.

### 9.1. `value` Containing a Placeholder

```xml
<property name="endpointUrl" value="${client.endpoint}"/>
```

If the application registers a `PropertySourcesPlaceholderConfigurer` or equivalent environment configuration, `${client.endpoint}` can be resolved from property sources into an actual string.

In plain Spring Framework using XML, you can configure:

```xml
<context:property-placeholder location="classpath:client.properties"/>
```

This requires declaring `xmlns:context`, the right XSD mapping, and `client.properties` on the classpath; the context namespace handler supports that mechanism. When a placeholder cannot be resolved and no fallback policy applies, the application may fail during bean processing/creation.

**Do not confuse:** `value="${client.repository}"` supplies a string value from properties; it does not automatically turn it into a bean reference unless you deliberately use an expression/lookup mechanism.

### 9.2. SpEL Inside `value`

```xml
<property name="region" value="#{'north'.toUpperCase()}"/>
```

In an `ApplicationContext` with a suitable bean expression resolver, Spring evaluates SpEL at the value position and returns `NORTH`. This example illustrates syntax; SpEL is not the same as literal `value="north"`.

SpEL can also express bean references, such as `value="#{@repository}"` in environments supporting an expression resolver. However, when the goal is simply to inject a named bean, `ref="repository"` is clearer, carries a direct bean dependency contract, and is easier to debug.

### 9.3. Placeholders and Bean References Change Configuration Meaning

| Syntax | Source determining the value |
| --- | --- |
| `value="hello"` | Literal supplied directly by XML |
| `value="${app.label}"` | Property placeholder processed by a resolver if configured |
| `value="#{1 + 2}"` | SpEL expression evaluated if supported by the context |
| `ref="repository"` | BeanFactory resolves bean name |
| `<idref bean="repository"/>` | Validated bean name as a String |

A system can combine placeholders with `ref` when a dependency name comes from configuration, but doing so requires strict control over validity and resolution timing; do not assume every `${...}` behaves like `@Autowired` injection.

## 10. Initialization Order, Lifecycle, and Optional Properties

### 10.1. Bean Is Instantiated Before Setters Are Called

For standard setter injection:

```text
BeanDefinition selected
           |
           v
Constructor/factory method creates instance
           |
           v
BeanFactory resolves property values / refs
           |
           v
Invoke corresponding writable setters
           |
           v
Aware callbacks, BeanPostProcessors, init callbacks
           |
           v
Managed bean ready
```

The exact sequence of infrastructure callbacks and processor hooks can be more intricate than the diagram, yet **property population happens before standard initialization steps**. Therefore, if a class relies on an injected property to function, do not access it inside the constructor before Spring invokes the setter.

### 10.2. What If a Setter Is Not Declared in XML?

If XML omits `<property name="..." .../>`, Spring **does not automatically set that property** merely because a setter exists, unless autowiring, annotations, or another processor does so. The Java field retains its default value (`null`, `0`, `false`) or whatever the constructor/field initializer set.

An omitted required dependency with setter injection may not fail context startup immediately, instead throwing `NullPointerException` only when a business method runs. That is why constructor injection is usually preferred for indispensable dependencies; with setter injection, validate state in an init method/`@PostConstruct` or context tests.

### 10.3. Constructor vs. Setter Cycles

A constructor dependency cycle A→B→A generally cannot be resolved via normal object creation. Setter-based cycles among singletons **can** be resolved by Spring in certain configurations via early references, yet should not be treated as a default design; especially with AOP proxies, other scopes, and framework settings, cycles can still fail or expose partially initialized objects.

**Recommendation:** Refactor the dependency graph, separate responsibilities, or introduce clear one-way abstractions instead of switching constructor injection to setters just to hide an A↔B cycle.

### 10.4. Properties Are Set Once at Bean Creation, Not Live Configuration

Normally `<property name="timeout" value="30"/>` sets the value when Spring creates the bean. Once the context has refreshed, editing the XML file on disk **does not** automatically re-invoke the setter or update the managed singleton. If hot reload or dynamic configuration is needed, design a dedicated refresh/lookup mechanism or runtime source of truth.

### 10.5. `@Autowired` and XML Properties Can Coexist

A class can be registered in XML while also using annotation injection, provided the context has the required annotation post-processor infrastructure. However, if the same dependency is set via both XML and annotations, the ordering/precedence between injection mechanisms can cause surprises. Choose **one authoritative configuration source** per property whenever possible, and test carefully during gradual XML-to-annotation migrations.

## 11. Complete Java 17+ Example: Literal `value`, `ref`, `list`/`map`, `idref`, `null`, and `p` Namespace

This project uses Spring Framework 6.2.19, Gradle, and Java 17. No Spring Boot or server is needed. All domain classes are **plain Java classes**, with no `@Component` or `@Autowired` annotations.

Observable outcomes:

- `String prefix`, `int retryLimit`, `boolean enabled` received via literal `value`.
- `CatalogRepository` and `DeliveryChannel` objects received via `ref`, sharing managed singletons.
- `tags` receives a `List<String>`; `routes` receives a `Map<String,String>`.
- `repositoryName` receives the bean id string via `<idref>`.
- `memo` receives Java `null` via `<null/>`.
- Bean `backupNotifier` uses shorthand `p:repo-ref`, `p:prefix`, and `p:enabled`.
- The program checks both business output and **reference identity** to distinguish `value` from `ref`.

### 11.1. Project Structure

```text
spring-xml-properties-demo/
├── settings.gradle
├── build.gradle
└── src/
    └── main/
        ├── java/
        │   └── demo/
        │       ├── CatalogRepository.java
        │       ├── DeliveryChannel.java
        │       ├── NotificationService.java
        │       └── Application.java
        └── resources/
            └── application-context.xml
```

File `settings.gradle`:

```groovy
rootProject.name = 'spring-xml-properties-demo'
```

File `build.gradle`:

```groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-context:6.2.19'
}

application {
    mainClass = 'demo.Application'
}
```

Run with JDK 17+ and a Gradle version compatible with that JDK. `spring-context` brings in Spring Beans/Core needed to parse XML, resolve dependencies, and manage `ApplicationContext`.

### 11.2. `CatalogRepository.java`

`src/main/java/demo/CatalogRepository.java`:

```java
package demo;

public final class CatalogRepository {
    public String find(String id) {
        return "order-" + id;
    }
}
```

This class has no Spring annotations. It has an implicit no-argument constructor and is instantiated via XML `<bean id="catalogRepository" .../>`.

### 11.3. `DeliveryChannel.java`

`src/main/java/demo/DeliveryChannel.java`:

```java
package demo;

public final class DeliveryChannel {
    private final String name;

    public DeliveryChannel(String name) {
        this.name = name;
    }

    public String name() {
        return name;
    }
}
```

`DeliveryChannel` is declared with a constructor argument in XML; `NotificationService` receives it via **property `ref`**. Both injection styles can be combined in the same configuration when the domain API requires it.

### 11.4. `NotificationService.java`

`src/main/java/demo/NotificationService.java`:

```java
package demo;

import java.util.List;
import java.util.Map;

public final class NotificationService {

    private CatalogRepository repo;
    private DeliveryChannel channel;
    private String prefix = "";
    private int retryLimit;
    private boolean enabled;
    private List<String> tags = List.of();
    private Map<String, String> routes = Map.of();
    private String repositoryName;
    private String memo;

    public void setRepo(CatalogRepository repo) {
        this.repo = repo;
    }

    public void setChannel(DeliveryChannel channel) {
        this.channel = channel;
    }

    public void setPrefix(String prefix) {
        this.prefix = prefix;
    }

    public void setRetryLimit(int retryLimit) {
        this.retryLimit = retryLimit;
    }

    public void setEnabled(boolean enabled) {
        this.enabled = enabled;
    }

    public void setTags(List<String> tags) {
        this.tags = tags;
    }

    public void setRoutes(Map<String, String> routes) {
        this.routes = routes;
    }

    public void setRepositoryName(String repositoryName) {
        this.repositoryName = repositoryName;
    }

    public void setMemo(String memo) {
        this.memo = memo;
    }

    public CatalogRepository getRepo() {
        return repo;
    }

    public DeliveryChannel getChannel() {
        return channel;
    }

    public String getPrefix() {
        return prefix;
    }

    public boolean isEnabled() {
        return enabled;
    }

    public String getRepositoryName() {
        return repositoryName;
    }

    public List<String> getTags() {
        return tags;
    }

    public String notifyFor(String orderId) {
        if (!enabled) {
            return "disabled";
        }

        return prefix + repo.find(orderId)
                + " via " + channel.name()
                + " retries=" + retryLimit
                + " tags=" + tags
                + " north=" + routes.get("north")
                + " memo=" + (memo == null ? "none" : memo);
    }
}
```

The setters are writable JavaBean properties. `notifyFor` intentionally uses no Spring APIs: it demonstrates a domain object simply receiving dependencies supplied by the container from XML.

### 11.5. `application-context.xml`

`src/main/resources/application-context.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<beans xmlns="http://www.springframework.org/schema/beans"
       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
       xmlns:p="http://www.springframework.org/schema/p"
       xsi:schemaLocation="
           http://www.springframework.org/schema/beans
           https://www.springframework.org/schema/beans/spring-beans.xsd">

    <bean id="catalogRepository" class="demo.CatalogRepository"/>

    <bean id="emailChannel" class="demo.DeliveryChannel">
        <constructor-arg value="email"/>
    </bean>

    <bean id="notifier" class="demo.NotificationService">
        <property name="repo" ref="catalogRepository"/>

        <property name="channel">
            <ref bean="emailChannel"/>
        </property>

        <property name="prefix" value="INFO: "/>
        <property name="retryLimit" value="3"/>

        <property name="enabled">
            <value>true</value>
        </property>

        <property name="tags">
            <list>
                <value>ops</value>
                <value>mail</value>
            </list>
        </property>

        <property name="routes">
            <map>
                <entry key="north" value="N"/>
                <entry key="south" value="S"/>
            </map>
        </property>

        <property name="repositoryName">
            <idref bean="catalogRepository"/>
        </property>

        <property name="memo">
            <null/>
        </property>
    </bean>

    <bean id="backupNotifier"
          class="demo.NotificationService"
          p:repo-ref="catalogRepository"
          p:channel-ref="emailChannel"
          p:prefix="WARN: "
          p:retryLimit="1"
          p:enabled="false"/>
</beans>
```

**Why is there no XSD mapping for `p`?** `p` is a shorthand namespace handled by Spring core, with no separate `spring-p.xsd` file. The XML root declares `xmlns:p`, while `xsi:schemaLocation` only needs the beans namespace and `spring-beans.xsd` pair.

**Why does `<idref bean="catalogRepository"/>` not receive the repository object?** It passes the **bean name string** into `setRepositoryName(String)`. In contrast, `<property name="repo" ref="catalogRepository"/>` passes a managed `CatalogRepository` into `setRepo(...)`.

**Why is `<null/>` not the same as `value=""`?** `setMemo(null)` causes the code to print `memo=none`. Changing it to an empty string makes the code print `memo=`; that is a data difference.

### 11.6. `Application.java` and Output

`src/main/java/demo/Application.java`:

```java
package demo;

import org.springframework.context.support.ClassPathXmlApplicationContext;

public final class Application {

    public static void main(String[] args) {
        try (var context =
                new ClassPathXmlApplicationContext(
                        "application-context.xml")) {

            CatalogRepository repository =
                    context.getBean("catalogRepository",
                            CatalogRepository.class);
            DeliveryChannel channel =
                    context.getBean("emailChannel",
                            DeliveryChannel.class);
            NotificationService notifier =
                    context.getBean("notifier",
                            NotificationService.class);
            NotificationService backup =
                    context.getBean("backupNotifier",
                            NotificationService.class);

            System.out.println("message = " +
                    notifier.notifyFor("42"));
            System.out.println("sameRepo = " +
                    (repository == notifier.getRepo()));
            System.out.println("sameChannel = " +
                    (channel == notifier.getChannel()));
            System.out.println("repositoryName = " +
                    notifier.getRepositoryName());
            System.out.println("enabled = " +
                    notifier.isEnabled());
            System.out.println("backupEnabled = " +
                    backup.isEnabled());
            System.out.println("backupPrefix = [" +
                    backup.getPrefix() + "]");
            System.out.println("backupSameRepo = " +
                    (repository == backup.getRepo()));
            System.out.println("tags = " +
                    notifier.getTags());
        }
    }
}
```

The program creates a Spring application context, loads bean definitions from XML on the classpath, and calls the managed beans after the context refreshes. It does not call `new NotificationService()` in `main`.

### 11.7. Running Gradle

At the `spring-xml-properties-demo` root:

```bash
gradle run --quiet
```

If using the Gradle Wrapper:

```bash
./gradlew run --quiet
```

Windows PowerShell:

```powershell
.\gradlew.bat run --quiet
```

Stdout produced by the program's `System.out.println` calls:

```text
message = INFO: order-42 via email retries=3 tags=[ops, mail] north=N memo=none
sameRepo = true
sameChannel = true
repositoryName = catalogRepository
enabled = true
backupEnabled = false
backupPrefix = [WARN: ]
backupSameRepo = true
tags = [ops, mail]
```

Gradle or Spring logging may print extra lines outside these `System.out.println` statements. The output above shows the deterministic business output for the supplied source and XML.

### 11.8. Output Explanation

**`message`:** literal `prefix="INFO: "`, `retryLimit="3"` converted by Spring to `int`, nested `<value>true</value>` converted to `boolean`, bean references to repository/channel supplied properly, `tags` is a list in declared order, `routes.get("north")` is `N`, and `memo` displays `none` because of `<null/>`.

**`sameRepo = true`:** `notifier` holds the managed singleton `catalogRepository` supplied by `ref`; it does not hold a bean-name string.

**`sameChannel = true`:** nested `<ref bean="emailChannel"/>` has the same object-reference semantics as `ref="emailChannel"` on `<property>`. It does not create another channel instance.

**`repositoryName = catalogRepository`:** this is a string thanks to `<idref>`, not a `CatalogRepository` object. When passing a bean name as infrastructure data, `idref` expresses intent more clearly than a literal string.

**`backupEnabled = false` and `backupPrefix = [WARN: ]`:** `p:enabled="false"` and `p:prefix="WARN: "` are shorthand for literal properties; the brackets in stdout make the trailing space of the prefix visible.

**`backupSameRepo = true`:** `p:repo-ref="catalogRepository"` also supplies the managed bean reference, equivalent to `<property name="repo" ref="catalogRepository"/>`.

**`tags = [ops, mail]`:** the XML list was assigned to the property while preserving order. Neither component scanning nor annotation injection is needed in the three domain classes.

## 12. Diagnosing Common Errors

### 12.1. Wrong Property Name

XML:

```xml
<property name="retry" value="3"/>
```

while the class only has `setRetryLimit(int)`. Spring may throw `NotWritablePropertyException` (typically wrapped in `BeanCreationException`). The fix is to check the **JavaBeans property name**, rather than guessing from a field name or inventing an XML attribute.

### 12.2. Wrong Literal Type

XML:

```xml
<property name="retryLimit" value="many"/>
```

the setter requires `int`, so conversion fails. Do not change the setter to `String` just to make startup pass if the domain genuinely needs a number; fix the configuration/validation and test invalid cases.

### 12.3. `value` Instead of `ref`

XML:

```xml
<property name="repo" value="catalogRepository"/>
```

while the setter expects `CatalogRepository`. Spring receives a literal `String` and attempts to convert it to the target type; normally it does not look up a bean automatically. Fix it to `ref="catalogRepository"`.

### 12.4. Wrong Bean Name in `ref`

XML:

```xml
<property name="repo" ref="catalogRepositorry"/>
```

Typo in the name, so BeanFactory cannot resolve the bean. Check declared `id`/`name`/`alias`, imported XML files, active profiles, and parsed bean definitions.

### 12.5. Wrong Setter Visibility or Signature

If a class has `void setRepo(CatalogRepository x)` without `public` visibility in a standard JavaBeans introspection context, or only has `getRepo()`, the property may not be writable via standard setter binding. Fix the API contract, or switch to constructor injection if the dependency is required.

### 12.6. Confusing `ref` with `idref`

`idref` passes a `String` bean name, not an instance. If the setter is `setRepo(CatalogRepository)`, `<idref bean="catalogRepository"/>` is semantically wrong. Use `<ref bean="catalogRepository"/>`.

### 12.7. Literal Contains a Placeholder Without a Resolver

`value="${app.repo}"` may remain unprocessed if placeholder resolution configuration is missing or the property is not provided. In plain Spring XML, check `context:property-placeholder` or `PropertySourcesPlaceholderConfigurer`, the properties file path, and active property sources.

### 12.8. Collection Entries Using the Wrong `value`/`ref`

`<entry key="main" value="mainChannel"/>` creates a `String`. If the setter expects `Map<String, Channel>`, use `value-ref="mainChannel"` to place the bean object in the map.

### 12.9. Circular Dependencies and Unready Objects

Setter cycles are sometimes permitted by Spring for singletons via early references, yet can introduce tight coupling and hard-to-control side effects. Do not conclude a bean graph is sound merely because “Spring started up”; verify post-initialization state and refactor cycles when possible.

### 12.10. Bean Exists Yet Setter Does Not Run

Possible causes: the bean class was instantiated by another source, the XML resource was not loaded, the property belongs to another bean definition with the same name, a profile skipped the XML block, or the bean is still lazy and uninstantiated. Check which files the context loads and inspect the actual bean definitions rather than staring at one XML snippet.

### 12.11. Thinking the `p`-Namespace Is Missing a Schema

When an IDE marks `p:repo-ref` in red, check `xmlns:p="http://www.springframework.org/schema/p"` and the property name. Do not add `spring-p.xsd`: the `p` namespace is handled by Spring as an XML shortcut and has no separate XSD.

### 12.12. Incorrect XML Escaping

`value="A & B"` is not well-formed. Fix it to `value="A &amp; B"`. This is an XML parsing error, not a setter or converter error.

## 13. Quick Reference Table: Which Syntax to Choose?

| Need | Suggested XML syntax | Corresponding setter |
| --- | --- | --- |
| Supply display name | `<property name="name" value="Demo"/>` | `setName(String)` |
| Supply retry count | `<property name="retryLimit" value="3"/>` | `setRetryLimit(int)` |
| Supply boolean | `<property name="enabled" value="true"/>` | `setEnabled(boolean)` |
| Inject repository bean | `<property name="repo" ref="repo"/>` | `setRepo(Repository)` |
| Inject via nested ref | `<property name="repo"><ref bean="repo"/></property>` | `setRepo(Repository)` |
| Pass bean name String | `<property name="targetName"><idref bean="repo"/></property>` | `setTargetName(String)` |
| Pass Java null | `<property name="memo"><null/></property>` | `setMemo(String)` |
| Pass list of literals | `<property name="tags"><list>...</list></property>` | `setTags(List<String>)` |
| Pass map of literals | `<property name="routes"><map>...</map></property>` | `setRoutes(Map<...>)` |
| Use p value shorthand | `p:name="Demo"` | `setName(String)` |
| Use p ref shorthand | `p:repo-ref="repo"` | `setRepo(Repository)` |
| Pass external property | `value="${app.name}"` | `setName(String)` after placeholder resolution |
| Create inner collaborator | `<property name="formatter"><bean .../></property>` | `setFormatter(Formatter)` |

Do not pick syntax solely to reduce line count. For multi-element properties or structured data, nested `<property>` tags can make code reviews more accurate than the `p` namespace.

## 14. Exercises with Answers

### Exercise 1 — A Literal Is Not a Bean Reference

You have `<bean id="store" class="demo.Store"/>` and a service setter `setStore(Store)`. Is writing:

```xml
<property name="store" value="store"/>
```

correct?

**Answer:** Not for the intent of injecting the bean. `value` is a `String` literal. You need `ref="store"` or nested `<ref bean="store"/>`.

### Exercise 2 — Does a Bean Reference Create Separate Objects?

Two services both have `<property name="repo" ref="repository"/>` and `repository` is a default singleton. Are both services guaranteed to receive two different `Repository` instances?

**Answer:** No. Normally both receive the same managed singleton reference in one container, unless scope, proxy, or configuration changes the semantics.

### Exercise 3 — Which Property Name Does the Setter Expose?

A class has `setTimeoutSeconds(int seconds)` and field `timeout`. Should you use `name="timeout"` or `name="timeoutSeconds"`?

**Answer:** `timeoutSeconds` per JavaBeans setter naming, unless there is a separate writable `timeout` property.

### Exercise 4 — Boolean Literal

Setter `setEnabled(boolean)` and XML `value="false"`. What does the method receive?

**Answer:** Java boolean `false` after conversion, not the `String` literal `"false"`.

### Exercise 5 — Empty String vs. `null`

Compare `<property name="memo" value=""/>` with nested `<null/>`. Are they equivalent?

**Answer:** No. One is an empty `String`, the other is `null`. Validation or serialization logic may distinguish them.

### Exercise 6 — Nested vs. Attribute `ref`

Do these two XML snippets:

```xml
<property name="repo" ref="repository"/>
```

```xml
<property name="repo">
    <ref bean="repository"/>
</property>
```

differ in the injected object?

**Answer:** When looking up the same bean name, both express the same managed bean reference.

### Exercise 7 — When Is `idref` Used?

An infrastructure class has setter `setTargetBeanName(String)` and must store the bean name `worker` for later use. Should you use `ref` or `idref`?

**Answer:** `<idref bean="worker"/>` when you want to pass the bean name as a `String` and verify its existence; do not pass the `worker` object via `ref`.

### Exercise 8 — Map Entry Reference

A setter expects `Map<String, EmailSender>`, and bean `emailSender` is registered. Is `<entry key="default" value="emailSender"/>` valid?

**Answer:** No if an `EmailSender` object is needed. Use `<entry key="default" value-ref="emailSender"/>`.

### Exercise 9 — `p` Namespace

For `p:repo-ref="repository"` to work, what namespace declaration is required? Is a separate XSD needed?

**Answer:** `xmlns:p="http://www.springframework.org/schema/p"`, with no `spring-p.xsd` needed.

### Exercise 10 — No Setter

A class has a private field `name` without `setName`, and XML tries `<property name="name" value="A"/>`. What happens?

**Answer:** Standard property binding may fail because the property is not writable. Add a valid setter or use constructor/factory injection.

### Exercise 11 — Property Reference and Lazy

Bean `repository` is marked `lazy-init="true"`, while non-lazy bean `service` has a required `ref="repository"`. Is `repository` guaranteed to remain uninstantiated when context refresh finishes?

**Answer:** No. The eager service's dependency can cause the lazy repository to be instantiated for injection.

### Exercise 12 — Changing XML After Refresh

The app has already created singleton `service` and set `retryLimit=3`. You edit XML to `retryLimit=8` while the app is running. Does the service value update automatically?

**Answer:** No. XML property injection normally happens during bean creation, not as live reload.

### Exercise 13 — Setter Injection Cycle

Two singletons A and B set `property ref` pointing to each other. Should this be considered clean design merely because certain Spring versions/configurations can resolve it?

**Answer:** No. It introduces coupling and lifecycle/proxy risks; refactor to a clearly directed dependency graph.

### Exercise 14 — Property Placeholder

Does `<property name="url" value="${api.url}"/>` always resolve automatically in any plain `BeanFactory`?

**Answer:** No. Suitable placeholder processing/environment support is required. Check `PropertySourcesPlaceholderConfigurer` or the property-placeholder namespace element.

### Exercise 15 — Identity in the Demo

Why does the output show `sameRepo = true` and `backupSameRepo = true`?

**Answer:** Both traditional XML `ref` and `p:repo-ref` use the BeanFactory to obtain **the same singleton** `catalogRepository`, rather than creating copies from a string name.

### Exercise 16 — Trailing Space in a Literal

In the demo, `p:prefix="WARN: "` has a space after the colon. Why does output show `backupPrefix = [WARN: ]`?

**Answer:** The getter returns the `String` including the trailing space from the literal, and the square brackets in `println` make the whitespace visible. This is the actual property content, not a newline split from XML.

## 15. Pre-Merge Checklist for XML Property Configuration

- Does the XML file have a `<beans>` root, valid default namespace, and valid `schemaLocation`?
- Are `bean id`/`alias` consistent with all `ref`/`idref` attributes?
- Does every `<property name="...">` correspond to an exact **writable JavaBean property**?
- Is `value` used for literals/converted scalars, `ref` for managed objects, and `idref` for bean-name `String`s?
- Do `int`, `boolean`, enum, and collection element types have valid conversions?
- Are `value=""` and `<null/>` distinguished and checked against the nullability contract?
- In lists/maps, are `<ref>` or `value-ref` used instead of literal bean names when objects are needed?
- If using `p` shorthand, is `xmlns:p` declared without inventing a fake XSD?
- Are inner beans used only where private ownership applies rather than shared named beans (and vice versa)?
- Do bean references affect scope/lazy/lifecycle as expected?
- Could an omitted required property remain `null` and cause a late runtime exception?
- Are property placeholders/SpEL configured and resolved correctly in the target environment?
- Was the configuration tested with `ClassPathXmlApplicationContext`, bean lookups, and identity/behavior assertions?
- Are errors classified accurately: XML parse, XSD, writable property, type mismatch, missing bean, or circular reference?
- When migrating from XML to JavaConfig, have you avoided configuring the same dependency twice?

## 16. Summary

**`<property name="x" value="..."/>`** supplies a literal value, which Spring converts to the writable property's target type using available converters/editors. **`<property name="x" ref="someBean"/>`** supplies a reference to the container-managed bean `someBean`. Nested `<ref bean="..."/>` is equivalent to the `ref` attribute; **`<idref bean="..."/>`** instead supplies the **bean name as a `String`**.

Setter injection occurs during bean creation, after construction and before standard initialization callbacks. Bean references obey BeanFactory scope, lifecycle, and proxy semantics. `<list>`, `<map>`, `<set>`, and `<props>` support structured data, `<null/>` differs from an empty `String`, and inner beans serve collaborators confined to a single configuration scope. The `p` namespace is a readable shorthand for scalar and ref properties, though it has no separate XSD and does not replace all nested constructs.

When an application needs a dependency object, choose **`ref` rather than `value`**; when you only want to store a bean's name as configuration data, consider **`idref`**. Keeping these two meanings distinct prevents most Spring XML setter injection mistakes.

### Official Documentation

- [Spring Framework 6.2 — Dependencies and Configuration in Detail](https://docs.spring.io/spring-framework/reference/6.2/core/beans/dependencies/factory-properties-detailed.html).
- [Spring Framework 6.2 — Dependency Injection](https://docs.spring.io/spring-framework/reference/6.2/core/beans/dependencies/factory-collaborators.html).
- [Spring Framework 6.2 — Bean Overview](https://docs.spring.io/spring-framework/reference/6.2/core/beans/definition.html).
- [Spring Framework 6.2 — Bean Scopes](https://docs.spring.io/spring-framework/reference/6.2/core/beans/factory-scopes.html).
- [Spring Framework 6.2 — Bean Lifecycle Callbacks](https://docs.spring.io/spring-framework/reference/6.2/core/beans/factory-nature.html).
- [Spring Framework 6.2 — PropertySourcesPlaceholderConfigurer Javadoc](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/context/support/PropertySourcesPlaceholderConfigurer.html).
