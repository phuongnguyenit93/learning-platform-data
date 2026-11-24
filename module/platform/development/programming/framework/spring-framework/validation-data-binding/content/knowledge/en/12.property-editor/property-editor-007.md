# PropertyEditorRegistrar and Reusing Registration Rules in Spring

When Spring needs to convert an incoming string into a custom Java type, you can create a `java.beans.PropertyEditor` and register it on a `BeanWrapper` or `DataBinder`. However, if an application has many beans, controllers, or binding entry points, repeating `registerCustomEditor(...)` calls creates duplicate code and risks inconsistent configuration.

**`org.springframework.beans.PropertyEditorRegistrar`** solves that problem by packaging **editor registration rules** into a reusable object. Whenever given a `PropertyEditorRegistry`, the registrar registers the needed editors on that registry.

Two key ideas:

1. **Reuse one registrar** to apply the same rule set in multiple places.
2. **Never share the same `PropertyEditor` instance** across multiple binders/threads: the registrar must create **new editors on each registration** because PropertyEditors are typically stateful and not thread-safe.

This lesson focuses on designing a registrar, why it is needed, a runnable Java 17+ example working with `BeanWrapper` and `DataBinder`, integration with Spring MVC/IoC containers, and practical mistakes to avoid.

## 1. Putting PropertyEditorRegistrar in Context

Suppose a domain model has a custom type:

~~~java
public record OrderCode(String value) {}
~~~

Clients submit `"ab-123"` while the object needs `OrderCode("AB-123")`. A `PropertyEditor` can convert it:

~~~text
"ab-123" (String)
      |
      v
OrderCodeEditor.setAsText(...)
      |
      v
OrderCode("AB-123")
      |
      v
OrderForm.setOrderCode(...)
~~~

With two separate binding coordinators, duplicated code quickly appears:

~~~java
// In a BeanWrapper:
wrapper.registerCustomEditor(OrderCode.class, new OrderCodeEditor());

// In another DataBinder:
binder.registerCustomEditor(OrderCode.class, new OrderCodeEditor());
~~~

The lines above are **excerpts**, not a complete program. Each call site must know the exact editor type and configuration. When adding another editor, multiple places must be updated.

Instead, define **one registrar**:

~~~java
public final class OrderCodeRegistrar implements PropertyEditorRegistrar {
    @Override
    public void registerCustomEditors(PropertyEditorRegistry registry) {
        registry.registerCustomEditor(
                OrderCode.class, new OrderCodeEditor());
    }
}
~~~

This is an illustrative class; you need to import the two Spring interfaces and provide `OrderCode` and `OrderCodeEditor`. Usage:

~~~java
PropertyEditorRegistrar registrar = new OrderCodeRegistrar();

registrar.registerCustomEditors(wrapper);
registrar.registerCustomEditors(binder);
~~~

**Same registrar**, yet `new OrderCodeEditor()` runs separately for `wrapper` and `binder`. As a result, they get distinct editors while **registration rules** live in a single place.

## 2. Distinguishing Related Interfaces and Components

| Component | Package / type | Role |
| --- | --- | --- |
| `PropertyEditor` | `java.beans.PropertyEditor`, interface | JavaBeans contract converting text <-> value; editor holds state via `getValue()/setValue()` |
| `PropertyEditorSupport` | `java.beans.PropertyEditorSupport`, class | Convenience base class for writing a custom PropertyEditor |
| `PropertyEditorRegistry` | `org.springframework.beans.PropertyEditorRegistry`, interface | Target where custom editors are registered by type or property path |
| `PropertyEditorRegistrar` | `org.springframework.beans.PropertyEditorRegistrar`, interface | Strategy that **registers a set of editors** on any given registry |
| `BeanWrapper` | `org.springframework.beans.BeanWrapper`, interface | Reads/writes JavaBean properties and performs conversion |
| `DataBinder` | `org.springframework.validation.DataBinder`, class | Accepts `PropertyValues`, binds onto target, manages binding errors and validation |
| `WebDataBinder` | `org.springframework.web.bind.WebDataBinder` | Binder suited for web contexts |
| `CustomEditorConfigurer` | `org.springframework.beans.factory.config.CustomEditorConfigurer` | `BeanFactoryPostProcessor` configuring custom editors/registrars for the **bean factory** |

