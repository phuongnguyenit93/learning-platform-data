# XML Autowiring by Name, by Type, and Its Limitations in Spring Framework

## 1. When You Do Not Want to Write Every `<property ref="..."/>` by Hand

The Spring Core Container manages objects (beans) and their dependency relationships. With XML bean definitions, the clearest way to wire two beans is explicit declaration:

```xml
<bean id="inventoryRepository" class="demo.InventoryRepository"/>

<bean id="inventoryService" class="demo.InventoryService">
    <property name="repository" ref="inventoryRepository"/>
</bean>
```

This is **illustrative XML**; to run in practice, `InventoryService` must have a matching `setRepository(...)` setter and both classes must exist on the runtime classpath.

Spring also supports **XML autowiring**: on a `<bean>` definition, you set the `autowire` attribute so the BeanFactory locates collaborators by property name, property type, or constructor. Example:

```xml
<bean id="repository" class="demo.InventoryRepository"/>

<bean id="inventoryService"
      class="demo.InventoryService"
      autowire="byName"/>
```

When `inventoryService` has a writable JavaBean property `repository` (such as `setRepository(...)`), Spring can locate the bean named exactly `repository` and invoke the setter. You do not need to write `<property name="repository" ref="repository"/>` on this bean.

However, autowiring **does not mean Spring picks a matching bean at random**, nor does it override the rules of bean names, types, scopes, or lifecycles. XML autowiring has clear limits: scalar values are not guessed automatically, multiple candidates can cause errors, some properties are skipped if no candidate exists, and dependency relationships become less explicit.

After this lesson, you will be able to:

1. Distinguish `autowire="no"`, `"byName"`, `"byType"`, and `"constructor"`.
2. Understand JavaBean property naming standards and how Spring resolves beans by name/type.
3. Recognize missing candidates, ambiguous candidates, primary candidates, and beans excluded from autowiring.
4. Use `autowire-candidate="false"`, `primary="true"`, and `default-autowire-candidates` properly.
5. Understand why explicit `<property>`/`<constructor-arg>` declarations take precedence.
6. Understand collection/array/map autowiring and limitations with scalar properties.
7. Distinguish XML autowiring from `@Autowired` annotations and JavaConfig.
8. Run a Java 17+ / Spring Framework 6.2 demo with stdout verifying byName, byType, explicit refs, and candidate filtering.
9. Know how to verify configurations, design clear dependencies, and avoid runtime failures.

## 2. Four Main Modes of XML Autowiring

In Spring Framework 6.2, the `autowire` attribute on `<bean>` accepts four main modes:

| XML mode | How dependencies are found | When no bean matches | When multiple beans match |
| --- | --- | --- | --- |
| `no` | No automatic wiring; requires `ref`/`constructor-arg` or another mechanism | Property is not automatically supplied | No automatic lookup for that property |
| `byName` | Looks for a bean whose **name matches the JavaBean property name** | Property is not set by `byName` | Does not fall back randomly by type; name match decides |
| `byType` | Looks for a bean matching **the type of a writable property** | For a single dependency, the setter may be skipped | Without a single winning candidate, ambiguity error |
| `constructor` | Resolves **constructor parameters** similarly to by-type resolution | Unresolved required constructor usually fails bean creation | Without a winning candidate for a single dependency, fails |

The default mode on `<bean>` is **`no`**. Spring does not require every XML bean to be autowired automatically.

Syntax examples:

```xml
<bean id="manual" class="demo.Service" autowire="no"/>
<bean id="named" class="demo.Service" autowire="byName"/>
<bean id="typed" class="demo.Service" autowire="byType"/>
<bean id="constructed" class="demo.ConstructorService"
      autowire="constructor"/>
```

These are **illustrative** bean definitions; the classes are placeholder names. On each bean definition, `autowire` specifies **how Spring locates dependencies for this bean**, not that this bean itself has become a required dependency of another bean.

### 2.1. `autowire="no"` Does Not Forbid Injection

`no` means **do not automatically resolve collaborators using XML autowiring**. You can still configure:

```xml
<bean id="service" class="demo.Service" autowire="no">
    <property name="repository" ref="repository"/>
</bean>
```

or pass constructor arguments. Likewise, a bean with `autowire="no"` can still receive annotation-based injection if Spring has the relevant post-processors enabled and the class carries matching annotations.

Do not conflate `autowire="no"` with `autowire-candidate="false"`. The first controls **whether this bean autowires its own dependencies via XML**; the second controls **whether this bean is eligible as a candidate to be injected by type into other beans**.

### 2.2. Autowiring Is Configured Per Bean

`<bean id="a" ... autowire="byType"/>` only instructs the BeanFactory to resolve **bean `a`**'s dependencies by type; it does not force every other bean to switch to `byType`.

You can set `default-autowire="byType"` on the `<beans>` root if you want a default for bean definitions that do not specify one individually:

```xml
<beans xmlns="http://www.springframework.org/schema/beans"
       default-autowire="byType">
    <bean id="a" class="demo.A"/>
    <bean id="b" class="demo.B" autowire="no"/>
</beans>
```

This is **illustrative XML**, not needed in the main demo below. Root-level defaults reduce repetition but can obscure the dependency graph and cause unintended wiring as a project grows. Spring documentation encourages explicitness in large systems.

## 3. `byName`: Bean Name Must Match JavaBean Property Name

Given the Java class:

```java
package demo;

public final class InvoiceService {
    private InvoiceRepository repository;

    public void setRepository(InvoiceRepository repository) {
        this.repository = repository;
    }

    public InvoiceRepository getRepository() {
        return repository;
    }
}
```

Spring recognizes a **writable property named `repository`** from `setRepository(...)`. If XML declares:

```xml
<bean id="repository" class="demo.InvoiceRepository"/>
<bean id="invoiceService"
      class="demo.InvoiceService"
      autowire="byName"/>
```

Spring looks up the bean named strictly `repository` and performs setter injection. That is what “by name” means.

**Note:** the two fragments here reference a hypothetical `InvoiceRepository` class; they do not form a standalone compilable project until that class is defined.

### 3.1. JavaBean Property Name Is Not Necessarily the Field Name

With:

```java
private Repository primaryStore;

public void setRepository(Repository value) {
    this.primaryStore = value;
}
```

the property name is still `repository` because the method is named `setRepository`. XML `autowire="byName"` looks up bean `repository`, not `primaryStore`, regardless of the field name.

If you rename the setter to `setPrimaryStore(...)`, the property name becomes `primaryStore`. Bean naming conventions thus directly affect XML `byName` wiring.

### 3.2. What If No Bean Has the Matching Name?

Suppose the class has `setRepository(...)` while the registry only contains a bean named `mainRepository`. `byName` mode does not fall back to looking at type `Repository` and picking `mainRepository` like `byType` would. That setter may simply be skipped, leaving the default field value — usually `null`.

