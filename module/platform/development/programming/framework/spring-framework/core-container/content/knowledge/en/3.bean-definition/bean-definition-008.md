# Abstract Definitions and Merging Inherited Configuration in Spring Core Container

## 1. The Problem: Multiple Beans Share Configuration Yet Still Must Differ

In Spring XML configuration, sometimes multiple beans share common baseline settings: instantiation details, property values, certain arguments, or lifecycle settings. If you copy every `<bean>` in full, updating a shared setting later makes it easy to miss one copy.

Spring Core Container supports **bean definition inheritance**. A child bean definition declares `parent="parentBeanName"` to reuse the parent definition's metadata, and can then add or override specific parts. A parent bean definition used purely as a **configuration template** is typically marked `abstract="true"`.

Key points to remember upfront:

- **Parent bean definition** is a **metadata template** used to produce complete bean definitions.
- **Child bean definition** inherits and merges metadata from the parent when the container processes configuration.
- **Bean instance** of the child is an object created from the final merged metadata.
- `abstract="true"` on an XML `<bean>` does **not** mean the bean's Java class must be declared `abstract class`.
- `parent` in XML does **not** mean `extends` in Java, and is **not** a `parent ApplicationContext` attribute.

Conceptual example:

~~~xml
<bean id="baseConfig" abstract="true"
      class="demo.AlertConfiguration">
    <property name="prefix" value="BASE"/>
</bean>

<bean id="emailConfig" parent="baseConfig">
    <property name="channel" value="email"/>
</bean>

<bean id="smsConfig" parent="baseConfig">
    <property name="channel" value="sms"/>
</bean>
~~~

This is **illustrative XML**; the class name here is not part of the runnable program in Section 6. Once the bean definitions are merged, both children inherit `prefix=BASE` yet have different `channel` values. The parent acts as a template, not as a business object being injected.

### Processing Model

~~~text
        parent bean definition
         id=baseTemplate
         abstract=true
         prefix=BASE
         tags=[audit, core]
                  |
          +-------+---------+
          |                 |
          v                 v
   emailConfig child   smsConfig child
   channel=email       channel=sms
   tags merge=true     tags replace
          |                 |
          v                 v
  merged definition   merged definition
          |                 |
          v                 v
  emailConfig object  smsConfig object
~~~

Spring merges the **definitions first**, then uses the effective definition to create each child instance. Each child can have its own scope and lifecycle; **no parent instance is required to be created beforehand**.

## 2. Distinguishing Three Commonly Confused Kinds of "Inheritance"

| Concept | Relationship | What is inherited / shared |
| --- | --- | --- |
| **Java class inheritance** | `class Child extends Parent` | Fields/methods and Java OOP rules |
| **Spring bean definition inheritance** | `<bean parent="baseTemplate">` | Container configuration: constructor args, property values, scope, and applicable metadata |
| **ApplicationContext hierarchy** | child context has a parent context | Ability to look up beans in the parent context and container relationship per configuration |

Do not treat them as three ways of writing the same thing.

For example, class `EmailConfig` may **not extend** class `BaseConfig` at all while its bean definition still has `parent="baseTemplate"`, as long as the final class accepts the inherited properties/arguments. Conversely, `class EmailConfig extends BaseConfig` **does not automatically create** an XML `parent` relationship.

Metadata inheritance can also occur when both parent and child use the **same Java class**, producing two beans with different configurations. That is precisely what the practice exercise uses: both children instantiate `AlertConfig`, without writing Java subclasses merely to change properties.

**Do not confuse with DI:** `parent="baseTemplate"` does not pass a parent bean into the child bean's constructor. If a service needs a real collaborator, use `<constructor-arg ref="..."/>`, `<property ref="..."/>`, or the corresponding constructor injection.

## 3. Declaring an Abstract Parent Bean Definition

### 3.1. Meaning of `abstract="true"`

~~~xml
<bean id="baseTemplate"
      class="demo.AlertConfig"
      abstract="true">
    <property name="prefix" value="BASE"/>
</bean>
~~~