Both `BeanWrapper` and `DataBinder` act as `PropertyEditorRegistry`. Therefore, a registrar **does not need to know** whether the recipient is a web binder, a JavaBean wrapper, or a manually created binder; it works purely against the common registration API.

### Exact signature

~~~java
package org.springframework.beans;

public interface PropertyEditorRegistrar {
    void registerCustomEditors(PropertyEditorRegistry registry);
}
~~~

The block above is a **simplified illustration of the API contract**, not a file to define yourself in your project. In Spring 6.2.x or newer, the interface also provides default APIs for handling default editors; the core method for applications to implement remains `registerCustomEditors(...)`.

The method receives a registry **from outside** and returns `void`. It does not return a list of editors and does not run automatically just because a class implements the interface. A caller—such as `@InitBinder` or `CustomEditorConfigurer`—is responsible for triggering registration.

## 3. Why Must a Fresh Editor Be Created on Each Registration?

`PropertyEditorSupport` holds the **current value** internally. For instance, an editor might do:

~~~java
@Override
public void setAsText(String text) {
    setValue(new OrderCode(text));
}
~~~

This is a **method excerpt**, requiring the surrounding editor class and domain type. When a binder converts multiple fields, objects, or requests, the editor is invoked and mutates its state. One instance used concurrently across threads can mix up data.

**Wrong approach — storing a pre-created editor inside a singleton registrar:**

~~~java
// ANTI-PATTERN ILLUSTRATION, DO NOT USE.
public final class UnsafeRegistrar implements PropertyEditorRegistrar {
    private final OrderCodeEditor editor = new OrderCodeEditor();

    @Override
    public void registerCustomEditors(PropertyEditorRegistry registry) {
        registry.registerCustomEditor(OrderCode.class, editor);
    }
}
~~~

When this registrar is reused, registries end up holding **the same mutable `editor`**. This breaks state isolation and creates concurrency hazards.

**Right approach — instantiating the editor inside the registrar call:**

~~~java
public final class SafeRegistrar implements PropertyEditorRegistrar {
    @Override
    public void registerCustomEditors(PropertyEditorRegistry registry) {
        registry.registerCustomEditor(
                OrderCode.class,
                new OrderCodeEditor());
    }
}
~~~

The two snippets are solely for comparison, omitting imports and dependent classes. **A registrar can be a stateless singleton**, because it holds no editor state itself; each `registerCustomEditors` invocation creates an independent editor for that registry.

If editors need unchanging settings, the registrar may hold **immutable configuration** (such as format patterns or time zone IDs) and pass them into each new editor's constructor. Avoid sharing non-thread-safe objects like `SimpleDateFormat` across editors. For newer types like `java.time.LocalDate`, consider a `Formatter` or `Converter` instead of a stateful custom PropertyEditor whenever possible.

### Do not misunderstand the scope of "new"

"A new editor per registrar call" does not mean Spring creates a new editor **for every character** or **every field assignment**. The right unit to think of is **per configured registry/binder**; a registered editor may be reused sequentially within that single registry's scope.

Do not rely on Spring cloning an old editor into a new one: creating new instances is the responsibility of the registrar code.

## 4. Java 17+ Example: One Registrar Reused for BeanWrapper and DataBinder

This example runs **without an HTTP server and without Spring Boot**:

- Source data contains order codes `" ab-123 "` or `" cd-456 "`.
- The JavaBean expects a property of type `OrderCode`, not `String`.
- `OrderCodeEditor` performs trim/uppercase normalization and validates the `AA-999` format.
- `OrderCodeRegistrar` registers the editor on any `PropertyEditorRegistry`.
- One registrar instance is used for both `BeanWrapperImpl` and `DataBinder`.
- An invalid code test demonstrates conversion errors recorded in `BindingResult` when using `DataBinder`.

### 4.1. Create the Maven project

Use **JDK 17+**, Maven, and a consistent Spring Framework version. The `pom.xml` below pins `spring-context:6.2.19` for the example (for reproducibility, not claiming it is the latest release). Module `spring-context` provides `DataBinder` and transitively depends on `spring-beans`.

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>example</groupId>
    <artifactId>property-editor-registrar-demo</artifactId>
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
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.1</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