```xml
<bean id="mainRepository" class="demo.InvoiceRepository"/>
<bean id="invoiceService"
      class="demo.InvoiceService"
      autowire="byName"/>
```

The result is **not** guaranteed to be an immediate configuration error at refresh. If business code later assumes `repository` is non-null, a late `NullPointerException` can occur. Write integration tests or validation for critical dependencies.

Intentional fixes: rename the bean to `repository`, add `<alias name="mainRepository" alias="repository"/>`, or use explicit `<property name="repository" ref="mainRepository"/>`.

### 3.3. `byName` Does Not Mean “Similar Class Name”

Property name `repository` is never treated as a fuzzy-matching hint. Beans named `repositoryImpl` or `Repository` with different casing are **not automatically picked** just for looking similar. If you cannot guarantee naming conventions, use explicit `ref` or `byType`/qualifiers.

### 3.4. The Bean Must Be Compatible with the Setter Type

The bean name may match while the instance does not fit the setter's type:

```xml
<bean id="repository" class="java.lang.String">
    <constructor-arg value="oops"/>
</bean>
<bean id="invoiceService"
      class="demo.InvoiceService"
      autowire="byName"/>
```

If the setter expects `InvoiceRepository`, Spring cannot normally assign a `String` bean to that property. This triggers a `TypeMismatchException`/`BeanCreationException` or conversion error. `byName` selects by **name**, yet must still satisfy Java type contracts when assigning the object.

### 3.5. Bean Aliases Participate in Name Lookup

If:

```xml
<bean id="mainRepository" class="demo.InvoiceRepository"/>
<alias name="mainRepository" alias="repository"/>
```

the bean can be looked up as `repository`; `byName` mode can leverage registered aliases. The alias points to the same bean definition without creating an extra object just because it has two names.

## 4. `byType`: A Single Dependency Needs One Winning Candidate

With:

```java
public class InvoiceService {
    private Repository store;

    public void setStore(Repository store) {
        this.store = store;
    }
}
```

`autowire="byType"` searches for beans of type `Repository` matching the parameter of writable property `store`. Property name `store` **does not need** to match the bean name.

Example:

```xml
<bean id="dbRepository" class="demo.DatabaseRepository"/>
<bean id="invoiceService"
      class="demo.InvoiceService"
      autowire="byType"/>
```

If `DatabaseRepository implements Repository` and is the sole eligible autowire candidate, Spring injects `dbRepository` into `setStore(Repository)` even though its name differs from `store`.

### 4.1. No Candidate Found

If no bean of type `Repository` matches, Spring XML `byType` for a single property normally **does not invoke the setter**, rather than always throwing an exception. The class may keep `store == null`. This differs from `@Autowired`, which defaults to `required=true`, and from required constructor dependencies.

**Design consequence:** for truly indispensable dependencies, do not rely solely on `byType` setters without tests. Constructor injection or explicit dependency declarations surface errors earlier.

### 4.2. Exactly One Candidate

If `dbRepository` is the only eligible candidate, Spring injects it. The type can be an interface or superclass that the implementation implements or extends. No bean-name match with the property name is required.

### 4.3. Multiple Candidates

Example:

```xml
<bean id="primaryRepository" class="demo.DatabaseRepository"/>
<bean id="backupRepository" class="demo.InMemoryRepository"/>

<bean id="invoiceService"
      class="demo.InvoiceService"
      autowire="byType"/>
```

If both implement `Repository` and both are candidates, Spring must not choose one arbitrarily. Without another selection rule, you encounter `NoUniqueBeanDefinitionException` or `UnsatisfiedDependencyException`/`BeanCreationException` wrapping the cause.

Ways to resolve:
- Use `<property name="store" ref="primaryRepository"/>` to specify the exact bean.
- Use `primary="true"` to designate one default where appropriate.
- Set `autowire-candidate="false"` on beans you want excluded from type-based autowiring.
- Change the design from a single dependency to a collection if the consumer genuinely needs multiple implementations.
- With annotation-based injection, `@Qualifier` and related refinement mechanisms express specific intent.

### 4.4. `primary="true"` Is a Selection Preference

```xml
<bean id="fastRepository"
      class="demo.FastRepository"
      primary="true"/>

<bean id="safeRepository"
      class="demo.SafeRepository"/>

<bean id="invoiceService"
      class="demo.InvoiceService"
      autowire="byType"/>
```

When two implementations share a type and `fastRepository` is the unique eligible primary candidate, Spring selects it for a single `byType` dependency. Do not mark multiple peer beans `primary="true"` expecting ambiguity to vanish.

**Primary does not filter collections:** an injection point of type `List<Repository>` still receives all eligible repository candidates even when one is primary, because that request asks for “the set of beans,” not “a single default bean.”

### 4.5. Property Name Fallback and Differences from `byName`

Modern candidate resolution can inspect multiple signals when resolving a single bean dependency, depending on the Spring version and injection point. Even so, never treat `autowire="byType"` as identical to `byName`: `byType` starts from the **property type**, not unconditionally by property name; when multiple candidates exist, express intent clearly with `primary`, qualifiers, or explicit `ref`.

In hands-on work, explicitly test having two beans of the same interface rather than relying on version-specific name/parameter-name fallback details.

## 5. `constructor`: Dependencies Resolved Before Creating the Object

Given the Java class:

```java
package demo;

public final class CheckoutService {
    private final PaymentGateway gateway;

    public CheckoutService(PaymentGateway gateway) {
        this.gateway = gateway;
    }

    public PaymentGateway getGateway() {
        return gateway;
    }
}
```

And XML:

```xml
<bean id="paymentGateway" class="demo.LocalPaymentGateway"/>
<bean id="checkoutService"
      class="demo.CheckoutService"
      autowire="constructor"/>
```

Spring selects an appropriate constructor, resolves its parameters via type-based resolution, and supplies the dependencies when instantiating. If the class has a single required constructor taking `PaymentGateway` and no candidate exists, context startup typically fails when creating the bean.

**Important distinction:** XML `byName`/`byType` mainly target **writable setters**; `constructor` mode targets **constructor arguments**. They are not the same mechanism under two names.

### 5.1. Constructor Injection Guarantees Dependencies at Creation Time

If `CheckoutService` only has `CheckoutService(PaymentGateway gateway)`, Spring cannot instantiate it without supplying a gateway. Required dependencies are therefore explicit in the Java API, and configuration mistakes surface when the container creates the bean.

Setter injection for an unset field can leave it `null` and fail much later. This is why modern codebases prefer constructor injection for essential dependencies, even when XML remains the configuration format.

### 5.2. Multiple Constructors and Overloads

If a class has multiple constructors, Spring must select a signature compatible with available candidates and metadata. XML `autowire="constructor"` considers constructor candidates; ambiguity or unconvertible types can trigger failures rather than blindly picking “the longest constructor” regardless of resolvability.