Here `baseTemplate` is an **abstract bean definition**, used as a template. The container retains its metadata, yet forbids looking up the parent as an instantiable bean:

~~~java
context.getBean("baseTemplate"); // Invalid for an abstract bean definition.
~~~

The line above is illustrative; it can throw `BeanIsAbstractException`. It is neither `null` nor an empty instance created as a placeholder. When Spring pre-instantiates singletons during `ApplicationContext.refresh()`, **abstract bean definitions are not created as ordinary singletons**.

If you intend a template **without** setting `abstract="true"`, the container may attempt to instantiate the parent bean like a normal bean, especially when it is a non-lazy singleton. If the template lacks essential properties/arguments, initialization fails; if it can be instantiated, you end up with an unwanted extra instance.

### 3.2. A Parent Can Have No Class

~~~xml
<bean id="commonDefaults" abstract="true">
    <property name="prefix" value="BASE"/>
    <property name="channel" value="general"/>
</bean>

<bean id="childConfig"
      parent="commonDefaults"
      class="demo.AlertConfig"/>
~~~

The XML snippet illustrates a metadata-only template **that does not specify `class`**. In that case, **declaring the parent as abstract is mandatory**, because the parent on its own lacks enough information to be instantiated. The child specifies a suitable class to provide how the instance is constructed.

If the parent already has a class, the child can **inherit that class** without re-declaring `class`. The child can also specify a different class, provided the new class supports the properties/constructor arguments required by the final metadata.

**An abstract bean definition differs from an abstract Java class.** A Java `abstract class` cannot be instantiated directly; XML `abstract="true"` marks a **bean definition** as template-only, even when the Java bean class is concrete.

### 3.3. Can a Non-Abstract Parent Be Used?

Mechanically, an ordinary bean definition can also serve as a parent. However, if its **sole** purpose is a shared template, mark it abstract to avoid the container creating an unnecessary parent singleton. When the parent class has initialization side effects, forgetting to mark it abstract can trigger unwanted connections, file reads, or startup failures.

Do not arbitrarily turn an actual business bean currently in use into abstract: every `getBean("parent")` or `ref` to that bean will stop working.

## 4. Which Parts of Metadata Does Spring Merge?

A child declaration is **merged** by the container with the parent definition. Do not imagine it simply as verbatim XML copying.

### 4.1. What Children Typically Inherit or Override

Key elements that can be inherited from a parent, which the child can then supplement/override:

- **Bean class**: if unspecified by the child, it can be taken from the parent.
- **Constructor argument values**: the child can inherit values defined on the parent, or add/override them according to index, name, and Spring's argument resolution rules.
- **Property values**: properties not re-declared on the child are kept from the parent; if the child redefines the same property, the child's value usually takes precedence.
- **Method override metadata** in the bean definition and certain other applicable settings.
- **Scope**: the child can inherit scope if unspecified; if a different `scope` is specified, the child uses the new scope.
- **Lifecycle/factory settings**: init/destroy methods or factory methods can be declared on the child to override the corresponding metadata.

Spring has specific rules for metadata always taken from the child definition—such as `depends-on` configuration, autowire mode, lazy initialization, and other settings depending on the bean definition type. **Do not assume every XML attribute is inherited/merged by one identical rule.** In particular, verify behavior when mixing `lazy-init` or `depends-on` with parent-child definitions.

### 4.2. Simple Property Configuration: Inheriting and Overriding

~~~xml
<bean id="parentTemplate"
      abstract="true"
      class="demo.AlertConfig">
    <property name="prefix" value="BASE"/>
    <property name="channel" value="general"/>
</bean>

<bean id="emailConfig" parent="parentTemplate">
    <property name="channel" value="email"/>
</bean>
~~~

After merging, `emailConfig` has `prefix=BASE` from the parent yet `channel=email` from the child. The child does not create a parent object and mutate it directly; the container builds the **final metadata** for the child bean.

### 4.3. Constructor Arguments Must Be Consistent

With XML like:

~~~xml
<bean id="baseClient" abstract="true"
      class="demo.Client">
    <constructor-arg index="0" value="localhost"/>
</bean>