If a real application uses Spring Boot, let the **Spring Boot BOM/parent** manage all Spring modules at matching versions instead of pinning `spring-context` to a version different from Boot's managed line.

### 4.2. Complete source code

Create **`src/main/java/example/PropertyEditorRegistrarDemo.java`**:

~~~java
package example;

import java.beans.PropertyEditorSupport;
import java.util.Locale;

import org.springframework.beans.BeanWrapper;
import org.springframework.beans.BeanWrapperImpl;
import org.springframework.beans.MutablePropertyValues;
import org.springframework.beans.PropertyEditorRegistrar;
import org.springframework.beans.PropertyEditorRegistry;
import org.springframework.validation.BindingResult;
import org.springframework.validation.DataBinder;

public class PropertyEditorRegistrarDemo {

    // Domain value type: canonical code, distinct from raw request string.
    public record OrderCode(String value) {
    }

    // Stateful PropertyEditor (inherits getValue/setValue).
    public static final class OrderCodeEditor extends PropertyEditorSupport {

        @Override
        public void setAsText(String text) throws IllegalArgumentException {
            if (text == null || text.isBlank()) {
                setValue(null);
                return;
            }

            String normalized = text.trim().toUpperCase(Locale.ROOT);

            if (!normalized.matches("[A-Z]{2}-[0-9]{3}")) {
                throw new IllegalArgumentException(
                        "Order code must match AA-999");
            }

            setValue(new OrderCode(normalized));
        }

        @Override
        public String getAsText() {
            OrderCode value = (OrderCode) getValue();
            return value == null ? "" : value.value();
        }
    }

    // The registrar can be shared across registries.
    // However, a new editor is created for each registerCustomEditors call.
    public static final class OrderCodeRegistrar
            implements PropertyEditorRegistrar {

        @Override
        public void registerCustomEditors(PropertyEditorRegistry registry) {
            registry.registerCustomEditor(
                    OrderCode.class, new OrderCodeEditor());
        }
    }

    // Target JavaBean: property binding uses getters/setters.
    public static final class OrderForm {
        private OrderCode orderCode;
        private String note;

        public OrderCode getOrderCode() {
            return orderCode;
        }

        public void setOrderCode(OrderCode orderCode) {
            this.orderCode = orderCode;
        }

        public String getNote() {
            return note;
        }

        public void setNote(String note) {
            this.note = note;
        }
    }

    public static void main(String[] args) {

        // This is the same registrar, not the same editor.
        PropertyEditorRegistrar registrar = new OrderCodeRegistrar();

        OrderForm viaWrapper = new OrderForm();
        BeanWrapper wrapper = new BeanWrapperImpl(viaWrapper);
        registrar.registerCustomEditors(wrapper);

        wrapper.setPropertyValue("orderCode", " ab-123 ");
        wrapper.setPropertyValue("note", "Created through BeanWrapper");

        System.out.println(
                "beanWrapper.code=" + viaWrapper.getOrderCode().value());
        System.out.println(
                "beanWrapper.note=" + viaWrapper.getNote());

        OrderForm viaBinder = new OrderForm();
        DataBinder binder = new DataBinder(viaBinder, "orderForm");
        binder.setAllowedFields("orderCode", "note");
        registrar.registerCustomEditors(binder);

        MutablePropertyValues input = new MutablePropertyValues()
                .add("orderCode", " cd-456 ")
                .add("note", "Created through DataBinder");

        binder.bind(input);

        System.out.println(
                "dataBinder.code=" + viaBinder.getOrderCode().value());
        System.out.println(
                "dataBinder.note=" + viaBinder.getNote());
        System.out.println(
                "dataBinder.errors=" + binder.getBindingResult().getErrorCount());

        OrderForm invalid = new OrderForm();
        DataBinder invalidBinder = new DataBinder(invalid, "orderForm");
        invalidBinder.setAllowedFields("orderCode");
        registrar.registerCustomEditors(invalidBinder);

        invalidBinder.bind(
                new MutablePropertyValues().add("orderCode", "invalid"));

        BindingResult errors = invalidBinder.getBindingResult();
        System.out.println(
                "badBinder.hasErrors=" + errors.hasErrors());
        System.out.println(
                "badBinder.field=" + errors.getFieldError("orderCode").getField());
    }
}
~~~

**Key characteristics of the code:**