When overloaded constructors or simple types like `String`/`int` are involved, declare `<constructor-arg index="..." type="..." value="..."/>` or explicit `ref` to avoid relying on constructor-selection heuristics and parameter-name metadata.

### 5.3. Constructor Autowiring Does Not Guess Literals

For `PaymentClient(String endpoint, int timeout)`, XML `autowire="constructor"` does not guess endpoint or timeout from bean names or synthesize default values. Simple scalars are not treated as collaborator beans for automatic wiring.

Example:

```xml
<bean id="client" class="demo.PaymentClient"
      autowire="constructor">
    <constructor-arg index="0" value="https://api.example.test"/>
    <constructor-arg index="1" value="2500"/>
</bean>
```

This is an **illustration** requiring `demo.PaymentClient` with a matching constructor. Both literals are supplied via explicit constructor arguments; autowiring can still resolve remaining arguments if the signature also requires bean dependencies.

### 5.4. Constructor Injection Is Not JavaConfig Bean-Method Interception

Unlike JavaConfig `@Bean A a(B b)`, XML constructor autowiring invokes a Java constructor on the target bean class. It does not depend on `@Configuration(proxyBeanMethods=true)` or CGLIB intercepting Java config methods. BeanFactory still manages scope and lifecycle per the XML definition.

## 6. Limitation: Spring Does Not Autowire “Simple Properties”

According to the Spring Reference, XML autowiring does not automatically populate simple properties such as primitives, `String`, `Class`, and arrays of simple types solely by name or type. This is intentional: configuration values carry domain-specific meaning, and Spring cannot guess a valid default string or number for business logic.

Consider:

```java
public class MailConfig {
    private String sender;
    private int retries;
    private MailRepository repository;

    public void setSender(String sender) { this.sender = sender; }
    public void setRetries(int retries) { this.retries = retries; }
    public void setRepository(MailRepository repository) {
        this.repository = repository;
    }
}
```

Even with `autowire="byType"`, Spring can supply the `MailRepository` collaborator if a suitable candidate exists, yet will not guess `sender` and `retries` just from their property types.

Explicit values are required:

```xml
<bean id="mailConfig" class="demo.MailConfig"
      autowire="byType">
    <property name="sender" value="no-reply@example.test"/>
    <property name="retries" value="3"/>
</bean>
```

The same applies to `autowire="byName"`: do not register a `String` bean named `sender` treating that as a general config-value injection pattern, because Spring deliberately avoids wiring simple properties under XML autowiring rules.

**Do not confuse:** you can still write `<property name="sender" ref="someStringBean"/>` if a design intentionally references a `String` bean object; that is an **explicit `ref`**, distinct from XML autowire discovery.

### 6.1. `value` Is Type-Converted for the Setter/Constructor

`<property name="retries" value="3"/>` holds an XML string literal. Spring's conversion infrastructure converts it to `int` because the setter expects `int`. Writing `value="three"` triggers a type mismatch. That is a conversion error, not an autowiring candidate error.

### 6.2. Optional Setter Dependencies Are Possible

With `setAuditSink(AuditSink sink)`, XML `byType` skips the setter if no matching `AuditSink` bean exists. In Java, the default `null` or a NoOp implementation assigned in the constructor stays intact. If the feature is genuinely optional, document that policy explicitly and test both with and without a provider; do not turn a required dependency into an optional one just to let the context start.

## 7. Explicit Wiring Always Overrides Autowiring

Example:

```xml
<bean id="fastGateway" class="demo.FastGateway"/>
<bean id="slowGateway" class="demo.SlowGateway"/>

<bean id="service" class="demo.CheckoutService"
      autowire="byType">
    <property name="gateway" ref="slowGateway"/>
</bean>
```

If the class has `setGateway(Gateway)`, the explicit property setting locks in `slowGateway`; Spring **does not overwrite** it with a `byType` lookup merely because the bean has `autowire="byType"`.

The same rule applies to explicit `<constructor-arg>` when using `autowire="constructor"`. This is valuable when evolving XML: you can enable autowiring for most collaborators while keeping explicit wiring for critical dependencies.

### 7.1. Why Explicit Configuration Remains Useful

- Reading XML immediately shows which bean a service uses.
- Adding another bean implementing the same interface cannot silently swap the collaborator.
- Allows selecting a bean that is excluded from type-based autowiring.
- Helpful in sensitive areas such as payments, transactions, and security.
- Configuration analysis tools get clearer relationship metadata.

Autowiring does not replace the value of **documenting the dependency graph** in configuration; it merely reduces verbosity when candidate resolution is simple and naming conventions are stable.

## 8. `autowire-candidate="false"`: Excluding from Type Selection Without Deleting the Bean

A frequently misunderstood attribute:

```xml
<bean id="backupStore"
      class="demo.BackupStore"
      autowire-candidate="false"/>
```

The bean remains registered in the container and can be looked up by name or type through container APIs. However, BeanFactory **does not consider this bean a candidate for type-based autowiring** when wiring other injection points.

Per Spring Framework Reference 6.2, this flag:

- excludes the bean from **type-based** autowire candidate resolution, including annotation injection points such as `@Autowired`;
- **does not forbid explicit `ref` by name**, such as `<property name="store" ref="backupStore"/>`;
- **does not block `byName` autowiring** when a property has the exact name `backupStore`;
- does not stop `backupStore` itself from using `autowire="byType"` to resolve its own dependencies.

### 8.1. Comparison Table

Suppose bean `backupStore` has `autowire-candidate="false"`:

| How `backupStore` is requested | Can it receive `backupStore`? | Explanation |
| --- | --- | --- |
| `autowire="byType"` for a property of type `Store` | Excluded bean is not selected as candidate | Type-based resolution skips it |
| `autowire="constructor"` needing `Store` | Excluded bean is not selected as candidate | Type-based constructor dependency |
| `autowire="byName"` for property named `backupStore` | Yes | Name matching is not blocked by this flag |
| `<property name="store" ref="backupStore"/>` | Yes | Explicit named reference |
| `context.getBean("backupStore")` | Yes | Direct lookup by name remains valid |

**Avoid this pitfall:** do not use `autowire-candidate="false"` to forbid access to a bean everywhere. It is not a security boundary or access-control mechanism.

### 8.2. Combining `primary="true"` and Candidate Exclusion

If Store A is `primary` yet `autowire-candidate="false"`, it does not become eligible for type-based injection just by being primary. Type-based resolution filters eligible candidates first; primary preference applies within that eligible set.

If there are two candidates and one unique primary bean, Spring selects the primary bean. If all candidates for a dependency are excluded, a `byType` setter is skipped while a required constructor fails.

## 9. `default-autowire-candidates` on the `<beans>` Root

Spring XML can filter candidates by **bean name patterns** at the root level:

```xml
<beans xmlns="http://www.springframework.org/schema/beans"
       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
       default-autowire-candidates="*Repository,core*"
       xsi:schemaLocation="
           http://www.springframework.org/schema/beans
           https://www.springframework.org/schema/beans/spring-beans.xsd">

    <bean id="orderRepository" class="demo.OrderRepository"/>
    <bean id="diagnosticRepository" class="demo.DiagnosticRepository"/>
    <bean id="billingService" class="demo.BillingService"/>
</beans>
```

This is illustrative XML; patterns `*Repository` and `core*` describe **eligible bean names** for definitions that do not specify `autowire-candidate` explicitly. It neither scans packages nor creates new beans.

**Policy note:** per Spring documentation, an **explicit** `autowire-candidate` attribute on an individual `<bean>` overrides the default patterns. To guarantee a bean is excluded, place `autowire-candidate="false"` directly on that bean definition.

`default-autowire-candidates` differs from `default-autowire`:
- `default-autowire` sets the **wiring mode used by beans to resolve their dependencies**.
- `default-autowire-candidates` limits which beans are **considered as type-based candidates**.

They govern opposite ends of a DI relationship, not two ways of writing the same setting.

## 10. Collections, Arrays, and `Map<String,T>` in `byType`/`constructor` Mode

XML `byType` and `constructor` modes do not only select single objects. When an injection point is an array or typed collection, Spring can gather **all eligible beans of that type**:

```java
public void setHandlers(List<Handler> handlers) {
    this.handlers = handlers;
}
```

or:

```java
public void setHandlers(Handler[] handlers) {
    this.handlers = handlers;
}
```

If the context has matching `Handler` candidates, Spring injects them all into the collection or array. For `Map<String, Handler>`, keys are **bean names** and values are the corresponding `Handler` instances.

XML example:

```xml
<bean id="emailHandler" class="demo.EmailHandler"/>
<bean id="smsHandler" class="demo.SmsHandler"/>

<bean id="pipeline" class="demo.Pipeline"
      autowire="byType"/>
```

Assuming `Pipeline` has `setHandlers(List<Handler>)`, it can receive both handlers when types/generics match and candidates are not excluded. The property name does not need to be `emailHandler` or `smsHandler`.

### 10.1. Collections Need Clear Element Types

A raw `List` or raw `Map` lacks generic type information, preventing Spring from knowing which bean type to gather. Always use parameterized types such as `List<Handler>` or `Map<String, Handler>` in the Java API.

### 10.2. `primary` Does Not Filter Out Collection Members

If `emailHandler` has `primary="true"`, a `List<Handler>` collection can still contain both email and sms handlers; `primary` primarily resolves **a single dependency** among multiple candidates.

### 10.3. `autowire-candidate` Filtering Applies to Collections

If `smsHandler` is marked `autowire-candidate="false"`, a collection **autowired by type** will exclude it even though the bean exists in the context. By contrast, an explicit `<list><ref bean="smsHandler"/></list>` can still include it.

### 10.4. Empty Sets and Exceptions

Do not apply a blanket rule “every collection receives an empty list” across all injection mechanisms. XML `byType` setters, annotation constructor injection, and Spring Framework versions differ in required/optional semantics. If empty is valid in business logic, define the contract clearly, initialize a default collection or provide an explicit XML list, and test the real behavior.

### 10.5. List Ordering

In collection injection, order can be influenced by `Ordered`, `@Order`, `@Priority`, or a matching comparator. Do not rely on incidental component-scan or bean-registration order for a business-critical pipeline sequence; when order is part of the contract, declare and assert it explicitly.

## 11. How Does XML Autowiring Differ from `@Autowired` and `@Resource`?

Three conceptual mechanisms must be separated:

1. **XML autowiring**: the `autowire` attribute on an XML `<bean>` instructs BeanFactory to populate setters/constructors via `byName`/`byType`/`constructor`.
2. **`@Autowired`**: annotation-based injection processed by annotation infrastructure such as `AutowiredAnnotationBeanPostProcessor`, with its own candidate selection and `required` semantics.
3. **`@Resource`**: a (Jakarta) annotation with name-oriented semantics in applicable contexts; requires annotation processing infrastructure.

These mechanisms can coexist in one context, yet should never be treated as **completely identical**.

| Topic | XML `autowire="byName"` | XML `autowire="byType"` | Annotation `@Autowired` |
| --- | --- | --- | --- |
| Where declared | `<bean>` definition | `<bean>` definition | Java field, constructor, method, or parameter |
| Primary matching basis | JavaBean property name | Property type | Type-based dependency resolution |
| Missing candidate for single dependency | Setter may be skipped | Setter may be skipped | Defaults to `required=true`, typically throwing an error |
| Multiple candidates of same type | Name match governs | Needs a single winning candidate | Qualifiers, primary, name fallback, and resolver rules |
| Requires Spring annotations on domain class? | No | No | Yes |
| Requires annotation processing infrastructure? | Not for pure XML autowiring | Not for pure XML autowiring | Yes |
| Automatically wires scalar types? | Not arbitrarily | Not arbitrarily | Simple types normally need explicit `@Value`/config mechanisms |

### 11.1. What Does Enabling `<context:annotation-config/>` Do?

If an XML file includes `<context:annotation-config/>` with the `context` namespace declared properly, Spring registers infrastructure to process annotations on **already-registered managed beans**. It does not scan the classpath for new beans; bean definitions or component scanning are still required.

Conversely, **XML `autowire="byType"` does not require `<context:annotation-config/>`**. This lesson's demo uses no annotation injection on its domain classes.

### 11.2. Which Mechanism Should New Code Use?

Constructor injection is usually clearer for required dependencies. With Java 17+ and JavaConfig, you can use an explicit constructor, bean definitions from `@Component`/`@Bean`, and type/qualifier injection. When maintaining legacy Spring XML, knowing the autowire modes lets you read and migrate configurations accurately; you do not have to rewrite every XML file to annotations just to shorten it.

## 12. Runnable Example with Java 17+ and Spring Framework 6.2

This example intentionally **uses neither `@Autowired` nor `@ComponentScan`** to isolate XML autowiring behavior. All beans are declared in a single XML file.

We will verify:

- `byName` receives bean `backupStore` matching the JavaBean property name, **even though** backup has `autowire-candidate="false"`.
- `byType` receives bean `mainStore` for the `Store` interface because backup is excluded from type-based candidate resolution.
- `constructor` receives `mainStore` before the constructor executes.
- Explicit `<property ref="backupStore"/>` overrides autowiring and still points to backup.
- `byType` injects `List<Store>` from eligible candidates.
- Simple property `caption` must be configured via `value`; an optional `AuditPort` with no matching bean remains `null`.

Every bean in this example uses the default singleton scope.

### 12.1. Project Structure

```text
xml-autowiring-demo/
├── settings.gradle
├── build.gradle
└── src/
    └── main/
        ├── java/
        │   └── demo/
        │       └── XmlAutowiringDemo.java
        └── resources/
            └── autowire-context.xml
```