<bean id="remoteClient" parent="baseClient">
    <constructor-arg index="1" value="443"/>
</bean>
~~~

This is an **illustrative example**, assuming class `demo.Client` has a matching constructor. The child inherits argument index 0 and adds argument index 1, so a matching constructor must accept both. When parent/child declare arguments by different types/names/indexes, verify carefully how arguments merge and which overload is selected; do not expect Spring to guess business intent if constructors are ambiguous.

### 4.4. Metadata Interpretation Table

| Attribute | Safe interpretation |
| --- | --- |
| `class` | Child can reuse parent's class or substitute a compatible class |
| `constructor-arg` | Inherits/adds/overrides arguments according to matching identifiers |
| `property` | Parent property value remains effective unless overridden by child |
| `scope` | Can inherit scope or declare a different scope on the child |
| `init-method` / `destroy-method` | Can override matching lifecycle configuration |
| `abstract` | Parent used as template is non-instantiable; concrete child must be complete |
| `depends-on`, `lazy-init`, `autowire` | Do not assume they inherit like properties; follows Spring bean definition metadata rules |
| `<list>`/`<set>`/`<map>`/`<props>` | If the same property is re-declared, merging collections requires `merge="true"` **on the child** |

## 5. Collection Merging: A Distinct Behavior to Learn Separately

### 5.1. Default: Replace, Not Automatically Combine

Suppose the parent defines:

~~~xml
<property name="tags">
    <list>
        <value>audit</value>
        <value>core</value>
    </list>
</property>
~~~

And the child also declares the `tags` property:

~~~xml
<property name="tags">
    <list>
        <value>sms</value>
    </list>
</property>
~~~

Without enabling merge on the child, the new list definition **overrides** the old list: the child receives `[sms]`, not `[audit, core, sms]`.

**Note:** if the child **does not re-declare** the `tags` property, it simply **inherits the parent's property intact**; that is not collection merging behavior.

### 5.2. Enabling `merge="true"` on the Child's Collection

~~~xml
<property name="tags">
    <list merge="true">
        <value>mail</value>
    </list>
</property>
~~~

When the parent has `[audit, core]` and the child has `[mail]` with `merge="true"`, Spring produces `[audit, core, mail]`. **List order is preserved**, with parent elements appearing before child elements.

For `<set>`, `<map>`, and `<props>`, Spring also supports merging matching types:

- **List**: appends child elements after parent elements; order is significant.
- **Set**: combines elements with Set semantics, deduplicating by equality; do not rely on unguaranteed ordering.
- **Map**: merges entries; for identical keys, the child value overrides the parent value.
- **Properties (`<props>`)**: like a string key–value map; keys in the child override matching keys from the parent.

Example:

~~~xml
<property name="routes">
    <props merge="true">
        <prop key="support">support-new@demo.test</prop>
        <prop key="sales">sales@demo.test</prop>
    </props>
</property>
~~~

If the parent has `support=support-old@demo.test` and `ops=ops@demo.test`, the child will have three keys: `ops` inherited, `support` overridden, and `sales` added.

### 5.3. Important Limitations

1. `merge="true"` must be placed on **the collection element in the child definition**. Placing it on the parent does not achieve the desired "auto-merge all children" behavior.
2. Both collections must be of **compatible types** to merge; you cannot mix `<map>` with `<list>` and expect Spring to convert arbitrarily.
3. Merging does not apply generically to scalar properties. With `<value>email</value>`, the child simply overrides the parent's scalar value.
4. Do not call this a "general-purpose deep merge of arbitrary objects". Spring applies merging according to bean definition managed collection metadata rules.
5. Do not expect iteration order of `Properties`, `Map`, or `Set` to behave like a List. If stdout needs to be deterministic, **fetch specific keys individually** rather than printing the whole map.
6. Parent-child bean definition merging takes effect when the container builds metadata/instances, not as a runtime list-synchronization algorithm between two objects.

The runnable example below demonstrates **both List replacement and List/Properties merging** in the same context.

## 6. Java 17 + Spring Framework 6.2 Example: Abstract Parent, Child, and Practical Merging