- `OrderCode` is a Java 17 record with accessor `value()`.
- `OrderForm` is a JavaBean with a default constructor and getters/setters so `BeanWrapper`/`DataBinder` can bind properties.
- The editor **does not mutate raw strings**, instead creating a new domain value `OrderCode(normalized)`.
- `PropertyEditorSupport` holds the value state and provides `setValue()/getValue()`; `getAsText()` converts the current value back to a string for display.
- `registerCustomEditors(...)` instantiates `new OrderCodeEditor()` **every time it is invoked**.
- The same registrar is used for the wrapper, the valid binder, and the binder handling invalid data.
- With `DataBinder`, the exception from `setAsText` on malformed input becomes a type conversion error in `BindingResult`; this is not a Jakarta Bean Validation error.

### 4.3. Run command and output

Directory structure:

~~~text
property-editor-registrar-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── example/
                └── PropertyEditorRegistrarDemo.java
~~~

From the directory containing `pom.xml`:

~~~bash
java -version
mvn -version
mvn -q compile exec:java -Dexec.mainClass=example.PropertyEditorRegistrarDemo
~~~

With JDK 17+ and Maven able to download dependencies, **the output printed by the program** is:

~~~text
beanWrapper.code=AB-123
beanWrapper.note=Created through BeanWrapper
dataBinder.code=CD-456
dataBinder.note=Created through DataBinder
dataBinder.errors=0
badBinder.hasErrors=true
badBinder.field=orderCode
~~~

Maven may print different logs depending on the environment. The lines above are determined by the `System.out.println` statements in the example. Plain `javac` alone is insufficient because Spring is not part of the JDK; Maven manages the classpath and compilation.

### 4.4. Result analysis

**With BeanWrapper:**

`wrapper.setPropertyValue("orderCode", " ab-123 ")` finds property `orderCode` of type `OrderCode`, uses the registered editor, invokes `setAsText`, and assigns `OrderCode("AB-123")` to the form. Because only `OrderCode` has a custom editor, the `String` property `note` binds normally.

**With DataBinder:**

`binder.bind(input)` reads both pairs from `MutablePropertyValues`, enforces allowed fields, converts `" cd-456 "` into `OrderCode("CD-456")`, and calls the setter. `dataBinder.errors=0` because the data is valid. In the example, `binder.setAllowedFields(...)` illustrates controlled assignment — the registrar **is not responsible** for security.

**With invalid data:**

`"invalid"` does not match pattern `AA-999`. The editor throws `IllegalArgumentException`; `DataBinder` catches it and stores binding error details for field `orderCode`. Thus `badBinder.hasErrors=true` and `badBinder.field=orderCode`. Exact message details can depend on configuration, so the example does not assert a fixed internal message string.

**Most important takeaway:** `PropertyEditorRegistrar` **does not perform binding or validation itself**. It only **installs conversion rules** on the right registry before binding executes.

## 5. Registering Multiple Editors and Controlling Scope

A registrar can register **multiple** editors:

~~~java
@Override
public void registerCustomEditors(PropertyEditorRegistry registry) {
    registry.registerCustomEditor(
            OrderCode.class, new OrderCodeEditor());

    registry.registerCustomEditor(
            Locale.class, new CustomLocaleEditor());
}
~~~

This is an **excerpt**; add imports for `java.util.Locale` and `org.springframework.beans.propertyeditors.CustomLocaleEditor`. Registering an editor for `Locale.class` applies that editor to `Locale` properties in that registry, as appropriate.

The `PropertyEditorRegistry` interface has two primary overloads:

~~~java
void registerCustomEditor(
        Class<?> requiredType, PropertyEditor propertyEditor);

void registerCustomEditor(
        Class<?> requiredType, String propertyPath,
        PropertyEditor propertyEditor);
~~~

These are **API description signatures**, not methods to redeclare. The `propertyPath` parameter can restrict the editor to a specific property. For example:

~~~java
registry.registerCustomEditor(
        OrderCode.class, "billing.orderCode",
        new OrderCodeEditor());
~~~

This is an **excerpt**, assuming the model has a nested property `billing.orderCode`. An editor by type `OrderCode.class` applies to properties matching that type; an editor by property path targets the designated field. Spring's precedence rules consider both type and path during lookup; test thoroughly if registering overlapping editors.