File `settings.gradle`:

```groovy
rootProject.name = 'xml-autowiring-demo'
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
    mainClass = 'demo.XmlAutowiringDemo'
}
```

Use JDK 17+ and a compatible Gradle version. `spring-context` pulls in `spring-beans`/`spring-core`; no Spring Boot, server, or database is needed. The example uses a single Java file with **`public static` nested classes** to avoid cluttering many files, so XML class names use `$` per Java binary naming rules.

### 12.2. Complete Java Code

Create `src/main/java/demo/XmlAutowiringDemo.java`:

```java
package demo;

import java.util.List;
import org.springframework.context.support.ClassPathXmlApplicationContext;

public final class XmlAutowiringDemo {

    public interface Store {
        String label();
    }

    public record MainStore() implements Store {
        @Override
        public String label() {
            return "main";
        }
    }

    public record BackupStore() implements Store {
        @Override
        public String label() {
            return "backup";
        }
    }

    public interface AuditPort {
        String audit();
    }

    public static class ByNameConsumer {
        private Store backupStore;

        public void setBackupStore(Store backupStore) {
            this.backupStore = backupStore;
        }

        public Store getBackupStore() {
            return backupStore;
        }
    }

    public static class ByTypeConsumer {
        private Store selected;

        public void setSelected(Store selected) {
            this.selected = selected;
        }

        public Store getSelected() {
            return selected;
        }
    }

    public static class ConstructorConsumer {
        private final Store selected;

        public ConstructorConsumer(Store selected) {
            this.selected = selected;
        }

        public Store getSelected() {
            return selected;
        }
    }

    public static class ExplicitConsumer {
        private Store selected;

        public void setSelected(Store selected) {
            this.selected = selected;
        }

        public Store getSelected() {
            return selected;
        }
    }

    public static class FleetConsumer {
        private List<Store> stores = List.of();

        public void setStores(List<Store> stores) {
            this.stores = stores;
        }

        public List<Store> getStores() {
            return stores;
        }
    }

    public static class SettingsConsumer {
        private String caption = "unset";
        private AuditPort auditPort;

        public void setCaption(String caption) {
            this.caption = caption;
        }

        public void setAuditPort(AuditPort auditPort) {
            this.auditPort = auditPort;
        }

        public String getCaption() {
            return caption;
        }

        public AuditPort getAuditPort() {
            return auditPort;
        }
    }

    public static void main(String[] args) {
        try (var context = new ClassPathXmlApplicationContext(
                "autowire-context.xml")) {

            Store main = context.getBean("mainStore", Store.class);
            Store backup = context.getBean("backupStore", Store.class);

            ByNameConsumer byName =
                    context.getBean(ByNameConsumer.class);
            ByTypeConsumer byType =
                    context.getBean(ByTypeConsumer.class);
            ConstructorConsumer constructor =
                    context.getBean(ConstructorConsumer.class);
            ExplicitConsumer explicit =
                    context.getBean(ExplicitConsumer.class);
            FleetConsumer fleet =
                    context.getBean(FleetConsumer.class);
            SettingsConsumer settings =
                    context.getBean(SettingsConsumer.class);

            System.out.println("byName = " +
                    byName.getBackupStore().label());
            System.out.println("byType = " +
                    byType.getSelected().label());
            System.out.println("constructor = " +
                    constructor.getSelected().label());
            System.out.println("explicit = " +
                    explicit.getSelected().label());
            System.out.println("byNameSameBackup = " +
                    (byName.getBackupStore() == backup));
            System.out.println("byTypeSameMain = " +
                    (byType.getSelected() == main));
            System.out.println("explicitSameBackup = " +
                    (explicit.getSelected() == backup));
            System.out.println("fleet = " +
                    fleet.getStores().stream()
                         .map(Store::label).toList());
            System.out.println("caption = " +
                    settings.getCaption());
            System.out.println("missingAudit = " +
                    (settings.getAuditPort() == null));
        }
    }
}
```

The Java code has a single top-level public class. Both records `MainStore` and `BackupStore` are nested types implementing `Store`; they have no-arg canonical constructors because the records declare no components. The consumer classes provide matching setters or constructors so BeanFactory executes each mode.

### 12.3. Complete XML Bean Definitions

Create `src/main/resources/autowire-context.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<beans xmlns="http://www.springframework.org/schema/beans"
       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
       xsi:schemaLocation="
           http://www.springframework.org/schema/beans
           https://www.springframework.org/schema/beans/spring-beans.xsd">

    <bean id="mainStore"
          class="demo.XmlAutowiringDemo$MainStore"/>

    <bean id="backupStore"
          class="demo.XmlAutowiringDemo$BackupStore"
          autowire-candidate="false"/>

    <bean id="byName"
          class="demo.XmlAutowiringDemo$ByNameConsumer"
          autowire="byName"/>

    <bean id="byType"
          class="demo.XmlAutowiringDemo$ByTypeConsumer"
          autowire="byType"/>

    <bean id="constructor"
          class="demo.XmlAutowiringDemo$ConstructorConsumer"
          autowire="constructor"/>

    <bean id="explicit"
          class="demo.XmlAutowiringDemo$ExplicitConsumer"
          autowire="byType">
        <property name="selected" ref="backupStore"/>
    </bean>

    <bean id="fleet"
          class="demo.XmlAutowiringDemo$FleetConsumer"
          autowire="byType"/>

    <bean id="settings"
          class="demo.XmlAutowiringDemo$SettingsConsumer"
          autowire="byType">
        <property name="caption" value="XML-configured"/>
    </bean>
</beans>
```

Note the `$` in the class names: those are **Java binary names for nested classes**, not typos. If you refactor them into top-level classes, update the XML class names to the new fully qualified names.

### 12.4. Run Command and Stdout

In the project directory:

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

**Lines printed by the program:**

```text
byName = backup
byType = main
constructor = main
explicit = backup
byNameSameBackup = true
byTypeSameMain = true
explicitSameBackup = true
fleet = [main]
caption = XML-configured
missingAudit = true
```

This is the business stdout from `System.out.println`. Depending on Gradle/logging configuration, the environment may print additional lines outside these statements.

### 12.5. Analyzing Each Output Line

**`byName = backup`:** `ByNameConsumer` has writable property `backupStore` via `setBackupStore(Store)`, so `byName` resolves strictly to the bean named `backupStore`. The attribute `autowire-candidate="false"` does not block name-based wiring, per Spring documentation.

**`byType = main`:** `ByTypeConsumer` needs a `Store` in `setSelected(Store)`. `mainStore` is an eligible candidate; `backupStore` is excluded from type-based autowiring, so Spring selects `main`.

**`constructor = main`:** `ConstructorConsumer(Store selected)` receives `Store` via constructor autowiring. Even though `backupStore` exists in the registry, it is not an eligible `Store` candidate for this injection point.