The example uses **XML bean definitions**, because `parent`, `abstract`, and `merge` are expressed directly in Spring's XML syntax. In modern Java configuration projects, `@Configuration`/`@Bean` typically expresses composition or shared factory helpers instead; do not assume there is an equivalent `@Bean(parent="...")` annotation.

### 6.1. Directory Structure

Requires JDK 17+, Maven, and permission to download Maven dependencies on the first run:

~~~text
bean-inheritance-demo/
├── pom.xml
└── src/
    └── main/
        ├── java/
        │   └── demo/
        │       └── TemplateInheritanceDemo.java
        └── resources/
            └── beans.xml
~~~

File `pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>edu.example</groupId>
    <artifactId>bean-inheritance-demo</artifactId>
    <version>1.0-SNAPSHOT</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.0</version>
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
                    <mainClass>demo.TemplateInheritanceDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 6.2. Complete Java File

Save `src/main/java/demo/TemplateInheritanceDemo.java`:

~~~java
package demo;

import java.util.List;
import java.util.Properties;
import org.springframework.context.support.ClassPathXmlApplicationContext;

public final class TemplateInheritanceDemo {
    private TemplateInheritanceDemo() {}

    public static final class AlertConfig {
        private String prefix;
        private String channel;
        private List<String> tags = List.of();
        private Properties routes = new Properties();

        // Public constructor for Spring property injection via setters.
        public AlertConfig() {}

        public void setPrefix(String prefix) {
            this.prefix = prefix;
        }

        public void setChannel(String channel) {
            this.channel = channel;
        }

        public void setTags(List<String> tags) {
            this.tags = tags;
        }

        public void setRoutes(Properties routes) {
            this.routes = routes;
        }

        public String summary() {
            return channel + "|" + prefix + "|" + tags;
        }

        public String route(String key) {
            return routes.getProperty(key);
        }
    }

    public static void main(String[] args) {
        try (ClassPathXmlApplicationContext context =
                     new ClassPathXmlApplicationContext("beans.xml")) {

            boolean parentAbstract = context.getBeanFactory()
                    .getBeanDefinition("baseTemplate").isAbstract();
            System.out.println("PARENT_ABSTRACT " + parentAbstract);

            AlertConfig email =
                    context.getBean("emailConfig", AlertConfig.class);
            AlertConfig sms =
                    context.getBean("smsConfig", AlertConfig.class);

            System.out.println("EMAIL " + email.summary());
            System.out.println("EMAIL_ROUTES "
                    + email.route("ops") + "|"
                    + email.route("support") + "|"
                    + email.route("sales"));

            System.out.println("SMS " + sms.summary());
            System.out.println("SMS_ROUTES "
                    + sms.route("ops") + "|"
                    + sms.route("support"));

            System.out.println("DIFFERENT " + (email != sms));
        }
    }
}
~~~

`AlertConfig` has public setters matching the properties declared in XML. This class **does not inherit from any other Java class defined in the example**; only the bean definitions themselves have a parent–child relationship.

### 6.3. Complete XML File

Save `src/main/resources/beans.xml`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<beans xmlns="http://www.springframework.org/schema/beans"
       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
       xsi:schemaLocation="
           http://www.springframework.org/schema/beans
           https://www.springframework.org/schema/beans/spring-beans.xsd">

    <!-- Template only: does not create a baseTemplate instance -->
    <bean id="baseTemplate"
          class="demo.TemplateInheritanceDemo$AlertConfig"
          abstract="true">

        <property name="prefix" value="BASE"/>
        <property name="channel" value="general"/>

        <property name="tags">
            <list>
                <value>audit</value>
                <value>core</value>
            </list>
        </property>

        <property name="routes">
            <props>
                <prop key="ops">ops@demo.test</prop>
                <prop key="support">support-old@demo.test</prop>
            </props>
        </property>
    </bean>

    <!-- Inherits class, prefix; overrides channel;
         merges list tags and Properties routes. -->
    <bean id="emailConfig" parent="baseTemplate">
        <property name="channel" value="email"/>

        <property name="tags">
            <list merge="true">
                <value>mail</value>
            </list>
        </property>

        <property name="routes">
            <props merge="true">
                <prop key="support">support-new@demo.test</prop>
                <prop key="sales">sales@demo.test</prop>
            </props>
        </property>
    </bean>

    <!-- Inherits class and routes; overrides scalars;
         new list does NOT merge so it replaces parent's list. -->
    <bean id="smsConfig" parent="baseTemplate">
        <property name="channel" value="sms"/>
        <property name="prefix" value="SHORT"/>
        <property name="tags">
            <list>
                <value>sms</value>
            </list>
        </property>
    </bean>
</beans>
~~~

### 6.4. Compile and Run Commands

Open PowerShell/CMD or a Linux/macOS terminal in the `bean-inheritance-demo` directory:

~~~bash
mvn -version
mvn -q compile exec:java
~~~

**Stdout printed by the program in exact order:**

~~~text
PARENT_ABSTRACT true
EMAIL email|BASE|[audit, core, mail]
EMAIL_ROUTES ops@demo.test|support-new@demo.test|sales@demo.test
SMS sms|SHORT|[sms]
SMS_ROUTES ops@demo.test|support-old@demo.test
DIFFERENT true
~~~

Maven and libraries may produce their own logs, especially when downloading dependencies; the block above is only the **stdout from the program's `System.out.println` calls**, not a promise that the entire terminal output will always have only six lines.

### 6.5. What Does Each Line of Stdout Prove?

1. `PARENT_ABSTRACT true`: `baseTemplate`'s metadata has the abstract flag; `getBeanFactory().getBeanDefinition(...)` only inspects metadata, **without creating a parent instance**.
2. `EMAIL email|BASE|[audit, core, mail]`: `emailConfig` overrides channel from `general` to `email`, inherits prefix `BASE`, and merges the list with parent before child.
3. `EMAIL_ROUTES ...`: key `ops` is inherited, key `support` takes the new value from the child, and key `sales` is added. The code reads specific keys so it does not depend on `Properties` iteration order.
4. `SMS sms|SHORT|[sms]`: `smsConfig` overrides prefix and channel, and declares a new list **without `merge="true"`**, so the parent list is replaced.
5. `SMS_ROUTES ...`: the child does not re-declare the routes property, so it directly inherits the parent's routes values, where `support` still holds the old value.
6. `DIFFERENT true`: the two child beans are **two distinct instances**. Sharing the `AlertConfig` class and one parent template does not make them the same bean.

The output is designed to be **independent of singleton creation order**: there is no `println` inside constructors/setters, and both children are looked up explicitly by bean name.

### 6.6. Try Variants to Observe Behavior Yourself

- Remove `merge="true"` from `emailConfig`'s list: the email list is expected to become `[mail]`.
- Place `merge="true"` on the parent's `<props>` while omitting it on the child: does not produce the desired merge effect; the child's new properties replace the old definition.
- Remove `abstract="true"` on the parent: the container can create an extra `baseTemplate` bean because the class is instantiable; you lose the template-only role.
- Try `context.getBean("baseTemplate")` **inside a try/catch in your practice copy**: it will fail because it is an abstract definition. Do not add this call to the main example if you want to keep the published stdout intact.
- Change the child's `class` to another class lacking `setTags`: metadata still inherits `tags` yet property setting will fail. Spring does not automatically adapt the new class to be compatible with the old configuration.

## 7. Programmatic Definition via the `BeanDefinition` API

XML configuration is a visual form. At the API level, Spring uses `BeanDefinition` and implementation types such as `ChildBeanDefinition` to express parent–child relationships where appropriate.

Illustrative metadata-creation example:

~~~java
import org.springframework.beans.factory.support.ChildBeanDefinition;
import org.springframework.beans.factory.support.RootBeanDefinition;

RootBeanDefinition parent =
        new RootBeanDefinition(TemplateInheritanceDemo.AlertConfig.class);
parent.setAbstract(true);
parent.getPropertyValues().add("prefix", "BASE");

ChildBeanDefinition child = new ChildBeanDefinition("baseTemplate");
child.getPropertyValues().add("channel", "email");
~~~

This snippet is **not standalone**: to run it, you must add a bean factory/registry to register `parent` under the name `baseTemplate`, register `child` under its own name, and then retrieve the bean. It is shown so you recognize that XML `parent` ultimately maps to **container metadata**, not a tree of instance objects.

Note that `ChildBeanDefinition` should not be viewed as mandatory in Java annotation configurations. When using `@Bean`, developers generally prefer factoring shared setup into explicit factories/helpers rather than recreating multi-level XML bean-definition inheritance with Java classes.

## 8. When to Use and When to Avoid Overuse

**Appropriate when:**

- Maintaining or designing Spring XML configurations where many child beans share a standard group of settings.
- Several beans share a large common configuration and differ only in a few properties or constructor arguments.
- You want to apply a shared policy configuration across multiple compatible bean implementations.
- You need to merge lists or properties where children only append partial definitions cleanly.

**Consider alternatives when:**

- Children diverge so much that the template holds numerous properties inapplicable to some classes.
- Multiple nested `parent` levels make the origin of final values hard to trace.
- Behavior must vary by runtime business data — bean definition inheritance is startup configuration, not per-request strategy selection.
- Using pure Java configuration: you can declare shared `@Bean` factories, helper constructors, or shared config classes with clear contracts instead of forcing XML `parent="..."` syntax into Java.
- Wanting to reuse *Java code*: use composition/class inheritance when truly appropriate rather than trying to solve every OOP problem with bean definition inheritance.

A good template should contain **stable settings of shared significance**. If every child has to override almost everything, the template adds little value and reduces clarity.

## 9. Common Errors and How to Fix Them

| Symptom / Misconception | Explanation and Fix |
| --- | --- |
| `getBean("baseTemplate")` fails | A parent with `abstract="true"` is a metadata template only, not instantiable. |
| Forgetting `abstract="true"` | A parent with a class may be created as an unwanted singleton during refresh. |
| Parent has no class yet is not abstract | The definition lacks creation info; mark it abstract and ensure the child is complete. |
| Thinking `parent` is Java `extends` | It is configuration inheritance, not changing the class hierarchy. |
| Thinking the child holds a reference to a parent object | The container merges metadata; no parent object is required to be created. |
| Child changes class and fails on properties | The new class lacks the inherited setters/constructors. |
| Child declares a list and loses parent elements | By default, a new collection property replaces the old list; set `merge="true"` on the child. |
| Placing `merge="true"` on the parent | Merging must be enabled on the collection in the child definition. |
| Merging `<list>` with `<map>` | Incompatible collection types; Spring cannot merge them that way. |
| Matching `Properties` key does not take child's value | Check `merge="true"` on the child and exact key; the child might be replacing. |
| Constructor error after merge | Check argument indexes/names/types and actual overloads on the bean class. |
| Thinking all metadata is inherited | `lazy-init`, `depends-on`, and other attributes have their own rules; do not assume. |
| Removing `abstract` to fix a missing-bean error | Determine whether the bean is a template or a real business bean; do not erase this boundary arbitrarily. |
| Multi-level parent-child hierarchies hard to debug | Reduce depth, use clear bean names, inspect merged bean definitions, and write configuration tests. |
| Forgetting to place `beans.xml` in resources | `ClassPathXmlApplicationContext("beans.xml")` cannot find the resource; check path and classpath. |
| Printing raw `Properties` and getting inconsistent stdout | `Properties` does not guarantee print order; read by specific key when deterministic output is needed. |

### Reading Spring Errors

- `BeanIsAbstractException`: attempting to retrieve an abstract bean definition.
- `BeanDefinitionStoreException` or bean definition errors: invalid XML, parent reference, or configuration.
- `BeanCreationException`: bean creation failed, possibly because a constructor or setter received invalid post-merge configuration.
- `NotWritablePropertyException`: the bean class lacks a setter/property matching the declared metadata.
- `NoSuchBeanDefinitionException`: misspelled bean name reference or retrieving an unregistered bean.

Read the **root cause** in the exception chain and the name of the child bean being created. Do not add a manual `new` outside the container merely to bypass configuration errors.

## 10. Self-Study Exercises (with Answers)

**Exercise 1.** Why is `abstract="true"` not synonymous with a Java `abstract` class?

**Answer:** The abstract flag applies to the **Spring bean definition**: the parent serves only as a template and cannot be looked up as an instance. The Java class itself can be concrete, such as `AlertConfig` in the main program.

**Exercise 2.** A child bean has no `class` attribute in XML—which class does it use?

**Answer:** If the parent provides a bean class, the child can inherit that class; if the parent has no class, the child must supply a suitable creation mechanism.

**Exercise 3.** If a child re-declares `<list>` for the same `tags` property, are the two lists automatically concatenated?

**Answer:** No. By default the child replaces the parent's collection property. To concatenate, set `merge="true"` on the child's list.

**Exercise 4.** Parent list `[a,b]` and child list `[c]` with `merge="true"`. What is the result?

**Answer:** `[a,b,c]`, with parent element order preserved before child elements.

**Exercise 5.** Parent has `support=old`, child has `support=new` and `sales=sales` inside `<props merge="true">`. What is the outcome?

**Answer:** Key `support` takes `new`, key `sales` is added; unoverridden parent keys are retained.

**Exercise 6.** Can `<bean parent="baseTemplate">` be used to automatically invoke a Java superclass method via `super`?

**Answer:** No. XML parent-child is metadata only; `super` belongs to Java class inheritance and is unrelated.

**Exercise 7.** In the example, do `emailConfig` and `smsConfig` share a single instance?

**Answer:** No. They are two independent bean definitions that inherit from the same metadata template and share the same bean class, yet create two distinct objects.

**Exercise 8.** If two separate `ApplicationContext` instances load the same `beans.xml`, are the singleton beans the same instance?

**Answer:** Not by default. Singleton scope is per container; loading the same XML does not share objects across two contexts.

**Exercise 9.** Should you migrate an entire modern Java-config application to parent-child XML because it has "fewer lines"?

**Answer:** Not necessarily. Weigh transparency, testability, and the configuration style in use. With Java config, composition and factory methods are usually easier to read than multi-level inherited metadata.

## 11. Configuration Checklist

- [ ] Parents used as templates are declared `abstract="true"`.
- [ ] When a parent has no class, the child supplies a class or valid creation mechanism.
- [ ] Distinguish bean definition inheritance from Java `extends` and context hierarchies.
- [ ] Verify the final bean class has setters/constructors matching inherited metadata.
- [ ] Override scalar properties only on children that genuinely need different values.
- [ ] For collections, decide explicitly between **replace** and **merge**.
- [ ] Place `merge="true"` on the child's list/set/map/props, not only on the parent.
- [ ] Do not merge incompatible collection types.
- [ ] Do not rely on Map/Properties iteration order for stdout assertions.
- [ ] Do not assume scope/lazy/depends-on all inherit like scalar properties.
- [ ] Do not directly look up an abstract parent bean.
- [ ] Avoid accidentally registering duplicate bean names/classes or deep, hard-to-trace parent chains.
- [ ] Ensure XML files are on the classpath and configuration is valid.
- [ ] Write integration tests for merged child definitions and critical properties.
- [ ] Avoid using metadata inheritance to hide runtime business rules.

### Official Spring Documentation

- [Bean Definition Inheritance](https://docs.spring.io/spring-framework/reference/core/beans/child-bean-definitions.html)
- [Collection Merging](https://docs.spring.io/spring-framework/reference/core/beans/dependencies/factory-properties-detailed.html)
- [Bean Overview](https://docs.spring.io/spring-framework/reference/core/beans/definition.html)

**Conclusion:** `abstract="true"` turns a parent bean definition into a **non-instantiable configuration template**. A child with `parent="..."` inherits and overrides applicable metadata; for collections, `merge="true"` on the child merges elements according to List, Set, Map, or Properties semantics. This is a **Spring configuration-reuse technique**, not Java code inheritance or injecting a parent object.