**Why distinguish these two registration forms?**

- By **type**: suitable when every `OrderCode` within the binder's scope shares the same parse/format rule.
- By **property path**: suitable when one specific field needs a different format, such as a legacy field with special rules.
- Never register one editor for a collection and another for its elements on **the same path** without carefully checking `PropertyEditorRegistry` rules; doing so can create confusing editor selection behavior.

When business contexts require different rules, do not force everything into one overly broad registrar. Design separate registrars for distinct domain groups, or let a registrar accept immutable configuration.

## 6. Reusing in Spring MVC with @InitBinder

In Spring MVC, a `@Controller` or `@ControllerAdvice` can declare `@InitBinder` to configure `WebDataBinder` before binding request data into a model attribute.

Integration concept:

~~~java
@Controller
public class OrderController {

    private final PropertyEditorRegistrar registrar;

    public OrderController(PropertyEditorRegistrar registrar) {
        this.registrar = registrar;
    }

    @InitBinder("orderForm")
    void initBinder(WebDataBinder binder) {
        registrar.registerCustomEditors(binder);
        binder.setAllowedFields("orderCode", "note");
    }

    @PostMapping("/orders")
    String submit(
            @ModelAttribute("orderForm") OrderForm form,
            BindingResult errors) {

        if (errors.hasErrors()) {
            return "order-form";
        }
        return "order-success";
    }
}
~~~

**This is an integration excerpt**, not a standalone program: you must import MVC annotations, `WebDataBinder`, `BindingResult`, define a `PropertyEditorRegistrar` bean, and keep `OrderForm` accessible. `"order-form"` and `"order-success"` are view names, requiring view templates or switching to a body-returning controller depending on the application.

Creating the registrar bean:

~~~java
@Configuration
class EditorRegistrationConfig {

    @Bean
    PropertyEditorRegistrar orderCodeRegistrar() {
        return new PropertyEditorRegistrarDemo.OrderCodeRegistrar();
    }
}
~~~

This is a **configuration excerpt**, requiring imports for `@Configuration`, `@Bean`, `PropertyEditorRegistrar`, and having the example class from section 4 in the same package or imported. In real applications, `OrderCodeRegistrar` and domain/editor classes are usually separated into their own top-level classes for reuse across modules.

Each incoming request can create a fresh `WebDataBinder`. When `@InitBinder` calls the registrar, it creates a new editor for that binder. The registrar can be a **singleton Spring bean** shared across multiple controllers without sharing mutable editor state.

### Using @ControllerAdvice to apply across multiple controllers

If multiple controllers all use `OrderCode`, shared registration rules can live in an advice:

~~~java
@ControllerAdvice
public class SharedEditorAdvice {

    private final PropertyEditorRegistrar registrar;

    public SharedEditorAdvice(PropertyEditorRegistrar registrar) {
        this.registrar = registrar;
    }

    @InitBinder
    void configure(WebDataBinder binder) {
        registrar.registerCustomEditors(binder);
    }
}
~~~

This is also an **integration excerpt**, requiring a registrar bean and Spring MVC imports. `@ControllerAdvice` shares binder configuration across controllers within the advice's scope. As needed, restrict the advice by base package, annotation, or assignable type, or restrict `@InitBinder("orderForm")` by model attribute name. Avoid accidentally registering broad editors for controllers that do not want them.

**Note:** registering on controller `@InitBinder` does not make the bean factory use those editors when instantiating configuration beans; these are **two different mechanisms and two different scopes**.

## 7. Reusing in the IoC Container with CustomEditorConfigurer

Another use case is letting the **Spring bean factory** use custom editors when converting string configuration values into domain types during bean creation/configuration. Spring provides `CustomEditorConfigurer`, a `BeanFactoryPostProcessor`, to register registrars with the bean factory.

### Illustrative XML configuration

~~~xml
<bean id="orderCodeRegistrar"
      class="example.OrderCodeRegistrar"/>

<bean class="org.springframework.beans.factory.config.CustomEditorConfigurer">
    <property name="propertyEditorRegistrars">
        <list>
            <ref bean="orderCodeRegistrar"/>
        </list>
    </property>
</bean>
~~~