**`explicit = backup`:** `ExplicitConsumer` has `autowire="byType"`, yet XML also declares `<property name="selected" ref="backupStore"/>`. Explicit `ref` takes precedence; even though backup is excluded from type-based autowiring, it is still looked up by name and injected successfully.

**The three `Same... = true` lines:** `==` identity proves the consumers receive the exact managed singleton references, not fresh copies constructed from name or type. Default bean scopes are singleton, so the context holds one `MainStore` and one `BackupStore`.

**`fleet = [main]`:** `setStores(List<Store>)` receives all eligible `Store` candidates. Because backup is excluded from type-based candidate selection, the list contains only `main`. This has nothing to do with the property name `stores`.

**`caption = XML-configured`:** the simple `String` property is supplied via explicit `<property value="..."/>`, not by `byType` searching for a `String` bean.

**`missingAudit = true`:** no `AuditPort` bean exists, so the `byType` setter for optional-looking `auditPort` is not invoked; the field stays `null`. If a real application cannot accept `null`, tighten the contract and wiring.

### 12.6. Variation 1: Two Candidates and Ambiguity

Edit `backupStore` in XML to remove `autowire-candidate="false"`, keeping `byType` and `constructor` unchanged:

```xml
<bean id="mainStore"
      class="demo.XmlAutowiringDemo$MainStore"/>
<bean id="backupStore"
      class="demo.XmlAutowiringDemo$BackupStore"/>
<bean id="byType"
      class="demo.XmlAutowiringDemo$ByTypeConsumer"
      autowire="byType"/>
```

This is a **test experiment fragment** (not a complete file). With two eligible `Store` beans and no tie-breaker, creating `byType` fails due to ambiguity. Run this scenario in a **separate test XML** rather than altering the main demo if you want to keep Section 12.4's stdout intact.

### 12.7. Variation 2: Setting `primary`

If both `Store` beans are allowed as candidates, you can write:

```xml
<bean id="mainStore"
      class="demo.XmlAutowiringDemo$MainStore"
      primary="true"/>

<bean id="backupStore"
      class="demo.XmlAutowiringDemo$BackupStore"/>
```

For a single dependency by type, Spring selects `mainStore` as the unique primary candidate. However, for a `List<Store>` collection, both candidates are normally still included (`primary` does not filter `backup` out of the list).

### 12.8. Variation 3: `byName` Missing the Matching Name

Rename bean `backupStore` to `spareStore` while keeping `setBackupStore(Store)`. With no `backupStore` alias and no explicit property, `byName` finds no matching bean name, so the field stays `null`. By contrast, `byType` does not care about the name `spareStore` as long as type and candidate status match.

### 12.9. Variation 4: Explicit Wiring Still Works

Keep `autowire-candidate="false"` on backup, and declare `<property name="selected" ref="backupStore"/>` on another bean. That reference remains valid because the flag does not disable direct lookup by name.

### 12.10. Variation 5: Excluding `mainStore` as Well

Add `autowire-candidate="false"` to `mainStore` too. Now the `byType` setter `selected` is skipped, whereas `constructor` requiring `Store` causes context startup to fail when Spring instantiates the bean. This experiment highlights the difference in required semantics between `byType` setters and constructors.

## 13. Common Errors and How to Fix Them

| Error or symptom | Common cause | How to fix |
| --- | --- | --- |
| `byName` setter does not run | No bean name matches property name | Check setter and `id`/`alias`; use explicit `ref` if needed |
| `byType` sees two implementations | Multiple eligible candidates with no winner | `primary`, candidate filtering, qualifier/explicit `ref` |
| Constructor fails on missing dependency | Required constructor argument cannot be resolved | Register a matching bean or provide explicit `constructor-arg` |
| Excluded bean still injected by `byName` | `autowire-candidate="false"` only restricts type-based selection | Expected design behavior; control `byName` separately |
| Explicit `ref` still injects excluded bean | Explicit named references are not blocked by the flag | Valid behavior, not a bug |
| `value="3"` not auto-injected by `byType` | Simple scalar properties are excluded from XML autowiring | Use `<property value>`/`<constructor-arg value>` |
| `NotWritablePropertyException` | No matching JavaBean setter name/signature | Check property descriptor and setter visibility |
| `TypeMismatchException` | Bean/value incompatible with setter type | Check class/interface and converters |
| `NoUniqueBeanDefinitionException` | Resolver cannot pick a single candidate | Resolve ambiguity intentionally |
| `NoSuchBeanDefinitionException` | Dependency bean unregistered or filtered out | Check imports, profiles, conditions, XML resources |
| Autowiring does not populate a private field | XML setter mode differs from annotation field injection | Add a setter or use constructor injection |
| Same property both explicit and autowired | Explicit metadata takes precedence | Keep one authoritative configuration source |
| Collection misses an implementation | Bean excluded by `autowire-candidate`/patterns | Check candidate flags |
| Editing XML after refresh does not update bean | Autowiring runs during bean creation | Reload/rebuild or use a dedicated runtime config mechanism |
| Property type is raw `List` | Spring lacks element type information | Use `List<Interface>` or an explicit XML collection |
| `byName` depends on setter name, not field name | JavaBeans property naming rules | Inspect `setXxx` and introspection |
| Every bean unexpectedly autowired | Unmanaged `default-autowire` on root | Keep default `no` or narrow config scope |
| Bean with `autowire="no"` still injected into other beans | Does not stop it from being a candidate | To exclude from type selection, use `autowire-candidate="false"` |
| Primary bean still excluded | Excluded before primary preference applies | Do not rely on `primary` to override candidate exclusion |
| Spring AOP proxy and raw bean differ in identity | Container applies post-processors/proxying | Compare references per lifecycle/proxy policy |

### 13.1. Classifying Errors by Phase

Spring XML errors fall into three major phases:

1. **XML parse/XSD:** invalid `autowire` attribute, wrong namespace URI, unclosed tag, unresolvable XSD.
2. **Bean definition / candidate resolution:** zero candidates, multiple candidates, non-writable property, unresolvable constructor.
3. **Bean creation / business runtime:** constructor throws exception, setter logic fails, field is `null` because an optional autowire was skipped, business method hits missing dependency.

Do not see `BeanCreationException` and immediately conclude “Spring failed to read the XML.” It may have read the XML fine and then failed to resolve dependencies or instantiate the class afterward.

### 13.2. Debugging Technique

**Step 1:** Verify which `autowire-context.xml` file the application context actually loaded. Duplicate filenames on the classpath can mislead you.

**Step 2:** Inspect existing bean names and implementation types. `context.getBeanNamesForType(Store.class)` reveals beans by type, but note that **querying type names is not identical to autowire candidate selection**: an excluded bean still exists and appears in that list.

**Step 3:** Check property names derived from `setXxx` and parameter types. For `byName`, name is decisive; for `byType`, type and eligible candidates matter.