This is a **Spring configuration XML fragment**, not a standalone file; `example.OrderCodeRegistrar` assumes you extracted the registrar into a public **top-level class** in package `example`. When keeping the nested class from `PropertyEditorRegistrarDemo.OrderCodeRegistrar`, the binary Java class name differs and the XML must be adjusted; the simplest option is moving it into `OrderCodeRegistrar.java`.

The configurer registers the **registrar strategy** so the bean factory can create editors during bean instantiation as needed. It does not share a single editor instance across all beans.

### Java-based configuration

When using `@Configuration`, you can define `CustomEditorConfigurer` as a bean post-processor:

~~~java
@Configuration
public class BeanFactoryEditorConfiguration {

    @Bean
    static CustomEditorConfigurer customEditorConfigurer() {
        CustomEditorConfigurer configurer = new CustomEditorConfigurer();
        configurer.setPropertyEditorRegistrars(
                new PropertyEditorRegistrar[]{
                        new OrderCodeRegistrar()
                });
        return configurer;
    }
}
~~~

This is a **configuration excerpt**, assuming a top-level `OrderCodeRegistrar` class and full Spring imports. Declaring `BeanFactoryPostProcessor` beans as `@Bean static` is commonly recommended to avoid premature initialization of the enclosing `@Configuration` class. Crucially, `setPropertyEditorRegistrars(...)` takes an **array of registrars**, not an array of `PropertyEditor`s.

**Differences in scope:**

| Registration method | Configured registry | Purpose |
| --- | --- | --- |
| `registrar.registerCustomEditors(wrapper)` | A manually created `BeanWrapper` | Reading/writing properties in direct Java code |
| `registrar.registerCustomEditors(binder)` | A `DataBinder` | Binding one target, obtaining `BindingResult` |
| `@InitBinder` in a controller | Request-scoped `WebDataBinder` | Converting form/model attribute inputs |
| `@ControllerAdvice + @InitBinder` | Binders of controllers matching the advice | Sharing rules across multiple controllers |
| `CustomEditorConfigurer` | Bean factory / IoC container | Converting properties during bean creation/config |

**Do not assume** configuring `CustomEditorConfigurer` alone automatically equips every MVC `WebDataBinder` with form editors. For custom request binding, configure the appropriate binder/web binding initializer/advice and test the real endpoint.

### Is CustomEditorConfigurer mandatory?

No. If an application only has a few controllers accepting forms, `@InitBinder` or `@ControllerAdvice` is usually clearer. `CustomEditorConfigurer` is useful when the **bean factory itself** needs the same conversion rules to populate bean properties inside the container.

In modern Spring Boot, many use cases benefit from `Converter`/`Formatter` via `ConversionService` rather than container-level PropertyEditor configuration; which choice fits best depends on data types, legacy compatibility requirements, and conversion scope.

## 8. How PropertyEditorRegistrar Differs from Converter and Formatter

All of these can relate to type conversion, yet their designs differ:

| Tool | Model | Best suited when |
| --- | --- | --- |
| `PropertyEditor` | Mutable JavaBeans editor holding value state | Integrating legacy APIs, editing fields/beans via PropertyEditor mechanics |
| `PropertyEditorRegistrar` | **Registration configuration** of multiple PropertyEditors for a registry | Existing PropertyEditors need reuse across multiple binders/BeanWrappers/containers |
| `Converter<S,T>` | Conversion function from type `S` to `T` | Compact conversion rules registrable in `ConversionService` |
| `Formatter<T>` | Locale-aware text parse/print | Form display values such as dates, currencies, or locale-sensitive numbers |
| `ConversionService` | Registry executing converters/formatters | Shared conversion configuration across layers in modern style |

With `Converter<String, OrderCode>`, you can write:

~~~java
public final class StringToOrderCodeConverter
        implements Converter<String, OrderCode> {

    @Override
    public OrderCode convert(String source) {
        String normalized = source.trim().toUpperCase(Locale.ROOT);
        if (!normalized.matches("[A-Z]{2}-[0-9]{3}")) {
            throw new IllegalArgumentException("Invalid order code");
        }
        return new OrderCode(normalized);
    }
}
~~~

This is an **excerpt**, requiring imports for `org.springframework.core.convert.converter.Converter`, `java.util.Locale`, and `OrderCode`. It is **not** code you can paste straight into `PropertyEditorRegistrarDemo.java` without adjusting classes/imports.

`Converter` has no `getValue()/setValue()` state like `PropertyEditorSupport`; with stateless converters, singleton sharing is much easier to manage safely. For greenfield Spring applications, consider `Converter`/`Formatter` first; when integrating an existing suite of `PropertyEditor`s, `PropertyEditorRegistrar` is the right packaging mechanism.

**Do not confuse them:** a registrar is not a `ConverterFactory`, does not automatically register converters into `ConversionService`, and does not perform validation.

## 9. Distinguishing Conversion, Binding, Validation, and Authorization

A request might send:

~~~text
orderCode=ab-123
note=Ship today
isAdmin=true
~~~

Processing should be separated into four questions:

1. **Conversion:** does `"ab-123"` convert to `OrderCode("AB-123")`? — `OrderCodeEditor` handles this.
2. **Binding:** which request fields get written onto the JavaBean? — `DataBinder`/`WebDataBinder` and property binding rules decide this.
3. **Validation:** does the order code exist, is it orderable, and is it business-valid? — `Validator`/Jakarta Validation/services handle this.
4. **Authorization:** does the caller have permission to act on that object/field? — security/service checks handle this.

**A successful registrar does not guarantee the other three succeed.**

In the Java example, `setAllowedFields("orderCode", "note")` limits property binding to two fields. `isAdmin` is disallowed if a client tries sending it. When fields are blocked, inspect `BindingResult#getSuppressedFields()` if policy requires logging or rejecting the request. Do not look only at `hasErrors()`, because suppressed fields do not necessarily generate binding errors automatically.

Use dedicated request DTOs to prevent **mass assignment** on entities with sensitive setters. With untrusted data, never rely solely on an editor validating string syntax.

### Do not sanitize sensitive data with overly broad rules

The editor in this article is solely for `OrderCode`, and its trim/uppercase behavior is an intentional domain contract. Never apply the same editor arbitrarily to all `String`s: passwords, signatures, tokens, or free-form text can be case- and whitespace-sensitive. Registering by specific **domain type** or **property path** keeps impact bounded.

## 10. Common Errors and How to Fix Them

### Error 1: registrar instantiates an editor once and shares it

**Wrong:** a `private final OrderCodeEditor editor` field on a singleton registrar registered into every binder.

**Right:** create `new OrderCodeEditor()` **inside** `registerCustomEditors(...)` for each registry. You may keep immutable configuration parameters on the registrar.

### Error 2: writing a registrar and forgetting to invoke it

Merely implementing `PropertyEditorRegistrar` does not make Spring auto-discover and register editors. You must invoke `registerCustomEditors(...)` or wire the registrar into `@InitBinder`, `CustomEditorConfigurer`, or an equivalent mechanism.

### Error 3: importing the wrong PropertyEditor package

The editor interface is **`java.beans.PropertyEditor`**; registrar and registry live in **`org.springframework.beans.*`**. `PropertyEditorSupport` belongs to the JDK, not Spring.

### Error 4: registering in the wrong scope

The IoC container configurer primarily assists value conversion when the bean factory instantiates/configures beans. It does not replace configuring a controller's `WebDataBinder`. Conversely, a controller's `@InitBinder` does not configure every bean in `ApplicationContext`.

### Error 5: mutating editor state across concurrent requests

`setAsText` and `setValue` mutate state. If multiple requests use the same editor instance, current values can be overwritten. Thread-safe sharing applies to stateless registrars, **not mutable editors**.

### Error 6: mishandling null, empty, and whitespace

Strings `null`, `""`, and `"   "` can carry different business meanings. The example converts all three to `null`. Yet that is just the example's choice; each application must decide explicitly whether a field is required, has a default, or allows clearing its value.

### Error 7: parse errors crashing unexpectedly

`setAsText` can throw `IllegalArgumentException` on malformed strings. With `DataBinder`, conversion errors are normally recorded as `FieldError`s; with direct `BeanWrapper.setPropertyValue`, errors are thrown to the caller. Catch/read results per the API and never swallow errors and continue processing invalid data.

### Error 8: overlooking custom editors when switching to ConversionService

An application may have multiple conversion sources: default editors, custom editors, ConversionService, formatters, and annotations. If one type is registered in multiple places, precedence behavior can surprise you. Test the real binding path instead of only testing a converter manually.