**Step 4:** Inspect `primary`, `autowire-candidate`, `default-autowire-candidates`, and explicit `<property ref>` declarations.

**Step 5:** For required dependencies, write an integration test asserting that the field/constructor dependency is non-null and has the expected implementation — rather than merely checking that context refresh didn't throw.

**Step 6:** Read the stack trace's root cause. Ambiguity, missing bean, missing setter, bad type conversion, and cycles are distinct root causes.

### 13.3. Custom Bean Name vs. Bean Type

An XML bean can be named `legacyJdbcStore` with a class implementing `Store`. Given `setStore`:

- `byName` looks for `store`, not `legacyJdbcStore`;
- `byType` can pick `legacyJdbcStore` if it is an eligible `Store` candidate.

Renaming a bean can break `byName` without affecting `byType`; changing an implementation type can break `byType` without breaking name matching (though it may then hit type compatibility). Weigh this trade-off when choosing modes.

## 14. Design Limitations and Practical Strategy

### 14.1. Less Boilerplate Comes with a Trade-off

Autowiring shortens XML, yet relationships between beans are no longer spelled out at the config site. Reviewers must inspect setter/constructor APIs and the entire registry's candidates to deduce actual wiring.

When a project later adds another bean implementing the same interface, a previously unique `byType` dependency can become ambiguous or switch implementations due to `primary`/candidate changes. In systems requiring high predictability, explicit configuration reduces surprises.

### 14.2. Do Not Mix Modes Arbitrarily

Having one module use explicit `ref`, another `byName`, and a third `byType` is valid in Spring, yet confusing without team conventions. Consider:

- Constructor injection for indispensable dependencies.
- Explicit XML references for collaborators with multiple implementations.
- `byType` for utility beans with a single candidate and tested boundaries.
- `byName` only when naming conventions are strictly stable.
- Explicit values/config properties for strings, numbers, and secrets.

These are guidelines, not rigid laws. Prioritize clarity and integration tests.

### 14.3. Type-Based Injection Is Not Security

`autowire-candidate="false"` filters dependency resolution; it does not prevent another bean from retrieving the object via `context.getBean("backupStore")`, nor does it prevent explicit `ref`. For sensitive objects, enforce access via module boundaries and APIs, not candidate flags.

### 14.4. Distinguish Startup from Runtime

Setter dependencies are injected when Spring creates the bean. Registering another `Store` bean after context refresh will not cause a singleton `ByTypeConsumer` to re-run its setter or switch candidates. For runtime routing, design an explicit abstraction, provider, or factory rather than treating XML autowiring as a dynamic router.

### 14.5. Do Not Use XML Autowiring to Solve Circular Dependencies

Setter cycles can sometimes be handled by Spring in singleton setups, yet carry lifecycle, proxy, and partially-initialized-state risks. Constructor cycles generally cannot be solved by autowiring. Refactor the dependency graph to be clearly directed, use events, or split service responsibilities.

### 14.6. Do Not Assume Identical Candidate Selection Across Spring Versions

Spring refines multi-candidate resolution across releases (e.g., Spring 6.2 handles additional qualifier/name/priority cases). Check the **actual framework version** in use rather than relying on an old Spring 2.x blog post. This lesson targets Spring Framework 6.2.19; specific behaviors should always be covered by integration tests in your project.

## 15. Intentional Testing of XML Autowiring

### 15.1. Happy-Path Identity Tests

For the Section 12 demo, you can add assertions:

```java
if (byName.getBackupStore() != backup) {
    throw new AssertionError("byName did not select backup");
}

if (byType.getSelected() != main) {
    throw new AssertionError("byType did not select main");
}

if (explicit.getSelected() != backup) {
    throw new AssertionError("Explicit ref was not honored");
}

if (fleet.getStores().size() != 1) {
    throw new AssertionError("Expected one eligible Store");
}
```

This is a **test snippet** using variables already declared in `XmlAutowiringDemo.main`. Such assertions guard assumptions about type, name, and candidate status when XML is edited.

### 15.2. Negative Test for Ambiguity

Use a separate XML fixture containing two eligible `Store` beans and a `ByTypeConsumer`. Running:

```java
try (var context = new ClassPathXmlApplicationContext(
        "ambiguous-context.xml")) {
    throw new AssertionError("Expected ambiguity");
} catch (org.springframework.beans.BeansException expected) {
    System.out.println("Ambiguous configuration rejected");
}
```

This is a **test snippet**, not part of the demo's `main`; it requires a separate `ambiguous-context.xml` resource. In serious tests, inspect the exception type and root cause so you do not mistake an XML parse error for ambiguity. Never catch any generic exception and blindly mark the test passed.

### 15.3. Missing Dependency Test

For a `byType` setter without a `Store`, tests should verify the getter remains `null` per contract; for a required constructor dependency, tests should expect failure. Verifying the contrast between the two modes is the key point.

### 15.4. Testing Candidate Exclusion

With `backupStore` excluded:
- `context.containsBean("backupStore")` must be `true`.
- `context.getBean("backupStore", Store.class)` must still succeed.
- `byName` property `backupStore` receives that object.
- `byType` dependency `Store` receives `main`.
- Explicit `ref` to `backup` still works.

When all five assertions pass, you have properly tested the distinction between **existing in the registry** and **being eligible for type-based autowiring**.

## 16. Exercises with Solutions

### Exercise 1 — What Name Does `byName` Use?

A class has field `primaryRepository` and setter `setRepository(Repository)`. XML enables `autowire="byName"`. Which bean name does Spring look up?

**Answer:** `repository`, based on the writable JavaBean property name. The field name does not directly drive `byName`.

### Exercise 2 — Does `byType` Require the Bean Name to Match the Setter?

Setter `setStore(Store)`, and the registry has a bean named `jdbcMain` implementing `Store`. Can XML `autowire="byType"` inject it?

**Answer:** Yes, if it is the sole/eligible matching candidate. `jdbcMain` does not need to match `store`.

### Exercise 3 — `byName` Without a Matching Bean Name

Setter `setNotifier(Notifier)`, and XML only has a bean named `smsNotifier`. With `byName`, is the setter guaranteed to be called?

**Answer:** No. Without a bean named `notifier`, `byName` skips the property; use an alias, explicit `ref`, or switch modes where appropriate.

### Exercise 4 — `byType` with Two Candidates

There are two eligible `PaymentGateway` beans and no clear tie-breaker. What happens?

**Answer:** Ambiguous dependency; Spring throws an exception during bean creation rather than picking one arbitrarily by XML order.

### Exercise 5 — `primary`

Two `Store` candidates exist, and one has `primary="true"`. For a single `Store` dependency, which bean can Spring select?

**Answer:** The primary bean if it is eligible among the candidates; `primary` does not remove the other bean from the registry.

### Exercise 6 — `autowire-candidate="false"`