### Error 9: implementing getAsText while forgetting setAsText

`getAsText` handles representing a value as a string; `setAsText` handles parsing a string into an object. For bidirectional editing/form rendering, both often need consistent implementation. If only parsing form input, do not assume `PropertyEditorSupport#getAsText`'s default always produces the format you want.

### Error 10: putting validation/authorization inside editors improperly

Checking `AA-999` syntax inside the editor makes sense for conversion. Checking whether the code is authorized for the user or exists in the database should not be treated as the registrar's job. Separate conversion from domain validation and authorization.

### Error 11: registering an editor for all Strings

Global registration for `String.class` can affect unrelated properties with different contracts. Register by specific domain type or field path, or use a formatter/converter with clear policies.

### Error 12: failing to test multiple registries

Testing `OrderCodeEditor` alone can still miss forgetting to register the editor on a specific `WebDataBinder` or `BeanWrapper`. Test every context your application relies on: bean factory, wrapper, controller/advice, valid binding, and invalid binding.

## 11. Checklist and Self-Check Exercises

**Checklist for implementing a reusable registrar:**

1. Identify the domain type that request strings must convert into; narrow type/path scope.
2. Write a `PropertyEditorSupport` with `setAsText`, `getAsText`, and contract-compliant null/invalid handling.
3. Create a stateless class implementing `PropertyEditorRegistrar`.
4. Inside **each** `registerCustomEditors(registry)` call, invoke `new` to create fresh editors, never a singleton editor.
5. Register in the right scope: `BeanWrapper`, `DataBinder`, `@InitBinder`, or `CustomEditorConfigurer`.
6. For external requests, apply DTOs/allowed fields and independent authorization rules.
7. Test valid, invalid, and empty data; verify conversion errors and ensure no state is shared across binders.
8. For new implementations, evaluate whether `Converter`/`Formatter` with `ConversionService` is a better fit.

**Self-check questions:**

1. Why can a `PropertyEditorRegistrar` be a singleton while a `PropertyEditor` should not be shared?
2. How does `PropertyEditorRegistry` differ from `PropertyEditorRegistrar`?
3. How do `registerCustomEditor(OrderCode.class, editor)` and the overload adding `"orderForm.orderCode"` differ in scope? What property path name should you verify against the actual registry?
4. Does `CustomEditorConfigurer` automatically guarantee every `@ModelAttribute` in Spring MVC uses the same editor?
5. When `DataBinder.bind(...)` receives `"invalid"`, is the error **conversion** or **business validation**?
6. Why keep the `AA-999` formatting rule in the editor while keeping order modification permissions in the service/security layer?
7. If an app has many controllers needing the same editor, how do you reduce `@InitBinder` repetition while ensuring each binder gets a fresh editor?
8. In a greenfield project, why might you prefer `Converter<String,OrderCode>` over `PropertyEditorSupport`?

**Remember:** `PropertyEditorRegistrar` is a reusable **registration blueprint**; every time it receives a registry, instantiate **fresh editor instances** and register them by type or property path. When sharing rules between a bean factory and web binders, **register in each required scope**. A registrar never replaces binding, validation, or authorization.

## Official Documentation

- [Spring Framework Reference — Data Binding / PropertyEditorRegistrar](https://docs.spring.io/spring-framework/reference/core/validation/data-binding.html)
- [Spring Framework Javadoc — PropertyEditorRegistrar](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/beans/PropertyEditorRegistrar.html)
- [Spring Framework Javadoc — PropertyEditorRegistry](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/beans/PropertyEditorRegistry.html)
- [Spring Framework Javadoc — DataBinder](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/validation/DataBinder.html)
- [Spring Framework Javadoc — CustomEditorConfigurer](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/beans/factory/config/CustomEditorConfigurer.html)
- [Spring Framework MVC Reference — @InitBinder](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-initbinder.html)
- [Spring Framework WebFlux Reference — DataBinder](https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-initbinder.html)
- [Oracle Java SE — PropertyEditor](https://docs.oracle.com/en/java/javase/17/docs/api/java.desktop/java/beans/PropertyEditor.html)
- [Oracle Java SE — PropertyEditorSupport](https://docs.oracle.com/en/java/javase/17/docs/api/java.desktop/java/beans/PropertyEditorSupport.html)