Bean `backupStore` has `autowire-candidate="false"`. Can a `byName` property named `backupStore` still receive it?

**Answer:** Yes. This flag restricts type-based autowiring, not `byName` matching.

### Exercise 7 — Explicit `ref` to an Excluded Bean

`backupStore` is excluded from type-based autowiring. Is `<property name="store" ref="backupStore"/>` still valid?

**Answer:** Yes. Explicit references by name are not disabled by the candidate flag.

### Exercise 8 — Simple Properties

Bean `Settings` has `setTimeout(int)`. Root XML sets `default-autowire="byType"`. Does `timeout` automatically receive `3000`?

**Answer:** No. Simple properties are never guessed. Provide explicit `<property name="timeout" value="3000"/>` or an explicit configuration mechanism.

### Exercise 9 — Missing Constructor Dependency

`CheckoutService(Store store)` has a single constructor, XML uses `autowire="constructor"`, and no `Store` bean exists. Will the context create the service with `store` set to `null`?

**Answer:** No. An unresolved required constructor dependency normally causes bean creation to fail.

### Exercise 10 — Explicit Property and Autowiring

Bean `service` has both `autowire="byType"` and `<property name="gateway" ref="backupGateway"/>`. When Spring creates the bean, will it replace `backupGateway` with another primary `Gateway`?

**Answer:** No. An explicit property setting overrides autowiring for that property.

### Exercise 11 — `List<Handler>`

Three eligible `Handler` beans exist. The injection point is `List<Handler>` via `byType`. Does Spring pick only one `@Primary` bean?

**Answer:** No. The collection receives all three eligible handlers; `primary` does not filter collections.

### Exercise 12 — `Map<String,Handler>`

Why does Spring use `String` keys in an autowired map?

**Answer:** Keys represent **bean names**, and values are the handler bean references. Clear generic types are needed so the resolver knows the element type.

### Exercise 13 — Does `autowire-candidate="false"` Delete the Bean?

You call `context.getBean("backupStore")` on the excluded backup bean. Is `NoSuchBeanDefinitionException` guaranteed?

**Answer:** No. The bean definition still exists; the flag is not a bean-deletion mechanism or security control.

### Exercise 14 — `default-autowire-candidates`

Does root `<beans default-autowire-candidates="*Repository">` mean only beans ending with `Repository` are registered in the context?

**Answer:** No. It restricts **candidate selection** by pattern for type-based autowiring; it does not prevent other beans from being registered.

### Exercise 15 — Annotations and XML

A bean has `autowire="no"`, yet its class uses `@Autowired` and annotation processing infrastructure is enabled. Can it still receive annotation injection?

**Answer:** Yes. `autowire="no"` disables XML autowire mode; it does not disable annotation `BeanPostProcessor`s.

### Exercise 16 — When Beans Are Wired

You edit the XML file while the application has already refreshed its context and holds singleton `service`. Does `setStore` automatically run again?

**Answer:** No. Autowiring normally runs during bean creation/population; reloading requires a dedicated mechanism.

### Exercise 17 — Prototype Scope

A singleton `Service` receives a prototype `Store` in its setter when created. Does each call to `service.find()` automatically receive a fresh `Store`?

**Answer:** No. The service keeps the injected reference; obtaining a new instance per call requires an appropriate provider or factory.

### Exercise 18 — Why Prefer Constructor Injection?

A `Service` cannot function without `Repository`, yet a `byType` setter can leave `repository` `null` if candidates are missing. How can this be improved?

**Answer:** Declare the dependency in a required constructor, or use an explicit XML reference with tests/init validation. Ensure the “repository required” contract is enforced before the service is used.

## 17. Checklist for Real-World Projects

- Is the bean using the intended `autowire` mode?
- For `byName`, have you verified the JavaBeans property name and exact bean `id`/`alias`?
- For `byType`, have you verified candidate counts, types, `primary`, and candidate flags?
- For `constructor`, have you checked constructor signatures, scalar arguments, and overloads?
- Do simple `String`/`int`/`boolean` properties have explicit values?
- Do critical dependencies needing a specific implementation use explicit `ref`/`constructor-arg`?
- Is any bean with `autowire-candidate="false"` intentionally retrieved via `byName` or explicit `ref`?
- Have you avoided confusing `default-autowire` with `default-autowire-candidates`?
- For collection injection, are generic element types and the eligible bean set accurate?
- Could adding a new bean make an existing `byType` dependency ambiguous?
- Could a missing required setter dependency leave a field `null` until late runtime?
- Do context tests assert bean identity, implementation types, and actual behavior?
- If XML includes `<context:annotation-config/>`, do you distinguish annotation injection from XML autowiring?
- Could scopes, proxies, lazy init, or circular references alter dependency resolution timing?
- When debugging, did you inspect the root cause instead of lumping every exception under “bad XML”?

## 18. Conclusion

**XML autowiring** lets the BeanFactory resolve collaborators from the bean registry instead of requiring every `<property ref="..."/>` to be written explicitly. `byName` matches **JavaBean property names to bean names**. `byType` matches **property types to autowire-eligible candidate beans**. `constructor` resolves **constructor arguments via type-based dependency resolution**. `no` is the default and never prohibits explicit DI.

Key limitations: **simple properties are never guessed**; a missing `byType` setter candidate leaves the property unset; multiple eligible beans for a single dependency cause ambiguity; and implicit wiring makes the dependency graph harder to read. Spring provides `primary`, `autowire-candidate`, and `default-autowire-candidates` to refine selection, while **explicit `ref` always pinpoints an exact dependency**.

One rule worth remembering: **`autowire-candidate="false"` does not delete the bean, does not block `byName`, and does not block explicit `ref`**; it primarily excludes the bean from type-based autowiring. This lesson's demo verifies all three resolution paths side by side.

In new code, constructor injection for required dependencies and explicit configuration for key business choices generally yield better maintainability. When maintaining Spring XML systems, understanding each autowire mode precisely prevents bugs that surface only when another bean of the same interface is added, a bean is renamed, or candidate-selection rules change.

### Official Documentation

- [Spring Framework 6.2 — Autowiring Collaborators](https://docs.spring.io/spring-framework/reference/6.2/core/beans/dependencies/factory-autowire.html).
- [Spring Framework 6.2 — Dependency Injection](https://docs.spring.io/spring-framework/reference/6.2/core/beans/dependencies/factory-collaborators.html).
- [Spring Framework 6.2 — Using `@Autowired`](https://docs.spring.io/spring-framework/reference/6.2/core/beans/annotation-config/autowired.html).
- [Spring Framework 6.2 — Spring Bean Scopes](https://docs.spring.io/spring-framework/reference/6.2/core/beans/factory-scopes.html).
- [Spring Framework 6.2 — Fine-tuning Annotation-based Autowiring with Qualifiers](https://docs.spring.io/spring-framework/reference/6.2/core/beans/annotation-config/autowired-qualifiers.html).
